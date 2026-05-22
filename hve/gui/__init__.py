"""hve.gui — PySide6 ベースの GUI フロントエンド（PoC）。

公開 API:
  run_gui()  — GUI モードのエントリポイント。`python -m hve gui` から呼ばれる。

依存:
  PySide6>=6.6 (pyproject.toml の optional dep `gui` 経由でインストール)

設計方針（plan.md §アーキテクチャ参照）:
  - データ層: hve.workbench.state / buffer / task_tree は無改変流用
  - 抽象層: hve.console.Console は CLI 専用、GUI モードは ConsoleAdapter (将来) で代替
  - UI 層: 本パッケージ配下（Qt6/PySide6 専用）
  - State 連携: 別プロセス方式 — orchestrator サブプロセスを fork し stdout/stderr を pipe で配信
"""

from __future__ import annotations

__all__ = ["run_gui"]


def run_gui(args=None) -> int:
    """GUI モードのエントリポイント。

    Args:
        args: ``argparse.Namespace``（``hve/__main__.py`` の `gui` サブパーサ由来）
            または ``None``。``None`` のときは通常 GUI を起動する。

    PySide6 が未インストールの場合は ImportError を返してエラーメッセージを stderr に出力。
    """
    try:
        from .app import run_app
    except ImportError as e:
        import sys
        print(
            "[hve.gui] PySide6 がインストールされていません。\n"
            "  pip install -e .[gui]  でインストールしてください。\n"
            f"  詳細: {e}",
            file=sys.stderr,
        )
        return 2
    return run_app(args)
