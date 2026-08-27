"""FR-GUI-49: Issue panel から Copilot cloud agent へ割り当てる UI 契約。"""

from __future__ import annotations

import importlib
import os
from functools import partial
from typing import Any, Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from hve.gui import github_issue_panel as module  # noqa: E402

_UNSET = object()


def _issue(number: int = 12) -> dict[str, Any]:
    return {
        "number": number,
        "title": f"Issue {number}",
        "state": "open",
        "user": {"login": "owner"},
        "labels": [],
        "assignees": [],
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
    monkeypatch.setattr(widget, "_load_comments", lambda _number: None)

    pending: list[
        tuple[
            Callable[[], Any],
            Callable[[Any], None],
            Callable[[str], None] | None,
        ]
    ] = []
    calls: list[tuple[str, int, str | None]] = []

    def _assign(repo: str, number: int, base_branch: str | None = None) -> dict:
        calls.append((repo, number, base_branch))
        return {
            "number": number,
            "assignees": [{"login": "copilot-swe-agent[bot]"}],
        }

    def _defer(
        task: Callable[[], Any],
        on_ok: Callable[[Any], None],
        on_ng: Callable[[str], None] | None = None,
    ) -> None:
        pending.append((task, on_ok, on_ng))

    monkeypatch.setattr(module.github_service, "assign_copilot_agent", _assign)
    monkeypatch.setattr(widget, "_run", _defer)
    widget._copilot_pending = pending  # type: ignore[attr-defined]
    widget._copilot_calls = calls  # type: ignore[attr-defined]
    yield widget
    widget.deleteLater()


def _select_issue(widget, number: int = 12) -> None:
    issue = _issue(number)
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


def _confirm(
    monkeypatch,
    answer: QMessageBox.StandardButton,
    captured: dict[str, Any] | None = None,
) -> None:
    def _question(parent, title, text, buttons, default):
        if captured is not None:
            captured.update(
                parent=parent,
                title=title,
                text=text,
                buttons=buttons,
                default=default,
            )
        return answer

    monkeypatch.setattr(module.QMessageBox, "question", _question)


def _resolve_success(widget, result: Any = _UNSET) -> None:
    task, on_ok, _on_ng = widget._copilot_pending.pop(0)
    actual = task() if result is _UNSET else result
    on_ok(actual)


def _resolve_failure(widget, message: str) -> None:
    _task, _on_ok, on_ng = widget._copilot_pending.pop(0)
    assert on_ng is not None
    on_ng(message)


def _load_metadata_candidates(widget) -> None:
    widget._on_creation_metadata_loaded(
        {
            "labels": [{"name": "bug"}],
            "assignees": [{"login": "alice"}],
            "milestones": [],
        }
    )


def test_controls_and_permission_guidance_are_always_present(panel) -> None:
    guidance = panel.copilot_assignment_guidance_label.text()

    assert panel.copilot_base_branch_edit.placeholderText()
    assert panel.assign_copilot_button.text() == "Copilotへ割り当て"
    assert not panel.copilot_assignment_guidance_label.isHidden()
    assert "public preview" in guidance
    assert "fine-grained PAT" in guidance
    assert "Metadata: read" in guidance
    for permission in ("Actions", "Contents", "Issues", "Pull requests"):
        assert f"{permission}: read and write" in guidance
    assert "classic PAT" in guidance
    assert "repo" in guidance


def test_panel_imports_the_shared_assignment_response_validator() -> None:
    contract = importlib.import_module("hve.github_copilot_assignment_contract")

    assert (
        module.validate_copilot_assignment_response
        is contract.validate_copilot_assignment_response
    )


@pytest.mark.parametrize(
    ("repo", "current"),
    [
        ("", _issue()),
        ("o/r", None),
        ("o/r", []),
        ("o/r", {"number": 0}),
        ("o/r", {"number": True}),
        ("o/r", {"number": "12"}),
        ("not-a-repo", _issue()),
    ],
)
def test_missing_or_invalid_target_fails_before_confirmation(
    panel, monkeypatch, repo: str, current: Any
) -> None:
    questions: list[bool] = []

    def _accept(*_args: Any) -> QMessageBox.StandardButton:
        questions.append(True)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(
        module.QMessageBox,
        "question",
        _accept,
    )
    panel.set_repo(repo)
    panel._current = current

    panel.assign_copilot_agent()

    assert questions == []
    assert panel._copilot_pending == []
    assert panel._copilot_calls == []
    assert panel.status_label.text()


def test_confirmation_lists_target_and_defaults_to_no(panel, monkeypatch) -> None:
    captured: dict[str, Any] = {}
    _select_issue(panel)
    panel.copilot_base_branch_edit.setText(" feature/t10 ")
    _confirm(monkeypatch, QMessageBox.StandardButton.No, captured)

    panel.assign_copilot_agent()

    assert "#12" in captured["text"]
    assert "o/r" in captured["text"]
    assert "feature/t10" in captured["text"]
    assert captured["default"] == QMessageBox.StandardButton.No
    assert captured["buttons"] & QMessageBox.StandardButton.Yes
    assert captured["buttons"] & QMessageBox.StandardButton.No
    assert panel._copilot_pending == []
    assert panel._copilot_calls == []
    assert panel._current["number"] == 12
    assert panel.copilot_base_branch_edit.text() == " feature/t10 "
    assert panel.assign_copilot_button.isEnabled()


def test_empty_base_uses_github_default_and_worker_seam(panel, monkeypatch) -> None:
    captured: dict[str, Any] = {}
    _select_issue(panel)
    panel.copilot_base_branch_edit.setText("   ")
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes, captured)

    panel.assign_copilot_agent()

    assert "GitHub の既定ブランチ" in captured["text"]
    assert len(panel._copilot_pending) == 1
    assert panel._copilot_calls == []
    _resolve_success(panel)
    assert panel._copilot_calls == [("o/r", 12, None)]


def test_pending_request_blocks_duplicate_and_disables_controls(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    panel.copilot_base_branch_edit.setText("main")
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.assign_copilot_agent()
    panel.assign_copilot_agent()
    panel.assign_copilot_button.click()

    assert len(panel._copilot_pending) == 1
    assert not panel.assign_copilot_button.isEnabled()
    assert not panel.copilot_base_branch_edit.isEnabled()


def test_success_preserves_selection_and_input_and_reports_status(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    panel.copilot_base_branch_edit.setText("release/2026")
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.assign_copilot_agent()
    _resolve_success(panel)

    assert panel._current["number"] == 12
    assert panel.issue_list.currentRow() == 0
    assert panel.copilot_base_branch_edit.text() == "release/2026"
    assert panel.assign_copilot_button.isEnabled()
    assert "#12" in panel.status_label.text()
    assert "割り当てました" in panel.status_label.text()


def test_failure_preserves_selection_and_input_and_reenables_button(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    panel.copilot_base_branch_edit.setText("keep/me")
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.assign_copilot_agent()
    _resolve_failure(panel, "assignment failed")

    assert panel._current["number"] == 12
    assert panel.issue_list.currentRow() == 0
    assert panel.copilot_base_branch_edit.text() == "keep/me"
    assert panel.assign_copilot_button.isEnabled()
    assert "assignment failed" in panel.status_label.text()
    assert "割り当てました" not in panel.status_label.text()


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        {},
        {"number": 99, "assignees": [{"login": "copilot-swe-agent[bot]"}]},
        {"number": 12},
        {"number": 12, "assignees": []},
        {"number": 12, "assignees": [{"login": "octocat"}]},
        {"number": 12, "assignees": ["copilot-swe-agent[bot]"]},
    ],
)
def test_unmatched_response_is_not_accepted_as_success(
    panel, monkeypatch, response: Any
) -> None:
    _select_issue(panel)
    panel.copilot_base_branch_edit.setText("main")
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.assign_copilot_agent()
    _resolve_success(panel, response)

    assert panel._current["number"] == 12
    assert panel.copilot_base_branch_edit.text() == "main"
    assert panel.assign_copilot_button.isEnabled()
    assert "一致" in panel.status_label.text() or "解釈" in panel.status_label.text()
    assert "割り当てました" not in panel.status_label.text()


def test_metadata_save_first_blocks_assignment_and_preserves_replace_payload(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    _load_metadata_candidates(panel)
    questions: list[bool] = []

    def _question(*_args: Any) -> QMessageBox.StandardButton:
        questions.append(True)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(module.QMessageBox, "question", _question)

    panel.save_issue_metadata()
    panel.assign_copilot_agent()

    assert len(panel._copilot_pending) == 1
    task = panel._copilot_pending[0][0]
    assert isinstance(task, partial)
    assert task.func is module.github_service.update_issue
    assert task.keywords["labels"] == []
    assert task.keywords["assignees"] == []
    assert questions == []
    assert panel._copilot_assignment_token is None
    assert not panel.assign_copilot_button.isEnabled()
    assert not panel.copilot_base_branch_edit.isEnabled()


def test_assignment_first_blocks_metadata_full_replace(panel, monkeypatch) -> None:
    _select_issue(panel)
    _load_metadata_candidates(panel)
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.assign_copilot_agent()
    panel.save_issue_metadata()

    assert len(panel._copilot_pending) == 1
    task = panel._copilot_pending[0][0]
    assert isinstance(task, partial)
    assert task.func is module.github_service.assign_copilot_agent
    assert panel._metadata_save_token is None
    assert not panel.save_metadata_button.isEnabled()
    assert not panel.edit_labels_list.isEnabled()
    assert not panel.edit_assignees_list.isEnabled()


def test_metadata_candidate_load_first_blocks_assignment(panel, monkeypatch) -> None:
    _select_issue(panel)
    _load_metadata_candidates(panel)
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.load_creation_metadata()
    panel.assign_copilot_agent()

    assert len(panel._copilot_pending) == 1
    assert panel._metadata_load_token is not None
    assert panel._copilot_assignment_token is None
    assert not panel.assign_copilot_button.isEnabled()
    assert not panel.edit_labels_list.isEnabled()
    assert not panel.edit_assignees_list.isEnabled()
    assert not panel.edit_milestone_combo.isEnabled()


def test_assignment_first_blocks_metadata_candidate_load(panel, monkeypatch) -> None:
    _select_issue(panel)
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.assign_copilot_agent()
    panel.load_creation_metadata()

    assert len(panel._copilot_pending) == 1
    assert panel._metadata_load_token is None
    assert not panel.load_metadata_button.isEnabled()


def test_assignment_disables_target_and_mutation_controls_and_direct_methods(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    _load_metadata_candidates(panel)
    panel._issues_have_more = True
    panel._update_issue_list_controls()
    panel.new_comment_edit.set_text("do not post")
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)

    panel.assign_copilot_agent()

    for control in (
        panel.state_combo,
        panel.refresh_button,
        panel.filter_edit,
        panel.issue_list,
        panel.load_more_button,
        panel.title_edit,
        panel.body_edit,
        panel.save_button,
        panel.state_button,
        panel.new_comment_edit,
        panel.post_comment_button,
        panel.edit_labels_list,
        panel.edit_assignees_list,
        panel.edit_milestone_combo,
        panel.save_metadata_button,
        panel.load_metadata_button,
    ):
        assert not control.isEnabled(), control

    pending_count = len(panel._copilot_pending)
    panel.refresh_issues()
    panel.load_more_issues()
    panel._request_issues(cursor=None, append=False)
    panel.save_issue()
    panel.toggle_state()
    panel.post_comment()
    panel.save_issue_metadata()
    panel.load_creation_metadata()
    panel._on_issue_selected(-1)
    panel._load_issue(9)
    panel._login = "me"
    module.GitHubIssuePanel._load_comments(panel, 12)

    assert len(panel._copilot_pending) == pending_count
    assert panel._current is not None
    assert panel._current["number"] == 12


def test_same_issue_detail_reload_does_not_stale_assignment(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)
    panel.assign_copilot_agent()

    panel._issue_load_generation += 1
    refreshed = _issue(12)
    refreshed["title"] = "refetched title"
    panel._on_issue_loaded(refreshed)
    _resolve_success(panel)

    assert panel._current is not None
    assert panel._current["title"] == "refetched title"
    assert "割り当てました" in panel.status_label.text()


def test_assignment_epoch_discards_older_list_callback_status_and_state(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    panel.refresh_issues()
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)
    panel.assign_copilot_agent()
    assignment_status = panel.status_label.text()

    _resolve_success(panel, [])

    assert panel.status_label.text() == assignment_status
    assert panel._current is not None
    assert panel._current["number"] == 12

    _resolve_success(panel)
    assert "割り当てました" in panel.status_label.text()

    panel.refresh_issues()
    _resolve_success(panel, [])
    assert "0 件" in panel.status_label.text()


def test_assignment_epoch_discards_older_comment_failure_status(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    panel._login = "me"
    module.GitHubIssuePanel._load_comments(panel, 12)
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)
    panel.assign_copilot_agent()
    assignment_status = panel.status_label.text()

    _resolve_failure(panel, "late comments failure")

    assert panel.status_label.text() == assignment_status
    assert "late comments failure" not in panel.status_label.text()
    _resolve_success(panel)
    assert "割り当てました" in panel.status_label.text()


def test_repo_change_keeps_request_target_immutable_and_discards_result(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    panel.copilot_base_branch_edit.setText("main")
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)
    panel.assign_copilot_agent()

    panel.set_repo("other/repo")
    status_after_repo_change = panel.status_label.text()
    assert panel._copilot_assignment_token is None
    assert panel.state_combo.isEnabled()
    assert panel.refresh_button.isEnabled()
    assert panel.filter_edit.isEnabled()
    assert panel.issue_list.isEnabled()
    assert panel.load_metadata_button.isEnabled()
    _resolve_success(panel)

    assert panel._copilot_calls == [("o/r", 12, "main")]
    assert panel._current is None
    assert panel.status_label.text() == status_after_repo_change
    assert "割り当てました" not in panel.status_label.text()


def test_old_repo_callback_cannot_clear_new_assignment_token_or_status(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)
    panel.assign_copilot_agent()

    panel.set_repo("other/repo")
    _select_issue(panel, 99)
    panel.copilot_base_branch_edit.setText("main")
    panel.assign_copilot_agent()
    new_token = panel._copilot_assignment_token
    new_status = panel.status_label.text()

    _resolve_success(
        panel,
        {"number": 12, "assignees": [{"login": "copilot-swe-agent[bot]"}]},
    )

    assert panel._copilot_assignment_token is new_token
    assert panel.status_label.text() == new_status
    assert not panel.assign_copilot_button.isEnabled()
    assert not panel.copilot_base_branch_edit.isEnabled()

    _resolve_success(
        panel,
        {"number": 99, "assignees": [{"login": "copilot-swe-agent[bot]"}]},
    )
    assert panel._copilot_assignment_token is None
    assert "#99" in panel.status_label.text()
    assert "割り当てました" in panel.status_label.text()


def test_repo_change_clears_old_detail_and_base_input(panel) -> None:
    _select_issue(panel)
    panel.copilot_base_branch_edit.setText("old/repo-branch")

    panel.set_repo("other/repo")

    assert panel._current is None
    assert panel.copilot_base_branch_edit.text() == ""
    assert not panel.assign_copilot_button.isEnabled()


def test_issue_or_generation_change_discards_stale_success(
    panel, monkeypatch
) -> None:
    _select_issue(panel)
    panel.copilot_base_branch_edit.setText("main")
    _confirm(monkeypatch, QMessageBox.StandardButton.Yes)
    panel.assign_copilot_agent()

    panel._issue_load_generation += 1
    panel._on_issue_loaded(_issue(9))
    _resolve_success(
        panel,
        {
            "number": 12,
            "assignees": [{"login": "copilot-swe-agent[bot]"}],
        },
    )

    assert panel._current["number"] == 9
    assert panel.assign_copilot_button.isEnabled()
    assert "破棄" in panel.status_label.text()
    assert "割り当てました" not in panel.status_label.text()


def test_target_change_during_confirmation_prevents_request(
    panel, monkeypatch
) -> None:
    _select_issue(panel)

    def _question(*_args):
        panel.set_repo("other/repo")
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(module.QMessageBox, "question", _question)

    panel.assign_copilot_agent()

    assert panel._copilot_pending == []
    assert panel._copilot_calls == []
    assert "送信しません" in panel.status_label.text()