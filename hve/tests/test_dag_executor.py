"""test_dag_executor.py — DAGExecutor の並列実行テスト"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dag_executor import DAGExecutor, StepResult
from dag_planner import build_dag_plan


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


class _RecordingConsole:
    """DAGExecutor の console 呼び出しを記録する最小スタブ。"""

    def __init__(self) -> None:
        self.stats_events: List[tuple] = []
        self.status_lines: List[str] = []
        self.warning_lines: List[str] = []
        self.error_lines: List[str] = []

    def stats_event(self, kind: str, step_id: str = "", **fields: object) -> None:
        self.stats_events.append((kind, step_id, dict(fields)))

    def status(self, msg: str) -> None:
        self.status_lines.append(msg)

    def warning(self, msg: str) -> None:
        self.warning_lines.append(msg)

    def error(self, msg: str) -> None:
        self.error_lines.append(msg)

    def dag_wave_start(self, *_args, **_kwargs) -> None:
        return None

    def dag_progress(self, *_args, **_kwargs) -> None:
        return None


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
    """ADFD ライクな 並列 fork → AND join の DAG テスト。

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

    def test_on_wave_start_receives_parallel_wave(self) -> None:
        run_fn = self._make_run_step_fn({"1": True, "2a": True, "2b": True, "3": True})
        waves_seen: List[List[str]] = []

        def on_wave_start(steps, wave_index):
            waves_seen.append([s.id for s in steps])

        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_fn,
            active_step_ids={"1", "2a", "2b", "3"},
            on_wave_start=on_wave_start,
        )
        _run(executor.execute())

        self.assertIn(["1"], waves_seen)
        self.assertIn(["2a", "2b"], waves_seen)
        self.assertIn(["3"], waves_seen)

    def test_parallel_wave_can_use_fleet_wave_runner(self) -> None:
        executed: List[str] = []
        fleet_waves: List[List[str]] = []

        async def run_step(step_id, title, prompt, custom_agent=None):
            executed.append(step_id)
            return True

        async def fleet_wave_runner(steps, wave_index):
            step_ids = [s.id for s in steps]
            if step_ids == ["2a", "2b"]:
                fleet_waves.append(step_ids)
                return {
                    sid: StepResult(sid, success=True, elapsed=0.0)
                    for sid in step_ids
                }
            return None

        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2a", "2b", "3"},
            fleet_wave_runner=fleet_wave_runner,
        )
        _run(executor.execute())

        self.assertEqual(fleet_waves, [["2a", "2b"]])
        self.assertNotIn("2a", executed)
        self.assertNotIn("2b", executed)
        self.assertIn("1", executed)
        self.assertIn("3", executed)
        self.assertEqual(executor.completed, {"1", "2a", "2b", "3"})

    def test_fleet_wave_emits_running_and_terminal_step_status(self) -> None:
        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        async def fleet_wave_runner(steps, wave_index):
            step_ids = [s.id for s in steps]
            if step_ids == ["2a", "2b"]:
                return {
                    "2a": StepResult("2a", success=True, elapsed=0.0),
                    "2b": StepResult("2b", success=False, elapsed=0.0),
                }
            return None

        console = _RecordingConsole()
        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2a", "2b", "3"},
            console=console,
            fleet_wave_runner=fleet_wave_runner,
        )
        _run(executor.execute())

        status_events = [
            (step_id, fields.get("status"))
            for kind, step_id, fields in console.stats_events
            if kind == "step_status"
        ]
        self.assertIn(("2a", "running"), status_events)
        self.assertIn(("2b", "running"), status_events)
        self.assertIn(("2a", "done"), status_events)
        self.assertIn(("2b", "failed"), status_events)

    def test_fleet_wave_invokes_on_step_start_for_state_updates(self) -> None:
        starts: List[str] = []

        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        async def fleet_wave_runner(steps, wave_index):
            step_ids = [s.id for s in steps]
            if step_ids == ["2a", "2b"]:
                return {
                    sid: StepResult(sid, success=True, elapsed=0.0)
                    for sid in step_ids
                }
            return None

        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2a", "2b", "3"},
            fleet_wave_runner=fleet_wave_runner,
            on_step_start=starts.append,
        )
        _run(executor.execute())

        self.assertEqual(starts, ["1", "2a", "2b", "3"])

    def test_fleet_wave_runner_none_falls_back_to_semaphore(self) -> None:
        executed: List[str] = []

        async def run_step(step_id, title, prompt, custom_agent=None):
            executed.append(step_id)
            return True

        async def fleet_wave_runner(steps, wave_index):
            if [s.id for s in steps] == ["2a", "2b"]:
                return None
            return None

        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2a", "2b", "3"},
            fleet_wave_runner=fleet_wave_runner,
        )
        _run(executor.execute())

        self.assertIn("2a", executed)
        self.assertIn("2b", executed)
        self.assertEqual(executor.completed, {"1", "2a", "2b", "3"})

    def test_fleet_wave_runner_exception_marks_wave_failed(self) -> None:
        executed: List[str] = []

        async def run_step(step_id, title, prompt, custom_agent=None):
            executed.append(step_id)
            return True

        async def fleet_wave_runner(steps, wave_index):
            if [s.id for s in steps] == ["2a", "2b"]:
                raise RuntimeError("fleet unavailable")
            return None

        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2a", "2b", "3"},
            fleet_wave_runner=fleet_wave_runner,
        )
        _run(executor.execute())

        self.assertNotIn("2a", executed)
        self.assertNotIn("2b", executed)
        self.assertIn("2a", executor.failed)
        self.assertIn("2b", executor.failed)
        self.assertNotIn("3", executed)

    def test_fleet_wave_runner_incomplete_results_mark_wave_failed(self) -> None:
        executed: List[str] = []

        async def run_step(step_id, title, prompt, custom_agent=None):
            executed.append(step_id)
            return True

        async def fleet_wave_runner(steps, wave_index):
            if [s.id for s in steps] == ["2a", "2b"]:
                return {"2a": StepResult("2a", success=True, elapsed=0.0)}
            return None

        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2a", "2b", "3"},
            fleet_wave_runner=fleet_wave_runner,
        )
        _run(executor.execute())

        self.assertNotIn("2a", executed)
        self.assertNotIn("2b", executed)
        self.assertIn("2a", executor.failed)
        self.assertIn("2b", executor.failed)

    def test_fleet_wave_runner_step_id_mismatch_marks_wave_failed(self) -> None:
        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        async def fleet_wave_runner(steps, wave_index):
            if [s.id for s in steps] == ["2a", "2b"]:
                return {
                    "2a": StepResult("2b", success=True, elapsed=0.0),
                    "2b": StepResult("2b", success=True, elapsed=0.0),
                }
            return None

        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2a", "2b", "3"},
            fleet_wave_runner=fleet_wave_runner,
        )
        _run(executor.execute())

        self.assertIn("2a", executor.failed)
        self.assertIn("2b", executor.failed)

    def test_fleet_wave_runner_invalid_state_marks_wave_failed(self) -> None:
        async def run_step(step_id, title, prompt, custom_agent=None):
            return True

        async def fleet_wave_runner(steps, wave_index):
            if [s.id for s in steps] == ["2a", "2b"]:
                return {
                    "2a": StepResult("2a", success=True, elapsed=0.0, state="mystery"),
                    "2b": StepResult("2b", success=True, elapsed=0.0),
                }
            return None

        executor = DAGExecutor(
            workflow=self.wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2a", "2b", "3"},
            fleet_wave_runner=fleet_wave_runner,
        )
        _run(executor.execute())

        self.assertIn("2a", executor.failed)
        self.assertIn("2b", executor.failed)


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

    def test_plan_execution_records_blocked_downstream_reason(self) -> None:
        """DAGPlan 経路では失敗後続を reason 付き blocked として結果に残す。"""
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
            _StepDef(id="2", title="Step 2", depends_on=["1"]),
        ])
        plan = build_dag_plan(wf, {"1", "2"})

        async def run_step(step_id, title, prompt, custom_agent=None):
            return step_id != "1"

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2"},
            dag_plan=plan,
        )
        result = _run(executor.execute())

        self.assertIn("1", executor.failed)
        self.assertIn("2", executor.blocked)
        self.assertEqual(result["2"].state, "blocked")
        self.assertEqual(result["2"].reason, "blocked_by_failed_dependency")

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

    def test_compute_waves_uses_dag_plan_snapshot(self) -> None:
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
            _StepDef(id="2", title="Step 2", depends_on=["1"]),
            _StepDef(id="3", title="Step 3", depends_on=["2"]),
        ])
        plan = build_dag_plan(wf, {"1", "3"})
        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=lambda *a, **kw: None,
            active_step_ids={"1", "3"},
            dag_plan=plan,
        )

        waves = executor.compute_waves()

        self.assertEqual([[s.id for s in wave] for wave in waves], [["1"], ["3"]])


class TestDAGExecutorPlanPrompts(unittest.TestCase):
    def test_plan_prompt_is_passed_to_runner(self) -> None:
        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
        ])
        plan = build_dag_plan(wf, {"1"}, step_prompts={"1": "planned prompt"})
        captured: Dict[str, str] = {}

        async def run_step(step_id, title, prompt, custom_agent=None):
            captured[step_id] = prompt
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1"},
            dag_plan=plan,
        )
        _run(executor.execute())

        self.assertEqual(captured["1"], "planned prompt")


class TestDAGExecutorStepTimeout(unittest.TestCase):
    """per-step wall-clock タイムアウト（ハング打ち切り）のテスト。

    DAGExecutor に ``step_timeout_seconds`` を渡すと、``run_step_fn`` の実行が
    その秒数を超えた場合に当該ステップを失敗扱いで打ち切り、DAG 全体の
    無期限ハングを防ぐことを固定する（root cause: 1 子のハングが step 全体と
    後続 DAG を無期限停止させる構造欠陥の是正）。
    """

    @staticmethod
    def _single_step_wf() -> "_WorkflowDef":
        return _WorkflowDef([_StepDef(id="1", title="Step 1", depends_on=[])])

    def test_hung_step_is_timed_out_and_marked_failed(self) -> None:
        """step_timeout_seconds を超えてハングする step は failed 扱いで打ち切られる。"""
        async def run_step(step_id, title, prompt, custom_agent=None):
            await asyncio.sleep(5.0)  # timeout より十分長い
            return True

        executor = DAGExecutor(
            workflow=self._single_step_wf(),
            run_step_fn=run_step,
            active_step_ids={"1"},
            step_timeout_seconds=0.1,
        )
        start = time.monotonic()
        result = _run(executor.execute())
        elapsed = time.monotonic() - start

        # ハングせず即座に返る（5s 待たない）
        self.assertLess(elapsed, 2.0)
        self.assertIn("1", executor.failed)
        self.assertFalse(result["1"].success)
        self.assertIsNotNone(result["1"].error)
        self.assertIn("step-timeout", result["1"].error)

    def test_none_timeout_disables_check(self) -> None:
        """step_timeout_seconds=None なら従来通り（打ち切りなし）。"""
        async def run_step(step_id, title, prompt, custom_agent=None):
            await asyncio.sleep(0.05)
            return True

        executor = DAGExecutor(
            workflow=self._single_step_wf(),
            run_step_fn=run_step,
            active_step_ids={"1"},
            step_timeout_seconds=None,
        )
        result = _run(executor.execute())
        self.assertTrue(result["1"].success)
        self.assertIn("1", executor.completed)

    def test_zero_timeout_disables_check(self) -> None:
        """step_timeout_seconds<=0 は None と同様に無効化される。"""
        async def run_step(step_id, title, prompt, custom_agent=None):
            await asyncio.sleep(0.05)
            return True

        executor = DAGExecutor(
            workflow=self._single_step_wf(),
            run_step_fn=run_step,
            active_step_ids={"1"},
            step_timeout_seconds=0,
        )
        result = _run(executor.execute())
        self.assertTrue(result["1"].success)
        self.assertIn("1", executor.completed)

    def test_fast_step_within_timeout_succeeds(self) -> None:
        """timeout 有効でも、期限内に完了する step は通常通り success になる。"""
        async def run_step(step_id, title, prompt, custom_agent=None):
            await asyncio.sleep(0.05)
            return True

        executor = DAGExecutor(
            workflow=self._single_step_wf(),
            run_step_fn=run_step,
            active_step_ids={"1"},
            step_timeout_seconds=5.0,
        )
        result = _run(executor.execute())
        self.assertTrue(result["1"].success)
        self.assertIn("1", executor.completed)
        self.assertNotIn("1", executor.failed)

    def test_timeout_blocks_downstream(self) -> None:
        """timeout した step の後続（依存先）は起動しない。"""
        executed: List[str] = []

        async def run_step(step_id, title, prompt, custom_agent=None):
            executed.append(step_id)
            if step_id == "1":
                await asyncio.sleep(5.0)
            return True

        wf = _WorkflowDef([
            _StepDef(id="1", title="Step 1", depends_on=[]),
            _StepDef(id="2", title="Step 2", depends_on=["1"]),
        ])
        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=run_step,
            active_step_ids={"1", "2"},
            step_timeout_seconds=0.1,
        )
        _run(executor.execute())

        self.assertIn("1", executor.failed)
        self.assertNotIn("2", executor.completed)
        self.assertNotIn("2", executed)

    def test_fork_retry_attempt_is_also_bounded(self) -> None:
        """fork_on_retry=True 時、初回・リトライの双方が timeout で bound される。"""
        call_count = {"n": 0}

        async def run_step(step_id, title, prompt, custom_agent=None):
            call_count["n"] += 1
            await asyncio.sleep(5.0)
            return True

        executor = DAGExecutor(
            workflow=self._single_step_wf(),
            run_step_fn=run_step,
            active_step_ids={"1"},
            step_timeout_seconds=0.1,
            fork_on_retry=True,
            on_fork_retry=lambda s, i: None,
        )
        start = time.monotonic()
        result = _run(executor.execute())
        elapsed = time.monotonic() - start

        # 初回 + リトライの 2 回呼ばれ、いずれも 5s 待たずに打ち切られる
        self.assertEqual(call_count["n"], 2)
        self.assertLess(elapsed, 3.0)
        self.assertFalse(result["1"].success)

    def test_cancelled_inner_runs_finally_cleanup(self) -> None:
        """timeout でキャンセルされた際、inner coroutine の finally が実行される
        （SDK セッションの session.disconnect 等のクリーンアップ相当）。"""
        cleaned = {"done": False}

        async def run_step(step_id, title, prompt, custom_agent=None):
            try:
                await asyncio.sleep(5.0)
                return True
            finally:
                cleaned["done"] = True

        executor = DAGExecutor(
            workflow=self._single_step_wf(),
            run_step_fn=run_step,
            active_step_ids={"1"},
            step_timeout_seconds=0.1,
        )
        _run(executor.execute())
        self.assertTrue(cleaned["done"])

    def test_timeout_emits_warning_log(self) -> None:
        """timeout 打ち切り時に warning ログ（step-timeout を含む）を出力する。"""
        async def run_step(step_id, title, prompt, custom_agent=None):
            await asyncio.sleep(5.0)
            return True

        console = _RecordingConsole()
        executor = DAGExecutor(
            workflow=self._single_step_wf(),
            run_step_fn=run_step,
            active_step_ids={"1"},
            step_timeout_seconds=0.1,
            console=console,
        )
        _run(executor.execute())
        joined = " ".join(console.warning_lines)
        self.assertIn("step-timeout", joined)
        self.assertIn("1", joined)


class TestOrchestratorWiresStepTimeout(unittest.TestCase):
    """orchestrator が config.step_timeout_seconds を DAGExecutor へ配線することを
    ソース検査で確認する（重い run_workflow のモック実行を避ける軽量検証。
    既存の inspect.getsource 契約テストパターンに倣う）。"""

    def test_run_workflow_passes_step_timeout_to_executor(self) -> None:
        import inspect
        from orchestrator import _run_workflow_body
        src = inspect.getsource(_run_workflow_body)
        self.assertIn("step_timeout_seconds=getattr(config", src)


if __name__ == "__main__":
    unittest.main()
