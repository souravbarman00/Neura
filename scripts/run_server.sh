#!/usr/bin/env bash
# Launch the Neura neuro-san server (serves the `neura` agent network over HTTP).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Load environment (ANTHROPIC_API_KEY, optional overrides) from .env if present.
# Parse line-by-line (never `source` it) so a key value containing spaces,
# parentheses or other shell-special characters can't break startup.
if [ -f .env ]; then
  while IFS= read -r _line || [ -n "$_line" ]; do
    case "$_line" in ''|\#*) continue ;; esac
    _key="${_line%%=*}"; _val="${_line#*=}"
    [ "$_key" = "$_line" ] && continue          # no '=' on the line
    export "$_key=$_val"
  done < .env
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key." >&2
  exit 1
fi

# Relative manifest path (we cd'd to ROOT): neuro-san splits AGENT_MANIFEST_FILE on
# spaces, so an absolute path under a folder with spaces would shatter and crash.
export AGENT_MANIFEST_FILE="registries/manifest.hocon"
export AGENT_TOOL_PATH="$ROOT/coded_tools"
# Repo root is on the path so `coded_tools.*` and `middleware.*` class references resolve.
export PYTHONPATH="$ROOT:$ROOT/coded_tools:${PYTHONPATH:-}"

# Toolbox + MCP catalogs (used by the agent-network designer family).
export AGENT_TOOLBOX_INFO_FILE="$ROOT/config/toolbox_info.hocon"
export AGENT_NETWORK_DESIGNER_TOOLBOX_INFO_FILE="$ROOT/config/agent_network_designer_toolbox_info.hocon"
export AGENT_NETWORK_DESIGNER_MANIFEST_FILE="registries/manifest.hocon"
export MCP_SERVERS_INFO_FILE="$ROOT/config/mcp/mcp_info.hocon"

# Poll the manifest so newly-spawned networks become live without a restart.
export AGENT_MANIFEST_UPDATE_PERIOD_SECONDS="${AGENT_MANIFEST_UPDATE_PERIOD_SECONDS:-5}"

echo "Neura server → http://localhost:${NEURA_HTTP_PORT:-8099}  (network: neura)"
exec "$ROOT/.venv/bin/python" -m neuro_san.service.main_loop.server_main_loop \
  --http_port "${NEURA_HTTP_PORT:-8099}"
