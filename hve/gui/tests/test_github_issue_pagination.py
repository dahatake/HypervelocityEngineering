"""FR-GUI-48: Issue 一覧の明示ページング UI 契約。"""

from __future__ import annotations

import os
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from hve.gui.github_service import GitHubServiceError  # noqa: E402


PAGE_SIZE = 50


class _IssuePage(list[dict[str, Any]]):
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


def _issue(number: int, title: str | None = None) -> dict[str, Any]:
    return {
        "number": number,
        "title": title or f"Issue {number}",
        "state": "open",
        "user": {"login": "alice"},
        "labels": [],
        "assignees": [],
        "body": "",
        "html_url": f"https://github.com/o/r/issues/{number}",
    }


def _full_page(first_number: int) -> list[dict[str, Any]]:
    return [_issue(first_number - offset) for offset in range(PAGE_SIZE)]


def _cursor(page: int, repo: str = "o/r", state: str = "open") -> str:
    return (
        f"https://api.github.com/repos/{repo}/issues"
        f"?state={state}&sort=created&direction=desc&per_page={PAGE_SIZE}&page={page}"
    )


def _page(
    values: list[dict[str, Any]],
    *,
    next_page: int | None = None,
    repo: str = "o/r",
    state: str = "open",
) -> _IssuePage:
    return _IssuePage(
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


def _comment(comment_id: int, body: str) -> dict[str, Any]:
    return {
        "id": comment_id,
        "body": body,
        "created_at": "2026-08-26T00:00:00Z",
        "user": {"login": "alice"},
    }


def _install_safe_detail_stubs(monkeypatch, module) -> None:
    monkeypatch.setattr(
        module.github_service,
        "get_issue",
        lambda repo, number: _issue(int(number)),
    )
    monkeypatch.setattr(
        module.github_service,
        "list_comments",
        lambda repo, number: [],
    )
    monkeypatch.setattr(module.github_service, "current_user_login", lambda: "me")


@pytest.fixture
def panel(qapp, monkeypatch):
    from hve.gui import github_issue_panel as module

    responses: dict[tuple[str, str, int], Any] = {
        ("o/r", "open", 1): _page(_full_page(1000), next_page=2),
        ("o/r", "open", 2): _page([_issue(900, "second-page")]),
    }
    calls: list[tuple[str, str, int, int]] = []
    cursors: list[str | None] = []

    def _list_issues(
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

    monkeypatch.setattr(module.github_service, "list_issues", _list_issues)
    _install_safe_detail_stubs(monkeypatch, module)

    widget = module.GitHubIssuePanel()
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
    from hve.gui import github_issue_panel as module

    responses: dict[tuple[str, str, int], Any] = {
        ("o/r", "open", 1): _page(_full_page(1000), next_page=2),
        ("new/repo", "open", 1): _page([_issue(77, "new-repo")]),
        ("o/r", "closed", 1): _page([_issue(66, "closed-state")]),
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

    def _list_issues(
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

    monkeypatch.setattr(module.github_service, "list_issues", _list_issues)
    _install_safe_detail_stubs(monkeypatch, module)

    widget = module.GitHubIssuePanel()
    widget.set_repo("o/r")
    monkeypatch.setattr(
        widget,
        "_load_comments",
        lambda _number, _operation_epoch=None: None,
    )

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


@pytest.fixture
def deferred_comment_panel(qapp, monkeypatch):
    from hve.gui import github_issue_panel as module

    responses: dict[tuple[str, int], list[dict[str, Any]]] = {
        ("o/r", 1): [_comment(101, "old issue")],
        ("o/r", 2): [_comment(202, "current issue")],
        ("new/repo", 1): [_comment(303, "current repo")],
    }
    pending: list[
        tuple[
            Callable[[], Any],
            Callable[[Any], None],
            Callable[[str], None] | None,
        ]
    ] = []

    monkeypatch.setattr(
        module.github_service,
        "list_comments",
        lambda repo, number: list(responses[(repo, int(number))]),
    )

    widget = module.GitHubIssuePanel()
    widget.set_repo("o/r")
    widget._login = "me"

    def _defer(
        task: Callable[[], Any],
        on_ok: Callable[[Any], None],
        on_ng: Callable[[str], None] | None = None,
    ) -> None:
        pending.append((task, on_ok, on_ng))

    monkeypatch.setattr(widget, "_run", _defer)
    yield widget, pending
    pending.clear()
    widget.deleteLater()
    qapp.processEvents()


def _resolve_at(widget, index: int = 0) -> None:
    task, on_ok, on_ng = widget._pagination_pending.pop(index)
    try:
        result = task()
    except GitHubServiceError as exc:
        (on_ng or widget._show_error)(str(exc))
    else:
        on_ok(result)


def _resolve_pending(
    pending: list[
        tuple[
            Callable[[], Any],
            Callable[[Any], None],
            Callable[[str], None] | None,
        ]
    ],
    index: int = 0,
) -> None:
    task, on_ok, on_ng = pending.pop(index)
    try:
        result = task()
    except GitHubServiceError as exc:
        if on_ng is not None:
            on_ng(str(exc))
    else:
        on_ok(result)


def _load_issue_with_deferred_requests(widget, number: int) -> None:
    widget.refresh_issues()
    _resolve_at(widget)
    assert widget.select_issue(number)
    _resolve_at(widget)


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
        panel.refresh_issues()
        assert [call[3] for call in panel._pagination_calls] == [1]

        scrollbar = panel.issue_list.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        qapp.processEvents()
        qapp.processEvents()

        assert [call[3] for call in panel._pagination_calls] == [1]
        panel.load_more_button.click()
        assert [call[3] for call in panel._pagination_calls] == [1, 2]
        assert panel._pagination_cursors == [None, _cursor(2)]

    def test_uses_no_timer(self, panel) -> None:
        assert panel.findChildren(QTimer) == []


class TestRefreshAndLoadMore:
    def test_refresh_uses_page_one_replaces_items_and_resets_page_state(
        self, panel
    ) -> None:
        panel.refresh_issues()
        panel.load_more_button.click()
        assert any(issue["number"] == 900 for issue in panel._issues)

        panel._pagination_responses[("o/r", "open", 1)] = [_issue(7, "fresh")]
        panel.refresh_issues()

        assert panel._pagination_calls[-1] == ("o/r", "open", PAGE_SIZE, 1)
        assert [(issue["number"], issue["title"]) for issue in panel._issues] == [
            (7, "fresh")
        ]
        assert not panel.load_more_button.isEnabled()

    def test_load_more_passes_each_next_page_and_advances_after_success(
        self, panel
    ) -> None:
        panel._pagination_responses[("o/r", "open", 2)] = _page(
            _full_page(950), next_page=3
        )
        panel._pagination_responses[("o/r", "open", 3)] = _page([_issue(850)])

        panel.refresh_issues()
        panel.load_more_button.click()
        panel.load_more_button.click()

        assert [call[3] for call in panel._pagination_calls] == [1, 2, 3]
        assert len(panel._issues) == 101
        assert not panel.load_more_button.isEnabled()

    def test_next_link_keeps_load_more_enabled_regardless_of_page_size(
        self, panel
    ) -> None:
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            [_issue(1000)], next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page(
            [], next_page=3
        )

        panel.refresh_issues()
        assert panel.load_more_button.isEnabled()
        panel.load_more_button.click()
        assert panel.load_more_button.isEnabled()

    @pytest.mark.parametrize("last_page", [[], _full_page(500)])
    def test_missing_next_link_disables_load_more(self, panel, last_page) -> None:
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            _full_page(1000), next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page(last_page)

        panel.refresh_issues()
        panel.load_more_button.click()

        assert not panel.load_more_button.isEnabled()

    def test_multi_page_cursor_cycle_is_rejected_without_appending(self, panel) -> None:
        panel._pagination_responses[("o/r", "open", 2)] = _page(
            [_issue(900)], next_page=3
        )
        panel._pagination_responses[("o/r", "open", 3)] = _IssuePage(
            [_issue(800)],
            next_url=_cursor(2),
        )

        panel.refresh_issues()
        panel.load_more_button.click()
        before_cycle = list(panel._issues)
        panel.load_more_button.click()

        assert panel._issues == before_cycle
        assert panel._next_issue_cursor == _cursor(3)
        assert panel.load_more_button.isEnabled()
        assert "循環" in panel.status_label.text()


class TestRequestSafety:
    def test_refresh_and_load_more_cannot_double_send_while_request_is_running(
        self, deferred_panel
    ) -> None:
        deferred_panel.refresh_issues()
        deferred_panel.refresh_issues()
        deferred_panel.load_more_issues()

        assert len(deferred_panel._pagination_pending) == 1
        assert not deferred_panel.refresh_button.isEnabled()
        assert not deferred_panel.load_more_button.isEnabled()

        _resolve_at(deferred_panel)
        assert deferred_panel.refresh_button.isEnabled()
        assert deferred_panel.load_more_button.isEnabled()

    def test_failed_load_more_preserves_items_page_and_filter_then_can_retry(
        self, panel
    ) -> None:
        panel.refresh_issues()
        panel.filter_edit.setText("Issue")
        original = list(panel._issues)
        next_cursor = panel._next_issue_cursor
        panel._pagination_responses[("o/r", "open", 2)] = GitHubServiceError(
            "temporary failure"
        )

        panel.load_more_button.click()

        assert panel._issues == original
        assert panel._next_issue_cursor == next_cursor
        assert panel.filter_edit.text() == "Issue"
        assert panel.load_more_button.isEnabled()
        assert "temporary failure" in panel.status_label.text()

        panel._pagination_responses[("o/r", "open", 2)] = [_issue(900)]
        panel.load_more_button.click()
        assert [call[3] for call in panel._pagination_calls] == [1, 2, 2]
        assert panel._issues[-1]["number"] == 900

    def test_failed_refresh_preserves_accumulated_items_and_next_page(
        self, panel
    ) -> None:
        panel._pagination_responses[("o/r", "open", 2)] = _page(
            _full_page(950), next_page=3
        )
        panel._pagination_responses[("o/r", "open", 3)] = _page([_issue(850)])
        panel.refresh_issues()
        panel.load_more_button.click()
        panel.filter_edit.setText("Issue")
        original = list(panel._issues)
        panel._pagination_responses[("o/r", "open", 1)] = GitHubServiceError(
            "refresh failed"
        )

        panel.refresh_issues()

        assert panel._issues == original
        assert panel.filter_edit.text() == "Issue"
        assert not panel.load_more_button.isEnabled()
        assert panel._next_issue_cursor is None
        assert [call[3] for call in panel._pagination_calls] == [1, 2, 1]

    def test_repo_change_discards_old_response_even_if_new_request_is_in_flight(
        self, deferred_panel
    ) -> None:
        deferred_panel.refresh_issues()
        deferred_panel.set_repo("new/repo")
        deferred_panel.refresh_issues()
        assert len(deferred_panel._pagination_pending) == 2

        _resolve_at(deferred_panel)
        assert deferred_panel._issues == []
        assert not deferred_panel.refresh_button.isEnabled()

        _resolve_at(deferred_panel)
        assert [issue["number"] for issue in deferred_panel._issues] == [77]
        assert deferred_panel.refresh_button.isEnabled()

    def test_repo_change_discards_old_selection_intents_and_pending_refresh(
        self, deferred_panel
    ) -> None:
        deferred_panel._created_issue_number = 77
        deferred_panel._created_issue_warnings = ["old warning"]
        deferred_panel._linked_number = 77
        deferred_panel._pending_issue_refresh = ("o/r", "open")

        deferred_panel.set_repo("new/repo")

        assert deferred_panel._created_issue_number is None
        assert deferred_panel._created_issue_warnings == []
        assert deferred_panel._linked_number is None
        assert deferred_panel._pending_issue_refresh is None

        deferred_panel.refresh_issues()
        _resolve_at(deferred_panel)

        assert deferred_panel.issue_list.currentRow() == -1
        assert deferred_panel._current is None

    def test_state_change_discards_old_response(self, deferred_panel) -> None:
        deferred_panel.refresh_issues()
        deferred_panel.state_combo.setCurrentIndex(
            deferred_panel.state_combo.findData("closed")
        )
        deferred_panel.refresh_issues()
        assert len(deferred_panel._pagination_pending) == 2

        _resolve_at(deferred_panel)
        assert deferred_panel._issues == []

        _resolve_at(deferred_panel)
        assert [issue["number"] for issue in deferred_panel._issues] == [66]

    def test_load_more_does_not_invalidate_inflight_detail(
        self, deferred_panel
    ) -> None:
        deferred_panel.refresh_issues()
        _resolve_at(deferred_panel)
        assert deferred_panel.select_issue(999)

        deferred_panel.load_more_issues()
        _resolve_at(deferred_panel)
        _resolve_at(deferred_panel)

        assert deferred_panel._current is not None
        assert deferred_panel._current["number"] == 999
        assert deferred_panel.title_edit.text() == "Issue 999"

    def test_detail_selection_does_not_invalidate_inflight_load_more(
        self, deferred_panel
    ) -> None:
        deferred_panel.refresh_issues()
        _resolve_at(deferred_panel)
        deferred_panel._pagination_responses[("o/r", "open", 2)] = _page(
            [_issue(900, "second-page")]
        )

        deferred_panel.load_more_issues()
        assert deferred_panel.select_issue(999)
        _resolve_at(deferred_panel)

        assert any(issue["number"] == 900 for issue in deferred_panel._issues)
        assert "取得中" not in deferred_panel.status_label.text()

    def test_load_more_does_not_hide_successful_comment_completion(
        self, deferred_panel, monkeypatch
    ) -> None:
        from hve.gui import github_issue_panel as module

        _load_issue_with_deferred_requests(deferred_panel, 999)
        calls: list[tuple[str, int, str]] = []
        monkeypatch.setattr(
            module.github_service,
            "post_comment",
            lambda repo, number, body: calls.append((repo, number, body)),
        )
        deferred_panel.new_comment_edit.set_text("one comment")

        deferred_panel.post_comment()
        deferred_panel.load_more_issues()
        _resolve_at(deferred_panel)

        assert calls == [("o/r", 999, "one comment")]
        assert deferred_panel.new_comment_edit.text() == ""
        assert "コメントを投稿しました" in deferred_panel.status_label.text()

    @pytest.mark.parametrize(
        "malformed",
        [
            {"unexpected": "shape"},
            [_issue(900), "not-an-issue"],
        ],
    )
    def test_malformed_page_fails_closed_before_state_change(
        self, panel, malformed
    ) -> None:
        panel.refresh_issues()
        panel.filter_edit.setText("Issue")
        original = list(panel._issues)
        next_cursor = panel._next_issue_cursor
        panel._pagination_responses[("o/r", "open", 2)] = malformed

        panel.load_more_button.click()

        assert panel._issues == original
        assert panel._next_issue_cursor == next_cursor
        assert panel.filter_edit.text() == "Issue"
        assert panel.load_more_button.isEnabled()
        assert "解釈" in panel.status_label.text()

    def test_worker_start_failure_recovers_list_controls(
        self, qapp, monkeypatch
    ) -> None:
        from hve.gui import github_issue_panel as module

        widget = module.GitHubIssuePanel()
        widget.set_repo("o/r")

        def _fail_start(_worker, *_args, **_kwargs):
            raise RuntimeError("thread unavailable")

        monkeypatch.setattr(module.GitHubWorker, "start", _fail_start)
        try:
            widget.refresh_issues()
            assert not widget._list_request_in_flight
            assert widget.refresh_button.isEnabled()
            assert "起動" in widget.status_label.text()
        finally:
            widget.deleteLater()
            qapp.processEvents()

    def test_create_completion_queues_page_one_behind_inflight_append(
        self, deferred_panel, monkeypatch
    ) -> None:
        from hve.gui import github_issue_panel as module

        deferred_panel.refresh_issues()
        _resolve_at(deferred_panel)
        deferred_panel._pagination_responses[("o/r", "open", 2)] = [_issue(2)]
        deferred_panel._pagination_responses[("o/r", "open", 1)] = [
            _issue(77, "created")
        ]
        monkeypatch.setattr(
            module.github_service,
            "create_issue_details",
            lambda *_args, **_kwargs: {
                "number": 77,
                "id": 7700,
                "warnings": [],
            },
        )

        deferred_panel.load_more_issues()
        deferred_panel.create_title_edit.setText("Created")
        deferred_panel.create_body_edit.set_text("Body")
        deferred_panel.create_issue()
        assert len(deferred_panel._pagination_pending) == 2

        _resolve_at(deferred_panel, 1)

        assert deferred_panel._created_issue_number == 77
        assert len(deferred_panel._pagination_pending) == 1

        _resolve_at(deferred_panel)

        assert deferred_panel._created_issue_number == 77
        assert len(deferred_panel._pagination_pending) == 1
        assert deferred_panel._pagination_calls[-1][3] == 2

        _resolve_at(deferred_panel)

        assert [issue["number"] for issue in deferred_panel._issues] == [77]
        assert deferred_panel._created_issue_number is None
        assert deferred_panel._pagination_calls[-1][3] == 1
        assert len(deferred_panel._pagination_pending) == 1

        _resolve_at(deferred_panel)
        assert deferred_panel._current is not None
        assert deferred_panel._current["number"] == 77


class TestAccumulationAndExistingBehaviors:
    def test_append_deduplicates_by_number_and_keeps_first_occurrence(
        self, panel
    ) -> None:
        first_page = _full_page(1000)
        first_page[0] = _issue(42, "first")
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            first_page, next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page([
            _issue(42, "duplicate"),
            _issue(41, "new"),
        ])

        panel.refresh_issues()
        panel.load_more_button.click()

        matches = [issue for issue in panel._issues if issue["number"] == 42]
        assert [(issue["number"], issue["title"]) for issue in matches] == [
            (42, "first")
        ]
        assert panel._issues[-1]["number"] == 41

    def test_client_filter_is_reapplied_to_all_accumulated_pages(self, panel) -> None:
        first_page = _full_page(1000)
        first_page[0] = _issue(42, "needle first")
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            first_page, next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page([
            _issue(41, "needle second"),
            _issue(40, "other"),
        ])

        panel.refresh_issues()
        panel.filter_edit.setText("needle")
        panel.load_more_button.click()

        assert [
            panel.issue_list.item(i).text() for i in range(panel.issue_list.count())
        ] == [
            "#42 needle first",
            "#41 needle second",
        ]
        assert [call[3] for call in panel._pagination_calls] == [1, 2]

    def test_append_preserves_selected_issue_and_unsaved_editor_state(
        self, panel
    ) -> None:
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            _full_page(1000), next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page([
            _issue(900, "second page")
        ])
        panel.refresh_issues()
        assert panel.select_issue(999)
        panel.title_edit.setText("unsaved title")
        panel.body_edit.set_text("unsaved body")

        panel.load_more_button.click()

        selected_row = panel.issue_list.currentRow()
        assert panel._visible[selected_row]["number"] == 999
        assert panel._current is not None
        assert panel._current["number"] == 999
        assert panel.title_edit.text() == "unsaved title"
        assert panel.body_edit.text() == "unsaved body"
        assert panel.save_button.isEnabled()

    def test_filter_preserves_selection_when_selected_issue_remains_visible(
        self, panel
    ) -> None:
        panel.refresh_issues()
        assert panel.select_issue(1000)
        panel.title_edit.setText("unsaved title")
        panel.body_edit.set_text("unsaved body")

        panel.filter_edit.setText("1000")

        selected_row = panel.issue_list.currentRow()
        assert panel._visible[selected_row]["number"] == 1000
        assert panel._current is not None
        assert panel._current["number"] == 1000
        assert panel.title_edit.text() == "unsaved title"
        assert panel.body_edit.text() == "unsaved body"

    def test_filter_clears_detail_only_when_selected_issue_disappears(
        self, panel
    ) -> None:
        panel.refresh_issues()
        assert panel.select_issue(1000)
        panel.title_edit.setText("unsaved title")
        panel.body_edit.set_text("unsaved body")

        panel.filter_edit.setText("not-visible")

        assert panel.issue_list.currentRow() == -1
        assert panel._current is None
        assert panel.title_edit.text() == ""
        assert panel.body_edit.text() == ""
        assert panel.meta_label.text() == ""
        assert panel.url_label.text() == ""
        assert panel.comment_list.count() == 0
        assert not panel.save_button.isEnabled()

    def test_linked_selection_can_be_fulfilled_by_later_page(self, panel) -> None:
        panel._pagination_responses[("o/r", "open", 1)] = _page(
            _full_page(1000), next_page=2
        )
        panel._pagination_responses[("o/r", "open", 2)] = _page([
            _issue(41, "linked")
        ])
        panel.set_linked_issue(41)

        panel.load_once()
        assert panel.issue_list.currentRow() == -1
        panel.load_more_button.click()

        assert panel._current is not None
        assert panel._current["number"] == 41
        assert len(panel._pagination_calls) == 2

    def test_created_issue_refresh_still_selects_from_first_page(self, panel) -> None:
        panel._pagination_responses[("o/r", "open", 1)] = [
            _issue(42, "created")
        ]
        panel._created_issue_number = 42

        panel.refresh_issues()

        assert panel._current is not None
        assert panel._current["number"] == 42
        assert panel._created_issue_number is None

    def test_load_once_still_fetches_only_once_for_same_repo(self, panel) -> None:
        panel.load_once()
        panel.load_once()

        assert [call[3] for call in panel._pagination_calls] == [1]


class TestCommentRequestSafety:
    def test_discards_comments_from_previously_selected_issue(
        self, deferred_comment_panel
    ) -> None:
        panel, pending = deferred_comment_panel
        panel._issue_load_generation = 10
        panel._current = _issue(1)
        panel._load_comments(1)

        panel._issue_load_generation += 1
        panel._current = _issue(2)
        panel._load_comments(2)

        _resolve_pending(pending)
        assert panel._comments == []
        assert panel.comment_list.count() == 0

        _resolve_pending(pending)
        assert [comment["id"] for comment in panel._comments] == [202]
        assert panel.comment_list.item(0).text().endswith("current issue")

    def test_discards_comments_from_previous_repository(
        self, deferred_comment_panel
    ) -> None:
        panel, pending = deferred_comment_panel
        panel._issue_load_generation = 20
        panel._current = _issue(1)
        panel._load_comments(1)

        panel.set_repo("new/repo")
        panel._current = _issue(1)
        panel._load_comments(1)

        _resolve_pending(pending)
        assert panel._comments == []
        assert panel.comment_list.count() == 0

        _resolve_pending(pending)
        assert [comment["id"] for comment in panel._comments] == [303]
        assert panel.comment_list.item(0).text().endswith("current repo")
