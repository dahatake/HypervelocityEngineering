"""FR-GUI-41: GUI service boundary for Issue metadata."""

from __future__ import annotations

import pytest

from hve.github_api import GitHubAPIError
from hve.gui import github_service


def test_create_issue_details_allows_blank_body_and_delegates_metadata(monkeypatch) -> None:
    captured = {}

    def _create(
        title,
        body,
        labels,
        repo=None,
        token=None,
        assignees=None,
        milestone=None,
        max_retries=5,
    ):
        captured.update(
            title=title,
            body=body,
            labels=labels,
            repo=repo,
            assignees=assignees,
            milestone=milestone,
            max_retries=max_retries,
        )
        return {
            "number": 7,
            "id": 70,
            "labels": [{"name": "bug"}],
            "assignees": [{"login": "me"}],
            "milestone": {"number": 2},
        }

    monkeypatch.setattr(github_service.github_api, "create_issue_details", _create)
    result = github_service.create_issue_details(
        "o/r",
        "Title",
        "",
        labels=["bug"],
        assignees=["me"],
        milestone=2,
    )
    assert captured == {
        "title": "Title",
        "body": "",
        "labels": ["bug"],
        "repo": "o/r",
        "assignees": ["me"],
        "milestone": 2,
        "max_retries": 1,
    }
    assert result["number"] == 7
    assert result["warnings"] == []


def test_create_issue_details_reports_silently_dropped_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        github_service.github_api,
        "create_issue_details",
        lambda *_a, **_kw: {"number": 7, "id": 70, "labels": [], "assignees": []},
    )
    result = github_service.create_issue_details(
        "o/r", "Title", "Body", labels=["bug"], assignees=["me"], milestone=2
    )
    assert result["number"] == 7
    assert result["warnings"]
    assert {warning["kind"] for warning in result["warnings"]} == {
        "label",
        "assignee",
        "milestone",
    }


def test_create_issue_details_requires_title(monkeypatch) -> None:
    monkeypatch.setattr(
        github_service.github_api,
        "create_issue_details",
        lambda *_a, **_kw: pytest.fail("must not call API"),
    )
    with pytest.raises(github_service.GitHubServiceError, match="タイトル"):
        github_service.create_issue_details("o/r", " ", "")


def test_candidate_list_errors_are_translated(monkeypatch) -> None:
    monkeypatch.setattr(
        github_service.github_api,
        "list_labels",
        lambda *_a, **_kw: (_ for _ in ()).throw(GitHubAPIError("forbidden", 403)),
    )
    with pytest.raises(github_service.GitHubServiceError, match="権限"):
        github_service.list_labels("o/r")


def test_candidate_list_delegation(monkeypatch) -> None:
    monkeypatch.setattr(
        github_service.github_api,
        "list_labels",
        lambda repo=None, token=None, per_page=100: [{"name": "bug"}],
    )
    monkeypatch.setattr(
        github_service.github_api,
        "list_assignees",
        lambda repo=None, token=None, per_page=100: [{"login": "me"}],
    )
    monkeypatch.setattr(
        github_service.github_api,
        "list_milestones",
        lambda repo=None, token=None, per_page=100: [{"number": 2, "title": "v1"}],
    )
    assert github_service.list_labels("o/r") == [{"name": "bug"}]
    assert github_service.list_assignees("o/r") == [{"login": "me"}]
    assert github_service.list_milestones("o/r") == [{"number": 2, "title": "v1"}]
