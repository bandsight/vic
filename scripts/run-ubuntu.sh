#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"

if [ ! -x ".venv/bin/python" ]; then
  echo "Missing .venv. Run scripts/setup-ubuntu.sh first." >&2
  exit 1
fi

export PYTHONPATH=src
export PYTHONIOENCODING=utf-8

.venv/bin/python -m uvicorn main:app --host "$HOST" --port "$PORT" --reload
