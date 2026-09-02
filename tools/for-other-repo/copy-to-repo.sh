#!/usr/bin/env bash
# copy-to-repo.sh — Linux/macOS ランチャー。判断は copy_to_repo.py が単独で持つ。
#
# 使い方:
#   bash copy-to-repo.sh /path/to/other-repo/tools/hve-kits
#   bash copy-to-repo.sh /path/to/other-repo/tools -p tool-search
#   bash copy-to-repo.sh --list
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
ENTRY="${SCRIPT_DIR}/copy_to_repo.py"

if [ ! -f "$ENTRY" ]; then
    echo "copy_to_repo.py not found: ${ENTRY}" >&2
    exit 2
fi

exec "$PYTHON" "$ENTRY" "$@"
