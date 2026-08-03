"""test_workflow_param_precheck.py — FR-DAG-08 実行開始時パラメータ pre-flight のテスト。

検証項目:
  1. active step の `required_params` 不足を **全件一括** で報告すること
  2. 未設定 / `None` / 空白のみ / `str` 以外を不足と判定すること
  3. fan-out 子 step ID を base step ID へ正規化して解決すること
  4. `required_params` を宣言しない Workflow は素通りすること
  5. `run_workflow` が DAG 実行前に abort し `blocked` に step ID を載せること
  6. 既定値（FR-DAG-07）が pre-flight より前に適用されること

根拠: hve-dev/requirement-definition.md §3.3 FR-DAG-08
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from orchestrator import (
    _check_required_workflow_params_for_active_steps,
    run_workflow,
)
from workflow_registry import StepDef, WorkflowDef, get_workflow


def _run(coro):
    return asyncio.run(coro)


def _make_workflow() -> WorkflowDef:
    return WorkflowDef(
        id="test-wf",
        name="Test Workflow",
        label_prefix="test",
        state_labels={},
        params=[],
        steps=[
            StepDef(
                id="1",
                title="root",
                custom_agent=None,
                required_params=["alpha", "beta"],
            ),
            StepDef(
                id="2",
                title="child",
                custom_agent=None,
                depends_on=["1"],
                required_params=["gamma"],
            ),
            StepDef(id="3", title="free", custom_agent=None, depends_on=["1"]),
        ],
    )


class TestCheckRequiredWorkflowParams(unittest.TestCase):
    """`_check_required_workflow_params_for_active_steps` の判定規則。"""

    def setUp(self) -> None:
        self.wf = _make_workflow()
        self.console = mock.MagicMock()

    def _check(self, active_steps, params):
        return _check_required_workflow_params_for_active_steps(
            wf=self.wf,
            active_steps=set(active_steps),
            params=params,
            console=self.console,
        )

    def test_all_present_passes(self) -> None:
        result = self._check({"1"}, {"alpha": "a", "beta": "b"})
        self.assertFalse(result["should_abort"])
        self.assertFalse(result["blocked"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["blocked_step_ids"], [])

    def test_reports_every_missing_key_at_once(self) -> None:
        """1 件ずつではなく全件を 1 回で報告する（実行の全損を繰り返さない）。"""
        result = self._check({"1", "2"}, {})
        self.assertTrue(result["should_abort"])
        self.assertTrue(result["blocked"])
        for key in ("alpha", "beta", "gamma"):
            self.assertIn(key, result["error"])

    def test_blocked_step_ids_are_registry_ordered_and_unique(self) -> None:
        result = self._check({"2", "1"}, {})
        self.assertEqual(result["blocked_step_ids"], ["1", "2"])

    def test_none_value_is_missing(self) -> None:
        result = self._check({"1"}, {"alpha": None, "beta": "b"})
        self.assertTrue(result["should_abort"])
        self.assertIn("alpha", result["error"])

    def test_blank_only_value_is_missing(self) -> None:
        result = self._check({"1"}, {"alpha": "   ", "beta": "b"})
        self.assertTrue(result["should_abort"])
        self.assertIn("alpha", result["error"])

    def test_non_string_value_is_missing(self) -> None:
        result = self._check({"1"}, {"alpha": 123, "beta": "b"})
        self.assertTrue(result["should_abort"])
        self.assertIn("alpha", result["error"])

    def test_fanout_child_step_id_is_normalized(self) -> None:
        result = self._check({"2/APP-009-S001"}, {})
        self.assertTrue(result["should_abort"])
        self.assertEqual(result["blocked_step_ids"], ["2"])

    def test_inactive_step_params_are_not_required(self) -> None:
        result = self._check({"1"}, {"alpha": "a", "beta": "b"})
        self.assertFalse(result["should_abort"])

    def test_step_without_declaration_passes(self) -> None:
        result = self._check({"3"}, {})
        self.assertFalse(result["should_abort"])

    def test_error_message_names_the_step(self) -> None:
        result = self._check({"2"}, {})
        self.assertIn("2", result["error"])


class TestRunWorkflowParamPrecheckWiring(unittest.TestCase):
    """`run_workflow` への配線（FR-DAG-08）。"""

    def _config(self) -> SDKConfig:
        return SDKConfig(dry_run=True, quiet=True)

    def _asdw_params(self, **overrides) -> dict:
        step = get_workflow("asdw-web").get_step("1.3")
        params = {
            "branch": "main",
            "selected_steps": ["1.3"],
            "resource_group": "rg-example",
        }
        params.update(step.default_params)
        params.update(overrides)
        return params

    def test_missing_required_param_blocks_before_execution(self) -> None:
        params = self._asdw_params()
        params.pop("resource_group")
        result = _run(run_workflow(
            workflow_id="asdw-web",
            params=params,
            config=self._config(),
        ))
        self.assertIn("resource_group", result.get("error") or "")
        self.assertIn("1.3", result.get("blocked") or [])
        self.assertNotIn("dry_run", result)

    def test_missing_resource_group_is_reported(self) -> None:
        params = self._asdw_params(resource_group="")
        result = _run(run_workflow(
            workflow_id="asdw-web",
            params=params,
            config=self._config(),
        ))
        self.assertIn("resource_group", result.get("error") or "")

    def test_all_params_present_proceeds(self) -> None:
        result = _run(run_workflow(
            workflow_id="asdw-web",
            params=self._asdw_params(),
            config=self._config(),
        ))
        self.assertTrue(result.get("dry_run"))
        self.assertNotIn("error", result)

    def test_defaults_are_applied_before_precheck(self) -> None:
        """既定値を持つキーは未指定でもブロックされない（FR-DAG-07 → FR-DAG-08 の順）。"""
        params = self._asdw_params()
        for key in get_workflow("asdw-web").get_step("1.3").default_params:
            params.pop(key, None)
        result = _run(run_workflow(
            workflow_id="asdw-web",
            params=params,
            config=self._config(),
        ))
        self.assertTrue(result.get("dry_run"))
        self.assertNotIn("error", result)

    def test_defaults_reach_downstream_workflow_params(self) -> None:
        """既定値は StepRunner へ渡る effective_params へ反映されること。"""
        from orchestrator import _collect_params_non_interactive
        from workflow_registry import apply_step_default_params

        wf = get_workflow("asdw-web")
        params = self._asdw_params()
        for key in wf.get_step("1.3").default_params:
            params.pop(key, None)
        effective = _collect_params_non_interactive(wf, params)
        self.assertNotIn("data_location", effective)
        apply_step_default_params(wf, {"1.3"}, effective)
        self.assertEqual(effective["data_location"], "japaneast")
        self.assertEqual(effective["data_aci_subnet_cidr"], "10.40.2.0/24")

    def test_precheck_is_not_downgraded_by_continue_on_error(self) -> None:
        """local 実行モードでもパラメータ不足は警告降格しない。"""
        from orchestrator_context import OrchestratorContext

        params = self._asdw_params()
        params.pop("resource_group")
        result = _run(run_workflow(
            workflow_id="asdw-web",
            params=params,
            config=self._config(),
            orchestrator_ctx=OrchestratorContext(continue_on_error=True),
        ))
        self.assertIn("resource_group", result.get("error") or "")

    def test_workflow_without_declaration_is_unaffected(self) -> None:
        result = _run(run_workflow(
            workflow_id="aas",
            params={"branch": "main", "selected_steps": []},
            config=self._config(),
        ))
        self.assertTrue(result.get("dry_run"))

    def test_step_1_3_not_selected_does_not_require_params(self) -> None:
        result = _run(run_workflow(
            workflow_id="asdw-web",
            params={"branch": "main", "selected_steps": ["1.1"]},
            config=self._config(),
        ))
        self.assertTrue(result.get("dry_run"))


if __name__ == "__main__":
    unittest.main()
