"""Neura CodedTool: Semantic Scholar lookup for the Research Radar.

Adds scholarly context a keyword search can't: citation counts, an AI TL;DR, the
key references, related/recommended papers, and any open-access PDF / code links.
Free Graph API, no key (rate-limited). Read-only.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict

import httpx
from neuro_san.interfaces.coded_tool import CodedTool

_BASE = "https://api.semanticscholar.org/graph/v1"


def _arxiv_id(s: str) -> str | None:
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", s or "")
    return m.group(1) if m else None


class SemanticScholar(CodedTool):
    """action=paper (by arXiv id/title) → impact + tldr + references + code;
    action=search (by query) → top related papers by citation."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        query = (args.get("query") or args.get("arxiv_id") or "").strip()
        action = (args.get("action") or "paper").strip().lower()
        if not query:
            return "Provide a `query` (arXiv id, title, or topic)."
        try:
            if action == "search" and not _arxiv_id(query):
                return self._search(query)
            return self._paper(query)
        except Exception as exc:  # noqa: BLE001
            return f"Semantic Scholar lookup failed: {exc}"

    def _paper(self, query: str) -> str:
        aid = _arxiv_id(query)
        fields = "title,year,citationCount,influentialCitationCount,tldr,openAccessPdf,externalIds,references.title,references.year"
        if aid:
            url = f"{_BASE}/paper/arXiv:{aid}?fields={fields}"
            r = httpx.get(url, timeout=30)
        else:
            # resolve by title first
            s = httpx.get(f"{_BASE}/paper/search", params={"query": query, "limit": 1, "fields": "paperId"}, timeout=30).json()
            data = (s.get("data") or [])
            if not data:
                return f"No Semantic Scholar match for: {query}"
            url = f"{_BASE}/paper/{data[0]['paperId']}?fields={fields}"
            r = httpx.get(url, timeout=30)
        if r.status_code != 200:
            return f"Semantic Scholar returned HTTP {r.status_code} for {query}."
        p = r.json()
        lines = [f"{p.get('title','?')} ({p.get('year','?')})"]
        lines.append(f"Citations: {p.get('citationCount', '?')} (influential: {p.get('influentialCitationCount', '?')})")
        tldr = (p.get("tldr") or {}).get("text")
        if tldr:
            lines.append(f"TL;DR: {tldr}")
        oa = (p.get("openAccessPdf") or {}).get("url")
        if oa:
            lines.append(f"Open-access PDF: {oa}")
        refs = [x.get("title") for x in (p.get("references") or []) if x.get("title")][:6]
        if refs:
            lines.append("Key references:\n" + "\n".join(f"  - {t}" for t in refs))
        return "\n".join(lines)

    def _search(self, query: str) -> str:
        r = httpx.get(
            f"{_BASE}/paper/search",
            params={"query": query, "limit": 6, "fields": "title,year,citationCount,externalIds,openAccessPdf"},
            timeout=30,
        )
        data = (r.json().get("data") or [])
        if not data:
            return f"No related papers for: {query}"
        data.sort(key=lambda x: x.get("citationCount", 0), reverse=True)
        out = [f"Related papers for '{query}' (by citations):\n"]
        for p in data:
            arx = (p.get("externalIds") or {}).get("ArXiv")
            link = f" arXiv:{arx}" if arx else ((p.get("openAccessPdf") or {}).get("url") or "")
            out.append(f"  - {p.get('title','?')} ({p.get('year','?')}) · {p.get('citationCount',0)} cites{(' · ' + link) if link else ''}")
        return "\n".join(out)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)
