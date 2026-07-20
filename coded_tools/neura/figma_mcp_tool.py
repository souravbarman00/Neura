"""Neura CodedTool: Figma via the Framelink MCP server (figma-developer-mcp).

neuro-san's built-in MCP client only speaks streamable-HTTP, but Framelink is a Node
*stdio* server — so we bridge it here with the official `mcp` Python SDK: spawn
`npx figma-developer-mcp --stdio`, then list/call its tools (get_figma_data,
download_figma_images). Auth uses FIGMA_TOKEN (same token as the REST tool).

Requires Node.js (npx) on the machine. First call downloads the npm package.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict

from neuro_san.interfaces.coded_tool import CodedTool

STARTUP_TIMEOUT = 90  # first run downloads the npm package
IMAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "artifacts"  # served at /artifacts


class FigmaMcp(CodedTool):
    """List or call Framelink Figma MCP tools over stdio."""

    async def _run(self, args: Dict[str, Any]) -> str:
        token = (os.environ.get("FIGMA_TOKEN") or "").strip()
        if len(token) < 10:
            return "Set FIGMA_TOKEN (a Figma personal access token, figd_…) to use the Figma MCP."
        npx = shutil.which("npx")
        if not npx:
            return "Node.js/npx is required for the Figma MCP (Framelink). Install Node, then retry."

        tool = (args.get("tool") or "").strip()
        arguments = args.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return "`arguments` must be a JSON object."

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as exc:  # noqa: BLE001
            return f"The `mcp` Python package is required: {exc}"

        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        params = StdioServerParameters(
            command=npx,
            args=["-y", "figma-developer-mcp", f"--figma-api-key={token}",
                  f"--image-dir={IMAGE_DIR}", "--stdio"],
            env={**os.environ, "FIGMA_API_KEY": token, "IMAGE_DIR": str(IMAGE_DIR)},
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=STARTUP_TIMEOUT)
                    if not tool:
                        listed = await session.list_tools()
                        lines = ["Figma MCP tools (call one via `tool` + `arguments`):"]
                        for t in listed.tools:
                            desc = (t.description or "").split("\n")[0][:160]
                            lines.append(f"- {t.name}: {desc}")
                        return "\n".join(lines)
                    result = await asyncio.wait_for(
                        session.call_tool(tool, arguments), timeout=STARTUP_TIMEOUT
                    )
                    parts = []
                    for c in getattr(result, "content", []) or []:
                        if getattr(c, "type", "") == "text":
                            parts.append(c.text)
                        else:
                            parts.append(f"[{getattr(c, 'type', 'content')}]")
                    out = "\n".join(parts).strip()
                    if getattr(result, "isError", False):
                        return f"Figma MCP tool '{tool}' error: {out or 'unknown error'}"
                    return out or "(no content returned)"
        except asyncio.TimeoutError:
            return "Figma MCP timed out (first run downloads the npm package; check network/Node)."
        except Exception as exc:  # noqa: BLE001
            return f"Figma MCP error: {exc}"

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await self._run(args)

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return asyncio.run(self._run(args))
