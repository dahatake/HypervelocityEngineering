"""ADFD（Dataflow Design）に欠落していた 4 Agent / 4 Step の契約テスト。

`adfdv`（Dataflow Dev）の各 Step は次の 4 ドキュメントを `required_input_paths`
として要求するが、これらを生成する Agent が ADFD に存在しなかった。

  - docs/dataflow/dataflow-data-model.md
  - docs/dataflow/dataflow-app-catalog.md
  - docs/dataflow/dataflow-service-catalog.md
  - docs/dataflow/dataflow-test-strategy.md

本テストは以下を固定する（FR-WF-ADFD-01〜05）:
  - 4 Prompt が実在し `<output_contract>` に所定の出力パスを 1 件だけ宣言すること
  - ADFD registry に 4 Step が存在し `output_paths` が 4 パスと一致すること
  - 4 Step が既存 Step 1/2/3 の上流（DAG 根側）に位置すること
  - 4 つの io-contract が実在し `yaml.safe_load` に成功し outputs が一致すること
  - `.github/io-contract-exceptions.yaml` に当該 4 パスが含まれないこと
  - 既存 Step 1/2/3 の ID / Agent / 出力宣言が不変であること
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_DIR = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES_DIR = _REPO_ROOT / ".github" / "scripts" / "templates" / "adfd"
_IO_CONTRACTS_DIR = _REPO_ROOT / ".github" / "io-contracts"
_EXCEPTIONS_FILE = _REPO_ROOT / ".github" / "io-contract-exceptions.yaml"

sys.path.insert(0, str(_REPO_ROOT / "hve"))
from workflow_registry import get_root_steps, get_step, get_workflow  # type: ignore[import]


# Step ID → (Agent 名, 出力パス, 依存元 Step ID)
_NEW_STEPS: dict[str, tuple[str, str, list[str]]] = {
    "0.1": ("Arch-Dataflow-DataModel", "docs/dataflow/dataflow-data-model.md", []),
    "0.2": ("Arch-Dataflow-AppCatalog", "docs/dataflow/dataflow-app-catalog.md", ["0.1"]),
    "4": ("Arch-Dataflow-ServiceCatalog", "docs/dataflow/dataflow-service-catalog.md", ["0.2"]),
    "5": ("Arch-Dataflow-TestStrategy", "docs/dataflow/dataflow-test-strategy.md", ["4"]),
}

_TARGET_PATHS = [spec[1] for spec in _NEW_STEPS.values()]

# 既存 Step（不変であることを固定する）
_EXISTING_STEPS: dict[str, tuple[str, list[str], list[str]]] = {
    # step_id: (agent, output_paths, output_paths_template)
    "1": ("Arch-Dataflow-AppSpec", [], ["docs/dataflow/apps/{key}-spec.md"]),
    "2": ("Arch-Dataflow-MonitoringDesign", ["docs/dataflow/dataflow-monitoring-design.md"], []),
    "3": ("Arch-Dataflow-TDD-TestSpec", [], ["docs/test-specs/{key}-test-spec.md"]),
}


class TestAdfdDataflowDesignPrompts(unittest.TestCase):
    """4 Agent の Prompt が実在し `<output_contract>` を持つこと。"""

    def test_prompt_files_exist(self) -> None:
        for _step_id, (agent, _path, _deps) in _NEW_STEPS.items():
            prompt = _PROMPTS_DIR / f"{agent}.prompt.md"
            self.assertTrue(prompt.exists(), f"Prompt が存在しません: {prompt}")

    def test_prompt_declares_single_output_path_in_output_contract(self) -> None:
        for _step_id, (agent, path, _deps) in _NEW_STEPS.items():
            prompt = _PROMPTS_DIR / f"{agent}.prompt.md"
            if not prompt.exists():
                self.fail(f"Prompt が存在しません: {prompt}")
            body = prompt.read_text(encoding="utf-8")
            self.assertIn("<output_contract>", body, f"{agent}: <output_contract> がありません")
            self.assertIn("</output_contract>", body, f"{agent}: </output_contract> がありません")
            start = body.index("<output_contract>")
            end = body.index("</output_contract>")
            contract = body[start:end]
            self.assertIn(path, contract, f"{agent}: <output_contract> に {path} がありません")
            # 主成果物は 1 件だけ（他の 3 パスを混在させない）
            for other in _TARGET_PATHS:
                if other == path:
                    continue
                self.assertNotIn(
                    other,
                    contract,
                    f"{agent}: <output_contract> に他 Agent の出力 {other} が混入しています",
                )

    def test_prompt_delegates_to_dataflow_design_guide_skill(self) -> None:
        for _step_id, (agent, _path, _deps) in _NEW_STEPS.items():
            prompt = _PROMPTS_DIR / f"{agent}.prompt.md"
            if not prompt.exists():
                self.fail(f"Prompt が存在しません: {prompt}")
            body = prompt.read_text(encoding="utf-8")
            self.assertIn(
                "dataflow-design-guide",
                body,
                f"{agent}: Skill dataflow-design-guide への委譲参照がありません",
            )


class TestAdfdDataflowDesignTemplates(unittest.TestCase):
    """新 Step の body template が実在し必須プレースホルダを持つこと。"""

    def test_templates_exist_with_required_placeholders(self) -> None:
        for step_id, (agent, path, _deps) in _NEW_STEPS.items():
            tpl = _TEMPLATES_DIR / f"step-{step_id}.md"
            self.assertTrue(tpl.exists(), f"template が存在しません: {tpl}")
            body = tpl.read_text(encoding="utf-8")
            for placeholder in (
                "{root_ref}",
                "{existing_artifact_policy}",
                "{completion_instruction}",
            ):
                self.assertIn(placeholder, body, f"step-{step_id}.md に {placeholder} がありません")
            self.assertIn(f"`{agent}`", body, f"step-{step_id}.md の ## Custom Agent が不正です")
            self.assertIn(path, body, f"step-{step_id}.md の ## 出力 に {path} がありません")

    def test_existing_templates_depends_section_follows_registry(self) -> None:
        """既存 Step 1/2 は Step.5 依存へ変更されたため `## 依存` も追随していること。"""
        for step_id in ("1", "2"):
            tpl = _TEMPLATES_DIR / f"step-{step_id}.md"
            self.assertTrue(tpl.exists(), f"template が存在しません: {tpl}")
            body = tpl.read_text(encoding="utf-8")
            self.assertNotIn(
                "- {dep}",
                body,
                f"step-{step_id}.md の ## 依存 が未解決プレースホルダのままです",
            )
            self.assertIn(
                "Step.5",
                body,
                f"step-{step_id}.md の ## 依存 に Step.5（テスト戦略書）参照がありません",
            )


class TestAdfdRegistryNewSteps(unittest.TestCase):
    """ADFD registry に 4 Step が追加され、既存 Step の上流であること。"""

    def test_new_steps_exist_with_expected_agent_and_outputs(self) -> None:
        for step_id, (agent, path, deps) in _NEW_STEPS.items():
            step = get_step("adfd", step_id)
            self.assertIsNotNone(step, f"adfd Step {step_id} が存在しません")
            assert step is not None
            self.assertEqual(step.custom_agent, agent)
            self.assertEqual(step.output_paths, [path])
            self.assertEqual(sorted(step.depends_on), sorted(deps))
            self.assertEqual(
                step.body_template_path,
                f"templates/adfd/step-{step_id}.md",
            )

    def test_new_steps_are_upstream_of_existing_steps(self) -> None:
        """DAG 根は新 Step 側であり、既存 Step 1/2 は新 Step の下流であること。"""
        root_ids = sorted(s.id for s in get_root_steps("adfd"))
        self.assertEqual(root_ids, ["0.1"])
        for step_id in ("1", "2"):
            step = get_step("adfd", step_id)
            self.assertIsNotNone(step)
            assert step is not None
            self.assertEqual(step.depends_on, ["5"])

    def test_new_steps_required_inputs_exist_in_repo_or_are_produced(self) -> None:
        """`required_input_paths` は実在パスまたは ADFD 内の上流出力のみであること。"""
        produced = {spec[1] for spec in _NEW_STEPS.values()}
        for step_id in _NEW_STEPS:
            step = get_step("adfd", step_id)
            self.assertIsNotNone(step)
            assert step is not None
            self.assertTrue(step.required_input_paths, f"Step {step_id} の必須入力が空です")
            for path in step.required_input_paths:
                if path in produced:
                    continue
                self.assertTrue(
                    (_REPO_ROOT / path).exists(),
                    f"Step {step_id}: 実在しない入力パスを宣言しています: {path}",
                )

    def test_existing_steps_are_unchanged(self) -> None:
        for step_id, (agent, outputs, outputs_tpl) in _EXISTING_STEPS.items():
            step = get_step("adfd", step_id)
            self.assertIsNotNone(step, f"既存 adfd Step {step_id} が消えています")
            assert step is not None
            self.assertEqual(step.custom_agent, agent)
            self.assertEqual(step.output_paths, outputs)
            self.assertEqual(step.output_paths_template or [], outputs_tpl)

    def test_workflow_step_count(self) -> None:
        wf = get_workflow("adfd")
        self.assertIsNotNone(wf)
        assert wf is not None
        self.assertEqual(len(wf.steps), 7)


class TestAdfdIoContracts(unittest.TestCase):
    """4 Agent の io-contract が実在し registry と一致すること。"""

    def _contract_path(self, step_id: str, agent: str) -> Path:
        return _IO_CONTRACTS_DIR / f"{agent}--adfd--{step_id}.yaml"

    def test_io_contracts_exist_and_parse(self) -> None:
        for step_id, (agent, _path, _deps) in _NEW_STEPS.items():
            fp = self._contract_path(step_id, agent)
            self.assertTrue(fp.exists(), f"io-contract が存在しません: {fp}")
            data = yaml.safe_load(fp.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict, f"{fp.name}: mapping ではありません")
            self.assertIn("inputs", data)
            self.assertIn("outputs", data)

    def test_io_contract_matches_registry(self) -> None:
        for step_id, (agent, path, _deps) in _NEW_STEPS.items():
            fp = self._contract_path(step_id, agent)
            if not fp.exists():
                self.fail(f"io-contract が存在しません: {fp}")
            data = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
            out_paths = {
                (o.get("path") or "").strip()
                for o in (data.get("outputs") or [])
                if isinstance(o, dict)
            }
            self.assertEqual(out_paths, {path})

            step = get_step("adfd", step_id)
            self.assertIsNotNone(step)
            assert step is not None
            required_inputs = {
                (i.get("path") or "").strip()
                for i in (data.get("inputs") or [])
                if isinstance(i, dict)
                and i.get("required") is True
                and i.get("kind") == "agent_artifact"
            }
            self.assertEqual(required_inputs, set(step.required_input_paths))


class TestAdfdIoContractExceptionsRemoved(unittest.TestCase):
    """暫定登録していた 4 パスの例外が削除されていること。"""

    def test_target_paths_not_in_exceptions(self) -> None:
        data = yaml.safe_load(_EXCEPTIONS_FILE.read_text(encoding="utf-8")) or {}
        external = set(data.get("external_paths") or [])
        static = set(data.get("static_paths") or [])
        for path in _TARGET_PATHS:
            self.assertNotIn(path, external, f"external_paths に {path} が残っています")
            self.assertNotIn(path, static, f"static_paths に {path} が混入しています")

    def test_target_paths_have_producer_in_inventory(self) -> None:
        producers: dict[str, list[str]] = {}
        for fp in sorted(_IO_CONTRACTS_DIR.glob("*.yaml")):
            if fp.name.startswith("_"):
                continue
            data = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                continue
            for out in data.get("outputs") or []:
                if isinstance(out, dict) and out.get("path"):
                    producers.setdefault(out["path"], []).append(fp.stem)
        for path in _TARGET_PATHS:
            self.assertTrue(
                producers.get(path),
                f"{path} を出力する io-contract が inventory に存在しません",
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
