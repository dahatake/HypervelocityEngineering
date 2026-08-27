"""FR-GUI-42: direct PR creation REST contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hve.github_api import (
    GitHubAPIError,
    compare_commits,
    create_pull_request,
    create_pull_request_details,
    find_open_pull_request,
)


@patch("hve.github_api.api_call")
def test_full_create_result_and_legacy_number_wrapper(api_call) -> None:
    api_call.return_value = {"number": 7, "html_url": "https://github.com/o/r/pull/7"}
    details = create_pull_request_details(
        "Title", "Body", "feature/x", "main", repo="o/r", token="t", draft=True
    )
    assert details["number"] == 7
    assert api_call.call_args.kwargs["data"]["draft"] is True
    api_call.reset_mock()
    api_call.return_value = {"number": 8}
    assert create_pull_request("T", "", "h", "b", repo="o/r", token="t") == 8


@patch("hve.github_api.api_call")
def test_full_create_rejects_non_object_or_missing_number(api_call) -> None:
    api_call.return_value = []
    with pytest.raises(GitHubAPIError, match="not an object"):
        create_pull_request_details("T", "", "h", "b", repo="o/r", token="t")
    api_call.return_value = {}
    with pytest.raises(GitHubAPIError, match="missing number"):
        create_pull_request_details("T", "", "h", "b", repo="o/r", token="t")


@patch("hve.github_api.api_call")
def test_compare_commits_encodes_refs(api_call) -> None:
    api_call.return_value = {"ahead_by": 2, "behind_by": 0, "total_commits": 2, "files": []}
    result = compare_commits("release/日本", "feature/x", repo="o/r", token="t")
    assert result["ahead_by"] == 2
    url = api_call.call_args.args[1]
    assert "release%2F" in url and "feature%2Fx" in url


@patch("hve.github_api.api_call")
def test_find_open_pull_request_uses_targeted_head_and_base(api_call) -> None:
    api_call.return_value = [{"number": 9, "head": {"ref": "feature/x"}}]
    result = find_open_pull_request("feature/x", "main", repo="o/r", token="t")
    assert result == {"number": 9, "head": {"ref": "feature/x"}}
    url = api_call.call_args.args[1]
    assert "state=open" in url
    assert "head=o%3Afeature%2Fx" in url
    assert "base=main" in url


@patch("hve.github_api.api_call", return_value={"message": "bad"})
def test_find_open_pull_request_rejects_non_list(_api_call) -> None:
    with pytest.raises(GitHubAPIError, match="not a list"):
        find_open_pull_request("h", "b", repo="o/r", token="t")
