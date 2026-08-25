"""FR-GUI-22: GUI 起動時の索引差分更新と、実行開始操作のガード。

RED 先行。`hve/gui/app.py` の起動フックと `MainWindow._refresh_navigation` の
ガードは本テストの後に追加する。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_refresh_state():
    from hve import index_refresh

    index_refresh._thread = None
    index_refresh._done.set()
    yield
    index_refresh._thread = None
    index_refresh._done.set()


class TestStartupTrigger:
    def test_startup_delegates_to_the_shared_implementation(
        self, qapp, tmp_path: Path, monkeypatch
    ):
        from hve import index_refresh
        from hve.gui import app as gui_app

        calls: list[Path] = []
        monkeypatch.setattr(
            index_refresh, "start_background",
            lambda root: calls.append(Path(root)) or True, raising=True,
        )

        started = gui_app.start_startup_index_refresh(tmp_path)

        assert started is True
        assert calls == [tmp_path]

    def test_no_polling_when_refresh_does_not_start(
        self, qapp, tmp_path: Path, monkeypatch
    ):
        from hve import index_refresh
        from hve.gui import app as gui_app

        monkeypatch.setattr(
            index_refresh, "start_background", lambda _root: False, raising=True,
        )

        assert gui_app.start_startup_index_refresh(tmp_path) is False


class TestRunGuard:
    def _window(self, tmp_path: Path):
        from hve.gui.main_window import MainWindow

        win = MainWindow(repo_root=tmp_path)
        win._page_workflow.selected_workflow_ids = lambda: ["akm"]
        return win

    def test_run_button_is_disabled_while_refreshing(
        self, qapp, tmp_path: Path, monkeypatch
    ):
        from hve import index_refresh

        win = self._window(tmp_path)
        try:
            monkeypatch.setattr(index_refresh, "is_running", lambda: True, raising=True)
            win._refresh_navigation()
            assert win._btn_next.isEnabled() is False

            monkeypatch.setattr(index_refresh, "is_running", lambda: False, raising=True)
            win._refresh_navigation()
            assert win._btn_next.isEnabled() is True
        finally:
            win.deleteLater()

    def test_status_explains_why_the_button_is_disabled(
        self, qapp, tmp_path: Path, monkeypatch
    ):
        from hve import index_refresh

        win = self._window(tmp_path)
        try:
            monkeypatch.setattr(index_refresh, "is_running", lambda: True, raising=True)
            win._refresh_navigation()
            assert "索引" in win._status_label.text()
        finally:
            win.deleteLater()


class TestSharedImplementation:
    """FR-MAINT-07: 対象列挙・更新処理を GUI 側で再実装していないこと。"""

    @pytest.mark.parametrize("relative", ["gui/app.py", "gui/main_window.py"])
    def test_gui_does_not_reimplement_index_paths(self, relative: str):
        # tests -> gui -> hve
        source = (Path(__file__).resolve().parents[2] / relative).read_text(
            encoding="utf-8"
        )

        assert "index-" not in source
        assert "mdq.indexer" not in source
        assert "cq.indexer" not in source
