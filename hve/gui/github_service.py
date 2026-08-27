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
    "create_issue",
    "create_issue_details",
    "list_labels",
    "list_assignees",
    "list_milestones",
    "list_issue_creation_metadata",
    "list_issues",
    "get_issue",
    "update_issue",
    "assign_copilot_agent",
    "list_comments",
    "create_comment",
    "post_comment",
    "update_comment",
    "list_pull_requests",
    "get_pull_request",
    "list_pull_request_reviews",
    "create_pull_request_review",
    "list_pull_request_review_comments",
    "create_pull_request_review_comment",
    "list_pull_request_files",
    "list_check_runs",
    "merge_pull_request",
    "get_repository_metadata",
    "compare_commits",
    "find_open_pull_request",
    "create_pull_request",
    "apply_pull_request_metadata",
    "delete_branch",
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
    for candidate in (explicit, os.environ.get("REPO")):
        repo = (candidate or "").strip()
        if not repo:
            continue
        if not _REPO_PATTERN.match(repo):
            raise GitHubServiceError(
                f"リポジトリの指定が不正です: '{repo}'（owner/repo 形式で入力してください）"
            )
        return repo
    candidate = _guess_repo()
    repo = (candidate or "").strip()
    if repo:
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
        405: "Pull Request をマージできません。保護ルール、レビュー、check-runs、draft 状態を確認してください。",
        409: "Pull Request の head が更新されたか競合しています。最新状態を再取得してください。",
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


def _require_title(title: str) -> str:
    text = (title or "").strip()
    if not text:
        raise GitHubServiceError("タイトルが空です。タイトルを入力してください。")
    return text


def current_user_login() -> str:
    """認証ユーザーの login を返す。取得できない場合は空文字列。"""
    user = _call(github_api.get_authenticated_user)
    login = user.get("login") if isinstance(user, dict) else None
    return str(login) if login else ""


# ---------------------------------------------------------------------------
# Issue（FR-GUI-26）
# ---------------------------------------------------------------------------


def create_issue(
    repo: str,
    title: str,
    body: str = "",
    *,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    milestone: Optional[int] = None,
) -> tuple[int, int]:
    """title / Markdown body から通常 Issue を作成する（FR-GUI-35）。"""
    kwargs: dict[str, Any] = {"repo": repo}
    if assignees:
        kwargs["assignees"] = list(assignees)
    if milestone is not None:
        kwargs["milestone"] = milestone
    result = _call(
        github_api.create_issue,
        _require_title(title),
        body,
        list(labels or []),
        **kwargs,
    )
    return int(result[0]), int(result[1])


def create_issue_details(
    repo: str,
    title: str,
    body: str = "",
    *,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    milestone: Optional[int] = None,
) -> dict:
    """Issue を作成し、requested metadata の反映結果を返す（FR-GUI-41）。"""
    requested_labels = [str(value).strip() for value in labels or [] if str(value).strip()]
    requested_assignees = [
        str(value).strip() for value in assignees or [] if str(value).strip()
    ]
    requested_milestone = parse_number(milestone) if milestone is not None else None
    response = _call(
        github_api.create_issue_details,
        _require_title(title),
        body or "",
        requested_labels,
        repo=repo,
        assignees=requested_assignees,
        milestone=requested_milestone,
        max_retries=1,
    )
    number = parse_number(response.get("number") if isinstance(response, dict) else None)
    issue_id = parse_number(response.get("id") if isinstance(response, dict) else None)
    actual_labels = {
        str(item.get("name"))
        for item in response.get("labels", [])
        if isinstance(item, dict) and item.get("name")
    }
    actual_assignees = {
        str(item.get("login"))
        for item in response.get("assignees", [])
        if isinstance(item, dict) and item.get("login")
    }
    actual_milestone = response.get("milestone")
    actual_milestone_number = (
        actual_milestone.get("number") if isinstance(actual_milestone, dict) else None
    )
    warnings: list[dict[str, Any]] = []
    for name in requested_labels:
        if name not in actual_labels:
            warnings.append({"kind": "label", "value": name})
    for login in requested_assignees:
        if login not in actual_assignees:
            warnings.append({"kind": "assignee", "value": login})
    if requested_milestone is not None and actual_milestone_number != requested_milestone:
        warnings.append({"kind": "milestone", "value": requested_milestone})
    return {
        "number": number,
        "id": issue_id,
        "html_url": str(response.get("html_url") or ""),
        "warnings": warnings,
    }


def list_labels(repo: str) -> List[dict]:
    return _call(github_api.list_labels, repo=repo, per_page=100)


def list_assignees(repo: str) -> List[dict]:
    return _call(github_api.list_assignees, repo=repo, per_page=100)


def list_milestones(repo: str) -> List[dict]:
    return _call(github_api.list_milestones, repo=repo, per_page=100)


def list_issue_creation_metadata(repo: str) -> dict:
    """Issue 作成候補を明示取得 1 回でまとめる。"""
    return {
        "labels": list_labels(repo),
        "assignees": list_assignees(repo),
        "milestones": list_milestones(repo),
    }


def list_issues(
    repo: str,
    state: str = "open",
    per_page: int = 50,
    page: int = 1,
    cursor: Optional[str] = None,
) -> List[dict]:
    options: dict[str, Any] = {
        "repo": repo,
        "state": state,
        "per_page": per_page,
        "page": page,
    }
    if cursor is not None:
        options["cursor"] = cursor
    return _call(
        github_api.list_issues,
        **options,
    )


def get_issue(repo: str, number: Any) -> dict:
    return _call(github_api.get_issue, parse_number(number), repo=repo)


def update_issue(
    repo: str,
    number: Any,
    title: Optional[str] = None,
    body: Optional[str] = None,
    state: Optional[str] = None,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    milestone: Optional[Any] = None,
) -> dict:
    milestone_number: Optional[int] = None
    if milestone is not None:
        if isinstance(milestone, bool):
            raise GitHubServiceError("マイルストーン番号は 0 以上の整数を指定してください。")
        try:
            milestone_number = int(str(milestone).strip())
        except (TypeError, ValueError):
            raise GitHubServiceError(
                "マイルストーン番号は 0 以上の整数を指定してください。"
            ) from None
        if milestone_number < 0:
            raise GitHubServiceError("マイルストーン番号は 0 以上の整数を指定してください。")
    return _call(
        github_api.update_issue,
        parse_number(number),
        repo=repo,
        title=title,
        body=body,
        state=state,
        labels=labels,
        assignees=assignees,
        milestone=milestone_number,
    )


def assign_copilot_agent(
    repo: str,
    number: Any,
    base_branch: Optional[str] = None,
) -> dict:
    """選択中 Issue を Copilot cloud agent へ割り当てる。"""
    branch: Optional[str] = None
    if base_branch is not None:
        if not isinstance(base_branch, str):
            raise GitHubServiceError("base branch の指定が不正です。")
        branch = base_branch.strip() or None
    return _call(
        github_api.assign_copilot_agent,
        parse_number(number),
        repo=resolve_repo(repo),
        base_branch=branch,
    )


def list_comments(repo: str, number: Any) -> List[dict]:
    return _call(github_api.list_issue_comments, parse_number(number), repo=repo)


def create_comment(repo: str, number: Any, body: str) -> Optional[int]:
    """コメントを作成し、作成された comment ID を返す（FR-GUI-36）。

    本文は Markdown をそのまま送る（`create_issue` と同じ方針）。自動進捗 Post の
    formatter 出力を GUI 側で書き換えないためであり、空判定だけを行う。
    ID を確定できない応答では ``None`` を返す。
    """
    if not (body or "").strip():
        raise GitHubServiceError("本文が空です。内容を入力してください。")
    return _call(github_api.create_comment, parse_number(number), body, repo=repo)


def post_comment(repo: str, number: Any, body: str) -> None:
    text = _require_body(body)
    _call(github_api.post_comment, parse_number(number), text, repo=repo)


def update_comment(repo: str, comment_id: Any, body: str) -> dict:
    text = _require_body(body)
    return _call(github_api.update_comment, parse_number(comment_id), text, repo=repo)


# ---------------------------------------------------------------------------
# Pull Request（FR-GUI-27）
# ---------------------------------------------------------------------------


def list_pull_requests(
    repo: str,
    state: str = "open",
    per_page: int = 50,
    page: int = 1,
    cursor: Optional[str] = None,
) -> List[dict]:
    options: dict[str, Any] = {
        "repo": repo,
        "state": state,
        "per_page": per_page,
        "page": page,
    }
    if cursor is not None:
        options["cursor"] = cursor
    return _call(
        github_api.list_pull_requests,
        **options,
    )


def get_pull_request(repo: str, number: Any) -> dict:
    return _call(github_api.get_pull_request, parse_number(number), repo=repo)


def list_pull_request_reviews(
    repo: str,
    number: Any,
    per_page: int = 100,
) -> List[dict]:
    return _call(
        github_api.list_pull_request_reviews,
        parse_number(number),
        repo=repo,
        per_page=per_page,
    )


def create_pull_request_review(
    repo: str,
    number: Any,
    event: str,
    body: Optional[str] = None,
) -> dict:
    return _call(
        github_api.create_pull_request_review,
        parse_number(number),
        event,
        body,
        repo=repo,
    )


def list_pull_request_review_comments(
    repo: str,
    number: Any,
    per_page: int = 100,
) -> List[dict]:
    return _call(
        github_api.list_pull_request_review_comments,
        parse_number(number),
        repo=repo,
        per_page=per_page,
    )


def create_pull_request_review_comment(
    repo: str,
    number: Any,
    body: str,
    commit_id: str,
    path: str,
    line: int,
    side: str,
) -> dict:
    return _call(
        github_api.create_pull_request_review_comment,
        parse_number(number),
        body,
        commit_id,
        path,
        line,
        side,
        repo=repo,
    )


def list_pull_request_files(repo: str, number: Any) -> List[Dict[str, Any]]:
    return _call(github_api.list_pull_request_files, parse_number(number), repo=repo)


def list_check_runs(repo: str, ref: Any) -> List[dict]:
    """選択中 PR の head SHA に対する check-runs を明示取得する。"""
    if not isinstance(ref, str) or not ref.strip():
        raise GitHubServiceError("Pull Request の head SHA を特定できません。")
    return _call(
        github_api.list_check_runs_for_ref,
        ref.strip(),
        repo=repo,
        per_page=100,
    )


def merge_pull_request(
    repo: str,
    number: Any,
    merge_method: str,
    *,
    sha: Optional[str] = None,
) -> dict:
    """利用者が確認した方式で Pull Request を同期マージする。"""
    return _call(
        github_api.merge_pull_request,
        parse_number(number),
        merge_method,
        repo=repo,
        sha=sha,
    )


def get_repository_metadata(repo: str) -> dict:
    return _call(github_api.get_repository_metadata, repo=resolve_repo(repo))


def compare_commits(repo: str, base: str, head: str) -> dict:
    base_name = (base or "").strip()
    head_name = (head or "").strip()
    if not base_name or not head_name:
        raise GitHubServiceError("base branch と head branch を指定してください。")
    return _call(
        github_api.compare_commits,
        base_name,
        head_name,
        repo=resolve_repo(repo),
    )


def find_open_pull_request(repo: str, head: str, base: str) -> Optional[dict]:
    return _call(
        github_api.find_open_pull_request,
        (head or "").strip(),
        (base or "").strip(),
        repo=resolve_repo(repo),
    )


def create_pull_request(
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str,
    *,
    draft: bool = False,
) -> dict:
    """GitHub Hub から Pull Request を作成する（FR-GUI-42）。"""
    head_name = (head or "").strip()
    base_name = (base or "").strip()
    if not head_name or not base_name:
        raise GitHubServiceError("base branch と head branch を指定してください。")
    result = _call(
        github_api.create_pull_request_details,
        _require_title(title),
        body or "",
        head_name,
        base_name,
        repo=resolve_repo(repo),
        draft=bool(draft),
        max_retries=1,
    )
    parse_number(result.get("number") if isinstance(result, dict) else None)
    return result


def apply_pull_request_metadata(
    repo: str,
    pr_number: Any,
    *,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    milestone: Optional[int] = None,
    reviewers: Optional[List[str]] = None,
    team_reviewers: Optional[List[str]] = None,
) -> dict:
    """PR 作成後 metadata を独立適用し、失敗項目だけを再試行用に返す。"""
    number = parse_number(pr_number)
    resolved_repo = resolve_repo(repo)
    label_values = [str(value).strip() for value in labels or [] if str(value).strip()]
    assignee_values = [
        str(value).strip() for value in assignees or [] if str(value).strip()
    ]
    reviewer_values = [
        str(value).strip() for value in reviewers or [] if str(value).strip()
    ]
    team_values = [
        str(value).strip() for value in team_reviewers or [] if str(value).strip()
    ]
    milestone_number = parse_number(milestone) if milestone is not None else None
    retry: dict[str, Any] = {"pr_number": number}
    warnings: list[dict[str, str]] = []
    metadata_response: dict = {}
    reviewer_response: dict = {}

    if label_values or assignee_values or milestone_number is not None:
        try:
            metadata_response = _call(
                github_api.update_pull_request_metadata,
                number,
                repo=resolved_repo,
                labels=label_values,
                assignees=assignee_values,
                milestone=milestone_number,
            )
        except GitHubServiceError:
            warnings.append({"kind": "metadata"})
            retry.update(
                labels=label_values,
                assignees=assignee_values,
                milestone=milestone_number,
            )

    if reviewer_values or team_values:
        try:
            reviewer_response = _call(
                github_api.request_pull_request_reviewers,
                number,
                repo=resolved_repo,
                reviewers=reviewer_values,
                team_reviewers=team_values,
            )
        except GitHubServiceError:
            warnings.append({"kind": "reviewers"})
            retry.update(reviewers=reviewer_values, team_reviewers=team_values)

    return {
        "warnings": warnings,
        "retry": retry if len(retry) > 1 else None,
        "metadata": metadata_response,
        "reviewers": reviewer_response,
    }


# ---------------------------------------------------------------------------
# ブランチ（FR-GUI-34）
# ---------------------------------------------------------------------------


def delete_branch(repo: str, branch: Any) -> None:
    """リモートのブランチを削除する。

    ブランチ名の妙当性検査は `hve.github_api` 側で行う（FR-GUI-28）。
    本関数は空値の境界だけを見て利用者向け文言へ変換する。
    """
    name = str(branch or "").strip()
    if not name:
        raise GitHubServiceError("削除するブランチを特定できません。")
    _call(github_api.delete_branch_ref, name, repo=repo)
