"""test_workflow_step_params.py — FR-DAG-07 Step パラメータ契約のテスト。

検証項目:
  1. ASDW-WEB Step 1.3 が `required_params` / `default_params` を宣言していること
  2. `data_verify_aci_image` が Workflow パラメータではないこと（検証イメージ参照は
     `RESOURCE_GROUP` / `RESOURCE_SUFFIX` から HVE が導出するため）
  3. `apply_step_default_params` が欠落・空白のみのキーだけを補完すること
  4. 既存の非空値を上書きしないこと
  5. fan-out 子 step ID（`{base}/{key}`）を base step ID へ正規化して解決すること
  6. active でない Step の `default_params` を適用しないこと
  7. `default_params` のキーが `required_params` の部分集合であることを
     `WorkflowDef._validate` が強制すること
  8. 宣言された既定値が実行時 validator（`build_asdw_data_deploy_bootstrap_context`）を通ること

根拠: hve-dev/requirement-definition.md §3.3 FR-DAG-07 / §13.3.1 FR-WF-ASDW-01
"""

from __future__ import annotations

import unittest

from hve.asdw_data_runtime_context import (
    AsdwDataDeployContextError,
    build_asdw_data_deploy_bootstrap_context,
)
from hve.workflow_registry import (
    StepDef,
    WorkflowDef,
    apply_step_default_params,
    get_workflow,
)


ASDW_STEP_1_3_REQUIRED_PARAMS = (
    "resource_group",
    "data_location",
    "data_resource_suffix",
    "data_vnet_cidr",
    "data_private_endpoint_subnet_cidr",
    "data_aci_subnet_cidr",
)

ASDW_STEP_1_3_DEFAULT_PARAMS = {
    "data_location": "japaneast",
    "data_resource_suffix": "app009",
    "data_vnet_cidr": "10.40.0.0/16",
    "data_private_endpoint_subnet_cidr": "10.40.1.0/24",
    "data_aci_subnet_cidr": "10.40.2.0/24",
}


def _make_workflow(steps: list) -> WorkflowDef:
    """テスト専用の最小 WorkflowDef を組み立てる。"""
    return WorkflowDef(
        id="test-wf",
        name="Test Workflow",
        label_prefix="test",
        state_labels={},
        params=[],
        steps=steps,
    )


class TestStepParamDeclaration(unittest.TestCase):
    """ASDW-WEB Step 1.3 のパラメータ契約宣言（FR-WF-ASDW-01）。"""

    def setUp(self) -> None:
        self.step = get_workflow("asdw-web").get_step("1.3")

    def test_step_1_3_exists(self) -> None:
        self.assertIsNotNone(self.step)

    def test_required_params_match_contract(self) -> None:
        self.assertEqual(
            tuple(self.step.required_params),
            ASDW_STEP_1_3_REQUIRED_PARAMS,
        )

    def test_default_params_match_contract(self) -> None:
        self.assertEqual(dict(self.step.default_params), ASDW_STEP_1_3_DEFAULT_PARAMS)

    def test_verify_aci_image_is_not_a_workflow_parameter(self) -> None:
        """検証イメージは prep stage が作成する導出値で、入力項目ではない。"""
        self.assertNotIn("data_verify_aci_image", self.step.required_params)
        self.assertNotIn("data_verify_aci_image", self.step.default_params)

    def test_resource_suffix_default_is_derived_from_the_supported_app_id(self) -> None:
        """リソース名のサフィックスは APP-ID から導出し、リテラルを二重管理しない。"""
        from hve.workflow_registry import (
            ASDW_DATA_DEPLOY_SUPPORTED_APP_ID,
            asdw_data_deploy_resource_suffix,
        )

        self.assertEqual(ASDW_DATA_DEPLOY_SUPPORTED_APP_ID, "APP-009")
        self.assertEqual(asdw_data_deploy_resource_suffix(), "app009")
        self.assertEqual(
            self.step.default_params["data_resource_suffix"],
            asdw_data_deploy_resource_suffix(),
        )

    def test_runner_reuses_the_registry_app_id_constant(self) -> None:
        """runner 側のスコープ定数と registry 側の正本がドリフトしないこと。"""
        from hve import runner
        from hve.workflow_registry import ASDW_DATA_DEPLOY_SUPPORTED_APP_ID

        self.assertEqual(
            runner._ASDW_DATA_DEPLOY_SUPPORTED_APP_ID,
            ASDW_DATA_DEPLOY_SUPPORTED_APP_ID,
        )

    def test_resource_group_has_no_default(self) -> None:
        self.assertNotIn("resource_group", self.step.default_params)

    def test_other_asdw_steps_declare_no_required_params(self) -> None:
        """Step 1.3 以外に必須パラメータ宣言を広げていないこと（YAGNI）。"""
        wf = get_workflow("asdw-web")
        declared = {
            step.id for step in wf.steps if step.required_params
        }
        self.assertEqual(declared, {"1.3"})


class TestDefaultParamsValidity(unittest.TestCase):
    """`default_params` は `required_params` の部分集合でなければならない。"""

    def test_default_params_subset_is_accepted(self) -> None:
        wf = _make_workflow([
            StepDef(
                id="1",
                title="s",
                custom_agent=None,
                required_params=["a", "b"],
                default_params={"a": "x"},
            )
        ])
        self.assertEqual(wf.get_step("1").default_params, {"a": "x"})

    def test_default_params_outside_required_params_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _make_workflow([
                StepDef(
                    id="1",
                    title="s",
                    custom_agent=None,
                    required_params=["a"],
                    default_params={"zzz": "x"},
                )
            ])
        self.assertIn("zzz", str(ctx.exception))

    def test_declared_defaults_pass_runtime_validator(self) -> None:
        """宣言済み既定値が実行時 validator を通ること。"""
        step = get_workflow("asdw-web").get_step("1.3")
        bootstrap = {
            "LOCATION": step.default_params["data_location"],
            "RESOURCE_SUFFIX": step.default_params["data_resource_suffix"],
            "DATA_VNET_CIDR": step.default_params["data_vnet_cidr"],
            "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR": step.default_params[
                "data_private_endpoint_subnet_cidr"
            ],
            "DATA_ACI_SUBNET_CIDR": step.default_params["data_aci_subnet_cidr"],
        }
        context = build_asdw_data_deploy_bootstrap_context(
            workflow_params={"resource_group": "rg-example"},
            bootstrap_inputs=bootstrap,
            subscription_id="00000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(context["LOCATION"], "japaneast")

    def test_declared_defaults_reject_an_undeclared_bootstrap_input(self) -> None:
        """導出値を bootstrap 入力として渡されたら fail-closed とする。"""
        step = get_workflow("asdw-web").get_step("1.3")
        bootstrap = {
            "LOCATION": step.default_params["data_location"],
            "RESOURCE_SUFFIX": step.default_params["data_resource_suffix"],
            "DATA_VNET_CIDR": step.default_params["data_vnet_cidr"],
            "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR": step.default_params[
                "data_private_endpoint_subnet_cidr"
            ],
            "DATA_ACI_SUBNET_CIDR": step.default_params["data_aci_subnet_cidr"],
            "DATA_VERIFY_ACI_IMAGE": "registry.example/verify:v1",
        }
        with self.assertRaises(AsdwDataDeployContextError):
            build_asdw_data_deploy_bootstrap_context(
                workflow_params={"resource_group": "rg-example"},
                bootstrap_inputs=bootstrap,
                subscription_id="00000000-0000-0000-0000-000000000001",
            )


class TestDuckTypedStepCompatibility(unittest.TestCase):
    """`WorkflowDef` は StepDef 互換のダックタイプ step も受け入れる。

    fan-out 展開後の `FanoutChildStep` を含む合成 WorkflowDef が構築されるため、
    新規フィールドの検証で `AttributeError` を出してはならない。
    """

    def test_step_without_new_fields_is_accepted(self) -> None:
        class _MinimalStep:
            id = "1"
            title = "minimal"
            is_container = False
            depends_on: list = []

        wf = _make_workflow([_MinimalStep()])
        self.assertEqual(wf.get_step("1").id, "1")

    def test_fanout_child_inherits_param_declaration(self) -> None:
        from hve.fanout_expander import _make_child

        base = StepDef(
            id="1.3",
            title="deploy",
            custom_agent=None,
            required_params=["resource_group", "data_location"],
            default_params={"data_location": "japaneast"},
        )
        child = _make_child(base, "APP-009")
        self.assertEqual(list(child.required_params), ["resource_group", "data_location"])
        self.assertEqual(dict(child.default_params), {"data_location": "japaneast"})

    def test_workflow_with_fanout_children_validates(self) -> None:
        from hve.fanout_expander import _make_child

        base = StepDef(
            id="1.3",
            title="deploy",
            custom_agent=None,
            required_params=["data_location"],
            default_params={"data_location": "japaneast"},
        )
        wf = _make_workflow([_make_child(base, "APP-009")])
        self.assertEqual(wf.get_step("1.3/APP-009").title, "deploy (APP-009)")


class TestApplyStepDefaultParams(unittest.TestCase):
    """`apply_step_default_params` の適用規則（FR-DAG-07）。"""

    def setUp(self) -> None:
        self.wf = _make_workflow([
            StepDef(
                id="1",
                title="root",
                custom_agent=None,
                required_params=["alpha", "beta"],
                default_params={"alpha": "A", "beta": "B"},
            ),
            StepDef(
                id="2",
                title="other",
                custom_agent=None,
                depends_on=["1"],
                required_params=["gamma"],
                default_params={"gamma": "G"},
            ),
        ])

    def test_fills_missing_keys(self) -> None:
        params: dict = {}
        applied = apply_step_default_params(self.wf, {"1"}, params)
        self.assertEqual(applied, ["alpha", "beta"])
        self.assertEqual(params["alpha"], "A")
        self.assertEqual(params["beta"], "B")

    def test_fills_none_values(self) -> None:
        params = {"alpha": None}
        applied = apply_step_default_params(self.wf, {"1"}, params)
        self.assertIn("alpha", applied)
        self.assertEqual(params["alpha"], "A")

    def test_fills_blank_only_values(self) -> None:
        params = {"alpha": "   "}
        applied = apply_step_default_params(self.wf, {"1"}, params)
        self.assertIn("alpha", applied)
        self.assertEqual(params["alpha"], "A")

    def test_does_not_override_existing_value(self) -> None:
        params = {"alpha": "explicit"}
        applied = apply_step_default_params(self.wf, {"1"}, params)
        self.assertNotIn("alpha", applied)
        self.assertEqual(params["alpha"], "explicit")

    def test_skips_inactive_steps(self) -> None:
        params: dict = {}
        apply_step_default_params(self.wf, {"1"}, params)
        self.assertNotIn("gamma", params)

    def test_normalizes_fanout_child_step_ids(self) -> None:
        params: dict = {}
        applied = apply_step_default_params(self.wf, {"2/APP-009-S001"}, params)
        self.assertEqual(applied, ["gamma"])
        self.assertEqual(params["gamma"], "G")

    def test_empty_active_steps_applies_nothing(self) -> None:
        params: dict = {}
        applied = apply_step_default_params(self.wf, set(), params)
        self.assertEqual(applied, [])
        self.assertEqual(params, {})

    def test_returns_sorted_unique_keys(self) -> None:
        params: dict = {}
        applied = apply_step_default_params(self.wf, {"1", "2"}, params)
        self.assertEqual(applied, ["alpha", "beta", "gamma"])

    def test_non_string_existing_value_is_left_for_preflight(self) -> None:
        """型不正な値は既定値で握り潰さず、pre-flight が検出できるよう温存する。"""
        params = {"alpha": 123}
        applied = apply_step_default_params(self.wf, {"1"}, params)
        self.assertNotIn("alpha", applied)
        self.assertEqual(params["alpha"], 123)


if __name__ == "__main__":
    unittest.main()
