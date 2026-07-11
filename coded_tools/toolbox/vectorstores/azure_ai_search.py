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

"""Azure AI Search vector-store adapter.

Wraps ``langchain_community.vectorstores.azuresearch.AzureSearch``. Both that
import AND ``azure.search.documents.indexes.SearchIndexClient`` are performed
inside ``build`` (H2/H3): the second physical import is what makes the exporter
discover ``azure`` — resolved to ``azure-search-documents`` via
``_VECTOR_BACKEND_PIP`` only, never the generic pip heuristic.

The embedding contract is stored as an index-level metadata document with the
reserved key ``__alive_contract__``.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

_LOG = logging.getLogger(__name__)

# Azure Search document keys may not start with an underscore, so this reserved
# key intentionally has no leading underscore.
_CONTRACT_ID = "alive_embedding_contract_doc"


async def build(conn: dict, embeddings: Any):
    """Return an AzureSearch vector store bound to ``embeddings``."""
    # Import smoke (H2): both must resolve for this backend to be usable.
    from langchain_community.vectorstores.azuresearch import AzureSearch
    from azure.search.documents.indexes import SearchIndexClient  # noqa: F401

    index = conn.get("index") or conn.get("index_name") or "vectorstore"
    return AzureSearch(
        azure_search_endpoint=conn["endpoint"],
        azure_search_key=conn.get("api_key") or conn.get("key"),
        index_name=index,
        embedding_function=embeddings.embed_query,
    )


def _search_client(vs):
    client = getattr(vs, "client", None)
    if client is None:
        raise RuntimeError("Could not resolve the Azure SearchClient for this store.")
    return client


def _safe_key(raw: str) -> str:
    """Encode an arbitrary chunk id into an Azure Search-legal document key.

    Azure Search keys allow only ``[A-Za-z0-9_-=]``; chunk ids can contain
    ``#`` / ``/`` / ``:`` / ``.`` (doc_id#index, URLs, paths). URL-safe base64
    maps into exactly that alphabet and is deterministic, so ``upsert`` and
    ``fetch_hashes`` stay consistent.
    """
    return base64.urlsafe_b64encode(str(raw).encode("utf-8")).decode("ascii")


async def fetch_hashes(vs, ids: list[str]) -> dict[str, str]:
    """Return ``{id: content_hash}`` for the requested ids via ``get_document``."""
    if not ids:
        return {}
    # Only a genuine "document not present" is benign; auth/connection errors
    # must propagate (never swallow them in a blanket except).
    from azure.core.exceptions import ResourceNotFoundError

    client = _search_client(vs)
    out: dict[str, str] = {}
    for key in ids:
        try:
            doc = client.get_document(key=_safe_key(key))
        except ResourceNotFoundError:
            continue
        metadata = doc.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        metadata = metadata or {}
        chash = metadata.get("content_hash")
        if chash is not None:
            out[str(key)] = str(chash)
    return out


async def upsert(vs, docs, ids) -> None:
    """Upsert-by-key — Azure Search merge-or-upload replaces existing keys."""
    vs.add_documents(documents=list(docs), keys=[_safe_key(i) for i in ids])


async def read_contract(vs) -> dict | None:
    """Return the stored embedding contract from the metadata doc, or ``None``."""
    # A missing contract doc is benign (returns None -> M5 warn/skip); any
    # auth/connection failure must propagate rather than silently disable the
    # embedding-contract safety check.
    from azure.core.exceptions import ResourceNotFoundError

    client = _search_client(vs)
    try:
        doc = client.get_document(key=_CONTRACT_ID)
    except ResourceNotFoundError:
        return None
    metadata = doc.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            return None
    metadata = metadata or {}
    raw = metadata.get("alive_embedding_contract")
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


async def write_contract(vs, meta: dict) -> None:
    """Persist the embedding contract as an index-level metadata document."""
    client = _search_client(vs)
    document = {
        "id": _CONTRACT_ID,
        "content": "",
        "metadata": json.dumps({"alive_embedding_contract": json.dumps(meta)}),
    }
    client.merge_or_upload_documents(documents=[document])
