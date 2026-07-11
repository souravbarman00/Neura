"""Shared ingestion logic for Neura's local knowledge base.

Used by both the CLI (scripts/ingest.py) and the backend (/api/ingest, /api/upload).
Everything runs on-device: text is chunked here and embedded locally by Chroma.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Iterable, Optional

from .knowledge_base import KnowledgeBase

TEXT_EXT = {
    ".md", ".txt", ".rst", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".hocon", ".cfg", ".ini", ".csv", ".html",
    ".css", ".sh", ".sql", ".java", ".go", ".rb",
}
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".next",
    "dist", "build", ".cache", ".idea", ".vscode", ".pytest_cache",
}


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join((pg.extract_text() or "") for pg in reader.pages)
        except Exception as exc:  # noqa: BLE001
            print(f"  ! skip pdf {path}: {exc}")
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! skip {path}: {exc}")
        return ""


def chunk(text: str, size: int = 1000, overlap: int = 200) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    i, n = 0, len(text)
    step = max(1, size - overlap)
    while i < n:
        chunks.append(text[i : i + size])
        i += step
    return chunks


def iter_files(root: Path, max_mb: float) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath) / fn
            ext = p.suffix.lower()
            if ext not in TEXT_EXT and ext != ".pdf":
                continue
            try:
                if p.stat().st_size > max_mb * 1024 * 1024:
                    continue
            except OSError:
                continue
            yield p


def iter_ingest(
    paths: list[str],
    collection: Optional[str] = None,
    max_mb: float = 2.0,
    chunk_size: int = 1000,
    overlap: int = 200,
):
    """Generator that indexes paths file-by-file, yielding progress events.

    Yields dicts:
      {"phase":"scanning","total":N,"missing":[...]}
      {"phase":"file","index":i,"total":N,"name":..,"source":..,"chunks":k,
       "added_files":..,"added_chunks":..}
      {"phase":"done","files":..,"chunks":..,"total":kb_total,"missing":[...]}
    """
    kb = KnowledgeBase(collection=collection)

    files: list[Path] = []
    missing: list[str] = []
    for raw in paths:
        root = Path(raw).expanduser().resolve()
        if not root.exists():
            missing.append(str(raw))
            continue
        if root.is_file():
            files.append(root)
        else:
            files.extend(iter_files(root, max_mb))

    total = len(files)
    yield {"phase": "scanning", "total": total, "missing": missing}

    added_files = added_chunks = 0
    for i, p in enumerate(files, 1):
        cks = chunk(read_text(p), chunk_size, overlap)
        n = 0
        if cks:
            ids, docs, metas = [], [], []
            src = str(p)
            for idx, c in enumerate(cks):
                cid = hashlib.sha1(f"{src}#{idx}".encode()).hexdigest()
                ids.append(cid)
                docs.append(c)
                metas.append({"source": src, "chunk": idx, "name": p.name, "ext": p.suffix.lower()})
            kb.add(ids, docs, metas)
            n = len(cks)
            added_files += 1
            added_chunks += n
        yield {
            "phase": "file",
            "index": i,
            "total": total,
            "name": p.name,
            "source": str(p),
            "chunks": n,
            "added_files": added_files,
            "added_chunks": added_chunks,
        }

    yield {"phase": "done", "files": added_files, "chunks": added_chunks, "total": kb.count(), "missing": missing}


def index_file(path: str, collection: Optional[str] = None, chunk_size: int = 1000, overlap: int = 200) -> int:
    """(Re)index a single file into a collection: drop its old chunks, add fresh ones."""
    p = Path(path)
    kb = KnowledgeBase(collection=collection)
    kb.delete_source(str(p))
    cks = chunk(read_text(p), chunk_size, overlap)
    if not cks:
        return 0
    ids, docs, metas = [], [], []
    src = str(p)
    for i, c in enumerate(cks):
        ids.append(hashlib.sha1(f"{src}#{i}".encode()).hexdigest())
        docs.append(c)
        metas.append({"source": src, "chunk": i, "name": p.name, "ext": p.suffix.lower()})
    kb.add(ids, docs, metas)
    return len(cks)


def remove_file(path: str, collection: Optional[str] = None) -> None:
    """Drop all chunks for a file (on delete)."""
    KnowledgeBase(collection=collection).delete_source(str(path))


def is_indexable(path: str, max_mb: float = 2.0) -> bool:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in TEXT_EXT and ext != ".pdf":
        return False
    if any(part in SKIP_DIRS or part.startswith(".") for part in p.parts):
        return False
    try:
        return p.is_file() and p.stat().st_size <= max_mb * 1024 * 1024
    except OSError:
        return False


def ingest_paths(
    paths: list[str],
    collection: Optional[str] = None,
    max_mb: float = 2.0,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> dict[str, Any]:
    """Index the given folders/files into the local knowledge base. Returns a report."""
    kb = KnowledgeBase(collection=collection)
    total_files = total_chunks = 0
    missing: list[str] = []

    for raw in paths:
        root = Path(raw).expanduser().resolve()
        if not root.exists():
            missing.append(str(raw))
            continue
        files = [root] if root.is_file() else list(iter_files(root, max_mb))
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []
        for p in files:
            cks = chunk(read_text(p), chunk_size, overlap)
            if not cks:
                continue
            total_files += 1
            src = str(p)
            for idx, c in enumerate(cks):
                cid = hashlib.sha1(f"{src}#{idx}".encode()).hexdigest()
                ids.append(cid)
                docs.append(c)
                metas.append({"source": src, "chunk": idx, "name": p.name, "ext": p.suffix.lower()})
                if len(ids) >= 200:
                    kb.add(ids, docs, metas)
                    total_chunks += len(ids)
                    ids, docs, metas = [], [], []
        if ids:
            kb.add(ids, docs, metas)
            total_chunks += len(ids)

    return {
        "files": total_files,
        "chunks": total_chunks,
        "total": kb.count(),
        "missing": missing,
    }
