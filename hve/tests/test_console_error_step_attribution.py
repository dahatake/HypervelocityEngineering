"""test_console_error_step_attribution.py — NFR-OBS-05 のテスト。

検証項目:
  1. `Console.error()` / `warning()` が GUI サブプロセス実行時に
     `[hve:ctx:<step_id>] ` マーカーを付与すること
  2. ContextVar 未設定時・非 GUI 実行時はマーカーを付与しないこと
  3. `Console.step_end()` が ContextVar を解除すること
  4. GUI 側パーサが ERROR / WARN 行から step_id を復元できること

根拠: hve-dev/requirement-definition.md §7 NFR-OBS-05
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from console import _CURRENT_EMIT_STEP_ID, Console


class _ConsoleCase(unittest.TestCase):
    def setUp(self) -> None:
        self._token = _CURRENT_EMIT_STEP_ID.set(None)

    def tearDown(self) -> None:
        _CURRENT_EMIT_STEP_ID.reset(self._token)

    def _console(self, *, gui_subprocess: bool) -> Console:
        con = Console(quiet=False)
        con._gui_subprocess = gui_subprocess
        return con

    @staticmethod
    def _capture(fn) -> str:
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            fn()
        return buffer.getvalue()


class TestErrorStepAttribution(_ConsoleCase):
    """NFR-OBS-05: ERROR / WARN 行のステップ帰属。"""

    def test_error_carries_ctx_marker_in_gui_subprocess(self) -> None:
        con = self._console(gui_subprocess=True)
        _CURRENT_EMIT_STEP_ID.set("1.3")
        out = self._capture(lambda: con.error("boom"))
        self.assertTrue(out.startswith("[hve:ctx:1.3] "), out)
        self.assertIn("boom", out)

    def test_warning_carries_ctx_marker_in_gui_subprocess(self) -> None:
        con = self._console(gui_subprocess=True)
        _CURRENT_EMIT_STEP_ID.set("2.1/SVC-01")
        out = self._capture(lambda: con.warning("careful"))
        self.assertTrue(out.startswith("[hve:ctx:2.1/SVC-01] "), out)

    def test_no_marker_when_context_unset(self) -> None:
        con = self._console(gui_subprocess=True)
        out = self._capture(lambda: con.error("boom"))
        self.assertFalse(out.startswith("[hve:ctx:"), out)

    def test_no_marker_outside_gui_subprocess(self) -> None:
        con = self._console(gui_subprocess=False)
        _CURRENT_EMIT_STEP_ID.set("1.3")
        out = self._capture(lambda: con.error("boom"))
        self.assertFalse(out.startswith("[hve:ctx:"), out)

    def test_error_is_still_written_to_stderr(self) -> None:
        con = self._console(gui_subprocess=True)
        _CURRENT_EMIT_STEP_ID.set("1.3")
        out = self._capture(lambda: con.error("boom"))
        self.assertIn("ERROR", out)

    def test_quiet_still_emits_error(self) -> None:
        con = Console(quiet=True)
        con._gui_subprocess = True
        _CURRENT_EMIT_STEP_ID.set("1.3")
        out = self._capture(lambda: con.error("boom"))
        self.assertIn("boom", out)


class TestStepEndClearsContext(_ConsoleCase):
    """NFR-OBS-05: Step 完了後の行を完了済み Step へ帰属させない。"""

    def test_step_end_clears_context_var(self) -> None:
        con = self._console(gui_subprocess=True)
        con.step_start("1.3", "deploy")
        self.assertEqual(_CURRENT_EMIT_STEP_ID.get(), "1.3")
        con.step_end("1.3", "failed", elapsed=0.0)
        self.assertIsNone(_CURRENT_EMIT_STEP_ID.get())

    def test_error_after_step_end_has_no_marker(self) -> None:
        con = self._console(gui_subprocess=True)
        con.step_start("1.3", "deploy")
        con.step_end("1.3", "success", elapsed=0.0)
        out = self._capture(lambda: con.error("after"))
        self.assertFalse(out.startswith("[hve:ctx:"), out)

    def test_step_end_of_other_step_does_not_clear(self) -> None:
        """並列実行で他 Step の完了が現在の帰属を壊さないこと。"""
        con = self._console(gui_subprocess=True)
        con.step_start("1.3", "deploy")
        con.step_end("9.9", "success", elapsed=0.0)
        self.assertEqual(_CURRENT_EMIT_STEP_ID.get(), "1.3")


class TestGuiParserRecoversStepId(unittest.TestCase):
    """GUI 側パーサが ERROR / WARN 行から step_id を復元できること。"""

    @staticmethod
    def _state():
        from hve.gui.workbench_state import WorkbenchState

        return WorkbenchState(workflow_id="asdw-web", run_id="r1", model="test")

    def test_workbench_logger_extracts_step_id_from_error_line(self) -> None:
        from hve.gui.workbench_logger import process_log_line

        state = self._state()
        process_log_line(state, "[hve:ctx:1.3] [00:38:28] ❌ ERROR: boom")
        actions = list(state.user_actions)
        self.assertTrue(actions)
        self.assertEqual(actions[-1].step_id, "1.3")
        self.assertEqual(actions[-1].level, "ERROR")

    def test_workbench_logger_extracts_step_id_from_warn_line(self) -> None:
        from hve.gui.workbench_logger import process_log_line

        state = self._state()
        process_log_line(state, "[hve:ctx:2.1] [00:38:28] ⚠️ careful")
        actions = list(state.user_actions)
        self.assertTrue(actions)
        self.assertEqual(actions[-1].step_id, "2.1")
        self.assertEqual(actions[-1].level, "WARN")

    def test_marker_is_removed_from_displayed_message(self) -> None:
        from hve.gui.workbench_logger import process_log_line

        state = self._state()
        process_log_line(state, "[hve:ctx:1.3] [00:38:28] ❌ ERROR: boom")
        self.assertNotIn("hve:ctx", list(state.user_actions)[-1].message)


if __name__ == "__main__":
    unittest.main()
