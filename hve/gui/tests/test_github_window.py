"""hve.gui.tests.test_github_window

FR-GUI-26 / FR-GUI-27: Issue / Pull Request パネルを束ねるウィンドウの単体テスト。
"""

from __future__ import annotations

import os
from typing import List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolate_repo_env(monkeypatch):
    """git remote 推定を除外し、`REPO` のみを解決元にする。"""
    from hve.gui import github_service

    monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
    saved = os.environ.get("REPO")
    os.environ["REPO"] = "o/r"
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("REPO", None)
        else:
            os.environ["REPO"] = saved


@pytest.fixture
def window(qapp):
    from hve.gui import github_window as module

    win = module.GitHubWindow()
    yield win
    win.deleteLater()


class TestGitHubWindow:
    def test_has_issue_and_pull_request_tabs(self, window) -> None:
        tabs = window.findChild(QTabWidget)
        assert tabs is not None
        assert [tabs.tabText(i) for i in range(tabs.count())] == [
            "Issue",
            "Pull Request",
        ]

    def test_window_title(self, window) -> None:
        assert "GitHub" in window.windowTitle()

    def test_repo_prefilled_from_service(self, window) -> None:
        assert window.repo_edit.text() == "o/r"

    def test_repo_is_propagated_to_both_panels(self, window) -> None:
        window.repo_edit.setText("other/repo")
        window.apply_repo()
        assert window.issue_panel._repo == "other/repo"
        assert window.pr_panel._repo == "other/repo"

    def test_unresolvable_repo_leaves_field_empty(self, qapp, monkeypatch) -> None:
        from hve.gui import github_window as module

        monkeypatch.delenv("REPO", raising=False)
        win = module.GitHubWindow()
        try:
            assert win.repo_edit.text() == ""
            assert "リポジトリ" in win.status_label.text()
        finally:
            win.deleteLater()

    def test_apply_repo_rejects_malformed_value(self, window) -> None:
        window.repo_edit.setText("broken value")
        window.apply_repo()
        assert window.issue_panel._repo == "o/r"
        assert window.status_label.text()

    def test_close_waits_for_panel_workers(self, window) -> None:
        calls: List[str] = []
        window.issue_panel.shutdown = lambda *_a, **_kw: calls.append("issue")  # type: ignore[method-assign]
        window.pr_panel.shutdown = lambda *_a, **_kw: calls.append("pr")  # type: ignore[method-assign]
        window.closeEvent(QCloseEvent())
        assert sorted(calls) == ["issue", "pr"]


class TestNoPullRequestCreationEntry:
    def test_window_has_no_create_pr_button(self, window) -> None:
        from PySide6.QtWidgets import QPushButton

        labels = [b.text() for b in window.findChildren(QPushButton)]
        assert not any("作成" in label for label in labels), labels
