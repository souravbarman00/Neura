#!/usr/bin/env python
"""Ingest local folders / files into Neura's private on-device knowledge base.

Everything stays on your machine: text is chunked here and embedded by Chroma's
local model. Nothing is uploaded.

Usage:
    python scripts/ingest.py ~/Documents ~/neuro-san-studio
    python scripts/ingest.py ~/notes --collection about_me --max-mb 2
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

# Make the coded_tools packages importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coded_tools"))
from neura.knowledge_base import KnowledgeBase  # noqa: E402

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
    chunks, i, n = [], 0, len(text)
    step = max(1, size - overlap)
    while i < n:
        chunks.append(text[i : i + size])
        i += step
    return chunks


def iter_files(root: Path, max_mb: float):
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingest folders into Neura's local knowledge base.")
    ap.add_argument("paths", nargs="+", help="Folders or files to index")
    ap.add_argument("--collection", default=None, help="Collection name (default: about_me)")
    ap.add_argument("--max-mb", type=float, default=2.0, help="Skip files larger than this (MB)")
    ap.add_argument("--chunk-size", type=int, default=1000)
    ap.add_argument("--overlap", type=int, default=200)
    args = ap.parse_args()

    kb = KnowledgeBase(collection=args.collection)
    print(f"Knowledge base: {kb.persist_dir}")
    print(f"Collection    : '{kb.collection_name}' (currently {kb.count()} chunks)\n")

    total_files = total_chunks = 0
    for raw in args.paths:
        root = Path(raw).expanduser().resolve()
        if not root.exists():
            print(f"! path not found: {root}")
            continue
        files = [root] if root.is_file() else list(iter_files(root, args.max_mb))
        print(f"Indexing {len(files)} file(s) under {root} …")

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []
        for p in files:
            cks = chunk(read_text(p), args.chunk_size, args.overlap)
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

    print(f"\nDone. Indexed {total_files} files → {total_chunks} chunks.")
    print(f"Collection '{kb.collection_name}' now holds {kb.count()} chunks.")


if __name__ == "__main__":
    main()
