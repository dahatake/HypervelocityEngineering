"""FR-CLI-82 の CLI startup preflight entrypoint 契約テスト。"""

from __future__ import annotations

import ast
import contextlib
import importlib
import inspect
import io
import subprocess
import unittest
from pathlib import Path
from unittest import mock

_MAIN_PATH = Path(__file__).resolve().parents[1] / "__main__.py"
_PREFLIGHT_NAME = "_run_startup_configuration_preflight"
_SECRET_TOKEN = "ghp_startup_preflight_secret_must_not_be_logged"


def _main_function(name: str) -> ast.FunctionDef:
    module = ast.parse(
        _MAIN_PATH.read_text(encoding="utf-8-sig"),
        filename=str(_MAIN_PATH),
    )
    return next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _call_lines(function: ast.FunctionDef, name: str) -> list[int]:
    return sorted(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    )


class TestStartupConfigurationPreflightHelper(unittest.TestCase):
    """共有 helper の公開形と失敗時の fail-closed 契約を固定する。"""

    @staticmethod
    def _helper():
        main_module = importlib.import_module("hve.__main__")
        return getattr(main_module, _PREFLIGHT_NAME)

    def test_signature_keeps_shared_cli_contract(self) -> None:
        parameters = inspect.signature(self._helper()).parameters

        self.assertEqual(
            list(parameters),
            ["config", "workflow_id", "active_steps", "check_remote"],
        )
        self.assertEqual(
            parameters["active_steps"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )
        self.assertEqual(parameters["active_steps"].default, ())
        self.assertEqual(
            parameters["check_remote"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )
        self.assertIs(parameters["check_remote"].default, False)

    def test_failure_reports_all_errors_without_token_value_and_returns_false(self) -> None:
        main_module = importlib.import_module("hve.__main__")
        config = main_module.SDKConfig(
            create_pr=True,
            repo="not-an-owner-repo",
            base_branch="main",
            github_token=_SECRET_TOKEN,
        )
        stderr = io.StringIO()
        stdout = io.StringIO()

        def no_network(command, *args, **kwargs):
            command_parts = [str(part) for part in command]
            if "ls-remote" in command_parts:
                raise AssertionError("check_remote=False must not run git ls-remote")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with mock.patch.object(config, "resolve_token", return_value=""), mock.patch(
            "subprocess.run", side_effect=no_network
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = self._helper()(
                config,
                "aas",
                check_remote=False,
            )

        error_output = stderr.getvalue()
        all_output = error_output + stdout.getvalue()
        self.assertIs(result, False)
        self.assertIn("repo", error_output.lower())
        self.assertIn("token", error_output.lower())
        self.assertNotIn(_SECRET_TOKEN, all_output)


class TestStartupConfigurationPreflightEntrypointOrder(unittest.TestCase):
    """CLI 入口の呼出し順をソース解析だけで検証する。"""

    def _assert_preflight_precedes_execution(self, function_name: str) -> None:
        function = _main_function(function_name)
        preflight_lines = _call_lines(function, _PREFLIGHT_NAME)
        auth_lines = _call_lines(function, "_run_copilot_auth_preflight")
        workflow_lines = _call_lines(function, "run_workflow")

        self.assertEqual(
            len(preflight_lines),
            1,
            f"{function_name} must call {_PREFLIGHT_NAME} exactly once",
        )
        self.assertTrue(
            auth_lines,
            f"{function_name} must retain _run_copilot_auth_preflight",
        )
        self.assertTrue(
            workflow_lines,
            f"{function_name} must retain run_workflow",
        )
        self.assertLess(preflight_lines[0], min(auth_lines))
        self.assertLess(preflight_lines[0], min(workflow_lines))

    def test_non_interactive_cli_runs_shared_preflight_first(self) -> None:
        self._assert_preflight_precedes_execution("_cmd_orchestrate")

    def test_cli_wizard_runs_shared_preflight_first(self) -> None:
        self._assert_preflight_precedes_execution("_cmd_run_interactive")


if __name__ == "__main__":
    unittest.main()