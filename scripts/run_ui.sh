#!/usr/bin/env bash
# Launch the Neura UI backend (serves the web app + proxies chat/voice).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export NEURA_SERVER_URL="${NEURA_SERVER_URL:-http://localhost:8099}"
export TTS_URL="${TTS_URL:-http://localhost:8900}"
PORT="${NEURA_UI_PORT:-8010}"
echo "Neura UI → http://localhost:${PORT}"
exec "$ROOT/.venv/bin/python" -m uvicorn backend.app:app --host 0.0.0.0 --port "${PORT}"
