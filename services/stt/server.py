"""Neura Whisper STT service.

A small, self-contained FastAPI server that transcribes speech to text using the
local Whisper model via faster-whisper (CTranslate2). Runs on :8901 and speaks the
exact contract the Neura backend proxies to:

    POST /api/stt   <raw audio bytes>  ->  {"text": str, "language": str, "duration": float}
    GET  /api/health                   ->  {"status","model","language","loaded"}

Accepts whatever the browser records (webm/opus by default) or a plain wav/mp3 —
PyAV (bundled with faster-whisper) decodes it, so there is no system ffmpeg
dependency. The model downloads from Hugging Face once on first startup; after
that everything is on-device.

Tunables (env):
    STT_MODEL    Whisper size, default "small.en" (English, good accuracy/speed).
                 Use "small"/"medium" for multilingual, "base.en" for more speed.
    STT_LANG     forced language, default "en". Set STT_LANG="" for auto-detect.
    STT_DEVICE   "cpu" (default) or "cuda".
    STT_COMPUTE  ctranslate2 compute type, default "int8" (CPU-friendly).
"""
from __future__ import annotations

import io
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MODEL_NAME = os.environ.get("STT_MODEL", "small.en")
LANGUAGE = os.environ.get("STT_LANG", "en") or None  # "" → auto-detect
DEVICE = os.environ.get("STT_DEVICE", "cpu")
COMPUTE = os.environ.get("STT_COMPUTE", "int8")

app = FastAPI(title="Neura Whisper STT")

# The model is expensive to build and holds weights, so keep exactly one instance.
_model = None


def _get_model():
    """Lazily create (and cache) the Whisper model. Imported here so the module can
    be inspected/tested without faster-whisper installed."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel  # noqa: WPS433 — lazy, heavy import

        _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE)
    return _model


def transcribe(data: bytes) -> dict:
    """Transcribe raw audio bytes to text. Reliability choices:
    - vad_filter drops non-speech so silence isn't hallucinated into words;
    - condition_on_previous_text=False stops short clips looping/repeating;
    - a forced language (default en) avoids mis-detection on short utterances."""
    model = _get_model()
    segments, info = model.transcribe(
        io.BytesIO(data),
        language=LANGUAGE,
        vad_filter=True,
        condition_on_previous_text=False,
        beam_size=5,
    )
    text = "".join(seg.text for seg in segments).strip()
    return {
        "text": text,
        "language": getattr(info, "language", LANGUAGE or "") or "",
        "duration": round(float(getattr(info, "duration", 0.0) or 0.0), 2),
    }


@app.post("/api/stt")
async def post_stt(request: Request) -> JSONResponse:
    data = await request.body()
    if not data:
        return JSONResponse({"text": "", "error": "empty audio"}, status_code=400)
    try:
        return JSONResponse(transcribe(data))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"text": "", "error": f"STT failed: {exc}"}, status_code=500)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "language": LANGUAGE or "auto",
        "loaded": _model is not None,
    }


@app.on_event("startup")
async def _warmup() -> None:
    """Load (and download) the model at startup so the first real request is fast
    and any failure surfaces immediately in the log rather than mid-conversation."""
    try:
        _get_model()
    except Exception as exc:  # noqa: BLE001 — log, don't crash the server
        print(f"[stt] model warmup failed: {exc}")
