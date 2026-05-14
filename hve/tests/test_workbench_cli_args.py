"""Phase 5: Workbench CLI フラグのパーサ + SDKConfig 反映テスト。"""
from __future__ import annotations

import unittest

from hve.__main__ import _build_parser as build_parser
from hve.config import SDKConfig


def _parse_orch(extra: list[str]):
    parser = build_parser()
    base = ["orchestrate", "--workflow", "aqod"] + extra
    return parser.parse_args(base)


class TestWorkbenchCLIArgs(unittest.TestCase):
    def test_default_workbench_is_auto(self):
        args = _parse_orch([])
        self.assertEqual(args.workbench, "auto")
        self.assertEqual(args.workbench_body_lines, 20)
        self.assertEqual(args.workbench_history, 10000)
        self.assertTrue(args.workbench_flush_on_exit)

    def test_workbench_off(self):
        args = _parse_orch(["--workbench", "off"])
        self.assertEqual(args.workbench, "off")

    def test_workbench_body_lines_explicit(self):
        args = _parse_orch(["--workbench-body-lines", "15"])
        self.assertEqual(args.workbench_body_lines, 15)

    def test_workbench_body_lines_max_20(self):
        args = _parse_orch(["--workbench-body-lines", "20"])
        self.assertEqual(args.workbench_body_lines, 20)

    def test_no_flush_on_exit(self):
        args = _parse_orch(["--no-workbench-flush-on-exit"])
        self.assertFalse(args.workbench_flush_on_exit)


class TestSDKConfigPropagation(unittest.TestCase):
    def _apply(self, extra: list[str], env: dict | None = None) -> SDKConfig:
        """args→cfg 適用ロジックを直接実行（_main 全体ではなくコピーで再現）。"""
        args = _parse_orch(extra)
        cfg = SDKConfig()
        # __main__.py の該当部抜粋を再現（テスト目的）
        _wb_mode = getattr(args, "workbench", "auto")
        cfg.no_workbench = (_wb_mode == "off")
        _raw = int(getattr(args, "workbench_body_lines", 20) or 20)
        env_v = (env or {}).get("HVE_WORKBENCH_BODY_LINES", "").strip()
        if env_v and _raw == 20:
            try:
                _raw = int(env_v)
            except ValueError:
                pass
        _clamped = max(10, min(20, _raw))
        cfg.workbench_body_lines = _clamped
        cfg.workbench_history = int(getattr(args, "workbench_history", 10000) or 10000)
        cfg.workbench_flush_on_exit = bool(getattr(args, "workbench_flush_on_exit", True))
        return cfg

    def test_off_sets_no_workbench(self):
        cfg = self._apply(["--workbench", "off"])
        self.assertTrue(cfg.no_workbench)

    def test_clamp_low(self):
        cfg = self._apply(["--workbench-body-lines", "5"])
        self.assertEqual(cfg.workbench_body_lines, 10)

    def test_clamp_high(self):
        cfg = self._apply(["--workbench-body-lines", "99"])
        self.assertEqual(cfg.workbench_body_lines, 20)

    def test_default_is_20(self):
        cfg = self._apply([])
        self.assertEqual(cfg.workbench_body_lines, 20)

    def test_env_var_overrides_default(self):
        cfg = self._apply([], env={"HVE_WORKBENCH_BODY_LINES": "13"})
        self.assertEqual(cfg.workbench_body_lines, 13)

    def test_cli_takes_precedence_over_env(self):
        cfg = self._apply(["--workbench-body-lines", "15"], env={"HVE_WORKBENCH_BODY_LINES": "11"})
        self.assertEqual(cfg.workbench_body_lines, 15)

    def test_env_var_clamped(self):
        cfg = self._apply([], env={"HVE_WORKBENCH_BODY_LINES": "100"})
        self.assertEqual(cfg.workbench_body_lines, 20)

    def test_history_propagated(self):
        cfg = self._apply(["--workbench-history", "500"])
        self.assertEqual(cfg.workbench_history, 500)


if __name__ == "__main__":
    unittest.main()
