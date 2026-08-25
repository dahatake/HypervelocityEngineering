"""hve.gui.tests.test_main_window_github_button

FR-GUI-26 / FR-GUI-27: MainWindow から GitHub Issue / PR ウィンドウを開く導線のテスト。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def main_window(qapp, tmp_path: Path, monkeypatch):
    from hve.gui.main_window import MainWindow

    monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path / "work"))
    win = MainWindow(repo_root=tmp_path)
    yield win
    win.deleteLater()


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
