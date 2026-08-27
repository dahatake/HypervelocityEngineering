"""FR-GUI-44: GUI service boundary for existing Issue metadata edits."""

from __future__ import annotations

from typing import Any

import pytest

from hve.github_api import GitHubAPIError
from hve.gui import github_service


def test_update_issue_delegates_explicit_metadata(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _update(
        number,
        repo=None,
        token=None,
        title=None,
        body=None,
        state=None,
        labels=None,
        assignees=None,
        milestone=None,
    ):
        captured.update(
            number=number,
            repo=repo,
            title=title,
            body=body,
            state=state,
            labels=labels,
            assignees=assignees,
            milestone=milestone,
        )
        return {"number": number}

    monkeypatch.setattr(github_service.github_api, "update_issue", _update)

    result = github_service.update_issue(
        "o/r",
        "7",
        labels=[],
        assignees=[],
        milestone=0,
    )

    assert result == {"number": 7}
    assert captured == {
        "number": 7,
        "repo": "o/r",
        "title": None,
        "body": None,
        "state": None,
        "labels": [],
        "assignees": [],
        "milestone": 0,
    }


def test_update_issue_omits_unspecified_metadata(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _update(number, **kwargs):
        captured.update(kwargs)
        return {"number": number}

    monkeypatch.setattr(github_service.github_api, "update_issue", _update)

    github_service.update_issue("o/r", 7, body="new body")

    assert captured == {
        "repo": "o/r",
        "title": None,
        "body": "new body",
        "state": None,
        "labels": None,
        "assignees": None,
        "milestone": None,
    }


def test_update_issue_normalizes_numeric_milestone_string_at_gui_boundary(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def _update(number, **kwargs):
        captured.update(kwargs)
        return {"number": number}

    monkeypatch.setattr(github_service.github_api, "update_issue", _update)

    github_service.update_issue("o/r", 7, milestone="3")

    assert captured["milestone"] == 3


@pytest.mark.parametrize("milestone", [-1, True, "not-a-number"])
def test_update_issue_rejects_invalid_milestone(monkeypatch, milestone) -> None:
    monkeypatch.setattr(
        github_service.github_api,
        "update_issue",
        lambda *_a, **_kw: pytest.fail("must not call API"),
    )

    with pytest.raises(github_service.GitHubServiceError, match="マイルストーン"):
        github_service.update_issue("o/r", 7, milestone=milestone)


def test_update_issue_translates_api_error(monkeypatch) -> None:
    def _boom(*_a, **_kw):
        raise GitHubAPIError("forbidden", 403)

    monkeypatch.setattr(github_service.github_api, "update_issue", _boom)

    with pytest.raises(github_service.GitHubServiceError, match="権限"):
        github_service.update_issue("o/r", 7, labels=["bug"])
