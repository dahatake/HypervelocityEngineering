"""FR-GUI-49: GUI service contract for Copilot cloud agent assignment."""

from __future__ import annotations

from typing import Any

import pytest

from hve.github_api import GitHubAPIError
from hve.gui import github_service


def test_assign_copilot_agent_delegates_validated_values(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _assign(issue_num, repo=None, token=None, base_branch=None):
        captured.update(
            issue_num=issue_num,
            repo=repo,
            base_branch=base_branch,
        )
        return {
            "number": issue_num,
            "assignees": [{"login": "copilot-swe-agent[bot]"}],
        }

    monkeypatch.setattr(github_service.github_api, "assign_copilot_agent", _assign)

    result = github_service.assign_copilot_agent("o/r", "7", " main ")

    assert result["number"] == 7
    assert captured == {
        "issue_num": 7,
        "repo": "o/r",
        "base_branch": "main",
    }


def test_assign_copilot_agent_allows_unspecified_base(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _assign(issue_num, repo=None, token=None, base_branch=None):
        captured.update(issue_num=issue_num, repo=repo, base_branch=base_branch)
        return {"number": issue_num}

    monkeypatch.setattr(github_service.github_api, "assign_copilot_agent", _assign)

    github_service.assign_copilot_agent("o/r", 7)

    assert captured["base_branch"] is None


@pytest.mark.parametrize("number", [0, "bad", None])
def test_assign_copilot_agent_rejects_invalid_number(monkeypatch, number) -> None:
    called: list[object] = []
    monkeypatch.setattr(
        github_service.github_api,
        "assign_copilot_agent",
        lambda *_args, **_kwargs: called.append(True),
    )

    with pytest.raises(github_service.GitHubServiceError):
        github_service.assign_copilot_agent("o/r", number)
    assert called == []


def test_assign_copilot_agent_translates_api_error(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise GitHubAPIError("assignment did not confirm Copilot", 422)

    monkeypatch.setattr(github_service.github_api, "assign_copilot_agent", _boom)

    with pytest.raises(github_service.GitHubServiceError, match="送信内容"):
        github_service.assign_copilot_agent("o/r", 7, "main")
