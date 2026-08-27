"""FR-GUI-45: GUI service contracts for Pull Request reviews."""

from __future__ import annotations

from typing import Any

import pytest

from hve.github_api import GitHubAPIError
from hve.gui import github_service


def test_list_reviews_delegates_and_validates_number(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _list(pr_number, repo=None, token=None, per_page=100):
        captured.update(pr_number=pr_number, repo=repo, per_page=per_page)
        return [{"id": 1}]

    monkeypatch.setattr(github_service.github_api, "list_pull_request_reviews", _list)

    assert github_service.list_pull_request_reviews("o/r", "7") == [{"id": 1}]
    assert captured == {"pr_number": 7, "repo": "o/r", "per_page": 100}


def test_create_review_delegates_without_reformatting_body(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    body = "\n## Review\n\nKeep markdown.\n"

    def _create(pr_number, event, received_body=None, repo=None, token=None):
        captured.update(
            pr_number=pr_number,
            event=event,
            body=received_body,
            repo=repo,
        )
        return {"id": 9}

    monkeypatch.setattr(github_service.github_api, "create_pull_request_review", _create)

    assert github_service.create_pull_request_review(
        "o/r", 7, "COMMENT", body
    ) == {"id": 9}
    assert captured == {
        "pr_number": 7,
        "event": "COMMENT",
        "body": body,
        "repo": "o/r",
    }


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (0, "review body is required", "review body is required"),
        (401, "bad token", "認証"),
        (403, "forbidden", "権限"),
        (422, "invalid review event", "送信内容"),
    ],
)
def test_api_error_is_translated(
    monkeypatch, status: int, message: str, expected: str
) -> None:
    def _boom(*_args, **_kwargs):
        raise GitHubAPIError(message, status)

    monkeypatch.setattr(github_service.github_api, "create_pull_request_review", _boom)

    with pytest.raises(github_service.GitHubServiceError, match=expected):
        github_service.create_pull_request_review("o/r", 7, "COMMENT", "")
