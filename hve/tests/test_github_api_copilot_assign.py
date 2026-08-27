"""FR-GUI-49 / FR-CLI-89: Copilot cloud agent assignment REST contracts."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

import hve.github_api as github_api
from hve.github_api import GitHubAPIError


class TestCopilotAssignmentResponseContract:
    @pytest.mark.parametrize(
        "response",
        [
            None,
            [],
            {},
            {"number": True, "assignees": [{"login": "copilot-swe-agent[bot]"}]},
            {"number": 8, "assignees": [{"login": "copilot-swe-agent[bot]"}]},
            {"number": 7},
            {"number": 7, "assignees": []},
            {"number": 7, "assignees": [{"login": "octocat"}]},
            {"number": 7, "assignees": ["copilot-swe-agent[bot]"]},
        ],
    )
    def test_shared_validator_rejects_invalid_response_contract(
        self, response
    ) -> None:
        contract = importlib.import_module(
            "hve.github_copilot_assignment_contract"
        )

        with pytest.raises(contract.CopilotAssignmentContractError):
            contract.validate_copilot_assignment_response(response, 7)

    def test_shared_validator_returns_the_validated_response(self) -> None:
        contract = importlib.import_module(
            "hve.github_copilot_assignment_contract"
        )
        response = {
            "number": 7,
            "assignees": [{"login": "copilot-swe-agent[bot]"}],
        }

        assert contract.validate_copilot_assignment_response(response, 7) is response

    def test_shared_validator_rejects_boolean_requested_issue_number(self) -> None:
        contract = importlib.import_module(
            "hve.github_copilot_assignment_contract"
        )
        response = {
            "number": 1,
            "assignees": [{"login": "copilot-swe-agent[bot]"}],
        }

        with pytest.raises(contract.CopilotAssignmentContractError):
            contract.validate_copilot_assignment_response(response, True)

    def test_github_api_imports_the_shared_validator(self) -> None:
        contract = importlib.import_module(
            "hve.github_copilot_assignment_contract"
        )

        assert (
            getattr(github_api, "validate_copilot_assignment_response")
            is contract.validate_copilot_assignment_response
        )


class TestAssignCopilotAgent:
    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_posts_agent_assignment_with_base_branch(self, api_call, sleep) -> None:
        api_call.return_value = {
            "number": 7,
            "assignees": [{"login": "copilot-swe-agent[bot]"}],
        }

        result = github_api.assign_copilot_agent(
            7,
            repo="o/r",
            token="token",
            base_branch="main",
        )

        assert result["number"] == 7
        api_call.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/issues/7/assignees",
            data={
                "assignees": ["copilot-swe-agent[bot]"],
                "agent_assignment": {
                    "target_repo": "o/r",
                    "base_branch": "main",
                },
            },
            token="token",
        )
        sleep.assert_called_once_with(1)

    @pytest.mark.parametrize("base_branch", [None, "", "   "])
    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_omits_empty_base_branch(
        self, api_call, sleep, base_branch
    ) -> None:
        api_call.return_value = {
            "number": 7,
            "assignees": [{"login": "copilot-swe-agent[bot]"}],
        }

        github_api.assign_copilot_agent(
            7,
            repo="o/r",
            token="token",
            base_branch=base_branch,
        )

        assert api_call.call_args.kwargs["data"] == {
            "assignees": ["copilot-swe-agent[bot]"],
            "agent_assignment": {"target_repo": "o/r"},
        }
        sleep.assert_called_once_with(1)

    @pytest.mark.parametrize(
        "base_branch",
        [
            123,
            True,
            "bad branch",
            "../main",
            "-leading",
            "topic/.hidden",
            "release.lock/next",
        ],
    )
    @patch("hve.github_api.api_call")
    def test_invalid_base_branch_fails_before_api(
        self, api_call, base_branch
    ) -> None:
        with pytest.raises(GitHubAPIError, match="base_branch"):
            github_api.assign_copilot_agent(
                7,
                repo="o/r",
                token="token",
                base_branch=base_branch,
            )
        api_call.assert_not_called()

    def test_waits_after_mutating_request(self, monkeypatch) -> None:
        events: list[str] = []

        def _api_call(*_args, **_kwargs):
            events.append("api_call")
            return {
                "number": 7,
                "assignees": [{"login": "copilot-swe-agent[bot]"}],
            }

        monkeypatch.setattr(github_api, "api_call", _api_call)
        monkeypatch.setattr(
            github_api.time,
            "sleep",
            lambda seconds: events.append(f"sleep:{seconds}"),
        )

        github_api.assign_copilot_agent(7, repo="o/r", token="token")

        assert events == ["api_call", "sleep:1"]

    @pytest.mark.parametrize(
        "response",
        [
            [],
            {},
            {
                "number": 8,
                "assignees": [{"login": "copilot-swe-agent[bot]"}],
            },
            {"number": 7, "assignees": []},
            {"number": 7, "assignees": [{"login": "octocat"}]},
            {"number": 7, "assignees": ["copilot-swe-agent[bot]"]},
        ],
    )
    @patch("hve.github_api.time.sleep")
    @patch("hve.github_api.api_call")
    def test_unconfirmed_assignment_fails_closed(
        self, api_call, sleep, response
    ) -> None:
        api_call.return_value = response

        with pytest.raises(GitHubAPIError, match="did not confirm"):
            github_api.assign_copilot_agent(
                7,
                repo="o/r",
                token="token",
                base_branch="main",
            )
        sleep.assert_called_once_with(1)
