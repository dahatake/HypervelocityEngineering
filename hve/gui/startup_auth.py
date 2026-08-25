"""hve.gui.startup_auth — GUI 起動時の GitHub 認証解決（FR-GUI-24）。

起動時に `GH_TOKEN` / `GITHUB_TOKEN` が未設定であれば `gh auth token` を試み、
取得できたトークンを現プロセスの `GH_TOKEN` へ注入する。取得できなかった場合に
限り、`gh auth login` を実行する導線を 1 回だけ提示する。

設計方針:
    - `gh auth login` を自動実行しない。対話ログインは利用者の明示操作に限る。
    - トークン捕捉・注入は `gh_cli`、対話ログイン端末は `GhLoginDialog` を再利用し、
      起動経路向けの別実装を持たない（FR-MAINT-07）。
    - 認証未完了でも GUI は通常どおり起動する（GitHub 連携を必要としない
      Workflow が存在するため）。
"""

from __future__ import annotations

import os
from typing import Optional

from . import gh_cli

__all__ = [
    "has_env_token",
    "resolve_startup_token",
    "ensure_startup_authentication",
]


def has_env_token() -> bool:
    """`GH_TOKEN` / `GITHUB_TOKEN` のいずれかが設定済みかを返す。"""
    return bool(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))


def resolve_startup_token() -> bool:
    """環境変数、無ければ `gh auth token` で認証状態を解決する。

    Returns:
        認証済み（環境変数トークンがある、または注入できた）なら ``True``。
    """
    if has_env_token():
        return True
    token = gh_cli.capture_gh_token()
    if not token:
        return False
    gh_cli.inject_token_into_env(token)
    return True


def ensure_startup_authentication(parent: Optional[object] = None) -> bool:
    """起動時の認証を解決し、未解決ならログイン導線を 1 回提示する。

    Args:
        parent: 確認ダイアログ / ログインダイアログの親ウィジェット。

    Returns:
        最終的に認証済みなら ``True``。利用者が拒否した場合やログインに
        失敗した場合は ``False``（呼び出し側は起動を継続する）。
    """
    if resolve_startup_token():
        return True
    return _prompt_login(parent)


def _ask_login_confirmation(parent: Optional[object]):
    """GitHub CLI ログインを実行するかの確認ダイアログを表示する。"""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(parent)  # type: ignore[arg-type]
    box.setIcon(QMessageBox.Icon.Question)
    # 抽出のため translate() にはリテラルを直接渡す
    box.setWindowTitle(QCoreApplication.translate("startup_auth", "GitHub 認証"))
    box.setText(
        QCoreApplication.translate(
            "startup_auth", "GitHub へのログインが完了していません。"
        )
    )
    box.setInformativeText(
        QCoreApplication.translate(
            "startup_auth",
            "今すぐ `gh auth login` を実行しますか？\n"
            "ログインすると Issue / Pull Request の閲覧・作成とブランチ取得が有効になります。\n"
            "後で設定画面の「GitHub」→「GitHub CLI でログイン」からも実行できます。",
        )
    )
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    return box.exec()


def _login_dialog_factory(parent: Optional[object]):
    """`gh auth login` の埋め込み端末ダイアログを生成する。"""
    from .gh_login_dialog import GhLoginDialog

    return GhLoginDialog(parent)  # type: ignore[arg-type]


def _prompt_login(parent: Optional[object]) -> bool:
    """確認 → 対話ログイン → トークン注入までを 1 回だけ実行する。"""
    from PySide6.QtWidgets import QMessageBox

    if _ask_login_confirmation(parent) != QMessageBox.StandardButton.Yes:
        return False

    _login_dialog_factory(parent).exec()

    token = gh_cli.capture_gh_token()
    if not token:
        return False
    gh_cli.inject_token_into_env(token)
    return True
