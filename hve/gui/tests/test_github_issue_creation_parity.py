"""FR-GUI-41: Issue creation metadata UI contract."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui import github_issue_panel as module  # noqa: E402
from hve.gui.github_service import GitHubServiceError  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, monkeypatch):
    widget = module.GitHubIssuePanel()
    widget.set_repo("o/r")
    monkeypatch.setattr(
        widget,
        "_run",
        lambda task, on_ok, on_ng=None: _run_sync(widget, task, on_ok, on_ng),
    )
    monkeypatch.setattr(module.github_service, "list_issues", lambda *_a, **_kw: [])
    return widget


def _run_sync(widget, task, on_ok, on_ng=None) -> None:
    try:
        value = task()
    except GitHubServiceError as exc:
        (on_ng or widget._show_error)(str(exc))
    else:
        on_ok(value)


def test_metadata_controls_and_default_link_are_present(panel) -> None:
    assert panel.create_labels_list.selectionMode().name == "MultiSelection"
    assert panel.create_assignees_list.selectionMode().name == "MultiSelection"
    assert panel.create_milestone_combo.itemData(0) is None
    assert panel.create_and_link_checkbox.isChecked()


def test_load_candidates_populates_controls(panel, monkeypatch) -> None:
    monkeypatch.setattr(
        module.github_service,
        "list_issue_creation_metadata",
        lambda repo: {
            "labels": [{"name": "bug"}, {"name": "docs"}],
            "assignees": [{"login": "alice"}],
            "milestones": [{"number": 2, "title": "v1"}],
        },
    )
    panel.load_creation_metadata()
    assert [panel.create_labels_list.item(i).text() for i in range(2)] == ["bug", "docs"]
    assert panel.create_assignees_list.item(0).text() == "alice"
    assert panel.create_milestone_combo.itemData(1) == 2


def test_title_with_blank_body_creates_with_selected_metadata(panel, monkeypatch) -> None:
    created = []
    monkeypatch.setattr(
        module.github_service,
        "create_issue_details",
        lambda repo, title, body, **metadata: created.append(
            (repo, title, body, metadata)
        )
        or {"number": 77, "id": 7700, "warnings": []},
    )
    monkeypatch.setattr(module.github_service, "list_issues", lambda *_a, **_kw: [])
    panel.create_labels_list.addItem("bug")
    panel.create_labels_list.item(0).setSelected(True)
    panel.create_assignees_list.addItem("alice")
    panel.create_assignees_list.item(0).setSelected(True)
    panel.create_milestone_combo.addItem("v1", 2)
    panel.create_milestone_combo.setCurrentIndex(1)
    emitted = []
    panel.issue_created.connect(emitted.append)
    panel.create_title_edit.setText("Title")
    panel.create_body_edit.set_text("")
    panel.create_issue()
    assert created == [
        (
            "o/r",
            "Title",
            "",
            {"labels": ["bug"], "assignees": ["alice"], "milestone": 2},
        )
    ]
    assert emitted == [{"number": 77, "repo": "o/r", "source": "created_in_hub"}]


def test_create_and_link_can_be_disabled(panel, monkeypatch) -> None:
    monkeypatch.setattr(
        module.github_service,
        "create_issue_details",
        lambda *_a, **_kw: {"number": 7, "id": 70, "warnings": []},
    )
    emitted = []
    panel.issue_created.connect(emitted.append)
    panel.create_and_link_checkbox.setChecked(False)
    panel.create_title_edit.setText("Title")
    panel.create_body_edit.set_text("")
    panel.create_issue()
    assert emitted == []


def test_failure_preserves_all_create_inputs(panel, monkeypatch) -> None:
    monkeypatch.setattr(
        module.github_service,
        "create_issue_details",
        lambda *_a, **_kw: (_ for _ in ()).throw(GitHubServiceError("failed")),
    )
    panel.create_labels_list.addItem("bug")
    panel.create_labels_list.item(0).setSelected(True)
    panel.create_title_edit.setText("Keep")
    panel.create_body_edit.set_text("Keep body")
    panel.create_issue()
    assert panel.create_title_edit.text() == "Keep"
    assert panel.create_body_edit.text() == "Keep body"
    assert panel.create_labels_list.item(0).isSelected()


def test_metadata_warning_does_not_retry_create(panel, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        module.github_service,
        "create_issue_details",
        lambda *_a, **_kw: calls.append(1)
        or {"number": 7, "id": 70, "warnings": [{"kind": "label", "value": "bug"}]},
    )
    panel.create_title_edit.setText("Title")
    panel.create_issue()
    assert calls == [1]
    assert "bug" in panel.status_label.text()


def test_stale_metadata_result_is_ignored_after_repo_change(panel, monkeypatch) -> None:
    pending = {}
    monkeypatch.setattr(
        panel,
        "_run",
        lambda task, on_ok, on_ng=None: pending.update(on_ok=on_ok),
    )
    panel.load_creation_metadata()
    panel.set_repo("other/repo")
    pending["on_ok"](
        {
            "labels": [{"name": "old-label"}],
            "assignees": [],
            "milestones": [],
        }
    )
    assert panel.create_labels_list.count() == 0
    assert "破棄" in panel.status_label.text()
