#!/usr/bin/env bash
# setup.sh — Linux/macOS setup for the standalone markdown-query GUI.
#
# Usage:
#   bash setup.sh                 # install only
#   bash setup.sh --build-index   # also run `mdq index`
#   bash setup.sh --with-watch    # install watchdog (realtime index update)
#   PYTHON=/usr/bin/python3.12 bash setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv-mdq-gui"
VENDOR_DIR="${SCRIPT_DIR}/vendor"
PYTHON="${PYTHON:-python3}"
BUILD_INDEX=0
WITH_WATCH=0
REPO_ROOT="${REPO_ROOT:-$PWD}"

for arg in "$@"; do
    case "$arg" in
        --build-index) BUILD_INDEX=1 ;;
        --with-watch)  WITH_WATCH=1 ;;
        --repo-root=*) REPO_ROOT="${arg#--repo-root=}" ;;
        -h|--help)
            cat <<'EOF'
Usage: bash setup.sh [--build-index] [--with-watch] [--repo-root=PATH]
  --build-index    Run `mdq index` after install to build the initial index.
  --with-watch     Also install watchdog (realtime index update).
  --repo-root=PATH Target repository root for the initial index build
                   (default: $PWD).
Environment:
  PYTHON           Path to a Python >=3.11 interpreter (default: python3).
  REPO_ROOT        Same as --repo-root=PATH.
EOF
            exit 0
            ;;
        *) echo "Unknown argument: $arg" >&2; exit 2 ;;
    esac
done

echo "[markdown-query gui setup] Python: $PYTHON"
"$PYTHON" --version

if [ ! -d "$VENV_DIR" ]; then
    echo "[markdown-query gui setup] Creating venv at $VENV_DIR ..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

VENV_PY="${VENV_DIR}/bin/python"
"$VENV_PY" -m pip install --upgrade pip

echo "[markdown-query gui setup] Installing dependencies (rank_bm25, tiktoken, PySide6)..."
"$VENV_PY" -m pip install "rank_bm25>=0.2.2" "tiktoken>=0.7.0" "PySide6>=6.6"

if [ "$WITH_WATCH" -eq 1 ]; then
    echo "[markdown-query gui setup] Installing watchdog..."
    "$VENV_PY" -m pip install "watchdog>=4.0"
fi

if [ ! -f "${VENDOR_DIR}/mdq/__init__.py" ]; then
    echo "vendor/mdq/ が見つかりません。リポジトリのコピーが不完全です。" >&2
    exit 2
fi

if [ "$BUILD_INDEX" -eq 1 ]; then
    echo "[markdown-query gui setup] Building initial index at $REPO_ROOT ..."
    if [ ! -d "$REPO_ROOT" ]; then
        echo "REPO_ROOT does not exist: $REPO_ROOT" >&2
        exit 2
    fi
    export PYTHONPATH="${VENDOR_DIR}:${PYTHONPATH:-}"
    (cd "$REPO_ROOT" && "$VENV_PY" -m mdq index) \
        || echo "[markdown-query gui setup] WARN: initial index build failed." >&2
fi

# Ensure launchers are executable (Q3 clone hygiene).
chmod +x "${SCRIPT_DIR}/launch-gui.sh" 2>/dev/null || true

echo ""
echo "[markdown-query gui setup] Done."
echo "Launch the GUI with:  bash launch-gui.sh"
