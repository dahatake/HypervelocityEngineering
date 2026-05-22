#!/usr/bin/env bash
# clear-python-catch.sh
# Python バイトコードキャッシュ (__pycache__ / *.pyc / *.pyo) を再帰的に削除する。
# macOS / Linux 対応。
#
# 使い方:
#   bash tools/hve-app-cash/clear-python-catch.sh
#   bash tools/hve-app-cash/clear-python-catch.sh /path/to/repo
#   bash tools/hve-app-cash/clear-python-catch.sh --dry-run

set -euo pipefail

DRY_RUN=0
TARGET=""

for arg in "$@"; do
    case "$arg" in
        -n|--dry-run|--DryRun)
            DRY_RUN=1
            ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            TARGET="$arg"
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$TARGET" ]]; then
    TARGET="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

if [[ ! -d "$TARGET" ]]; then
    echo "Path が見つかりません: $TARGET" >&2
    exit 1
fi

echo "[clear-python-catch] target: $TARGET"
[[ $DRY_RUN -eq 1 ]] && echo "[clear-python-catch] DryRun モード (削除はしません)"

DIR_COUNT=$(find "$TARGET" -type d -name "__pycache__" 2>/dev/null | wc -l | tr -d ' ')
FILE_COUNT=$(find "$TARGET" -type f \( -name "*.pyc" -o -name "*.pyo" \) 2>/dev/null | wc -l | tr -d ' ')
echo "[clear-python-catch] __pycache__ ディレクトリ: ${DIR_COUNT} 件"
echo "[clear-python-catch] *.pyc / *.pyo ファイル   : ${FILE_COUNT} 件"

if [[ $DRY_RUN -eq 1 ]]; then
    find "$TARGET" -type d -name "__pycache__" -print 2>/dev/null | sed 's/^/DIR  /'
    find "$TARGET" -type f \( -name "*.pyc" -o -name "*.pyo" \) -print 2>/dev/null | sed 's/^/FILE /'
    exit 0
fi

find "$TARGET" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$TARGET" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true

echo "[clear-python-catch] 完了"
