"""tests/test_github_api.py — hve.github_api のユニットテスト

HTTP 通信は unittest.mock.patch でモックに差し替え、
ロジック（リトライ・リゾルバ・エラー分岐）を検証する。
"""

from __future__ import annotations

import json
import os
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from hve.github_api import (
    GitHubAPIError,
    _parse_retry_after,
    _resolve_repo,
    _resolve_token,
    add_labels,
    api_call,
    create_issue,
    create_pull_request,
    get_authenticated_user,
    get_issue,
    get_pull_request,
    get_repository_metadata,
    link_sub_issue,
    list_check_runs_for_ref,
    list_issue_comments,
    list_issues,
    list_pull_requests,
    list_viewer_repositories,
    list_branches,
    post_comment,
    update_comment,
    update_issue,
)


# =====================================================================
# _resolve_token
# =====================================================================


class TestResolveToken:
    def test_explicit_token(self):
        assert _resolve_token("tok-123") == "tok-123"

    def test_gh_token_env(self, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "ghtoken")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert _resolve_token(None) == "ghtoken"

    def test_github_token_env(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "github-tok")
        assert _resolve_token(None) == "github-tok"

    def test_gh_token_takes_priority(self, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "first")
        monkeypatch.setenv("GITHUB_TOKEN", "second")
        assert _resolve_token(None) == "first"

    def test_missing_raises(self, monkeypatch):
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(GitHubAPIError, match="token not found"):
            _resolve_token(None)


# =====================================================================
# _resolve_repo
# =====================================================================


class TestResolveRepo:
    def test_explicit_repo(self):
        assert _resolve_repo("owner/repo") == "owner/repo"

    def test_env_repo(self, monkeypatch):
        monkeypatch.setenv("REPO", "env/repo")
        assert _resolve_repo(None) == "env/repo"

    def test_missing_raises(self, monkeypatch):
        monkeypatch.delenv("REPO", raising=False)
        with pytest.raises(GitHubAPIError, match="Repository not specified"):
            _resolve_repo(None)


# =====================================================================
# _parse_retry_after
# =====================================================================


class TestParseRetryAfter:
    def test_none(self):
        assert _parse_retry_after(None) is None

    def test_valid_int(self):
        assert _parse_retry_after("30") == 30

    def test_garbage(self):
        assert _parse_retry_after("abc") is None


# =====================================================================
# api_call — 正常系
# =====================================================================


def _mock_response(data, status=200):
    """urlopen のモック用レスポンスオブジェクトを生成する。"""
    body = json.dumps(data).encode() if data is not None else b""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestApiCallSuccess:
    @patch("hve.github_api.urllib.request.urlopen")
    def test_get_returns_json(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        mock_urlopen.return_value = _mock_response({"ok": True})
        result = api_call("GET", "https://api.github.com/test")
        assert result == {"ok": True}

    @patch("hve.github_api.urllib.request.urlopen")
    def test_post_sends_body(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        mock_urlopen.return_value = _mock_response({"id": 1})
        result = api_call(
            "POST", "https://api.github.com/test", data={"key": "val"}
        )
        assert result == {"id": 1}
        # Request body should be JSON-encoded
        req = mock_urlopen.call_args[0][0]
        assert json.loads(req.data) == {"key": "val"}

    @patch("hve.github_api.urllib.request.urlopen")
    def test_empty_body_returns_empty_dict(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        mock_urlopen.return_value = _mock_response(None)
        result = api_call("GET", "https://api.github.com/test")
        assert result == {}


# =====================================================================
# api_call — エラー系
# =====================================================================


def _make_http_error(status, body=b"", headers=None):
    """urllib.error.HTTPError を生成する。"""
    err = urllib.error.HTTPError(
        url="https://api.github.com/test",
        code=status,
        msg=f"HTTP {status}",
        hdrs=headers or {},
        fp=BytesIO(body),
    )
    return err


class TestApiCallErrors:
    @patch("hve.github_api.urllib.request.urlopen")
    def test_401_raises_immediately(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        mock_urlopen.side_effect = _make_http_error(401)
        with pytest.raises(GitHubAPIError, match="認証失敗") as exc_info:
            api_call("GET", "https://api.github.com/test", max_retries=3)
        assert exc_info.value.status == 401
        assert mock_urlopen.call_count == 1

    @patch("hve.github_api.urllib.request.urlopen")
    def test_422_raises_immediately(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        mock_urlopen.side_effect = _make_http_error(422, b'{"message":"bad"}')
        with pytest.raises(GitHubAPIError, match="処理不可能") as exc_info:
            api_call("GET", "https://api.github.com/test", max_retries=3)
        assert exc_info.value.status == 422
        assert mock_urlopen.call_count == 1

    @patch("hve.github_api.urllib.request.urlopen")
    def test_403_without_retry_after_raises(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        mock_urlopen.side_effect = _make_http_error(403)
        with pytest.raises(GitHubAPIError, match="アクセス拒否"):
            api_call("GET", "https://api.github.com/test", max_retries=3)
        assert mock_urlopen.call_count == 1

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.urllib.request.urlopen")
    def test_500_retries_then_fails(
        self, mock_urlopen, mock_sleep, monkeypatch
    ):
        monkeypatch.setenv("GH_TOKEN", "tok")
        mock_urlopen.side_effect = _make_http_error(500)
        with pytest.raises(GitHubAPIError, match="API 呼び出し失敗"):
            api_call("GET", "https://api.github.com/test", max_retries=3)
        assert mock_urlopen.call_count == 3
        # 指数バックオフ: 1s, 2s
        assert mock_sleep.call_count == 2

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.urllib.request.urlopen")
    def test_500_retry_success(
        self, mock_urlopen, mock_sleep, monkeypatch
    ):
        monkeypatch.setenv("GH_TOKEN", "tok")
        mock_urlopen.side_effect = [
            _make_http_error(500),
            _mock_response({"recovered": True}),
        ]
        result = api_call("GET", "https://api.github.com/test", max_retries=3)
        assert result == {"recovered": True}
        assert mock_urlopen.call_count == 2

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.urllib.request.urlopen")
    def test_network_error_retries(
        self, mock_urlopen, mock_sleep, monkeypatch
    ):
        monkeypatch.setenv("GH_TOKEN", "tok")
        mock_urlopen.side_effect = urllib.error.URLError("DNS fail")
        with pytest.raises(GitHubAPIError, match="network error"):
            api_call("GET", "https://api.github.com/test", max_retries=2)
        assert mock_urlopen.call_count == 2


# =====================================================================
# create_issue
# =====================================================================


class TestCreateIssue:
    @patch("hve.github_api.api_call")
    def test_returns_number_and_id(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {"number": 42, "id": 99999}
        num, db_id = create_issue("Test", "body", ["bug"])
        assert num == 42
        assert db_id == 99999
        mock_api.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/issues",
            data={"title": "Test", "body": "body", "labels": ["bug"]},
            token=None,
        )

    @patch("hve.github_api.api_call")
    def test_explicit_repo_and_token(self, mock_api):
        mock_api.return_value = {"number": 1, "id": 111}
        num, db_id = create_issue(
            "T", "B", [], repo="explicit/repo", token="tok"
        )
        assert num == 1
        url_called = mock_api.call_args[0][1]
        assert "explicit/repo" in url_called

    @patch("hve.github_api.api_call")
    def test_assignees_included_in_payload(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {"number": 10, "id": 200}
        num, db_id = create_issue("T", "B", [], assignees=["copilot"])
        assert num == 10
        mock_api.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/issues",
            data={"title": "T", "body": "B", "labels": [], "assignees": ["copilot"]},
            token=None,
        )

    @patch("hve.github_api.api_call")
    def test_assignees_none_not_in_payload(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {"number": 11, "id": 201}
        num, db_id = create_issue("T", "B", ["label"])
        payload = mock_api.call_args[1]["data"] if "data" in mock_api.call_args[1] else mock_api.call_args[0][2] if len(mock_api.call_args[0]) > 2 else None
        # assignees=None の場合、payload に assignees キーが含まれないこと
        called_data = mock_api.call_args.kwargs.get("data") or mock_api.call_args[0][2]
        assert "assignees" not in called_data

    @patch("hve.github_api.api_call")
    def test_assignees_empty_list_not_in_payload(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {"number": 12, "id": 202}
        num, db_id = create_issue("T", "B", [], assignees=[])
        called_data = mock_api.call_args.kwargs.get("data") or mock_api.call_args[0][2]
        # 空リストの場合も assignees キーが含まれないこと
        assert "assignees" not in called_data


# =====================================================================
# link_sub_issue
# =====================================================================


class TestLinkSubIssue:
    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_success(self, mock_api, mock_sleep, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {}
        result = link_sub_issue(1, 999)
        assert result is True
        mock_sleep.assert_called_once_with(1)

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_422_idempotent(self, mock_api, mock_sleep, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.side_effect = GitHubAPIError("already linked", status=422)
        result = link_sub_issue(1, 999)
        assert result is True  # 422 は既にリンク済みとみなす
        mock_sleep.assert_called_once_with(1)

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_other_error_returns_false(
        self, mock_api, mock_sleep, monkeypatch
    ):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.side_effect = GitHubAPIError("server error", status=500)
        result = link_sub_issue(1, 999)
        assert result is False
        mock_sleep.assert_called_once_with(1)


# =====================================================================
# add_labels
# =====================================================================


class TestAddLabels:
    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_success(self, mock_api, mock_sleep, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {}
        result = add_labels(42, ["akm:done"])
        assert result is True
        mock_api.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/issues/42/labels",
            data={"labels": ["akm:done"]},
            token=None,
        )
        mock_sleep.assert_called_once_with(1)

    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_failure_returns_false(self, mock_api, mock_sleep, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.side_effect = GitHubAPIError("forbidden", status=403)
        result = add_labels(42, ["akm:done"])
        assert result is False
        mock_sleep.assert_not_called()


# =====================================================================
# post_comment
# =====================================================================


class TestPostComment:
    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_success(self, mock_api, mock_sleep, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {"id": 1}
        result = post_comment(42, "hello")
        assert result is True
        mock_api.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/issues/42/comments",
            data={"body": "hello"},
            token=None,
        )
        mock_sleep.assert_called_once_with(1)


# =====================================================================
# list_issue_comments
# =====================================================================


class TestListIssueComments:
    @patch("hve.github_api.api_call")
    def test_success_filters_dict_items(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = [{"body": "a"}, "bad", {"body": "b"}]

        result = list_issue_comments(42)

        assert result == [{"body": "a"}, {"body": "b"}]
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/o/r/issues/42/comments?per_page=100",
            token=None,
        )

    @patch("hve.github_api.api_call")
    def test_non_list_response_returns_empty(self, mock_api):
        mock_api.return_value = {"message": "unexpected"}

        assert list_issue_comments(42, repo="o/r", token="tok") == []


# =====================================================================
# create_pull_request
# =====================================================================


class TestCreatePullRequest:
    @patch("hve.github_api.api_call")
    def test_returns_pr_number(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {"number": 7}
        pr_num = create_pull_request(
            title="PR title",
            body="PR body",
            head="feature",
            base="main",
        )
        assert pr_num == 7
        mock_api.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/pulls",
            data={
                "title": "PR title",
                "body": "PR body",
                "head": "feature",
                "base": "main",
            },
            token=None,
        )

    @patch("hve.github_api.api_call")
    def test_explicit_repo_token(self, mock_api):
        mock_api.return_value = {"number": 99}
        pr_num = create_pull_request(
            "T", "B", "h", "b", repo="x/y", token="tok"
        )
        assert pr_num == 99
        url_called = mock_api.call_args[0][1]
        assert "x/y" in url_called


# =====================================================================
# get_pull_request
# =====================================================================


class TestGetPullRequest:
    @patch("hve.github_api.api_call")
    def test_returns_merged_state(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {"number": 7, "merged": True, "state": "closed"}
        result = get_pull_request(7)
        assert result["merged"] is True
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/o/r/pulls/7",
            token=None,
        )

    @patch("hve.github_api.api_call")
    def test_returns_unmerged(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {"number": 7, "merged": False, "state": "open"}
        assert get_pull_request(7)["merged"] is False

    @patch("hve.github_api.api_call")
    def test_explicit_repo_and_token(self, mock_api):
        mock_api.return_value = {"number": 99, "merged": True}
        result = get_pull_request(99, repo="x/y", token="tok")
        assert result["merged"] is True
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/x/y/pulls/99",
            token="tok",
        )

    @patch("hve.github_api.api_call")
    def test_404_propagates(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.side_effect = GitHubAPIError("not found", status=404)
        with pytest.raises(GitHubAPIError, match="not found"):
            get_pull_request(7)

    @patch("hve.github_api.api_call")
    def test_non_dict_response_returns_empty(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = []
        assert get_pull_request(7) == {}


# =====================================================================
# list_check_runs_for_ref
# =====================================================================


class TestListCheckRunsForRef:
    @patch("hve.github_api.api_call")
    def test_returns_check_runs(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = {
            "total_count": 1,
            "check_runs": [
                {"name": "build", "status": "completed", "conclusion": "success"}
            ],
        }

        result = list_check_runs_for_ref("abc123")

        assert result == [{"name": "build", "status": "completed", "conclusion": "success"}]
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/o/r/commits/abc123/check-runs?per_page=100",
            token=None,
        )

    @patch("hve.github_api.api_call")
    def test_non_dict_response_returns_empty(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = []

        assert list_check_runs_for_ref("abc123") == []


# =====================================================================
# list_branches
# =====================================================================


class TestListBranches:
    @patch("hve.github_api.api_call")
    def test_returns_branch_names(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = [{"name": "main"}, {"name": "dev"}]
        result = list_branches()
        assert result == ["main", "dev"]
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/o/r/branches?per_page=100",
            token=None,
        )

    @patch("hve.github_api.api_call")
    def test_empty_list(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = []
        assert list_branches() == []

    @patch("hve.github_api.api_call")
    def test_explicit_repo_and_token(self, mock_api):
        mock_api.return_value = [{"name": "feature"}]
        result = list_branches(repo="x/y", token="tok")
        assert result == ["feature"]
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/x/y/branches?per_page=100",
            token="tok",
        )

    @patch("hve.github_api.api_call")
    def test_404_propagates(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.side_effect = GitHubAPIError("not found", status=404)
        with pytest.raises(GitHubAPIError, match="not found"):
            list_branches()

    @patch("hve.github_api.api_call")
    def test_non_list_response_returns_empty(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        # api_call は空ボディ時 {} (dict) を返す。list 以外は [] へフォールバック。
        mock_api.return_value = {}
        assert list_branches() == []

    @patch("hve.github_api.api_call")
    def test_skips_entries_without_name(self, mock_api, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "tok")
        monkeypatch.setenv("REPO", "o/r")
        mock_api.return_value = [{"name": "main"}, {"protected": True}, {"name": "dev"}]
        assert list_branches() == ["main", "dev"]


# =====================================================================
# repository metadata helpers
# =====================================================================


class TestGitHubMetadataHelpers:
    @patch("hve.github_api.api_call")
    def test_get_repository_metadata(self, mock_api):
        mock_api.return_value = {"full_name": "owner/repo", "has_issues": True}
        assert get_repository_metadata("owner/repo", token="tok") == {
            "full_name": "owner/repo",
            "has_issues": True,
        }
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/owner/repo",
            token="tok",
        )

    @patch("hve.github_api.api_call")
    def test_list_viewer_repositories(self, mock_api):
        mock_api.return_value = [{"full_name": "owner/repo"}]
        assert list_viewer_repositories(token="tok") == [{"full_name": "owner/repo"}]
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/user/repos?affiliation=owner,collaborator,organization_member&sort=updated&per_page=100",
            token="tok",
        )

    @patch("hve.github_api.api_call")
    def test_list_viewer_repositories_non_list_response_returns_empty(self, mock_api):
        mock_api.return_value = {}
        assert list_viewer_repositories(token="tok") == []

    @patch("hve.github_api.api_call")
    def test_get_authenticated_user(self, mock_api):
        mock_api.return_value = {"login": "octocat"}
        assert get_authenticated_user(token="tok") == {"login": "octocat"}
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/user",
            token="tok",
        )

    @patch("hve.github_api.api_call")
    def test_get_authenticated_user_non_object_response_returns_empty(self, mock_api):
        mock_api.return_value = []
        assert get_authenticated_user(token="tok") == {}


# =====================================================================
# FR-GUI-26: Issue の一覧 / 詳細 / 編集 / コメント編集
# =====================================================================


class TestIssueEndpoints:
    @patch("hve.github_api.api_call")
    def test_list_issues_uses_state_and_per_page(self, mock_api):
        mock_api.return_value = [{"number": 1}]
        assert list_issues(repo="o/r", token="tok", state="all", per_page=30) == [
            {"number": 1}
        ]
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/o/r/issues?state=all&sort=updated&direction=desc&per_page=30",
            token="tok",
        )

    @patch("hve.github_api.api_call")
    def test_list_issues_excludes_pull_requests(self, mock_api):
        mock_api.return_value = [
            {"number": 1},
            {"number": 2, "pull_request": {"url": "https://example.invalid/2"}},
            {"number": 3},
        ]
        assert list_issues(repo="o/r", token="tok") == [{"number": 1}, {"number": 3}]

    @patch("hve.github_api.api_call")
    def test_list_issues_non_list_response_returns_empty(self, mock_api):
        mock_api.return_value = {"message": "unexpected"}
        assert list_issues(repo="o/r", token="tok") == []

    @patch("hve.github_api.api_call")
    def test_list_issues_clamps_per_page(self, mock_api):
        mock_api.return_value = []
        list_issues(repo="o/r", token="tok", per_page=5000)
        assert "per_page=100" in mock_api.call_args.args[1]

    @patch("hve.github_api.api_call")
    def test_get_issue_returns_object(self, mock_api):
        mock_api.return_value = {"number": 42, "title": "t"}
        assert get_issue(42, repo="o/r", token="tok") == {"number": 42, "title": "t"}
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/o/r/issues/42",
            token="tok",
        )

    @patch("hve.github_api.api_call")
    def test_get_issue_rejects_non_object_response(self, mock_api):
        mock_api.return_value = []
        with pytest.raises(GitHubAPIError):
            get_issue(42, repo="o/r", token="tok")

    @patch("hve.github_api.api_call")
    def test_update_issue_sends_only_provided_fields(self, mock_api):
        mock_api.return_value = {"number": 42}
        update_issue(42, repo="o/r", token="tok", title="new title")
        mock_api.assert_called_once_with(
            "PATCH",
            "https://api.github.com/repos/o/r/issues/42",
            data={"title": "new title"},
            token="tok",
        )

    @patch("hve.github_api.api_call")
    def test_update_issue_allows_empty_body(self, mock_api):
        mock_api.return_value = {"number": 42}
        update_issue(42, repo="o/r", token="tok", body="")
        assert mock_api.call_args.kwargs["data"] == {"body": ""}

    @patch("hve.github_api.api_call")
    def test_update_issue_sends_state(self, mock_api):
        mock_api.return_value = {"number": 42}
        update_issue(42, repo="o/r", token="tok", state="closed")
        assert mock_api.call_args.kwargs["data"] == {"state": "closed"}

    @patch("hve.github_api.api_call")
    def test_update_issue_without_fields_raises(self, mock_api):
        with pytest.raises(GitHubAPIError, match="no fields"):
            update_issue(42, repo="o/r", token="tok")
        mock_api.assert_not_called()

    @patch("hve.github_api.api_call")
    def test_update_issue_rejects_unknown_state(self, mock_api):
        with pytest.raises(GitHubAPIError, match="state"):
            update_issue(42, repo="o/r", token="tok", state="merged")
        mock_api.assert_not_called()

    @patch("hve.github_api.api_call")
    def test_update_comment_patches_comment_endpoint(self, mock_api):
        mock_api.return_value = {"id": 9}
        assert update_comment(9, "edited", repo="o/r", token="tok") == {"id": 9}
        mock_api.assert_called_once_with(
            "PATCH",
            "https://api.github.com/repos/o/r/issues/comments/9",
            data={"body": "edited"},
            token="tok",
        )


# =====================================================================
# FR-GUI-27: Pull Request 一覧
# =====================================================================


class TestPullRequestEndpoints:
    @patch("hve.github_api.api_call")
    def test_list_pull_requests_uses_state_and_per_page(self, mock_api):
        mock_api.return_value = [{"number": 3}]
        assert list_pull_requests(repo="o/r", token="tok", state="closed", per_page=20) == [
            {"number": 3}
        ]
        mock_api.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/o/r/pulls?state=closed&sort=updated&direction=desc&per_page=20",
            token="tok",
        )

    @patch("hve.github_api.api_call")
    def test_list_pull_requests_filters_non_dict_entries(self, mock_api):
        mock_api.return_value = [{"number": 3}, "bad", {"number": 4}]
        assert list_pull_requests(repo="o/r", token="tok") == [
            {"number": 3},
            {"number": 4},
        ]

    @patch("hve.github_api.api_call")
    def test_list_pull_requests_non_list_response_returns_empty(self, mock_api):
        mock_api.return_value = {"message": "unexpected"}
        assert list_pull_requests(repo="o/r", token="tok") == []

    @patch("hve.github_api.api_call")
    def test_list_pull_requests_rejects_unknown_state(self, mock_api):
        with pytest.raises(GitHubAPIError, match="state"):
            list_pull_requests(repo="o/r", token="tok", state="draft")
        mock_api.assert_not_called()
