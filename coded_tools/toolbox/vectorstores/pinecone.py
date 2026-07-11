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

"""Pinecone vector-store adapter — client-side embeddings.

ALIVE embeds text on the client (``PineconeVectorStore(index, embedding=...)``)
and records ``mode="client_embeddings"`` in the embedding contract. This is
deliberately incompatible with integrated-inference indexes: if a fetched record
carries no ``content_hash`` we raise a clear error (B1) rather than silently
mixing embedding regimes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_LOG = logging.getLogger(__name__)

# Sentinel record id holding the embedding contract metadata.
_CONTRACT_ID = "__alive_contract__"
_CONTRACT_KEY = "alive_embedding_contract"

_INDEX_ATTR = "_alive_pc_index"
_NS_ATTR = "_alive_pc_namespace"


async def build(conn: dict, embeddings: Any):
    """Return a PineconeVectorStore configured for client-side embeddings."""
    from langchain_pinecone import PineconeVectorStore
    from pinecone import Pinecone

    pc = Pinecone(api_key=conn["api_key"])
    index = pc.Index(host=conn["host"]) if conn.get("host") else pc.Index(conn["index"])
    namespace = conn.get("namespace") or ""
    store = PineconeVectorStore(index=index, embedding=embeddings, namespace=namespace)
    try:
        object.__setattr__(store, _INDEX_ATTR, index)
        object.__setattr__(store, _NS_ATTR, namespace)
    except Exception:  # pragma: no cover
        _LOG.debug(
            "Could not stash index/namespace on the PineconeVectorStore instance."
        )
    return store


def _index_and_ns(vs):
    index = getattr(vs, _INDEX_ATTR, None) or getattr(vs, "_index", None)
    namespace = getattr(vs, _NS_ATTR, None)
    if namespace is None:
        namespace = getattr(vs, "_namespace", "") or ""
    if index is None:
        raise RuntimeError("Could not resolve the Pinecone index for this store.")
    return index, namespace


async def fetch_hashes(vs, ids: list[str]) -> dict[str, str]:
    """Return ``{id: content_hash}``; reject integrated-inference indexes (B1)."""
    if not ids:
        return {}
    index, namespace = _index_and_ns(vs)
    fetched = index.fetch(ids=list(ids), namespace=namespace)
    vectors = getattr(fetched, "vectors", None)
    if vectors is None and isinstance(fetched, dict):
        vectors = fetched.get("vectors") or {}
    out: dict[str, str] = {}
    for rec_id, record in (vectors or {}).items():
        metadata = getattr(record, "metadata", None)
        if metadata is None and isinstance(record, dict):
            metadata = record.get("metadata")
        metadata = metadata or {}
        if "content_hash" not in metadata:
            raise ValueError(
                "Pinecone record has no 'content_hash' metadata: this index was built in "
                "integrated-inference mode and is incompatible with ALIVE's client-side "
                "embeddings (mode=client_embeddings). Re-create the index for client-side "
                "embeddings, or use a matching retriever."
            )
        out[str(rec_id)] = str(metadata["content_hash"])
    return out


async def upsert(vs, docs, ids) -> None:
    """Upsert-by-id (a genuine replace on Pinecone) via the client-side embedder."""
    index, namespace = _index_and_ns(vs)
    await vs.aadd_documents(list(docs), ids=list(ids), namespace=namespace)


async def read_contract(vs) -> dict | None:
    """Return the stored embedding contract from the sentinel record, or ``None``."""
    index, namespace = _index_and_ns(vs)
    fetched = index.fetch(ids=[_CONTRACT_ID], namespace=namespace)
    vectors = getattr(fetched, "vectors", None)
    if vectors is None and isinstance(fetched, dict):
        vectors = fetched.get("vectors") or {}
    record = (vectors or {}).get(_CONTRACT_ID)
    if record is None:
        return None
    metadata = getattr(record, "metadata", None)
    if metadata is None and isinstance(record, dict):
        metadata = record.get("metadata")
    metadata = metadata or {}
    raw = metadata.get(_CONTRACT_KEY)
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


async def write_contract(vs, meta: dict) -> None:
    """Persist the contract on a sentinel record and cross-check the index dims."""
    index, namespace = _index_and_ns(vs)
    stats = index.describe_index_stats()
    dimension = getattr(stats, "dimension", None)
    if dimension is None and isinstance(stats, dict):
        dimension = stats.get("dimension")
    want_dims = meta.get("dimensions")
    if (
        dimension is not None
        and want_dims is not None
        and int(dimension) != int(want_dims)
    ):
        raise ValueError(
            f"Pinecone index dimension {dimension} does not match the embedding "
            f"contract dimensions {want_dims}."
        )
    zero_vector = [0.0] * int(dimension or want_dims or 1)
    index.upsert(
        vectors=[
            {
                "id": _CONTRACT_ID,
                "values": zero_vector,
                "metadata": {_CONTRACT_KEY: json.dumps(meta)},
            }
        ],
        namespace=namespace,
    )
