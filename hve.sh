#!/bin/sh
# ============================================================
# hve.sh — HVE CLI ランチャー (Linux/macOS)
#
# 目的:
#   .venv を activate せずに、リポジトリ直下の .venv の Python で
#   `python -m hve` を実行する薄いラッパ。
#   activate 漏れによる ModuleNotFoundError (PySide6 等) を防ぐ。
#
# 使い方:
#   ./hve.sh                       (引数なし → GUI 起動 / PySide6 未導入時は CLI フォールバック)
#   ./hve.sh cli
#   ./hve.sh orchestrate --workflow aad
#   ./hve.sh --help
#
# 前提:
#   hve/setup-hve.sh で .venv が作成済みであること。
#   リポジトリ直下での実行を想定（シンボリックリンク経由は非サポート）。
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="$SCRIPT_DIR/.venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
    echo "[ERROR] .venv の Python が見つからない、または実行できません: $VENV_PY" >&2
    echo "        先にセットアップを実行してください: ./hve/setup-hve.sh" >&2
    echo "        詳細: users-guide/hve-cli-getting-started.md" >&2
    exit 1
fi

exec "$VENV_PY" -m hve "$@"
