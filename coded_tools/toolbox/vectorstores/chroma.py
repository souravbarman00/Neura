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

"""Chroma vector-store adapter.

Wraps ``langchain_chroma.Chroma``. Uses an HTTP client when a host is
configured, otherwise a local persistent client. The embedding contract is
stored on the collection metadata; upserts use the Chroma-native collection API
(version-tolerant) so re-runs replace by id.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_LOG = logging.getLogger(__name__)

# Key under which the embedding contract JSON is stored in collection metadata.
_CONTRACT_KEY = "alive_embedding_contract"

_EMB_ATTR = "_alive_embeddings"


async def build(conn: dict, embeddings: Any):
    """Return a Chroma vector store backed by an HTTP or persistent client."""
    from langchain_chroma import Chroma
    import chromadb

    collection = conn.get("index") or conn.get("collection_name") or "vectorstore"
    if conn.get("host"):
        client = chromadb.HttpClient(
            host=conn["host"], port=int(conn.get("port") or 8000)
        )
    else:
        client = chromadb.PersistentClient(path=conn.get("path") or "./chroma")

    store = Chroma(
        client=client,
        collection_name=collection,
        embedding_function=embeddings,
    )
    try:
        object.__setattr__(store, _EMB_ATTR, embeddings)
    except Exception:  # pragma: no cover
        _LOG.debug("Could not stash embeddings on the Chroma store instance.")
    return store


def _collection(vs):
    collection = getattr(vs, "_collection", None) or getattr(vs, "collection", None)
    if collection is None:
        raise RuntimeError("Could not resolve the Chroma collection for this store.")
    return collection


async def fetch_hashes(vs, ids: list[str]) -> dict[str, str]:
    """Return ``{id: content_hash}`` for the requested ids."""
    if not ids:
        return {}
    collection = _collection(vs)
    got = collection.get(ids=list(ids), include=["metadatas"])
    out: dict[str, str] = {}
    result_ids = got.get("ids") or []
    metadatas = got.get("metadatas") or []
    for rec_id, metadata in zip(result_ids, metadatas):
        chash = (metadata or {}).get("content_hash")
        if chash is not None:
            out[str(rec_id)] = str(chash)
    return out


async def upsert(vs, docs, ids) -> None:
    """Replace-by-id via Chroma's native ``upsert`` (idempotent on re-run)."""
    collection = _collection(vs)
    embeddings = getattr(vs, _EMB_ATTR, None) or getattr(
        vs, "_embedding_function", None
    )
    texts = [d.page_content for d in docs]
    metadatas = [dict(getattr(d, "metadata", {}) or {}) for d in docs]
    vectors = None
    if embeddings is not None and hasattr(embeddings, "embed_documents"):
        vectors = embeddings.embed_documents(texts)
    collection.upsert(
        ids=list(ids),
        documents=texts,
        embeddings=vectors,
        metadatas=metadatas,
    )


async def read_contract(vs) -> dict | None:
    """Return the stored embedding contract from collection metadata, or ``None``."""
    collection = _collection(vs)
    metadata = getattr(collection, "metadata", None) or {}
    raw = metadata.get(_CONTRACT_KEY)
    if raw is None:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


async def write_contract(vs, meta: dict) -> None:
    """Persist the embedding contract onto the collection metadata."""
    collection = _collection(vs)
    existing = dict(getattr(collection, "metadata", None) or {})
    existing[_CONTRACT_KEY] = json.dumps(meta)
    collection.modify(metadata=existing)
