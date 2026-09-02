"""MainWindow の GUI ログ出力先を GUI セッション作業ディレクトリへ限定する回帰テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize("pass_repo_root", [False, True])
def test_main_window_creates_gui_log_only_under_session_work_root(
    qapp, monkeypatch, tmp_path: Path, pass_repo_root: bool
) -> None:
    """既定・明示の repo_root とも、cwd 直下へ gui-logs を作成しない。"""
    from hve.gui import settings_store
    from hve.gui.main_window import MainWindow

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )

    window = MainWindow(repo_root=tmp_path) if pass_repo_root else MainWindow()
    try:
        work_root = window._session_workdir.work_root
        assert work_root.parent == tmp_path / "work" / "run"
        assert (work_root / "gui-logs" / "log-0001.log").is_file()
        assert not (tmp_path / "gui-logs").exists()
    finally:
        window._page_workbench.cleanup()
        window.close()
        window.deleteLater()
