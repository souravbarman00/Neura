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

"""Read-only semantic-search CodedTool over the configured vector index (P1-T4).

READ-ONLY BY CONSTRUCTION: this module never imports or calls
``add_documents`` / ``delete`` / ``upsert``. Non-secret selection (backend,
index, namespace, embedding model/dimensions, top_k) is taken from ``args``
(HOCON operator config) and PREFERS ``args`` over ``sly_data``; secrets
(host/creds/api keys/endpoints) come ONLY from ``sly_data``. The output shape
matches ``base_rag.query_retriever`` (``[{content, metadata}]``) so agent
prompts are unchanged.
"""

from __future__ import annotations

import logging
from typing import Any
from typing import Dict

from neuro_san.interfaces.coded_tool import CodedTool

import toolbox.vector_backends as vector_backends

logger = logging.getLogger(__name__)


class VectorSearchTool(CodedTool):
    """Semantic search over the configured vector index; returns passages."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        """Run a read-only similarity search and return matching passages.

        :param args: Non-secret selection (HOCON operator config). Recognized
            keys: ``query``, ``top_k``, ``backend``, ``index``, ``namespace``,
            ``embedding_provider``, ``embedding_model``, ``embedding_dimensions``.
        :param sly_data: Secrets. ``sly_data["vector_store"]`` holds the
            connection (host/port/user/password/database/api_key/endpoint and
            optional ``backend``/``index``/``namespace``);
            ``sly_data["embeddings"]`` holds the embedding provider api_key.
        :return: ``[{"content": str, "metadata": dict}]`` on success, or a
            concise tool-error string / dict on failure.
        """
        query: str = (args.get("query") or "").strip()
        if not query:
            return "Missing required input: 'query'."

        top_k: int = int(args.get("top_k") or 5)

        # SECRETS: connection comes only from sly_data.
        conn: Dict[str, Any] = dict((sly_data or {}).get("vector_store") or {})

        # NON-secret selection prefers args (HOCON) over sly_data.
        backend: str = args.get("backend") or conn.get("backend") or "pgvector"
        if args.get("index"):
            conn["index"] = args["index"]
        if args.get("namespace"):
            conn["namespace"] = args["namespace"]

        if not conn:
            return {
                "error": (
                    f"Vector store '{backend}' not configured. "
                    "Configure the connection."
                )
            }

        # Non-secret embedding selection from args; secret api_key from sly_data.
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

        try:
            emb = vector_backends.get_embeddings(embed_cfg)
            vs = await vector_backends.get_vectorstore(backend, conn, emb)
            # FAIL LOUD before returning any results on a contract mismatch.
            await vector_backends.verify_embedding_contract(vs, backend, embed_cfg)
            docs = await vs.asimilarity_search(query, k=top_k)
        except ValueError as error:
            # Unknown backend/provider or embedding-contract mismatch.
            logger.error("vector_search configuration/contract error: %s", error)
            return f"Vector search error: {error}"
        except Exception as error:  # noqa: BLE001 — surface ops errors to the agent
            logger.error("vector_search operational error: %s", error)
            return f"Vector search failed: {error}"

        return [{"content": d.page_content, "metadata": d.metadata} for d in docs]
