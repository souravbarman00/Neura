"""Neura CodedTool: search arXiv for the Research Radar network.

Lets the research_radar front-man scan recent papers in the user's areas and pull
a specific paper's details to answer questions about it. Read-only, no API key.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from neuro_san.interfaces.coded_tool import CodedTool

from neura import arxiv_lib


class ArxivSearch(CodedTool):
    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        query = (args.get("query") or "").strip()
        if not query:
            return "Provide a `query`, e.g. 'multi-agent LLM' or an arXiv id like 2401.01234."
        try:
            max_results = max(1, min(int(args.get("max_results", 6)), 25))
        except (TypeError, ValueError):
            max_results = 6
        # If the query looks like an arXiv id, fetch that paper specifically.
        q = query
        if all(c.isdigit() or c == "." for c in query.replace("v", "")) and "." in query:
            q = f"id:{query}"
        papers = arxiv_lib.search(q, max_results=max_results)
        if not papers:
            return f"No arXiv results for: {query}"
        lines = [f"{len(papers)} arXiv result(s) for '{query}':\n"]
        for i, p in enumerate(papers, 1):
            authors = ", ".join(p["authors"]) + (" et al." if len(p["authors"]) >= 5 else "")
            abstract = " ".join(p["abstract"].split())
            if len(abstract) > 900:
                abstract = abstract[:900] + "…"
            lines.append(
                f"[{i}] {p['title']} ({p['published']})\n"
                f"    authors: {authors}\n"
                f"    {p['url']}\n"
                f"    abstract: {abstract}\n"
            )
        return "\n".join(lines)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)
