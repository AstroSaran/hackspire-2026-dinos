#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x "$ROOT/.venv/bin/python" ]; then python3 -m venv "$ROOT/.venv"; fi
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/backend/requirements-live.txt"
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
