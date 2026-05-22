"""WorkbenchPage の致命的エラー（fatal）検知・キュー停止ロジックのテスト。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.page_workbench import WorkbenchPage  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


class TestFatalMarkerDetection(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()

    def test_initial_state(self) -> None:
        self.assertFalse(self.page.was_fatal())
        self.assertFalse(self.page.was_fatal_marker_seen())
        self.assertIsNone(self.page.fatal_info())

    def test_valid_json_marker(self) -> None:
        self.page._detect_fatal_marker(
            '[hve:fatal] {"kind":"fatal_abort","exception_type":"FileNotFoundError","message":"foo.yaml"}'
        )
        self.assertTrue(self.page.was_fatal())
        info = self.page.fatal_info() or {}
        self.assertEqual(info.get("exception_type"), "FileNotFoundError")
        self.assertEqual(info.get("message"), "foo.yaml")

    def test_non_json_payload_falls_back(self) -> None:
        self.page._detect_fatal_marker("[hve:fatal] plain text reason")
        self.assertTrue(self.page.was_fatal())
        info = self.page.fatal_info() or {}
        self.assertEqual(info.get("exception_type"), "FatalError")
        self.assertEqual(info.get("message"), "plain text reason")
        self.assertEqual(info.get("raw_payload"), "plain text reason")

    def test_marker_must_be_line_head(self) -> None:
        """C2: 行頭一致限定。モデル応答内の引用は偽陽性にならない。"""
        self.page._detect_fatal_marker("[12:34:56] see [hve:fatal] event for details")
        self.assertFalse(self.page.was_fatal())
        self.page._detect_fatal_marker('user said: [hve:fatal] {"x":1}')
        self.assertFalse(self.page.was_fatal())

    def test_no_marker_keeps_state_clean(self) -> None:
        self.page._detect_fatal_marker("normal log line")
        self.page._detect_fatal_marker('[hve:stats] {"a":1}')
        self.assertFalse(self.page.was_fatal())

    def test_detection_is_idempotent(self) -> None:
        self.page._detect_fatal_marker(
            '[hve:fatal] {"exception_type":"FirstError","message":"first"}'
        )
        self.page._detect_fatal_marker(
            '[hve:fatal] {"exception_type":"SecondError","message":"second"}'
        )
        info = self.page.fatal_info() or {}
        self.assertEqual(info.get("exception_type"), "FirstError")

    def test_fatal_info_returns_readonly_mapping(self) -> None:
        """B6: 戻り値は読み取り専用 Mapping を返し、書き換え不可。"""
        self.page._detect_fatal_marker('[hve:fatal] {"exception_type":"E","message":"m"}')
        info1 = self.page.fatal_info()
        assert info1 is not None
        with self.assertRaises(TypeError):
            info1["exception_type"] = "tampered"  # type: ignore[index]
        info2 = self.page.fatal_info()
        assert info2 is not None
        self.assertEqual(info2.get("exception_type"), "E")


class TestFatalSubprocessTermination(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()

    def test_terminate_called_when_running(self) -> None:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        self.page._reader = MagicMock()
        self.page._reader._proc = mock_proc
        self.page._is_running = True

        self.page._terminate_subprocess_for_fatal()
        mock_proc.terminate.assert_called_once()

    def test_no_terminate_when_not_running(self) -> None:
        mock_proc = MagicMock()
        self.page._reader = MagicMock()
        self.page._reader._proc = mock_proc
        self.page._is_running = False

        self.page._terminate_subprocess_for_fatal()
        mock_proc.terminate.assert_not_called()

    def test_no_terminate_when_no_reader(self) -> None:
        self.page._reader = None
        self.page._is_running = True
        self.page._terminate_subprocess_for_fatal()

    def test_terminate_swallows_oserror(self) -> None:
        mock_proc = MagicMock()
        mock_proc.terminate.side_effect = OSError("test")
        mock_proc.poll.return_value = 0
        self.page._reader = MagicMock()
        self.page._reader._proc = mock_proc
        self.page._is_running = True
        self.page._terminate_subprocess_for_fatal()
        mock_proc.terminate.assert_called_once()


class TestFatalQueueStop(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()

    def test_fatal_clears_remaining_queue(self) -> None:
        args1 = MagicMock()
        args2 = MagicMock()
        args3 = MagicMock()
        self.page._args_queue = [args1, args2, args3]
        self.page._queue_index = 1
        self.page._current_workflow_id = "wf2"
        self.page._workflow_status = {"wf1": "完了", "wf2": "", "wf3": ""}
        self.page._is_running = True
        self.page._fatal_detected = True
        self.page._stop_on_fatal = True
        self.page._fatal_info = {"exception_type": "E", "message": "m"}

        captured: list = []
        self.page.process_finished.connect(lambda rc: captured.append(rc))

        self.page._on_process_finished(0)

        self.assertEqual(len(self.page._args_queue), 2)
        self.assertFalse(self.page._is_running)
        self.assertEqual(captured, [0])

    def test_fatal_workflow_status_label(self) -> None:
        self.page._args_queue = [MagicMock()]
        self.page._queue_index = 0
        self.page._current_workflow_id = "wf1"
        self.page._workflow_status = {"wf1": ""}
        self.page._is_running = True
        self.page._fatal_detected = True
        self.page._stop_on_fatal = True
        self.page._fatal_info = {"exception_type": "E", "message": "m"}
        self.page._progress_widget = MagicMock()
        self.page._on_process_finished(0)
        self.assertNotEqual(self.page._workflow_status.get("wf1"), "完了")
        self.assertIn("致命的", self.page._workflow_status.get("wf1") or "")


class TestStartOrchestratorsResetsFatalState(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()

    def test_fatal_state_reset_on_new_run(self) -> None:
        self.page._fatal_detected = True
        self.page._fatal_info = {"exception_type": "Old", "message": "old"}
        self.page._is_running = False
        args = MagicMock()
        args.to_argv.side_effect = ValueError("test stub")
        args.workflow = "wf_test"
        args.stop_on_fatal = True
        self.page._build_workflow_plan = MagicMock(return_value=[])  # type: ignore[assignment]
        try:
            self.page.start_orchestrators([args])
        except Exception:
            pass
        self.assertFalse(self.page._fatal_detected)
        self.assertIsNone(self.page._fatal_info)


class TestStopOnFatalToggle(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self._prev_env = os.environ.pop("HVE_GUI_STOP_ON_FATAL", None)
        self.page = WorkbenchPage()

    def tearDown(self) -> None:
        if self._prev_env is not None:
            os.environ["HVE_GUI_STOP_ON_FATAL"] = self._prev_env
        else:
            os.environ.pop("HVE_GUI_STOP_ON_FATAL", None)

    def _start_with(self, *, stop_on_fatal: bool) -> None:
        self.page._is_running = False
        args = MagicMock()
        args.to_argv.side_effect = ValueError("test stub")
        args.workflow = "wf_test"
        args.stop_on_fatal = stop_on_fatal
        self.page._build_workflow_plan = MagicMock(return_value=[])  # type: ignore[assignment]
        try:
            self.page.start_orchestrators([args])
        except Exception:
            pass

    def test_default_true_from_args(self) -> None:
        self._start_with(stop_on_fatal=True)
        self.assertTrue(self.page._stop_on_fatal)

    def test_args_false_disables_stop(self) -> None:
        self._start_with(stop_on_fatal=False)
        self.assertFalse(self.page._stop_on_fatal)

    def test_env_var_override_off(self) -> None:
        os.environ["HVE_GUI_STOP_ON_FATAL"] = "0"
        self._start_with(stop_on_fatal=True)
        self.assertFalse(self.page._stop_on_fatal)

    def test_env_var_override_on(self) -> None:
        os.environ["HVE_GUI_STOP_ON_FATAL"] = "1"
        self._start_with(stop_on_fatal=False)
        self.assertTrue(self.page._stop_on_fatal)

    def test_was_fatal_false_when_stop_disabled(self) -> None:
        self._start_with(stop_on_fatal=False)
        self.page._on_line_received(
            '[hve:fatal] {"exception_type":"E","message":"m"}'
        )
        self.assertTrue(self.page.was_fatal_marker_seen())
        self.assertFalse(self.page.was_fatal())


if __name__ == "__main__":
    unittest.main()
