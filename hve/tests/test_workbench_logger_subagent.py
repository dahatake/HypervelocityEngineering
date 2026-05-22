"""hve.gui.workbench_logger.parse_subagent_event のユニットテスト。

console.subagent_started/_completed/_failed が出力する確定行
（例: ``▶ [step1] Sub-agent: code-reviewer``）を解析できるかを確認する。
"""

from __future__ import annotations

import pytest

from hve.gui.workbench_logger import (
    parse_log_line,
    parse_subagent_event,
)


class TestParseSubagentEventStart:
    def test_start_with_step_and_timestamp(self) -> None:
        line = "[15:30:45]   ▶ [step-1] Sub-agent: code-reviewer"
        assert parse_subagent_event(line) == ("step-1", "code-reviewer", "running")

    def test_start_without_timestamp(self) -> None:
        line = "  ▶ [step-1] Sub-agent: code-reviewer"
        assert parse_subagent_event(line) == ("step-1", "code-reviewer", "running")

    def test_start_without_step(self) -> None:
        line = "  ▶ Sub-agent: tdd-guide"
        assert parse_subagent_event(line) == (None, "tdd-guide", "running")

    def test_start_name_with_spaces(self) -> None:
        line = "  ▶ [s2] Sub-agent: My Long Agent Name"
        assert parse_subagent_event(line) == ("s2", "My Long Agent Name", "running")


class TestParseSubagentEventDone:
    def test_done_with_step(self) -> None:
        line = "[15:31:00]   ✅ [step-1] Sub-agent 完了: code-reviewer"
        assert parse_subagent_event(line) == ("step-1", "code-reviewer", "done")

    def test_done_without_step(self) -> None:
        line = "  ✅ Sub-agent 完了: tdd-guide"
        assert parse_subagent_event(line) == (None, "tdd-guide", "done")


class TestParseSubagentEventFailed:
    def test_failed_with_error(self) -> None:
        line = "[15:31:00]   ❌ [step-1] Sub-agent 失敗: code-reviewer - timeout"
        assert parse_subagent_event(line) == ("step-1", "code-reviewer", "failed")

    def test_failed_without_error(self) -> None:
        line = "  ❌ [step-1] Sub-agent 失敗: code-reviewer"
        assert parse_subagent_event(line) == ("step-1", "code-reviewer", "failed")

    def test_failed_without_step(self) -> None:
        line = "  ❌ Sub-agent 失敗: tdd-guide - boom"
        assert parse_subagent_event(line) == (None, "tdd-guide", "failed")


class TestParseSubagentEventNoMatch:
    @pytest.mark.parametrize(
        "line",
        [
            "",
            "  ",
            "[15:30:45] step-1: INFO: 通常のログ行",
            "▶ Step-1 started",  # Sub-agent: が無い
            "✅ 完了しました",
            "❌ エラー: something",
            "ランダムなテキスト",
        ],
    )
    def test_not_matched(self, line: str) -> None:
        assert parse_subagent_event(line) is None


class TestNoRegressionOnStandardLog:
    """既存の _LOG_PATTERN にマッチする通常ログ行と競合しないこと。"""

    def test_standard_log_still_parses(self) -> None:
        line = "[15:30:45] step-1: INFO: 開始しました"
        ts, sid, lvl, msg = parse_log_line(line)
        assert ts == "15:30:45"
        assert sid == "step-1"
        assert lvl == "INFO"
        assert msg == "開始しました"
        # かつ Sub-agent 行としてはマッチしない
        assert parse_subagent_event(line) is None
