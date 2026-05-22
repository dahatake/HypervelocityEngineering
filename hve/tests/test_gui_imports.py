"""test_gui_imports.py — hve.gui パッケージのインポートテストと
`OrchestrateArgs` / workflow_select の純粋ユニットテスト。

PySide6 がインストールされているかどうかにかかわらず、
hve.gui.__init__.run_gui() が安全に呼び出せることを確認する。

OrchestrateArgs / doc_convert / page_workflow_select._load_workflow_choices()
は QApplication 不要なので純粋ユニットテストとして実行可能。
"""

from __future__ import annotations

import sys
import unittest


class TestGuiPackageImport(unittest.TestCase):
    """hve.gui パッケージ自体がインポート可能であることを確認する。"""

    def test_gui_init_importable(self) -> None:
        """hve.gui はインポートできる（PySide6 有無を問わず）。"""
        import hve.gui  # noqa: F401

    def test_run_gui_callable(self) -> None:
        """run_gui は呼び出し可能なオブジェクトとして公開されている。"""
        from hve.gui import run_gui

        self.assertTrue(callable(run_gui))


class TestGuiModulesImport(unittest.TestCase):
    """PySide6 がある環境では各 GUI サブモジュールが全てインポート可能。"""

    _pyside6_available: bool

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import PySide6  # noqa: F401

            cls._pyside6_available = True
        except ImportError:
            cls._pyside6_available = False

    def _skip_if_no_pyside6(self) -> None:
        if not self._pyside6_available:
            self.skipTest("PySide6 not installed")

    def test_copy_button_importable(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.copy_button import CopyButton  # noqa: F401

    def test_state_bridge_importable(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.state_bridge import SubprocessReader, launch_orchestrator  # noqa: F401

    def test_header_bar_importable(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.header_bar import HeaderBar, STEP_LABELS  # noqa: F401

    def test_page_workflow_select_importable(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.page_workflow_select import (  # noqa: F401
            WorkflowSelectPage,
            _load_workflow_choices,
        )

    def test_page_options_importable(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.page_options import OptionsPage, TriStateCombo  # noqa: F401

    def test_page_options_ard_importable(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.page_options_ard import (  # noqa: F401
            AttachmentPane,
            choose_origin_file,
            ORIGIN_OUTPUT_NAME,
            ATTACHED_SUBDIR,
        )

    def test_page_workbench_importable(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.page_workbench import WorkbenchPage  # noqa: F401

    def test_main_window_importable(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.main_window import MainWindow  # noqa: F401

    def test_app_importable(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.app import run_app  # noqa: F401


class TestOrchestrateArgs(unittest.TestCase):
    """OrchestrateArgs の純粋ユニットテスト（QApplication 不要）。

    PySide6 にも依存しないため、PySide6 未インストール環境でも実行可能。
    """

    def test_minimal_argv(self) -> None:
        """workflow のみ指定した最小構成。"""
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(workflow="akm")
        argv = a.to_argv()
        self.assertEqual(argv[0], "orchestrate")
        self.assertIn("--workflow", argv)
        self.assertIn("akm", argv)
        # GUI モードでは workbench=off が必ず付く
        self.assertIn("--workbench", argv)
        self.assertIn("off", argv)

    def test_workbench_off_always_injected(self) -> None:
        """GUI モードでは常に --workbench off が末尾に注入される（設計書 §8.3）。"""
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(workflow="ard")
        argv = a.to_argv()
        self.assertEqual(argv[-2:], ["--workbench", "off"])

    def test_workflow_empty_raises(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(workflow="")
        with self.assertRaises(ValueError):
            a.to_argv()

    def test_basic_flags(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(
            workflow="ard",
            dry_run=True,
            auto_qa=True,
            quiet=True,
            self_improve=True,
        )
        argv = a.to_argv()
        self.assertIn("--dry-run", argv)
        self.assertIn("--auto-qa", argv)
        self.assertIn("--quiet", argv)
        self.assertIn("--self-improve", argv)

    def test_workiq_options(self) -> None:
        """Work IQ オプション 11 個の argv 生成。"""
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(
            workflow="akm",
            workiq=True,
            workiq_akm_review=True,
            workiq_akm_ingest=False,
            workiq_dxx="D01,D04",
            workiq_draft=True,
            workiq_draft_output_dir="qa",
            workiq_tenant_id="tenant-id-123",
            workiq_prompt_qa="custom qa prompt",
            workiq_prompt_km="custom km prompt",
            workiq_prompt_review="custom review prompt",
            workiq_per_question_timeout=1800.0,
            workiq_request_timeout=600.0,
        )
        argv = a.to_argv()
        self.assertIn("--workiq", argv)
        self.assertIn("--workiq-akm-review", argv)
        self.assertIn("--no-workiq-akm-ingest", argv)
        self.assertIn("--workiq-dxx", argv)
        self.assertIn("D01,D04", argv)
        self.assertIn("--workiq-draft", argv)
        self.assertIn("--workiq-tenant-id", argv)
        self.assertIn("tenant-id-123", argv)
        self.assertIn("--workiq-per-question-timeout", argv)
        self.assertIn("1800.0", argv)
        self.assertIn("--workiq-request-timeout", argv)
        self.assertIn("600.0", argv)

    def test_tristate_combobox_value_inherit(self) -> None:
        """TriState が None の場合は引数に含まれない（継承）。"""
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(workflow="akm", workiq_akm_review=None)
        argv = a.to_argv()
        self.assertNotIn("--workiq-akm-review", argv)
        self.assertNotIn("--no-workiq-akm-review", argv)

    def test_tristate_combobox_value_false(self) -> None:
        """TriState が False の場合は --no-* フラグが付く。"""
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(workflow="akm", banner=False)
        argv = a.to_argv()
        self.assertIn("--no-banner", argv)
        self.assertNotIn("--banner", argv)

    def test_ard_options(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(
            workflow="ard",
            company_name="ACME Corp",
            target_business="docs/attached/business-requirement-input.md",
            survey_period_years=10,
            target_region="日本",
            attached_docs="docs/attached/a.md,docs/attached/b.md",
        )
        argv = a.to_argv()
        self.assertIn("--company-name", argv)
        self.assertIn("ACME Corp", argv)
        self.assertIn("--target-business", argv)
        self.assertIn("--survey-period-years", argv)
        self.assertIn("10", argv)
        self.assertIn("--attached-docs", argv)

    def test_to_command_line_starts_with_python(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(workflow="akm")
        cmd = a.to_command_line()
        self.assertTrue(cmd.startswith("python -m hve "))
        self.assertIn("orchestrate", cmd)

    def test_to_command_line_quotes_spaces(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(workflow="ard", company_name="Some Company Inc.")
        cmd = a.to_command_line()
        self.assertIn('"Some Company Inc."', cmd)

    def test_to_summary_contains_workflow(self) -> None:
        from hve.gui.orchestrate_args import OrchestrateArgs

        a = OrchestrateArgs(workflow="akm", auto_qa=True)
        text = a.to_summary_text()
        self.assertIn("akm", text)
        self.assertIn("python -m hve", text)


class TestWorkflowChoicesFromRegistry(unittest.TestCase):
    """page_workflow_select._load_workflow_choices() が workflow_registry の実データを返す。

    PySide6 が無くてもインポート可能（page_workflow_select.py は PySide6 を import するが、
    本テストは PySide6 が利用可能な場合のみ実行する）。
    """

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import PySide6  # noqa: F401

            cls._pyside6_available = True
        except ImportError:
            cls._pyside6_available = False

    def _skip_if_no_pyside6(self) -> None:
        if not self._pyside6_available:
            self.skipTest("PySide6 not installed")

    def test_returns_nonempty_list(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.page_workflow_select import _load_workflow_choices

        choices = _load_workflow_choices()
        self.assertIsInstance(choices, list)
        self.assertGreater(len(choices), 0)

    def test_each_choice_is_two_tuple(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.page_workflow_select import _load_workflow_choices

        for item in _load_workflow_choices():
            self.assertEqual(len(item), 2, f"Expected (id, name), got: {item!r}")

    def test_contains_known_workflow_ids(self) -> None:
        self._skip_if_no_pyside6()
        from hve.gui.page_workflow_select import _load_workflow_choices

        ids = {item[0] for item in _load_workflow_choices()}
        for expected in ("akm", "aqod", "ard"):
            self.assertIn(expected, ids, f"Expected workflow id {expected!r} in registry")

    def test_workflow_names_match_registry(self) -> None:
        """`name` フィールドが実 workflow_registry の値と一致する。

        敵対的レビュー No.1 (Critical) の検証: ワークフロー名が捏造されていないこと。
        """
        self._skip_if_no_pyside6()
        from hve.gui.page_workflow_select import _load_workflow_choices

        names = dict(_load_workflow_choices())
        # workflow_registry.py の実 name フィールドと一致するべき
        # （フォールバック時もこの値を使う）
        expected_pairs = {
            "aas": "Architecture Design",
            "aad-web": "Web App Design",
            "asdw-web": "Web App Dev & Deploy",
            "ard": "Auto Requirement Definition",
        }
        for wf_id, expected_name in expected_pairs.items():
            self.assertEqual(
                names.get(wf_id),
                expected_name,
                f"workflow {wf_id!r} should be named {expected_name!r}, got {names.get(wf_id)!r}",
            )


if __name__ == "__main__":
    unittest.main()
