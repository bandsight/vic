#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SOURCE_ZIP="${1:-}"
DESTINATION="${2:-}"
FORCE="${FORCE:-0}"
RUN_SETUP="${RUN_SETUP:-0}"

if [ -z "$SOURCE_ZIP" ]; then
  SOURCE_ZIP="$(ls -t exports/portable/eba-workbench-*.zip 2>/dev/null | head -n 1 || true)"
fi

if [ -z "$SOURCE_ZIP" ] || [ ! -f "$SOURCE_ZIP" ]; then
  echo "Source zip not found. Provide a zip path or create a package first." >&2
  exit 1
fi

if [ -z "$DESTINATION" ]; then
  base_name="$(basename "$SOURCE_ZIP" .zip)"
  DESTINATION="$ROOT/exports/portable/unpacked/$base_name"
fi

if [ -e "$DESTINATION" ]; then
  if [ "$FORCE" != "1" ]; then
    echo "Destination already exists: $DESTINATION. Set FORCE=1 to replace it." >&2
    exit 1
  fi
  rm -rf "$DESTINATION"
fi

mkdir -p "$DESTINATION"
unzip -q "$SOURCE_ZIP" -d "$DESTINATION"

mkdir -p \
  "$DESTINATION/cache" \
  "$DESTINATION/exports" \
  "$DESTINATION/var" \
  "$DESTINATION/artifacts" \
  "$DESTINATION/canonical" \
  "$DESTINATION/registers" \
  "$DESTINATION/scenario-overrides" \
  "$DESTINATION/documents/immutable" \
  "$DESTINATION/data/analysis"

if [ ! -f "$DESTINATION/.env" ] && [ -f "$DESTINATION/.env.example" ]; then
  cp "$DESTINATION/.env.example" "$DESTINATION/.env"
fi

cat > "$DESTINATION/var/portable-install.json" <<JSON
{
  "unpacked_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "source_zip": "$(cd "$(dirname "$SOURCE_ZIP")" && pwd)/$(basename "$SOURCE_ZIP")",
  "destination": "$(cd "$DESTINATION" && pwd)",
  "platform": "ubuntu",
  "setup_run": $([ "$RUN_SETUP" = "1" ] && echo true || echo false)
}
JSON

if [ "$RUN_SETUP" = "1" ]; then
  bash "$DESTINATION/scripts/setup-ubuntu.sh"
fi

echo "Unpacked workbench to: $DESTINATION"
