"""test_dag_executor.py — DAGExecutor の並列実行テスト"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dag_executor import DAGExecutor, StepResult


# ---------------------------------------------------------------------------
# テスト用スタブ (workflow_registry.py の WorkflowDef / StepDef を模倣)
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
    """テスト用最小 WorkflowDef スタブ。"""

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
        existing_ids = set(self._index.keys())

        result: List[_StepDef] = []
        for step in self.steps:
            if step.is_container:
                continue
            if step.id in completed or step.id in skipped:
                continue
            if not step.depends_on:
                result.append(step)
            else:
                deps_ok = all(
                    dep in effective_done or dep not in existing_ids
                    for dep in step.depends_on
                )
                if deps_ok:
                    result.append(step)
        return result


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# テストケース
# ---------------------------------------------------------------------------


class TestDAGExecutorAAS(unittest.TestCase):
    """AAS ライクな 2ステップ直列 DAG のテスト。"""

    def setUp(self) -> None:
        # Step.1 → Step.2
        self.wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", custom_agent=None, depends_on=[]),
            _StepDef(id="2", title="Step 2", custom_agent=None, depends_on=["1"]),
        ])
        self.execution_order: List[str] = []

    def _make_run_step_fn(self, results: Dict[str, bool]):
        async def run_step(step_id, title, prompt, custom_agent=None):
            self.execution_order.append(step_id)
            return results.get(step_id, True)
        return run_step

    def test_sequential_execution(self) -> None:
        """2ステップが順番に実行されることを確認。"""
        run_fn = self._make_run_step_fn({"1": True, "2": True})
        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_fn,
            active_step_ids={"1", "2"},
            max_parallel=15,
        )
        result = _run(executor.execute())

        self.assertIn("1", result)
        self.assertIn("2", result)
        self.assertTrue(result["1"].success)
        self.assertTrue(result["2"].success)
        # Step.1 が Step.2 より先に完了することを確認
        self.assertLess(
            self.execution_order.index("1"),
            self.execution_order.index("2"),
        )

    def test_all_steps_completed(self) -> None:
        run_fn = self._make_run_step_fn({"1": True, "2": True})
        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_fn,
            active_step_ids={"1", "2"},
        )
        _run(executor.execute())
        self.assertEqual(executor.completed, {"1", "2"})
        self.assertEqual(executor.failed, set())

    def test_step1_inactive_step2_runs(self) -> None:
        """Step.1 が active でない場合、Step.1 はスキップされ、
        その後 Step.2（依存解決済み）が正常に実行されることを確認。"""
        executed: List[str] = []

        async def run_step(step_id, title, prompt, custom_agent=None):
            executed.append(step_id)
            return True

        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_step,
            active_step_ids={"2"},  # Step.1 は active でない
        )
        _run(executor.execute())

        # Step.1 は auto-skip される
        self.assertIn("1", executor.skipped)
        self.assertNotIn("1", executed)

        # Step.1 がスキップされたことで依存が解決され、Step.2 が実行される
        self.assertIn("2", executor.completed)
        self.assertIn("2", executed)


class TestDAGExecutorABD(unittest.TestCase):
    """ABD ライクな 並列 fork → AND join の DAG テスト。

    DAG: 1 → 2a ‖ 2b → 3 (AND join)
    """

    def setUp(self) -> None:
        self.wf = _WorkflowDef([
            _StepDef(id="1",  title="Step 1",  depends_on=[]),
            _StepDef(id="2a", title="Step 2a", depends_on=["1"]),
            _StepDef(id="2b", title="Step 2b", depends_on=["1"]),
            _StepDef(id="3",  title="Step 3",  depends_on=["2a", "2b"]),
        ])
        self.execution_order: List[str] = []

    def _make_run_step_fn(self, results: Dict[str, bool]):
        async def run_step(step_id, title, prompt, custom_agent=None):
            self.execution_order.append(step_id)
            return results.get(step_id, True)
        return run_step

    def test_parallel_fork_and_join(self) -> None:
        """2a と 2b が 1 の完了後に並列実行され、3 が AND join されることを確認。"""
        run_fn = self._make_run_step_fn({"1": True, "2a": True, "2b": True, "3": True})
        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_fn,
            active_step_ids={"1", "2a", "2b", "3"},
        )
        _run(executor.execute())

        self.assertEqual(executor.completed, {"1", "2a", "2b", "3"})
        self.assertEqual(executor.failed, set())

        # Step.1 は 2a/2b より先
        idx_1 = self.execution_order.index("1")
        idx_2a = self.execution_order.index("2a")
        idx_2b = self.execution_order.index("2b")
        idx_3 = self.execution_order.index("3")
        self.assertLess(idx_1, idx_2a)
        self.assertLess(idx_1, idx_2b)
        # Step.3 は 2a/2b より後
        self.assertGreater(idx_3, idx_2a)
        self.assertGreater(idx_3, idx_2b)

    def test_all_active_completed(self) -> None:
        run_fn = self._make_run_step_fn({"1": True, "2a": True, "2b": True, "3": True})
        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_fn,
            active_step_ids={"1", "2a", "2b", "3"},
        )
        result = _run(executor.execute())
        for sid in ["1", "2a", "2b", "3"]:
            self.assertIn(sid, result)
            self.assertTrue(result[sid].success)


class TestDAGExecutorMaxParallel(unittest.TestCase):
    """max_parallel=1 での直列実行テスト。"""

    def test_serial_execution_with_max_parallel_1(self) -> None:
        """max_parallel=1 でも全ステップが完了することを確認。"""
        # 独立した 3 ステップ（全てルート）
        wf = _WorkflowDef([
            _StepDef(id="A", title="A", depends_on=[]),
            _StepDef(id="B", title="B", depends_on=[]),
            _StepDef(id="C", title="C", depends_on=[]),
        ])
        concurrent_count = [0]
        max_concurrent = [0]

        async def run_step(step_id, title, prompt, custom_agent=None):
            concurrent_count[0] += 1
            max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
            await asyncio.sleep(0.01)
            concurrent_count[0] -= 1
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"A", "B", "C"},
            max_parallel=1,
        )
        _run(executor.execute())

        # max_parallel=1 なので同時実行数は 1
        self.assertEqual(max_concurrent[0], 1)
        self.assertEqual(executor.completed, {"A", "B", "C"})


class TestDAGExecutorFailure(unittest.TestCase):
    """失敗ステップの後続ブロックテスト。"""

    def test_failed_step_blocks_downstream(self) -> None:
        """Step.1 が失敗した場合、Step.2 は実行されないことを確認。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
            _StepDef(id="2", title="Step 2", depends_on=["1"]),
        ])
        executed: List[str] = []

        async def run_step(step_id, title, prompt, custom_agent=None):
            executed.append(step_id)
            return step_id != "1"  # Step.1 は失敗

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2"},
        )
        result = _run(executor.execute())

        # Step.1 は失敗
        self.assertIn("1", result)
        self.assertFalse(result["1"].success)
        self.assertIn("1", executor.failed)

        # Step.2 は実行されない（Step.1 が failed なので依存解決されない）
        self.assertNotIn("2", executed)

    def test_step_result_has_elapsed(self) -> None:
        """StepResult に elapsed が設定されることを確認。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
        ])

        async def run_step(step_id, title, prompt, custom_agent=None):
            await asyncio.sleep(0.01)
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1"},
        )
        result = _run(executor.execute())
        self.assertGreaterEqual(result["1"].elapsed, 0.0)


class TestStepResult(unittest.TestCase):
    """StepResult クラスの基本テスト。"""

    def test_step_result_attributes(self) -> None:
        r = StepResult("1.1", True, 3.5)
        self.assertEqual(r.step_id, "1.1")
        self.assertTrue(r.success)
        self.assertAlmostEqual(r.elapsed, 3.5)

    def test_step_result_repr(self) -> None:
        r = StepResult("2", False, 0.0)
        self.assertIn("2", repr(r))
        self.assertIn("False", repr(r))


class TestDAGExecutorConsole(unittest.TestCase):
    """Console が接続されている場合のテスト。"""

    def test_dag_wave_start_called_when_console_provided(self) -> None:
        """console.dag_wave_start() が呼ばれることを確認。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
        ])

        mock_console = MagicMock()

        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1"},
            console=mock_console,
        )
        _run(executor.execute())

        mock_console.dag_wave_start.assert_called_once()

    def test_dag_progress_called_on_step_completion(self) -> None:
        """ステップ完了時に console.dag_progress() が呼ばれることを確認。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
            _StepDef(id="2", title="Step 2", depends_on=["1"]),
        ])

        mock_console = MagicMock()

        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2"},
            console=mock_console,
        )
        _run(executor.execute())

        # dag_progress は各ステップ完了時に呼ばれる (最低2回)
        self.assertGreaterEqual(mock_console.dag_progress.call_count, 2)


class TestDAGExecutorComputeWaves(unittest.TestCase):
    """compute_waves() のテスト。"""

    def test_sequential_dag_has_separate_waves(self) -> None:
        """直列 DAG: 各ステップが別 Wave になる。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
            _StepDef(id="2", title="Step 2", depends_on=["1"]),
        ])
        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=lambda *a, **kw: None,
            active_step_ids={"1", "2"},
        )
        waves = executor.compute_waves()
        self.assertEqual(len(waves), 2)
        self.assertEqual([s.id for s in waves[0]], ["1"])
        self.assertEqual([s.id for s in waves[1]], ["2"])

    def test_parallel_fork_in_same_wave(self) -> None:
        """並列 fork: 同じ依存の複数ステップが同一 Wave に入る。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
            _StepDef(id="2a", title="Step 2a", depends_on=["1"]),
            _StepDef(id="2b", title="Step 2b", depends_on=["1"]),
            _StepDef(id="3", title="Step 3", depends_on=["2a", "2b"]),
        ])
        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=lambda *a, **kw: None,
            active_step_ids={"1", "2a", "2b", "3"},
        )
        waves = executor.compute_waves()
        self.assertEqual(len(waves), 3)
        wave2_ids = sorted(s.id for s in waves[1])
        self.assertEqual(wave2_ids, ["2a", "2b"])

    def test_inactive_steps_skipped_in_waves(self) -> None:
        """active でないステップは Wave に含まれない。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
            _StepDef(id="2", title="Step 2", depends_on=["1"]),
            _StepDef(id="3", title="Step 3", depends_on=["2"]),
        ])
        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=lambda *a, **kw: None,
            active_step_ids={"1", "3"},  # Step.2 は inactive
        )
        waves = executor.compute_waves()
        all_ids = [s.id for wave in waves for s in wave]
        self.assertIn("1", all_ids)
        self.assertIn("3", all_ids)
        self.assertNotIn("2", all_ids)


if __name__ == "__main__":
    unittest.main()
