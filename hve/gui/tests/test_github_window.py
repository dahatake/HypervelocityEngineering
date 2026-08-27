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


@pytest.fixture(autouse=True)
def _stub_listing(monkeypatch):
    """FR-GUI-31 の初期取得が実 API へ到達しないよう stub 化し、同期実行する。"""
    from hve.gui import github_service
    from hve.gui.github_threads import GitHubWorker

    calls: dict[str, List[str]] = {"issues": [], "pulls": []}
    monkeypatch.setattr(
        github_service,
        "list_issues",
        lambda repo, state="open", per_page=50: calls["issues"].append(repo) or [],
    )
    monkeypatch.setattr(
        github_service,
        "list_pull_requests",
        lambda repo, state="open", per_page=50: calls["pulls"].append(repo) or [],
    )
    # QThread を起動せず同一スレッドで実行する（イベントループ不要）
    monkeypatch.setattr(GitHubWorker, "start", lambda self, *_a, **_kw: self.run())
    return calls


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
    from hve.gui import github_window as module
    from hve.gui import settings_store

    # FR-GUI-35: Hub は C5 設定を所有するため、保存先をテスト内へ隔離する。
    monkeypatch.setattr(settings_store, "settings_path", lambda: tmp_path / ".settings.txt")

    win = module.GitHubWindow()
    yield win
    win.deleteLater()


class TestGitHubWindow:
    def test_has_settings_issue_and_pull_request_tabs(self, window) -> None:
        tabs = window.tabs
        assert isinstance(tabs, QTabWidget)
        assert [tabs.tabText(i) for i in range(tabs.count())] == [
            "連携設定",
            "Issue",
            "Pull Request",
        ]

    def test_window_title(self, window) -> None:
        assert "GitHub" in window.windowTitle()

    def test_repo_prefilled_from_service(self, window) -> None:
        assert window.settings_section.repo.text() == "o/r"

    def test_repo_is_propagated_to_both_panels(self, window) -> None:
        window.settings_section.repo.setText("other/repo")
        window.apply_repo()
        assert window.issue_panel._repo == "other/repo"
        assert window.pr_panel._repo == "other/repo"

    def test_unresolvable_repo_leaves_field_empty(self, qapp, monkeypatch, tmp_path) -> None:
        from hve.gui import github_window as module
        from hve.gui import settings_store

        monkeypatch.setattr(
            settings_store, "settings_path", lambda: tmp_path / ".unresolvable.txt"
        )
        monkeypatch.delenv("REPO", raising=False)
        win = module.GitHubWindow()
        try:
            assert win.settings_section.repo.text() == ""
            assert "リポジトリ" in win.status_label.text()
        finally:
            win.deleteLater()

    def test_apply_repo_rejects_malformed_value(self, window) -> None:
        window.settings_section.repo.setText("broken value")
        window.apply_repo()
        assert window.issue_panel._repo == "o/r"
        assert window.status_label.text()

    def test_close_waits_for_panel_workers(self, window) -> None:
        calls: List[str] = []
        window.issue_panel.shutdown = lambda *_a, **_kw: calls.append("issue")  # type: ignore[method-assign]
        window.pr_panel.shutdown = lambda *_a, **_kw: calls.append("pr")  # type: ignore[method-assign]
        window.closeEvent(QCloseEvent())
        assert sorted(calls) == ["issue", "pr"]


class TestPullRequestCreationEntry:
    def test_window_has_pull_request_creation_button(self, window) -> None:
        from PySide6.QtWidgets import QPushButton

        # FR-GUI-35 の Hub 化で「連携設定」タブの C5 ボタン（リポジトリ取得等）が
        # 同居するため、Issue / PR パネル側だけを検査する。
        panels = (window.issue_panel, window.pr_panel)
        labels = [
            button.text()
            for panel in panels
            for button in panel.findChildren(QPushButton)
        ]
        assert any("Pull Request を作成" in label for label in labels), labels


class TestInitialLoad:
    """FR-GUI-31: リポジトリ確定時に一覧を 1 回だけ取得すること。"""

    def test_both_lists_are_loaded_on_open(self, window, _stub_listing) -> None:
        assert _stub_listing["issues"] == ["o/r"]
        assert _stub_listing["pulls"] == ["o/r"]

    def test_applying_same_repo_does_not_refetch(self, window, _stub_listing) -> None:
        window.apply_repo()
        assert _stub_listing["issues"] == ["o/r"]
        assert _stub_listing["pulls"] == ["o/r"]

    def test_applying_new_repo_loads_again(self, window, _stub_listing) -> None:
        window.settings_section.repo.setText("other/repo")
        window.apply_repo()
        assert _stub_listing["issues"] == ["o/r", "other/repo"]
        assert _stub_listing["pulls"] == ["o/r", "other/repo"]

    def test_unresolvable_repo_does_not_load(
        self, qapp, monkeypatch, tmp_path, _stub_listing
    ) -> None:
        from hve.gui import github_window as module
        from hve.gui import settings_store

        monkeypatch.setattr(
            settings_store, "settings_path", lambda: tmp_path / ".noload.txt"
        )
        monkeypatch.delenv("REPO", raising=False)
        win = module.GitHubWindow()
        try:
            assert _stub_listing["issues"] == []
            assert _stub_listing["pulls"] == []
        finally:
            win.deleteLater()

    def test_no_polling_timer_is_created(self, window) -> None:
        from PySide6.QtCore import QTimer

        assert window.findChildren(QTimer) == []


class TestConsoleSourcePassthrough:
    """FR-GUI-33: コンソール出力の取得元を PR パネルへ伝えること。"""

    def test_provider_and_run_id_reach_pr_panel(self, window) -> None:
        provider = lambda: "log text"  # noqa: E731
        window.set_console_source(provider, "20260825T000000-abcdef")
        assert window.pr_panel._console_provider is provider
        assert window.pr_panel._console_run_id == "20260825T000000-abcdef"

    def test_clearing_provider_disables_button(self, window) -> None:
        window.set_console_source(lambda: "x")
        window.set_console_source(None)
        assert window.pr_panel._console_provider is None
        assert not window.pr_panel.post_console_button.isEnabled()


class TestLinkedPullRequest:
    """FR-GUI-32: 関連付けた Pull Request を PR パネルへ事前選択させること。"""

    def test_number_is_delegated_to_the_pr_panel(self, window) -> None:
        calls: List[int] = []
        window.pr_panel.set_linked_pull_request = (  # type: ignore[method-assign]
            lambda number: calls.append(number)
        )
        window.set_linked_pull_request(7)
        assert calls == [7]

    @pytest.mark.parametrize("value", [None, 0])
    def test_unset_number_selects_nothing(self, window, value) -> None:
        window.set_linked_pull_request(value)
        assert window.pr_panel._linked_number is None
        assert window.pr_panel.pr_list.currentRow() == -1

    def test_it_does_not_refetch_the_lists(self, window, _stub_listing) -> None:
        window.set_linked_pull_request(42)
        assert _stub_listing["issues"] == ["o/r"]
        assert _stub_listing["pulls"] == ["o/r"]

    def test_selection_survives_asynchronous_list_loading(self, qapp, monkeypatch) -> None:
        """一覧取得がイベントループ経由で完了しても選択されること（実運用順序）。"""
        from PySide6.QtCore import QTimer

        from hve.gui import github_service, github_window as module
        from hve.gui.github_threads import GitHubWorker

        pulls = [
            {"number": 41, "title": "a", "state": "closed"},
            {"number": 42, "title": "b", "state": "open"},
        ]
        monkeypatch.setattr(
            github_service, "list_pull_requests", lambda repo, state="open", per_page=50: list(pulls)
        )
        monkeypatch.setattr(
            github_service,
            "get_pull_request",
            lambda repo, number: next(p for p in pulls if p["number"] == int(number)),
        )
        monkeypatch.setattr(github_service, "list_pull_request_files", lambda repo, number: [])
        monkeypatch.setattr(github_service, "list_comments", lambda repo, number: [])
        monkeypatch.setattr(
            GitHubWorker, "start", lambda self, *_a, **_kw: QTimer.singleShot(0, self.run)
        )

        win = module.GitHubWindow()
        try:
            win.set_linked_pull_request(42)
            assert win.pr_panel.pr_list.currentRow() == -1
            for _ in range(5):
                qapp.processEvents()
            assert win.pr_panel.pr_list.currentRow() == 1
        finally:
            win.deleteLater()
