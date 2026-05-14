"""Phase 7-8 追加: Controller の Live 起動経路・pause/resume・flush_on_exit・
history 伝播の統合テスト。

screen=True が pytest 配下では失敗する前提で、Live を直接 mock して
controller の制御フローのみ検証する。
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from hve.workbench import RingBuffer, StepView, WorkbenchController, WorkbenchState


def _state() -> WorkbenchState:
    return WorkbenchState(
        workflow_id="wf",
        run_id="r1",
        model="m",
        steps=[StepView(id="1", title="t", status="pending")],
        body_window=12,
    )


class TestControllerLiveActiveBranch(unittest.TestCase):
    """Live が起動できたケース（active=True）の経路を mock で検証する。"""

    def test_keyreader_started_when_opt_in_and_active(self):
        wb = WorkbenchController(_state())
        with patch.dict(os.environ, {"HVE_WORKBENCH_KEYREADER": "1"}), \
             patch("hve.workbench.controller.Live") as mock_live_cls, \
             patch.object(WorkbenchController, "_can_force_active", create=True, return_value=True):
            mock_live_inst = MagicMock()
            mock_live_cls.return_value = mock_live_inst
            # __enter__ で Live を成功させる
            mock_live_inst.__enter__.return_value = mock_live_inst
            # KeyReader の enabled は環境依存だが、ここでは _key_reader が
            # 生成されたかのみ確認する
            wb.__enter__()
            try:
                self.assertTrue(wb.active)
                self.assertIsNotNone(wb._key_reader)
            finally:
                wb.__exit__(None, None, None)

    def test_keyreader_not_created_when_live_fails(self):
        wb = WorkbenchController(_state())
        with patch("hve.workbench.controller.Live") as mock_live_cls:
            mock_live_cls.side_effect = RuntimeError("no screen")
            wb.__enter__()
            try:
                self.assertFalse(wb.active)
                self.assertIsNone(wb._key_reader)
            finally:
                wb.__exit__(None, None, None)


class TestPauseResumeSync(unittest.TestCase):
    def test_pause_stops_keyreader(self):
        wb = WorkbenchController(_state())
        # active=True 状態を擬似的に作る
        wb._active = True
        wb._live = MagicMock()
        wb._key_reader = MagicMock()
        wb.pause()
        wb._key_reader.stop.assert_called_once()
        wb._live.stop.assert_called_once()
        self.assertFalse(wb._active)

    def test_resume_starts_keyreader_when_live_resumed(self):
        wb = WorkbenchController(_state())
        wb._active = False
        wb._live = MagicMock()
        wb._key_reader = MagicMock()
        wb.resume()
        wb._live.start.assert_called_once()
        self.assertTrue(wb._active)
        wb._key_reader.start.assert_called_once()

    def test_resume_does_not_start_keyreader_if_live_failed(self):
        wb = WorkbenchController(_state())
        wb._active = False
        wb._live = MagicMock()
        wb._live.start.side_effect = RuntimeError("boom")
        wb._key_reader = MagicMock()
        wb.resume()
        self.assertFalse(wb._active)
        wb._key_reader.start.assert_not_called()


class TestFlushOnExit(unittest.TestCase):
    def test_flush_on_exit_writes_buffer_to_stdout(self):
        import io
        import contextlib

        state = _state()
        state.body.append("line1")
        state.body.append("line2")
        wb = WorkbenchController(state, flush_on_exit=True)
        # active=False のまま stop（Live 起動失敗パス）→ buffer + fallback を flush
        wb._fallback_lines.append("fallback1")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            wb.stop()
        out = buf.getvalue()
        self.assertIn("line1", out)
        self.assertIn("line2", out)
        self.assertIn("fallback1", out)

    def test_no_flush_when_disabled(self):
        import io
        import contextlib

        state = _state()
        state.body.append("line1")
        wb = WorkbenchController(state, flush_on_exit=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            wb.stop()
        self.assertEqual(buf.getvalue(), "")


class TestHistoryCapacityPropagation(unittest.TestCase):
    """orchestrator が --workbench-history で RingBuffer を差し替える挙動を
    state 直接生成で再現する単体テスト。"""

    def test_state_default_capacity(self):
        s = _state()
        self.assertEqual(s.body.capacity, 10000)

    def test_state_replace_buffer_with_custom_capacity(self):
        s = _state()
        s.body = RingBuffer(capacity=500)
        self.assertEqual(s.body.capacity, 500)
        for i in range(600):
            s.body.append(f"l{i}")
        # 最大 500 行に切り詰められる
        self.assertEqual(len(s.body), 500)


if __name__ == "__main__":
    unittest.main()
