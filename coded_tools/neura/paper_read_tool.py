"""Neura CodedTool: read the FULL text of an arXiv paper.

Downloads the PDF and extracts its text so the Research Radar can answer deep
questions (method, results, limitations) — not just from the abstract. Read-only,
no API key. Uses pypdf (already a dependency).
"""
from __future__ import annotations

import asyncio
import re
from io import BytesIO
from typing import Any, Dict

import httpx
from neuro_san.interfaces.coded_tool import CodedTool


def _arxiv_id(s: str) -> str:
    s = (s or "").strip()
    m = re.search(r"(\d{4}\.\d{4,5}(v\d+)?)", s)
    return m.group(1) if m else s


class PaperRead(CodedTool):
    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        raw = (args.get("arxiv_id") or args.get("url") or args.get("query") or "").strip()
        if not raw:
            return "Provide an arXiv id or URL to read."
        aid = _arxiv_id(raw)
        try:
            max_chars = max(2000, min(int(args.get("max_chars", 14000)), 40000))
        except (TypeError, ValueError):
            max_chars = 14000
        url = f"https://arxiv.org/pdf/{aid}"
        try:
            r = httpx.get(url, timeout=45, follow_redirects=True)
            if r.status_code != 200 or not r.content:
                return f"Could not download the PDF for {aid} (HTTP {r.status_code})."
            from pypdf import PdfReader  # noqa: WPS433

            reader = PdfReader(BytesIO(r.content))
            parts, total = [], 0
            for page in reader.pages:
                try:
                    t = page.extract_text() or ""
                except Exception:  # noqa: BLE001
                    t = ""
                if t:
                    parts.append(t)
                    total += len(t)
                if total >= max_chars:
                    break
            text = re.sub(r"[ \t]+", " ", "\n".join(parts)).strip()
        except Exception as exc:  # noqa: BLE001
            return f"Failed to read paper {aid}: {exc}"
        if not text:
            return f"No extractable text in the PDF for {aid} (it may be scanned/figures-only)."
        clipped = text[:max_chars]
        note = "" if len(text) <= max_chars else f"\n\n… (truncated to {max_chars} chars of {len(text)})"
        return f"Full text of arXiv:{aid} ({len(reader.pages)} pages):\n\n{clipped}{note}"

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)
