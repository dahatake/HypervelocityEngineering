"""ASDW Step 1.3 の Azure CLI 起動が Windows で解決できることを固定する。

live canary (`20260728T034239-836daa`) の Wave 9 で Step 1.3 が
`could not run the Azure CLI to resolve SUBSCRIPTION_ID` により失敗した。
原因は Windows の ``CreateProcess`` が拡張子なしコマンドへ ``.exe`` しか
補完せず、Azure CLI の実体 ``az.CMD`` を起動できないこと。
``hve/__main__.py::_azure_account_available`` は既に ``shutil.which`` で
解決してから argv[0] に渡しており、ASDW の 2 箇所だけが素の ``"az"`` を
渡していた。ここではその規約を ASDW 経路にも固定する。
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hve import asdw_data_script_launcher as launcher  # noqa: E402
from hve import runner as runner_module  # noqa: E402
from hve.asdw_data_runtime_context import AsdwDataDeployContextError  # noqa: E402


class TestResolveAzureCliExecutable(unittest.TestCase):
    """``resolve_azure_cli_executable`` の解決順序と fail-closed を固定する。"""

    def test_prefers_trusted_runtime_path(self) -> None:
        """信頼済みルート上で解決できる場合は継承 PATH を参照しない。"""
        calls: list[object] = []

        def fake_which(cmd: str, path: object = None) -> str | None:
            calls.append(path)
            return "/trusted/az.CMD" if path is not None else "/inherited/az"

        with mock.patch.object(launcher.shutil, "which", side_effect=fake_which):
            resolved = launcher.resolve_azure_cli_executable()

        self.assertEqual(resolved, "/trusted/az.CMD")
        self.assertEqual(len(calls), 1, "信頼済みルートで解決できたら追加探索しない")
        self.assertIsNotNone(calls[0])

    def test_falls_back_to_inherited_path(self) -> None:
        """信頼済みルートに無い場合のみ継承 PATH へフォールバックする。"""

        def fake_which(cmd: str, path: object = None) -> str | None:
            return None if path is not None else "/inherited/az"

        with mock.patch.object(launcher.shutil, "which", side_effect=fake_which):
            resolved = launcher.resolve_azure_cli_executable()

        self.assertEqual(resolved, "/inherited/az")

    def test_fails_closed_when_azure_cli_missing(self) -> None:
        """どちらでも解決できない場合は実行可能な指示付きで停止する。"""
        with mock.patch.object(launcher.shutil, "which", return_value=None):
            with self.assertRaises(launcher.ScriptLauncherError) as caught:
                launcher.resolve_azure_cli_executable()

        self.assertIn("az", str(caught.exception))

    def test_resolves_the_real_azure_cli_when_installed(self) -> None:
        """実機に Azure CLI がある場合、実在するパスへ解決する。"""
        try:
            resolved = launcher.resolve_azure_cli_executable()
        except launcher.ScriptLauncherError:
            self.skipTest("Azure CLI 未インストール環境")
        self.assertTrue(Path(resolved).exists(), f"解決結果が実在しない: {resolved}")
        self.assertNotEqual(resolved, "az", "素のコマンド名は Windows で起動できない")


class TestSubscriptionIdUsesResolvedExecutable(unittest.TestCase):
    """runner の SUBSCRIPTION_ID 解決が解決済みパスを起動することを固定する。"""

    def test_invokes_resolved_executable(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="sub-id\n", stderr="")
        with mock.patch.object(
            runner_module,
            "resolve_azure_cli_executable",
            return_value="/resolved/az.CMD",
        ), mock.patch.object(runner_module.subprocess, "run", return_value=completed) as run_mock:
            resolved = runner_module._resolve_asdw_data_deploy_subscription_id()

        self.assertEqual(resolved, "sub-id")
        argv = run_mock.call_args.args[0]
        self.assertEqual(argv[0], "/resolved/az.CMD")
        self.assertEqual(argv[1:], ["account", "show", "--query", "id", "--output", "tsv"])

    def test_reports_actionable_error_when_cli_missing(self) -> None:
        with mock.patch.object(
            runner_module,
            "resolve_azure_cli_executable",
            side_effect=launcher.ScriptLauncherError("azure cli not found"),
        ):
            with self.assertRaises(AsdwDataDeployContextError):
                runner_module._resolve_asdw_data_deploy_subscription_id()


class TestIdentityReadBackUsesResolvedExecutable(unittest.TestCase):
    """launcher の client ID 読み戻しが解決済みパスを起動することを固定する。"""

    def test_invokes_resolved_executable(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="client-id\n", stderr="")
        environment = {
            "RESOURCE_GROUP": "dahatake-test",
            "DATA_DEPLOY_IDENTITY_ID": "/subscriptions/s/resourceGroups/r/providers/"
            "Microsoft.ManagedIdentity/userAssignedIdentities/data-deploy-identity",
        }
        with mock.patch.object(
            launcher,
            "resolve_azure_cli_executable",
            return_value="/resolved/az.CMD",
        ), mock.patch.object(launcher.subprocess, "run", return_value=completed) as run_mock:
            resolved = launcher._resolve_deploy_identity_client_id(environment)

        self.assertEqual(resolved, "client-id")
        argv = run_mock.call_args.args[0]
        self.assertEqual(argv[0], "/resolved/az.CMD")
        self.assertEqual(argv[1:3], ["identity", "show"])


class TestNoBareAzureCliInvocation(unittest.TestCase):
    """素の ``"az"`` を argv[0] に渡す退行をソースレベルで禁止する。"""

    _BARE_AZ_ARGV = re.compile(r'^\s*(?:\[\s*)?"az"\s*,', re.MULTILINE)

    def test_asdw_sources_never_spawn_bare_az(self) -> None:
        package_root = Path(__file__).resolve().parents[1]
        for name in ("runner.py", "asdw_data_script_launcher.py"):
            source = (package_root / name).read_text(encoding="utf-8")
            self.assertIsNone(
                self._BARE_AZ_ARGV.search(source),
                f"{name} が素の \"az\" を argv[0] に渡している（Windows で起動不可）",
            )


if __name__ == "__main__":
    unittest.main()
