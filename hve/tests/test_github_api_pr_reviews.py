"""FR-GUI-45: Pull Request review REST contracts."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

import hve.github_api as github_api
from hve.github_api import GitHubAPIError
from hve.github_review_contract import ALLOWED_EVENTS


class TestListPullRequestReviews:
    @patch("hve.github_api.api_call")
    def test_preserves_api_order(self, api_call) -> None:
        first = {"id": 1, "state": "COMMENTED"}
        second = {"id": 2, "state": "APPROVED"}
        api_call.return_value = [first, second]

        result = github_api.list_pull_request_reviews(
            7, repo="o/r", token="token", per_page=25
        )

        assert result == [first, second]
        assert api_call.call_args.args == (
            "GET",
            "https://api.github.com/repos/o/r/pulls/7/reviews?per_page=25",
        )
        assert api_call.call_args.kwargs["token"] == "token"
        assert api_call.call_args.kwargs["response_headers"] == {}

    @patch("hve.github_api.api_call", return_value={})
    def test_non_list_response_fails_closed(self, _api_call) -> None:
        with pytest.raises(GitHubAPIError, match="reviews response is not a list"):
            github_api.list_pull_request_reviews(7, repo="o/r", token="token")

    @patch("hve.github_api.api_call", return_value=[{"id": 1}, "invalid"])
    def test_non_object_entry_fails_closed(self, _api_call) -> None:
        with pytest.raises(GitHubAPIError, match="non-object entry"):
            github_api.list_pull_request_reviews(7, repo="o/r", token="token")

    @patch("hve.github_api.api_call")
    def test_fetches_all_review_pages_in_chronological_order(self, api_call) -> None:
        second_url = (
            "https://api.github.com/repos/o/r/pulls/7/reviews"
            "?per_page=2&page=2"
        )

        def respond(_method, url, *, response_headers, **_kwargs):
            if url == second_url:
                return [{"id": 3}]
            response_headers["link"] = f'<{second_url}>; rel="next"'
            return [{"id": 1}, {"id": 2}]

        api_call.side_effect = respond

        result = github_api.list_pull_request_reviews(
            7, repo="o/r", token="token", per_page=2
        )

        assert result == [{"id": 1}, {"id": 2}, {"id": 3}]
        assert api_call.call_args_list[-1].args[1] == second_url


class TestCreatePullRequestReview:
    @pytest.mark.parametrize("event", ["APPROVE", "REQUEST_CHANGES", "COMMENT"])
    @patch("hve.github_api.api_call")
    def test_sends_allowed_event_and_body(self, api_call, event: str) -> None:
        api_call.return_value = {"id": 9, "state": event}
        body = None if event == "APPROVE" else "review body"

        result = github_api.create_pull_request_review(
            7,
            event,
            body,
            repo="o/r",
            token="token",
        )

        expected = {"event": event}
        if body is not None:
            expected["body"] = body
        assert result["id"] == 9
        api_call.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/o/r/pulls/7/reviews",
            data=expected,
            token="token",
        )

    @patch("hve.github_api.api_call")
    def test_approve_can_include_optional_body(self, api_call) -> None:
        api_call.return_value = {"id": 9}

        github_api.create_pull_request_review(
            7, "APPROVE", "looks good", repo="o/r", token="token"
        )

        assert api_call.call_args.kwargs["data"] == {
            "event": "APPROVE",
            "body": "looks good",
        }

    @pytest.mark.parametrize("body", [None, "", "   "])
    @patch("hve.github_api.api_call")
    def test_approve_omits_blank_body(self, api_call, body) -> None:
        api_call.return_value = {"id": 9}

        github_api.create_pull_request_review(
            7, "APPROVE", body, repo="o/r", token="token"
        )

        assert api_call.call_args.kwargs["data"] == {"event": "APPROVE"}

    @pytest.mark.parametrize("event", ["approve", "DISMISS", "", None])
    @patch("hve.github_api.api_call")
    def test_rejects_unknown_event_before_api(self, api_call, event) -> None:
        with pytest.raises(GitHubAPIError, match="event"):
            github_api.create_pull_request_review(
                7, event, "body", repo="o/r", token="token"
            )
        api_call.assert_not_called()

    @pytest.mark.parametrize("event", ["REQUEST_CHANGES", "COMMENT"])
    @pytest.mark.parametrize("body", [None, "", "   "])
    @patch("hve.github_api.api_call")
    def test_non_approve_event_requires_body(
        self, api_call, event: str, body
    ) -> None:
        with pytest.raises(GitHubAPIError, match="body"):
            github_api.create_pull_request_review(
                7, event, body, repo="o/r", token="token"
            )
        api_call.assert_not_called()

    @patch("hve.github_api.api_call", return_value=[])
    def test_non_object_response_fails_closed(self, _api_call) -> None:
        with pytest.raises(GitHubAPIError, match="not an object"):
            github_api.create_pull_request_review(
                7, "APPROVE", repo="o/r", token="token"
            )


class TestReviewValidationSingleSource:
    def test_contract_owns_allowed_events_for_api_and_panel(self) -> None:
        from hve.gui import github_pr_panel

        assert ALLOWED_EVENTS == (
            "APPROVE",
            "REQUEST_CHANGES",
            "COMMENT",
        )

        api_source = Path(github_api.__file__).read_text(encoding="utf-8")
        panel_source = Path(github_pr_panel.__file__).read_text(encoding="utf-8")
        api_contract_imports = {
            alias.name
            for node in ast.walk(ast.parse(api_source))
            if isinstance(node, ast.ImportFrom)
            and node.module == "hve.github_review_contract"
            for alias in node.names
        }
        panel_contract_imports = {
            alias.name
            for node in ast.walk(ast.parse(panel_source))
            if isinstance(node, ast.ImportFrom)
            and node.module == "hve.github_review_contract"
            for alias in node.names
        }
        assert api_contract_imports == {
            "ReviewValidationError",
            "validate_pull_request_review",
        }
        assert panel_contract_imports == {
            "ALLOWED_EVENTS",
            "ReviewValidationError",
            "validate_pull_request_review",
        }
        assert "_PULL_REQUEST_REVIEW_EVENTS" not in api_source
        assert "_REVIEW_EVENTS" not in panel_source
        assert "_REVIEW_BODY_REQUIRED_EVENTS" not in panel_source

    def test_api_delegates_event_and_body_validation_to_contract(
        self, monkeypatch
    ) -> None:
        seen: list[tuple[object, object]] = []

        def _validate(event, body):
            seen.append((event, body))
            return "APPROVE", None

        monkeypatch.setattr(github_api, "validate_pull_request_review", _validate)
        monkeypatch.setattr(github_api, "api_call", lambda *_a, **_kw: {"id": 9})

        github_api.create_pull_request_review(
            7,
            "anything",
            "original body",
            repo="o/r",
            token="token",
        )

        assert seen == [("anything", "original body")]
