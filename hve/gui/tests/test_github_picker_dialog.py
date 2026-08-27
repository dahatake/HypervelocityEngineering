"""hve.gui.github_picker_dialog のユニットテスト（FR-GUI-32）。"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.github_service import GitHubServiceError  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


_ISSUES = [
    {"number": 12, "title": "既存の不具合"},
    {"number": 9, "title": "改善提案"},
]
_PULLS = [
    {"number": 42, "title": "機能追加"},
]


@pytest.fixture
def calls(monkeypatch):
    from hve.gui import github_service
    from hve.gui.github_threads import GitHubWorker

    seen: Dict[str, List[Any]] = {"issues": [], "pulls": []}
    monkeypatch.setattr(
        github_service,
        "list_issues",
        lambda repo, state="open", per_page=50: seen["issues"].append((repo, state))
        or list(_ISSUES),
    )
    monkeypatch.setattr(
        github_service,
        "list_pull_requests",
        lambda repo, state="open", per_page=50: seen["pulls"].append((repo, state))
        or list(_PULLS),
    )
    monkeypatch.setattr(GitHubWorker, "start", lambda self, *_a, **_kw: self.run())
    return seen


@pytest.fixture
def issue_dialog(qapp, calls):
    from hve.gui.github_picker_dialog import GitHubPickerDialog

    dlg = GitHubPickerDialog("o/r", "issue")
    yield dlg
    dlg.deleteLater()


class TestPicker:
    def test_lists_issues_on_open(self, issue_dialog, calls) -> None:
        assert calls["issues"] == [("o/r", "open")]
        assert issue_dialog.item_list.count() == 2
        assert "#12" in issue_dialog.item_list.item(0).text()

    def test_returns_selected_number(self, issue_dialog) -> None:
        issue_dialog.item_list.setCurrentRow(1)
        assert issue_dialog.selected_number() == 9

    def test_returns_none_without_selection(self, issue_dialog) -> None:
        assert issue_dialog.selected_number() is None

    def test_pull_request_mode_uses_pull_request_api(self, qapp, calls) -> None:
        from hve.gui.github_picker_dialog import GitHubPickerDialog

        dlg = GitHubPickerDialog("o/r", "pr")
        try:
            assert calls["pulls"] == [("o/r", "open")]
            assert calls["issues"] == []
            dlg.item_list.setCurrentRow(0)
            assert dlg.selected_number() == 42
        finally:
            dlg.deleteLater()

    def test_unknown_kind_falls_back_to_issue(self, qapp, calls) -> None:
        from hve.gui.github_picker_dialog import GitHubPickerDialog

        dlg = GitHubPickerDialog("o/r", "unknown")
        try:
            assert calls["issues"] == [("o/r", "open")]
        finally:
            dlg.deleteLater()

    def test_state_filter_is_passed_through(self, issue_dialog, calls) -> None:
        issue_dialog.state_combo.setCurrentIndex(issue_dialog.state_combo.findData("all"))
        issue_dialog.refresh()
        assert calls["issues"][-1] == ("o/r", "all")

    def test_client_side_filter_does_not_call_api(self, issue_dialog, calls) -> None:
        before = len(calls["issues"])
        issue_dialog.filter_edit.setText("改善")
        assert issue_dialog.item_list.count() == 1
        assert len(calls["issues"]) == before

    def test_selection_uses_filtered_row(self, issue_dialog) -> None:
        issue_dialog.filter_edit.setText("改善")
        issue_dialog.item_list.setCurrentRow(0)
        assert issue_dialog.selected_number() == 9

    def test_without_repo_does_not_call_api(self, qapp, calls) -> None:
        from hve.gui.github_picker_dialog import GitHubPickerDialog

        dlg = GitHubPickerDialog("", "issue")
        try:
            assert calls["issues"] == []
            assert dlg.status_label.text()
        finally:
            dlg.deleteLater()

    def test_empty_open_result_suggests_all(self, qapp, monkeypatch, calls) -> None:
        from hve.gui import github_service
        from hve.gui.github_picker_dialog import GitHubPickerDialog

        monkeypatch.setattr(
            github_service, "list_issues", lambda repo, state="open", per_page=50: []
        )
        dlg = GitHubPickerDialog("o/r", "issue")
        try:
            assert "すべて" in dlg.status_label.text()
        finally:
            dlg.deleteLater()

    def test_service_error_is_shown(self, qapp, monkeypatch, calls) -> None:
        from hve.gui import github_service
        from hve.gui.github_picker_dialog import GitHubPickerDialog

        def _boom(*_a, **_kw):
            raise GitHubServiceError("権限が不足しています。")

        monkeypatch.setattr(github_service, "list_issues", _boom)
        dlg = GitHubPickerDialog("o/r", "issue")
        try:
            assert "権限が不足しています。" in dlg.status_label.text()
            assert dlg.item_list.count() == 0
        finally:
            dlg.deleteLater()

    def test_entries_without_number_are_skipped(self, qapp, monkeypatch, calls) -> None:
        from hve.gui import github_service
        from hve.gui.github_picker_dialog import GitHubPickerDialog

        monkeypatch.setattr(
            github_service,
            "list_issues",
            lambda repo, state="open", per_page=50: [{"title": "no number"}, {"number": 1, "title": "ok"}],
        )
        dlg = GitHubPickerDialog("o/r", "issue")
        try:
            assert dlg.item_list.count() == 1
            dlg.item_list.setCurrentRow(0)
            assert dlg.selected_number() == 1
        finally:
            dlg.deleteLater()
