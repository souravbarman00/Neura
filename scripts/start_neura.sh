#!/usr/bin/env bash
# One-shot: set up (venv + packages) and start ALL Neura servers.
# Idempotent — safe to re-run. Keeps running in this terminal; Ctrl-C stops everything.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "▸ Neura setup + start   ($ROOT)"

# ---- 1. Python venv ----
if [ ! -x .venv/bin/python ]; then
  echo "▸ Creating virtualenv (.venv)…"
  if command -v uv >/dev/null 2>&1; then uv venv .venv; else python3 -m venv .venv; fi
fi
PY=".venv/bin/python"

# ---- 2. Install Python packages (only when requirements change) ----
REQS=(requirements.txt backend/requirements.txt services/tts/requirements.txt services/stt/requirements.txt)
HASH="$(cat "${REQS[@]}" 2>/dev/null | shasum | awk '{print $1}')"
if [ "$(cat .venv/.neura-deps 2>/dev/null || echo x)" != "$HASH" ]; then
  echo "▸ Installing Python packages (first run can take a few minutes)…"
  ARGS=(); for r in "${REQS[@]}"; do [ -f "$r" ] && ARGS+=(-r "$r"); done
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$PY" "${ARGS[@]}" && echo "$HASH" > .venv/.neura-deps
  else
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q "${ARGS[@]}" && echo "$HASH" > .venv/.neura-deps
  fi
fi
# Browser for screenshots (best-effort; skip if it fails/offline).
"$PY" -c "import playwright" >/dev/null 2>&1 && "$PY" -m playwright install chromium >/dev/null 2>&1 || true

# ---- 3. Build the web UI if missing (best-effort; the VS Code extension has its own UI) ----
if [ ! -f frontend/dist/index.html ] && command -v npm >/dev/null 2>&1; then
  echo "▸ Building the web UI…"
  ( cd frontend && npm install && npm run build ) || echo "  (UI build skipped — backend still starts)"
fi

# ---- 4. .env + API key check ----
[ -f .env ] || { [ -f .env.example ] && cp .env.example .env; }
if ! grep -qiE '^(ANTHROPIC|OPENAI|MISTRAL)_API_KEY=.{15,}' .env 2>/dev/null; then
  echo "⚠  No LLM API key found in .env. Add one, e.g.:  ANTHROPIC_API_KEY=sk-ant-…"
  echo "   (Then re-run this. See the extension's Help for details.)"
fi

# ---- 5. Start all servers; stop them together on Ctrl-C / terminal close ----
export NEURA_HTTP_PORT="${NEURA_HTTP_PORT:-8099}" NEURA_UI_PORT="${NEURA_UI_PORT:-8010}"
export TTS_PORT="${TTS_PORT:-8900}" STT_PORT="${STT_PORT:-8901}"
export NEURA_SERVER_URL="http://localhost:${NEURA_HTTP_PORT}"
export TTS_URL="http://localhost:${TTS_PORT}" STT_URL="http://localhost:${STT_PORT}"

pids=()
cleanup() { echo; echo "▸ Stopping Neura…"; for p in "${pids[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done; }
trap cleanup EXIT INT TERM

echo "▸ Starting servers…"
bash scripts/run_server.sh & pids+=($!)
bash scripts/run_ui.sh     & pids+=($!)
bash scripts/run_tts.sh    & pids+=($!)
bash scripts/run_stt.sh    & pids+=($!)

echo "✅ Neura starting → http://localhost:${NEURA_UI_PORT}"
echo "   The VS Code panel will connect automatically once it's up."
echo "   Keep this terminal open; press Ctrl-C here to stop Neura."
wait
