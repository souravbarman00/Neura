"""Research Radar feed cache — powers the dedicated panel's "latest updates" view.

The chat/Q&A side is the `research_radar` neuro-san network (see registries/
research_radar.hocon). This module only builds & caches the daily feed the panel
renders (one JSON at data/research_radar.json), sharing the arXiv fetch lib with
the network's coded tool. Enrichment (summary/skill/read-vs-try) is supplied by
the caller (app.py) via the provider-aware utility LLM.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List

import httpx

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "coded_tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "coded_tools"))
from neura import arxiv_lib  # noqa: E402

_CACHE = _ROOT / "data" / "research_radar.json"

# Neutral default research areas (general agentic-AI topics) — editable from the UI.
DEFAULT_AREAS: List[Dict[str, str]] = [
    {"label": "Multi-agent LLM systems", "query": 'all:"multi-agent" AND all:"language model"'},
    {"label": "Agent orchestration & frameworks", "query": 'all:"agentic" OR all:"agent orchestration"'},
    {"label": "LLM reasoning & tool use", "query": 'all:"tool use" AND all:"large language model"'},
    {"label": "Retrieval-augmented generation", "query": 'all:"retrieval-augmented generation"'},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load() -> Dict[str, Any]:
    if _CACHE.exists():
        try:
            return json.loads(_CACHE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"generated": None, "day": None, "areas": DEFAULT_AREAS, "items": []}


def save(doc: Dict[str, Any]) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def get_areas() -> List[Dict[str, str]]:
    return load().get("areas") or DEFAULT_AREAS


def set_areas(areas: List[Dict[str, str]]) -> None:
    doc = load()
    doc["areas"] = [a for a in areas if a.get("query", "").strip()] or DEFAULT_AREAS
    save(doc)


def is_stale(doc: Dict[str, Any]) -> bool:
    """True if the radar wasn't generated today — drives the daily auto-refresh."""
    return doc.get("day") != _today() or not doc.get("items")


async def fetch(areas: List[Dict[str, str]], per_area: int = 6) -> List[Dict[str, Any]]:
    """Recent papers across all areas, newest first, deduped by arXiv id."""
    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for area in areas:
            for p in await arxiv_lib.asearch(client, area["query"], per_area):
                p["area"] = area["label"]
                results.append(p)
    seen, deduped = set(), []
    for p in sorted(results, key=lambda x: x.get("published", ""), reverse=True):
        if p["id"] and p["id"] not in seen:
            seen.add(p["id"])
            deduped.append(p)
    return deduped


async def fetch_one(ref: str) -> Dict[str, Any] | None:
    """Fetch a single paper by arXiv id or URL (for the 'paste a paper link' flow)."""
    import re

    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", ref or "")
    aid = m.group(1) if m else (ref or "").strip()
    if not aid:
        return None
    async with httpx.AsyncClient() as client:
        papers = await arxiv_lib.asearch(client, f"id:{aid}", 1)
    if not papers:
        return None
    p = papers[0]
    p["area"] = "On demand"
    return p


async def build(
    areas: List[Dict[str, str]],
    enrich: Callable[[List[Dict[str, Any]]], Awaitable[List[Dict[str, Any]]]],
) -> Dict[str, Any]:
    """Fetch + enrich, preserving read/dismissed status of items already seen."""
    prev = {i["id"]: i for i in load().get("items", [])}
    papers = await enrich(await fetch(areas))
    for p in papers:
        old = prev.get(p["id"])
        p["status"] = old.get("status", "new") if old else "new"
    doc = {"generated": _now(), "day": _today(), "areas": areas, "items": papers}
    save(doc)
    return doc


def set_item_status(item_id: str, status: str) -> bool:
    doc = load()
    hit = False
    for i in doc.get("items", []):
        if i.get("id") == item_id:
            i["status"] = status
            hit = True
    if hit:
        save(doc)
    return hit
