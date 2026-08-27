"""FR-GUI-46: GUI service contracts for PR review comments."""

from __future__ import annotations

from typing import Any

import pytest

from hve.github_api import GitHubAPIError
from hve.gui import github_service


def test_list_review_comments_delegates(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _list(pr_number, repo=None, token=None, per_page=100):
        captured.update(pr_number=pr_number, repo=repo, per_page=per_page)
        return [{"id": 1}]

    monkeypatch.setattr(
        github_service.github_api, "list_pull_request_review_comments", _list
    )

    assert github_service.list_pull_request_review_comments("o/r", "7") == [
        {"id": 1}
    ]
    assert captured == {"pr_number": 7, "repo": "o/r", "per_page": 100}


def test_create_review_comment_delegates_exact_selection(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _create(
        pr_number,
        body,
        commit_id,
        path,
        line,
        side,
        repo=None,
        token=None,
    ):
        captured.update(
            pr_number=pr_number,
            body=body,
            commit_id=commit_id,
            path=path,
            line=line,
            side=side,
            repo=repo,
        )
        return {"id": 9}

    monkeypatch.setattr(
        github_service.github_api, "create_pull_request_review_comment", _create
    )

    result = github_service.create_pull_request_review_comment(
        "o/r", "7", "body", "abc123", "src/app.py", 12, "RIGHT"
    )

    assert result == {"id": 9}
    assert captured == {
        "pr_number": 7,
        "body": "body",
        "commit_id": "abc123",
        "path": "src/app.py",
        "line": 12,
        "side": "RIGHT",
        "repo": "o/r",
    }


def test_api_validation_error_is_translated(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise GitHubAPIError("side must be LEFT or RIGHT", 0)

    monkeypatch.setattr(
        github_service.github_api, "create_pull_request_review_comment", _boom
    )

    with pytest.raises(github_service.GitHubServiceError, match="side must"):
        github_service.create_pull_request_review_comment(
            "o/r", 7, "body", "abc123", "src/app.py", 12, "BOTH"
        )
