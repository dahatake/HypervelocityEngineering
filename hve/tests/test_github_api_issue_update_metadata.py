"""FR-GUI-44: existing Issue metadata update REST contracts."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import patch

import pytest

from hve.github_api import GitHubAPIError, update_issue


class TestUpdateIssueMetadata:
    @patch("hve.github_api.api_call")
    def test_none_metadata_is_omitted(self, api_call) -> None:
        api_call.return_value = {"number": 7}

        update_issue(
            7,
            repo="o/r",
            token="token",
            title="new title",
            labels=None,
            assignees=None,
            milestone=None,
        )

        api_call.assert_called_once_with(
            "PATCH",
            "https://api.github.com/repos/o/r/issues/7",
            data={"title": "new title"},
            token="token",
        )

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"labels": []}, {"labels": []}),
            ({"assignees": []}, {"assignees": []}),
            ({"milestone": 3}, {"milestone": 3}),
            ({"milestone": 0}, {"milestone": None}),
        ],
    )
    @patch("hve.github_api.api_call")
    def test_explicit_metadata_is_sent(self, api_call, kwargs, expected) -> None:
        response: dict[str, object] = {"number": 7}
        if "labels" in kwargs:
            response["labels"] = [{"name": value} for value in kwargs["labels"]]
        if "assignees" in kwargs:
            response["assignees"] = [
                {"login": value} for value in kwargs["assignees"]
            ]
        if "milestone" in kwargs:
            response["milestone"] = (
                None
                if kwargs["milestone"] == 0
                else {"number": kwargs["milestone"]}
            )
        api_call.return_value = response

        update_issue(7, repo="o/r", token="token", **kwargs)

        assert api_call.call_args.kwargs["data"] == expected

    @patch("hve.github_api.api_call")
    def test_metadata_can_be_combined_with_existing_fields(self, api_call) -> None:
        api_call.return_value = {
            "number": 7,
            "labels": [{"name": "bug"}],
            "assignees": [{"login": "octocat"}],
            "milestone": {"number": 2},
        }

        update_issue(
            7,
            repo="o/r",
            token="token",
            body="body",
            labels=["bug"],
            assignees=["octocat"],
            milestone=2,
        )

        assert api_call.call_args.kwargs["data"] == {
            "body": "body",
            "labels": ["bug"],
            "assignees": ["octocat"],
            "milestone": 2,
        }

    @patch("hve.github_api.api_call")
    def test_metadata_lists_are_copied_before_sending(self, api_call) -> None:
        api_call.return_value = {
            "number": 7,
            "labels": [{"name": "bug"}],
            "assignees": [{"login": "octocat"}],
        }
        labels = ["bug"]
        assignees = ["octocat"]

        update_issue(
            7,
            repo="o/r",
            token="token",
            labels=labels,
            assignees=assignees,
        )
        labels.append("later")
        assignees.append("later")

        assert api_call.call_args.kwargs["data"] == {
            "labels": ["bug"],
            "assignees": ["octocat"],
        }

    @patch("hve.github_api.api_call", return_value=[])
    def test_non_object_response_fails_closed(self, _api_call) -> None:
        with pytest.raises(GitHubAPIError, match="not an object"):
            update_issue(7, repo="o/r", token="token", labels=["bug"])

    @pytest.mark.parametrize("response", [{}, {"number": 8}])
    @patch("hve.github_api.api_call")
    def test_response_must_confirm_requested_issue(
        self, api_call, response: dict
    ) -> None:
        api_call.return_value = response

        with pytest.raises(GitHubAPIError, match="issue number"):
            update_issue(7, repo="o/r", token="token", labels=[])

    @pytest.mark.parametrize(
        ("kwargs", "response", "field"),
        [
            ({"labels": []}, {"number": 7}, "labels"),
            ({"assignees": []}, {"number": 7}, "assignees"),
            ({"milestone": 0}, {"number": 7}, "milestone"),
            ({"labels": []}, {"number": 7, "labels": "bad"}, "labels"),
            (
                {"assignees": []},
                {"number": 7, "assignees": ["bad"]},
                "assignees",
            ),
            ({"milestone": 3}, {"number": 7, "milestone": "bad"}, "milestone"),
        ],
    )
    @patch("hve.github_api.api_call")
    def test_requested_metadata_response_schema_is_required(
        self, api_call, kwargs: dict, response: dict, field: str
    ) -> None:
        api_call.return_value = response

        with pytest.raises(GitHubAPIError, match=field):
            update_issue(7, repo="o/r", token="token", **kwargs)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("labels", "bug"),
            ("labels", {"bug": True}),
            ("labels", [1]),
            ("labels", [""]),
            ("assignees", "octocat"),
            ("assignees", {"login": "octocat"}),
            ("assignees", [1]),
            ("assignees", [""]),
        ],
    )
    @patch("hve.github_api.api_call")
    def test_invalid_metadata_list_fails_before_api(
        self, api_call, field: str, value: object
    ) -> None:
        with pytest.raises(GitHubAPIError, match=field):
            cast(Any, update_issue)(
                7, repo="o/r", token="token", **{field: value}
            )
        api_call.assert_not_called()

    @pytest.mark.parametrize("milestone", [-1, True, "3"])
    @patch("hve.github_api.api_call")
    def test_invalid_milestone_is_rejected(self, api_call, milestone) -> None:
        with pytest.raises(GitHubAPIError, match="milestone"):
            update_issue(7, repo="o/r", token="token", milestone=milestone)
        api_call.assert_not_called()

    @patch("hve.github_api.api_call")
    def test_none_only_still_counts_as_no_fields(self, api_call) -> None:
        with pytest.raises(GitHubAPIError, match="no fields"):
            update_issue(
                7,
                repo="o/r",
                token="token",
                labels=None,
                assignees=None,
                milestone=None,
            )
        api_call.assert_not_called()
