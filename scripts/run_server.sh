#!/usr/bin/env bash
# Launch the Neura neuro-san server (serves the `neura` agent network over HTTP).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Load environment (ANTHROPIC_API_KEY, optional overrides) from .env if present.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key." >&2
  exit 1
fi

export AGENT_MANIFEST_FILE="$ROOT/registries/manifest.hocon"
export AGENT_TOOL_PATH="$ROOT/coded_tools"
# Repo root is on the path so `coded_tools.*` and `middleware.*` class references resolve.
export PYTHONPATH="$ROOT:$ROOT/coded_tools:${PYTHONPATH:-}"

# Toolbox + MCP catalogs (used by the agent-network designer family).
export AGENT_TOOLBOX_INFO_FILE="$ROOT/config/toolbox_info.hocon"
export AGENT_NETWORK_DESIGNER_TOOLBOX_INFO_FILE="$ROOT/config/agent_network_designer_toolbox_info.hocon"
export AGENT_NETWORK_DESIGNER_MANIFEST_FILE="$ROOT/registries/manifest.hocon"
export MCP_SERVERS_INFO_FILE="$ROOT/config/mcp/mcp_info.hocon"

# Poll the manifest so newly-spawned networks become live without a restart.
export AGENT_MANIFEST_UPDATE_PERIOD_SECONDS="${AGENT_MANIFEST_UPDATE_PERIOD_SECONDS:-5}"

echo "Neura server → http://localhost:${NEURA_HTTP_PORT:-8099}  (network: neura)"
exec "$ROOT/.venv/bin/python" -m neuro_san.service.main_loop.server_main_loop \
  --http_port "${NEURA_HTTP_PORT:-8099}"
