"""hve.gui.workbench_logger の `✗ ツール失敗:` パターン fallback テスト。

`_LOG_PATTERN` にマッチしない以下の形式のログ行が、
`state.add_user_action` 経由で「実行中の課題」へ反映されることを保証する:

  `  ✗ [step_id] ツール失敗: <error_msg>`   (console.py tool_result(success=False))
"""

from __future__ import annotations

from hve.gui.workbench_logger import process_log_line
from hve.gui.workbench_state import WorkbenchState


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r", model="m")


class TestToolFailedFallback:
    def test_tool_failed_with_step_id_recorded(self) -> None:
        s = _state()
        process_log_line(s, "  ✗ [2.2] ツール失敗: timeout")
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "ERROR"
        assert a.message == "timeout"
        assert a.step_id == "2.2"
        assert a.category == "ツール失敗"

    def test_tool_failed_with_timestamp_and_complex_step_id(self) -> None:
        s = _state()
        process_log_line(
            s,
            "[15:25:23]   ✗ [3.0TC/APP-07-S010] ツール失敗: Path already exists",
        )
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.timestamp == "15:25:23"
        assert a.step_id == "3.0TC/APP-07-S010"
        assert a.message == "Path already exists"

    def test_tool_failed_without_step_id(self) -> None:
        s = _state()
        process_log_line(s, "  ✗ ツール失敗: rg: no such file")
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.step_id is None
        assert "rg: no such file" in a.message

    def test_standard_log_pattern_does_not_double_count(self) -> None:
        """`_LOG_PATTERN` にマッチする標準形式行は新パターンでは処理されない。"""
        s = _state()
        # 標準形式: [HH:MM:SS] step: LEVEL: msg
        process_log_line(s, "[09:00:00] 2.5: INFO: 通常メッセージ")
        # 1 件のみ（標準パスで追加され、TOOL_FAILED では追加されない）
        assert len(s.user_actions) == 1
        assert s.user_actions[0].message == "通常メッセージ"

    def test_tool_failed_with_tool_name_prefix(self) -> None:
        """T-M5: runner が tool_name を error_msg に前置した形式も処理できる。"""
        s = _state()
        process_log_line(s, "  ✗ [1] ツール失敗: view: timeout")
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "ERROR"
        assert a.step_id == "1"
        assert a.category == "ツール失敗"
        # tool_name を含む全体が message に格納される
        assert a.message == "view: timeout"
