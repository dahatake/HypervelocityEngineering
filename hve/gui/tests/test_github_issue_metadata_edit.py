"""FR-GUI-44: existing Issue metadata edit UI contract."""

from __future__ import annotations

import os
from functools import partial
from typing import Any, Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QListWidget  # noqa: E402

from hve.gui import github_issue_panel as module  # noqa: E402
from hve.gui.github_service import GitHubServiceError  # noqa: E402


_CANDIDATES = {
    "labels": [{"name": "bug"}, {"name": "docs"}],
    "assignees": [{"login": "alice"}, {"login": "bob"}],
    "milestones": [
        {"number": 2, "title": "v1"},
        {"number": 3, "title": "v2"},
    ],
}


def _issue(
    number: int = 12,
    *,
    labels: tuple[str, ...] = ("bug",),
    assignees: tuple[str, ...] = ("alice",),
    milestone: int = 2,
) -> dict[str, Any]:
    milestone_title = {2: "v1", 3: "v2"}.get(milestone, f"m{milestone}")
    return {
        "number": number,
        "title": f"Issue {number}",
        "state": "open",
        "user": {"login": "owner"},
        "labels": [{"name": value} for value in labels],
        "assignees": [{"login": value} for value in assignees],
        "milestone": (
            {"number": milestone, "title": milestone_title} if milestone else None
        ),
        "body": "body",
        "html_url": f"https://github.com/o/r/issues/{number}",
    }


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, monkeypatch):
    widget = module.GitHubIssuePanel()
    widget.set_repo("o/r")
    calls: dict[str, list[Any]] = {"metadata": [], "updates": []}

    def _metadata(repo: str) -> dict[str, Any]:
        calls["metadata"].append(repo)
        return _CANDIDATES

    def _update(repo: str, number: int, **metadata: Any) -> dict[str, Any]:
        calls["updates"].append((repo, number, metadata))
        milestone = int(metadata["milestone"])
        return _issue(
            int(number),
            labels=tuple(metadata["labels"]),
            assignees=tuple(metadata["assignees"]),
            milestone=milestone,
        )

    monkeypatch.setattr(module.github_service, "list_issue_creation_metadata", _metadata)
    monkeypatch.setattr(module.github_service, "update_issue", _update)
    monkeypatch.setattr(widget, "_load_comments", lambda _number: None)
    monkeypatch.setattr(
        widget,
        "_run",
        lambda task, on_ok, on_ng=None: _run_sync(widget, task, on_ok, on_ng),
    )
    widget._metadata_calls = calls  # type: ignore[attr-defined]
    return widget


def _run_sync(
    widget,
    task: Callable[[], Any],
    on_ok: Callable[[Any], None],
    on_ng: Callable[[str], None] | None = None,
) -> None:
    try:
        value = task()
    except GitHubServiceError as exc:
        (on_ng or widget._show_error)(str(exc))
    else:
        on_ok(value)


def _selected_texts(widget: QListWidget) -> list[str]:
    return [item.text() for item in widget.selectedItems()]


def _select_only(widget: QListWidget, value: str) -> None:
    widget.clearSelection()
    for row in range(widget.count()):
        item = widget.item(row)
        if item.text() == value:
            item.setSelected(True)
            return
    raise AssertionError(f"candidate not found: {value}")


def _seed_selected_issue(widget, issue: dict[str, Any]) -> None:
    widget._issues = [issue]
    widget._visible = [issue]
    previous = widget.issue_list.blockSignals(True)
    try:
        widget.issue_list.clear()
        widget.issue_list.addItem(widget._issue_label(issue))
        widget.issue_list.setCurrentRow(0)
    finally:
        widget.issue_list.blockSignals(previous)
    widget._on_issue_loaded(issue)


def _delay_update_requests(widget, monkeypatch) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []

    def _run(task, on_ok, on_ng=None):
        if isinstance(task, partial) and task.func is module.github_service.update_issue:
            pending.append({"task": task, "on_ok": on_ok, "on_ng": on_ng})
            return
        _run_sync(widget, task, on_ok, on_ng)

    monkeypatch.setattr(widget, "_run", _run)
    return pending


def test_missing_candidates_guides_user_and_blocks_save_without_fetch(panel) -> None:
    panel._on_issue_loaded(_issue())

    assert panel._metadata_calls["metadata"] == []
    assert not panel.edit_labels_list.isEnabled()
    assert not panel.edit_assignees_list.isEnabled()
    assert not panel.edit_milestone_combo.isEnabled()
    assert not panel.save_metadata_button.isEnabled()
    assert "作成候補を取得" in panel.metadata_guidance_label.text()

    panel.save_issue_metadata()
    assert panel._metadata_calls["metadata"] == []
    assert panel._metadata_calls["updates"] == []


def test_explicit_creation_candidates_are_reused_for_current_selection(panel) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())

    assert panel._metadata_calls["metadata"] == ["o/r"]
    assert _selected_texts(panel.edit_labels_list) == ["bug"]
    assert _selected_texts(panel.edit_assignees_list) == ["alice"]
    assert panel.edit_milestone_combo.currentData() == 2
    assert panel.save_metadata_button.isEnabled()

    panel.save_issue_metadata()
    assert panel._metadata_calls["metadata"] == ["o/r"]


def test_empty_selections_and_unset_milestone_are_explicit_replacements(panel) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    panel.edit_labels_list.clearSelection()
    panel.edit_assignees_list.clearSelection()
    panel.edit_milestone_combo.setCurrentIndex(0)

    panel.save_issue_metadata()

    assert panel._metadata_calls["updates"] == [
        ("o/r", 12, {"labels": [], "assignees": [], "milestone": 0})
    ]
    assert panel._current is not None
    assert panel._current["labels"] == []
    assert panel._current["assignees"] == []
    assert panel._current["milestone"] is None


def test_empty_but_fetched_candidates_allow_explicit_clear(panel, monkeypatch) -> None:
    monkeypatch.setattr(
        module.github_service,
        "list_issue_creation_metadata",
        lambda repo: {"labels": [], "assignees": [], "milestones": []},
    )
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue(labels=(), assignees=(), milestone=0))

    assert panel.save_metadata_button.isEnabled()
    assert panel.edit_labels_list.isEnabled()
    assert panel.edit_assignees_list.isEnabled()
    assert panel.edit_milestone_combo.currentData() == 0


def test_save_uses_run_seam_and_blocks_duplicate_request(panel, monkeypatch) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    pending = _delay_update_requests(panel, monkeypatch)

    panel.save_issue_metadata()
    panel.save_issue_metadata()

    assert len(pending) == 1
    assert not panel.save_metadata_button.isEnabled()
    assert not panel.edit_labels_list.isEnabled()
    pending[0]["on_ok"](_issue())
    assert panel.save_metadata_button.isEnabled()


def test_metadata_save_blocks_other_issue_mutations(panel, monkeypatch) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    panel.new_comment_edit.set_text("must stay local")
    pending = _delay_update_requests(panel, monkeypatch)

    panel.save_issue_metadata()
    panel.save_issue()
    panel.toggle_state()
    panel.post_comment()

    assert len(pending) == 1
    assert not panel.save_button.isEnabled()
    assert not panel.state_button.isEnabled()
    assert not panel.post_comment_button.isEnabled()
    assert panel.new_comment_edit.text() == "must stay local"

    pending[0]["on_ng"]("metadata failed")
    assert panel.save_button.isEnabled()
    assert panel.state_button.isEnabled()
    assert panel.post_comment_button.isEnabled()


def test_failure_preserves_selection_and_reenables_editor(panel, monkeypatch) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    _select_only(panel.edit_labels_list, "docs")
    _select_only(panel.edit_assignees_list, "bob")
    panel.edit_milestone_combo.setCurrentIndex(
        panel.edit_milestone_combo.findData(3)
    )
    pending = _delay_update_requests(panel, monkeypatch)

    panel.save_issue_metadata()
    pending[0]["on_ng"]("update failed")

    assert _selected_texts(panel.edit_labels_list) == ["docs"]
    assert _selected_texts(panel.edit_assignees_list) == ["bob"]
    assert panel.edit_milestone_combo.currentData() == 3
    assert panel.save_metadata_button.isEnabled()
    assert "update failed" in panel.status_label.text()


def test_success_uses_response_metadata_for_current_and_controls(panel, monkeypatch) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    _select_only(panel.edit_labels_list, "docs")
    _select_only(panel.edit_assignees_list, "bob")
    panel.edit_milestone_combo.setCurrentIndex(
        panel.edit_milestone_combo.findData(3)
    )
    response = _issue(labels=("docs",), assignees=("bob",), milestone=3)
    monkeypatch.setattr(module.github_service, "update_issue", lambda *_a, **_kw: response)

    panel.save_issue_metadata()

    assert panel._current is not None
    assert panel._current["labels"] == [{"name": "docs"}]
    assert panel._current["assignees"] == [{"login": "bob"}]
    assert panel._current["milestone"] == {"number": 3, "title": "v2"}
    assert _selected_texts(panel.edit_labels_list) == ["docs"]
    assert _selected_texts(panel.edit_assignees_list) == ["bob"]
    assert panel.edit_milestone_combo.currentData() == 3
    assert "docs" in panel.meta_label.text()
    assert "bob" in panel.meta_label.text()
    assert "v2" in panel.meta_label.text()


def test_mismatched_response_warns_once_and_uses_returned_metadata(
    panel, monkeypatch
) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    _select_only(panel.edit_labels_list, "docs")
    _select_only(panel.edit_assignees_list, "bob")
    panel.edit_milestone_combo.setCurrentIndex(
        panel.edit_milestone_combo.findData(3)
    )
    calls: list[dict[str, Any]] = []

    def _update_with_mismatch(*_args: Any, **metadata: Any) -> dict[str, Any]:
        calls.append(metadata)
        return _issue()

    monkeypatch.setattr(
        module.github_service,
        "update_issue",
        _update_with_mismatch,
    )

    panel.save_issue_metadata()

    assert len(calls) == 1
    assert "警告" in panel.status_label.text()
    assert "一致" in panel.status_label.text()
    assert panel._current is not None
    assert panel._current["labels"] == [{"name": "bug"}]
    assert _selected_texts(panel.edit_labels_list) == ["bug"]


def test_repo_change_discards_inflight_response(panel, monkeypatch) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    pending = _delay_update_requests(panel, monkeypatch)
    panel.save_issue_metadata()

    panel.set_repo("other/repo")
    panel.load_creation_metadata()
    panel._on_issue_loaded(
        _issue(99, labels=("docs",), assignees=("bob",), milestone=3)
    )
    pending[0]["on_ok"](_issue(labels=(), assignees=(), milestone=0))

    assert panel._current is not None
    assert panel._current["number"] == 99
    assert panel._current["labels"] == [{"name": "docs"}]
    assert _selected_texts(panel.edit_labels_list) == ["docs"]


def test_issue_change_discards_inflight_response(panel, monkeypatch) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    pending = _delay_update_requests(panel, monkeypatch)
    panel.save_issue_metadata()

    panel._on_issue_loaded(
        _issue(9, labels=("docs",), assignees=("bob",), milestone=3)
    )
    pending[0]["on_ok"](_issue(labels=(), assignees=(), milestone=0))

    assert panel._current is not None
    assert panel._current["number"] == 9
    assert panel._current["labels"] == [{"name": "docs"}]
    assert _selected_texts(panel.edit_labels_list) == ["docs"]


def test_newer_detail_context_for_same_issue_discards_inflight_response(
    panel, monkeypatch
) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    pending = _delay_update_requests(panel, monkeypatch)
    panel.save_issue_metadata()

    panel._issue_load_generation += 1
    panel._on_issue_loaded(
        _issue(12, labels=("docs",), assignees=("bob",), milestone=3)
    )
    pending[0]["on_ok"](_issue(labels=(), assignees=(), milestone=0))

    assert panel._current is not None
    assert panel._current["number"] == 12
    assert panel._current["labels"] == [{"name": "docs"}]
    assert _selected_texts(panel.edit_labels_list) == ["docs"]


def test_repo_change_clears_old_detail_before_any_update(panel) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())

    panel.set_repo("new/r")
    panel.save_issue()
    panel.save_issue_metadata()

    assert panel._current is None
    assert panel._metadata_calls["updates"] == []
    assert not panel.save_button.isEnabled()
    assert not panel.save_metadata_button.isEnabled()
    assert panel.title_edit.text() == ""
    assert panel.body_edit.text() == ""


def test_current_values_outside_candidates_are_preserved_and_selected(
    panel, monkeypatch
) -> None:
    monkeypatch.setattr(
        module.github_service,
        "list_issue_creation_metadata",
        lambda _repo: _CANDIDATES,
    )
    panel.load_creation_metadata()
    current = _issue(
        labels=("legacy-label",),
        assignees=("former-user",),
        milestone=99,
    )
    current["milestone"] = {"number": 99, "title": "closed-v0"}
    panel._on_issue_loaded(current)

    assert _selected_texts(panel.edit_labels_list) == ["legacy-label"]
    assert _selected_texts(panel.edit_assignees_list) == ["former-user"]
    assert panel.edit_milestone_combo.currentData() == 99

    panel.save_issue_metadata()

    assert panel._metadata_calls["updates"] == [
        (
            "o/r",
            12,
            {
                "labels": ["legacy-label"],
                "assignees": ["former-user"],
                "milestone": 99,
            },
        )
    ]


def test_candidate_reload_is_blocked_while_metadata_save_is_pending(
    panel, monkeypatch
) -> None:
    panel.load_creation_metadata()
    panel._on_issue_loaded(_issue())
    _select_only(panel.edit_labels_list, "docs")
    _select_only(panel.edit_assignees_list, "bob")
    panel.edit_milestone_combo.setCurrentIndex(
        panel.edit_milestone_combo.findData(3)
    )
    pending = _delay_update_requests(panel, monkeypatch)
    metadata_calls_before = list(panel._metadata_calls["metadata"])

    panel.save_issue_metadata()
    panel.load_creation_metadata()

    assert panel._metadata_calls["metadata"] == metadata_calls_before
    assert not panel.load_metadata_button.isEnabled()
    pending[0]["on_ng"]("update failed")
    assert _selected_texts(panel.edit_labels_list) == ["docs"]
    assert _selected_texts(panel.edit_assignees_list) == ["bob"]
    assert panel.edit_milestone_combo.currentData() == 3
    assert panel.load_metadata_button.isEnabled()


def test_append_during_metadata_save_preserves_target_and_editor_selection(
    panel, monkeypatch
) -> None:
    panel.load_creation_metadata()
    selected_issue = _issue()
    _seed_selected_issue(panel, selected_issue)
    _select_only(panel.edit_labels_list, "docs")
    _select_only(panel.edit_assignees_list, "bob")
    panel.edit_milestone_combo.setCurrentIndex(
        panel.edit_milestone_combo.findData(3)
    )
    pending = _delay_update_requests(panel, monkeypatch)

    panel.save_issue_metadata()
    panel._on_issues_loaded([_issue(13)], append=True)

    selected_row = panel.issue_list.currentRow()
    assert panel._visible[selected_row]["number"] == 12
    assert panel._current is not None
    assert panel._current["number"] == 12
    assert _selected_texts(panel.edit_labels_list) == ["docs"]
    assert _selected_texts(panel.edit_assignees_list) == ["bob"]
    assert panel.edit_milestone_combo.currentData() == 3
    assert panel._metadata_save_token is not None

    pending[0]["on_ok"](
        _issue(labels=("docs",), assignees=("bob",), milestone=3)
    )
    assert panel._metadata_save_token is None
    assert panel._current is not None
    assert panel._current["labels"] == [{"name": "docs"}]
