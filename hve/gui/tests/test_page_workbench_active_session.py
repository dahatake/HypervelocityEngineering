"""WorkbenchPage.resolve_active_main_step_id() / active_steering_ipc_dir() のテスト。

T7（hve/gui/page_workbench.py — Steering IPC ディレクトリ常時生成、対象 step_id 解決）に対応する。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.page_workbench import WorkbenchPage  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


class TestResolveActiveMainStepId(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()

    def test_no_running_steps_returns_none(self) -> None:
        """running_step_ids が空集合の場合は None を返す。"""
        self.assertEqual(self.page._state.running_step_ids, set())
        self.assertIsNone(self.page.resolve_active_main_step_id())

    def test_single_running_step_returns_it(self) -> None:
        """running_step_ids が単一要素の場合はその step_id を返す。"""
        self.page._state.set_step_status("1.1", "running")
        self.assertEqual(self.page.resolve_active_main_step_id(), "1.1")

    def test_multiple_running_steps_returns_none(self) -> None:
        """running_step_ids が複数要素（並列実行中）の場合は None を返す（不明点2）。"""
        self.page._state.set_step_status("1.1", "running")
        self.page._state.set_step_status("1.2", "running")
        self.assertIsNone(self.page.resolve_active_main_step_id())

    def test_finished_step_no_longer_counted(self) -> None:
        """running から done 等へ遷移した step は対象から外れる。"""
        self.page._state.set_step_status("1.1", "running")
        self.page._state.set_step_status("1.1", "done")
        self.assertIsNone(self.page.resolve_active_main_step_id())


class TestActiveSteeringIpcDir(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()

    def test_initial_state_is_none(self) -> None:
        """ワークフロー未起動時は None を返す。"""
        self.assertIsNone(self.page.active_steering_ipc_dir())

    def test_start_next_in_queue_creates_ipc_dir(self) -> None:
        """_start_next_in_queue 実行時に Steering IPC ディレクトリが生成され、
        args.steering_ipc_dir にも反映される（argv 構築失敗でサブプロセス起動前に
        リターンするケースでも、IPC ディレクトリ生成自体は argv 構築より前に行われる想定）。
        """
        import shutil
        import tempfile as _tempfile

        tmp_repo = Path(_tempfile.mkdtemp(prefix="steering-repo-test-"))
        try:
            args = MagicMock()
            args.repo_root = tmp_repo
            args.workflow = "wf_test"
            args.model = None
            args.to_argv.side_effect = ValueError("test stub")
            self.page._args_queue = [args]
            self.page._queue_index = 0
            self.page._start_next_in_queue()

            ipc_dir = self.page.active_steering_ipc_dir()
            self.assertIsNotNone(ipc_dir)
            assert ipc_dir is not None
            self.assertTrue(Path(ipc_dir).is_dir())
            self.assertTrue(
                Path(ipc_dir).parent == tmp_repo / ".hve" / "steering-ipc"
            )
            # args にも反映されていること
            self.assertEqual(args.steering_ipc_dir, ipc_dir)
        finally:
            shutil.rmtree(tmp_repo, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
