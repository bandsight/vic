#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
OUTPUT_DIR="${OUTPUT_DIR:-vendor}"
WITH_BROWSER="${WITH_BROWSER:-0}"
WITH_NODE_TOOLS="${WITH_NODE_TOOLS:-0}"

WHEELHOUSE="$OUTPUT_DIR/python-wheels"
NPM_CACHE="$OUTPUT_DIR/npm-cache"
mkdir -p "$WHEELHOUSE"

PIP_ARGS=()
if [ "${PIP_TRUSTED_HOST:-0}" = "1" ]; then
  PIP_ARGS+=(--trusted-host pypi.org --trusted-host files.pythonhosted.org)
fi

"$PYTHON_BIN" -m pip download "${PIP_ARGS[@]}" --dest "$WHEELHOUSE" -r requirements-dev.txt

if [ "$WITH_BROWSER" = "1" ]; then
  "$PYTHON_BIN" -m pip download "${PIP_ARGS[@]}" --dest "$WHEELHOUSE" -r requirements-browser.txt
fi

if [ "$WITH_NODE_TOOLS" = "1" ] && [ -f "package.json" ]; then
  mkdir -p "$NPM_CACHE"
  NPM_ARGS=(ci --no-audit --no-fund --prefer-offline --cache "$NPM_CACHE")
  if [ ! -f "package-lock.json" ]; then
    NPM_ARGS=(install --no-audit --no-fund --prefer-offline --cache "$NPM_CACHE")
  fi
  if [ "${NPM_STRICT_SSL_FALSE:-0}" = "1" ]; then
    NPM_ARGS+=(--strict-ssl=false)
  fi
  if [ "${NPM_USE_SYSTEM_CA:-0}" = "1" ]; then
    NODE_OPTIONS="${NODE_OPTIONS:-} --use-system-ca" npm "${NPM_ARGS[@]}"
  else
    npm "${NPM_ARGS[@]}"
  fi
fi

cat > "$OUTPUT_DIR/dependency-bundle.json" <<JSON
{
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "platform": "ubuntu",
  "python_command": "$PYTHON_BIN",
  "wheelhouse": "$WHEELHOUSE",
  "requirements": ["requirements-dev.txt"],
  "with_browser": $([ "$WITH_BROWSER" = "1" ] && echo true || echo false),
  "with_node_tools": $([ "$WITH_NODE_TOOLS" = "1" ] && echo true || echo false),
  "npm_cache": $([ -d "$NPM_CACHE" ] && echo "\"$NPM_CACHE\"" || echo null)
}
JSON

echo "Offline dependency bundle prepared under: $OUTPUT_DIR"
