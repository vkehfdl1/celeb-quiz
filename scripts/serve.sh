#!/usr/bin/env bash
# Serves the celeb-quiz repo root via the admin server (static + REST API).
# Both web/ and data/ are reachable on the same origin; /admin/ exposes the
# curation UI; /api/* endpoints handle entry mutations.
#
# Usage: bash scripts/serve.sh [port]
set -euo pipefail

PORT="${1:-8765}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  exec python3 scripts/admin_server.py --port "$PORT"
elif command -v python >/dev/null 2>&1; then
  exec python scripts/admin_server.py --port "$PORT"
else
  echo "Error: python3 (or python) is required." >&2
  exit 1
fi
