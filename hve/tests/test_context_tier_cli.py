"""test_context_tier_cli.py — `--context-tier` CLI 引数 → SDKConfig 伝搬テスト。

context_tier の end-to-end 配線（GUI to_argv → CLI パーサ → SDKConfig）のうち、
CLI パーサ層の責務を検証する。GUI 側の to_argv は test_orchestrate_args.py、
セッション注入は test_session_context_tier.py が担う。
"""

from __future__ import annotations

import unittest

from hve.__main__ import _build_config, _build_parser
from hve.gui.orchestrate_args import OrchestrateArgs


class TestContextTierCli(unittest.TestCase):
    def test_long_context_transfers_to_config(self) -> None:
        args = _build_parser().parse_args(
            ["orchestrate", "--workflow", "akm", "--context-tier", "long_context"]
        )
        cfg = _build_config(args)
        self.assertEqual(cfg.context_tier, "long_context")

    def test_default_value_transfers_to_config(self) -> None:
        args = _build_parser().parse_args(
            ["orchestrate", "--workflow", "akm", "--context-tier", "default"]
        )
        cfg = _build_config(args)
        self.assertEqual(cfg.context_tier, "default")

    def test_omitted_is_none(self) -> None:
        args = _build_parser().parse_args(["orchestrate", "--workflow", "akm"])
        cfg = _build_config(args)
        self.assertIsNone(cfg.context_tier)

    def test_invalid_value_rejected(self) -> None:
        """choices 検証で不正値は argparse が SystemExit する。"""
        with self.assertRaises(SystemExit):
            _build_parser().parse_args(
                ["orchestrate", "--workflow", "akm", "--context-tier", "huge"]
            )

    def test_gui_default_round_trips_to_long_context(self) -> None:
        """GUI 既定（long_context）が to_argv → CLI パース → cfg まで往復する。"""
        argv = OrchestrateArgs(workflow="akm").to_argv()
        args = _build_parser().parse_args(argv)
        cfg = _build_config(args)
        self.assertEqual(cfg.context_tier, "long_context")


if __name__ == "__main__":
    unittest.main()
