"""FR-GUI-48: Pull Request 一覧の明示ページング UI 契約。"""

from __future__ import annotations

import os
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from hve.gui.github_service import GitHubServiceError  # noqa: E402


PAGE_SIZE = 50


class _PullRequestPage(list[dict[str, Any]]):
    def __init__(
        self,
        values: list[dict[str, Any]],
        next_url: str | None = None,
    ) -> None:
        super().__init__(values)
        self.next_url = next_url


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _pull(number: int, title: str | None = None) -> dict[str, Any]:
    return {
        "number": number,
        "title": title or f"PR {number}",
        "state": "open",
        "body": "",
        "head": {"ref": f"feature/{number}", "repo": {"full_name": "o/r"}},
        "base": {"ref": "main"},
        "html_url": f"https://github.com/o/r/pull/{number}",
    }


def _full_page(first_number: int) -> list[dict[str, Any]]:
    return [_pull(first_number - offset) for offset in range(PAGE_SIZE)]


def _cursor(page: int, repo: str = "o/r", state: str = "open") -> str:
    return (
        f"https://api.github.com/repos/{repo}/pulls"
        f"?state={state}&sort=created&direction=desc&per_page={PAGE_SIZE}&page={page}"
    )


def _page(
    values: list[dict[str, Any]],
    *,
    next_page: int | None = None,
    repo: str = "o/r",
    state: str = "open",
) -> _PullRequestPage:
    return _PullRequestPage(
        values,
        next_url=(
            _cursor(next_page, repo=repo, state=state)
            if next_page is not None
            else None
        ),
    )


def _page_from_cursor(cursor: str | None, fallback: int = 1) -> int:
    if cursor is None:
        return fallback
    return int(parse_qs(urlsplit(cursor).query)["page"][0])


def _install_safe_detail_stubs(monkeypatch, module) -> None:
    monkeypatch.setattr(
        module.github_service,
        "get_pull_request",
        lambda repo, number: _pull(int(number)),
    )
    monkeypatch.setattr(
        module.github_service,
        "list_pull_request_files",
        lambda repo, number: [],
    )
    monkeypatch.setattr(
        module.github_service,
        "list_comments",
        lambda repo, number: [],
    )
    monkeypatch.setattr(
        module.github_service,
        "list_pull_request_reviews",
        lambda repo, number: [],
    )


@pytest.fixture
def panel(qapp, monkeypatch):
    from hve.gui import github_pr_panel as module

    responses: dict[tuple[str, str, int], Any] = {
        ("o/r", "open", 1): _page(_full_page(1000), next_page=2),
        ("o/r", "open", 2): _page([_pull(900, "second-page")]),
    }
    calls: list[tuple[str, str, int, int]] = []
    cursors: list[str | None] = []

    def _list_pull_requests(
        repo: str,
        state: str = "open",
        per_page: int = PAGE_SIZE,
        page: int = 1,
        cursor: str | None = None,
    ) -> Any:
        requested_page = _page_from_cursor(cursor, page)
        calls.append((repo, state, per_page, requested_page))
        cursors.append(cursor)
        result = responses.get((repo, state, requested_page), _page([]))
        if isinstance(result, Exception):
            raise result
        if isinstance(result, list):
            return (
                result
                if hasattr(result, "next_url")
                else _page(list(result))
            )
        return result

    monkeypatch.setattr(
        module.github_service, "list_pull_requests", _list_pull_requests
    )
    _install_safe_detail_stubs(monkeypatch, module)

    widget = module.GitHubPullRequestPanel()
    widget.set_repo("o/r")

    def _sync(
        task: Callable[[], Any],
        on_ok: Callable[[Any], None],
        on_ng: Callable[[str], None] | None = None,
    ) -> None:
        try:
            result = task()
        except GitHubServiceError as exc:
            (on_ng or widget._show_error)(str(exc))
        else:
            on_ok(result)

    monkeypatch.setattr(widget, "_run", _sync)
    widget._pagination_calls = calls  # type: ignore[attr-defined]
    widget._pagination_cursors = cursors  # type: ignore[attr-defined]
    widget._pagination_responses = responses  # type: ignore[attr-defined]
    yield widget
    widget.deleteLater()
    qapp.processEvents()


@pytest.fixture
def deferred_panel(qapp, monkeypatch):
    from hve.gui import github_pr_panel as module

    responses: dict[tuple[str, str, int], Any] = {
        ("o/r", "open", 1): _page(_full_page(1000), next_page=2),
        ("new/repo", "open", 1): _page([_pull(77, "new-repo")]),
        ("o/r", "closed", 1): _page([_pull(66, "closed-state")]),
    }
    calls: list[tuple[str, str, int, int]] = []
    cursors: list[str | None] = []
    pending: list[
        tuple[
            Callable[[], Any],
            Callable[[Any], None],
            Callable[[str], None] | None,
        ]
    ] = []

    def _list_pull_requests(
        repo: str,
        state: str = "open",
        per_page: int = PAGE_SIZE,
        page: int = 1,
        cursor: str | None = None,
    ) -> Any:
        requested_page = _page_from_cursor(cursor, page)
        calls.append((repo, state, per_page, requested_page))
        cursors.append(cursor)
        result = responses.get((repo, state, requested_page), _page([]))
        if isinstance(result, Exception):
            raise result
        if isinstance(result, list):
            return (
                result
                if hasattr(result, "next_url")
                else _page(list(result))
            )
        return result

    monkeypatch.setattr(
        module.github_service, "list_pull_requests", _list_pull_requests
    )
    _install_safe_detail_stubs(monkeypatch, module)

    widget = module.GitHubPullRequestPanel()
    widget.set_repo("o/r")

    def _defer(
        task: Callable[[], Any],
        on_ok: Callable[[Any], None],
        on_ng: Callable[[str], None] | None = None,
    ) -> None:
        pending.append((task, on_ok, on_ng))

    monkeypatch.setattr(widget, "_run", _defer)
    widget._pagination_calls = calls  # type: ignore[attr-defined]
    widget._pagination_cursors = cursors  # type: ignore[attr-defined]
    widget._pagination_responses = responses  # type: ignore[attr-defined]
    widget._pagination_pending = pending  # type: ignore[attr-defined]
    yield widget
    pending.clear()
    widget.deleteLater()
    qapp.processEvents()


def _resolve_next(widget) -> None:
    task, on_ok, on_ng = widget._pagination_pending.pop(0)
    try:
        result = task()
    except GitHubServiceError as exc:
        (on_ng or widget._show_error)(str(exc))
    else:
        on_ok(result)


class TestExplicitPaginationControls:
    def test_exposes_exactly_one_explicit_load_more_button(self, panel) -> None:
        buttons = [
            button
            for button in panel.findChildren(QPushButton)
            if button.text() == "さらに読み込む"
        ]
        assert buttons == [panel.load_more_button]
        assert not panel.load_more_button.isEnabled()

    def test_does_not_prefetch_on_refresh_scroll_or_event_processing(
        self, panel, qapp
    ) -> None:
        panel.refresh_pull_requests()
        assert [call[3] for call in panel._pagination_calls] == [1]

        scrollbar = panel.pr_list.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        qapp.processEvents()
        qapp.processEvents()

        assert [call[3] for call in panel._pagination_calls] == [1]
        panel.load_more_button.click()
        assert [call[3] for call in panel._pagination_calls] == [1, 2]
        assert panel._pagination_cursors == [None, _cursor(2)]


class TestRefreshAndLoadMore:
    def test_refresh_uses_page_one_replaces_items_and_resets_page_state(
        self, panel
    ) -> None:
        panel.refresh_pull_requests()
        panel.load_more_button.click()
        assert any(pr["number"] == 900 for pr in panel._pulls)

        panel._pagination_responses[("o/r", "open", 1)] = [_pull(7, "fresh")]
        panel.refresh_pull_requests()

        assert panel._pagination_calls[-1] == ("o/r", "open", PAGE_SIZE, 1)
        assert [(pr["number"], pr["title"]) for pr in panel._pulls] == [(7, "fresh")]
        assert not panel.load_more_button.isEnabled()

    def test_load_more_passes_each_next_page_and_advances_after_success(
        self, panel
    ) -> None:
        panel._pagination_responses[("o/r", "open", 2)] = _page(
            _full_page(950), next_page=3
        )
        panel._pagination_responses[("o/r", "open", 3)] = _page([_pull(850)])

        panel.refresh_pull_requests()
        panel.load_more_button.click()
        panel.load_more_button.click()

        assert [call[3] for call in panel._pagination_calls] == [1, 2, 3]
        assert len(panel._pulls) == 101
        assert not panel.load_more_button.isEnabled()

    def test_next_link_keeps_load_more_enabled_regardless_of_page_size(
        self, panel
    ) -> None:
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            [_pull(1000)], next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page(
            [], next_page=3
        )

        panel.refresh_pull_requests()
        assert panel.load_more_button.isEnabled()
        panel.load_more_button.click()
        assert panel.load_more_button.isEnabled()

    @pytest.mark.parametrize("last_page", [[], _full_page(500)])
    def test_missing_next_link_disables_load_more(self, panel, last_page) -> None:
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            _full_page(1000), next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page(last_page)

        panel.refresh_pull_requests()
        panel.load_more_button.click()

        assert not panel.load_more_button.isEnabled()

    def test_multi_page_cursor_cycle_is_rejected_without_appending(self, panel) -> None:
        panel._pagination_responses[("o/r", "open", 2)] = _page(
            [_pull(900)], next_page=3
        )
        panel._pagination_responses[("o/r", "open", 3)] = _PullRequestPage(
            [_pull(800)],
            next_url=_cursor(2),
        )

        panel.refresh_pull_requests()
        panel.load_more_button.click()
        before_cycle = list(panel._pulls)
        panel.load_more_button.click()

        assert panel._pulls == before_cycle
        assert panel._next_pull_request_cursor == _cursor(3)
        assert panel.load_more_button.isEnabled()
        assert "循環" in panel.status_label.text()


class TestRequestSafety:
    def test_refresh_and_load_more_cannot_double_send_while_request_is_running(
        self, deferred_panel
    ) -> None:
        deferred_panel.refresh_pull_requests()
        deferred_panel.refresh_pull_requests()
        deferred_panel.load_more_pull_requests()

        assert len(deferred_panel._pagination_pending) == 1
        assert not deferred_panel.refresh_button.isEnabled()
        assert not deferred_panel.load_more_button.isEnabled()

        _resolve_next(deferred_panel)
        assert deferred_panel.refresh_button.isEnabled()
        assert deferred_panel.load_more_button.isEnabled()

    def test_failed_load_more_preserves_items_and_page_then_can_retry(
        self, panel
    ) -> None:
        panel.refresh_pull_requests()
        original = list(panel._pulls)
        panel._pagination_responses[("o/r", "open", 2)] = GitHubServiceError(
            "temporary failure"
        )

        panel.load_more_button.click()

        assert panel._pulls == original
        assert panel.load_more_button.isEnabled()
        assert "temporary failure" in panel.status_label.text()

        panel._pagination_responses[("o/r", "open", 2)] = [_pull(900)]
        panel.load_more_button.click()
        assert [call[3] for call in panel._pagination_calls] == [1, 2, 2]
        assert panel._pulls[-1]["number"] == 900

    def test_failed_refresh_preserves_accumulated_items_and_next_page(
        self, panel
    ) -> None:
        panel._pagination_responses[("o/r", "open", 2)] = _page(
            _full_page(950), next_page=3
        )
        panel._pagination_responses[("o/r", "open", 3)] = _page([_pull(850)])
        panel.refresh_pull_requests()
        panel.load_more_button.click()
        original = list(panel._pulls)
        panel._pagination_responses[("o/r", "open", 1)] = GitHubServiceError(
            "refresh failed"
        )

        panel.refresh_pull_requests()

        assert panel._pulls == original
        assert not panel.load_more_button.isEnabled()
        assert panel._next_pull_request_cursor is None
        assert [call[3] for call in panel._pagination_calls] == [1, 2, 1]

    def test_repo_change_discards_old_response_even_if_new_request_is_in_flight(
        self, deferred_panel
    ) -> None:
        deferred_panel.refresh_pull_requests()
        deferred_panel.set_repo("new/repo")
        deferred_panel.refresh_pull_requests()
        assert len(deferred_panel._pagination_pending) == 2

        _resolve_next(deferred_panel)
        assert deferred_panel._pulls == []
        assert not deferred_panel.refresh_button.isEnabled()

        _resolve_next(deferred_panel)
        assert [pr["number"] for pr in deferred_panel._pulls] == [77]
        assert deferred_panel.refresh_button.isEnabled()

    def test_state_change_discards_old_response(self, deferred_panel) -> None:
        deferred_panel.refresh_pull_requests()
        deferred_panel.state_combo.setCurrentIndex(
            deferred_panel.state_combo.findData("closed")
        )
        deferred_panel.refresh_pull_requests()
        assert len(deferred_panel._pagination_pending) == 2

        _resolve_next(deferred_panel)
        assert deferred_panel._pulls == []

        _resolve_next(deferred_panel)
        assert [pr["number"] for pr in deferred_panel._pulls] == [66]

    @pytest.mark.parametrize(
        "malformed",
        [
            {"unexpected": "shape"},
            [_pull(900), {"title": "missing number"}],
        ],
    )
    def test_malformed_page_preserves_existing_items_and_page_state(
        self, panel, malformed
    ) -> None:
        panel.refresh_pull_requests()
        original = list(panel._pulls)
        next_cursor = panel._next_pull_request_cursor
        panel._pagination_responses[("o/r", "open", 2)] = malformed

        panel.load_more_button.click()

        assert panel._pulls == original
        assert panel._next_pull_request_cursor == next_cursor
        assert panel.load_more_button.isEnabled()
        assert "解釈" in panel.status_label.text()

    def test_mutation_refresh_waits_for_inflight_page_then_reloads_page_one(
        self, deferred_panel
    ) -> None:
        deferred_panel.refresh_pull_requests()
        _resolve_next(deferred_panel)
        deferred_panel._pagination_responses[("o/r", "open", 2)] = [_pull(2)]
        deferred_panel._pagination_responses[("o/r", "open", 1)] = [
            _pull(77, "created")
        ]

        deferred_panel.load_more_pull_requests()
        deferred_panel._created_pr_number = 77
        deferred_panel._on_post_create_metadata(
            77,
            "o/r",
            {"warnings": [], "retry": None},
        )

        assert len(deferred_panel._pagination_pending) == 1
        _resolve_next(deferred_panel)
        assert deferred_panel._created_pr_number == 77
        assert deferred_panel._post_create_metadata_message
        assert len(deferred_panel._pagination_pending) == 1

        _resolve_next(deferred_panel)
        assert [pr["number"] for pr in deferred_panel._pulls] == [77]
        assert len(deferred_panel._pagination_pending) == 1
        _resolve_next(deferred_panel)
        assert deferred_panel._current is not None
        assert deferred_panel._current["number"] == 77
        assert deferred_panel._created_pr_number is None
        assert deferred_panel._post_create_metadata_message == ""

    def test_create_completion_queues_refresh_behind_inflight_page(
        self, deferred_panel, monkeypatch
    ) -> None:
        from hve.gui import github_pr_panel as module

        deferred_panel.refresh_pull_requests()
        _resolve_next(deferred_panel)
        deferred_panel._pagination_responses[("o/r", "open", 2)] = [_pull(2)]
        deferred_panel._pagination_responses[("o/r", "open", 1)] = [
            _pull(77, "created")
        ]
        monkeypatch.setattr(
            module.git_ops,
            "inspect_pull_request",
            lambda root, base: module.git_ops.PullRequestPreflight(
                "feature/new", base, 1, 1, True, 0, "o/r"
            ),
        )
        monkeypatch.setattr(
            module.github_service,
            "find_open_pull_request",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            module.github_service,
            "get_repository_metadata",
            lambda _repo: {"default_branch": "main"},
        )
        monkeypatch.setattr(
            module.github_service,
            "compare_commits",
            lambda *_args, **_kwargs: {"ahead_by": 1},
        )
        monkeypatch.setattr(
            module.github_service,
            "create_pull_request",
            lambda *_args, **_kwargs: {
                "number": 77,
                "html_url": "https://github.com/o/r/pull/77",
            },
        )

        deferred_panel.load_more_pull_requests()
        deferred_panel.create_title_edit.setText("Created")
        deferred_panel.create_pull_request()
        assert len(deferred_panel._pagination_pending) == 2

        task, on_ok, on_ng = deferred_panel._pagination_pending.pop(1)
        try:
            result = task()
        except (GitHubServiceError, module.git_ops.GitOpsError) as exc:
            (on_ng or deferred_panel._show_error)(str(exc))
        else:
            on_ok(result)

        assert deferred_panel._created_pr_number == 77
        assert len(deferred_panel._pagination_pending) == 1
        _resolve_next(deferred_panel)
        assert len(deferred_panel._pagination_pending) == 1
        _resolve_next(deferred_panel)
        assert [pr["number"] for pr in deferred_panel._pulls] == [77]
        assert deferred_panel._created_pr_number is None


class TestAccumulationAndExistingBehaviors:
    def test_append_deduplicates_by_number_and_keeps_first_occurrence(
        self, panel
    ) -> None:
        first_page = _full_page(1000)
        first_page[0] = _pull(42, "first")
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            first_page, next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page([
            _pull(42, "duplicate"),
            _pull(41, "new"),
        ])

        panel.refresh_pull_requests()
        panel.load_more_button.click()

        matches = [pr for pr in panel._pulls if pr["number"] == 42]
        assert [(pr["number"], pr["title"]) for pr in matches] == [(42, "first")]
        assert panel._pulls[-1]["number"] == 41

    def test_client_filter_is_reapplied_to_all_accumulated_pages(self, panel) -> None:
        first_page = _full_page(1000)
        first_page[0] = _pull(42, "needle first")
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            first_page, next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page([
            _pull(41, "needle second"),
            _pull(40, "other"),
        ])

        panel.refresh_pull_requests()
        panel.filter_edit.setText("needle")
        panel.load_more_button.click()

        assert [panel.pr_list.item(i).text() for i in range(panel.pr_list.count())] == [
            "#42 needle first",
            "#41 needle second",
        ]
        assert [call[3] for call in panel._pagination_calls] == [1, 2]

    def test_linked_selection_can_be_fulfilled_by_later_page(self, panel) -> None:
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            _full_page(1000), next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page(
            [_pull(41, "linked")]
        )
        panel.set_linked_pull_request(41)

        panel.load_once()
        assert panel.pr_list.currentRow() == -1
        panel.load_more_button.click()

        assert panel._current is not None
        assert panel._current["number"] == 41
        assert len(panel._pagination_calls) == 2

    def test_created_pull_request_refresh_still_selects_from_first_page(
        self, panel
    ) -> None:
        panel._pagination_responses[("o/r", "open", 1)] = [
            _pull(42, "created")
        ]
        panel._created_pr_number = 42

        panel.refresh_pull_requests()

        assert panel._current is not None
        assert panel._current["number"] == 42
        assert panel._created_pr_number is None
