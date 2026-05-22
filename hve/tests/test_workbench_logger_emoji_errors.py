"""hve.gui.workbench_logger.process_log_line の絵文字プレフィックス fallback テスト。

`_LOG_PATTERN` にマッチしない以下の3種類のログ行が、
`state.add_user_action` 経由で「実行中の課題」へ反映されることを保証する:

  1. `[HH:MM:SS] ❌ ERROR: <msg>`              (console.py error())
  2. `[HH:MM:SS] ⚠️ Session error [...]: ...`  (console.py session_error())
  3. `[HH:MM:SS] ❌ [step] Sub-agent 失敗: name - error`
"""

from __future__ import annotations

from hve.gui.workbench_logger import process_log_line
from hve.gui.workbench_state import WorkbenchState


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r", model="m")


class TestEmojiErrorFallback:
    def test_error_line_with_timestamp_recorded(self) -> None:
        s = _state()
        process_log_line(s, "[00:38:11] ❌ ERROR: completion-report.md が存在しない")
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "ERROR"
        assert "completion-report.md" in a.message
        assert a.timestamp == "00:38:11"

    def test_error_line_without_message_is_skipped(self) -> None:
        s = _state()
        process_log_line(s, "[00:38:11] ❌ ERROR: ")
        assert s.user_actions == []

    def test_error_line_without_timestamp_uses_now(self) -> None:
        s = _state()
        process_log_line(s, "❌ ERROR: boom")
        assert len(s.user_actions) == 1
        # フォールバック現在時刻が HH:MM:SS 形式で入る
        assert len(s.user_actions[0].timestamp) == 8


class TestSessionWarnFallback:
    def test_session_error_recorded_as_warn(self) -> None:
        s = _state()
        process_log_line(
            s, "[00:40:00]   \u26A0\uFE0F  Session error [auth]: token expired"
        )
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "WARN"
        assert "Session error" in a.message

    def test_unrelated_warning_emoji_ignored(self) -> None:
        s = _state()
        # `Session error` を含まない単なる警告は WARN として記録しない
        process_log_line(s, "[00:41:00]   \u26A0\uFE0F  disk almost full")
        assert s.user_actions == []


class TestSubagentFailedFallback:
    def test_subagent_failed_includes_step_name_and_error(self) -> None:
        s = _state()
        process_log_line(
            s,
            "[00:38:11] ❌ [6] Sub-agent 失敗: split-002 (Arch-X) - completion-report.md が存在しない",
        )
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "ERROR"
        assert a.step_id == "6"
        assert "split-002" in a.message
        # エラー詳細が失われないこと
        assert "completion-report.md" in a.message
        assert a.timestamp == "00:38:11"

    def test_subagent_failed_without_error_detail(self) -> None:
        s = _state()
        process_log_line(
            s, "[00:38:11] ❌ [6] Sub-agent 失敗: split-002"
        )
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "ERROR"
        assert a.message == "Sub-agent 失敗: split-002"

    def test_standard_log_line_still_works(self) -> None:
        """fallback の追加が標準パスを壊していないことを確認。"""
        s = _state()
        process_log_line(s, "[00:38:11] step-1: INFO: hello")
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "INFO"
        assert a.step_id == "step-1"
        assert a.message == "hello"
