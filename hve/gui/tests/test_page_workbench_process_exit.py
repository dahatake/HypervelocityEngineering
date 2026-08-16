"""FR-GUI-19: ストリーム終端を伴わないサブプロセス終了の検知テスト。

`SubprocessReader` は stdout の EOF に達するまで終了を通知しないため、
子孫プロセスがパイプを保持したまま親が終了すると通知が届かない。
その場合でも経過時間の計測を停止することを検証する。
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.page_workbench import WorkbenchPage  # noqa: E402
from hve.gui.workbench_state import WorkflowInstanceSeed  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


class _Clock:
    """`time.monotonic` の差し替え用。`value` を書き換えて時刻を進める。"""

    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value


class _ProcessExitTestBase(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()
        self.page._progress_widget = MagicMock()
        self.logged: list[str] = []
        self.page._log_pane.append_line = self.logged.append  # type: ignore[method-assign]
        self.proc = MagicMock()
        reader = MagicMock()
        reader._proc = self.proc
        self.page._reader = reader
        self.page._is_running = True

    def _advance(self, clock: _Clock, *offsets: float) -> None:
        """指定オフセットごとに死活チェックを 1 回ずつ実行する。"""
        with patch("time.monotonic", clock):
            for offset in offsets:
                clock.value = offset
                self.page._check_subprocess_liveness()

    def _trigger_orphaned_exit(self, returncode: int = 3) -> _Clock:
        self.proc.poll.return_value = returncode
        clock = _Clock(0.0)
        self._advance(clock, 0.0, WorkbenchPage._ORPHANED_EXIT_GRACE_SEC + 0.1)
        return clock


class TestGracePeriod(_ProcessExitTestBase):
    def test_grace_period_is_within_requirement_upper_bound(self) -> None:
        """猶予と死活チェック 1 周期の合計が、FR-GUI-19 の上限 10 秒を超えない。"""
        self.assertGreater(WorkbenchPage._ORPHANED_EXIT_GRACE_SEC, 0.0)
        # 検知は _update_timer の周期でしか走らないため、実際の最大待ちは猶予 + 1 周期。
        check_interval_sec = self.page._update_timer.interval() / 1000.0
        self.assertGreater(check_interval_sec, 0.0)
        max_wait = WorkbenchPage._ORPHANED_EXIT_GRACE_SEC + check_interval_sec
        self.assertLessEqual(max_wait, 10.0)

    def test_no_freeze_while_process_alive_despite_long_silence(self) -> None:
        """プロセスが生存していれば、出力が猶予を超えて途絶しても停止しない。"""
        self.proc.poll.return_value = None
        clock = _Clock(0.0)
        self._advance(clock, 0.0, 600.0)

        self.page._progress_widget.freeze_elapsed.assert_not_called()
        self.assertTrue(self.page._is_running)
        self.assertFalse(self.page._state.all_done)

    def test_no_freeze_within_grace_period(self) -> None:
        """終了を確認しても、猶予内は停止しない。"""
        self.proc.poll.return_value = 0
        clock = _Clock(0.0)
        self._advance(clock, 0.0, WorkbenchPage._ORPHANED_EXIT_GRACE_SEC - 0.1)

        self.page._progress_widget.freeze_elapsed.assert_not_called()
        self.assertTrue(self.page._is_running)

    def test_grace_is_measured_from_exit_detection(self) -> None:
        """猶予の起点は監視開始時刻ではなく、終了を確認した時刻である。"""
        grace = WorkbenchPage._ORPHANED_EXIT_GRACE_SEC
        clock = _Clock(0.0)
        self.proc.poll.return_value = None
        self._advance(clock, 0.0, 100.0)

        # t=100.0 で初めて終了を確認する。
        self.proc.poll.return_value = 0
        self._advance(clock, 100.0, 100.0 + grace - 0.1)
        self.page._progress_widget.freeze_elapsed.assert_not_called()

        self._advance(clock, 100.0 + grace + 0.1)
        self.page._progress_widget.freeze_elapsed.assert_called_once_with()


class TestOrphanedExitDetection(_ProcessExitTestBase):
    def test_freeze_after_grace_period_when_stream_never_ends(self) -> None:
        """ストリーム終端が来なくても猶予経過で停止し、異常終了として記録される。"""
        self._trigger_orphaned_exit(returncode=3)

        self.page._progress_widget.freeze_elapsed.assert_called_once_with()
        self.assertFalse(self.page._is_running)
        self.assertTrue(self.page._state.all_done)
        self.assertTrue(self.page._state.aborted)

        warnings = [line for line in self.logged if line.startswith("[WARN]")]
        self.assertEqual(len(warnings), 1, self.logged)
        self.assertIn("3", warnings[0])

    def test_orphaned_exit_does_not_rewrite_running_step_status(self) -> None:
        """実行中 Step の状態表示を完了・失敗へ書き換えない。"""
        self.page._state.prepopulate_workflow_instances(
            [
                WorkflowInstanceSeed(
                    instance_id="wf-a",
                    workflow_id="wf-a",
                    label="WF-A",
                    app_id=None,
                    steps=[("1", "T1")],
                )
            ]
        )
        self.page._state.update_step_status_in_instance("wf-a", "1", "running")

        self._trigger_orphaned_exit()

        step = self.page._state.find_step_in_instance("wf-a", "1")
        assert step is not None
        self.assertEqual(step.status, "running")

    def test_late_process_finished_is_ignored_after_orphaned_exit(self) -> None:
        """遅れて到着したストリーム終端で終了処理を二重実行しない。"""
        self._trigger_orphaned_exit()
        self.page._args_queue = [MagicMock(), MagicMock()]
        self.page._queue_index = 0
        captured: list[int] = []
        self.page.process_finished.connect(captured.append)

        self.page._on_process_finished(0)

        self.assertEqual(self.page._queue_index, 0)
        self.assertEqual(captured, [])
        self.page._progress_widget.freeze_elapsed.assert_called_once_with()

    def test_orphaned_exit_finalizes_session_like_other_exit_paths(self) -> None:
        """異常終了検知も既存の終了経路と同じセッション後始末を伴う。"""
        self.page._maybe_dump_console_log = MagicMock()  # type: ignore[method-assign]

        self._trigger_orphaned_exit()

        self.page._maybe_dump_console_log.assert_called_once_with()

    def test_user_requested_stop_is_not_recorded_as_abnormal(self) -> None:
        """停止要求後の終了は停止するが、異常終了として記録しない。"""
        self.page._stop_requested = True

        self._trigger_orphaned_exit()

        self.page._progress_widget.freeze_elapsed.assert_called_once_with()
        self.assertTrue(self.page._state.all_done)
        self.assertFalse(self.page._state.aborted)
        self.assertEqual([line for line in self.logged if line.startswith("[WARN]")], [])

    def test_mid_queue_completion_does_not_freeze(self) -> None:
        """キューに未実行が残る通常完了では経過時間を停止しない。"""
        self.page._args_queue = [MagicMock(), MagicMock()]
        self.page._queue_index = 0

        self.page._on_process_finished(0)

        self.page._progress_widget.freeze_elapsed.assert_not_called()
        self.assertEqual(self.page._queue_index, 1)


class TestOrphanedExitStateReset(_ProcessExitTestBase):
    def test_start_orchestrators_resets_orphaned_exit_state(self) -> None:
        """新規実行の開始時に前回の終了検知状態が初期化される。"""
        self._trigger_orphaned_exit()
        self.assertTrue(self.page._orphaned_exit_handled)

        args = MagicMock()
        args.to_argv.side_effect = ValueError("test stub")
        args.workflow = "wf_test"
        args.stop_on_fatal = True
        self.page._build_workflow_plan = MagicMock(return_value=[])  # type: ignore[assignment]
        self.page.start_orchestrators([args])

        self.assertFalse(self.page._orphaned_exit_handled)
        self.assertIsNone(self.page._proc_exit_seen_at)


if __name__ == "__main__":
    unittest.main()
