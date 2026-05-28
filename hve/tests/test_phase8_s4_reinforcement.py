"""Phase 8 S-4: Custom Agent 廃止後の補強テスト群。

テスト対象:
1. `.github/scripts/validate-io-contract.py` の validate_io_contract / collect_producers
2. Phase 5 `customAgent=""` 固定化 (`.github/scripts/{bash,powershell}/lib/copilot-assign.*`)
3. `.github/workflows/create-subissues-from-pr.yml` 内 create_issue Prompt 注入ロジック

詳細は work/custom-agent-tasks-phase8/plan.md S-4 を参照。
"""
from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_validate_io_contract_module():
    """`.github/scripts/validate-io-contract.py` を動的に import する。

    Python 規約外の `.github/scripts/` 配下からの import を可能にするため、
    importlib.util を経由する。
    """
    script_path = REPO_ROOT / ".github" / "scripts" / "validate-io-contract.py"
    spec = importlib.util.spec_from_file_location("validate_io_contract", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_io_contract"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# S-4 (1): validate-io-contract.py の単体テスト
# ---------------------------------------------------------------------------

class TestValidateIoContract(unittest.TestCase):
    """`validate_io_contract` の正常系・異常系を検証する。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_validate_io_contract_module()

    def test_valid_minimal_contract(self) -> None:
        contract = {
            "inputs": [
                {"path": "docs/in.md", "required": True, "kind": "static"},
            ],
            "outputs": [
                {"path": "work/out.md", "required": True, "mode": "create"},
            ],
        }
        errs = self.mod.validate_io_contract("TestAgent", contract)
        self.assertEqual(errs, [])

    def test_missing_inputs(self) -> None:
        contract = {
            "outputs": [
                {"path": "work/out.md", "required": True, "mode": "create"},
            ],
        }
        errs = self.mod.validate_io_contract("X", contract)
        self.assertTrue(any("missing io_contract.inputs" in e for e in errs))

    def test_missing_outputs(self) -> None:
        contract = {
            "inputs": [
                {"path": "docs/in.md", "required": True, "kind": "static"},
            ],
        }
        errs = self.mod.validate_io_contract("X", contract)
        self.assertTrue(any("missing io_contract.outputs" in e for e in errs))

    def test_inputs_must_be_list(self) -> None:
        contract = {
            "inputs": {"path": "x"},
            "outputs": [],
        }
        errs = self.mod.validate_io_contract("X", contract)
        self.assertTrue(any("must be a list" in e for e in errs))

    def test_invalid_input_kind(self) -> None:
        contract = {
            "inputs": [
                {"path": "in.md", "required": True, "kind": "bogus_kind"},
            ],
            "outputs": [],
        }
        errs = self.mod.validate_io_contract("X", contract)
        self.assertTrue(any("inputs[0].kind invalid" in e for e in errs))

    def test_invalid_output_mode(self) -> None:
        contract = {
            "inputs": [],
            "outputs": [
                {"path": "out.md", "required": True, "mode": "replace"},
            ],
        }
        errs = self.mod.validate_io_contract("X", contract)
        self.assertTrue(any("outputs[0].mode invalid" in e for e in errs))

    def test_required_must_be_bool(self) -> None:
        contract = {
            "inputs": [{"path": "in.md", "required": "yes", "kind": "static"}],
            "outputs": [],
        }
        errs = self.mod.validate_io_contract("X", contract)
        self.assertTrue(any("required must be bool" in e for e in errs))

    def test_missing_path(self) -> None:
        contract = {
            "inputs": [{"required": True, "kind": "static"}],
            "outputs": [],
        }
        errs = self.mod.validate_io_contract("X", contract)
        self.assertTrue(any("inputs[0].path missing" in e for e in errs))


class TestCollectProducers(unittest.TestCase):
    """`collect_producers` の動作確認。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_validate_io_contract_module()

    def test_collect_producers_basic(self) -> None:
        agents = {
            "A": {"outputs": [{"path": "out/a.md"}]},
            "B": {"outputs": [{"path": "out/b.md"}, {"path": "out/shared.md"}]},
            "C": {"outputs": [{"path": "out/shared.md"}]},
        }
        producers = self.mod.collect_producers(agents)
        self.assertEqual(producers["out/a.md"], ["A"])
        self.assertEqual(sorted(producers["out/shared.md"]), ["B", "C"])

    def test_collect_producers_skips_invalid(self) -> None:
        agents = {
            "A": {"outputs": [{"path": ""}, "not_a_dict", {"no_path_key": "x"}]},
        }
        producers = self.mod.collect_producers(agents)
        self.assertEqual(dict(producers), {})


# ---------------------------------------------------------------------------
# S-4 (2): customAgent="" 固定化の静的検査
# ---------------------------------------------------------------------------

class TestCustomAgentEmptyFixation(unittest.TestCase):
    """Phase 5 で bash / PowerShell の lib スクリプト内 customAgent が
    常に空文字で SDK へ渡されることを静的に検査する。
    """

    BASH_PATH = REPO_ROOT / ".github" / "scripts" / "bash" / "lib" / "copilot-assign.sh"
    PWSH_PATH = REPO_ROOT / ".github" / "scripts" / "powershell" / "lib" / "copilot-assign.ps1"

    def test_bash_lib_has_empty_custom_agent(self) -> None:
        if not self.BASH_PATH.exists():
            self.skipTest(f"bash lib not found: {self.BASH_PATH}")
        text = self.BASH_PATH.read_text(encoding="utf-8")
        # Phase 5 固定化: gh api graphql へ `-f "customAgent="` として空値を渡す
        self.assertIn(
            'customAgent="',
            text,
            "bash lib should pass customAgent= as empty value to gh CLI",
        )
        # 同時に、非空の Custom Agent 名をハードコードしていないことを確認
        self.assertNotRegex(
            text,
            r'customAgent=\$\{custom_agent\}',
            "bash lib must not interpolate custom_agent variable",
        )

    def test_pwsh_lib_has_empty_custom_agent(self) -> None:
        if not self.PWSH_PATH.exists():
            self.skipTest(f"powershell lib not found: {self.PWSH_PATH}")
        text = self.PWSH_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'customAgent="',
            text,
            "powershell lib should pass customAgent= as empty value to gh CLI",
        )
        self.assertNotRegex(
            text,
            r'customAgent=\$CustomAgent',
            "powershell lib must not interpolate CustomAgent variable",
        )


# ---------------------------------------------------------------------------
# S-4 (3): create_issue Python heredoc Prompt 注入ロジックの検査
# ---------------------------------------------------------------------------
# NOTE: `.github/workflows/create-subissues-from-pr.yml` の create_issue は
# Phase 4 レポートにより primary sub-issue creation 経路で既に Prompt 注入済みの
# Issue を PR から分割する経路であり、トップレベルの同性を単体テストとして
# 独立検証するのは現実的ではない（Prompt 本文は上流依存）。Phase 8 S-4 では
# この課題をプレースホルダとして記録し、将来 primary 経路と独立した Prompt 注入が
# 追加された際に実テストを追加するとした（work/custom-agent-tasks-migration.md #5）。


if __name__ == "__main__":
    unittest.main()
