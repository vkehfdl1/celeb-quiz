#!/usr/bin/env bash
# Serves the celeb-quiz repo root over HTTP so both web/ and data/ are reachable
# on the same origin (required for fetch() to load list.jsonl + images).
#
# Usage: bash scripts/serve.sh [port]
set -euo pipefail

PORT="${1:-8000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT"

echo "celeb-quiz local server"
echo "  Repo root : $ROOT"
echo "  Port      : $PORT"
echo "  Open      : http://localhost:$PORT/web/"
echo

if command -v python3 >/dev/null 2>&1; then
  exec python3 -m http.server "$PORT"
elif command -v python >/dev/null 2>&1; then
  exec python -m http.server "$PORT"
else
  echo "Error: python3 (or python) is required." >&2
  exit 1
fi
