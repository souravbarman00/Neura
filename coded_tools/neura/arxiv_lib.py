"""arXiv fetch/parse — shared by the Research Radar network's coded tool and the
backend feed cache. Pure httpx + stdlib, no API key needed."""
from __future__ import annotations

from typing import Any, Dict, List
from xml.etree import ElementTree as ET

import httpx

ARXIV = "https://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"


def _text(el, tag: str) -> str:
    node = el.find(_ATOM + tag)
    return " ".join(node.text.split()) if node is not None and node.text else ""


def _parse(xml: str) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(xml)
    except Exception:  # noqa: BLE001
        return []
    out: List[Dict[str, Any]] = []
    for e in root.findall(_ATOM + "entry"):
        arxiv_id = _text(e, "id")
        out.append({
            "id": arxiv_id.rsplit("/", 1)[-1] if arxiv_id else "",
            "title": _text(e, "title"),
            "authors": [_text(a, "name") for a in e.findall(_ATOM + "author")][:5],
            "published": (_text(e, "published") or "")[:10],
            "url": arxiv_id,
            "abstract": _text(e, "summary"),
        })
    return out


def search(query: str, max_results: int = 6, sort: str = "submittedDate") -> List[Dict[str, Any]]:
    """Synchronous search (for the coded tool). Newest first by default."""
    try:
        r = httpx.get(ARXIV, params={"search_query": query, "start": 0, "max_results": max_results,
                                     "sortBy": sort, "sortOrder": "descending"}, timeout=20)
        return _parse(r.text)
    except Exception:  # noqa: BLE001
        return []


async def asearch(client: httpx.AsyncClient, query: str, max_results: int = 6) -> List[Dict[str, Any]]:
    """Async search (for the backend feed builder)."""
    try:
        r = await client.get(ARXIV, params={"search_query": query, "start": 0, "max_results": max_results,
                                            "sortBy": "submittedDate", "sortOrder": "descending"}, timeout=20)
        return _parse(r.text)
    except Exception:  # noqa: BLE001
        return []
