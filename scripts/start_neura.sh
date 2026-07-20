#!/usr/bin/env bash
# One-shot: set up (venv + packages) and start ALL Neura servers.
# Thin POSIX wrapper around the cross-platform launcher (scripts/neura_serve.py).
# Keeps running in this terminal; Ctrl-C stops everything.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
exec "$PY" "$ROOT/scripts/neura_serve.py" "$@"
