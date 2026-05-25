"""DAG planner contract tests."""

from __future__ import annotations

import unittest

from hve.dag_planner import build_dag_plan
from hve.workflow_registry import get_workflow


class TestDAGPlanner(unittest.TestCase):
    def test_build_dag_plan_keeps_prompt_and_wave_snapshot(self) -> None:
        wf = get_workflow("aad-web")
        self.assertIsNotNone(wf)

        plan = build_dag_plan(
            wf,
            {"1", "2.1", "2.2", "2.3"},
            step_prompts={"1": "prompt-1", "2.3": "prompt-23"},
            max_parallel=7,
            max_parallel_source="test",
        )

        self.assertEqual(plan.workflow_id, "aad-web")
        self.assertEqual(plan.max_parallel, 7)
        self.assertEqual(plan.max_parallel_source, "test")
        self.assertEqual(plan.prompt_for("1"), "prompt-1")
        self.assertEqual(plan.prompt_for("2.3"), "prompt-23")
        self.assertEqual(
            [wave.step_ids for wave in plan.waves],
            [("1",), ("2.1", "2.2"), ("2.3",)],
        )

    def test_build_dag_plan_marks_inactive_steps_as_auto_skipped(self) -> None:
        wf = get_workflow("aas")
        self.assertIsNotNone(wf)

        plan = build_dag_plan(wf, {"1", "3.1"})

        skipped_node = plan.get_node("2")
        self.assertIsNotNone(skipped_node)
        self.assertEqual(skipped_node.skip_reason, "inactive")
        self.assertIn("2", plan.auto_skipped_step_ids)
        self.assertEqual([wave.step_ids for wave in plan.waves], [("1",), ("3.1",)])

    def test_build_dag_plan_records_container_nodes_but_excludes_them_from_waves(self) -> None:
        wf = get_workflow("asdw-web")
        self.assertIsNotNone(wf)

        plan = build_dag_plan(wf, {"1.1", "1.2"})
        container_node = plan.get_node("1")

        self.assertIsNotNone(container_node)
        self.assertTrue(container_node.is_container)
        self.assertEqual(container_node.skip_reason, "container")
        self.assertTrue(all("1" not in wave.step_ids for wave in plan.waves))

    def test_build_dag_plan_handles_fanout_expanded_workflow(self) -> None:
        """fan-out 事前展開済み workflow から build_dag_plan が正しく Wave を生成すること。

        production 経路 (orchestrator が wf_for_dag を事前展開) の回帰テスト。
        """
        import tempfile
        from pathlib import Path
        from hve.orchestrator import _expand_workflow_for_dag

        akm = get_workflow("akm")
        with tempfile.TemporaryDirectory() as td:
            expanded_wf, expanded_active, _ = _expand_workflow_for_dag(
                akm, {"1", "2"}, Path(td)
            )
            plan = build_dag_plan(expanded_wf, expanded_active)

        # Wave 1 = 21 個の fan-out 子、Wave 2 = Step 2
        self.assertEqual(len(plan.waves), 2)
        self.assertEqual(len(plan.waves[0].step_ids), 21)
        self.assertTrue(
            all(sid.startswith("1/D") for sid in plan.waves[0].step_ids)
        )
        self.assertEqual(plan.waves[1].step_ids, ("2",))
        # active_step_ids に子 ID が含まれている
        self.assertIn("1/D01", plan.active_step_ids)
        # 子ノードが auto_skipped に含まれない
        self.assertNotIn("1/D01", plan.auto_skipped_step_ids)


if __name__ == "__main__":
    unittest.main()
