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

"""Write-path ingest CodedTool (P1-T5) — OPS / INGEST tool, NOT chat-exposed.

This is a deliberately THIN wrapper around the WI1 vector-backend factory: it
loads inline documents, writes the embedding contract, splits, hashes, and does
an INCREMENTAL (skip-unchanged) upsert through the backend adapter. It is kept
out of the Designer toolbox so a chat network never wires it in.

The full decoupled connector/CLI ingestion pipeline (multiple source loaders,
manifests, deletions/reconciliation) is P2-T1; this tool only covers the inline
document / simple-source case the demo endpoint (P2-T5) needs.

Secrets (host/creds/api keys/endpoints) come ONLY from ``sly_data``. Non-secret
selection (backend/index/namespace/embedding model+dims/chunk params) is taken
from ``args`` (operator config) and PREFERS ``args`` over ``sly_data``.
"""

from __future__ import annotations

import logging
from typing import Any
from typing import Dict
from typing import List

from langchain_core.documents import Document
from neuro_san.interfaces.coded_tool import CodedTool

import toolbox.vector_backends as vector_backends

logger = logging.getLogger(__name__)


def _normalize_documents(raw: Any) -> List[Document]:
    """Coerce inline ``documents``/``sources`` args into ``Document`` objects.

    Accepts a list of ``Document``, ``{content|page_content, metadata}`` dicts,
    or bare strings.
    """
    docs: List[Document] = []
    for item in raw or []:
        if isinstance(item, Document):
            docs.append(item)
        elif isinstance(item, str):
            docs.append(Document(page_content=item, metadata={}))
        elif isinstance(item, dict):
            content = item.get("content")
            if content is None:
                content = item.get("page_content") or ""
            metadata = dict(item.get("metadata") or {})
            docs.append(Document(page_content=content, metadata=metadata))
    return docs


class VectorIngestTool(CodedTool):
    """Ops/ingest tool: incrementally upsert documents into the vector index.

    Not intended for the chat LLM — this is an operator/ingest path.
    """

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        """Ingest inline documents into the configured vector store.

        :param args: Non-secret selection + payload. Recognized keys:
            ``documents`` (or ``sources``) — list of
            ``{content|page_content, metadata}`` / strings; ``backend``,
            ``index``, ``namespace``, ``embedding_provider``,
            ``embedding_model``, ``embedding_dimensions``, ``chunk_size``,
            ``chunk_overlap``.
        :param sly_data: Secrets. ``sly_data["vector_store"]`` holds the
            connection; ``sly_data["embeddings"]`` holds the embedding api_key.
        :return: An ingestion report dict
            ``{backend, index, added, updated, skipped, deleted, chunks,
            failures}``.
        """
        docs = _normalize_documents(args.get("documents") or args.get("sources"))
        if not docs:
            return "Missing required input: 'documents' (or 'sources')."

        # SECRETS: connection only from sly_data.
        conn: Dict[str, Any] = dict((sly_data or {}).get("vector_store") or {})

        # NON-secret selection prefers args (operator config).
        backend: str = args.get("backend") or conn.get("backend") or "pgvector"
        if args.get("index"):
            conn["index"] = args["index"]
        if args.get("namespace"):
            conn["namespace"] = args["namespace"]
        index = conn.get("index") or args.get("index")

        embed_cfg: Dict[str, Any] = {
            k: v
            for k, v in {
                "provider": args.get("embedding_provider"),
                "model": args.get("embedding_model"),
                "dimensions": args.get("embedding_dimensions"),
            }.items()
            if v is not None
        }
        embed_cfg = {**embed_cfg, **((sly_data or {}).get("embeddings") or {})}

        chunk_cfg: Dict[str, Any] = {
            k: v
            for k, v in {
                "size": args.get("chunk_size"),
                "overlap": args.get("chunk_overlap"),
                "encoder": args.get("chunk_encoder"),
            }.items()
            if v is not None
        }

        report: Dict[str, Any] = {
            "backend": backend,
            "index": index,
            "added": 0,
            "updated": 0,
            "skipped": 0,
            "deleted": 0,
            "chunks": 0,
            "failures": [],
        }

        try:
            emb = vector_backends.get_embeddings(embed_cfg)
            vs = await vector_backends.get_vectorstore(backend, conn, emb)
            # Write the embedding contract on (first) write so later reads verify.
            await vector_backends.write_embedding_contract(
                vs, backend, vector_backends.contract_for(embed_cfg)
            )

            splitter = vector_backends.get_splitter(chunk_cfg)
            chunks: List[Document] = splitter.split_documents(docs)
            report["chunks"] = len(chunks)
            if not chunks:
                return report

            # Stable per-chunk ids derived from the source doc id + position
            # (NOT content), so a changed chunk keeps its id and counts as an
            # update rather than an add. content_hash drives skip-unchanged.
            ids: List[str] = []
            hashes: List[str] = []
            counter: Dict[str, int] = {}
            for chunk in chunks:
                base = vector_backends.doc_id_for(chunk)
                pos = counter.get(base, 0)
                counter[base] = pos + 1
                chunk_id = f"{base}#{pos}"
                chash = vector_backends.content_hash(chunk.page_content)
                chunk.metadata["doc_id"] = chunk_id
                chunk.metadata["content_hash"] = chash
                ids.append(chunk_id)
                hashes.append(chash)

            existing = await vector_backends.fetch_hashes(backend, vs, ids)

            upsert_docs: List[Document] = []
            upsert_ids: List[str] = []
            for chunk, chunk_id, chash in zip(chunks, ids, hashes):
                prev = existing.get(chunk_id)
                if prev is None:
                    report["added"] += 1
                    upsert_docs.append(chunk)
                    upsert_ids.append(chunk_id)
                elif prev != chash:
                    report["updated"] += 1
                    upsert_docs.append(chunk)
                    upsert_ids.append(chunk_id)
                else:
                    report["skipped"] += 1

            if upsert_ids:
                await vector_backends.upsert(backend, vs, upsert_docs, upsert_ids)
        except ValueError as error:
            # Unknown backend/provider or contract issue: fail loud but structured.
            logger.error("vector_ingest configuration error: %s", error)
            report["failures"].append(str(error))
        except Exception as error:  # noqa: BLE001 — surface ops errors in the report
            logger.error("vector_ingest operational error: %s", error)
            report["failures"].append(str(error))

        return report
