"""test_fork_flag_rollback.py — Fork-integration T4.5.

`HVE_FORK_ON_RETRY` フラグの完全ロールバック動作を検証する。

DoD (T4.5):
- 既定値 False が `SDKConfig` で確定している
- env `HVE_FORK_ON_RETRY` の各種表記が正しく bool に解釈される
- フラグ OFF 時、`DAGExecutor` は旧挙動と完全一致（リトライしない / KPI ファイル作成しない）
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from dag_executor import DAGExecutor  # type: ignore[import-not-found]
from fork_kpi_logger import ForkKPILogger  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# テスト用最小スタブ（test_dag_executor_fork.py と等価）
# ---------------------------------------------------------------------------


@dataclass
class _StepDef:
    id: str
    title: str
    custom_agent: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    is_container: bool = False
    body_template_path: Optional[str] = None
    skip_fallback_deps: List[str] = field(default_factory=list)
    block_unless: List[str] = field(default_factory=list)


class _WorkflowDef:
    def __init__(self, steps: List[_StepDef]) -> None:
        self.steps = steps
        self._index = {s.id: s for s in steps}

    def get_next_steps(
        self,
        completed_step_ids: List[str],
        skipped_step_ids: Optional[List[str]] = None,
    ) -> List[_StepDef]:
        completed = set(completed_step_ids)
        skipped = set(skipped_step_ids or [])
        effective_done = completed | skipped
        existing = set(self._index.keys())
        result: List[_StepDef] = []
        for step in self.steps:
            if step.is_container or step.id in completed or step.id in skipped:
                continue
            if not step.depends_on:
                result.append(step)
            else:
                if all(d in effective_done or d not in existing for d in step.depends_on):
                    result.append(step)
        return result


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------


class TestSDKConfigForkFlagDefault(unittest.TestCase):
    """`SDKConfig.fork_on_retry` の既定値は False。"""

    def test_default_is_false(self) -> None:
        cfg = SDKConfig()
        self.assertFalse(cfg.fork_on_retry)

    def test_from_env_false_when_unset(self) -> None:
        # 環境変数を確実にクリアしてから from_env を呼ぶ
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HVE_FORK_ON_RETRY", None)
            cfg = SDKConfig.from_env()
        self.assertFalse(cfg.fork_on_retry)

    def test_from_env_true_when_set_true(self) -> None:
        with patch.dict(os.environ, {"HVE_FORK_ON_RETRY": "true"}):
            cfg = SDKConfig.from_env()
        self.assertTrue(cfg.fork_on_retry)

    def test_from_env_truthy_alternatives(self) -> None:
        for val in ("1", "yes", "TRUE", "Yes"):
            with patch.dict(os.environ, {"HVE_FORK_ON_RETRY": val}):
                cfg = SDKConfig.from_env()
            self.assertTrue(cfg.fork_on_retry, f"value '{val}' should be truthy")

    def test_from_env_false_alternatives(self) -> None:
        for val in ("", "0", "no", "false", "FALSE"):
            with patch.dict(os.environ, {"HVE_FORK_ON_RETRY": val}):
                cfg = SDKConfig.from_env()
            self.assertFalse(cfg.fork_on_retry, f"value '{val}' should be falsy")


class TestDAGExecutorRollback(unittest.TestCase):
    """フラグ OFF 時に `DAGExecutor` がリトライしない（旧挙動）。"""

    def test_flag_off_does_not_retry_on_failure(self) -> None:
        wf = _WorkflowDef([_StepDef(id="F", title="F")])
        attempts = {"n": 0}

        async def run_step(step_id, title, prompt, custom_agent=None):
            attempts["n"] += 1
            return False

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"F"},
            fork_on_retry=False,
        )
        results = _run(executor.execute())
        self.assertFalse(results["F"].success)
        self.assertEqual(results["F"].retry_count, 0)
        self.assertEqual(attempts["n"], 1)

    def test_flag_off_does_not_create_kpi_file(self) -> None:
        """フラグ OFF + enabled=False ロガーは KPI ファイルを作らない。"""
        with tempfile.TemporaryDirectory() as td:
            kpi_dir = Path(td) / "kpi"
            logger = ForkKPILogger(enabled=False, run_id="run-rb", kpi_dir=kpi_dir)
            wf = _WorkflowDef([_StepDef(id="G", title="G")])

            async def run_step(step_id, title, prompt, custom_agent=None):
                return True

            executor = DAGExecutor(
                workflow=wf,
                run_step_fn=run_step,
                active_step_ids={"G"},
                fork_on_retry=False,
                fork_kpi_logger=logger,
            )
            _run(executor.execute())
            self.assertFalse(logger.log_path.exists())


if __name__ == "__main__":
    unittest.main()
