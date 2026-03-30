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
from typing import Optional

__all__ = [
    "GitHubAPIError",
    "api_call",
    "create_issue",
    "link_sub_issue",
    "post_comment",
    "create_pull_request",
]

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_API_VERSION = "2022-11-28"
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_TIMEOUT = 30


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
    payload: dict = {"title": title, "body": body, "labels": list(labels)}
    if assignees:
        payload["assignees"] = list(assignees)
    resp = api_call("POST", url, data=payload, token=token)
    return (int(resp["number"]), int(resp["id"]))


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


def create_pull_request(
    title: str,
    body: str,
    head: str,
    base: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> int:
    """Pull Request を作成し PR 番号を返す。"""
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls"
    payload = {"title": title, "body": body, "head": head, "base": base}
    resp = api_call("POST", url, data=payload, token=token)
    return int(resp["number"])
