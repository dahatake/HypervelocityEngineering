"""FR-GUI-45: Pull Request review 一覧表示と提出 UI 契約。"""

from __future__ import annotations

import os
from typing import Any, Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QGroupBox  # noqa: E402

from hve.gui.github_comment_editor import GitHubCommentEditor  # noqa: E402
from hve.gui.github_service import GitHubServiceError  # noqa: E402


_PULLS = [
    {
        "number": 42,
        "title": "review target",
        "state": "open",
        "user": {"login": "alice"},
        "head": {"ref": "feature/review", "repo": {"full_name": "o/r"}},
        "base": {"ref": "main"},
        "body": "PR body",
        "html_url": "https://github.com/o/r/pull/42",
    },
    {
        "number": 41,
        "title": "other target",
        "state": "open",
        "user": {"login": "bob"},
        "head": {"ref": "feature/other", "repo": {"full_name": "o/r"}},
        "base": {"ref": "main"},
        "body": "Other body",
        "html_url": "https://github.com/o/r/pull/41",
    },
]

_REVIEWS = [
    {
        "id": 11,
        "user": {"login": "z-last-by-time"},
        "state": "COMMENTED",
        "submitted_at": "2026-08-26T02:00:00Z",
        "body": "先頭コメント\n表示しない 2 行目",
    },
    {
        "id": 10,
        "user": {"login": "a-first-by-time"},
        "state": "APPROVED",
        "submitted_at": "2026-08-26T01:00:00Z",
        "body": "LGTM",
    },
]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _copy_pulls() -> list[dict[str, Any]]:
    return [dict(pull) for pull in _PULLS]


def _copy_reviews(reviews: list[Any]) -> list[Any]:
    copied: list[Any] = []
    for review in reviews:
        if not isinstance(review, dict):
            copied.append(review)
            continue
        item = dict(review)
        if isinstance(review.get("user"), dict):
            item["user"] = dict(review["user"])
        copied.append(item)
    return copied


def _install_service_fakes(monkeypatch, module):
    calls: dict[str, list[Any]] = {
        "list_pull_requests": [],
        "get_pull_request": [],
        "list_comments": [],
        "list_pull_request_reviews": [],
        "create_pull_request_review": [],
    }
    state: dict[str, Any] = {
        "review_result": _copy_reviews(_REVIEWS),
        "create_result": {"id": 99, "state": "APPROVED"},
    }

    def _list_pull_requests(
        repo: str,
        state_name: str = "open",
        per_page: int = 50,
        page: int = 1,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        actual_state = kwargs.get("state", state_name)
        calls["list_pull_requests"].append((repo, actual_state, per_page, page))
        return _copy_pulls()

    def _get_pull_request(repo: str, number: Any) -> dict[str, Any]:
        calls["get_pull_request"].append((repo, int(number)))
        return dict(next(pull for pull in _PULLS if pull["number"] == int(number)))

    def _list_comments(repo: str, number: Any) -> list[dict[str, Any]]:
        calls["list_comments"].append((repo, int(number)))
        return [
            {
                "id": 7,
                "user": {"login": "conversation-user"},
                "created_at": "2026-08-26T00:00:00Z",
                "body": "conversation comment",
            }
        ]

    def _list_reviews(repo: str, number: Any, per_page: int = 100) -> Any:
        calls["list_pull_request_reviews"].append((repo, int(number), per_page))
        result = state["review_result"]
        if isinstance(result, Exception):
            raise result
        return _copy_reviews(result) if isinstance(result, list) else result

    def _create_review(
        repo: str,
        number: Any,
        event: str,
        body: str | None = None,
    ) -> Any:
        calls["create_pull_request_review"].append(
            (repo, int(number), event, body)
        )
        result = state["create_result"]
        if isinstance(result, Exception):
            raise result
        return dict(result) if isinstance(result, dict) else result

    monkeypatch.setattr(module.github_service, "list_pull_requests", _list_pull_requests)
    monkeypatch.setattr(module.github_service, "get_pull_request", _get_pull_request)
    monkeypatch.setattr(
        module.github_service,
        "list_pull_request_files",
        lambda repo, number: [],
    )
    monkeypatch.setattr(module.github_service, "list_comments", _list_comments)
    monkeypatch.setattr(
        module.github_service,
        "list_pull_request_reviews",
        _list_reviews,
    )
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request_review",
        _create_review,
    )
    return calls, state


@pytest.fixture
def panel(qapp, monkeypatch):
    from hve.gui import github_pr_panel as module

    calls, state = _install_service_fakes(monkeypatch, module)
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
    widget._review_calls = calls  # type: ignore[attr-defined]
    widget._review_state = state  # type: ignore[attr-defined]
    return widget


@pytest.fixture
def deferred_panel(qapp, monkeypatch):
    from hve.gui import github_pr_panel as module

    calls, state = _install_service_fakes(monkeypatch, module)
    pending: list[
        tuple[
            Callable[[], Any],
            Callable[[Any], None],
            Callable[[str], None] | None,
        ]
    ] = []
    widget = module.GitHubPullRequestPanel()
    widget.set_repo("o/r")

    def _defer(
        task: Callable[[], Any],
        on_ok: Callable[[Any], None],
        on_ng: Callable[[str], None] | None = None,
    ) -> None:
        pending.append((task, on_ok, on_ng))

    monkeypatch.setattr(widget, "_run", _defer)
    widget._review_calls = calls  # type: ignore[attr-defined]
    widget._review_state = state  # type: ignore[attr-defined]
    widget._review_pending = pending  # type: ignore[attr-defined]
    widget._review_module = module  # type: ignore[attr-defined]
    return widget


def _select(panel, row: int = 0) -> None:
    panel.refresh_pull_requests()
    panel.pr_list.setCurrentRow(row)


def _texts(list_widget) -> list[str]:
    return [list_widget.item(i).text() for i in range(list_widget.count())]


def _take_pending(widget, target: Callable[..., Any]):
    for index, entry in enumerate(widget._review_pending):
        task = entry[0]
        if getattr(task, "func", None) is target:
            return widget._review_pending.pop(index)
    pytest.fail(f"pending task not found: {target.__name__}")


def _resolve(entry) -> Any:
    task, on_ok, on_ng = entry
    try:
        result = task()
    except GitHubServiceError as exc:
        (on_ng or pytest.fail)(str(exc))
        return None
    on_ok(result)
    return result


def _load_deferred_selection(widget, row: int = 0) -> None:
    module = widget._review_module
    widget.refresh_pull_requests()
    _resolve(_take_pending(widget, module.github_service.list_pull_requests))
    widget.pr_list.setCurrentRow(row)
    _resolve(_take_pending(widget, module.github_service.get_pull_request))
    _resolve(_take_pending(widget, module.github_service.list_pull_request_reviews))


class TestReviewSurface:
    def test_review_is_a_separate_group_from_conversation_comments(self, panel) -> None:
        groups = {group.title(): group for group in panel.findChildren(QGroupBox)}
        assert groups["レビュー"] is panel.review_group
        assert groups["コメント"] is not panel.review_group
        assert panel.review_list is not panel.comment_list

    def test_reuses_comment_editor_and_offers_only_three_events(self, panel) -> None:
        assert isinstance(panel.review_body_edit, GitHubCommentEditor)
        assert [
            panel.review_event_combo.itemData(i)
            for i in range(panel.review_event_combo.count())
        ] == ["APPROVE", "REQUEST_CHANGES", "COMMENT"]

    def test_detail_load_fetches_reviews_once_and_never_polls(
        self, panel, qapp
    ) -> None:
        _select(panel)
        assert panel._review_calls["list_pull_request_reviews"] == [
            ("o/r", 42, 100)
        ]

        qapp.processEvents()
        qapp.processEvents()
        assert len(panel._review_calls["list_pull_request_reviews"]) == 1

        panel.refresh_reviews_button.click()
        assert len(panel._review_calls["list_pull_request_reviews"]) == 2

    def test_keeps_api_order_and_displays_required_review_fields(self, panel) -> None:
        _select(panel)
        rows = _texts(panel.review_list)
        assert "z-last-by-time" in rows[0]
        assert "COMMENTED" in rows[0]
        assert "2026-08-26T02:00:00Z" in rows[0]
        assert "先頭コメント" in rows[0]
        assert "表示しない 2 行目" not in rows[0]
        assert "a-first-by-time" in rows[1]
        assert "conversation-user" not in "\n".join(rows)
        assert "conversation-user" in panel.comment_list.item(0).text()


class TestReviewValidationAndResultHandling:
    @pytest.mark.parametrize("event", ["REQUEST_CHANGES", "COMMENT"])
    def test_body_required_events_reject_trimmed_empty_before_api(
        self, panel, event: str
    ) -> None:
        _select(panel)
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData(event)
        )
        panel.review_body_edit.set_text(" \n\t ")

        panel.submit_review()

        assert panel._review_calls["create_pull_request_review"] == []
        assert panel.review_body_edit.text() == " \n\t "
        assert panel.review_event_combo.currentData() == event
        assert panel.submit_review_button.isEnabled()

    def test_approve_allows_empty_body_and_refreshes_list_once(self, panel) -> None:
        _select(panel)
        before = len(panel._review_calls["list_pull_request_reviews"])
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("APPROVE")
        )
        panel.review_body_edit.clear()

        panel.submit_review()

        assert panel._review_calls["create_pull_request_review"] == [
            ("o/r", 42, "APPROVE", "")
        ]
        assert len(panel._review_calls["list_pull_request_reviews"]) == before + 1
        assert panel.review_body_edit.text() == ""

    def test_unknown_event_fails_closed_before_api(self, panel) -> None:
        _select(panel)
        panel.review_event_combo.addItem("INVALID", "INVALID")
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("INVALID")
        )
        panel.review_body_edit.set_text("must stay")

        panel.submit_review()

        assert panel._review_calls["create_pull_request_review"] == []
        assert panel.review_body_edit.text() == "must stay"
        assert panel.review_event_combo.currentData() == "INVALID"

    def test_submit_failure_preserves_body_event_list_and_current_pr(self, panel) -> None:
        _select(panel)
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("COMMENT")
        )
        body = "\n## Review\n\nKeep markdown.\n"
        panel.review_body_edit.set_text(body)
        rows = _texts(panel.review_list)
        current = panel._current
        panel._review_state["create_result"] = GitHubServiceError("review failed")

        panel.submit_review()

        assert panel.review_body_edit.text() == body
        assert panel.review_event_combo.currentData() == "COMMENT"
        assert _texts(panel.review_list) == rows
        assert panel._current is current
        assert panel.submit_review_button.isEnabled()
        assert "review failed" in panel.status_label.text()

    @pytest.mark.parametrize(
        "result",
        [["unexpected"], {}, {"id": "not-a-number"}],
    )
    def test_malformed_submit_result_is_failure_and_preserves_input(
        self, panel, result: Any
    ) -> None:
        _select(panel)
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("COMMENT")
        )
        panel.review_body_edit.set_text("keep")
        panel._review_state["create_result"] = result
        before = len(panel._review_calls["list_pull_request_reviews"])

        panel.submit_review()

        assert panel.review_body_edit.text() == "keep"
        assert panel.review_event_combo.currentData() == "COMMENT"
        assert len(panel._review_calls["list_pull_request_reviews"]) == before
        assert panel.submit_review_button.isEnabled()
        assert "解釈" in panel.status_label.text()

    def test_malformed_review_list_preserves_previous_rows_and_reenables(self, panel) -> None:
        _select(panel)
        rows = _texts(panel.review_list)
        current = panel._current
        panel.review_body_edit.set_text("draft")
        panel._review_state["review_result"] = [
            {
                "user": None,
                "state": "APPROVED",
                "submitted_at": "2026-08-26T03:00:00Z",
                "body": "bad",
            }
        ]

        panel.refresh_reviews_button.click()

        assert _texts(panel.review_list) == rows
        assert panel._current is current
        assert panel.review_body_edit.text() == "draft"
        assert panel.refresh_reviews_button.isEnabled()
        assert "解釈" in panel.status_label.text()

    @pytest.mark.parametrize(
        "review_result",
        [
            {"unexpected": "object"},
            GitHubServiceError("review refresh failed"),
        ],
    )
    def test_submit_success_with_refresh_failure_is_partial_success(
        self, panel, review_result: Any
    ) -> None:
        _select(panel)
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("APPROVE")
        )
        panel.review_body_edit.set_text("clear after accepted submit")
        panel._review_state["review_result"] = review_result

        panel.submit_review()

        assert panel._review_calls["create_pull_request_review"] == [
            ("o/r", 42, "APPROVE", "clear after accepted submit")
        ]
        assert panel.review_body_edit.text() == ""
        assert "提出済み" in panel.status_label.text()
        assert "一覧" in panel.status_label.text()
        assert "失敗" in panel.status_label.text()


class TestReviewContextBindingAndReset:
    def test_switching_pull_request_clears_bound_draft_and_event(self, panel) -> None:
        _select(panel)
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("COMMENT")
        )
        panel.review_body_edit.set_text("draft for #42 only")

        panel.pr_list.setCurrentRow(1)

        assert panel._current["number"] == 41
        assert panel.review_body_edit.text() == ""
        assert panel.review_event_combo.currentData() == "APPROVE"
        assert "draft for #42 only" not in str(
            panel._review_calls["create_pull_request_review"]
        )

    def test_same_pull_request_new_generation_clears_bound_draft(self, panel) -> None:
        _select(panel)
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("REQUEST_CHANGES")
        )
        panel.review_body_edit.set_text("old generation")

        panel.pr_list.setCurrentRow(-1)
        panel.pr_list.setCurrentRow(0)

        assert panel._current["number"] == 42
        assert panel.review_body_edit.text() == ""
        assert panel.review_event_combo.currentData() == "APPROVE"

    def test_set_repo_completely_clears_old_pull_request_context(self, panel) -> None:
        _select(panel)
        panel.file_list.addItem("old-file.py [modified]")
        panel.new_comment_edit.set_text("old conversation draft")
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("COMMENT")
        )
        panel.review_body_edit.set_text("old review draft")

        panel.set_repo("new/repo")

        assert panel._current is None
        assert panel._pulls == []
        assert panel._visible == []
        assert panel.pr_list.count() == 0
        assert panel.meta_label.text() == ""
        assert panel.url_label.text() == ""
        assert panel.body_view.toPlainText() == ""
        assert panel.file_list.count() == 0
        assert panel.comment_list.count() == 0
        assert panel.review_list.count() == 0
        assert panel.new_comment_edit.text() == ""
        assert panel.review_body_edit.text() == ""
        assert panel.review_event_combo.currentData() == "APPROVE"
        for widget in (
            panel.body_view,
            panel.file_list,
            panel.comment_list,
            panel.review_list,
            panel.new_comment_edit,
            panel.post_comment_button,
            panel.review_event_combo,
            panel.review_body_edit,
            panel.refresh_reviews_button,
            panel.submit_review_button,
        ):
            assert not widget.isEnabled()


class TestDetailCollectionStaleSafety:
    @pytest.mark.parametrize(
        ("service_name", "widget_name", "payload", "marker"),
        [
            (
                "list_pull_request_files",
                "file_list",
                [{"filename": "stale.py", "status": "modified"}],
                "stale.py",
            ),
            (
                "list_comments",
                "comment_list",
                [
                    {
                        "user": {"login": "stale-user"},
                        "created_at": "2026-08-26T03:00:00Z",
                        "body": "stale comment",
                    }
                ],
                "stale-user",
            ),
        ],
    )
    @pytest.mark.parametrize("context_change", ["repo", "number", "generation"])
    def test_old_response_cannot_populate_new_context(
        self,
        deferred_panel,
        service_name: str,
        widget_name: str,
        payload: list[dict[str, Any]],
        marker: str,
        context_change: str,
    ) -> None:
        module = deferred_panel._review_module
        deferred_panel.refresh_pull_requests()
        _resolve(
            _take_pending(
                deferred_panel, module.github_service.list_pull_requests
            )
        )
        deferred_panel.pr_list.setCurrentRow(0)
        _resolve(
            _take_pending(deferred_panel, module.github_service.get_pull_request)
        )
        old_response = _take_pending(
            deferred_panel, getattr(module.github_service, service_name)
        )

        if context_change == "repo":
            deferred_panel.set_repo("new/repo")
        elif context_change == "number":
            deferred_panel.pr_list.setCurrentRow(1)
            _resolve(
                _take_pending(
                    deferred_panel, module.github_service.get_pull_request
                )
            )
        else:
            deferred_panel.pr_list.setCurrentRow(-1)
            deferred_panel.pr_list.setCurrentRow(0)
            _resolve(
                _take_pending(
                    deferred_panel, module.github_service.get_pull_request
                )
            )

        old_response[1](payload)

        assert marker not in "\n".join(
            _texts(getattr(deferred_panel, widget_name))
        )


class TestReviewWorkerAndStaleSafety:
    def test_submit_busy_queues_refresh_and_ignores_load_more(
        self, deferred_panel
    ) -> None:
        module = deferred_panel._review_module
        _load_deferred_selection(deferred_panel)
        deferred_panel.review_event_combo.setCurrentIndex(
            deferred_panel.review_event_combo.findData("COMMENT")
        )
        deferred_panel.review_body_edit.set_text("pending review")
        deferred_panel._pull_requests_have_more = True

        deferred_panel.submit_review()
        submit = _take_pending(
            deferred_panel, module.github_service.create_pull_request_review
        )
        pending_before = len(deferred_panel._review_pending)
        deferred_panel.refresh_pull_requests()
        deferred_panel.load_more_pull_requests()

        assert len(deferred_panel._review_pending) == pending_before
        assert deferred_panel._pending_pull_request_refresh == ("o/r", "open")

        _resolve(submit)
        review_refresh = _take_pending(
            deferred_panel, module.github_service.list_pull_request_reviews
        )
        _resolve(review_refresh)
        assert any(
            getattr(entry[0], "func", None)
            is module.github_service.list_pull_requests
            for entry in deferred_panel._review_pending
        )

    def test_submit_busy_blocks_other_pr_mutations(self, deferred_panel) -> None:
        module = deferred_panel._review_module
        _load_deferred_selection(deferred_panel)
        deferred_panel.review_event_combo.setCurrentIndex(
            deferred_panel.review_event_combo.findData("COMMENT")
        )
        deferred_panel.review_body_edit.set_text("pending review")
        deferred_panel.new_comment_edit.set_text("must stay local")

        deferred_panel.submit_review()
        submit = _take_pending(
            deferred_panel, module.github_service.create_pull_request_review
        )
        pending_before = len(deferred_panel._review_pending)
        deferred_panel.post_comment()
        deferred_panel.post_console_log()
        deferred_panel.push_current_branch()

        assert len(deferred_panel._review_pending) == pending_before
        assert not deferred_panel.post_comment_button.isEnabled()
        assert not deferred_panel.push_button.isEnabled()
        assert deferred_panel.new_comment_edit.text() == "must stay local"

        assert submit[2] is not None
        submit[2]("review stopped")
        assert deferred_panel.post_comment_button.isEnabled()

    def test_append_and_filter_preserve_selected_review_draft(self, panel) -> None:
        _select(panel)
        current = panel._current
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("REQUEST_CHANGES")
        )
        panel.review_body_edit.set_text("bound draft")

        panel._on_pull_requests_loaded(
            [
                {
                    "number": 40,
                    "title": "later page",
                    "state": "open",
                    "head": {"ref": "feature/later"},
                    "base": {"ref": "main"},
                }
            ],
            append=True,
        )
        panel.filter_edit.setText("review target")

        assert panel._current is current
        assert panel._current["number"] == 42
        assert panel.pr_list.currentRow() == 0
        assert panel.review_event_combo.currentData() == "REQUEST_CHANGES"
        assert panel.review_body_edit.text() == "bound draft"

    def test_list_request_blocks_submit_and_preserves_bound_draft(
        self, deferred_panel
    ) -> None:
        module = deferred_panel._review_module
        _load_deferred_selection(deferred_panel)
        deferred_panel.review_event_combo.setCurrentIndex(
            deferred_panel.review_event_combo.findData("COMMENT")
        )
        deferred_panel.review_body_edit.set_text("must survive list refresh")

        deferred_panel.refresh_pull_requests()
        list_request = _take_pending(
            deferred_panel, module.github_service.list_pull_requests
        )
        deferred_panel.submit_review()

        assert not any(
            getattr(entry[0], "func", None)
            is module.github_service.create_pull_request_review
            for entry in deferred_panel._review_pending
        )
        assert not deferred_panel.submit_review_button.isEnabled()

        _resolve(list_request)

        assert deferred_panel._current is not None
        assert deferred_panel._current["number"] == 42
        assert deferred_panel.review_event_combo.currentData() == "COMMENT"
        assert deferred_panel.review_body_edit.text() == "must survive list refresh"

    def test_explicit_refresh_uses_worker_seam_and_blocks_double_request(
        self, panel, monkeypatch
    ) -> None:
        _select(panel)
        pending = []

        def _defer(task, on_ok, on_ng=None):
            pending.append((task, on_ok, on_ng))

        monkeypatch.setattr(panel, "_run", _defer)
        before = len(panel._review_calls["list_pull_request_reviews"])

        panel.refresh_pull_request_reviews()
        panel.refresh_pull_request_reviews()

        assert len(panel._review_calls["list_pull_request_reviews"]) == before
        assert len(pending) == 1
        assert not panel.refresh_reviews_button.isEnabled()

        _resolve(pending.pop(0))
        assert len(panel._review_calls["list_pull_request_reviews"]) == before + 1
        assert panel.refresh_reviews_button.isEnabled()

    def test_submit_uses_worker_seam_and_blocks_double_send(
        self, panel, monkeypatch
    ) -> None:
        _select(panel)
        pending = []

        def _defer(task, on_ok, on_ng=None):
            pending.append((task, on_ok, on_ng))

        monkeypatch.setattr(panel, "_run", _defer)
        panel.review_event_combo.setCurrentIndex(
            panel.review_event_combo.findData("COMMENT")
        )
        panel.review_body_edit.set_text("ship it")

        panel.submit_review()
        panel.submit_review()

        assert panel._review_calls["create_pull_request_review"] == []
        assert len(pending) == 1
        assert not panel.submit_review_button.isEnabled()
        for widget in (
            panel.pr_list,
            panel.filter_edit,
            panel.state_combo,
            panel.refresh_button,
            panel.load_more_button,
        ):
            assert not widget.isEnabled()

        _resolve(pending.pop(0))
        assert panel._review_calls["create_pull_request_review"] == [
            ("o/r", 42, "COMMENT", "ship it")
        ]
        assert panel.review_body_edit.text() == ""
        assert len(pending) == 1  # 成功後の review 一覧再取得だけ
        assert not panel.submit_review_button.isEnabled()

        _resolve(pending.pop(0))
        assert panel.submit_review_button.isEnabled()

    def test_repo_stale_review_response_is_discarded(self, deferred_panel) -> None:
        module = deferred_panel._review_module
        deferred_panel.refresh_pull_requests()
        _resolve(
            _take_pending(
                deferred_panel, module.github_service.list_pull_requests
            )
        )
        deferred_panel.pr_list.setCurrentRow(0)
        _resolve(
            _take_pending(deferred_panel, module.github_service.get_pull_request)
        )
        old_review = _take_pending(
            deferred_panel, module.github_service.list_pull_request_reviews
        )
        old_result = old_review[0]()

        deferred_panel.set_repo("new/repo")
        old_review[1](old_result)

        assert deferred_panel.review_list.count() == 0

    def test_pr_stale_review_response_is_discarded(self, deferred_panel) -> None:
        module = deferred_panel._review_module
        deferred_panel.refresh_pull_requests()
        _resolve(
            _take_pending(
                deferred_panel, module.github_service.list_pull_requests
            )
        )
        deferred_panel.pr_list.setCurrentRow(0)
        _resolve(
            _take_pending(deferred_panel, module.github_service.get_pull_request)
        )
        old_review = _take_pending(
            deferred_panel, module.github_service.list_pull_request_reviews
        )
        old_result = old_review[0]()

        deferred_panel.pr_list.setCurrentRow(1)
        _resolve(
            _take_pending(deferred_panel, module.github_service.get_pull_request)
        )
        new_review = _take_pending(
            deferred_panel, module.github_service.list_pull_request_reviews
        )
        new_result = new_review[0]()

        old_review[1](old_result)
        assert deferred_panel.review_list.count() == 0
        new_review[1](new_result)
        assert deferred_panel.review_list.count() == 2
        assert deferred_panel._current["number"] == 41

    def test_same_number_new_generation_discards_older_response(
        self, deferred_panel
    ) -> None:
        module = deferred_panel._review_module
        deferred_panel.refresh_pull_requests()
        _resolve(
            _take_pending(
                deferred_panel, module.github_service.list_pull_requests
            )
        )
        deferred_panel.pr_list.setCurrentRow(0)
        _resolve(
            _take_pending(deferred_panel, module.github_service.get_pull_request)
        )
        old_review = _take_pending(
            deferred_panel, module.github_service.list_pull_request_reviews
        )
        old_result = old_review[0]()

        deferred_panel.pr_list.setCurrentRow(-1)
        deferred_panel.pr_list.setCurrentRow(0)
        _resolve(
            _take_pending(deferred_panel, module.github_service.get_pull_request)
        )
        new_review = _take_pending(
            deferred_panel, module.github_service.list_pull_request_reviews
        )
        new_result = new_review[0]()

        old_review[1](old_result)
        assert deferred_panel.review_list.count() == 0
        new_review[1](new_result)
        assert deferred_panel.review_list.count() == 2

    def test_stale_submit_success_does_not_clear_new_context_or_refetch(
        self, deferred_panel
    ) -> None:
        module = deferred_panel._review_module
        _load_deferred_selection(deferred_panel)
        deferred_panel.review_event_combo.setCurrentIndex(
            deferred_panel.review_event_combo.findData("COMMENT")
        )
        deferred_panel.review_body_edit.set_text("old draft")
        deferred_panel.submit_review()
        old_submit = _take_pending(
            deferred_panel, module.github_service.create_pull_request_review
        )
        old_result = old_submit[0]()

        deferred_panel.pr_list.setCurrentRow(1)
        _resolve(
            _take_pending(deferred_panel, module.github_service.get_pull_request)
        )
        deferred_panel.review_event_combo.setCurrentIndex(
            deferred_panel.review_event_combo.findData("COMMENT")
        )
        deferred_panel.review_body_edit.set_text("new draft")
        review_requests_before = len(
            deferred_panel._review_calls["list_pull_request_reviews"]
        )

        old_submit[1](old_result)

        assert deferred_panel.review_body_edit.text() == "new draft"
        assert deferred_panel.review_event_combo.currentData() == "COMMENT"
        assert deferred_panel._current["number"] == 41
        assert (
            len(deferred_panel._review_calls["list_pull_request_reviews"])
            == review_requests_before
        )
        assert "o/r" in deferred_panel.status_label.text()
        assert "#42" in deferred_panel.status_label.text()
        assert "提出" in deferred_panel.status_label.text()

    def test_stale_submit_failure_identifies_original_target_without_new_damage(
        self, deferred_panel
    ) -> None:
        module = deferred_panel._review_module
        _load_deferred_selection(deferred_panel)
        deferred_panel.review_event_combo.setCurrentIndex(
            deferred_panel.review_event_combo.findData("COMMENT")
        )
        deferred_panel.review_body_edit.set_text("old draft")
        deferred_panel.submit_review()
        old_submit = _take_pending(
            deferred_panel, module.github_service.create_pull_request_review
        )

        deferred_panel.pr_list.setCurrentRow(1)
        _resolve(
            _take_pending(deferred_panel, module.github_service.get_pull_request)
        )
        deferred_panel.review_event_combo.setCurrentIndex(
            deferred_panel.review_event_combo.findData("REQUEST_CHANGES")
        )
        deferred_panel.review_body_edit.set_text("new draft")

        assert old_submit[2] is not None
        old_submit[2]("review failed")

        assert deferred_panel.review_body_edit.text() == "new draft"
        assert deferred_panel.review_event_combo.currentData() == "REQUEST_CHANGES"
        assert deferred_panel._current["number"] == 41
        assert "o/r" in deferred_panel.status_label.text()
        assert "#42" in deferred_panel.status_label.text()
        assert "review failed" in deferred_panel.status_label.text()
