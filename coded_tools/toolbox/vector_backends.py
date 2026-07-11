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

"""Shared vector-backend factory for the ALIVE plugin layer.

Single source of truth for embeddings / text-splitting / vector-store
construction and the embedding contract. Backend adapters are imported with
DOTTED submodule imports (``from toolbox.vectorstores.pgvector import ...``) so
the exporter's ``ast.walk`` vendors each adapter file (BUG-2). Never collapse
these to package-form imports.
"""

from __future__ import annotations

import logging

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

# DOTTED submodule imports — REQUIRED so the exporter's ast.walk vendors each
# adapter (BUG-2). Do NOT rewrite as `from toolbox.vectorstores import pgvector`.
from toolbox.vectorstores.pgvector import (
    build as _pg_build,
    fetch_hashes as _pg_fetch,
    upsert as _pg_upsert,
    read_contract as _pg_rc,
    write_contract as _pg_wc,
)
from toolbox.vectorstores.chroma import (
    build as _ch_build,
    fetch_hashes as _ch_fetch,
    upsert as _ch_upsert,
    read_contract as _ch_rc,
    write_contract as _ch_wc,
)
from toolbox.vectorstores.pinecone import (
    build as _pc_build,
    fetch_hashes as _pc_fetch,
    upsert as _pc_upsert,
    read_contract as _pc_rc,
    write_contract as _pc_wc,
)
from toolbox.vectorstores.azure_ai_search import (
    build as _az_build,
    fetch_hashes as _az_fetch,
    upsert as _az_upsert,
    read_contract as _az_rc,
    write_contract as _az_wc,
)
from toolbox.vectorstores.in_memory import (
    build as _im_build,
    fetch_hashes as _im_fetch,
    upsert as _im_upsert,
    read_contract as _im_rc,
    write_contract as _im_wc,
)

_LOG = logging.getLogger(__name__)

DEFAULT_BACKEND = "pgvector"
DEFAULT_EMBED_MODEL = "text-embedding-3-small"
DEFAULT_DIMS = 1536  # back-compat with base_rag VECTOR_SIZE
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200  # replaces base_rag's 100/50

# tuple = (build, fetch_hashes, upsert, read_contract, write_contract)
_ADAPTERS = {
    "pgvector": (_pg_build, _pg_fetch, _pg_upsert, _pg_rc, _pg_wc),
    "chroma": (_ch_build, _ch_fetch, _ch_upsert, _ch_rc, _ch_wc),
    "pinecone": (_pc_build, _pc_fetch, _pc_upsert, _pc_rc, _pc_wc),
    "azure_ai_search": (_az_build, _az_fetch, _az_upsert, _az_rc, _az_wc),
    "in_memory": (_im_build, _im_fetch, _im_upsert, _im_rc, _im_wc),
}


def _adapter(backend: str):
    """Return the adapter tuple for ``backend`` (defaulting when falsy)."""
    entry = _ADAPTERS.get((backend or DEFAULT_BACKEND).lower())
    if entry is None:
        raise ValueError(
            f"Unknown vector backend '{backend}'. Options: {sorted(_ADAPTERS)}"
        )
    return entry


def get_embeddings(cfg: dict) -> Embeddings:
    """Construct an ``Embeddings`` from a (non-secret + secret) config dict."""
    cfg = cfg or {}
    provider = (cfg.get("provider") or "openai").lower()
    model = cfg.get("model") or DEFAULT_EMBED_MODEL
    dims = int(cfg.get("dimensions") or DEFAULT_DIMS)
    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=model, dimensions=dims, api_key=cfg.get("api_key") or None
        )
    if provider == "azure_openai":
        from langchain_openai import AzureOpenAIEmbeddings

        return AzureOpenAIEmbeddings(
            model=model,
            azure_endpoint=cfg.get("endpoint"),
            api_key=cfg.get("api_key") or None,
        )
    if provider in ("google", "google_genai"):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(model=model)
    raise ValueError(f"Unknown embeddings provider '{provider}'")


def get_splitter(cfg: dict | None = None):
    """Build a ``RecursiveCharacterTextSplitter`` (tiktoken encoder by default)."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    cfg = cfg or {}
    size = int(cfg.get("size") or DEFAULT_CHUNK_SIZE)
    overlap = int(cfg.get("overlap") or DEFAULT_CHUNK_OVERLAP)
    if (cfg.get("encoder") or "tiktoken") == "tiktoken":
        return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=size, chunk_overlap=overlap
        )
    return RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)


async def get_vectorstore(
    backend: str, conn: dict, embeddings: Embeddings
) -> VectorStore:
    """Build a live vector store for ``backend`` (adapter lazy-imports its lib)."""
    build, *_ = _adapter(backend)
    return await build(conn, embeddings)


def content_hash(text: str) -> str:
    """Stable content hash used for idempotent upserts."""
    import hashlib

    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def doc_id_for(doc) -> str:
    """Derive a stable document id from common metadata keys, else content."""
    md = getattr(doc, "metadata", {}) or {}
    return str(
        md.get("doc_id")
        or md.get("source")
        or md.get("file_path")
        or md.get("url")
        or md.get("id")
        or content_hash(doc.page_content)[:16]
    )


def contract_for(embed_cfg: dict) -> dict:
    """Build the embedding contract recorded on / verified against an index."""
    embed_cfg = embed_cfg or {}
    return {
        "provider": (embed_cfg.get("provider") or "openai").lower(),
        "model": embed_cfg.get("model") or DEFAULT_EMBED_MODEL,
        "dimensions": int(embed_cfg.get("dimensions") or DEFAULT_DIMS),
        # index-mode disambiguation for Pinecone (B1): client-side embeddings vs
        # integrated inference.
        "mode": embed_cfg.get("mode") or "client_embeddings",
    }


async def fetch_hashes(backend: str, vs, ids: list[str]) -> dict:
    """Return ``{id: content_hash}`` for ``ids`` via the backend adapter.

    Thin public wrapper (mirrors the contract helpers) so ingest callers never
    reach into the private adapter tuple.
    """
    _build, fetch, *_ = _adapter(backend)
    return await fetch(vs, ids)


async def upsert(backend: str, vs, docs, ids) -> None:
    """Upsert ``docs`` under ``ids`` via the backend adapter (replace-by-id)."""
    _build, _fetch, up, *_ = _adapter(backend)
    await up(vs, docs, ids)


async def write_embedding_contract(vs, backend: str, meta: dict) -> None:
    """Persist the embedding contract on the backend's index."""
    *_, wc = _adapter(backend)
    await wc(vs, meta)


async def verify_embedding_contract(vs, backend: str, embed_cfg: dict) -> None:
    """Fail loud on a contract mismatch; warn + skip when none is stored (M5)."""
    *_, rc, _wc = _adapter(backend)
    stored = await rc(vs)
    want = contract_for(embed_cfg)
    if stored is None:
        _LOG.warning(
            "No embedding contract stored on '%s' index; skipping verification "
            "(legacy/pre-contract index). Expected %s.",
            backend,
            want,
        )
        return
    if stored != want:
        raise ValueError(
            f"Embedding contract mismatch on '{backend}': index built with {stored}, "
            f"query wants {want}. Re-ingest or fix the retriever config."
        )
