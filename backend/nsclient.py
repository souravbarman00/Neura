"""Thin async client for the neuro-san runtime's streaming_chat HTTP API."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import httpx

NEURA_SERVER_URL = os.environ.get("NEURA_SERVER_URL", "http://localhost:8099")


def parse_sources(text: str) -> list[dict]:
    """Extract '[n] source: <path> (match <score>)' lines from a tool result."""
    out: list[dict] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("[") and "source:" in line:
            try:
                path = line.split("source:")[1].split("(match")[0].strip()
                score = None
                if "(match" in line:
                    score = line.split("(match")[1].strip().rstrip(")").strip()
                out.append({"source": path, "name": Path(path).name, "score": score})
            except Exception:  # noqa: BLE001
                continue
    return out


async def stream_frames(
    network: str,
    message: str,
    chat_context: Optional[dict] = None,
    sly_data: Optional[dict] = None,
) -> AsyncIterator[dict[str, Any]]:
    req: dict[str, Any] = {
        "user_message": {"type": "HUMAN", "text": message},
        "chat_filter": {"chat_filter_type": "MAXIMAL"},
    }
    if chat_context:
        req["chat_context"] = chat_context
    if sly_data:
        req["sly_data"] = sly_data
    url = f"{NEURA_SERVER_URL}/api/v1/{network}/streaming_chat"
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, json=req) as resp:
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


async def collect(
    network: str,
    message: str,
    chat_context: Optional[dict] = None,
    sly_data: Optional[dict] = None,
) -> tuple[str, list[dict], Optional[dict]]:
    """Run a full turn and return (answer, sources, new_chat_context)."""
    answer = ""
    sources: list[dict] = []
    ctx: Optional[dict] = None
    async for frame in stream_frames(network, message, chat_context, sly_data):
        r = frame.get("response", {}) or {}
        t = r.get("type")
        if t == "AGENT_TOOL_RESULT":
            sources.extend(parse_sources(r.get("text", "")))
        elif t in ("AI", "AGENT_FRAMEWORK") and r.get("text"):
            answer = r["text"]
        if isinstance(r, dict) and r.get("chat_context"):
            ctx = r["chat_context"]
    return answer, sources, ctx
