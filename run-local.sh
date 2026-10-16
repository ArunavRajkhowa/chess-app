#!/usr/bin/env bash
# One-command local run: installs what is missing, builds the frontend, starts the server.
# Usage: ./run-local.sh            (production-style: one process on http://127.0.0.1:8765)
#        ./run-local.sh dev        (backend + Vite dev server with hot reload on :5173)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r backend/requirements.txt

if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi
(cd frontend && node scripts/copy-engine.mjs)

if [ "${1:-}" = "dev" ]; then
  (cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) &
  python -m uvicorn backend.app:app --host 127.0.0.1 --port "${PORT:-8765}" --reload
else
  (cd frontend && npm run build)
  echo "Open http://127.0.0.1:${PORT:-8765}"
  python -m uvicorn backend.app:app --host 127.0.0.1 --port "${PORT:-8765}"
fi
