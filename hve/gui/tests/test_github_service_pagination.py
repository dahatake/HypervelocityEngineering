"""FR-GUI-48: GUI service pagination delegation contracts."""

from __future__ import annotations

from typing import Any

import pytest

from hve.github_api import GitHubAPIError
from hve.gui import github_service


@pytest.mark.parametrize(
    ("service_name", "api_name"),
    [
        ("list_issues", "list_issues"),
        ("list_pull_requests", "list_pull_requests"),
    ],
)
def test_list_service_delegates_page(monkeypatch, service_name: str, api_name: str) -> None:
    captured: dict[str, Any] = {}

    def _list(repo=None, token=None, state="open", per_page=50, page=1):
        captured.update(repo=repo, state=state, per_page=per_page, page=page)
        return [{"number": 1}]

    monkeypatch.setattr(github_service.github_api, api_name, _list)

    result = getattr(github_service, service_name)(
        "o/r", state="closed", per_page=20, page=4
    )

    assert result == [{"number": 1}]
    assert captured == {
        "repo": "o/r",
        "state": "closed",
        "per_page": 20,
        "page": 4,
    }


@pytest.mark.parametrize("service_name", ["list_issues", "list_pull_requests"])
def test_invalid_page_error_is_translated(monkeypatch, service_name: str) -> None:
    api_name = service_name

    def _boom(*_args, **_kwargs):
        raise GitHubAPIError("page must be positive", 0)

    monkeypatch.setattr(github_service.github_api, api_name, _boom)

    with pytest.raises(github_service.GitHubServiceError, match="page must be positive"):
        getattr(github_service, service_name)("o/r", page=0)


@pytest.mark.parametrize(
    ("service_name", "api_name", "resource"),
    [
        ("list_issues", "list_issues", "issues"),
        ("list_pull_requests", "list_pull_requests", "pulls"),
    ],
)
def test_list_service_delegates_opaque_cursor(
    monkeypatch,
    service_name: str,
    api_name: str,
    resource: str,
) -> None:
    captured: dict[str, Any] = {}
    cursor = f"https://api.github.com/repos/o/r/{resource}?page=2"

    def _list(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(github_service.github_api, api_name, _list)

    getattr(github_service, service_name)("o/r", cursor=cursor)

    assert captured == {
        "repo": "o/r",
        "state": "open",
        "per_page": 50,
        "page": 1,
        "cursor": cursor,
    }
