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

"""In-memory vector-store adapter.

The always-green dev/demo/CI fallback: requires no external service. Wraps
``langchain_community.vectorstores.InMemoryVectorStore``. The embedding contract
is stored on an instance attribute; ``fetch_hashes`` scans the store's metadata;
``upsert`` is a delete-by-id followed by ``aadd_documents``.
"""

from __future__ import annotations

from typing import Any

# Attribute used to stash the embedding contract on the store instance.
_CONTRACT_ATTR = "_alive_embedding_contract"


async def build(conn: dict, embeddings: Any):
    """Return a fresh in-memory vector store bound to ``embeddings``."""
    # Lazy import keeps parity with the other adapters (and avoids the
    # community deprecation warning at module import time).
    from langchain_community.vectorstores import InMemoryVectorStore

    return InMemoryVectorStore(embedding=embeddings)


async def fetch_hashes(vs, ids: list[str]) -> dict[str, str]:
    """Return ``{id: content_hash}`` for the requested ids present in the store."""
    store = getattr(vs, "store", {}) or {}
    wanted = set(ids or [])
    out: dict[str, str] = {}
    for rec_id, record in store.items():
        if rec_id not in wanted:
            continue
        metadata = (record or {}).get("metadata") or {}
        chash = metadata.get("content_hash")
        if chash is not None:
            out[rec_id] = str(chash)
    return out


async def upsert(vs, docs, ids) -> None:
    """Replace-by-id: delete the ids, then add the documents under those ids."""
    if ids:
        # Only delete ids that already exist to avoid backend-specific errors.
        store = getattr(vs, "store", {}) or {}
        existing = [i for i in ids if i in store]
        if existing:
            await vs.adelete(ids=existing)
    await vs.aadd_documents(list(docs), ids=list(ids) if ids else None)


async def read_contract(vs) -> dict | None:
    """Return the stored embedding contract, or ``None`` if never written."""
    return getattr(vs, _CONTRACT_ATTR, None)


async def write_contract(vs, meta: dict) -> None:
    """Persist the embedding contract on the store instance."""
    setattr(vs, _CONTRACT_ATTR, dict(meta))
