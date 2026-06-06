#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROFILE="${1:-runtime_code}"
OUTPUT_DIR="${OUTPUT_DIR:-exports/portable}"
INCLUDE_DEPENDENCY_BUNDLE="${INCLUDE_DEPENDENCY_BUNDLE:-0}"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
PACKAGE_NAME="eba-workbench-${PROFILE}-${TIMESTAMP}.zip"

mkdir -p "$OUTPUT_DIR"

EXCLUDES=(
  ".env"
  ".git/*"
  ".venv/*"
  ".venv-win/*"
  "node_modules/*"
  "*/__pycache__/*"
  ".pytest_cache/*"
  "cache/*"
  "llm-bundle/*"
  "llm-bundle.zip"
  "artifacts/*"
  "exports/*"
  "var/*"
  "uvicorn-*.log"
  "*.pyc"
)

if [ "$INCLUDE_DEPENDENCY_BUNDLE" != "1" ]; then
  EXCLUDES+=("vendor/*")
fi

if [ "$PROFILE" = "runtime_code" ]; then
  EXCLUDES+=(
    "canonical/*"
    "registers/*"
    "scenario-overrides/*"
    "documents/immutable/*"
    "data/analysis/distribution-point-analysis.json"
    "data/bronze/*"
  )
elif [ "$PROFILE" = "with_governed_data" ]; then
  EXCLUDES+=("documents/immutable/*")
elif [ "$PROFILE" != "with_source_evidence" ]; then
  echo "Unknown profile: $PROFILE" >&2
  exit 1
fi

ZIP_ARGS=()
for pattern in "${EXCLUDES[@]}"; do
  ZIP_ARGS+=("-x" "$pattern")
done

zip -r "$OUTPUT_DIR/$PACKAGE_NAME" . "${ZIP_ARGS[@]}"
echo "Created portable package: $OUTPUT_DIR/$PACKAGE_NAME"
