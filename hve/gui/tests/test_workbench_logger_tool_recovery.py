"""test_workbench_logger_tool_recovery.py — NFR-OBS-07 のテスト。

検証項目:
  1. 同一 Step・同一ツールの失敗後に同ツールが成功したら課題を解決済みへ降格すること
  2. 別 Step / 別ツールの成功では降格しないこと
  3. 降格後も失敗事実の記録自体は残ること（履歴の消失を防ぐ）
  4. 相関に使う `tool_result` 構造化イベントを runner が発火すること

実データ根拠: work/run/20260726T210312-2e97d7/console-log.txt の
`✗ [1.1] ツール失敗: edit: Multiple matches found` は次ターンで Agent が
自力回復しており、未解決の ERROR として残置すべきではなかった。

根拠: hve-dev/requirement-definition.md §7 NFR-OBS-07
"""

from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.gui.workbench_logger import process_log_line
from hve.gui.workbench_state import WorkbenchState


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="asdw-web", run_id="r1", model="test")


def _tool_failures(state: WorkbenchState) -> list:
    return [a for a in state.user_actions if a.category == "ツール失敗"]


def _tool_result_line(step: str, tool_name: str, success: bool) -> str:
    payload = {
        "kind": "tool_result",
        "step": step,
        "success": success,
        "tool_name": tool_name,
    }
    return "[hve:stats] " + json.dumps(payload, ensure_ascii=False, sort_keys=True)


class TestToolFailureRecovery(unittest.TestCase):
    """NFR-OBS-07: 回復済みツール失敗の降格。"""

    FAIL_LINE = "[hve:ctx:1.1] [21:14:39] ✗ [1.1] ツール失敗: edit: Multiple matches found"

    def test_failure_is_recorded_as_error(self) -> None:
        state = _state()
        process_log_line(state, self.FAIL_LINE)
        failures = _tool_failures(state)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].level, "ERROR")
        self.assertEqual(failures[0].step_id, "1.1")

    def test_same_tool_success_downgrades_failure(self) -> None:
        state = _state()
        process_log_line(state, self.FAIL_LINE)
        process_log_line(state, _tool_result_line("1.1", "edit", True))
        failures = _tool_failures(state)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].level, "INFO")
        self.assertIn("回復", failures[0].message)

    def test_other_tool_success_does_not_downgrade(self) -> None:
        state = _state()
        process_log_line(state, self.FAIL_LINE)
        process_log_line(state, _tool_result_line("1.1", "view", True))
        self.assertEqual(_tool_failures(state)[0].level, "ERROR")

    def test_other_step_success_does_not_downgrade(self) -> None:
        state = _state()
        process_log_line(state, self.FAIL_LINE)
        process_log_line(state, _tool_result_line("2.1", "edit", True))
        self.assertEqual(_tool_failures(state)[0].level, "ERROR")

    def test_failed_tool_result_does_not_downgrade(self) -> None:
        state = _state()
        process_log_line(state, self.FAIL_LINE)
        process_log_line(state, _tool_result_line("1.1", "edit", False))
        self.assertEqual(_tool_failures(state)[0].level, "ERROR")

    def test_failure_record_is_preserved_after_downgrade(self) -> None:
        state = _state()
        process_log_line(state, self.FAIL_LINE)
        process_log_line(state, _tool_result_line("1.1", "edit", True))
        failures = _tool_failures(state)
        self.assertEqual(len(failures), 1)
        self.assertIn("Multiple matches found", failures[0].message)

    def test_success_without_prior_failure_creates_no_action(self) -> None:
        state = _state()
        before = len(state.user_actions)
        process_log_line(state, _tool_result_line("1.1", "edit", True))
        self.assertEqual(len(state.user_actions), before)

    def test_repeated_failure_then_success_downgrades_all(self) -> None:
        state = _state()
        process_log_line(state, self.FAIL_LINE)
        process_log_line(state, self.FAIL_LINE)
        process_log_line(state, _tool_result_line("1.1", "edit", True))
        self.assertTrue(all(a.level == "INFO" for a in _tool_failures(state)))

    def test_stats_line_is_not_shown_as_body(self) -> None:
        state = _state()
        before = len(state.body)
        process_log_line(state, _tool_result_line("1.1", "edit", True))
        self.assertEqual(len(state.body), before)


class TestRunnerEmitsToolResultEvent(unittest.TestCase):
    """runner が相関用の `tool_result` イベントを発火すること。"""

    def test_runner_emits_tool_result_stats_event(self) -> None:
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        source = (repo_root / "hve" / "runner.py").read_text(encoding="utf-8")
        self.assertIn('"tool_result"', source)


class TestEditUniquenessGuidance(unittest.TestCase):
    """`edit` の一意化ガイダンスがリポジトリ規範に存在すること。"""

    def test_guidance_exists_in_common_preamble_skill(self) -> None:
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        skill = repo_root / ".github" / "skills" / "agent-common-preamble" / "SKILL.md"
        self.assertTrue(skill.is_file(), f"{skill} が存在しない")
        text = skill.read_text(encoding="utf-8")
        self.assertIn("Multiple matches", text)


if __name__ == "__main__":
    unittest.main()
