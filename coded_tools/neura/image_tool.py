"""Neura CodedTool: generate an image with OpenAI's image API.

Always uses OPENAI_API_KEY (independent of whichever LLM provider powers the chat),
so image generation works even when Neura is running on Claude/Mistral. The image is
saved under data/artifacts/ and returned as markdown so the chat renders it inline.
"""
from __future__ import annotations

import asyncio
import base64
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from neuro_san.interfaces.coded_tool import CodedTool

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "data" / "artifacts"
API_URL = "https://api.openai.com/v1/images/generations"
VALID_SIZES = {"1024x1024", "1536x1024", "1024x1536", "1792x1024", "1024x1792", "auto"}
TIMEOUT = 120


class ImageGenerate(CodedTool):
    """Create an image from a text prompt via OpenAI (gpt-image-1, falling back to dall-e-3)."""

    async def _run(self, args: Dict[str, Any]) -> str:
        prompt = (args.get("prompt") or "").strip()
        if not prompt:
            return "Provide a `prompt` describing the image to generate."
        key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if len(key) < 15:
            return ("Image generation needs an OpenAI key. Add OPENAI_API_KEY to .env "
                    "(image gen always uses OpenAI, even if the chat runs on another provider).")
        size = (args.get("size") or "1024x1024").strip()
        if size not in VALID_SIZES:
            size = "1024x1024"

        try:
            import httpx
        except Exception:  # noqa: BLE001
            return "The `httpx` package is required for image generation."

        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        # Try the newer gpt-image-1 first; fall back to dall-e-3 (broadest availability).
        attempts = [
            {"model": "gpt-image-1", "prompt": prompt, "size": size, "n": 1},
            {"model": "dall-e-3", "prompt": prompt,
             "size": size if size in {"1024x1024", "1792x1024", "1024x1792"} else "1024x1024",
             "n": 1, "response_format": "b64_json"},
        ]
        last_err = ""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for body in attempts:
                try:
                    r = await client.post(API_URL, headers=headers, json=body)
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    continue
                if r.status_code != 200:
                    last_err = f"{r.status_code} {r.text[:300]}"
                    continue
                data = (r.json().get("data") or [])
                if not data:
                    last_err = "no image returned"
                    continue
                b64 = data[0].get("b64_json")
                if not b64:
                    last_err = "response had no b64 image"
                    continue
                ARTIFACTS.mkdir(parents=True, exist_ok=True)
                out = ARTIFACTS / f"img-{int(time.time())}-{uuid.uuid4().hex[:6]}.png"
                try:
                    out.write_bytes(base64.b64decode(b64))
                except Exception as exc:  # noqa: BLE001
                    return f"Could not save the generated image: {exc}"
                alt = prompt if len(prompt) <= 120 else prompt[:117] + "…"
                return f"![{alt}](/artifacts/{out.name})"

        return f"Image generation failed: {last_err}"

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return asyncio.run(self._run(args))

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await self._run(args)
