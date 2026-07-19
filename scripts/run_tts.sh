#!/usr/bin/env bash
# Launch the Neura Kokoro TTS service on :8900.
#
# Runs from the PROJECT virtualenv (../.venv) — the same env as the rest of the
# app — so Kokoro's deps live alongside the project instead of a separate/foreign
# venv. First run installs the TTS requirements into it and Kokoro downloads its
# model from Hugging Face.
#
# System prerequisite: espeak-ng  (macOS: `brew install espeak-ng`)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SVC="$ROOT/services/tts"
VENV="$ROOT/.venv"          # shared project venv (was services/tts/.venv)
PORT="${TTS_PORT:-8900}"

if [ ! -d "$VENV" ]; then
  echo "Creating project virtualenv at $VENV …"
  python3 -m venv "$VENV"
fi

# Install/refresh deps when requirements change (marker keeps re-runs fast).
# Installed with `uv`: the corporate pip mirror caps kokoro at 0.7.16, so plain
# pip cannot resolve kokoro>=0.9.4 — uv resolves it (PyPI + shared cache). Falls
# back to pip only if uv is unavailable.
#
# STANDALONE: the bundled venv already has every package, so if kokoro imports we
# skip the install entirely — the packaged app must never depend on uv/pip/network.
if ! "$VENV/bin/python" -c "import kokoro" >/dev/null 2>&1; then
  STAMP="$VENV/.requirements.sha"
  NEW_SHA="$(shasum "$SVC/requirements.txt" | awk '{print $1}')"
  if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$NEW_SHA" ]; then
    echo "Installing TTS requirements into $VENV …"
    if command -v uv >/dev/null 2>&1; then
      uv pip install --python "$VENV/bin/python" -r "$SVC/requirements.txt"
    else
      "$VENV/bin/pip" install -q --upgrade pip
      "$VENV/bin/pip" install -q -r "$SVC/requirements.txt"
    fi
    echo "$NEW_SHA" > "$STAMP"
  fi
fi

echo "Neura Kokoro TTS → http://localhost:${PORT}  (voices: /api/voices)"
cd "$SVC"
exec "$VENV/bin/python" -m uvicorn server:app --host 0.0.0.0 --port "$PORT"
