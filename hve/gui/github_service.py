"""hve.gui.github_service — GUI 向け GitHub 連携サービス層（FR-GUI-28）。

役割は次の 3 点だけに限定する。

    1. リポジトリ（``owner/repo``）と Issue / PR 番号の境界検証
    2. `hve.github_api` への委譲
    3. `GitHubAPIError` の利用者向けメッセージへの変換

HTTP・認証・リトライ・ページングは `hve.github_api` の実装をそのまま使い、
本モジュールで再実装しない（FR-MAINT-07）。PySide6 へは依存しない。
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable, Dict, List, Optional, TypeVar

from hve import github_api
from hve.github_api import GitHubAPIError

__all__ = [
    "GitHubServiceError",
    "resolve_repo",
    "parse_number",
    "current_user_login",
    "list_issues",
    "get_issue",
    "update_issue",
    "list_comments",
    "post_comment",
    "update_comment",
    "list_pull_requests",
    "get_pull_request",
    "list_pull_request_files",
]

_T = TypeVar("_T")

# ``owner/repo``。GitHub が許可する所有者名・リポジトリ名の文字種に合わせる。
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


class GitHubServiceError(Exception):
    """GUI へ表示するための GitHub 連携エラー。"""


def _guess_repo() -> Optional[str]:
    """ローカル git remote から ``owner/repo`` を推定する。

    推定処理は既存実装（`page_options._guess_repo_from_git_remote`）を再利用する。
    本モジュールを PySide6 なしで import できるよう遅延 import する。
    """
    try:
        from .page_options import _guess_repo_from_git_remote
    except ImportError:
        return None
    return _guess_repo_from_git_remote()


def resolve_repo(explicit: Optional[str] = None) -> str:
    """``owner/repo`` を解決する。明示指定 > ``REPO`` 環境変数 > git remote。"""
    for candidate in (explicit, os.environ.get("REPO"), _guess_repo()):
        repo = (candidate or "").strip()
        if not repo:
            continue
        if not _REPO_PATTERN.match(repo):
            raise GitHubServiceError(
                f"リポジトリの指定が不正です: '{repo}'（owner/repo 形式で入力してください）"
            )
        return repo
    raise GitHubServiceError(
        "リポジトリを特定できません。設定画面の「GitHub」でリポジトリ (owner/repo) を指定してください。"
    )


def parse_number(raw: Any) -> int:
    """Issue / PR 番号を正の整数へ検証する。

    URL パスへ直接埋め込まれる値のため、API へ渡す前に境界で検証する。
    """
    if isinstance(raw, bool) or raw is None:
        raise GitHubServiceError(f"番号の指定が不正です: {raw!r}")
    try:
        number = int(str(raw).strip())
    except (TypeError, ValueError):
        raise GitHubServiceError(f"番号の指定が不正です: {raw!r}") from None
    if number <= 0:
        raise GitHubServiceError(f"番号は 1 以上を指定してください: {number}")
    return number


def _describe(exc: GitHubAPIError) -> str:
    """`GitHubAPIError` を利用者向けメッセージへ変換する。"""
    hints = {
        401: "GitHub の認証に失敗しました。設定画面の「GitHub」からログインしてください。",
        403: "権限が不足しているか、レート制限に達しました。",
        404: "対象が見つかりません。リポジトリ名と番号を確認してください。",
        422: "送信内容が GitHub に受け付けられませんでした。",
    }
    head = hints.get(exc.status, "GitHub API の呼び出しに失敗しました。")
    return f"{head} ({exc})"


def _call(fn: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    try:
        return fn(*args, **kwargs)
    except GitHubAPIError as exc:
        raise GitHubServiceError(_describe(exc)) from exc


def _require_body(body: str) -> str:
    text = (body or "").strip()
    if not text:
        raise GitHubServiceError("本文が空です。内容を入力してください。")
    return text


def current_user_login() -> str:
    """認証ユーザーの login を返す。取得できない場合は空文字列。"""
    user = _call(github_api.get_authenticated_user)
    login = user.get("login") if isinstance(user, dict) else None
    return str(login) if login else ""


# ---------------------------------------------------------------------------
# Issue（FR-GUI-26）
# ---------------------------------------------------------------------------


def list_issues(repo: str, state: str = "open", per_page: int = 50) -> List[dict]:
    return _call(github_api.list_issues, repo=repo, state=state, per_page=per_page)


def get_issue(repo: str, number: Any) -> dict:
    return _call(github_api.get_issue, parse_number(number), repo=repo)


def update_issue(
    repo: str,
    number: Any,
    title: Optional[str] = None,
    body: Optional[str] = None,
    state: Optional[str] = None,
) -> dict:
    return _call(
        github_api.update_issue,
        parse_number(number),
        repo=repo,
        title=title,
        body=body,
        state=state,
    )


def list_comments(repo: str, number: Any) -> List[dict]:
    return _call(github_api.list_issue_comments, parse_number(number), repo=repo)


def post_comment(repo: str, number: Any, body: str) -> None:
    text = _require_body(body)
    _call(github_api.post_comment, parse_number(number), text, repo=repo)


def update_comment(repo: str, comment_id: Any, body: str) -> dict:
    text = _require_body(body)
    return _call(github_api.update_comment, parse_number(comment_id), text, repo=repo)


# ---------------------------------------------------------------------------
# Pull Request（FR-GUI-27）
# ---------------------------------------------------------------------------


def list_pull_requests(repo: str, state: str = "open", per_page: int = 50) -> List[dict]:
    return _call(
        github_api.list_pull_requests, repo=repo, state=state, per_page=per_page
    )


def get_pull_request(repo: str, number: Any) -> dict:
    return _call(github_api.get_pull_request, parse_number(number), repo=repo)


def list_pull_request_files(repo: str, number: Any) -> List[Dict[str, Any]]:
    return _call(github_api.list_pull_request_files, parse_number(number), repo=repo)
