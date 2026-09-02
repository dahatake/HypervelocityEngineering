"""test_workflow_max_parallel_resolution.py — FR-DAG-03（v2.32 改訂）の RED テスト。

DAG の並列上限を「ARD bridge mode → `WorkflowDef.max_parallel` の宣言値 →
`SDKConfig.max_parallel`」の順で解決し、解決根拠を `DAGPlan.max_parallel_source`
へ保持することを検証する。

実装前は `run_workflow` が `SDKConfig.max_parallel` だけを `build_dag_plan()` へ
渡しており、宣言値が実行へ反映されないため RED となる。
"""

from __future__ import annotations

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dag_planner import build_dag_plan
from workflow_registry import get_workflow

# 宣言を持つ Workflow とその宣言値（hve/workflow_registry.py が正本）。
DECLARED = {"akm": 21, "adi": 21, "ard": 15, "asdw-web": 1}
# 宣言を持たない Workflow の代表。
UNDECLARED = ("aas", "adoc")


def _resolve():
    from orchestrator import _resolve_max_parallel

    return _resolve_max_parallel


class TestDeclaredValuesAreIntact(unittest.TestCase):
    """前提: レジストリの宣言値が想定どおりであること。"""

    def test_declared_workflows(self):
        for workflow_id, expected in DECLARED.items():
            with self.subTest(workflow=workflow_id):
                self.assertEqual(get_workflow(workflow_id).max_parallel, expected)

    def test_undeclared_workflows(self):
        for workflow_id in UNDECLARED:
            with self.subTest(workflow=workflow_id):
                self.assertIsNone(get_workflow(workflow_id).max_parallel)


class TestResolveMaxParallel(unittest.TestCase):
    """FR-DAG-03: 解決順序と根拠。"""

    def test_declared_value_wins_over_config(self):
        resolve = _resolve()
        for workflow_id, expected in DECLARED.items():
            for config_value in (1, 4, 15, 40):
                with self.subTest(workflow=workflow_id, config=config_value):
                    value, source = resolve(
                        workflow=get_workflow(workflow_id),
                        config_max_parallel=config_value,
                        ard_force_serial=False,
                    )
                    self.assertEqual(value, expected)
                    self.assertEqual(source, "workflow")

    def test_config_is_used_when_not_declared(self):
        resolve = _resolve()
        for workflow_id in UNDECLARED:
            for config_value in (1, 15, 40):
                with self.subTest(workflow=workflow_id, config=config_value):
                    value, source = resolve(
                        workflow=get_workflow(workflow_id),
                        config_max_parallel=config_value,
                        ard_force_serial=False,
                    )
                    self.assertEqual(value, config_value)
                    self.assertEqual(source, "config")

    def test_ard_serial_wins_over_declaration(self):
        resolve = _resolve()
        value, source = resolve(
            workflow=get_workflow("ard"),
            config_max_parallel=15,
            ard_force_serial=True,
        )
        self.assertEqual(value, 1)
        self.assertEqual(source, "ard-serial")


class TestRunWorkflowWiring(unittest.TestCase):
    """解決は orchestrator の単一実装だけで行う（FR-MAINT-07）。"""

    def _source(self) -> str:
        from orchestrator import _run_workflow_body

        return inspect.getsource(_run_workflow_body)

    def test_run_workflow_uses_the_resolver(self):
        self.assertIn("_resolve_max_parallel(", self._source())

    def test_run_workflow_does_not_hardcode_the_source_label(self):
        self.assertNotIn(
            'max_parallel_source="ard-serial" if _ard_force_serial else "config"',
            self._source(),
        )

    def test_run_workflow_does_not_pass_config_max_parallel_directly(self):
        self.assertNotIn("effective_max_parallel = config.max_parallel", self._source())


class TestPlanCarriesResolution(unittest.TestCase):
    """解決結果と根拠が DAGPlan へ載る。"""

    def test_declared_workflow_plan_uses_declared_value(self):
        resolve = _resolve()
        for workflow_id, expected in DECLARED.items():
            with self.subTest(workflow=workflow_id):
                wf = get_workflow(workflow_id)
                value, source = resolve(
                    workflow=wf, config_max_parallel=15, ard_force_serial=False,
                )
                active = {s.id for s in wf.steps if not getattr(s, "is_container", False)}
                plan = build_dag_plan(
                    wf, active, max_parallel=value, max_parallel_source=source,
                )
                self.assertEqual(plan.max_parallel, expected)
                self.assertEqual(plan.max_parallel_source, "workflow")


class TestExecutorDoesNotReResolve(unittest.TestCase):
    """実行段階で WorkflowDef.max_parallel を再解決しない。"""

    def test_semaphore_follows_the_plan_not_the_declaration(self):
        from dag_executor import DAGExecutor

        wf = get_workflow("akm")
        active = {"1", "2"}
        plan = build_dag_plan(
            wf, active, max_parallel=1, max_parallel_source="ard-serial",
        )

        async def noop(*args, **kwargs):
            return True

        executor = DAGExecutor(
            workflow=wf,
            run_step_fn=noop,
            active_step_ids=active,
            max_parallel=1,
            dag_plan=plan,
            repo_root=".",
        )
        self.assertEqual(executor._semaphore._value, 1)


if __name__ == "__main__":
    unittest.main()
