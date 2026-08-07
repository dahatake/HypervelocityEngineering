"""console-log ダンプ機能のテスト。

対象:
- ``hve.gui.page_workbench._write_console_log`` 純関数（Qt 依存なし）
- ``WorkbenchPage.set_session_work_root`` setter / ``_maybe_dump_console_log``
  および ``_on_process_finished`` 経路での dump 発火（pytest-qt 流儀）

要件:
- GUI セッションのキュー全完了時にログ全文を ``<run_dir>/console-log.txt`` へ UTF-8 上書き
- run_dir 未設定 / 不在 / 書き込み失敗時は GUI を止めず黙ってスキップ
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from hve.gui.page_workbench import _write_console_log


# --------------------------------------------------------------------------
# 純関数 _write_console_log の単体テスト（Qt 不要）
# --------------------------------------------------------------------------


class TestWriteConsoleLogPureFunction:
    """``_write_console_log`` の純関数テスト群。"""

    def test_writes_text_to_console_log_txt(self, tmp_path: Path) -> None:
        text = "line1\nline2\nline3\n"
        result = _write_console_log(text, tmp_path)
        assert result is not None
        assert result == tmp_path / "console-log.txt"
        assert result.exists()
        assert result.read_text(encoding="utf-8") == text

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "console-log.txt"
        target.write_text("OLD CONTENT", encoding="utf-8")
        new_text = "NEW CONTENT\n"
        result = _write_console_log(new_text, tmp_path)
        assert result == target
        assert target.read_text(encoding="utf-8") == new_text

    def test_empty_text_creates_zero_byte_file(self, tmp_path: Path) -> None:
        result = _write_console_log("", tmp_path)
        assert result is not None
        assert result.exists()
        assert result.read_text(encoding="utf-8") == ""

    def test_returns_none_when_run_dir_is_none(self) -> None:
        result = _write_console_log("hello", None)
        assert result is None

    def test_returns_none_when_run_dir_does_not_exist(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        result = _write_console_log("hello", missing)
        assert result is None

    def test_returns_none_when_run_dir_is_a_file(self, tmp_path: Path) -> None:
        not_a_dir = tmp_path / "not-a-dir.txt"
        not_a_dir.write_text("x", encoding="utf-8")
        result = _write_console_log("hello", not_a_dir)
        assert result is None

    def test_preserves_utf8_multibyte_characters(self, tmp_path: Path) -> None:
        text = "日本語ログ\n絵文字 🚀✅\n"
        result = _write_console_log(text, tmp_path)
        assert result is not None
        assert result.read_text(encoding="utf-8") == text

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX chmod のみ")
    def test_returns_none_on_oserror_for_readonly_dir(self, tmp_path: Path) -> None:
        ro_dir = tmp_path / "ro"
        ro_dir.mkdir()
        os.chmod(ro_dir, 0o500)  # read+execute のみ（write 不可）
        try:
            result = _write_console_log("hello", ro_dir)
            assert result is None
        finally:
            os.chmod(ro_dir, 0o700)  # cleanup のため write 戻し


# --------------------------------------------------------------------------
# WorkbenchPage 統合テスト（pytest-qt 流儀、QApplication 必要）
# --------------------------------------------------------------------------


pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def page(qapp, tmp_path, monkeypatch):
    """``WorkbenchPage`` のインスタンスを作成。cwd を tmp_path に固定して
    ``_LogPane`` の gui-logs 副作用を tmp 配下に閉じ込める。"""
    monkeypatch.chdir(tmp_path)
    from hve.gui.page_workbench import WorkbenchPage

    p = WorkbenchPage()
    yield p
    p.deleteLater()


class TestWorkbenchPageConsoleLogDump:
    """``WorkbenchPage`` 側 dump 経路の統合テスト。"""

    def test_set_session_work_root_stores_path(self, page, tmp_path: Path) -> None:
        page.set_session_work_root(tmp_path)
        assert page._session_work_root == tmp_path

    def test_maybe_dump_console_log_writes_global_log_text(
        self, page, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "run-dir"
        run_dir.mkdir()
        page.set_session_work_root(run_dir)
        page._log_pane.append_line("integration-test-line-1")
        page._log_pane.append_line("integration-test-line-2")

        page._maybe_dump_console_log()

        target = run_dir / "console-log.txt"
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert "integration-test-line-1" in content
        assert "integration-test-line-2" in content

    def test_maybe_dump_console_log_noop_when_work_root_unset(
        self, page, tmp_path: Path
    ) -> None:
        # set_session_work_root を呼ばない → no-op
        page._log_pane.append_line("should-not-be-dumped")
        # 例外なく完了し、tmp_path 配下に console-log.txt は生成されない
        page._maybe_dump_console_log()
        assert not (tmp_path / "console-log.txt").exists()

    def test_dump_triggered_on_queue_completion(
        self, page, tmp_path: Path
    ) -> None:
        """キュー消化完了経路（_start_next_in_queue の終了分岐）で dump 発火する。"""
        run_dir = tmp_path / "run-dir-queue"
        run_dir.mkdir()
        page.set_session_work_root(run_dir)
        page._log_pane.append_line("queue-completion-marker")

        # キューが空の状態で _start_next_in_queue を呼ぶと完了分岐へ落ちる
        page._args_queue = []
        page._queue_index = 0
        page._return_codes = []
        page._start_next_in_queue()

        target = run_dir / "console-log.txt"
        assert target.exists()
        assert "queue-completion-marker" in target.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# _LogPane のローテーションログ出力先（work/run/<id>/gui-logs/）の検証
# --------------------------------------------------------------------------


class TestLogPaneBaseDir:
    """``_LogPane.set_log_base_dir`` とローテーションログの出力先検証。"""

    def test_no_log_file_at_construction(
        self, qapp, tmp_path: Path, monkeypatch
    ) -> None:
        """構築時点では cwd 配下に gui-logs を作らない（注入式へ移行）。"""
        monkeypatch.chdir(tmp_path)
        from hve.gui.page_workbench import _LogPane

        pane = _LogPane("ログ")
        try:
            assert pane._log_file_path is None
            assert not (tmp_path / "work" / "gui-logs").exists()
        finally:
            pane.deleteLater()

    def test_set_log_base_dir_opens_log_under_gui_logs(
        self, qapp, tmp_path: Path
    ) -> None:
        """注入後は ``<run_dir>/gui-logs/log-0001.log`` を開く。"""
        from hve.gui.page_workbench import _LogPane

        pane = _LogPane("ログ")
        run_dir = tmp_path / "run-x"
        run_dir.mkdir()
        try:
            pane.set_log_base_dir(run_dir)
            log_file = run_dir / "gui-logs" / "log-0001.log"
            assert log_file.exists()
            assert pane._log_file_path == log_file
        finally:
            pane.deleteLater()

    def test_append_line_persists_under_gui_logs(
        self, qapp, tmp_path: Path
    ) -> None:
        """注入後の ``append_line`` が gui-logs 配下へ永続化される。"""
        from hve.gui.page_workbench import _LogPane

        pane = _LogPane("ログ")
        run_dir = tmp_path / "run-y"
        run_dir.mkdir()
        try:
            pane.set_log_base_dir(run_dir)
            pane.append_line("persisted-line")
            content = (run_dir / "gui-logs" / "log-0001.log").read_text(
                encoding="utf-8"
            )
            assert "persisted-line" in content
        finally:
            pane.deleteLater()

    def test_set_log_base_dir_none_disables_persistence(
        self, qapp, tmp_path: Path
    ) -> None:
        """``None`` 注入で永続化を無効化し、append しても書き込まない。"""
        from hve.gui.page_workbench import _LogPane

        pane = _LogPane("ログ")
        try:
            pane.set_log_base_dir(None)
            assert pane._log_file_path is None
            pane.append_line("dropped-line")
            assert pane._log_file_path is None
        finally:
            pane.deleteLater()

    def test_set_log_base_dir_none_closes_handle(
        self, qapp, tmp_path: Path
    ) -> None:
        """NFR-OBS-09 (1): 永続化無効化時に保持中のハンドルを閉じる。"""
        from hve.gui.page_workbench import _LogPane

        pane = _LogPane("ログ")
        run_dir = tmp_path / "run-close"
        run_dir.mkdir()
        try:
            pane.set_log_base_dir(run_dir)
            pane.append_line("before-close")
            handle = pane._log_file
            assert handle is not None and not handle.closed
            pane.set_log_base_dir(None)
            assert handle.closed
            assert pane._log_file is None
        finally:
            pane.deleteLater()

    def test_append_line_does_not_reopen_file_each_line(
        self, qapp, tmp_path: Path, monkeypatch
    ) -> None:
        """NFR-OBS-09 (1): 1 行ごとに ``open`` し直さない（ハンドルを保持する）。"""
        from hve.gui.page_workbench import _LogPane

        opened: list[str] = []
        original_open = Path.open

        def counting_open(self: Path, *args, **kwargs):
            opened.append(str(self))
            return original_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", counting_open)

        pane = _LogPane("ログ")
        run_dir = tmp_path / "run-handle"
        run_dir.mkdir()
        try:
            pane.set_log_base_dir(run_dir)
            baseline = len(opened)
            for i in range(50):
                pane.append_line(f"line-{i}")
            assert len(opened) - baseline <= 1
            content = (run_dir / "gui-logs" / "log-0001.log").read_text(
                encoding="utf-8"
            )
            assert "line-0" in content and "line-49" in content
        finally:
            pane.deleteLater()

    def test_rotation_opens_new_file_once(
        self, qapp, tmp_path: Path, monkeypatch
    ) -> None:
        """NFR-OBS-09 (1): ローテーション時のみ次ファイルを開き直す。"""
        from hve.gui import page_workbench

        monkeypatch.setattr(page_workbench, "_LOG_ROTATE_LINES", 3)

        opened: list[str] = []
        original_open = Path.open

        def counting_open(self: Path, *args, **kwargs):
            opened.append(str(self))
            return original_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", counting_open)

        pane = page_workbench._LogPane("ログ")
        run_dir = tmp_path / "run-rotate"
        run_dir.mkdir()
        try:
            pane.set_log_base_dir(run_dir)
            baseline = len(opened)
            for i in range(4):
                pane.append_line(f"rot-{i}")
            # 4 行 = 初回ファイル 1 回 + ローテーション後 1 回
            assert len(opened) - baseline <= 2
            gui_logs = run_dir / "gui-logs"
            assert "rot-0" in (gui_logs / "log-0001.log").read_text(encoding="utf-8")
            assert "rot-3" in (gui_logs / "log-0002.log").read_text(encoding="utf-8")
        finally:
            pane.deleteLater()

    def test_set_session_work_root_wires_gui_logs(
        self, page, tmp_path: Path
    ) -> None:
        """``WorkbenchPage.set_session_work_root`` が gui-logs 出力先を配線する。"""
        run_dir = tmp_path / "run-z"
        run_dir.mkdir()
        page.set_session_work_root(run_dir)
        assert (run_dir / "gui-logs" / "log-0001.log").exists()

    def test_cleanup_closes_log_file_handle(self, page, tmp_path: Path) -> None:
        """NFR-OBS-09 (1): ページ cleanup 時に保持中のハンドルを閉じる。"""
        run_dir = tmp_path / "run-cleanup"
        run_dir.mkdir()
        page.set_session_work_root(run_dir)
        page._log_pane.append_line("before-cleanup")
        handle = page._log_pane._log_file
        assert handle is not None and not handle.closed
        page.cleanup()
        assert handle.closed
