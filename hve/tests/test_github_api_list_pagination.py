"""FR-GUI-48: explicit Issue / Pull Request list pagination contracts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hve.github_api import GitHubAPIError, list_issues, list_pull_requests


@pytest.mark.parametrize(
    ("function", "resource"),
    [
        (list_issues, "issues"),
        (list_pull_requests, "pulls"),
    ],
)
class TestListPagination:
    @patch("hve.github_api.api_call", return_value=[])
    def test_default_page_uses_created_desc_stable_order(
        self, api_call, function, resource
    ) -> None:
        result = function(repo="o/r", token="token", state="all", per_page=25)

        assert api_call.call_args.args == (
            "GET",
            f"https://api.github.com/repos/o/r/{resource}"
            "?state=all&sort=created&direction=desc&per_page=25",
        )
        assert api_call.call_args.kwargs["token"] == "token"
        assert api_call.call_args.kwargs["response_headers"] == {}
        assert getattr(result, "next_url") is None

    @patch("hve.github_api.api_call", return_value=[])
    def test_explicit_page_one_is_also_omitted(self, api_call, function, resource) -> None:
        function(repo="o/r", token="token", page=1)

        assert "&page=" not in api_call.call_args.args[1]

    @patch("hve.github_api.api_call", return_value=[])
    def test_later_page_is_appended_to_query(self, api_call, function, resource) -> None:
        function(repo="o/r", token="token", state="open", per_page=50, page=3)

        assert api_call.call_args.args == (
            "GET",
            f"https://api.github.com/repos/o/r/{resource}"
            "?state=open&sort=created&direction=desc&per_page=50&page=3",
        )

    @pytest.mark.parametrize("page", [0, -1, True, "2"])
    @patch("hve.github_api.api_call")
    def test_invalid_page_is_rejected(self, api_call, function, resource, page) -> None:
        with pytest.raises(GitHubAPIError, match="page"):
            function(repo="o/r", token="token", page=page)
        api_call.assert_not_called()

    @patch("hve.github_api.api_call")
    def test_next_link_is_exposed_as_opaque_cursor(
        self, api_call, function, resource
    ) -> None:
        next_url = (
            f"https://api.github.com/repos/o/r/{resource}"
            "?state=open&sort=created&direction=desc&per_page=2&page=2"
        )

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = (
                f'<{next_url}>; rel="next", '
                f'<{next_url.replace("page=2", "page=9")}>; rel="last"'
            )
            return [{"number": 1}, {"number": 2}]

        api_call.side_effect = respond

        result = function(repo="o/r", token="token", per_page=2)

        assert getattr(result, "next_url") == next_url

    @patch("hve.github_api.api_call", return_value=[])
    @pytest.mark.parametrize(
        "query",
        [
            "state=open&sort=created&direction=desc&per_page=50&page=2",
            "per_page=50&after=opaque%2Bcursor%2Fvalue",
        ],
    )
    def test_valid_cursor_is_used_verbatim(
        self, api_call, function, resource, query
    ) -> None:
        cursor = (
            f"https://api.github.com/repos/o/r/{resource}"
            f"?{query}"
        )

        function(repo="o/r", token="token", cursor=cursor)

        assert api_call.call_args.args == ("GET", cursor)

    @pytest.mark.parametrize(
        "cursor",
        [
            "http://api.github.com/repos/o/r/{resource}?page=2",
            "https://evil.example/repos/o/r/{resource}?page=2",
            "https://token@api.github.com/repos/o/r/{resource}?page=2",
            "https://api.github.com:444/repos/o/r/{resource}?page=2",
            "https://api.github.com:invalid/repos/o/r/{resource}?page=2",
            "https://api.github.com:99999/repos/o/r/{resource}?page=2",
            "https://[invalid/repos/o/r/{resource}?page=2",
            "https://api.github.com/repos/o/other/{resource}?page=2",
            "https://api.github.com/repos/o/r/{resource}?page=2#fragment",
            "https://api.github.com/repos/o/r/{resource}?page=2\x00ignored",
        ],
    )
    @patch("hve.github_api.api_call")
    def test_unsafe_cursor_is_rejected_before_request(
        self, api_call, function, resource, cursor
    ) -> None:
        with pytest.raises(GitHubAPIError, match="pagination cursor"):
            function(
                repo="o/r",
                token="token",
                cursor=cursor.format(resource=resource),
            )

        api_call.assert_not_called()

    @patch("hve.github_api.api_call", return_value=[])
    def test_explicit_default_https_port_is_same_origin_and_normalized(
        self, api_call, function, resource
    ) -> None:
        cursor = f"https://api.github.com:443/repos/o/r/{resource}?page=2"

        function(repo="o/r", token="token", cursor=cursor)

        assert api_call.call_args.args == (
            "GET",
            f"https://api.github.com/repos/o/r/{resource}?page=2",
        )

    @patch("hve.github_api.api_call")
    def test_quoted_comma_in_other_link_parameter_is_supported(
        self, api_call, function, resource
    ) -> None:
        next_url = f"https://api.github.com/repos/o/r/{resource}?page=2"

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["Link"] = (
                f'<{next_url}>; title="page, two"; rel="next"'
            )
            return []

        api_call.side_effect = respond

        result = function(repo="o/r", token="token")

        assert getattr(result, "next_url") == next_url

    @patch("hve.github_api.api_call")
    def test_quoted_semicolon_in_other_link_parameter_is_supported(
        self, api_call, function, resource
    ) -> None:
        next_url = f"https://api.github.com/repos/o/r/{resource}?page=2"

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = (
                f'<{next_url}>; title="page; two"; rel="next"'
            )
            return []

        api_call.side_effect = respond

        result = function(repo="o/r", token="token")

        assert getattr(result, "next_url") == next_url

    @patch("hve.github_api.api_call")
    def test_quoted_parameter_text_cannot_be_parsed_as_rel(
        self, api_call, function, resource
    ) -> None:
        next_url = f"https://api.github.com/repos/o/r/{resource}?page=2"

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = (
                f'<{next_url}>; title="ignored; rel=next"; rel="last"'
            )
            return []

        api_call.side_effect = respond

        result = function(repo="o/r", token="token")

        assert getattr(result, "next_url") is None

    @patch("hve.github_api.api_call")
    @pytest.mark.parametrize(
        ("first_rel", "second_rel", "expects_next"),
        [
            ("prev", "next", False),
            ("next", "prev", True),
        ],
    )
    def test_duplicate_rel_parameters_use_the_first_occurrence(
        self, api_call, function, resource, first_rel, second_rel, expects_next
    ) -> None:
        next_url = f"https://api.github.com/repos/o/r/{resource}?page=2"

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = (
                f'<{next_url}>; rel="{first_rel}"; rel="{second_rel}"'
            )
            return []

        api_call.side_effect = respond

        result = function(repo="o/r", token="token")

        assert getattr(result, "next_url") == (next_url if expects_next else None)

    @patch("hve.github_api.api_call")
    def test_quoted_pair_is_unescaped_before_rel_matching(
        self, api_call, function, resource
    ) -> None:
        next_url = f"https://api.github.com/repos/o/r/{resource}?page=2"

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = f'<{next_url}>; rel="nex\\t"'
            return []

        api_call.side_effect = respond

        result = function(repo="o/r", token="token")

        assert getattr(result, "next_url") == next_url

    @patch("hve.github_api.api_call")
    def test_anchored_next_link_is_ignored(
        self, api_call, function, resource
    ) -> None:
        next_url = f"https://api.github.com/repos/o/r/{resource}?page=2"

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = (
                f'<{next_url}>; rel="next"; anchor="/different-context"'
            )
            return []

        api_call.side_effect = respond

        result = function(repo="o/r", token="token")

        assert getattr(result, "next_url") is None

    @patch("hve.github_api.api_call")
    def test_empty_http_list_members_are_ignored(
        self, api_call, function, resource
    ) -> None:
        next_url = f"https://api.github.com/repos/o/r/{resource}?page=2"

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = f', , <{next_url}>; rel="next", '
            return []

        api_call.side_effect = respond

        result = function(repo="o/r", token="token")

        assert getattr(result, "next_url") == next_url

    @pytest.mark.parametrize(
        "relation_value",
        ["next previous", "next\x1b"],
    )
    @patch("hve.github_api.api_call")
    def test_malformed_unquoted_rel_is_rejected(
        self, api_call, function, resource, relation_value
    ) -> None:
        next_url = f"https://api.github.com/repos/o/r/{resource}?page=2"

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = f"<{next_url}>; rel={relation_value}"
            return []

        api_call.side_effect = respond

        with pytest.raises(GitHubAPIError, match="malformed rel"):
            function(repo="o/r", token="token")

    @patch("hve.github_api.api_call")
    def test_multiple_next_links_are_rejected(
        self, api_call, function, resource
    ) -> None:
        first = f"https://api.github.com/repos/o/r/{resource}?page=2"
        second = f"https://api.github.com/repos/o/r/{resource}?page=3"

        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = (
                f'<{first}>; rel="next", <{second}>; rel="next"'
            )
            return []

        api_call.side_effect = respond

        with pytest.raises(GitHubAPIError, match="multiple rel=next"):
            function(repo="o/r", token="token")

    @patch("hve.github_api.api_call")
    def test_unsafe_next_link_is_rejected(
        self, api_call, function, resource
    ) -> None:
        def respond(_method, _url, *, response_headers, **_kwargs):
            response_headers["link"] = (
                f'<https://evil.example/repos/o/r/{resource}?page=2>; rel="next"'
            )
            return []

        api_call.side_effect = respond

        with pytest.raises(GitHubAPIError, match="pagination cursor"):
            function(repo="o/r", token="token")

    @patch("hve.github_api.api_call")
    def test_self_referencing_next_link_is_rejected_as_cycle(
        self, api_call, function, resource
    ) -> None:
        def respond(_method, url, *, response_headers, **_kwargs):
            response_headers["link"] = f'<{url}>; rel="next"'
            return []

        api_call.side_effect = respond

        with pytest.raises(GitHubAPIError, match="cycle"):
            function(repo="o/r", token="token")

    @patch("hve.github_api.api_call")
    def test_cursor_cannot_be_combined_with_later_numeric_page(
        self, api_call, function, resource
    ) -> None:
        cursor = f"https://api.github.com/repos/o/r/{resource}?page=2"

        with pytest.raises(GitHubAPIError, match="page.*cursor|cursor.*page"):
            function(repo="o/r", token="token", page=2, cursor=cursor)

        api_call.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        {},
        [{"number": 1}, "invalid"],
    ],
)
@patch("hve.github_api.api_call")
def test_pull_request_page_malformed_response_fails_closed(
    api_call, response
) -> None:
    api_call.return_value = response

    with pytest.raises(GitHubAPIError, match="pull requests response"):
        list_pull_requests(repo="o/r", token="token", page=2)

