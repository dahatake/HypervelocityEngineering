"""github_api.py — GitHub REST API ユーティリティ

hve/orchestrator.py が使用する最小限の GitHub API 関数を提供する。
旧 `.github/cli/lib/github_api.py` から必要な関数のみ移植。

環境変数 (対応するパラメータ省略時に使用):
    GH_TOKEN / GITHUB_TOKEN — GitHub トークン
    REPO                    — "owner/repo" 形式のリポジトリ
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Optional, cast

__all__ = [
    "GitHubAPIError",
    "api_call",
    "create_issue",
    "add_labels",
    "link_sub_issue",
    "post_comment",
    "list_issue_comments",
    "create_pull_request",
    "get_pull_request",
    "list_pull_request_files",
    "list_check_runs_for_ref",
    "list_branches",
    "get_repository_metadata",
    "list_viewer_repositories",
]

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_API_VERSION = "2022-11-28"
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_TIMEOUT = 30
_PULL_REQUEST_FILES_PAGE_SIZE = 100
_PULL_REQUEST_FILES_MAX = 3000


# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------


class GitHubAPIError(Exception):
    """GitHub API 呼び出し失敗時の例外。"""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------


def _resolve_token(token: Optional[str]) -> str:
    """トークンを解決する。引数 > GH_TOKEN > GITHUB_TOKEN の優先順。"""
    if token:
        return token
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not t:
        raise GitHubAPIError(
            "GitHub token not found. Set GH_TOKEN (or GITHUB_TOKEN) environment variable."
        )
    return t


def _resolve_repo(repo: Optional[str]) -> str:
    """リポジトリを解決する。引数 > REPO 環境変数の優先順。"""
    if repo:
        return repo
    r = os.environ.get("REPO")
    if not r:
        raise GitHubAPIError(
            "Repository not specified. Set REPO environment variable (owner/repo)."
        )
    return r


def _parse_retry_after(value: Optional[str]) -> Optional[int]:
    """Retry-After ヘッダを整数秒に変換する。"""
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------


def api_call(
    method: str,
    url: str,
    data: Optional[dict] = None,
    token: Optional[str] = None,
    timeout: int = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> dict | list:
    """認証付き GitHub API 呼び出し（指数バックオフリトライ付き）。

    リトライポリシー:
      - 最大 max_retries 回試行
      - 401 / 422 / 403(Retry-After なし): 即座に例外
      - 403/429(Retry-After あり): 指定秒数待機してリトライ
      - その他: 指数バックオフ (1, 2, 4, 8 秒)

    Returns:
        パース済み JSON レスポンス (dict or list)。空ボディは {} を返す。

    Raises:
        GitHubAPIError: リトライ上限到達、またはリトライ不可エラー時。
    """
    resolved_token = _resolve_token(token)
    headers: dict = {
        "Authorization": f"Bearer {resolved_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
    }
    body_bytes: Optional[bytes]
    if data is not None:
        body_bytes = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    else:
        body_bytes = None

    wait = 1
    last_error: Optional[Exception] = None
    last_status: int = 0

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            url, data=body_bytes, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                if not raw:
                    return {}
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise GitHubAPIError(
                        f"非JSONレスポンス (HTTP {resp.status}): {method} {url}"
                        f" — {raw[:200]!r}",
                        resp.status,
                    ) from exc

        except urllib.error.HTTPError as exc:
            status = exc.code
            last_status = status
            last_error = exc

            if status == 401:
                raise GitHubAPIError(
                    f"認証失敗 (HTTP 401): {method} {url}", status
                ) from exc

            if status == 422:
                try:
                    error_body = exc.read().decode()
                except Exception:
                    error_body = "(unreadable)"
                raise GitHubAPIError(
                    f"処理不可能エンティティ (HTTP 422): {method} {url} — {error_body}",
                    status,
                ) from exc

            if status in (403, 429):
                retry_after_secs = _parse_retry_after(
                    exc.headers.get("Retry-After") if exc.headers else None
                )
                if retry_after_secs is not None:
                    print(
                        f"レート制限 (HTTP {status})、{retry_after_secs}秒後にリトライ"
                        f" ({attempt}/{max_retries})",
                        flush=True,
                    )
                    time.sleep(retry_after_secs)
                    continue
                if status == 403:
                    raise GitHubAPIError(
                        f"アクセス拒否 (HTTP 403): {method} {url}", status
                    ) from exc

            if attempt < max_retries:
                print(
                    f"API エラー: HTTP {status}、{wait}秒後にリトライ"
                    f" ({attempt}/{max_retries})",
                    flush=True,
                )
                time.sleep(wait)
                wait *= 2

        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < max_retries:
                print(
                    f"ネットワークエラー: {exc.reason}、{wait}秒後にリトライ"
                    f" ({attempt}/{max_retries})",
                    flush=True,
                )
                time.sleep(wait)
                wait *= 2

    raise GitHubAPIError(
        f"API 呼び出し失敗{f' (HTTP {last_status})' if last_status else ' (network error)'}: {method} {url}",
        last_status,
    ) from last_error


def get_repository_metadata(
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """リポジトリの metadata を取得する。"""
    resolved_repo = _resolve_repo(repo)
    resp = api_call("GET", f"{_GITHUB_API_BASE}/repos/{resolved_repo}", token=token)
    return resp if isinstance(resp, dict) else {}


def list_viewer_repositories(
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """認証ユーザーが参照可能なリポジトリ一覧（先頭 1 ページ）を取得する。"""
    page_size = max(1, min(100, int(per_page)))
    url = (
        f"{_GITHUB_API_BASE}/user/repos"
        "?affiliation=owner,collaborator,organization_member"
        f"&sort=updated&per_page={page_size}"
    )
    resp = api_call("GET", url, token=token)
    if not isinstance(resp, list):
        return []
    return [repo for repo in resp if isinstance(repo, dict)]


def create_issue(
    title: str,
    body: str,
    labels: list,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    assignees: Optional[list] = None,
) -> tuple:
    """GitHub Issue を作成し (number, id) を返す。

    id は Sub Issues API が要求する数値データベース ID。

    Args:
        assignees: アサイン先ユーザー名のリスト（例: ["copilot"]）。
                   None または空リストの場合はアサインしない。
    """
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues"
    payload: dict[str, Any] = {
        "title": title,
        "body": body,
        "labels": list(labels),
    }
    if assignees:
        payload["assignees"] = list(assignees)
    raw_resp = api_call("POST", url, data=payload, token=token)
    if not isinstance(raw_resp, dict):
        raise GitHubAPIError("create issue response is not an object")
    resp = cast(dict[str, Any], raw_resp)
    number = resp.get("number")
    issue_id = resp.get("id")
    if number is None or issue_id is None:
        raise GitHubAPIError("create issue response is missing number or id")
    return (int(number), int(issue_id))


def add_labels(
    issue_num: int,
    labels: list,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> bool:
    """Issue にラベルを付与する。"""
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/{issue_num}/labels"
    try:
        api_call("POST", url, data={"labels": list(labels)}, token=token)
    except GitHubAPIError as exc:
        print(f"WARNING: add_labels 失敗: {exc}", flush=True)
        return False
    time.sleep(1)
    return True


def link_sub_issue(
    parent_num: int,
    child_id: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> bool:
    """Issue を親 Issue のサブイシューとしてリンクする（冪等）。

    エラーはログ出力のみで例外を再送出しない（bash の ``|| true`` パターン）。
    """
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/{parent_num}/sub_issues"
    success = True
    try:
        api_call("POST", url, data={"sub_issue_id": child_id}, token=token)
    except GitHubAPIError as exc:
        if exc.status != 422:
            print(f"WARNING: link_sub_issue 失敗: {exc}", flush=True)
            success = False
    finally:
        time.sleep(1)
    return success


def post_comment(
    issue_num: int,
    body: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> bool:
    """Issue / PR にコメントを投稿する。"""
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/{issue_num}/comments"
    api_call("POST", url, data={"body": body}, token=token)
    time.sleep(1)
    return True


def list_issue_comments(
    issue_num: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """Issue / PR コメント一覧（先頭 1 ページ）を取得する。"""
    resolved_repo = _resolve_repo(repo)
    page_size = max(1, min(100, int(per_page)))
    url = (
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/"
        f"{issue_num}/comments?per_page={page_size}"
    )
    resp = api_call("GET", url, token=token)
    if not isinstance(resp, list):
        return []
    return [comment for comment in resp if isinstance(comment, dict)]


def create_pull_request(
    title: str,
    body: str,
    head: str,
    base: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    draft: bool = False,
) -> int:
    """Pull Request を作成し PR 番号を返す。"""
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls"
    payload: dict[str, Any] = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
    }
    if draft:
        # draft は必要時のみ送信し、既存の PR 作成 payload を変えない。
        payload = {**payload, "draft": True}
    raw_resp = api_call("POST", url, data=payload, token=token)
    if not isinstance(raw_resp, dict):
        raise GitHubAPIError("create pull request response is not an object")
    resp = cast(dict[str, Any], raw_resp)
    number = resp.get("number")
    if number is None:
        raise GitHubAPIError("create pull request response is missing number")
    return int(number)


def get_pull_request(
    pr_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """PR の情報（``merged`` / ``state`` 等）を取得して dict で返す。

    FR-CLI-34 のマージ完了検知に使用する。非 dict レスポンス時は空 dict を返す。
    """
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls/{pr_number}"
    resp = api_call("GET", url, token=token)
    return resp if isinstance(resp, dict) else {}


def _sanitize_pull_request_file(entry: object, index: int) -> dict:
    """PR Files API の 1 行を path 判定に必要な最小フィールドへ縮約する。"""

    if not isinstance(entry, dict):
        raise GitHubAPIError(f"invalid pull request file entry at index {index}: not an object")
    filename = entry.get("filename")
    status = entry.get("status")
    if not isinstance(filename, str) or not filename:
        raise GitHubAPIError(
            f"invalid pull request file entry at index {index}: filename is missing"
        )
    if not isinstance(status, str) or not status:
        raise GitHubAPIError(
            f"invalid pull request file entry at index {index}: status is missing"
        )

    result = {"filename": filename, "status": status}
    previous = entry.get("previous_filename")
    if status in {"renamed", "copied"}:
        if not isinstance(previous, str) or not previous:
            raise GitHubAPIError(
                f"invalid pull request file entry at index {index}: "
                f"{status} source is missing"
            )
        result["previous_filename"] = previous
    return result


def list_pull_request_files(
    pr_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> list[dict]:
    """PR の変更ファイルを全ページ取得し、最小フィールドだけを返す。

    GitHub REST API の当該 endpoint は最大 3,000 files である。PR metadata の
    ``changed_files`` と取得件数を照合し、上限超過・途中空ページ・非 list・件数
    不一致を部分結果へ縮退せず例外にする。``patch`` 等の本文は保持しない。
    """

    resolved_repo = _resolve_repo(repo)
    metadata = get_pull_request(pr_number, repo=resolved_repo, token=token)
    expected = metadata.get("changed_files")
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise GitHubAPIError("pull request metadata changed_files is invalid")
    if expected > _PULL_REQUEST_FILES_MAX:
        raise GitHubAPIError(
            "pull request has more than the GitHub API limit of 3,000 changed files"
        )
    if expected == 0:
        return []

    result: list[dict] = []
    page = 1
    while len(result) < expected:
        url = (
            f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls/{pr_number}/files"
            f"?per_page={_PULL_REQUEST_FILES_PAGE_SIZE}&page={page}"
        )
        response = api_call("GET", url, token=token)
        if not isinstance(response, list):
            raise GitHubAPIError(
                f"pull request files page {page} response is not a list"
            )
        if not response:
            raise GitHubAPIError(
                f"pull request changed_files expected {expected} but retrieved {len(result)}"
            )
        start = len(result)
        result.extend(
            _sanitize_pull_request_file(entry, start + index)
            for index, entry in enumerate(response)
        )
        if len(result) > expected:
            raise GitHubAPIError(
                f"pull request changed_files expected {expected} but retrieved {len(result)}"
            )
        page += 1

    if len(result) != expected:
        raise GitHubAPIError(
            f"pull request changed_files expected {expected} but retrieved {len(result)}"
        )
    return result


def list_check_runs_for_ref(
    ref: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """commit ref に紐づく check-run 一覧を返す。"""
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/commits/{ref}/check-runs?per_page={per_page}"
    resp = api_call("GET", url, token=token)
    if not isinstance(resp, dict):
        return []
    runs = resp.get("check_runs")
    return runs if isinstance(runs, list) else []


def list_branches(
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[str]:
    """リポジトリのブランチ名一覧を取得する。

    Args:
        repo: "owner/repo" 形式。省略時は REPO 環境変数を使用。
        token: GitHub トークン。省略時は GH_TOKEN / GITHUB_TOKEN を使用。
        per_page: 1 ページの件数（最大 100）。ページネーションは行わず先頭 1 ページのみ。

    Returns:
        ブランチ名のリスト。

    Raises:
        GitHubAPIError: 認証失敗・リポジトリ不在（404）・ネットワークエラー等。
    """
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/branches?per_page={per_page}"
    resp = api_call("GET", url, token=token)
    if not isinstance(resp, list):
        return []
    return [b["name"] for b in resp if isinstance(b, dict) and "name" in b]
