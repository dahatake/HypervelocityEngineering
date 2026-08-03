"""hve.gui.gh_cli — GitHub CLI (``gh``) 連携ヘルパ。

GUI から ``gh auth login`` でログイン後、``gh auth token`` で取得したトークンを
現プロセスの環境変数 ``GH_TOKEN`` へ橋渡しするための薄いヘルパ群。

設計方針:
    - アプリのトークン解決は環境変数のみ（``hve.auth`` / ``hve.github_api`` /
      ``hve.config``）。``gh`` は資格情報を独自ストアへ保存し環境変数を設定しない
      ため、GUI 側で ``gh auth token`` の出力を ``os.environ`` へ注入する。
    - トークンはセッション限り（``os.environ`` のみ）。ディスクには永続化しない。
    - 例外は呼び出し側へ伝播させない（失敗時は None / 何もしない）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

__all__ = ["find_gh_binary", "capture_gh_token", "inject_token_into_env"]


def find_gh_binary() -> Optional[str]:
    """``gh`` 実行ファイルの絶対パスを返す。見つからなければ ``None``。"""
    return shutil.which("gh")


def capture_gh_token(*, timeout: float = 15.0) -> Optional[str]:
    """``gh auth token`` を実行し、トークン文字列を返す。

    Args:
        timeout: サブプロセスタイムアウト秒。

    Returns:
        非空トークン文字列。``gh`` 未検出・非ログイン・失敗時は ``None``。
    """
    exe = find_gh_binary()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    token = (proc.stdout or "").strip()
    return token or None


def inject_token_into_env(token: str) -> None:
    """トークンを ``os.environ['GH_TOKEN']`` へ設定する（セッション限り）。

    空文字列の場合は何もしない（既存値を消さない）。

    Note:
        トークン参照優先順は ``COPILOT_GITHUB_TOKEN`` > ``GH_TOKEN`` >
        ``GITHUB_TOKEN``。``COPILOT_GITHUB_TOKEN`` が既に設定済みの環境では
        Copilot SDK 経路（モデル一覧等）はそちらを優先する。本注入は
        ``GH_TOKEN`` を見る GitHub REST 経路（``hve.github_api``: ブランチ取得 /
        Issue・PR 作成）を有効化する用途。
    """
    if token:
        os.environ["GH_TOKEN"] = token
