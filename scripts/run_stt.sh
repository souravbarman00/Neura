#!/usr/bin/env bash
# Launch the Neura Whisper STT service on :8901.
#
# Runs from the PROJECT virtualenv (../.venv) — the same env as the rest of the
# app — so the STT deps live alongside the project. First run installs the
# requirements into it and faster-whisper downloads its Whisper model from
# Hugging Face. No system ffmpeg needed (PyAV, bundled with faster-whisper,
# decodes the browser's webm/opus).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SVC="$ROOT/services/stt"
VENV="$ROOT/.venv"          # shared project venv
PORT="${STT_PORT:-8901}"

if [ ! -d "$VENV" ]; then
  echo "Creating project virtualenv at $VENV …"
  python3 -m venv "$VENV"
fi

# Install/refresh deps when requirements change (marker keeps re-runs fast).
# Installed with `uv`: the corporate pip mirror is stale, so plain pip may fail to
# resolve current faster-whisper. uv resolves it (PyPI + shared cache). Falls back
# to pip only if uv is unavailable.
# STANDALONE: the bundled venv already has every package, so if faster_whisper
# imports we skip the install entirely — the packaged app must never depend on
# uv/pip/network.
if ! "$VENV/bin/python" -c "import faster_whisper" >/dev/null 2>&1; then
  STAMP="$VENV/.stt-requirements.sha"
  NEW_SHA="$(shasum "$SVC/requirements.txt" | awk '{print $1}')"
  if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$NEW_SHA" ]; then
    echo "Installing STT requirements into $VENV …"
    if command -v uv >/dev/null 2>&1; then
      uv pip install --python "$VENV/bin/python" -r "$SVC/requirements.txt"
    else
      "$VENV/bin/pip" install -q --upgrade pip
      "$VENV/bin/pip" install -q -r "$SVC/requirements.txt"
    fi
    echo "$NEW_SHA" > "$STAMP"
  fi
fi

echo "Neura Whisper STT → http://localhost:${PORT}  (model: ${STT_MODEL:-small.en})"
cd "$SVC"
exec "$VENV/bin/python" -m uvicorn server:app --host 0.0.0.0 --port "$PORT"
