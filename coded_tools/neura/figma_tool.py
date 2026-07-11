"""Neura CodedTool: authenticated Figma REST API calls.

Reads config from the environment (Configuration panel → .env):
  - FIGMA_TOKEN   a Figma personal access token (figd_...)

The `figma` sub-agent drives this by choosing Figma REST endpoints. Auth is the
X-Figma-Token header. Base is https://api.figma.com.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import httpx

from neuro_san.interfaces.coded_tool import CodedTool


class FigmaRequest(CodedTool):
    """Call a Figma REST API endpoint and return the JSON result."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        method = (args.get("method") or "GET").upper()
        path = args.get("path") or ""
        body = args.get("body")

        token = os.environ.get("FIGMA_TOKEN") or ""
        if not path:
            return "Provide a Figma API path, e.g. /v1/me or /v1/files/{file_key}."
        if not token:
            return "Figma isn't configured. Set FIGMA_TOKEN in the Configuration panel."

        if path.startswith("http"):
            url = path
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = f"https://api.figma.com{path}"

        if isinstance(body, str) and body.strip():
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass

        headers = {"X-Figma-Token": token, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=45) as c:
                r = await c.request(method, url, headers=headers, json=body if body not in (None, "") else None)
        except Exception as exc:  # noqa: BLE001
            return f"Figma request error: {exc}"

        if r.status_code in (401, 403):
            return (
                f"Figma auth failed (HTTP {r.status_code}). Check FIGMA_TOKEN in the "
                "Configuration panel (and that the token has the needed scopes)."
            )
        ctype = r.headers.get("content-type", "")
        if "json" in ctype:
            try:
                text = json.dumps(r.json(), indent=2)
            except Exception:  # noqa: BLE001
                text = r.text
        else:
            text = r.text or f"(HTTP {r.status_code}, empty body)"
        if len(text) > 6000:
            text = text[:6000] + "\n… (truncated)"
        return f"HTTP {r.status_code}\n{text}"
