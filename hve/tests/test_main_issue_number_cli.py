"""tests/test_main_issue_number_cli.py — FR-GUI-25 の `--issue-number` CLI 契約。

`test_main_entrypoints.py` へ同居させない理由（実測）:
`test_main_entrypoints.py` の `TestMainDispatch` は `builtins.__import__` を patch する。
同一プロセスで `test_phase6_option_parity.py` と一緒に実行すると、その patch 下で
`yaml` が初回 import され partially initialized module が `sys.modules` へ残り、
parity 側が 22 件失敗する。これは本変更以前から存在する組み合わせ依存の不具合で、
`test_main_entrypoints.py` + `test_main_ard.py` + `test_phase6_option_parity.py`
（いずれも既存ファイル）でも同一の 22 件が失敗する。
本テストを同居させると 2 ファイルだけの組み合わせでも再現するようになるため分離する。
"""

from __future__ import annotations

import importlib.util as _ilu
import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

# test_main_ard.py と同じ importlib パターンで __main__.py を直接ロードする
# (__main__ は Python ランナーと名前が衝突するため)。`__main__.py` の絶対 import
# フォールバックが解決できるよう `hve/` を `sys.path` へ入れる。
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_issue_number", os.path.abspath(_main_path))
assert _spec is not None and _spec.loader is not None
hve_main = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(hve_main)


class TestIssueNumberArg(unittest.TestCase):
    """FR-GUI-25: `--issue-number` のパースと SDKConfig への伝達。"""

    def _parse(self, extra):
        parser = hve_main._build_parser()
        return parser.parse_args(["orchestrate", "--workflow", "aad-web", *extra])

    def test_default_is_none(self) -> None:
        self.assertIsNone(self._parse([]).issue_number)

    def test_parses_integer(self) -> None:
        self.assertEqual(self._parse(["--issue-number", "1234"]).issue_number, 1234)

    def test_rejects_non_integer(self) -> None:
        with self.assertRaises(SystemExit):
            self._parse(["--issue-number", "abc"])

    def test_build_config_propagates_issue_number(self) -> None:
        args = self._parse(["--issue-number", "77", "--create-issues"])
        cfg = hve_main._build_config(args)
        self.assertEqual(cfg.issue_number, 77)

    def test_build_config_default_is_none(self) -> None:
        cfg = hve_main._build_config(self._parse([]))
        self.assertIsNone(cfg.issue_number)

    def test_issue_number_without_create_flags_warns_and_is_ignored(self) -> None:
        args = self._parse(["--issue-number", "77"])
        stderr = io.StringIO()

        with mock.patch.object(
            hve_main, "_run_startup_configuration_preflight", return_value=False
        ), redirect_stderr(stderr):
            self.assertEqual(hve_main._cmd_orchestrate(args), 1)

        warning = stderr.getvalue()
        self.assertIn("--issue-number", warning)
        self.assertIn("--create-issues", warning)
        self.assertIn("--create-pr", warning)
        self.assertIn("無視", warning)

    def test_create_pr_with_issue_number_is_valid_without_warning(self) -> None:
        args = self._parse(["--create-pr", "--issue-number", "77"])
        stderr = io.StringIO()

        with mock.patch.object(
            hve_main, "_run_startup_configuration_preflight", return_value=False
        ), redirect_stderr(stderr):
            self.assertEqual(hve_main._cmd_orchestrate(args), 1)

        warning = stderr.getvalue()
        self.assertNotIn("--issue-number は無視", warning)


if __name__ == "__main__":
    unittest.main()
