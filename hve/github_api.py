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
import urllib.parse
import urllib.request
from collections.abc import MutableMapping
from typing import Any, Optional, cast

from hve.git_ref import is_valid_branch_name
from hve.github_copilot_assignment_contract import (
    COPILOT_AGENT_LOGIN,
    CopilotAssignmentContractError,
    validate_copilot_assignment_response,
)
from hve.github_review_contract import (
    ReviewValidationError,
    validate_pull_request_review,
)

__all__ = [
    "GitHubAPIError",
    "api_call",
    "create_issue",
    "create_issue_details",
    "list_labels",
    "list_assignees",
    "list_milestones",
    "add_labels",
    "link_sub_issue",
    "create_comment",
    "post_comment",
    "list_issue_comments",
    "update_comment",
    "list_issues",
    "get_issue",
    "update_issue",
    "assign_copilot_agent",
    "create_pull_request",
    "create_pull_request_details",
    "compare_commits",
    "find_open_pull_request",
    "update_pull_request_metadata",
    "request_pull_request_reviewers",
    "get_pull_request",
    "list_pull_requests",
    "list_pull_request_reviews",
    "create_pull_request_review",
    "list_pull_request_review_comments",
    "create_pull_request_review_comment",
    "list_pull_request_files",
    "merge_pull_request",
    "list_check_runs_for_ref",
    "list_branches",
    "delete_branch_ref",
    "get_repository_metadata",
    "get_authenticated_user",
    "list_viewer_repositories",
]

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_API_VERSION = "2022-11-28"
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_TIMEOUT = 30
_PULL_REQUEST_FILES_PAGE_SIZE = 100
_PULL_REQUEST_FILES_MAX = 3000
_LIST_STATES = ("open", "closed", "all")
_ISSUE_UPDATE_STATES = ("open", "closed")
_PULL_REQUEST_REVIEW_COMMENT_SIDES = ("LEFT", "RIGHT")
_PULL_REQUEST_MERGE_METHODS = ("merge", "squash", "rebase")
_LINK_PARAMETER_TOKEN_CHARS = frozenset(
    "!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)


class _PaginatedPage(list[dict]):
    """GitHub ``Link`` header の検証済み next cursor を保持するページ。"""

    def __init__(
        self,
        values: list[dict],
        *,
        next_url: Optional[str],
    ) -> None:
        super().__init__(values)
        self.next_url = next_url


class _PullRequestFiles(list[dict]):
    """Files API の取得基準になった Pull Request head SHA を保持する。"""

    def __init__(self, values: list[dict], *, head_sha: str) -> None:
        super().__init__(values)
        self.head_sha = head_sha


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


def _resolve_page_size(per_page: int) -> int:
    """GitHub API が受け付ける 1..100 の範囲へ丸める。"""
    return max(1, min(100, int(per_page)))


def _require_list_state(state: str) -> str:
    """一覧 API の ``state`` を検証する。"""
    if state not in _LIST_STATES:
        raise GitHubAPIError(
            f"invalid state '{state}'. expected one of {list(_LIST_STATES)}"
        )
    return state


def _require_page(page: int) -> int:
    """ページ番号を 1 以上の整数として検証する（FR-GUI-48）。"""
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise GitHubAPIError("page must be an integer greater than or equal to 1")
    return page


def _require_pagination_url(url: object, expected_path: str) -> str:
    """GitHub が返した next URL を認証付き request に安全な形へ制限する。"""
    if not isinstance(url, str) or not url or url != url.strip():
        raise GitHubAPIError("pagination cursor must be a non-empty URL")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in url):
        raise GitHubAPIError("pagination cursor contains a control character")

    try:
        parsed = urllib.parse.urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise GitHubAPIError("pagination cursor is not a valid URL") from exc
    if (
        parsed.scheme.lower() != "https"
        or hostname is None
        or hostname.lower() != "api.github.com"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
        or parsed.path != expected_path
    ):
        raise GitHubAPIError(
            "pagination cursor must use HTTPS api.github.com and the same endpoint path"
        )
    return urllib.parse.urlunsplit(
        ("https", "api.github.com", parsed.path, parsed.query, "")
    )


def _split_link_header(value: str) -> list[str]:
    """Link header を angle bracket / quote 内の comma を壊さず分割する。"""
    parts: list[str] = []
    start = 0
    in_angle = False
    in_quote = False
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if in_quote and char == "\\":
            escaped = True
            continue
        if char == '"' and not in_angle:
            in_quote = not in_quote
            continue
        if not in_quote:
            if char == "<":
                if in_angle:
                    raise GitHubAPIError("pagination Link header is malformed")
                in_angle = True
            elif char == ">":
                if not in_angle:
                    raise GitHubAPIError("pagination Link header is malformed")
                in_angle = False
            elif char == "," and not in_angle:
                part = value[start:index].strip()
                if part:
                    parts.append(part)
                start = index + 1
    if in_angle or in_quote or escaped:
        raise GitHubAPIError("pagination Link header is malformed")
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _split_link_parameters(value: str) -> list[str]:
    """link-value の parameter を quoted-string 内の semicolon を保って分割する。"""
    parameters: list[str] = []
    start = 0
    in_quote = False
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if in_quote and char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if char == ";" and not in_quote:
            parameter = value[start:index].strip()
            if parameter:
                parameters.append(parameter)
            start = index + 1
    if in_quote or escaped:
        raise GitHubAPIError("pagination Link header is malformed")
    tail = value[start:].strip()
    if tail:
        parameters.append(tail)
    return parameters


def _unquote_link_value(value: str) -> str:
    """HTTP quoted-string の quoted-pair を後続 octet へ復号する。"""
    result: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            result.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            result.append(char)
    if escaped:
        raise GitHubAPIError("pagination Link header is malformed")
    return "".join(result)


def _parse_next_link(value: object) -> Optional[str]:
    """RFC 8288 Link header から一意な ``rel=next`` URL を抽出する。"""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise GitHubAPIError("pagination Link header is not a string")

    next_urls: list[str] = []
    for part in _split_link_header(value):
        if not part.startswith("<") or ">" not in part:
            raise GitHubAPIError("pagination Link header is malformed")
        closing = part.find(">")
        target = part[1:closing]
        suffix = part[closing + 1 :].strip()
        if not target or (suffix and not suffix.startswith(";")):
            raise GitHubAPIError("pagination Link header is malformed")

        relations: list[str] = []
        rel_seen = False
        anchor_seen = False
        for parameter in _split_link_parameters(suffix):
            parameter = parameter.strip()
            if not parameter:
                continue
            if "=" in parameter:
                name, raw_value = parameter.split("=", 1)
            else:
                name, raw_value = parameter, None
            parameter_name = name.strip().lower()
            if parameter_name == "anchor":
                anchor_seen = True
                continue
            if parameter_name != "rel":
                continue
            if rel_seen:
                # RFC 8288 §3.3: 2個目以降の rel は無視する。
                continue
            rel_seen = True
            if raw_value is None:
                continue
            relation_value = raw_value.strip()
            if relation_value.startswith('"') or relation_value.endswith('"'):
                if (
                    len(relation_value) < 2
                    or not relation_value.startswith('"')
                    or not relation_value.endswith('"')
                ):
                    raise GitHubAPIError("pagination Link header has malformed rel")
                relation_value = _unquote_link_value(relation_value[1:-1])
                if not relation_value or any(
                    ord(char) < 0x20 or ord(char) == 0x7F
                    for char in relation_value
                ):
                    raise GitHubAPIError(
                        "pagination Link header has malformed rel"
                    )
                relations.extend(relation_value.lower().split())
            else:
                if not relation_value or any(
                    char not in _LINK_PARAMETER_TOKEN_CHARS
                    for char in relation_value
                ):
                    raise GitHubAPIError(
                        "pagination Link header has malformed rel"
                    )
                relations.append(relation_value.lower())
        # pagination application は anchor で上書きされた context を適用しない。
        if not anchor_seen and "next" in relations:
            next_urls.append(target)

    if len(next_urls) > 1:
        raise GitHubAPIError("pagination Link header has multiple rel=next URLs")
    return next_urls[0] if next_urls else None


def _get_header(headers: MutableMapping[str, str], name: str) -> Optional[str]:
    """Mockを含む応答header mapから大文字小文字を無視して値を取得する。"""
    expected = name.lower()
    for key, value in headers.items():
        if str(key).lower() == expected:
            return str(value)
    return None


def _request_paginated_page(
    url: str,
    *,
    expected_path: str,
    token: Optional[str],
) -> tuple[dict | list, Optional[str]]:
    """1ページを取得し、検証済みの opaque next cursor と組にして返す。"""
    current_url = _require_pagination_url(url, expected_path)
    response_headers: dict[str, str] = {}
    response = api_call(
        "GET",
        current_url,
        token=token,
        response_headers=response_headers,
    )
    next_candidate = _parse_next_link(_get_header(response_headers, "link"))
    next_url = (
        _require_pagination_url(next_candidate, expected_path)
        if next_candidate is not None
        else None
    )
    if next_url == current_url:
        raise GitHubAPIError("pagination cursor cycle detected")
    return response, next_url


def _list_all_paginated_objects(
    initial_url: str,
    *,
    expected_path: str,
    token: Optional[str],
    response_name: str,
) -> list[dict]:
    """Link headerだけを継続条件としてobject配列を全ページ取得する。"""
    result: list[dict] = []
    current_url: Optional[str] = initial_url
    seen: set[str] = set()
    while current_url is not None:
        normalized = _require_pagination_url(current_url, expected_path)
        if normalized in seen:
            raise GitHubAPIError("pagination cursor cycle detected")
        seen.add(normalized)
        response, current_url = _request_paginated_page(
            normalized,
            expected_path=expected_path,
            token=token,
        )
        if not isinstance(response, list):
            raise GitHubAPIError(f"{response_name} response is not a list")
        if any(not isinstance(item, dict) for item in response):
            raise GitHubAPIError(
                f"{response_name} response contains a non-object entry"
            )
        result.extend(cast(list[dict], response))
    return result


def _copy_string_list(value: object, field: str) -> list[str]:
    """GitHub の文字列配列を検証して defensive copy する。"""
    if not isinstance(value, list):
        raise GitHubAPIError(f"{field} must be a list of non-empty strings")
    if any(not isinstance(item, str) or not item for item in value):
        raise GitHubAPIError(f"{field} must be a list of non-empty strings")
    return list(value)


def _parse_retry_after(value: Optional[str]) -> Optional[int]:
    """Retry-After ヘッダを整数秒に変換する。"""
    if not value:
        return None
    try:
        seconds = int(value)
    except (ValueError, TypeError):
        return None
    return seconds if seconds >= 0 else None


def _require_positive_number(value: object, field: str) -> int:
    """URL path に埋め込む Issue / PR / comment 番号を検証する。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GitHubAPIError(f"{field} must be a positive integer")
    return value


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
    response_headers: Optional[MutableMapping[str, str]] = None,
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
    if (
        isinstance(max_retries, bool)
        or not isinstance(max_retries, int)
        or max_retries <= 0
    ):
        raise GitHubAPIError("max_retries must be a positive integer")
    if response_headers is not None:
        response_headers.clear()
    resolved_token = _resolve_token(token)
    request_headers: dict = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
    }
    body_bytes: Optional[bytes]
    if data is not None:
        body_bytes = json.dumps(data).encode()
        request_headers["Content-Type"] = "application/json"
    else:
        body_bytes = None

    wait = 1
    last_error: Optional[Exception] = None
    last_status: int = 0

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(
            url, data=body_bytes, headers=request_headers, method=method
        )
        # urllib の redirect handler は通常 header を次 origin へ複製する。
        # Authorization は初回 request 限定 header として保持し、redirectへ渡さない。
        req.add_unredirected_header("Authorization", f"Bearer {resolved_token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                if response_headers is not None:
                    for key, value in (resp.headers or {}).items():
                        normalized_key = str(key).lower()
                        normalized_value = str(value)
                        if normalized_key == "link" and normalized_key in response_headers:
                            response_headers[normalized_key] = (
                                f"{response_headers[normalized_key]}, {normalized_value}"
                            )
                        else:
                            response_headers[normalized_key] = normalized_value
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

            if status in (405, 409):
                raise GitHubAPIError(
                    f"要求失敗 (HTTP {status}): {method} {url}",
                    status,
                ) from exc

            if status in (403, 429):
                error_headers: Any = exc.headers or {}
                retry_after_secs = _parse_retry_after(
                    error_headers.get("Retry-After")
                )
                if retry_after_secs is not None:
                    if attempt >= max_retries:
                        break
                    print(
                        f"レート制限 (HTTP {status})、{retry_after_secs}秒後にリトライ"
                        f" ({attempt}/{max_retries})",
                        flush=True,
                    )
                    time.sleep(retry_after_secs)
                    continue
                if error_headers.get("X-RateLimit-Remaining") == "0":
                    try:
                        reset_epoch = int(
                            error_headers.get("X-RateLimit-Reset", "")
                        )
                    except (TypeError, ValueError):
                        reset_epoch = 0
                    if reset_epoch > 0:
                        if attempt >= max_retries:
                            break
                        reset_wait = max(0, reset_epoch - int(time.time()))
                        print(
                            f"レート上限 (HTTP {status})、{reset_wait}秒後にリトライ"
                            f" ({attempt}/{max_retries})",
                            flush=True,
                        )
                        time.sleep(reset_wait)
                        continue
                if status == 429:
                    if attempt >= max_retries:
                        break
                    retry_wait = max(60, wait)
                    print(
                        f"レート制限 (HTTP 429)、{retry_wait}秒後にリトライ"
                        f" ({attempt}/{max_retries})",
                        flush=True,
                    )
                    time.sleep(retry_wait)
                    wait = retry_wait * 2
                    continue
                if status == 403:
                    raise GitHubAPIError(
                        f"アクセス拒否 (HTTP 403): {method} {url}", status
                    ) from exc

            if 400 <= status < 500:
                raise GitHubAPIError(
                    f"要求失敗 (HTTP {status}): {method} {url}", status
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


def get_authenticated_user(token: Optional[str] = None) -> dict:
    """認証ユーザーの情報を取得する（FR-GUI-26 の自コメント判定に使用）。"""
    resp = api_call("GET", f"{_GITHUB_API_BASE}/user", token=token)
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
    body: Optional[str],
    labels: list,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    assignees: Optional[list] = None,
    milestone: Optional[int] = None,
) -> tuple:
    """GitHub Issue を作成し (number, id) を返す。

    id は Sub Issues API が要求する数値データベース ID。

    Args:
        assignees: アサイン先ユーザー名のリスト（例: ["copilot"]）。
                   None または空リストの場合はアサインしない。
    """
    resp = create_issue_details(
        title,
        body,
        labels,
        repo=repo,
        token=token,
        assignees=assignees,
        milestone=milestone,
    )
    return (int(resp["number"]), int(resp["id"]))


def create_issue_details(
    title: str,
    body: Optional[str],
    labels: Optional[list] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    assignees: Optional[list] = None,
    milestone: Optional[int] = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> dict:
    """GitHub Issue を作成し、API の response object を返す（FR-GUI-41）。"""
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues"
    payload: dict[str, Any] = {
        "title": title,
        "labels": list(labels or []),
    }
    if body is not None:
        payload["body"] = body
    if assignees:
        payload["assignees"] = list(assignees)
    if milestone is not None:
        payload["milestone"] = int(milestone)
    call_kwargs: dict[str, Any] = {"data": payload, "token": token}
    if max_retries != _DEFAULT_MAX_RETRIES:
        call_kwargs["max_retries"] = max_retries
    raw_resp = api_call("POST", url, **call_kwargs)
    if not isinstance(raw_resp, dict):
        raise GitHubAPIError("create issue response is not an object")
    resp = cast(dict[str, Any], raw_resp)
    number = resp.get("number")
    issue_id = resp.get("id")
    if number is None or issue_id is None:
        raise GitHubAPIError("create issue response is missing number or id")
    return resp


def list_labels(
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """Issue 作成候補の labels を先頭 1 ページだけ取得する。"""
    resolved_repo = _resolve_repo(repo)
    page_size = _resolve_page_size(per_page)
    response = api_call(
        "GET",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/labels?per_page={page_size}",
        token=token,
    )
    if not isinstance(response, list):
        raise GitHubAPIError("labels response is not a list")
    return [item for item in response if isinstance(item, dict) and item.get("name")]


def list_assignees(
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """Issue 作成候補の assignees を先頭 1 ページだけ取得する。"""
    resolved_repo = _resolve_repo(repo)
    page_size = _resolve_page_size(per_page)
    response = api_call(
        "GET",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/assignees?per_page={page_size}",
        token=token,
    )
    if not isinstance(response, list):
        raise GitHubAPIError("assignees response is not a list")
    return [item for item in response if isinstance(item, dict) and item.get("login")]


def list_milestones(
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """Issue 作成候補の open milestones を先頭 1 ページだけ取得する。"""
    resolved_repo = _resolve_repo(repo)
    page_size = _resolve_page_size(per_page)
    response = api_call(
        "GET",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/milestones"
        f"?state=open&sort=due_on&direction=asc&per_page={page_size}",
        token=token,
    )
    if not isinstance(response, list):
        raise GitHubAPIError("milestones response is not a list")
    return [
        item
        for item in response
        if isinstance(item, dict)
        and isinstance(item.get("number"), int)
        and not isinstance(item.get("number"), bool)
        and item["number"] > 0
        and item.get("title")
    ]


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
    """Issue を親 Issue のサブイシューとしてリンクする。

    エラーはログ出力のみで例外を再送出しない（bash の ``|| true`` パターン）。
    """
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/{parent_num}/sub_issues"
    success = True
    try:
        api_call("POST", url, data={"sub_issue_id": child_id}, token=token)
    except GitHubAPIError as exc:
        print(f"WARNING: link_sub_issue 失敗: {exc}", flush=True)
        success = False
    finally:
        time.sleep(1)
    return success


def create_comment(
    issue_num: int,
    body: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[int]:
    """Issue / PR にコメントを投稿し、作成された comment ID を返す（FR-GUI-36）。

    コメント作成 endpoint の唯一の実装とし、`post_comment` は本関数を包む
    （FR-MAINT-07）。応答が dict でない場合や `id` が正の整数でない場合は
    ``None`` を返す（推定変換は行わない）。
    """
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/{issue_num}/comments"
    resp = api_call("POST", url, data={"body": body}, token=token)
    time.sleep(1)
    if not isinstance(resp, dict):
        return None
    comment_id = resp.get("id")
    if isinstance(comment_id, bool) or not isinstance(comment_id, int) or comment_id <= 0:
        return None
    return comment_id


def post_comment(
    issue_num: int,
    body: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> bool:
    """Issue / PR にコメントを投稿する。

    既存の戻り値契約（成功時 ``True``）を維持するための薄い wrapper。
    endpoint 実装は `create_comment` に集約する（FR-MAINT-07）。
    """
    comment_id = create_comment(issue_num, body, repo=repo, token=token)
    if comment_id is None:
        raise GitHubAPIError("post comment response did not confirm creation")
    return True


def list_issue_comments(
    issue_num: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """Issue / PR 会話コメントを API 順のまま全ページ取得する。"""
    issue_num = _require_positive_number(issue_num, "issue_num")
    resolved_repo = _resolve_repo(repo)
    page_size = _resolve_page_size(per_page)
    expected_path = f"/repos/{resolved_repo}/issues/{issue_num}/comments"
    return _list_all_paginated_objects(
        f"{_GITHUB_API_BASE}{expected_path}?per_page={page_size}",
        expected_path=expected_path,
        token=token,
        response_name="issue comments",
    )


def update_comment(
    comment_id: int,
    body: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Issue / PR コメントの本文を更新する（FR-GUI-26）。"""
    comment_id = _require_positive_number(comment_id, "comment_id")
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/comments/{comment_id}"
    resp = api_call("PATCH", url, data={"body": body}, token=token)
    if not isinstance(resp, dict):
        raise GitHubAPIError("update comment response is not an object")
    response_id = resp.get("id")
    if (
        isinstance(response_id, bool)
        or not isinstance(response_id, int)
        or response_id != comment_id
    ):
        raise GitHubAPIError("update comment response did not confirm comment_id")
    return resp


def list_issues(
    repo: Optional[str] = None,
    token: Optional[str] = None,
    state: str = "open",
    per_page: int = 50,
    page: int = 1,
    cursor: Optional[str] = None,
) -> list[dict]:
    """Issue 一覧の指定ページを取得する（FR-GUI-26 / FR-GUI-48）。

    GitHub の Issues API は Pull Request も同じ一覧へ返すため、
    ``pull_request`` キーを持つエントリを除外する。
    """
    resolved_repo = _resolve_repo(repo)
    resolved_state = _require_list_state(state)
    page_size = _resolve_page_size(per_page)
    resolved_page = _require_page(page)
    expected_path = f"/repos/{resolved_repo}/issues"
    initial_url = (
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues"
        f"?state={resolved_state}&sort=created&direction=desc&per_page={page_size}"
    )
    if cursor is not None:
        if resolved_page != 1:
            raise GitHubAPIError("page and pagination cursor cannot be combined")
        url = _require_pagination_url(cursor, expected_path)
    else:
        url = initial_url
        if resolved_page > 1:
            url += f"&page={resolved_page}"
    resp, next_url = _request_paginated_page(
        url,
        expected_path=expected_path,
        token=token,
    )
    if not isinstance(resp, list):
        raise GitHubAPIError("issues response is not a list")
    if any(not isinstance(issue, dict) for issue in resp):
        raise GitHubAPIError("issues response contains a non-object entry")
    raw_issues = cast(list[dict], resp)
    if any(
        isinstance(issue.get("number"), bool)
        or not isinstance(issue.get("number"), int)
        or issue["number"] <= 0
        for issue in raw_issues
    ):
        raise GitHubAPIError("issues response contains an invalid number")
    return _PaginatedPage([
        issue
        for issue in raw_issues
        if "pull_request" not in issue
    ], next_url=next_url)


def get_issue(
    issue_num: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """Issue の詳細を取得する（FR-GUI-25 / FR-GUI-26）。

    Raises:
        GitHubAPIError: レスポンスが object でない場合。FR-GUI-25 の fail-closed を
            成立させるため、空 dict へ縮退させない。
    """
    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/{issue_num}"
    resp = api_call("GET", url, token=token)
    if not isinstance(resp, dict):
        raise GitHubAPIError(f"get issue #{issue_num} response is not an object")
    return resp


def update_issue(
    issue_num: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    title: Optional[str] = None,
    body: Optional[str] = None,
    state: Optional[str] = None,
    labels: Optional[list[str]] = None,
    assignees: Optional[list[str]] = None,
    milestone: Optional[int] = None,
) -> dict:
    """Issue の本文・状態・metadata を更新する（FR-GUI-26 / FR-GUI-44）。

    ``None`` の項目は payload へ含めない。空文字列は本文の消去、空の
    labels / assignees は全解除、milestone ``0`` は未設定への変更を表す。
    """
    issue_num = _require_positive_number(issue_num, "issue_num")
    payload: dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if state is not None:
        if state not in _ISSUE_UPDATE_STATES:
            raise GitHubAPIError(
                f"invalid state '{state}'. expected one of {list(_ISSUE_UPDATE_STATES)}"
            )
        payload["state"] = state
    if labels is not None:
        payload["labels"] = _copy_string_list(labels, "labels")
    if assignees is not None:
        payload["assignees"] = _copy_string_list(assignees, "assignees")
    if milestone is not None:
        if isinstance(milestone, bool) or not isinstance(milestone, int) or milestone < 0:
            raise GitHubAPIError("milestone must be a non-negative integer")
        payload["milestone"] = None if milestone == 0 else milestone
    if not payload:
        raise GitHubAPIError("update_issue called with no fields to update")

    resolved_repo = _resolve_repo(repo)
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/{issue_num}"
    resp = api_call("PATCH", url, data=payload, token=token)
    if not isinstance(resp, dict):
        raise GitHubAPIError("update issue response is not an object")
    response_number = resp.get("number")
    if (
        isinstance(response_number, bool)
        or not isinstance(response_number, int)
        or response_number != issue_num
    ):
        raise GitHubAPIError("update issue response did not confirm issue number")
    if labels is not None:
        response_labels = resp.get("labels")
        if not isinstance(response_labels, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not item["name"]
            for item in response_labels
        ):
            raise GitHubAPIError("update issue response has invalid labels")
    if assignees is not None:
        response_assignees = resp.get("assignees")
        if not isinstance(response_assignees, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("login"), str)
            or not item["login"]
            for item in response_assignees
        ):
            raise GitHubAPIError("update issue response has invalid assignees")
    if milestone is not None:
        response_milestone = resp.get("milestone", ...)
        if milestone == 0:
            if response_milestone is not None:
                raise GitHubAPIError("update issue response has invalid milestone")
        elif (
            not isinstance(response_milestone, dict)
            or isinstance(response_milestone.get("number"), bool)
            or not isinstance(response_milestone.get("number"), int)
        ):
            raise GitHubAPIError("update issue response has invalid milestone")
    return resp


def assign_copilot_agent(
    issue_num: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    base_branch: Optional[str] = None,
) -> dict:
    """既存 Issue を Copilot cloud agent へ割り当てる（preview）。"""
    issue_num = _require_positive_number(issue_num, "issue_num")
    resolved_repo = _resolve_repo(repo)
    agent_assignment: dict[str, str] = {"target_repo": resolved_repo}
    if base_branch is not None:
        if not isinstance(base_branch, str):
            raise GitHubAPIError("invalid base_branch: expected a string")
        if base_branch.strip():
            try:
                agent_assignment["base_branch"] = _require_branch_name(base_branch)
            except GitHubAPIError as exc:
                raise GitHubAPIError(f"invalid base_branch: {exc}") from exc

    response = api_call(
        "POST",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/{issue_num}/assignees",
        data={
            "assignees": [COPILOT_AGENT_LOGIN],
            "agent_assignment": agent_assignment,
        },
        token=token,
    )
    time.sleep(1)
    try:
        return validate_copilot_assignment_response(response, issue_num)
    except CopilotAssignmentContractError as exc:
        raise GitHubAPIError(str(exc)) from exc


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
    resp = create_pull_request_details(
        title,
        body,
        head,
        base,
        repo=repo,
        token=token,
        draft=draft,
    )
    return int(resp["number"])


def create_pull_request_details(
    title: str,
    body: str,
    head: str,
    base: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    draft: bool = False,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> dict:
    """Pull Request を作成し、API の response object を返す（FR-GUI-42）。"""
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
    call_kwargs: dict[str, Any] = {"data": payload, "token": token}
    if max_retries != _DEFAULT_MAX_RETRIES:
        call_kwargs["max_retries"] = max_retries
    raw_resp = api_call("POST", url, **call_kwargs)
    if not isinstance(raw_resp, dict):
        raise GitHubAPIError("create pull request response is not an object")
    resp = cast(dict[str, Any], raw_resp)
    number = resp.get("number")
    if number is None:
        raise GitHubAPIError("create pull request response is missing number")
    return resp


def compare_commits(
    base: str,
    head: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """base と head の比較結果を取得する（FR-GUI-42）。"""
    resolved_repo = _resolve_repo(repo)
    encoded_base = urllib.parse.quote((base or "").strip(), safe="")
    encoded_head = urllib.parse.quote((head or "").strip(), safe="")
    if not encoded_base or not encoded_head:
        raise GitHubAPIError("compare base and head are required")
    response = api_call(
        "GET",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/compare/{encoded_base}...{encoded_head}",
        token=token,
    )
    if not isinstance(response, dict):
        raise GitHubAPIError("compare commits response is not an object")
    return response


def find_open_pull_request(
    head: str,
    base: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[dict]:
    """同一 repository の head/base に一致する open PR を返す。"""
    resolved_repo = _resolve_repo(repo)
    owner = resolved_repo.split("/", 1)[0]
    query = urllib.parse.urlencode(
        {
            "state": "open",
            "head": f"{owner}:{(head or '').strip()}",
            "base": (base or "").strip(),
            "per_page": 1,
        }
    )
    response = api_call(
        "GET",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls?{query}",
        token=token,
    )
    if not isinstance(response, list):
        raise GitHubAPIError("find open pull request response is not a list")
    return next((item for item in response if isinstance(item, dict)), None)


def update_pull_request_metadata(
    pr_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    labels: Optional[list] = None,
    assignees: Optional[list] = None,
    milestone: Optional[int] = None,
) -> dict:
    """PR の Issue-compatible metadata を更新する（FR-GUI-43）。"""
    payload: dict[str, Any] = {}
    if labels:
        payload["labels"] = list(labels)
    if assignees:
        payload["assignees"] = list(assignees)
    if milestone is not None:
        payload["milestone"] = int(milestone)
    if not payload:
        return {}
    resolved_repo = _resolve_repo(repo)
    response = api_call(
        "PATCH",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/issues/{pr_number}",
        data=payload,
        token=token,
    )
    if not isinstance(response, dict):
        raise GitHubAPIError("update pull request metadata response is not an object")
    return response


def request_pull_request_reviewers(
    pr_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    reviewers: Optional[list] = None,
    team_reviewers: Optional[list] = None,
) -> dict:
    """PR の user / team reviewers を要求する（FR-GUI-43）。"""
    payload: dict[str, Any] = {}
    if reviewers:
        payload["reviewers"] = list(reviewers)
    if team_reviewers:
        payload["team_reviewers"] = list(team_reviewers)
    if not payload:
        return {}
    resolved_repo = _resolve_repo(repo)
    response = api_call(
        "POST",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls/{pr_number}/requested_reviewers",
        data=payload,
        token=token,
    )
    if not isinstance(response, dict):
        raise GitHubAPIError("request pull request reviewers response is not an object")
    return response


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


def list_pull_requests(
    repo: Optional[str] = None,
    token: Optional[str] = None,
    state: str = "open",
    per_page: int = 50,
    page: int = 1,
    cursor: Optional[str] = None,
) -> list[dict]:
    """Pull Request 一覧の指定ページを取得する（FR-GUI-27 / FR-GUI-48）。"""
    resolved_repo = _resolve_repo(repo)
    resolved_state = _require_list_state(state)
    page_size = _resolve_page_size(per_page)
    resolved_page = _require_page(page)
    expected_path = f"/repos/{resolved_repo}/pulls"
    initial_url = (
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls"
        f"?state={resolved_state}&sort=created&direction=desc&per_page={page_size}"
    )
    if cursor is not None:
        if resolved_page != 1:
            raise GitHubAPIError("page and pagination cursor cannot be combined")
        url = _require_pagination_url(cursor, expected_path)
    else:
        url = initial_url
        if resolved_page > 1:
            url += f"&page={resolved_page}"
    resp, next_url = _request_paginated_page(
        url,
        expected_path=expected_path,
        token=token,
    )
    if not isinstance(resp, list):
        raise GitHubAPIError("pull requests response is not a list")
    if any(not isinstance(pr, dict) for pr in resp):
        raise GitHubAPIError("pull requests response contains a non-object entry")
    raw_pulls = cast(list[dict], resp)
    if any(
        isinstance(pr.get("number"), bool)
        or not isinstance(pr.get("number"), int)
        or pr["number"] <= 0
        for pr in raw_pulls
    ):
        raise GitHubAPIError("pull requests response contains an invalid number")
    return _PaginatedPage(raw_pulls, next_url=next_url)


def list_pull_request_reviews(
    pr_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """PR review を GitHub API の時系列順のまま取得する（FR-GUI-45）。"""
    pr_number = _require_positive_number(pr_number, "pr_number")
    resolved_repo = _resolve_repo(repo)
    page_size = _resolve_page_size(per_page)
    expected_path = f"/repos/{resolved_repo}/pulls/{pr_number}/reviews"
    return _list_all_paginated_objects(
        f"{_GITHUB_API_BASE}{expected_path}?per_page={page_size}",
        expected_path=expected_path,
        token=token,
        response_name="pull request reviews",
    )


def create_pull_request_review(
    pr_number: int,
    event: str,
    body: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """APPROVE / REQUEST_CHANGES / COMMENT review を提出する（FR-GUI-45）。"""
    pr_number = _require_positive_number(pr_number, "pr_number")
    try:
        event, body = validate_pull_request_review(event, body)
    except ReviewValidationError as exc:
        raise GitHubAPIError(str(exc)) from exc

    payload: dict[str, Any] = {"event": event}
    if body is not None and body.strip():
        payload["body"] = body
    resolved_repo = _resolve_repo(repo)
    response = api_call(
        "POST",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls/{pr_number}/reviews",
        data=payload,
        token=token,
    )
    if not isinstance(response, dict):
        raise GitHubAPIError("create pull request review response is not an object")
    return response


def list_pull_request_review_comments(
    pr_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """PR の行単位 review comment 一覧を取得する（FR-GUI-46）。"""
    pr_number = _require_positive_number(pr_number, "pr_number")
    resolved_repo = _resolve_repo(repo)
    page_size = _resolve_page_size(per_page)
    expected_path = f"/repos/{resolved_repo}/pulls/{pr_number}/comments"
    return _list_all_paginated_objects(
        f"{_GITHUB_API_BASE}{expected_path}?per_page={page_size}",
        expected_path=expected_path,
        token=token,
        response_name="pull request review comments",
    )


def create_pull_request_review_comment(
    pr_number: int,
    body: str,
    commit_id: str,
    path: str,
    line: int,
    side: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """取得済み patch の選択行へ review comment を投稿する（FR-GUI-46）。"""
    pr_number = _require_positive_number(pr_number, "pr_number")
    for field, value in (("body", body), ("commit_id", commit_id), ("path", path)):
        if not isinstance(value, str) or not value.strip():
            raise GitHubAPIError(f"{field} must be a non-empty string")
    if isinstance(line, bool) or not isinstance(line, int) or line <= 0:
        raise GitHubAPIError("line must be a positive integer")
    if side not in _PULL_REQUEST_REVIEW_COMMENT_SIDES:
        raise GitHubAPIError(
            f"side must be one of {list(_PULL_REQUEST_REVIEW_COMMENT_SIDES)}"
        )

    resolved_repo = _resolve_repo(repo)
    response = api_call(
        "POST",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls/{pr_number}/comments",
        data={
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "side": side,
        },
        token=token,
    )
    if not isinstance(response, dict):
        raise GitHubAPIError("create pull request review comment response is not an object")
    return response


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
    if "patch" in entry:
        patch = entry.get("patch")
        if not isinstance(patch, str):
            raise GitHubAPIError(
                f"invalid pull request file entry at index {index}: patch is not a string"
            )
        result["patch"] = patch
    return result


def list_pull_request_files(
    pr_number: int,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> list[dict]:
    """PR の変更ファイルを全ページ取得し、最小フィールドだけを返す。

    GitHub REST API の当該 endpoint は最大 3,000 files である。PR metadata の
    ``changed_files`` と取得件数を照合し、上限超過・途中空ページ・非 list・件数
    不一致を部分結果へ縮退せず例外にする。FR-GUI-46 用の ``patch`` と、取得基準
    になった metadata の ``head.sha`` を戻り値に保持する。
    """

    resolved_repo = _resolve_repo(repo)
    metadata = get_pull_request(pr_number, repo=resolved_repo, token=token)
    head = metadata.get("head")
    head_sha_value = head.get("sha") if isinstance(head, dict) else None
    head_sha = (
        head_sha_value.strip()
        if isinstance(head_sha_value, str)
        else ""
    )
    expected = metadata.get("changed_files")
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise GitHubAPIError("pull request metadata changed_files is invalid")
    if expected > _PULL_REQUEST_FILES_MAX:
        raise GitHubAPIError(
            "pull request has more than the GitHub API limit of 3,000 changed files"
        )
    if expected == 0:
        return _PullRequestFiles([], head_sha=head_sha)

    expected_path = f"/repos/{resolved_repo}/pulls/{pr_number}/files"
    current_url: Optional[str] = (
        f"{_GITHUB_API_BASE}{expected_path}"
        f"?per_page={_PULL_REQUEST_FILES_PAGE_SIZE}"
    )
    result: list[dict] = []
    seen: set[str] = set()
    page = 1
    while current_url is not None:
        normalized = _require_pagination_url(current_url, expected_path)
        if normalized in seen:
            raise GitHubAPIError("pagination cursor cycle detected")
        seen.add(normalized)
        response, current_url = _request_paginated_page(
            normalized,
            expected_path=expected_path,
            token=token,
        )
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
    return _PullRequestFiles(result, head_sha=head_sha)


def merge_pull_request(
    pr_number: int,
    merge_method: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    sha: Optional[str] = None,
) -> dict:
    """同期 endpoint で Pull Request をマージする（FR-GUI-47）。"""
    pr_number = _require_positive_number(pr_number, "pr_number")
    if merge_method not in _PULL_REQUEST_MERGE_METHODS:
        raise GitHubAPIError(
            f"invalid merge_method {merge_method!r}. expected one of "
            f"{list(_PULL_REQUEST_MERGE_METHODS)}"
        )

    payload: dict[str, Any] = {"merge_method": merge_method}
    if sha is not None:
        if not isinstance(sha, str) or not sha.strip():
            raise GitHubAPIError("sha must be a non-empty string when provided")
        payload["sha"] = sha.strip()

    resolved_repo = _resolve_repo(repo)
    response = api_call(
        "PUT",
        f"{_GITHUB_API_BASE}/repos/{resolved_repo}/pulls/{pr_number}/merge",
        data=payload,
        token=token,
    )
    if not isinstance(response, dict):
        raise GitHubAPIError("merge pull request response is not an object")
    if response.get("merged") is not True:
        message = response.get("message")
        detail = f": {message}" if isinstance(message, str) and message else ""
        raise GitHubAPIError(f"merge response did not confirm success{detail}")
    return response


def list_check_runs_for_ref(
    ref: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """commit ref に紐づく check-run を全ページ取得する（FR-GUI-47）。"""
    if not isinstance(ref, str) or not ref.strip():
        raise GitHubAPIError("check-runs ref must be a non-empty string")
    resolved_repo = _resolve_repo(repo)
    page_size = _resolve_page_size(per_page)
    encoded_ref = urllib.parse.quote(ref.strip(), safe="/")
    expected_path = (
        f"/repos/{resolved_repo}/commits/{encoded_ref}/check-runs"
    )
    current_url: Optional[str] = (
        f"{_GITHUB_API_BASE}{expected_path}?per_page={page_size}"
    )
    result: list[dict] = []
    expected: Optional[int] = None
    seen: set[str] = set()

    while current_url is not None:
        normalized = _require_pagination_url(current_url, expected_path)
        if normalized in seen:
            raise GitHubAPIError("pagination cursor cycle detected")
        seen.add(normalized)
        response, current_url = _request_paginated_page(
            normalized,
            expected_path=expected_path,
            token=token,
        )
        if not isinstance(response, dict):
            raise GitHubAPIError("check-runs response is not an object")

        total_count = response.get("total_count")
        runs = response.get("check_runs")
        if (
            isinstance(total_count, bool)
            or not isinstance(total_count, int)
            or total_count < 0
            or not isinstance(runs, list)
            or any(not isinstance(run, dict) for run in runs)
        ):
            raise GitHubAPIError("check-runs response has an invalid schema")
        if expected is None:
            expected = total_count
        elif total_count != expected:
            raise GitHubAPIError(
                f"check-runs response count changed from {expected} to {total_count}"
            )
        if not runs and len(result) < expected:
            raise GitHubAPIError(
                f"check-runs expected {expected} but retrieved {len(result)}"
            )

        result.extend(cast(list[dict], runs))
        if len(result) > expected:
            raise GitHubAPIError(
                f"check-runs expected {expected} but retrieved {len(result)}"
            )

    if expected is None or len(result) != expected:
        raise GitHubAPIError(
            f"check-runs expected {expected} but retrieved {len(result)}"
        )
    return result


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


def _require_branch_name(branch: str) -> str:
    """ブランチ名を git の ref 命名規則に照らして検証する。

    URL パスへ直接埋め込む値のため、API へ渡す前に境界で検証する。
    """
    name = (branch or "").strip()
    if not name:
        raise GitHubAPIError("branch name is empty")
    if not is_valid_branch_name(name):
        raise GitHubAPIError(f"invalid branch name: {branch!r}")
    return name


def delete_branch_ref(
    branch: str,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> None:
    """リモートのブランチ ref を削除する（FR-GUI-34）。

    Args:
        branch: 削除するブランチ名（``refs/heads/`` を含まない形式）。
        repo: "owner/repo" 形式。省略時は REPO 環境変数を使用。
        token: GitHub トークン。省略時は GH_TOKEN / GITHUB_TOKEN を使用。

    Raises:
        GitHubAPIError: ブランチ名が不正、認証失敗、ref 不在（404）等。
    """
    name = _require_branch_name(branch)
    resolved_repo = _resolve_repo(repo)
    quoted = urllib.parse.quote(name, safe="/")
    url = f"{_GITHUB_API_BASE}/repos/{resolved_repo}/git/refs/heads/{quoted}"
    api_call("DELETE", url, token=token)
