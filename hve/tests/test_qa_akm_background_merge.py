"""test_qa_akm_background_merge.py — FR-QA-05 の RED テスト。

QA 起点 AKM（FR-QA-03）のバックグラウンド起動可否を、利用者が明示選択できる
設定 `qa_akm_background_merge`（既定無効）で制御することを検証する。

実装前は `SDKConfig.qa_akm_background_merge` と `--qa-akm-background-merge` が
存在しないため全件 RED となる。
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # noqa: E402

_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_qa_akm_merge", os.path.abspath(_main_path))
_main_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)


def _parse(argv):
    return _main_mod._build_parser().parse_args(argv)


class TestQaAkmBackgroundMergeConfigDefaults(unittest.TestCase):
    """既定は無効で、環境変数経路を新設しない。"""

    def test_default_is_disabled(self) -> None:
        self.assertFalse(SDKConfig().qa_akm_background_merge)

    def test_from_env_does_not_read_a_new_variable(self) -> None:
        backup = os.environ.copy()
        try:
            os.environ["QA_AKM_BACKGROUND_MERGE"] = "true"
            self.assertFalse(SDKConfig.from_env().qa_akm_background_merge)
        finally:
            os.environ.clear()
            os.environ.update(backup)


class TestShouldEnableQaAkmDispatchGate(unittest.TestCase):
    """判定は `_should_enable_qa_akm_dispatch` の 1 箇所だけで行う。"""

    def test_disabled_setting_suppresses_dispatch(self) -> None:
        from orchestrator import _should_enable_qa_akm_dispatch

        self.assertFalse(_should_enable_qa_akm_dispatch(
            auto_qa=True, workflow_id="aas", dry_run=False,
            qa_akm_background_merge=False,
        ))

    def test_enabled_setting_allows_dispatch(self) -> None:
        from orchestrator import _should_enable_qa_akm_dispatch

        self.assertTrue(_should_enable_qa_akm_dispatch(
            auto_qa=True, workflow_id="aas", dry_run=False,
            qa_akm_background_merge=True,
        ))

    def test_existing_conditions_still_apply(self) -> None:
        from orchestrator import _should_enable_qa_akm_dispatch

        for kwargs in (
            {"auto_qa": False, "workflow_id": "aas", "dry_run": False},
            {"auto_qa": True, "workflow_id": "akm", "dry_run": False},
            {"auto_qa": True, "workflow_id": "aas", "dry_run": True},
        ):
            with self.subTest(**kwargs):
                self.assertFalse(_should_enable_qa_akm_dispatch(
                    qa_akm_background_merge=True, **kwargs,
                ))

    def test_run_workflow_passes_the_setting_to_the_gate(self) -> None:
        """`run_workflow` が config の値を判定へ渡していること（配線の固定）。"""
        import inspect

        import orchestrator

        source = inspect.getsource(orchestrator._run_workflow_body)
        self.assertIn("qa_akm_background_merge=config.qa_akm_background_merge", source)


class TestQaAkmBackgroundMergeCliArgs(unittest.TestCase):
    """CLI フラグのパースと SDKConfig への反映。"""

    def test_flag_defaults_to_false(self) -> None:
        args = _parse(["orchestrate", "-w", "aas"])
        self.assertFalse(args.qa_akm_background_merge)

    def test_flag_can_be_enabled(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--qa-akm-background-merge"])
        self.assertTrue(args.qa_akm_background_merge)

    def test_flag_reaches_config(self) -> None:
        config = _main_mod._build_config(
            _parse(["orchestrate", "-w", "aas", "--auto-qa", "--qa-akm-background-merge"])
        )
        self.assertTrue(config.qa_akm_background_merge)

    def test_config_stays_false_without_the_flag(self) -> None:
        config = _main_mod._build_config(_parse(["orchestrate", "-w", "aas", "--auto-qa"]))
        self.assertFalse(config.qa_akm_background_merge)


if __name__ == "__main__":
    unittest.main()
