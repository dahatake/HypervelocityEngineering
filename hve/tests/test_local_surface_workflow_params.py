"""test_local_surface_workflow_params.py — FR-LOCAL-SURFACE-01 (b) の契約テスト。

検証項目:
  1. `--create-remote-mcp-server` / `--no-create-remote-mcp-server` / `--tdd-max-retries`
     が `orchestrate` の CLI 引数として存在すること
  2. 明示指定が `_build_params` / `_collect_params_non_interactive` の双方から
     params へ届くこと
  3. 未指定のときは params へ現れず、既存の既定値解決（対話ウィザード /
     テンプレート既定 / 環境変数）を壊さないこと
  4. `WorkflowDef.params` が宣言していない Workflow へは渡らないこと
  5. `OrchestrateArgs` から同じフラグが argv へ出ること（GUI / Prompt 版の経路）

根拠: hve-dev/requirement-definition.md §5.21 FR-LOCAL-SURFACE-01
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_local_surface", os.path.abspath(_main_path))
assert _spec is not None and _spec.loader is not None
_main_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)

_build_parser = _main_mod._build_parser
_build_params = _main_mod._build_params

from hve.gui.orchestrate_args import OrchestrateArgs
from hve.orchestrator import _collect_params_non_interactive
from hve.workflow_registry import get_workflow, list_workflows


def _parse(*extra: str):
    return _build_parser().parse_args(
        ["orchestrate", "--workflow", "asdw-web", "--dry-run", *extra]
    )


class TestDeclaredWorkflowsAreUnchanged(unittest.TestCase):
    """本タスクは registry の宣言を変更しない（実測値の固定）。"""

    def test_create_remote_mcp_server_is_declared_by_two_workflows(self) -> None:
        ids = sorted(
            w.id for w in list_workflows() if "create_remote_mcp_server" in (w.params or [])
        )
        self.assertEqual(ids, ["aad-web", "asdw-web"])

    def test_tdd_max_retries_is_declared_by_three_workflows(self) -> None:
        ids = sorted(
            w.id for w in list_workflows() if "tdd_max_retries" in (w.params or [])
        )
        self.assertEqual(ids, ["aagd", "adfdv", "asdw-web"])


class TestCliFlags(unittest.TestCase):
    def test_create_remote_mcp_server_defaults_to_unset(self) -> None:
        self.assertIsNone(_parse().create_remote_mcp_server)

    def test_create_remote_mcp_server_can_be_enabled(self) -> None:
        self.assertIs(_parse("--create-remote-mcp-server").create_remote_mcp_server, True)

    def test_create_remote_mcp_server_can_be_disabled(self) -> None:
        self.assertIs(
            _parse("--no-create-remote-mcp-server").create_remote_mcp_server, False
        )

    def test_tdd_max_retries_defaults_to_unset(self) -> None:
        self.assertIsNone(_parse().tdd_max_retries)

    def test_tdd_max_retries_accepts_an_integer(self) -> None:
        self.assertEqual(_parse("--tdd-max-retries", "9").tdd_max_retries, 9)


class TestBuildParamsProjection(unittest.TestCase):
    def test_explicit_values_reach_params(self) -> None:
        params = _build_params(_parse("--no-create-remote-mcp-server", "--tdd-max-retries", "9"))
        self.assertIs(params["create_remote_mcp_server"], False)
        self.assertEqual(params["tdd_max_retries"], 9)

    def test_unset_values_do_not_appear(self) -> None:
        """未指定なら params へ入れない。既存の既定値解決を上書きしない。"""
        params = _build_params(_parse())
        self.assertNotIn("create_remote_mcp_server", params)
        self.assertNotIn("tdd_max_retries", params)

    def test_undeclared_workflow_does_not_receive_the_params(self) -> None:
        args = _build_parser().parse_args(
            [
                "orchestrate",
                "--workflow",
                "ard",
                "--dry-run",
                "--create-remote-mcp-server",
                "--tdd-max-retries",
                "9",
            ]
        )
        params = _build_params(args)
        self.assertNotIn("create_remote_mcp_server", params)
        self.assertNotIn("tdd_max_retries", params)


class TestNonInteractiveCollection(unittest.TestCase):
    def test_explicit_values_reach_params(self) -> None:
        params = _collect_params_non_interactive(
            get_workflow("asdw-web"),
            {"create_remote_mcp_server": False, "tdd_max_retries": 9},
        )
        self.assertIs(params["create_remote_mcp_server"], False)
        self.assertEqual(params["tdd_max_retries"], 9)

    def test_unset_values_do_not_appear(self) -> None:
        params = _collect_params_non_interactive(get_workflow("asdw-web"), {})
        self.assertNotIn("create_remote_mcp_server", params)
        self.assertNotIn("tdd_max_retries", params)

    def test_undeclared_workflow_does_not_receive_the_params(self) -> None:
        params = _collect_params_non_interactive(
            get_workflow("adfd"),
            {"create_remote_mcp_server": True, "tdd_max_retries": 9},
        )
        self.assertNotIn("create_remote_mcp_server", params)
        self.assertNotIn("tdd_max_retries", params)


class TestOrchestrateArgsArgv(unittest.TestCase):
    def test_workflow_params_are_emitted(self) -> None:
        argv = OrchestrateArgs(
            workflow="asdw-web", create_remote_mcp_server=False, tdd_max_retries=9
        ).to_argv()
        self.assertIn("--no-create-remote-mcp-server", argv)
        self.assertIn("--tdd-max-retries", argv)
        self.assertEqual(argv[argv.index("--tdd-max-retries") + 1], "9")

    def test_enabled_form_is_emitted(self) -> None:
        argv = OrchestrateArgs(
            workflow="aad-web", create_remote_mcp_server=True
        ).to_argv()
        self.assertIn("--create-remote-mcp-server", argv)

    def test_include_kpi_okr_is_emitted(self) -> None:
        argv = OrchestrateArgs(workflow="ard", include_kpi_okr=True).to_argv()
        self.assertIn("--include-kpi-okr", argv)

    def test_defaults_emit_nothing(self) -> None:
        argv = OrchestrateArgs(workflow="asdw-web").to_argv()
        for flag in (
            "--create-remote-mcp-server",
            "--no-create-remote-mcp-server",
            "--tdd-max-retries",
            "--include-kpi-okr",
        ):
            self.assertNotIn(flag, argv)

    def test_emitted_argv_is_accepted_by_the_parser(self) -> None:
        """argv → parser の往復で値が保たれる（フラグ名の綴り違いを検出する）。"""
        argv = OrchestrateArgs(
            workflow="asdw-web", create_remote_mcp_server=True, tdd_max_retries=7
        ).to_argv()
        parsed = _build_parser().parse_args(argv)
        self.assertIs(parsed.create_remote_mcp_server, True)
        self.assertEqual(parsed.tdd_max_retries, 7)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
