"""hve.gui.tests.test_github_service

FR-GUI-26 / FR-GUI-27 / FR-GUI-28: GUI 向け GitHub サービス層の単体テスト。

HTTP は `hve.github_api` の関数を mock して検証する（実 API を呼ばない）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest

from hve.github_api import GitHubAPIError
from hve.gui import github_service


@pytest.fixture(autouse=True)
def _clear_repo_env():
    saved = os.environ.get("REPO")
    os.environ.pop("REPO", None)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("REPO", None)
        else:
            os.environ["REPO"] = saved


class TestResolveRepo:
    def test_explicit_wins(self) -> None:
        os.environ["REPO"] = "env/repo"
        assert github_service.resolve_repo("owner/explicit") == "owner/explicit"

    def test_env_fallback(self) -> None:
        os.environ["REPO"] = "env/repo"
        assert github_service.resolve_repo(None) == "env/repo"

    def test_git_remote_fallback(self, monkeypatch) -> None:
        monkeypatch.setattr(github_service, "_guess_repo", lambda: "guessed/repo")
        assert github_service.resolve_repo("  ") == "guessed/repo"

    def test_raises_when_unresolvable(self, monkeypatch) -> None:
        monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
        with pytest.raises(github_service.GitHubServiceError):
            github_service.resolve_repo(None)

    def test_rejects_malformed_repo(self, monkeypatch) -> None:
        with pytest.raises(github_service.GitHubServiceError):
            github_service.resolve_repo("not-a-repo")

    def test_rejects_path_traversal_repo(self) -> None:
        with pytest.raises(github_service.GitHubServiceError):
            github_service.resolve_repo("owner/repo/../../user")

    def test_rejects_malformed_env_repo(self, monkeypatch) -> None:
        """環境変数の設定ミスを git remote へ黙ってフォールバックさせないこと。"""
        os.environ["REPO"] = "broken repo"
        monkeypatch.setattr(github_service, "_guess_repo", lambda: "guessed/repo")
        with pytest.raises(github_service.GitHubServiceError):
            github_service.resolve_repo(None)


class TestNumberValidation:
    def test_accepts_int_and_numeric_string(self) -> None:
        assert github_service.parse_number("42") == 42
        assert github_service.parse_number(42) == 42

    @pytest.mark.parametrize("raw", ["", "  ", "abc", "1/2", "-3", "0", None])
    def test_rejects_invalid(self, raw) -> None:
        with pytest.raises(github_service.GitHubServiceError):
            github_service.parse_number(raw)


class TestErrorTranslation:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, "認証"),
            (403, "権限"),
            (404, "見つかりません"),
            (422, "内容"),
            (0, "GitHub API"),
        ],
    )
    def test_api_error_becomes_service_error(self, status, expected, monkeypatch) -> None:
        def _boom(*_a, **_kw):
            raise GitHubAPIError("boom", status)

        monkeypatch.setattr(github_service.github_api, "list_issues", _boom)
        with pytest.raises(github_service.GitHubServiceError) as excinfo:
            github_service.list_issues("o/r")
        assert expected in str(excinfo.value)

    def test_original_message_is_preserved(self, monkeypatch) -> None:
        def _boom(*_a, **_kw):
            raise GitHubAPIError("original detail", 404)

        monkeypatch.setattr(github_service.github_api, "get_issue", _boom)
        with pytest.raises(github_service.GitHubServiceError) as excinfo:
            github_service.get_issue("o/r", 1)
        assert "original detail" in str(excinfo.value)


class TestIssueService:
    def test_list_issues_delegates(self, monkeypatch) -> None:
        seen: Dict[str, Any] = {}

        def _list(repo=None, token=None, state="open", per_page=50):
            seen.update(repo=repo, state=state, per_page=per_page)
            return [{"number": 1}]

        monkeypatch.setattr(github_service.github_api, "list_issues", _list)
        assert github_service.list_issues("o/r", state="all", per_page=20) == [
            {"number": 1}
        ]
        assert seen == {"repo": "o/r", "state": "all", "per_page": 20}

    def test_get_issue_validates_number(self, monkeypatch) -> None:
        monkeypatch.setattr(
            github_service.github_api, "get_issue", lambda *_a, **_kw: {"number": 5}
        )
        assert github_service.get_issue("o/r", "5") == {"number": 5}
        with pytest.raises(github_service.GitHubServiceError):
            github_service.get_issue("o/r", "5x")

    def test_update_issue_passes_only_given_fields(self, monkeypatch) -> None:
        seen: Dict[str, Any] = {}

        def _update(number, repo=None, token=None, title=None, body=None, state=None):
            seen.update(number=number, repo=repo, title=title, body=body, state=state)
            return {"number": number}

        monkeypatch.setattr(github_service.github_api, "update_issue", _update)
        github_service.update_issue("o/r", 7, body="new body")
        assert seen == {
            "number": 7,
            "repo": "o/r",
            "title": None,
            "body": "new body",
            "state": None,
        }

    def test_post_comment_rejects_blank_body(self, monkeypatch) -> None:
        monkeypatch.setattr(
            github_service.github_api,
            "post_comment",
            lambda *_a, **_kw: pytest.fail("must not call API for blank body"),
        )
        with pytest.raises(github_service.GitHubServiceError):
            github_service.post_comment("o/r", 1, "   ")

    def test_post_comment_delegates(self, monkeypatch) -> None:
        seen: Dict[str, Any] = {}

        def _post(issue_num, body, repo=None, token=None):
            seen.update(issue_num=issue_num, body=body, repo=repo)
            return True

        monkeypatch.setattr(github_service.github_api, "post_comment", _post)
        github_service.post_comment("o/r", 1, "hello")
        assert seen == {"issue_num": 1, "body": "hello", "repo": "o/r"}

    def test_update_comment_rejects_blank_body(self, monkeypatch) -> None:
        monkeypatch.setattr(
            github_service.github_api,
            "update_comment",
            lambda *_a, **_kw: pytest.fail("must not call API for blank body"),
        )
        with pytest.raises(github_service.GitHubServiceError):
            github_service.update_comment("o/r", 9, "")

    def test_current_user_login(self, monkeypatch) -> None:
        monkeypatch.setattr(
            github_service.github_api,
            "get_authenticated_user",
            lambda token=None: {"login": "octocat"},
        )
        assert github_service.current_user_login() == "octocat"

    def test_current_user_login_missing_returns_empty(self, monkeypatch) -> None:
        monkeypatch.setattr(
            github_service.github_api, "get_authenticated_user", lambda token=None: {}
        )
        assert github_service.current_user_login() == ""


class TestPullRequestService:
    def test_list_pull_requests_delegates(self, monkeypatch) -> None:
        seen: Dict[str, Any] = {}

        def _list(repo=None, token=None, state="open", per_page=50):
            seen.update(repo=repo, state=state, per_page=per_page)
            return [{"number": 3}]

        monkeypatch.setattr(github_service.github_api, "list_pull_requests", _list)
        assert github_service.list_pull_requests("o/r", state="closed") == [
            {"number": 3}
        ]
        assert seen["state"] == "closed"

    def test_get_pull_request_validates_number(self, monkeypatch) -> None:
        monkeypatch.setattr(
            github_service.github_api,
            "get_pull_request",
            lambda *_a, **_kw: {"number": 3},
        )
        with pytest.raises(github_service.GitHubServiceError):
            github_service.get_pull_request("o/r", "abc")

    def test_list_pull_request_files_delegates(self, monkeypatch) -> None:
        captured: List[Any] = []

        def _files(pr_number, repo=None, token=None):
            captured.append((pr_number, repo))
            return [{"filename": "a.py", "status": "modified"}]

        monkeypatch.setattr(
            github_service.github_api, "list_pull_request_files", _files
        )
        assert github_service.list_pull_request_files("o/r", 3) == [
            {"filename": "a.py", "status": "modified"}
        ]
        assert captured == [(3, "o/r")]


class TestDelegationSignatures:
    """mock では検出できない引数名 / 順の不一致を実シグネチャで固定する。"""

    @pytest.mark.parametrize(
        ("name", "expected_head"),
        [
            ("list_issues", ["repo", "token", "state", "per_page"]),
            ("get_issue", ["issue_num", "repo", "token"]),
            ("update_issue", ["issue_num", "repo", "token", "title", "body", "state"]),
            ("list_issue_comments", ["issue_num", "repo", "token", "per_page"]),
            ("post_comment", ["issue_num", "body", "repo", "token"]),
            ("update_comment", ["comment_id", "body", "repo", "token"]),
            ("list_pull_requests", ["repo", "token", "state", "per_page"]),
            ("get_pull_request", ["pr_number", "repo", "token"]),
            ("list_pull_request_files", ["pr_number", "repo", "token"]),
            ("get_authenticated_user", ["token"]),
        ],
    )
    def test_github_api_signature(self, name, expected_head) -> None:
        import inspect

        params = list(inspect.signature(getattr(github_service.github_api, name)).parameters)
        assert params == expected_head
