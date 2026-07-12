"""Neura CodedTool: workflow memory (per-conversation JSON store).

Lets Neura record the important details of a long, multi-step task as it goes —
ticket keys, branch names, PR/commit URLs, decisions, resource IDs — so they
survive context compaction and ground every later turn. Scoped to THIS
conversation via sly_data["conversation_id"]; stored as one JSON per workflow.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from neuro_san.interfaces.coded_tool import CodedTool

from neura import workflow_memory_lib as wm


class WorkflowMemory(CodedTool):
    """actions: append (default), read, delete."""

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        conv_id = (sly_data or {}).get("conversation_id") or ""
        if not conv_id:
            return "No conversation context — cannot record workflow memory."
        action = (args.get("action") or "append").strip().lower()

        if action in ("append", "add", "remember", "save"):
            value = (args.get("value") or args.get("note") or "").strip()
            key = (args.get("key") or "note").strip() or "note"
            if not value:
                return "Nothing to remember — provide `value`."
            entry = wm.add(conv_id, value, key=key, source="model")
            if entry is None:
                return f"Already in workflow memory: [{key}] {value}"
            return f"Saved to workflow memory: [{entry['key']}] {entry['value']}"

        if action == "read":
            doc = wm.load(conv_id)
            entries = doc.get("entries") or []
            if not entries:
                return "This workflow has no saved memory yet."
            return "This workflow's memory:\n" + "\n".join(
                f"  - [{e.get('key','note')}] {e.get('value','')}" for e in entries
            )

        if action == "delete":
            entry_id = (args.get("entry_id") or "").strip()
            if not entry_id:
                return "Provide `entry_id` to delete (or the user can clear it from the UI)."
            ok = wm.delete_entry(conv_id, entry_id)
            return "Deleted." if ok else "No such entry."

        return f"Unknown action '{action}'. Use append, read, or delete."

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)
