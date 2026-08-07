"""Agentic Retrieval Step の条件付き無効化（`enable_agentic_retrieval=no`）の契約テスト。

`StepDef.disabled_when_config` の宣言と `resolve_disabled_step_ids` の解決、
および無効化しても下流 Step の DAG が壊れないことを検証する。
"""

from __future__ import annotations

import unittest

from hve.dag_planner import build_dag_plan
from hve.template_engine import resolve_selected_steps
from hve.workflow_registry import (
    get_step,
    get_workflow,
    resolve_disabled_step_ids,
)


_AGENTIC_STEPS = {
    "aad-web": ["2.6"],
    "asdw-web": ["2.5", "2.6"],
}


class TestDisabledWhenConfigDeclaration(unittest.TestCase):
    """Agentic Retrieval Step が無効化条件を宣言していること。"""

    def test_agentic_steps_declare_disable_condition(self) -> None:
        for workflow_id, step_ids in _AGENTIC_STEPS.items():
            for step_id in step_ids:
                step = get_step(workflow_id, step_id)
                self.assertIsNotNone(step, f"{workflow_id}/{step_id}")
                self.assertEqual(
                    step.disabled_when_config,
                    {"enable_agentic_retrieval": ["no"]},
                    msg=f"{workflow_id}/{step_id}",
                )

    def test_other_steps_do_not_declare_disable_condition(self) -> None:
        for workflow_id in _AGENTIC_STEPS:
            wf = get_workflow(workflow_id)
            for step in wf.steps:
                if step.id in _AGENTIC_STEPS[workflow_id]:
                    continue
                self.assertEqual(
                    step.disabled_when_config, {}, msg=f"{workflow_id}/{step.id}"
                )


class TestResolveDisabledStepIds(unittest.TestCase):
    """config 値から無効化 Step を解決すること。"""

    def test_no_disables_agentic_steps(self) -> None:
        for workflow_id, step_ids in _AGENTIC_STEPS.items():
            disabled = resolve_disabled_step_ids(
                workflow_id, {"enable_agentic_retrieval": "no"}
            )
            self.assertEqual(sorted(disabled), sorted(step_ids), msg=workflow_id)

    def test_auto_and_yes_do_not_disable(self) -> None:
        for value in ("auto", "yes"):
            for workflow_id in _AGENTIC_STEPS:
                disabled = resolve_disabled_step_ids(
                    workflow_id, {"enable_agentic_retrieval": value}
                )
                self.assertEqual(disabled, frozenset(), msg=f"{workflow_id}/{value}")

    def test_missing_key_does_not_disable(self) -> None:
        self.assertEqual(resolve_disabled_step_ids("asdw-web", {}), frozenset())

    def test_ui_display_value_disables(self) -> None:
        """UI 表示値「しない」も内部値 `no` と同じく無効化すること。"""
        disabled = resolve_disabled_step_ids(
            "asdw-web", {"enable_agentic_retrieval": "しない"}
        )
        self.assertEqual(sorted(disabled), ["2.5", "2.6"])

    def test_case_and_whitespace_are_normalized(self) -> None:
        disabled = resolve_disabled_step_ids(
            "asdw-web", {"enable_agentic_retrieval": "  NO  "}
        )
        self.assertEqual(sorted(disabled), ["2.5", "2.6"])

    def test_unknown_workflow_returns_empty(self) -> None:
        self.assertEqual(
            resolve_disabled_step_ids("unknown-wf", {"enable_agentic_retrieval": "no"}),
            frozenset(),
        )

    def test_workflow_without_agentic_steps_returns_empty(self) -> None:
        self.assertEqual(
            resolve_disabled_step_ids("aagd", {"enable_agentic_retrieval": "no"}),
            frozenset(),
        )


class TestDisabledStepsDoNotBreakDownstream(unittest.TestCase):
    """無効化しても下流 Step が到達不能にならないこと。"""

    def _plan_step_ids(self, workflow_id: str, disabled: set) -> set:
        wf = get_workflow(workflow_id)
        active = resolve_selected_steps(wf, []) - disabled
        plan = build_dag_plan(wf, active, max_parallel=1)
        return {step_id for wave in plan.waves for step_id in wave.step_ids}

    def test_asdw_web_reaches_all_steps_without_agentic(self) -> None:
        """2.5 / 2.6 を無効化しても 4.2 以降の全 Step が計画に残ること。"""
        disabled = set(resolve_disabled_step_ids("asdw-web", {"enable_agentic_retrieval": "no"}))
        planned = self._plan_step_ids("asdw-web", disabled)
        self.assertNotIn("2.5", planned)
        self.assertNotIn("2.6", planned)
        for step_id in ("1.3", "4.2", "4.3", "4.4", "5.1", "5.2"):
            self.assertIn(step_id, planned, msg=step_id)

    def test_asdw_web_includes_agentic_steps_when_enabled(self) -> None:
        planned = self._plan_step_ids("asdw-web", set())
        self.assertIn("2.5", planned)
        self.assertIn("2.6", planned)

    def test_aad_web_reaches_all_steps_without_agentic(self) -> None:
        disabled = set(resolve_disabled_step_ids("aad-web", {"enable_agentic_retrieval": "no"}))
        planned = self._plan_step_ids("aad-web", disabled)
        self.assertNotIn("2.6", planned)
        for step_id in ("1", "2.1", "2.2", "2.3", "2.4", "2.5", "3"):
            self.assertIn(step_id, planned, msg=step_id)


class TestOrchestratorConfigDisabledSteps(unittest.TestCase):
    """orchestrator が設定値から無効化 Step を解決すること。"""

    class _Config:
        def __init__(self, value: str) -> None:
            self.enable_agentic_retrieval = value

    def _resolve(self, workflow_id: str, config) -> frozenset:
        from hve.orchestrator import _resolve_config_disabled_steps

        return _resolve_config_disabled_steps(get_workflow(workflow_id), workflow_id, config)

    def test_no_disables_declared_steps(self) -> None:
        self.assertEqual(
            sorted(self._resolve("asdw-web", self._Config("no"))), ["2.5", "2.6"]
        )

    def test_auto_keeps_steps(self) -> None:
        self.assertEqual(self._resolve("asdw-web", self._Config("auto")), frozenset())

    def test_missing_config_object_returns_empty(self) -> None:
        self.assertEqual(self._resolve("asdw-web", None), frozenset())

    def test_config_without_declared_attribute_returns_empty(self) -> None:
        class _Other:
            unrelated = "no"

        self.assertEqual(self._resolve("asdw-web", _Other()), frozenset())

    def test_workflow_without_declaration_does_not_read_config(self) -> None:
        """宣言が無い workflow では設定値に関わらず空集合を返すこと。"""
        self.assertEqual(self._resolve("aagd", self._Config("no")), frozenset())


if __name__ == "__main__":
    unittest.main()
