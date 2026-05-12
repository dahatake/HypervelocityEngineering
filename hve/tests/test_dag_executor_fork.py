"""test_dag_executor_fork.py — Fork-integration T4.4.

`DAGExecutor` の Fork-on-Retry 機構を検証する。

DoD (T4.4):
- `fork_on_retry=True` で初回失敗 → 1 回だけリトライ → 成功時に `retry_count=1`
- `fork_on_retry=True` で初回失敗 → リトライも失敗 → `retry_count=1` で `failed`
- `fork_on_retry=False`（既定）で初回失敗 → リトライしない → `retry_count=0`
- リトライ時に `on_fork_retry(step_id, 1)` フックが呼ばれる
- KPI ロガーが各ステップで `log_step` を呼ばれる（フォーク発火時のみ enabled）
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dag_executor import DAGExecutor  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# テスト用最小スタブ
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


class _StubKPILogger:
    def __init__(self) -> None:
        self.records: List[dict] = []

    def log_step(self, **kwargs) -> None:
        self.records.append(kwargs)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------


class TestForkOnRetrySuccess(unittest.TestCase):
    """フラグ ON: 初回失敗 → リトライ成功。"""

    def test_retry_success_sets_retry_count_one(self) -> None:
        wf = _WorkflowDef([_StepDef(id="X", title="X")])
        attempt = {"n": 0}

        async def run_step(step_id, title, prompt, custom_agent=None):
            attempt["n"] += 1
            return attempt["n"] >= 2  # 1 回目は False、2 回目は True

        fork_hook_calls: List[Tuple[str, int]] = []

        def on_fork(step_id: str, idx: int) -> None:
            fork_hook_calls.append((step_id, idx))

        logger = _StubKPILogger()
        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"X"},
            fork_on_retry=True,
            fork_kpi_logger=logger,
            on_fork_retry=on_fork,
        )
        results = _run(executor.execute())

        self.assertTrue(results["X"].success)
        self.assertEqual(results["X"].retry_count, 1)
        self.assertEqual(attempt["n"], 2)
        # C1 対応: リトライ後に fork_index=0 リセット呼び出しが必ず実行される
        self.assertEqual(fork_hook_calls, [("X", 1), ("X", 0)])
        # KPI ロガーに 1 件以上記録される
        self.assertEqual(len(logger.records), 1)
        self.assertEqual(logger.records[0]["retry_count"], 1)


class TestForkOnRetryFailure(unittest.TestCase):
    """フラグ ON: 初回失敗 → リトライも失敗 → step は failed。"""

    def test_retry_failure_keeps_failed(self) -> None:
        wf = _WorkflowDef([_StepDef(id="Y", title="Y")])
        attempts = {"n": 0}

        async def run_step(step_id, title, prompt, custom_agent=None):
            attempts["n"] += 1
            return False

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"Y"},
            fork_on_retry=True,
            on_fork_retry=lambda s, i: None,
        )
        results = _run(executor.execute())

        self.assertFalse(results["Y"].success)
        self.assertEqual(results["Y"].retry_count, 1)
        self.assertIn("Y", executor.failed)
        # 2 回呼ばれる（初回 + リトライ 1 回のみ）
        self.assertEqual(attempts["n"], 2)


class TestForkOnRetryDisabled(unittest.TestCase):
    """フラグ OFF（既定）: 失敗してもリトライしない（旧挙動）。"""

    def test_default_no_retry(self) -> None:
        wf = _WorkflowDef([_StepDef(id="Z", title="Z")])
        attempts = {"n": 0}

        async def run_step(step_id, title, prompt, custom_agent=None):
            attempts["n"] += 1
            return False

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"Z"},
            # fork_on_retry 既定 = False
        )
        results = _run(executor.execute())

        self.assertFalse(results["Z"].success)
        self.assertEqual(results["Z"].retry_count, 0)
        self.assertEqual(attempts["n"], 1)  # 1 回だけ


class TestForkOnRetryHookSafety(unittest.TestCase):
    """on_fork_retry / fork_kpi_logger が None でも例外を出さない。"""

    def test_no_hook_and_no_logger(self) -> None:
        wf = _WorkflowDef([_StepDef(id="A", title="A")])
        attempts = {"n": 0}

        async def run_step(step_id, title, prompt, custom_agent=None):
            attempts["n"] += 1
            return attempts["n"] >= 2

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"A"},
            fork_on_retry=True,
            # フック / ロガーいずれも未指定
        )
        results = _run(executor.execute())
        self.assertTrue(results["A"].success)
        self.assertEqual(results["A"].retry_count, 1)

    def test_hook_failure_skips_retry(self) -> None:
        """C19: on_fork_retry が例外を投げたらリトライをスキップして初回失敗を最終結果とする。"""
        wf = _WorkflowDef([_StepDef(id="B", title="B")])
        attempts = {"n": 0}

        async def run_step(step_id, title, prompt, custom_agent=None):
            attempts["n"] += 1
            return False  # 常に失敗

        def failing_hook(step_id: str, idx: int) -> None:
            raise RuntimeError("hook broken")

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"B"},
            fork_on_retry=True,
            on_fork_retry=failing_hook,
        )
        results = _run(executor.execute())
        # 初回失敗のみで終了（リトライは発火しない）
        self.assertFalse(results["B"].success)
        self.assertEqual(results["B"].retry_count, 0)
        self.assertEqual(attempts["n"], 1)


if __name__ == "__main__":
    unittest.main()
