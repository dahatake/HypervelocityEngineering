"""test_qa_ipc_manager.py — QAIpcManager の単体テスト (offscreen)。

実行: QT_QPA_PLATFORM=offscreen pytest hve/gui/tests/test_qa_ipc_manager.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication

from hve.gui.qa_ipc_manager import QAIpcManager


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _process_events_for(ms: int) -> None:
    """指定ミリ秒間 Qt イベントループを回す。"""
    app = _get_app()
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.05)


class TestQAIpcManager(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        self._tmp = tempfile.mkdtemp(prefix="hve-qa-ipc-mgr-test-")
        self.ipc_dir = Path(self._tmp)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_request_json_triggers_signal(self) -> None:
        """request JSON 配置で questionnaire_ready が発火する。"""
        mgr = QAIpcManager(self.ipc_dir)
        captured = []
        mgr.questionnaire_ready.connect(
            lambda step, path, ipc: captured.append((step, path, ipc))
        )
        # request JSON 配置
        req = {
            "schema_version": 1,
            "step_id": "1.1",
            "pid": 12345,
            "created_at": "2026-05-18T10:00:00Z",
            "questionnaire_path": str(self.ipc_dir / "1.1.questionnaire.md"),
            "qa_input_timeout_seconds": 3600,
        }
        (self.ipc_dir / "1.1.request.json").write_text(
            json.dumps(req), encoding="utf-8"
        )
        _process_events_for(2000)  # poll timer が動くまで待機
        self.assertTrue(captured, "questionnaire_ready シグナルが発火していない")
        step_id, q_path, ipc_dir = captured[0]
        self.assertEqual(step_id, "1.1")
        self.assertTrue(q_path.endswith("1.1.questionnaire.md"))
        mgr.stop_and_cleanup()

    def test_write_answers(self) -> None:
        mgr = QAIpcManager(self.ipc_dir)
        ok = mgr.write_answers("1.1", "1: A\n2: B\n")
        self.assertTrue(ok)
        ans = self.ipc_dir / "1.1.answers.md"
        self.assertTrue(ans.exists())
        self.assertIn("1: A", ans.read_text(encoding="utf-8"))
        mgr.stop_and_cleanup()

    def test_write_cancel(self) -> None:
        mgr = QAIpcManager(self.ipc_dir)
        ok = mgr.write_cancel("1.1")
        self.assertTrue(ok)
        self.assertTrue((self.ipc_dir / "1.1.cancel").exists())
        mgr.stop_and_cleanup()

    def test_subprocess_termination_emits_signal(self) -> None:
        """subprocess.poll() が None でなくなるとシグナル発火。"""
        mock_popen = MagicMock()
        # 最初は poll=None、3 回目で 0 を返す
        mock_popen.poll.side_effect = [None, None, 0, 0, 0]
        mgr = QAIpcManager(self.ipc_dir, popen=mock_popen)
        terminated = []
        mgr.subprocess_terminated.connect(lambda: terminated.append(True))
        _process_events_for(4000)  # 1s 間隔の poll が 3 回以上回るまで
        self.assertTrue(terminated, "subprocess_terminated が発火していない")
        mgr.stop_and_cleanup()

    def test_duplicate_request_not_re_emitted(self) -> None:
        """同じ request JSON は 2 度発火しない。"""
        mgr = QAIpcManager(self.ipc_dir)
        captured = []
        mgr.questionnaire_ready.connect(
            lambda step, path, ipc: captured.append(step)
        )
        req_path = self.ipc_dir / "1.1.request.json"
        req = {
            "schema_version": 1,
            "step_id": "1.1",
            "pid": 1,
            "created_at": "x",
            "questionnaire_path": str(self.ipc_dir / "1.1.questionnaire.md"),
        }
        req_path.write_text(json.dumps(req), encoding="utf-8")
        _process_events_for(2000)
        _process_events_for(2000)  # 再度 polling
        self.assertEqual(len(captured), 1)
        mgr.stop_and_cleanup()

    def test_stop_and_cleanup_removes_ipc_dir(self) -> None:
        mgr = QAIpcManager(self.ipc_dir)
        # 何か書く
        (self.ipc_dir / "test.txt").write_text("x", encoding="utf-8")
        mgr.stop_and_cleanup()
        self.assertFalse(self.ipc_dir.exists())

    def test_multiple_sequential_requests_emit_separately(self) -> None:
        """連続して 2 つの request JSON を配置すると、それぞれ別個に発火する。"""
        mgr = QAIpcManager(self.ipc_dir)
        captured: list = []
        mgr.questionnaire_ready.connect(
            lambda step, path, ipc: captured.append(step)
        )
        # 1 つめ
        (self.ipc_dir / "1.1.request.json").write_text(
            json.dumps({
                "step_id": "1.1",
                "questionnaire_path": str(self.ipc_dir / "1.1.questionnaire.md"),
            }),
            encoding="utf-8",
        )
        _process_events_for(2000)
        # 2 つめ（別 step_id）
        (self.ipc_dir / "1.2.request.json").write_text(
            json.dumps({
                "step_id": "1.2",
                "questionnaire_path": str(self.ipc_dir / "1.2.questionnaire.md"),
            }),
            encoding="utf-8",
        )
        _process_events_for(2000)
        self.assertIn("1.1", captured)
        self.assertIn("1.2", captured)
        self.assertEqual(len(captured), 2)
        mgr.stop_and_cleanup()


if __name__ == "__main__":
    unittest.main()
