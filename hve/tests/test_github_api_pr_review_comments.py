"""FR-GUI-46: Pull Request review comment REST contracts."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

import hve.github_api as github_api
from hve.github_api import GitHubAPIError


class TestListPullRequestReviewComments:
    @patch("hve.github_api.api_call")
    def test_lists_review_comments_without_reordering(self, api_call) -> None:
        comments = [{"id": 1}, {"id": 2}]
        api_call.return_value = comments

        result = github_api.list_pull_request_review_comments(
            7, repo="o/r", token="token", per_page=25
        )

        assert result == comments
        assert api_call.call_args.args == (
            "GET",
            "https://api.github.com/repos/o/r/pulls/7/comments?per_page=25",
        )
        assert api_call.call_args.kwargs["token"] == "token"
        assert api_call.call_args.kwargs["response_headers"] == {}

    @pytest.mark.parametrize("response", [{}, [{"id": 1}, "invalid"]])
    @patch("hve.github_api.api_call")
    def test_malformed_response_fails_closed(self, api_call, response) -> None:
        api_call.return_value = response

        with pytest.raises(GitHubAPIError, match="review comments response"):
            github_api.list_pull_request_review_comments(
                7, repo="o/r", token="token"
            )

    @patch("hve.github_api.api_call")
    def test_fetches_all_comment_pages_in_api_order(self, api_call) -> None:
        second_url = (
            "https://api.github.com/repos/o/r/pulls/7/comments"
            "?per_page=2&page=2"
        )

        def respond(_method, url, *, response_headers, **_kwargs):
            if url == second_url:
                return [{"id": 3}]
            response_headers["link"] = f'<{second_url}>; rel="next"'
            return [{"id": 1}, {"id": 2}]

        api_call.side_effect = respond

        result = github_api.list_pull_request_review_comments(
            7, repo="o/r", token="token", per_page=2
        )

        assert result == [{"id": 1}, {"id": 2}, {"id": 3}]
        assert api_call.call_args_list[-1].args[1] == second_url


class TestCreatePullRequestReviewComment:
    @patch("hve.github_api.api_call")
    def test_posts_modern_line_side_payload(self, api_call) -> None:
        api_call.return_value = {"id": 9}

        result = github_api.create_pull_request_review_comment(
            7,
            "Please fix this.",
            "abc123",
            "src/app.py",
            12,
            "RIGHT",
            repo="o/r",
            token="token",
        )

        assert result == {"id": 9}
        api_call.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/pulls/7/comments",
            data={
                "body": "Please fix this.",
                "commit_id": "abc123",
                "path": "src/app.py",
                "line": 12,
                "side": "RIGHT",
            },
            token="token",
        )
        assert "position" not in api_call.call_args.kwargs["data"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("body", None),
            ("body", "   "),
            ("commit_id", None),
            ("commit_id", ""),
            ("path", None),
            ("path", "   "),
            ("line", 0),
            ("line", -1),
            ("line", True),
            ("line", "12"),
            ("side", "right"),
            ("side", "BOTH"),
        ],
    )
    @patch("hve.github_api.api_call")
    def test_invalid_field_fails_before_api(
        self, api_call, field: str, value: object
    ) -> None:
        arguments: dict[str, Any] = {
            "body": "body",
            "commit_id": "abc123",
            "path": "src/app.py",
            "line": 12,
            "side": "RIGHT",
        }
        arguments[field] = value

        with pytest.raises(GitHubAPIError, match=field):
            github_api.create_pull_request_review_comment(
                7, repo="o/r", token="token", **arguments
            )
        api_call.assert_not_called()

    @patch("hve.github_api.api_call", return_value=[])
    def test_non_object_response_fails_closed(self, _api_call) -> None:
        with pytest.raises(GitHubAPIError, match="not an object"):
            github_api.create_pull_request_review_comment(
                7,
                "body",
                "abc123",
                "src/app.py",
                12,
                "LEFT",
                repo="o/r",
                token="token",
            )


@patch("hve.github_api.api_call")
def test_pull_request_files_preserve_returned_patch(api_call) -> None:
    patch_text = "@@ -1 +1 @@\n-old\n+new"
    api_call.side_effect = [
        {"number": 7, "changed_files": 1},
        [
            {
                "filename": "src/app.py",
                "status": "modified",
                "patch": patch_text,
            }
        ],
    ]

    result = github_api.list_pull_request_files(7, repo="o/r", token="token")

    assert result == [
        {
            "filename": "src/app.py",
            "status": "modified",
            "patch": patch_text,
        }
    ]


@patch("hve.github_api.api_call")
def test_pull_request_files_bind_the_metadata_head_sha(api_call) -> None:
    api_call.side_effect = [
        {
            "number": 7,
            "changed_files": 1,
            "head": {"sha": "files-snapshot-sha"},
        },
        [{"filename": "src/app.py", "status": "modified", "patch": "+new"}],
    ]

    result = github_api.list_pull_request_files(7, repo="o/r", token="token")

    assert getattr(result, "head_sha", None) == "files-snapshot-sha"


@patch("hve.github_api.api_call")
def test_pull_request_files_keep_absent_patch_absent(api_call) -> None:
    api_call.side_effect = [
        {"number": 7, "changed_files": 1},
        [{"filename": "binary.dat", "status": "modified"}],
    ]

    result = github_api.list_pull_request_files(7, repo="o/r", token="token")

    assert result == [{"filename": "binary.dat", "status": "modified"}]
    assert "patch" not in result[0]


@patch("hve.github_api.api_call")
def test_pull_request_files_reject_non_string_patch(api_call) -> None:
    api_call.side_effect = [
        {"number": 7, "changed_files": 1},
        [{"filename": "src/app.py", "status": "modified", "patch": None}],
    ]

    with pytest.raises(GitHubAPIError, match="patch is not a string"):
        github_api.list_pull_request_files(7, repo="o/r", token="token")


@patch("hve.github_api.api_call")
def test_pull_request_files_fetch_all_declared_pages(api_call) -> None:
    first_page = [
        {"filename": f"src/{index}.py", "status": "modified"}
        for index in range(100)
    ]
    last = {"filename": "src/100.py", "status": "added", "patch": "+new"}
    second_url = (
        "https://api.github.com/repos/o/r/pulls/7/files"
        "?per_page=100&page=2"
    )

    def respond(_method, url, **kwargs):
        if url.endswith("/pulls/7"):
            return {"number": 7, "changed_files": 101}
        if url == second_url:
            return [last]
        kwargs["response_headers"]["link"] = f'<{second_url}>; rel="next"'
        return first_page

    api_call.side_effect = respond

    result = github_api.list_pull_request_files(7, repo="o/r", token="token")

    assert len(result) == 101
    assert result[-1] == last
    assert api_call.call_args_list[-1].args[1] == second_url


@pytest.mark.parametrize("changed_files", [True, -1, "1", None])
@patch("hve.github_api.api_call")
def test_pull_request_files_reject_invalid_expected_count(
    api_call, changed_files
) -> None:
    api_call.return_value = {"number": 7, "changed_files": changed_files}

    with pytest.raises(GitHubAPIError, match="changed_files is invalid"):
        github_api.list_pull_request_files(7, repo="o/r", token="token")
    assert api_call.call_count == 1


@patch("hve.github_api.api_call")
def test_pull_request_files_reject_more_than_api_limit(api_call) -> None:
    api_call.return_value = {"number": 7, "changed_files": 3001}

    with pytest.raises(GitHubAPIError, match="3,000"):
        github_api.list_pull_request_files(7, repo="o/r", token="token")
    assert api_call.call_count == 1


@pytest.mark.parametrize(
    "page",
    [
        [],
        [
            {"filename": "src/a.py", "status": "modified"},
            {"filename": "src/b.py", "status": "modified"},
        ],
    ],
)
@patch("hve.github_api.api_call")
def test_pull_request_files_reject_count_mismatch(api_call, page) -> None:
    api_call.side_effect = [{"number": 7, "changed_files": 1}, page]

    with pytest.raises(GitHubAPIError, match="expected 1"):
        github_api.list_pull_request_files(7, repo="o/r", token="token")
