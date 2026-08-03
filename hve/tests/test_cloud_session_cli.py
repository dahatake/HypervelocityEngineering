"""test_cloud_session_cli.py — Cloud Session CLI / GUI argv 伝搬テスト。"""

from __future__ import annotations

import json
import os
import unittest
import unittest.mock

from hve.__main__ import _build_config, _build_parser
from hve.gui.orchestrate_args import OrchestrateArgs


class TestCloudSessionCliArgs(unittest.TestCase):
    def test_build_config_reads_cloud_session_cli_args(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "orchestrate",
            "--workflow", "akm",
            "--cloud-session",
            "--cloud-session-owner", "alice",
            "--cloud-session-repository-name", "svc",
            "--cloud-session-branch", "feature/cloud",
            "--cloud-session-max-concurrency", "3",
            "--cloud-session-integration-id", "integration-1",
            "--cloud-session-mc-base-url", "https://mc.example.test",
            "--cloud-session-step-overrides", json.dumps({"1": True}),
            "--cloud-session-subtask-overrides", json.dumps({"review": False}),
        ])
        cfg = _build_config(args)
        self.assertTrue(cfg.cloud_session_enabled)
        self.assertEqual(cfg.cloud_session_repository_owner, "alice")
        self.assertEqual(cfg.cloud_session_repository_name, "svc")
        self.assertEqual(cfg.cloud_session_repository_branch, "feature/cloud")
        self.assertEqual(cfg.cloud_session_max_concurrency, 3)
        self.assertEqual(cfg.cloud_session_integration_id, "integration-1")
        self.assertEqual(cfg.cloud_session_mc_base_url, "https://mc.example.test")
        self.assertEqual(cfg.cloud_session_step_overrides, {"1": True})
        self.assertEqual(cfg.cloud_session_subtask_overrides, {"review": False})

    def test_no_cloud_session_overrides_enabled_environment(self) -> None:
        parser = _build_parser()
        with unittest.mock.patch.dict(os.environ, {"HVE_CLOUD_SESSION_ENABLED": "true"}, clear=False):
            args = parser.parse_args(["orchestrate", "--workflow", "akm", "--no-cloud-session"])
            cfg = _build_config(args)
        self.assertFalse(cfg.cloud_session_enabled)

    def test_gui_orchestrate_args_to_argv_contains_cloud_session_args(self) -> None:
        args = OrchestrateArgs(
            workflow="akm",
            cloud_session_enabled=True,
            cloud_session_owner="alice",
            cloud_session_repository_name="svc",
            cloud_session_branch="feature/cloud",
            cloud_session_max_concurrency=3,
            cloud_session_integration_id="integration-1",
            cloud_session_mc_base_url="https://mc.example.test",
            cloud_session_step_overrides=json.dumps({"1": True}),
            cloud_session_subtask_overrides=json.dumps({"review": False}),
        )
        argv = args.to_argv()
        self.assertIn("--cloud-session", argv)
        self.assertIn("--cloud-session-owner", argv)
        self.assertIn("alice", argv)
        self.assertIn("--cloud-session-repository-name", argv)
        self.assertIn("svc", argv)
        self.assertIn("--cloud-session-branch", argv)
        self.assertIn("feature/cloud", argv)
        self.assertIn("--cloud-session-max-concurrency", argv)
        self.assertIn("3", argv)
        self.assertIn("--cloud-session-step-overrides", argv)
        self.assertIn(json.dumps({"1": True}), argv)
        self.assertIn("--workbench", argv)
        self.assertIn("off", argv)

    def test_gui_orchestrate_args_round_trips_through_cli_config(self) -> None:
        original = OrchestrateArgs(
            workflow="akm",
            cloud_session_enabled=True,
            cloud_session_owner="alice",
            cloud_session_repository_name="svc",
            cloud_session_branch="feature/cloud",
            cloud_session_max_concurrency=3,
            cloud_session_integration_id="integration-1",
            cloud_session_mc_base_url="https://mc.example.test",
            cloud_session_step_overrides=json.dumps({"1": True}),
            cloud_session_subtask_overrides=json.dumps({"review": False}),
        )
        parsed = _build_parser().parse_args(original.to_argv())
        cfg = _build_config(parsed)
        self.assertTrue(cfg.cloud_session_enabled)
        self.assertEqual(cfg.cloud_session_repository_owner, "alice")
        self.assertEqual(cfg.cloud_session_repository_name, "svc")
        self.assertEqual(cfg.cloud_session_repository_branch, "feature/cloud")
        self.assertEqual(cfg.cloud_session_max_concurrency, 3)
        self.assertEqual(cfg.cloud_session_integration_id, "integration-1")
        self.assertEqual(cfg.cloud_session_mc_base_url, "https://mc.example.test")
        self.assertEqual(cfg.cloud_session_step_overrides, {"1": True})
        self.assertEqual(cfg.cloud_session_subtask_overrides, {"review": False})

    def test_gui_disable_round_trips_through_cli_config(self) -> None:
        parsed = _build_parser().parse_args(
            OrchestrateArgs(workflow="akm", cloud_session_enabled=False).to_argv()
        )
        cfg = _build_config(parsed)
        self.assertFalse(cfg.cloud_session_enabled)

    def test_gui_orchestrate_args_to_argv_can_disable_cloud_session(self) -> None:
        argv = OrchestrateArgs(workflow="akm", cloud_session_enabled=False).to_argv()
        self.assertIn("--no-cloud-session", argv)
        self.assertNotIn("--cloud-session", argv)


class TestFleetModeCliArgs(unittest.TestCase):
    def test_build_config_reads_fleet_mode_cli_args(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["orchestrate", "--workflow", "akm", "--fleet-mode"])
        cfg = _build_config(args)
        self.assertTrue(cfg.fleet_mode_enabled)

    def test_no_fleet_mode_overrides_enabled_environment(self) -> None:
        parser = _build_parser()
        with unittest.mock.patch.dict(os.environ, {"HVE_FLEET_MODE_ENABLED": "true"}, clear=False):
            args = parser.parse_args(["orchestrate", "--workflow", "akm", "--no-fleet-mode"])
            cfg = _build_config(args)
        self.assertFalse(cfg.fleet_mode_enabled)

    def test_gui_orchestrate_args_to_argv_contains_fleet_mode_args(self) -> None:
        argv = OrchestrateArgs(workflow="akm", fleet_mode_enabled=True).to_argv()
        self.assertIn("--fleet-mode", argv)

    def test_gui_orchestrate_args_to_argv_omits_fleet_mode_when_unset(self) -> None:
        argv = OrchestrateArgs(workflow="akm", fleet_mode_enabled=None).to_argv()
        self.assertNotIn("--fleet-mode", argv)
        self.assertNotIn("--no-fleet-mode", argv)

    def test_gui_orchestrate_args_to_argv_can_disable_fleet_mode(self) -> None:
        argv = OrchestrateArgs(workflow="akm", fleet_mode_enabled=False).to_argv()
        self.assertIn("--no-fleet-mode", argv)
        self.assertNotIn("--fleet-mode", argv)


if __name__ == "__main__":
    unittest.main()
