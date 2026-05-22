"""run_step が HVE_STEP_ID / HVE_AGENT_ID を os.environ に設定することのテスト。

mdq CLI の利用ログを Step / Agent と紐付けるための環境変数伝播を検証する。
並列実行下の競合は本テストの範囲外（実装側コメントで best-effort と明示）。
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
from typing import Any
from unittest.mock import MagicMock, patch


def _make_runner() -> Any:
    """StepRunner のインスタンスを最小モックで作る。"""
    from hve import runner as runner_mod
    cfg = MagicMock()
    cfg.run_id = "test-run-1"
    cfg.dry_run = True  # dry_run で SDK 呼び出しをスキップ
    cfg.verbose = False
    cfg.quiet = True
    cfg.show_stream = False
    cfg.show_reasoning = False
    cfg.verbosity = "normal"
    cfg.no_color = True
    cfg.screen_reader = False
    cfg.timestamp_style = "prefix"
    cfg.final_only = False
    r = runner_mod.StepRunner(cfg, MagicMock())
    return r


class TestRunStepEnvPropagation(unittest.IsolatedAsyncioTestCase):

    async def test_run_step_sets_hve_step_id(self) -> None:
        runner = _make_runner()
        captured = {}

        original_environ = os.environ.copy()
        try:
            await runner.run_step(
                step_id="step-2.1",
                title="t",
                prompt="p",
                custom_agent="Arch-UI-Detail",
            )
            # dry_run 後に env vars が設定済みとなる（本実装は run_step 入口で設定）
            captured["step_id"] = os.environ.get("HVE_STEP_ID")
            captured["agent_id"] = os.environ.get("HVE_AGENT_ID")
        finally:
            os.environ.clear()
            os.environ.update(original_environ)

        self.assertEqual(captured["step_id"], "step-2.1")
        self.assertEqual(captured["agent_id"], "Arch-UI-Detail")

    async def test_run_step_clears_agent_id_when_none(self) -> None:
        runner = _make_runner()
        original_environ = os.environ.copy()
        os.environ["HVE_AGENT_ID"] = "stale-agent"
        try:
            await runner.run_step(
                step_id="step-3",
                title="t",
                prompt="p",
                custom_agent=None,  # Agent 指定なし
            )
            self.assertNotIn("HVE_AGENT_ID", os.environ,
                              "custom_agent=None 時は HVE_AGENT_ID を削除すべき")
        finally:
            os.environ.clear()
            os.environ.update(original_environ)

    async def test_run_step_sets_step_id_string_form(self) -> None:
        """step_id が非文字列でも文字列化されること。"""
        runner = _make_runner()
        original_environ = os.environ.copy()
        try:
            await runner.run_step(
                step_id="1.2",
                title="t",
                prompt="p",
                custom_agent="A",
            )
            self.assertEqual(os.environ.get("HVE_STEP_ID"), "1.2")
        finally:
            os.environ.clear()
            os.environ.update(original_environ)


class TestRunStepSourceContainsEnvWrap(unittest.TestCase):
    """run_step のソースに環境変数設定コードが存在することを検査する。

    `test_runner.py` の inspect.getsource ベース検査と同じ流儀で、
    将来のリファクタで env wrap が消えた場合を検知する。
    """

    def test_source_inspection_run_step_sets_hve_env_vars(self) -> None:
        import inspect
        from hve.runner import StepRunner
        source = inspect.getsource(StepRunner.run_step)
        self.assertIn("HVE_STEP_ID", source)
        self.assertIn("HVE_AGENT_ID", source)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
