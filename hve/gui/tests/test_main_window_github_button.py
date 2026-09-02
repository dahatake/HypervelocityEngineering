"""hve.gui.tests.test_main_window_github_button

FR-GUI-26 / FR-GUI-27: MainWindow から GitHub Issue / PR ウィンドウを開く導線のテスト。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _stub_github_listing(monkeypatch):
    """FR-GUI-31 の初期取得が実 API へ到達しないよう stub 化し、同期実行する。"""
    from hve.gui import github_service
    from hve.gui.github_threads import GitHubWorker

    monkeypatch.setattr(
        github_service, "list_issues", lambda repo, state="open", per_page=50: []
    )
    monkeypatch.setattr(
        github_service, "list_pull_requests", lambda repo, state="open", per_page=50: []
    )
    monkeypatch.setattr(GitHubWorker, "start", lambda self, *_a, **_kw: self.run())


@pytest.fixture
def main_window(qapp, tmp_path: Path, monkeypatch):
    from hve.gui.main_window import MainWindow

    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work"))
    win = MainWindow(repo_root=tmp_path)
    yield win
    win.close()
    win.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


class TestGitHubButton:
    def test_button_exists_in_header(self, main_window) -> None:
        assert isinstance(main_window._btn_github, QToolButton)
        assert main_window._btn_github.text() == "GitHub"

    def test_button_has_tooltip(self, main_window) -> None:
        tooltip = main_window._btn_github.toolTip()
        assert "Issue" in tooltip and "Pull Request" in tooltip

    def test_click_opens_github_window(self, main_window, monkeypatch) -> None:
        from hve.gui import github_service

        monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
        monkeypatch.setenv("REPO", "o/r")

        assert main_window._github_window is None
        main_window._open_github_window()
        assert main_window._github_window is not None
        assert main_window._github_window.isVisible()
        main_window._github_window.close()

    def test_reopening_reuses_the_same_window(self, main_window, monkeypatch) -> None:
        from hve.gui import github_service

        monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
        monkeypatch.setenv("REPO", "o/r")

        main_window._open_github_window()
        first = main_window._github_window
        main_window._open_github_window()
        assert main_window._github_window is first
        first.close()

    def test_closing_main_window_closes_github_window(self, main_window, monkeypatch) -> None:
        from hve.gui import github_service

        monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
        monkeypatch.setenv("REPO", "o/r")

        main_window._open_github_window()
        github_window = main_window._github_window
        assert github_window is not None
        main_window.close()
        assert not github_window.isVisible()


class TestConsoleSourceWiring:
    """FR-GUI-33: 作業状況画面のコンソール出力を PR パネルへ渡すこと。"""

    def test_provider_is_the_workbench_console_text(self, main_window, monkeypatch) -> None:
        from hve.gui import github_service

        monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
        monkeypatch.setenv("REPO", "o/r")

        main_window._open_github_window()
        panel = main_window._github_window.pr_panel
        try:
            assert panel._console_provider == main_window._page_workbench.console_text
        finally:
            main_window._github_window.close()

    def test_run_id_is_the_session_run_id(self, main_window, monkeypatch) -> None:
        from hve.gui import github_service

        monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
        monkeypatch.setenv("REPO", "o/r")

        main_window._open_github_window()
        panel = main_window._github_window.pr_panel
        try:
            assert panel._console_run_id == main_window._session_workdir.session_run_id
        finally:
            main_window._github_window.close()

    def test_console_text_returns_displayed_log(self, main_window) -> None:
        page = main_window._page_workbench
        page._log_tabs.append_global("hello world")
        assert "hello world" in page.console_text()


class TestLinkedPullRequestWiring:
    """FR-GUI-32: 保存済みの「連携する Pull Request 番号」を GitHub ウィンドウへ渡すこと。"""

    @pytest.fixture
    def linked_calls(self, monkeypatch):
        from hve.gui import github_service
        from hve.gui.github_window import GitHubWindow

        monkeypatch.setattr(github_service, "_guess_repo", lambda: None)
        monkeypatch.setenv("REPO", "o/r")
        calls: list = []
        monkeypatch.setattr(
            GitHubWindow,
            "set_linked_pull_request",
            lambda self, number: calls.append(number),
        )
        return calls

    def _stub_option(self, monkeypatch, value: str) -> None:
        from hve.gui import settings_store

        monkeypatch.setattr(
            settings_store,
            "get_option",
            lambda key, **_kw: value if key == "linked_pr_number" else "",
        )

    def test_saved_number_is_applied(self, main_window, monkeypatch, linked_calls) -> None:
        self._stub_option(monkeypatch, "42")
        main_window._open_github_window()
        try:
            assert linked_calls == [42]
        finally:
            main_window._github_window.close()

    @pytest.mark.parametrize("value", ["", "   ", "abc", "-3"])
    def test_unset_or_invalid_number_passes_none(
        self, main_window, monkeypatch, linked_calls, value
    ) -> None:
        self._stub_option(monkeypatch, value)
        main_window._open_github_window()
        try:
            assert linked_calls == [None]
        finally:
            main_window._github_window.close()

    def test_reopening_does_not_override_current_selection(
        self, main_window, monkeypatch, linked_calls
    ) -> None:
        self._stub_option(monkeypatch, "42")
        main_window._open_github_window()
        main_window._open_github_window()
        try:
            assert linked_calls == [42]
        finally:
            main_window._github_window.close()

    def test_number_is_not_propagated_to_orchestrator_args(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        args = OrchestrateArgs(workflow="ard")
        assert not hasattr(args, "linked_pr_number")
        assert not any("pr-number" in token for token in args.to_argv())
