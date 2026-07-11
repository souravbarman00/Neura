"""Neura Kokoro TTS service.

A small, self-contained FastAPI server that turns text into 24 kHz speech using
the local Kokoro model (https://github.com/hexgrad/kokoro). Runs on :8900 and
speaks the exact contract the Neura backend proxies to:

    POST /api/tts    {"text": str, "voice": str, "speed": float}  -> audio/wav (24 kHz)
    GET  /api/voices                                              -> {"voices": [{"id","label"}]}

Nothing here talks to the network except Kokoro's one-time model download from
Hugging Face on first run. Everything else is on-device.
"""
from __future__ import annotations

import io
import wave

import numpy as np
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

SAMPLE_RATE = 24000  # Kokoro always outputs 24 kHz mono

# The voice catalogue Neura offers. The first letter of each id is Kokoro's
# lang_code (a = American English, b = British English, h = Hindi).
VOICES: list[dict[str, str]] = [
    {"id": "af_heart", "label": "Heart (Female · American)"},
    {"id": "af_sky", "label": "Sky (Female · American)"},
    {"id": "af_nicole", "label": "Nicole (Female · American)"},
    {"id": "af_bella", "label": "Bella (Female · American)"},
    {"id": "af_sarah", "label": "Sarah (Female · American)"},
    {"id": "am_adam", "label": "Adam (Male · American)"},
    {"id": "am_michael", "label": "Michael (Male · American)"},
    {"id": "bf_emma", "label": "Emma (Female · British)"},
    {"id": "bm_george", "label": "George (Male · British)"},
    {"id": "hf_alpha", "label": "Alpha (Female · Hindi)"},
    {"id": "hf_beta", "label": "Beta (Female · Hindi)"},
    {"id": "hm_omega", "label": "Omega (Male · Hindi)"},
    {"id": "hm_psi", "label": "Psi (Male · Hindi)"},
]
_VOICE_IDS = {v["id"] for v in VOICES}
DEFAULT_VOICE = "af_heart"

app = FastAPI(title="Neura Kokoro TTS")

# KPipeline is expensive to build and holds the model, so we keep one per language.
_pipelines: dict[str, object] = {}


def _get_pipeline(lang_code: str):
    """Lazily create (and cache) a Kokoro pipeline for a language.
    Imported here so the module can be inspected/tested without kokoro installed."""
    if lang_code not in _pipelines:
        from kokoro import KPipeline  # noqa: WPS433 — lazy, heavy import

        _pipelines[lang_code] = KPipeline(lang_code=lang_code)
    return _pipelines[lang_code]


def _to_float32(audio) -> np.ndarray:
    """Kokoro yields a torch tensor (or array-like) of float32 samples in [-1, 1]."""
    if hasattr(audio, "detach"):  # torch.Tensor
        audio = audio.detach().cpu().numpy()
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def _wav_bytes(samples: np.ndarray) -> bytes:
    """Encode float32 [-1, 1] mono samples as a 16-bit PCM WAV (stdlib only)."""
    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm16.tobytes())
    return buf.getvalue()


def synthesize(text: str, voice: str, speed: float) -> bytes:
    """Render `text` to WAV bytes with the given Kokoro voice."""
    if voice not in _VOICE_IDS:
        voice = DEFAULT_VOICE
    lang_code = voice[0]  # 'a' American, 'b' British, 'h' Hindi, ...
    pipeline = _get_pipeline(lang_code)

    parts: list[np.ndarray] = []
    for result in pipeline(text, voice=voice, speed=speed):
        # KPipeline yields (graphemes, phonemes, audio) tuples.
        audio = result[2] if isinstance(result, (tuple, list)) else getattr(result, "audio", None)
        if audio is not None:
            parts.append(_to_float32(audio))

    samples = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    return _wav_bytes(samples)


class TtsRequest(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE
    speed: float = 1.0


@app.get("/api/voices")
async def get_voices() -> JSONResponse:
    return JSONResponse({"voices": VOICES})


@app.post("/api/tts")
async def post_tts(req: TtsRequest) -> Response:
    text = (req.text or "").strip()
    if not text:
        return Response(content=b"empty text", status_code=400)
    try:
        wav = synthesize(text, req.voice, req.speed or 1.0)
        return Response(content=wav, media_type="audio/wav")
    except Exception as exc:  # noqa: BLE001
        return Response(content=f"TTS failed: {exc}", status_code=500)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "sample_rate": SAMPLE_RATE, "voices": len(VOICES)}
