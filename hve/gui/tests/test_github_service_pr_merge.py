"""FR-GUI-47: GUI service contracts for check-runs and PR merge."""

from __future__ import annotations

from typing import Any

import pytest

from hve.github_api import GitHubAPIError
from hve.gui import github_service


def test_list_check_runs_delegates_head_sha(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _list(ref, repo=None, token=None, per_page=100):
        captured.update(ref=ref, repo=repo, per_page=per_page)
        return [{"name": "build", "status": "completed", "conclusion": "success"}]

    monkeypatch.setattr(github_service.github_api, "list_check_runs_for_ref", _list)

    result = github_service.list_check_runs("o/r", " head123 ")

    assert result == [
        {"name": "build", "status": "completed", "conclusion": "success"}
    ]
    assert captured == {"ref": "head123", "repo": "o/r", "per_page": 100}


@pytest.mark.parametrize("ref", ["", "   ", None])
def test_list_check_runs_rejects_missing_head_sha(monkeypatch, ref) -> None:
    called: list[object] = []
    monkeypatch.setattr(
        github_service.github_api,
        "list_check_runs_for_ref",
        lambda *_args, **_kwargs: called.append(True),
    )

    with pytest.raises(github_service.GitHubServiceError, match="head SHA"):
        github_service.list_check_runs("o/r", ref)
    assert called == []


def test_list_check_runs_translates_malformed_response(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise GitHubAPIError("check-runs response is invalid", 0)

    monkeypatch.setattr(github_service.github_api, "list_check_runs_for_ref", _boom)

    with pytest.raises(github_service.GitHubServiceError, match="invalid"):
        github_service.list_check_runs("o/r", "head123")


def test_merge_delegates_number_method_and_sha(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _merge(pr_number, merge_method, repo=None, token=None, sha=None):
        captured.update(
            pr_number=pr_number,
            merge_method=merge_method,
            repo=repo,
            sha=sha,
        )
        return {"sha": "merged123", "merged": True, "message": "ok"}

    monkeypatch.setattr(github_service.github_api, "merge_pull_request", _merge)

    result = github_service.merge_pull_request(
        "o/r", "7", "squash", sha="head123"
    )

    assert result["merged"] is True
    assert captured == {
        "pr_number": 7,
        "merge_method": "squash",
        "repo": "o/r",
        "sha": "head123",
    }


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (405, "マージできません"),
        (409, "head が更新"),
    ],
)
def test_merge_error_explains_recoverable_state(
    monkeypatch, status: int, expected: str
) -> None:
    def _boom(*_args, **_kwargs):
        raise GitHubAPIError("merge rejected", status)

    monkeypatch.setattr(github_service.github_api, "merge_pull_request", _boom)

    with pytest.raises(github_service.GitHubServiceError, match=expected):
        github_service.merge_pull_request("o/r", 7, "merge", sha="head123")
