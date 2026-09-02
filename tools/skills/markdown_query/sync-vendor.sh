#!/usr/bin/env bash
# sync-vendor.sh — Linux/macOS launcher for the shared kit sync (FR-KIT-03).
#
# The rules for what ships and what is excluded live in
# tools/skills/_kit/kit_sync.py. Run this inside the upstream repository only;
# downstream copies ship the generated directories as-is.
#
# Usage:
#   bash sync-vendor.sh
#   bash sync-vendor.sh --source /path/to/mdq
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
ENTRY="$(cd "${SCRIPT_DIR}/.." && pwd)/_kit/kit_sync.py"

if [ ! -f "$ENTRY" ]; then
    echo "shared sync implementation not found: ${ENTRY} (run this inside the upstream repository)" >&2
    exit 2
fi

exec "$PYTHON" "$ENTRY" --kit-dir "$SCRIPT_DIR" "$@"
