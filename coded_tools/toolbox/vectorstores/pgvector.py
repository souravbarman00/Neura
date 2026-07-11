# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT

"""pgvector (PostgreSQL) vector-store adapter — the default backend.

Adapted from ``base_rag._create_postgres_vector_store``. Uses
``langchain_postgres.PGEngine`` / ``PGVectorStore`` over a
``postgresql+asyncpg`` URL. All SQL is parameterized; table/index names come
from the operator connection config only. The embedding contract lives in a
dedicated ``_alive_index_meta`` table.

Exception handling is narrow (M3): only "table already exists" style errors are
swallowed during table init; auth/connection/permission errors propagate.
"""

from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger(__name__)

# Private attributes stashed on the returned store so the helper coroutines can
# reach the engine / table name without reverse-engineering langchain internals.
_ENGINE_ATTR = "_alive_pg_engine"
_TABLE_ATTR = "_alive_pg_table"

# Metadata table holding the per-index embedding contract.
_META_TABLE = "_alive_index_meta"


def _connection_url(conn: dict) -> str:
    """Build a ``postgresql+asyncpg`` URL from the operator connection config."""
    port = conn.get("port", 5432)
    return (
        f"postgresql+asyncpg://{conn['user']}:{conn['password']}"
        f"@{conn['host']}:{port}/{conn['database']}"
    )


def _table_name(conn: dict) -> str:
    return conn.get("index") or conn.get("table_name") or "vectorstore"


def _sa_engine(pg_engine):
    """Return the underlying SQLAlchemy AsyncEngine wrapped by a ``PGEngine``."""
    engine = getattr(pg_engine, "_pool", None) or getattr(pg_engine, "pool", None)
    if engine is None:
        raise RuntimeError("Could not resolve the SQLAlchemy engine from the PGEngine.")
    return engine


async def build(conn: dict, embeddings: Any):
    """Connect, create the vectorstore table if missing, return a live store."""
    # ast.walk discovers "langchain_postgres" and "asyncpg" here.
    from langchain_postgres import PGEngine, PGVectorStore
    import asyncpg  # noqa: F401  -- ensures the exporter records the "asyncpg" dep

    url = _connection_url(conn)
    engine = PGEngine.from_connection_string(url=url)
    table = _table_name(conn)
    dims = int(conn.get("dimensions") or 1536)

    try:
        await engine.ainit_vectorstore_table(table_name=table, vector_size=dims)
    except Exception as exc:  # noqa: BLE001 -- narrowed below; re-raised otherwise (M3)
        from sqlalchemy.exc import ProgrammingError

        try:
            from asyncpg.exceptions import DuplicateTableError
        except (
            Exception
        ):  # pragma: no cover - asyncpg always present alongside langchain_postgres
            DuplicateTableError = ()  # type: ignore[assignment]

        msg = str(exc).lower()
        if (
            isinstance(exc, ProgrammingError)
            or isinstance(exc, DuplicateTableError)
            or "already exists" in msg
        ):
            _LOG.info("pgvector table '%s' already exists; reusing it.", table)
        else:
            # Auth / connection / permission errors must surface, not degrade.
            raise

    store = await PGVectorStore.create(
        engine=engine, table_name=table, embedding_service=embeddings
    )
    # Stash for the helper coroutines (best-effort; helpers also re-derive).
    try:
        object.__setattr__(store, _ENGINE_ATTR, engine)
        object.__setattr__(store, _TABLE_ATTR, table)
    except Exception:  # pragma: no cover - pydantic models may reject attr set
        _LOG.debug("Could not stash engine/table on the PGVectorStore instance.")
    return store


def _engine_and_table(vs):
    """Resolve the PGEngine and table name for a built store."""
    engine = (
        getattr(vs, _ENGINE_ATTR, None)
        or getattr(vs, "_engine", None)
        or getattr(vs, "engine", None)
    )
    table = (
        getattr(vs, _TABLE_ATTR, None)
        or getattr(vs, "_table_name", None)
        or getattr(vs, "table_name", None)
    )
    if engine is None or not table:
        raise RuntimeError(
            "Could not resolve the pgvector engine/table for this store."
        )
    return engine, table


async def fetch_hashes(vs, ids: list[str]) -> dict[str, str]:
    """Return ``{id: content_hash}`` for the requested ids (parameterized query)."""
    if not ids:
        return {}
    from sqlalchemy import text

    engine, table = _engine_and_table(vs)
    sa_engine = _sa_engine(engine)
    # Table name is operator-controlled config, never LLM input; values are bound.
    sql = text(
        f"SELECT langchain_id AS id, langchain_metadata->>'content_hash' AS content_hash "  # noqa: E501
        f'FROM "{table}" WHERE langchain_id = ANY(:ids)'
    )
    out: dict[str, str] = {}
    async with sa_engine.connect() as connection:
        result = await connection.execute(sql, {"ids": list(ids)})
        for row in result.mappings():
            if row["content_hash"] is not None:
                out[str(row["id"])] = str(row["content_hash"])
    return out


async def upsert(vs, docs, ids) -> None:
    """Explicit replace-by-id then add — avoids duplicate-id IntegrityError."""
    from sqlalchemy import text

    engine, table = _engine_and_table(vs)
    if ids:
        sa_engine = _sa_engine(engine)
        sql = text(f'DELETE FROM "{table}" WHERE langchain_id = ANY(:ids)')
        async with sa_engine.begin() as connection:
            await connection.execute(sql, {"ids": list(ids)})
    await vs.aadd_documents(list(docs), ids=list(ids) if ids else None)


async def _ensure_meta_table(sa_engine) -> None:
    from sqlalchemy import text

    async with sa_engine.begin() as connection:
        await connection.execute(
            text(
                f'CREATE TABLE IF NOT EXISTS "{_META_TABLE}" (index text PRIMARY KEY, meta jsonb)'
            )
        )


async def read_contract(vs) -> dict | None:
    """Return the stored embedding contract for this index, or ``None``."""
    from sqlalchemy import text

    engine, table = _engine_and_table(vs)
    sa_engine = _sa_engine(engine)
    await _ensure_meta_table(sa_engine)
    sql = text(f'SELECT meta FROM "{_META_TABLE}" WHERE index = :index')
    async with sa_engine.connect() as connection:
        result = await connection.execute(sql, {"index": table})
        row = result.first()
    if row is None:
        return None
    meta = row[0]
    if isinstance(meta, str):
        import json

        return json.loads(meta)
    return dict(meta) if meta is not None else None


async def write_contract(vs, meta: dict) -> None:
    """Upsert the embedding contract for this index (parameterized)."""
    import json

    from sqlalchemy import text

    engine, table = _engine_and_table(vs)
    sa_engine = _sa_engine(engine)
    await _ensure_meta_table(sa_engine)
    sql = text(
        f'INSERT INTO "{_META_TABLE}" (index, meta) VALUES (:index, CAST(:meta AS jsonb)) '
        f"ON CONFLICT (index) DO UPDATE SET meta = EXCLUDED.meta"
    )
    async with sa_engine.begin() as connection:
        await connection.execute(sql, {"index": table, "meta": json.dumps(meta)})
