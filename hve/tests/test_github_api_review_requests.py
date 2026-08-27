"""FR-GUI-43: Pull Request metadata and reviewer REST contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hve.github_api import (
    GitHubAPIError,
    request_pull_request_reviewers,
    update_pull_request_metadata,
)


@patch("hve.github_api.api_call")
def test_update_pull_request_metadata_uses_issues_endpoint(api_call) -> None:
    api_call.return_value = {"number": 7, "labels": [{"name": "bug"}]}
    result = update_pull_request_metadata(
        7,
        repo="o/r",
        token="t",
        labels=["bug"],
        assignees=["alice"],
        milestone=2,
    )
    assert result["number"] == 7
    api_call.assert_called_once_with(
        "PATCH",
        "https://api.github.com/repos/o/r/issues/7",
        data={"labels": ["bug"], "assignees": ["alice"], "milestone": 2},
        token="t",
    )


@patch("hve.github_api.api_call")
def test_reviewer_users_and_teams_use_distinct_fields(api_call) -> None:
    api_call.return_value = {
        "requested_reviewers": [{"login": "alice"}],
        "requested_teams": [{"slug": "platform"}],
    }
    request_pull_request_reviewers(
        7,
        repo="o/r",
        token="t",
        reviewers=["alice"],
        team_reviewers=["platform"],
    )
    api_call.assert_called_once_with(
        "POST",
        "https://api.github.com/repos/o/r/pulls/7/requested_reviewers",
        data={"reviewers": ["alice"], "team_reviewers": ["platform"]},
        token="t",
    )


@patch("hve.github_api.api_call")
def test_empty_metadata_and_reviewers_do_not_call_api(api_call) -> None:
    assert update_pull_request_metadata(7, repo="o/r", token="t") == {}
    assert request_pull_request_reviewers(7, repo="o/r", token="t") == {}
    api_call.assert_not_called()


@pytest.mark.parametrize(
    "function,kwargs",
    [
        (update_pull_request_metadata, {"labels": ["bug"]}),
        (request_pull_request_reviewers, {"reviewers": ["alice"]}),
    ],
)
@patch("hve.github_api.api_call", return_value=[])
def test_non_object_response_fails_closed(api_call, function, kwargs) -> None:
    with pytest.raises(GitHubAPIError, match="not an object"):
        function(7, repo="o/r", token="t", **kwargs)
