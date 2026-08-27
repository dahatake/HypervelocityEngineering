"""FR-GUI-47: synchronous Pull Request merge REST contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import hve.github_api as github_api
from hve.github_api import GitHubAPIError


class TestMergePullRequest:
    @pytest.mark.parametrize("merge_method", ["merge", "squash", "rebase"])
    @patch("hve.github_api.api_call")
    def test_puts_allowed_merge_method(self, api_call, merge_method: str) -> None:
        api_call.return_value = {
            "sha": "merged123",
            "merged": True,
            "message": "Pull Request successfully merged",
        }

        result = github_api.merge_pull_request(
            7,
            merge_method,
            repo="o/r",
            token="token",
        )

        assert result["merged"] is True
        api_call.assert_called_once_with(
            "PUT",
            "https://api.github.com/repos/o/r/pulls/7/merge",
            data={"merge_method": merge_method},
            token="token",
        )

    @patch("hve.github_api.api_call")
    def test_sends_expected_head_sha_when_provided(self, api_call) -> None:
        api_call.return_value = {"sha": "merged123", "merged": True, "message": "ok"}

        github_api.merge_pull_request(
            7,
            "squash",
            sha="head123",
            repo="o/r",
            token="token",
        )

        assert api_call.call_args.kwargs["data"] == {
            "merge_method": "squash",
            "sha": "head123",
        }

    @pytest.mark.parametrize("merge_method", ["", "MERGE", "auto", None, True])
    @patch("hve.github_api.api_call")
    def test_rejects_unknown_method_before_api(self, api_call, merge_method) -> None:
        with pytest.raises(GitHubAPIError, match="merge_method"):
            github_api.merge_pull_request(
                7,
                merge_method,
                repo="o/r",
                token="token",
            )
        api_call.assert_not_called()

    @pytest.mark.parametrize("sha", ["", "   ", 123, True])
    @patch("hve.github_api.api_call")
    def test_rejects_invalid_explicit_sha_before_api(self, api_call, sha) -> None:
        with pytest.raises(GitHubAPIError, match="sha"):
            github_api.merge_pull_request(
                7,
                "merge",
                sha=sha,
                repo="o/r",
                token="token",
            )
        api_call.assert_not_called()

    @patch("hve.github_api.api_call", return_value=[])
    def test_non_object_response_fails_closed(self, _api_call) -> None:
        with pytest.raises(GitHubAPIError, match="not an object"):
            github_api.merge_pull_request(
                7,
                "merge",
                repo="o/r",
                token="token",
            )

    @pytest.mark.parametrize(
        "response",
        [
            {},
            {"merged": False, "message": "not merged"},
            {"merged": "true", "message": "invalid"},
        ],
    )
    @patch("hve.github_api.api_call")
    def test_unconfirmed_merge_response_fails_closed(
        self, api_call, response: dict
    ) -> None:
        api_call.return_value = response

        with pytest.raises(GitHubAPIError, match="did not confirm"):
            github_api.merge_pull_request(
                7,
                "merge",
                repo="o/r",
                token="token",
            )


class TestListCheckRunsForRef:
    @patch("hve.github_api.api_call")
    def test_fetches_all_declared_pages(self, api_call) -> None:
        first_page = [
            {"name": f"check-{index}", "status": "completed", "conclusion": "success"}
            for index in range(100)
        ]
        failure = {"name": "late-failure", "status": "completed", "conclusion": "failure"}
        second_url = (
            "https://api.github.com/repos/o/r/commits/head123/check-runs"
            "?per_page=100&page=2"
        )

        def respond(_method, url, *, response_headers, **_kwargs):
            if url == second_url:
                return {"total_count": 101, "check_runs": [failure]}
            response_headers["link"] = f'<{second_url}>; rel="next"'
            return {"total_count": 101, "check_runs": first_page}

        api_call.side_effect = respond

        result = github_api.list_check_runs_for_ref(
            "head123", repo="o/r", token="token"
        )

        assert len(result) == 101
        assert result[-1] == failure
        assert api_call.call_args_list[-1].args[1] == second_url

    @pytest.mark.parametrize(
        "response",
        [
            [],
            {},
            {"total_count": 1, "check_runs": "invalid"},
            {"total_count": 1, "check_runs": ["invalid"]},
            {"total_count": True, "check_runs": []},
        ],
    )
    @patch("hve.github_api.api_call")
    def test_malformed_response_fails_closed(self, api_call, response) -> None:
        api_call.return_value = response

        with pytest.raises(GitHubAPIError, match="check-runs response"):
            github_api.list_check_runs_for_ref(
                "head123", repo="o/r", token="token"
            )

    @pytest.mark.parametrize(
        "pages",
        [
            [
                {"total_count": 2, "check_runs": [{"name": "one"}]},
                {"total_count": 2, "check_runs": []},
            ],
            [
                {"total_count": 1, "check_runs": [{"name": "one"}, {"name": "extra"}]},
            ],
        ],
    )
    @patch("hve.github_api.api_call")
    def test_count_mismatch_fails_closed(self, api_call, pages) -> None:
        second_url = (
            "https://api.github.com/repos/o/r/commits/head123/check-runs"
            "?per_page=100&page=2"
        )

        def respond(_method, url, *, response_headers, **_kwargs):
            index = 1 if url == second_url else 0
            if index == 0 and len(pages) > 1:
                response_headers["link"] = f'<{second_url}>; rel="next"'
            return pages[index]

        api_call.side_effect = respond

        with pytest.raises(GitHubAPIError, match="expected"):
            github_api.list_check_runs_for_ref(
                "head123", repo="o/r", token="token"
            )
