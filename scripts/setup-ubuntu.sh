#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
OFFLINE="${OFFLINE:-0}"
WHEELHOUSE="${WHEELHOUSE:-vendor/python-wheels}"
PIP_ARGS=()
if [ "$OFFLINE" = "1" ]; then
  if [ ! -d "$WHEELHOUSE" ]; then
    echo "Offline Python wheelhouse not found: $WHEELHOUSE. Run scripts/build-offline-deps.sh first." >&2
    exit 1
  fi
  PIP_ARGS+=(--no-index --find-links "$WHEELHOUSE")
  echo "Using offline Python wheelhouse: $WHEELHOUSE"
elif [ "${PIP_TRUSTED_HOST:-0}" = "1" ]; then
  PIP_ARGS+=(--trusted-host pypi.org --trusted-host files.pythonhosted.org)
fi

if [ ! -d ".venv" ]; then
  echo "Creating Ubuntu virtual environment..."
  "$PYTHON_BIN" -m venv .venv
fi

if [ "$OFFLINE" != "1" ]; then
  .venv/bin/python -m pip install "${PIP_ARGS[@]}" --upgrade pip
fi
.venv/bin/python -m pip install "${PIP_ARGS[@]}" -r requirements-dev.txt

if [ "${WITH_BROWSER:-0}" = "1" ]; then
  .venv/bin/python -m pip install "${PIP_ARGS[@]}" -r requirements-browser.txt
  .venv/bin/python -m playwright install chromium
fi

if [ "${WITH_NODE_TOOLS:-0}" = "1" ] && [ -f "package.json" ]; then
  NPM_ARGS=(ci --no-audit --no-fund)
  NPM_CACHE="${NPM_CACHE:-vendor/npm-cache}"
  if [ ! -f "package-lock.json" ]; then
    NPM_ARGS=(install --no-audit --no-fund)
  fi
  if [ "$OFFLINE" = "1" ]; then
    if [ ! -d "$NPM_CACHE" ]; then
      echo "Offline npm cache not found: $NPM_CACHE. Run scripts/build-offline-deps.sh with WITH_NODE_TOOLS=1 first." >&2
      exit 1
    fi
    NPM_ARGS+=(--offline --cache "$NPM_CACHE")
  elif [ -d "$NPM_CACHE" ]; then
    NPM_ARGS+=(--prefer-offline --cache "$NPM_CACHE")
  fi
  if [ "${NPM_STRICT_SSL_FALSE:-0}" = "1" ]; then
    NPM_ARGS+=(--strict-ssl=false)
  fi
  if [ "${NPM_USE_SYSTEM_CA:-0}" = "1" ]; then
    NODE_OPTIONS="${NODE_OPTIONS:-} --use-system-ca" npm "${NPM_ARGS[@]}"
  else
    npm "${NPM_ARGS[@]}"
  fi
elif [ -f "package.json" ]; then
  echo "Skipped Node tooling install. Set WITH_NODE_TOOLS=1 to install lint/dev dependencies."
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp ".env.example" ".env"
  echo "Created .env from .env.example. Add provider keys before extraction work."
fi

echo "Ubuntu setup complete."
