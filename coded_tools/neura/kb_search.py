"""Neura CodedTool: read-only semantic search over the user's knowledge.

Two scopes:
  - LOCAL  — the current chat's own knowledge (a folder you uploaded for this
             conversation, e.g. the codebase you're working in).
  - GLOBAL — the always-on "about me" knowledge base.

Default behavior is LOCAL-first: search the chat's local index and, only if it has
nothing relevant (or the agent explicitly asks), fall back to / include GLOBAL.
The per-chat and global collection names arrive via `sly_data` (kept out of the LLM
prompt) so the same tool serves every conversation.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from neuro_san.interfaces.coded_tool import CodedTool

from .knowledge_base import KnowledgeBase, DEFAULT_COLLECTION


class KnowledgeSearch(CodedTool):
    """Search the user's local (per-chat) and/or global knowledge, returning passages."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        query = (args.get("query") or "").strip()
        if not query:
            return "No query provided."
        try:
            top_k = int(args.get("top_k", 5))
        except (TypeError, ValueError):
            top_k = 5
        scope = (args.get("scope") or "local").strip().lower()

        kb_cfg = (sly_data or {}).get("knowledge_base", {}) or {}
        local_col = kb_cfg.get("local_collection")
        global_col = kb_cfg.get("global_collection") or DEFAULT_COLLECTION

        results: List[Dict[str, Any]] = []

        def run(collection: str, tag: str) -> List[Dict[str, Any]]:
            try:
                hits = KnowledgeBase(collection=collection).search(query, top_k)
            except Exception:  # noqa: BLE001
                return []
            for h in hits:
                h["scope"] = tag
            return hits

        if scope == "global":
            results = run(global_col, "global")
        elif scope == "both":
            if local_col:
                results += run(local_col, "local")
            results += run(global_col, "global")
        else:  # local (default) — local-first, global fallback
            if local_col:
                results = run(local_col, "local")
            if not results:
                results = run(global_col, "global")

        if not results:
            return (
                "No matching passages found. This chat's local knowledge may be empty — "
                "use 'Add to knowledge base → This chat' to index a folder, or try scope=global."
            )

        lines = [f"Found {len(results)} passage(s):\n"]
        for i, r in enumerate(results, 1):
            snippet = " ".join(r["content"].split())
            if len(snippet) > 700:
                snippet = snippet[:700] + "…"
            tag = r.get("scope", "").upper()
            lines.append(f"[{i}] ({tag}) source: {r['source']} (match {r['score']})\n{snippet}\n")
        return "\n".join(lines)

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)
