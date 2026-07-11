"""Neura local knowledge base — a private, on-device vector store.

Uses ChromaDB with its built-in on-device embedding model (all-MiniLM-L6-v2, ONNX).
Nothing in this module contacts the cloud: your documents are embedded and searched
entirely on your machine. Only the final answer composition (in the agent network)
may use a cloud LLM — and sensitive fields travel via neuro-san `sly_data`, never in
an LLM prompt.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

# Resolve the project root so paths work regardless of the current working directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_PERSIST_DIR = os.environ.get(
    "NEURA_CHROMA_DIR", str(_PROJECT_ROOT / "data" / "chroma")
)
DEFAULT_COLLECTION = os.environ.get("NEURA_COLLECTION", "about_me")


class KnowledgeBase:
    """Thin wrapper over a persistent, local Chroma collection.

    No embedding function is passed to Chroma, so it uses its default on-device model
    (all-MiniLM-L6-v2 via ONNX) — embeddings never leave the machine.
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> None:
        self.persist_dir = persist_dir or DEFAULT_PERSIST_DIR
        self.collection_name = collection or DEFAULT_COLLECTION
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False, allow_reset=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return self.collection.count()

    def delete_source(self, source: str) -> None:
        """Remove all chunks for a given source file (for incremental re-index)."""
        try:
            self.collection.delete(where={"source": source})
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def drop(collection: str, persist_dir: Optional[str] = None) -> None:
        """Delete an entire collection (e.g. when a chat workspace is removed)."""
        try:
            client = chromadb.PersistentClient(
                path=persist_dir or DEFAULT_PERSIST_DIR,
                settings=Settings(anonymized_telemetry=False, allow_reset=False),
            )
            client.delete_collection(collection)
        except Exception:  # noqa: BLE001
            pass

    def add(
        self,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Upsert chunks so re-ingesting refreshes existing ids instead of erroring."""
        if not ids:
            return
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Return the most relevant passages for a natural-language query."""
        if self.collection.count() == 0:
            return []
        res = self.collection.query(
            query_texts=[query],
            n_results=max(1, min(int(top_k), 20)),
            include=["documents", "metadatas", "distances"],
        )
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out: List[Dict[str, Any]] = []
        for doc, meta, dist in zip(docs, metas, dists):
            meta = meta or {}
            out.append(
                {
                    "content": doc,
                    "source": meta.get("source", "unknown"),
                    "metadata": meta,
                    # cosine distance -> similarity score in [0, 1]
                    "score": round(1.0 - float(dist), 3),
                }
            )
        return out
