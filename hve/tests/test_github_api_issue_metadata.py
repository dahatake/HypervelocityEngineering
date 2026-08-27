"""FR-GUI-41: Issue metadata REST contract tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hve.github_api import (
    GitHubAPIError,
    create_issue,
    create_issue_details,
    list_assignees,
    list_labels,
    list_milestones,
)


class TestCreateIssueMetadata:
    @patch("hve.github_api.api_call")
    def test_optional_body_and_metadata_payload(self, api_call) -> None:
        api_call.return_value = {
            "number": 12,
            "id": 1200,
            "html_url": "https://github.com/o/r/issues/12",
            "labels": [{"name": "bug"}],
            "assignees": [{"login": "octocat"}],
            "milestone": {"number": 3, "title": "v1"},
        }
        result = create_issue_details(
            "Title",
            "",
            ["bug"],
            repo="o/r",
            token="token",
            assignees=["octocat"],
            milestone=3,
        )
        assert result["number"] == 12
        api_call.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/issues",
            data={
                "title": "Title",
                "body": "",
                "labels": ["bug"],
                "assignees": ["octocat"],
                "milestone": 3,
            },
            token="token",
        )

    @patch("hve.github_api.api_call")
    def test_legacy_wrapper_keeps_tuple_result(self, api_call) -> None:
        api_call.return_value = {"number": 12, "id": 1200}
        assert create_issue("Title", "Body", [], repo="o/r", token="t") == (12, 1200)

    @patch("hve.github_api.api_call", return_value=[])
    def test_non_object_create_response_fails_closed(self, _api_call) -> None:
        with pytest.raises(GitHubAPIError, match="not an object"):
            create_issue_details("Title", None, [], repo="o/r", token="t")


@pytest.mark.parametrize(
    ("function", "path", "response", "expected"),
    [
        (
            list_labels,
            "labels?per_page=100",
            [{"name": "bug"}, {"color": "fff"}, "bad"],
            [{"name": "bug"}],
        ),
        (
            list_assignees,
            "assignees?per_page=100",
            [{"login": "octocat"}, {"id": 2}, None],
            [{"login": "octocat"}],
        ),
        (
            list_milestones,
            "milestones?state=open&sort=due_on&direction=asc&per_page=100",
            [{"number": 3, "title": "v1"}, {"number": 0, "title": "bad"}],
            [{"number": 3, "title": "v1"}],
        ),
    ],
)
def test_metadata_candidates_use_bounded_first_page(
    function, path, response, expected
) -> None:
    with patch("hve.github_api.api_call", return_value=response) as api_call:
        assert function(repo="o/r", token="t", per_page=500) == expected
    assert path in api_call.call_args.args[1]


@pytest.mark.parametrize("function", [list_labels, list_assignees, list_milestones])
def test_metadata_candidate_non_list_response_is_rejected(function) -> None:
    with patch("hve.github_api.api_call", return_value={"message": "bad"}):
        with pytest.raises(GitHubAPIError, match="not a list"):
            function(repo="o/r", token="t")
