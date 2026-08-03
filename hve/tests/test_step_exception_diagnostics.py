"""test_step_exception_diagnostics.py — NFR-OBS-08 のテスト。

検証項目:
  1. Step 実行の包括例外ハンドラが例外型名を出力すること
  2. 例外メッセージが空でも型名から原因種別を特定できること

実データ根拠: work/run/20260722T060338-401c6f / 20260722T025029-a51cc7 の
`Step.1.1 実行中にエラーが発生しました: '1.1'` は例外型が失われており、
2 ラン連続で同じ表示のまま原因を特定できなかった。

根拠: hve-dev/requirement-definition.md §7 NFR-OBS-08
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from runner import format_exception_for_log


class TestFormatExceptionForLog(unittest.TestCase):
    """NFR-OBS-08: 例外の型情報を保持する。"""

    def test_includes_exception_type_name(self) -> None:
        formatted = format_exception_for_log(KeyError("1.1"))
        self.assertIn("KeyError", formatted)

    def test_includes_exception_message(self) -> None:
        formatted = format_exception_for_log(ValueError("bad value"))
        self.assertIn("bad value", formatted)

    def test_empty_message_still_identifies_type(self) -> None:
        formatted = format_exception_for_log(RuntimeError())
        self.assertIn("RuntimeError", formatted)

    def test_key_error_regression_case_is_diagnosable(self) -> None:
        """実ログ `... : '1.1'` だけでは型が判らなかったケース。"""
        formatted = format_exception_for_log(KeyError("1.1"))
        self.assertNotEqual(formatted.strip(), "'1.1'")
        self.assertTrue(formatted.startswith("KeyError"), formatted)


class TestRunnerUsesFormatter(unittest.TestCase):
    """runner の包括ハンドラが本ヘルパを使うこと。"""

    def test_runner_step_handler_uses_formatter(self) -> None:
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "runner.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "実行中にエラーが発生しました: {format_exception_for_log(exc)}", source
        )

    def test_orchestrator_review_handler_uses_formatter(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1] / "orchestrator.py"
        ).read_text(encoding="utf-8")
        self.assertIn("format_exception_for_log(exc)", source)


if __name__ == "__main__":
    unittest.main()
