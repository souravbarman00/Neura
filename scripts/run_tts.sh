#!/usr/bin/env bash
# Launch the Neura Kokoro TTS service on :8900.
#
# Uses its own virtualenv (services/tts/.venv) so the heavy ML deps that `kokoro`
# pulls in (torch, etc.) stay isolated from the main app environment. First run
# installs deps and Kokoro downloads its model from Hugging Face.
#
# System prerequisite: espeak-ng  (macOS: `brew install espeak-ng`)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SVC="$ROOT/services/tts"
VENV="$SVC/.venv"
PORT="${TTS_PORT:-8900}"

if [ ! -d "$VENV" ]; then
  echo "Creating TTS virtualenv at $VENV …"
  python3 -m venv "$VENV"
fi

# Install/refresh deps when requirements change (marker keeps re-runs fast).
STAMP="$VENV/.requirements.sha"
NEW_SHA="$(shasum "$SVC/requirements.txt" | awk '{print $1}')"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$NEW_SHA" ]; then
  echo "Installing TTS requirements …"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$SVC/requirements.txt"
  echo "$NEW_SHA" > "$STAMP"
fi

echo "Neura Kokoro TTS → http://localhost:${PORT}  (voices: /api/voices)"
cd "$SVC"
exec "$VENV/bin/python" -m uvicorn server:app --host 0.0.0.0 --port "$PORT"
