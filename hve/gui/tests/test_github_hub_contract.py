"""FR-GUI-35: GitHub設定・Issue・PRを単一の非モーダルHubへ集約するRED契約。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
    from hve.gui import github_service, settings_store
    from hve.gui.github_threads import GitHubWorker
    from hve.gui.github_window import GitHubWindow

    monkeypatch.setattr(settings_store, "settings_path", lambda: tmp_path / ".settings.txt")
    monkeypatch.setenv("REPO", "o/r")
    monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
    monkeypatch.setattr(
        github_service,
        "list_issues",
        lambda repo, state="open", per_page=50: [],
    )
    monkeypatch.setattr(
        github_service,
        "list_pull_requests",
        lambda repo, state="open", per_page=50: [],
    )
    monkeypatch.setattr(GitHubWorker, "start", lambda self, *_a, **_kw: self.run())

    widget = GitHubWindow()
    yield widget
    widget.close()
    widget.deleteLater()


class TestSingleVisibleOwner:
    """GitHub Hubだけが設定・Issue・PRの可視ownerであること。"""

    def test_hub_has_settings_issue_and_pull_request_tabs(self, window) -> None:
        assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
            "連携設定",
            "Issue",
            "Pull Request",
        ]

    def test_hub_owns_the_existing_c5_settings_widget(self, window) -> None:
        from hve.gui.page_options import _C5IssuePR

        assert isinstance(window.settings_section, _C5IssuePR)

    def test_hub_preserves_existing_issue_and_pr_panels(self, window) -> None:
        from hve.gui.github_issue_panel import GitHubIssuePanel
        from hve.gui.github_pr_panel import GitHubPullRequestPanel

        assert isinstance(window.issue_panel, GitHubIssuePanel)
        assert isinstance(window.pr_panel, GitHubPullRequestPanel)

    def test_settings_tree_no_longer_exposes_c5(self) -> None:
        from hve.gui.settings_window import _CATEGORY_TREE

        keys = {
            key
            for _group, entries in _CATEGORY_TREE
            for _label, key in entries
        }
        assert "C5" not in keys

    def test_repository_input_is_not_duplicated_above_tabs(self, window) -> None:
        assert not hasattr(window, "repo_edit")
        assert window.settings_section.repo.placeholderText() == "owner/repo"

    def test_hub_persists_repo_through_existing_c5_store(self, window) -> None:
        from hve.gui import settings_store

        window.settings_section.repo.setText("acme/service")
        window.settings_section.repo.editingFinished.emit()
        assert settings_store.get_option("repo") == "acme/service"

    def test_hub_is_non_modal(self, window) -> None:
        assert not window.isModal()


class TestSettingsPropagation:
    """FR-GUI-35: Hub の保存を他面が古い値のまま使わないこと。"""

    def test_saving_emits_settings_changed(self, window) -> None:
        received = []
        window.settings_changed.connect(lambda payload: received.append(payload))

        window.settings_section.repo.setText("acme/service")
        window.settings_section.repo.editingFinished.emit()

        assert len(received) >= 1

    def test_close_persists_current_values(self, window) -> None:
        from PySide6.QtGui import QCloseEvent
        from hve.gui import settings_store

        window.settings_section.branch.setText("develop")
        window.closeEvent(QCloseEvent())

        assert settings_store.get_option("branch") == "develop"

    def test_hub_restores_saved_values_on_open(self, qapp, monkeypatch, tmp_path) -> None:
        from hve.gui import github_service, settings_store
        from hve.gui.github_threads import GitHubWorker
        from hve.gui.github_window import GitHubWindow

        monkeypatch.setattr(
            settings_store, "settings_path", lambda: tmp_path / ".restore.txt"
        )
        monkeypatch.setenv("REPO", "o/r")
        monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
        monkeypatch.setattr(
            github_service, "list_issues", lambda repo, state="open", per_page=50: []
        )
        monkeypatch.setattr(
            github_service,
            "list_pull_requests",
            lambda repo, state="open", per_page=50: [],
        )
        monkeypatch.setattr(GitHubWorker, "start", lambda self, *_a, **_kw: self.run())
        settings_store.set_option("branch", "release")

        widget = GitHubWindow()
        try:
            assert widget.settings_section.branch.text() == "release"
        finally:
            widget.close()
            widget.deleteLater()
