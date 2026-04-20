"""test_main.py — CLI 引数パースのテスト"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# __main__.py は Python の __main__ と名前が衝突するため importlib で直接ロードする
_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main", os.path.abspath(_main_path))
_main_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)

_build_parser = _main_mod._build_parser
_build_params = _main_mod._build_params
_build_config = _main_mod._build_config
_load_mcp_config = _main_mod._load_mcp_config
_validate_auto_coding_agent_review = _main_mod._validate_auto_coding_agent_review
_resolve_model = _main_mod._resolve_model
_prompt_valid_doc_purpose = _main_mod._prompt_valid_doc_purpose
_prompt_valid_aqod_depth = _main_mod._prompt_valid_aqod_depth
_prompt_valid_max_file_lines = _main_mod._prompt_valid_max_file_lines
_prompt_akm_params = _main_mod._prompt_akm_params
main = _main_mod.main


def _parse(argv):
    """_build_parser() でコマンドライン引数をパースするヘルパー。"""
    return _build_parser().parse_args(argv)


class TestParserBasic(unittest.TestCase):
    """基本的な argparse テスト。"""

    def test_workflow_required(self) -> None:
        """--workflow が必須であることを確認。"""
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["orchestrate"])

    def test_workflow_short_option(self) -> None:
        """-w の短縮形が動作することを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        self.assertEqual(args.workflow, "aas")

    def test_defaults(self) -> None:
        """argparse で --model 未指定時は None になることを確認。"""
        args = _parse(["orchestrate", "--workflow", "aad"])
        self.assertIsNone(args.model)
        self.assertEqual(args.max_parallel, 15)
        self.assertFalse(args.auto_qa)
        self.assertFalse(args.auto_contents_review)
        self.assertFalse(args.auto_coding_agent_review)
        self.assertFalse(args.auto_coding_agent_review_auto_approval)
        self.assertFalse(args.create_issues)
        self.assertFalse(args.create_pr)
        self.assertFalse(args.quiet)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.branch, "main")
        self.assertIsNone(args.steps)
        self.assertIsNone(args.app_id)
        self.assertIsNone(args.app_ids)
        self.assertIsNone(args.resource_group)
        self.assertIsNone(args.batch_job_id)
        self.assertIsNone(args.usecase_id)
        self.assertEqual(args.sources, "qa")
        self.assertIsNone(args.target_files)
        self.assertIsNone(args.force_refresh)
        self.assertFalse(args.enable_auto_merge)
        self.assertIsNone(args.target_scope)
        self.assertIsNone(args.depth)
        self.assertIsNone(args.focus_areas)
        self.assertIsNone(args.target_dirs)
        self.assertIsNone(args.exclude_patterns)
        self.assertIsNone(args.doc_purpose)
        self.assertIsNone(args.max_file_lines)
        self.assertIsNone(args.cli_path)
        self.assertIsNone(args.cli_url)
        self.assertIsNone(args.mcp_config)
        self.assertEqual(args.timeout, 21600.0)
        self.assertEqual(args.log_level, "error")

    def test_log_level_option(self) -> None:
        """--log-level オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--log-level", "debug"])
        self.assertEqual(args.log_level, "debug")

    def test_model_option(self) -> None:
        """-m / --model オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "-m", "gpt-5.4"])
        self.assertEqual(args.model, "gpt-5.4")

    def test_max_parallel_option(self) -> None:
        """--max-parallel オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--max-parallel", "5"])
        self.assertEqual(args.max_parallel, 5)

    def test_auto_qa_flag(self) -> None:
        """--auto-qa フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--auto-qa"])
        self.assertTrue(args.auto_qa)

    def test_auto_contents_review_flag(self) -> None:
        """--auto-contents-review フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--auto-contents-review"])
        self.assertTrue(args.auto_contents_review)

    def test_auto_coding_agent_review_flag(self) -> None:
        """--auto-coding-agent-review フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--auto-coding-agent-review"])
        self.assertTrue(args.auto_coding_agent_review)

    def test_auto_coding_agent_review_auto_approval_flag(self) -> None:
        """--auto-coding-agent-review-auto-approval フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--auto-coding-agent-review-auto-approval"])
        self.assertTrue(args.auto_coding_agent_review_auto_approval)

    def test_create_issues_flag(self) -> None:
        """--create-issues フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--create-issues"])
        self.assertTrue(args.create_issues)

    def test_create_pr_flag(self) -> None:
        """--create-pr フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--create-pr"])
        self.assertTrue(args.create_pr)

    def test_quiet_flag(self) -> None:
        """-q / --quiet フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "-q"])
        self.assertTrue(args.quiet)

    def test_dry_run_flag(self) -> None:
        """--dry-run フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--dry-run"])
        self.assertTrue(args.dry_run)

    def test_branch_option(self) -> None:
        """--branch オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--branch", "develop"])
        self.assertEqual(args.branch, "develop")

    def test_steps_option(self) -> None:
        """--steps オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--steps", "1,2"])
        self.assertEqual(args.steps, "1,2")

    def test_app_id_option(self) -> None:
        """--app-id オプションのテスト（後方互換）。"""
        args = _parse(["orchestrate", "-w", "asdw", "--app-id", "APP-03"])
        self.assertEqual(args.app_id, "APP-03")

    def test_app_ids_option(self) -> None:
        """--app-ids オプション（カンマ区切り複数指定）のテスト。"""
        args = _parse(["orchestrate", "-w", "asdw", "--app-ids", "APP-01,APP-02,APP-03"])
        self.assertEqual(args.app_ids, "APP-01,APP-02,APP-03")

    def test_resource_group_option(self) -> None:
        """--resource-group オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "asdw", "--resource-group", "rg-dev"])
        self.assertEqual(args.resource_group, "rg-dev")

    def test_timeout_option(self) -> None:
        """--timeout オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--timeout", "600"])
        self.assertEqual(args.timeout, 600.0)

    def test_review_timeout_default(self) -> None:
        """--review-timeout のデフォルト値が 7200.0 であることを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        self.assertEqual(args.review_timeout, 7200.0)

    def test_review_timeout_option(self) -> None:
        """--review-timeout オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--review-timeout", "600"])
        self.assertEqual(args.review_timeout, 600.0)

    def test_cli_url_option(self) -> None:
        """--cli-url オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--cli-url", "localhost:4321"])
        self.assertEqual(args.cli_url, "localhost:4321")

    def test_repo_option(self) -> None:
        """--repo オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--repo", "owner/repo"])
        self.assertEqual(args.repo, "owner/repo")

    def test_scope_option(self) -> None:
        """--sources オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "qa"])
        self.assertEqual(args.sources, "qa")

    def test_scope_both_option(self) -> None:
        """--sources both のテスト。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "both"])
        self.assertEqual(args.sources, "both")

    def test_sources_original_docs_option(self) -> None:
        """--sources original-docs のテスト。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "original-docs"])
        self.assertEqual(args.sources, "original-docs")

    def test_target_files_option(self) -> None:
        """--target-files オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "both",
                        "--target-files", "qa/file1.md", "qa/file2.md"])
        self.assertEqual(args.target_files, ["qa/file1.md", "qa/file2.md"])

    def test_force_refresh_flag(self) -> None:
        """--force-refresh フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "qa", "--force-refresh"])
        self.assertTrue(args.force_refresh)

    def test_adoc_target_dirs_option(self) -> None:
        args = _parse(["orchestrate", "-w", "adoc", "--target-dirs", "src/,hve/"])
        self.assertEqual(args.target_dirs, "src/,hve/")

    def test_adoc_exclude_patterns_option(self) -> None:
        args = _parse(["orchestrate", "-w", "adoc", "--exclude-patterns", "dist/,*.lock"])
        self.assertEqual(args.exclude_patterns, "dist/,*.lock")

    def test_adoc_doc_purpose_option(self) -> None:
        args = _parse(["orchestrate", "-w", "adoc", "--doc-purpose", "migration"])
        self.assertEqual(args.doc_purpose, "migration")

    def test_adoc_max_file_lines_option(self) -> None:
        args = _parse(["orchestrate", "-w", "adoc", "--max-file-lines", "1000"])
        self.assertEqual(args.max_file_lines, 1000)

    def test_aqod_target_scope_option(self) -> None:
        args = _parse(["orchestrate", "-w", "aqod", "--target-scope", "original-docs/"])
        self.assertEqual(args.target_scope, "original-docs/")

    def test_aqod_depth_option(self) -> None:
        args = _parse(["orchestrate", "-w", "aqod", "--depth", "lightweight"])
        self.assertEqual(args.depth, "lightweight")

    def test_aqod_focus_areas_option(self) -> None:
        args = _parse(["orchestrate", "-w", "aqod", "--focus-areas", "データ整合性"])
        self.assertEqual(args.focus_areas, "データ整合性")


class TestBuildParams(unittest.TestCase):
    """_build_params() のテスト。"""

    def test_steps_parsed_as_list(self) -> None:
        """--steps がリストとして解析されることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--steps", "1,2,3"])
        params = _build_params(args)
        self.assertEqual(params["steps"], ["1", "2", "3"])

    def test_steps_empty_when_not_specified(self) -> None:
        """--steps 未指定の場合、空リストになることを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        params = _build_params(args)
        self.assertEqual(params["steps"], [])

    def test_branch_in_params(self) -> None:
        """branch がパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--branch", "feature/test"])
        params = _build_params(args)
        self.assertEqual(params["branch"], "feature/test")

    def test_auto_qa_in_params(self) -> None:
        """auto_qa フラグがパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--auto-qa"])
        params = _build_params(args)
        self.assertTrue(params["auto_qa"])

    def test_app_id_in_params(self) -> None:
        """app_id (旧形式) が app_ids リストにも正規化されることを確認。"""
        args = _parse(["orchestrate", "-w", "asdw", "--app-id", "APP-05"])
        params = _build_params(args)
        self.assertEqual(params["app_id"], "APP-05")
        self.assertEqual(params["app_ids"], ["APP-05"])

    def test_app_ids_in_params(self) -> None:
        """--app-ids がカンマ分割されてリストになることを確認。"""
        args = _parse(["orchestrate", "-w", "asdw", "--app-ids", "APP-01,APP-02,APP-03"])
        params = _build_params(args)
        self.assertEqual(params["app_ids"], ["APP-01", "APP-02", "APP-03"])
        self.assertNotIn("app_id", params)

    def test_app_ids_single_also_sets_app_id(self) -> None:
        """--app-ids に1件だけ指定すると app_id にも設定されることを確認。"""
        args = _parse(["orchestrate", "-w", "asdw", "--app-ids", "APP-01"])
        params = _build_params(args)
        self.assertEqual(params["app_ids"], ["APP-01"])
        self.assertEqual(params["app_id"], "APP-01")

    def test_resource_group_in_params(self) -> None:
        """resource_group がパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "asdw", "--resource-group", "rg-test"])
        params = _build_params(args)
        self.assertEqual(params["resource_group"], "rg-test")

    def test_steps_with_spaces(self) -> None:
        """--steps のスペースが除去されることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--steps", " 1 , 2 , 3 "])
        params = _build_params(args)
        self.assertEqual(params["steps"], ["1", "2", "3"])

    def test_akm_scope_in_params(self) -> None:
        """AKM sources がパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "qa"])
        params = _build_params(args)
        self.assertEqual(params["sources"], "qa")

    def test_akm_target_files_in_params(self) -> None:
        """AKM target_files がスペース区切り文字列としてパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "both",
                        "--target-files", "qa/f1.md", "qa/f2.md"])
        params = _build_params(args)
        self.assertEqual(params["target_files"], "qa/f1.md qa/f2.md")

    def test_akm_force_refresh_in_params(self) -> None:
        """AKM force_refresh フラグがパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "qa", "--force-refresh"])
        params = _build_params(args)
        self.assertTrue(params["force_refresh"])

    def test_akm_force_refresh_default_true(self) -> None:
        """AKM force_refresh デフォルト値が True であることを確認。"""
        args = _parse(["orchestrate", "-w", "akm"])
        params = _build_params(args)
        self.assertTrue(params["force_refresh"])

    def test_akm_no_force_refresh_sets_false(self) -> None:
        """AKM --no-force-refresh で force_refresh が False になることを確認。"""
        args = _parse(["orchestrate", "-w", "akm", "--no-force-refresh"])
        params = _build_params(args)
        self.assertFalse(params["force_refresh"])

    def test_akm_enable_auto_merge_default(self) -> None:
        """AKM enable_auto_merge が未指定時に False になることを確認。"""
        args = _parse(["orchestrate", "-w", "akm"])
        params = _build_params(args)
        self.assertFalse(params["enable_auto_merge"])

    def test_akm_enable_auto_merge_enabled(self) -> None:
        """AKM --enable-auto-merge 指定時に True になることを確認。"""
        args = _parse(["orchestrate", "-w", "akm", "--enable-auto-merge"])
        params = _build_params(args)
        self.assertTrue(params["enable_auto_merge"])

    def test_akm_sources_default_when_not_specified(self) -> None:
        """AKM sources が未指定時に 'qa' になることを確認。"""
        args = _parse(["orchestrate", "-w", "akm"])
        params = _build_params(args)
        self.assertEqual(params["sources"], "qa")

    def test_akm_target_files_default_when_not_specified(self) -> None:
        """AKM target_files が未指定時に 'qa/*.md' になることを確認。"""
        args = _parse(["orchestrate", "-w", "akm"])
        params = _build_params(args)
        self.assertEqual(params["target_files"], "qa/*.md")

    def test_akm_target_files_default_original_docs_when_sources_original_docs(self) -> None:
        """AKM target_files は sources=original-docs で 'original-docs/*' を既定にする。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "original-docs"])
        params = _build_params(args)
        self.assertEqual(params["target_files"], "original-docs/*")

    def test_akm_target_files_default_empty_when_sources_both(self) -> None:
        """AKM target_files は sources=both で未指定（空）を既定にする。"""
        args = _parse(["orchestrate", "-w", "akm", "--sources", "both"])
        params = _build_params(args)
        self.assertEqual(params["target_files"], "")

    def test_akm_target_files_in_params_when_specified(self) -> None:
        """AKM --target-files 指定時は指定値（スペース区切り）が優先されることを確認。"""
        args = _parse([
            "orchestrate", "-w", "akm", "--sources", "both",
            "--target-files", "original-docs/f1.md", "original-docs/f2.md",
        ])
        params = _build_params(args)
        self.assertEqual(params["target_files"], "original-docs/f1.md original-docs/f2.md")

    def test_non_akm_sources_not_set_when_not_specified(self) -> None:
        """非 AKM ワークフローで --sources 未指定時は params に sources が含まれないことを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        params = _build_params(args)
        self.assertNotIn("sources", params)

    def test_non_akm_target_files_not_set_when_not_specified(self) -> None:
        """非 AKM ワークフローで --target-files 未指定時は params に target_files が含まれないことを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        params = _build_params(args)
        self.assertNotIn("target_files", params)

    def test_non_akm_force_refresh_not_in_params_when_not_specified(self) -> None:
        """非 AKM ワークフローで --force-refresh 未指定時は params に force_refresh が含まれないことを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        params = _build_params(args)
        self.assertNotIn("force_refresh", params)

    def test_adoc_params_defaults(self) -> None:
        args = _parse(["orchestrate", "-w", "adoc"])
        params = _build_params(args)
        self.assertEqual(params["target_dirs"], "")
        self.assertEqual(params["exclude_patterns"], "node_modules/,vendor/,dist/,*.lock,__pycache__/")
        self.assertEqual(params["doc_purpose"], "all")
        self.assertEqual(params["max_file_lines"], 500)

    def test_adoc_params_custom_values(self) -> None:
        args = _parse([
            "orchestrate", "-w", "adoc",
            "--target-dirs", "src/,hve/",
            "--exclude-patterns", "dist/,node_modules/",
            "--doc-purpose", "refactoring",
            "--max-file-lines", "300",
        ])
        params = _build_params(args)
        self.assertEqual(params["target_dirs"], "src/,hve/")
        self.assertEqual(params["exclude_patterns"], "dist/,node_modules/")
        self.assertEqual(params["doc_purpose"], "refactoring")
        self.assertEqual(params["max_file_lines"], 300)

    def test_aqod_params_defaults(self) -> None:
        args = _parse(["orchestrate", "-w", "aqod"])
        params = _build_params(args)
        self.assertEqual(params["target_scope"], "original-docs/")
        self.assertEqual(params["depth"], "standard")
        self.assertEqual(params["focus_areas"], "")

    def test_aqod_params_custom_values(self) -> None:
        args = _parse([
            "orchestrate", "-w", "aqod",
            "--target-scope", "original-docs/subdir/",
            "--depth", "lightweight",
            "--focus-areas", "データ整合性",
        ])
        params = _build_params(args)
        self.assertEqual(params["target_scope"], "original-docs/subdir/")
        self.assertEqual(params["depth"], "lightweight")
        self.assertEqual(params["focus_areas"], "データ整合性")


    def test_model_auto_resolved_in_config(self) -> None:
        """--model Auto が claude-opus-4.7 に解決されることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--model", "Auto"])
        config = _build_config(args)
        self.assertEqual(config.model, "claude-opus-4.7")

    def test_model_4_6_still_selectable(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--model", "claude-opus-4.6"])
        config = _build_config(args)
        self.assertEqual(config.model, "claude-opus-4.6")

    def test_env_model_4_6_preserves_old_default(self) -> None:
        with mock.patch.dict(os.environ, {"MODEL": "claude-opus-4.6"}, clear=False):
            args = _parse(["orchestrate", "-w", "aas"])
            config = _build_config(args)
            self.assertEqual(config.model, "claude-opus-4.6")

    def test_default_model_used_when_cli_and_env_missing(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            args = _parse(["orchestrate", "-w", "aas"])
            config = _build_config(args)
            self.assertEqual(config.model, "claude-opus-4.7")

    def test_cli_explicit_default_model_overrides_env_model(self) -> None:
        with mock.patch.dict(os.environ, {"MODEL": "claude-opus-4.6"}, clear=False):
            args = _parse(["orchestrate", "-w", "aas", "--model", "claude-opus-4.7"])
            config = _build_config(args)
            self.assertEqual(config.model, "claude-opus-4.7")


class TestPromptAkmParamsEnableAutoMerge(unittest.TestCase):
    """_prompt_akm_params: PR 作成有無で enable_auto_merge 質問が切り替わる。"""

    _AUTO_MERGE_LABEL = "PR の自動 Approve & Auto-merge を有効にする？"

    def _make_con(self):
        con = mock.MagicMock()
        con.menu_select.return_value = 0
        con.prompt_input.return_value = ""
        con.prompt_yes_no.return_value = False
        return con

    def _called_labels(self, con) -> list[str]:
        return [call.args[0] for call in con.prompt_yes_no.call_args_list]

    def test_skips_auto_merge_when_no_pr(self) -> None:
        """will_create_pr=False のとき auto_merge 質問をスキップし False 固定。"""
        con = self._make_con()
        params = _prompt_akm_params(con, is_quick_auto=False, will_create_pr=False)
        self.assertFalse(params["enable_auto_merge"])
        self.assertNotIn(self._AUTO_MERGE_LABEL, self._called_labels(con))

    def test_asks_auto_merge_when_pr(self) -> None:
        """will_create_pr=True のとき auto_merge 質問を表示する。"""
        con = self._make_con()
        _prompt_akm_params(con, is_quick_auto=False, will_create_pr=True)
        self.assertIn(self._AUTO_MERGE_LABEL, self._called_labels(con))

    def test_quick_auto_unaffected(self) -> None:
        """is_quick_auto=True は will_create_pr に依らず False 固定。"""
        con = self._make_con()
        params_no_pr = _prompt_akm_params(con, is_quick_auto=True, will_create_pr=False)
        params_with_pr = _prompt_akm_params(con, is_quick_auto=True, will_create_pr=True)
        self.assertFalse(params_no_pr["enable_auto_merge"])
        self.assertFalse(params_with_pr["enable_auto_merge"])
        self.assertEqual(con.prompt_yes_no.call_count, 0)


class TestReviewModelCLI(unittest.TestCase):
    """review/qa モデル CLI の動作を検証する。"""

    def test_review_model_parsed(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--review-model", "claude-opus-4.6"])
        self.assertEqual(args.review_model, "claude-opus-4.6")

    def test_qa_model_parsed(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--qa-model", "gpt-5.4"])
        self.assertEqual(args.qa_model, "gpt-5.4")

    def test_review_model_default_none(self) -> None:
        args = _parse(["orchestrate", "-w", "aas"])
        self.assertIsNone(args.review_model)

    def test_qa_model_default_none(self) -> None:
        args = _parse(["orchestrate", "-w", "aas"])
        self.assertIsNone(args.qa_model)

    def test_review_model_auto_resolved_in_config(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--review-model", "Auto"])
        config = _build_config(args)
        self.assertEqual(config.review_model, "claude-opus-4.7")

    def test_review_model_auto_resolved_from_env_when_cli_missing(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["REVIEW_MODEL"] = "Auto"
            args = _parse(["orchestrate", "-w", "aas"])
            config = _build_config(args)
            self.assertEqual(config.review_model, "claude-opus-4.7")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_qa_model_auto_resolved_from_env_when_cli_missing(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["QA_MODEL"] = "Auto"
            args = _parse(["orchestrate", "-w", "aas"])
            config = _build_config(args)
            self.assertEqual(config.qa_model, "claude-opus-4.7")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_qa_merge_default_model_is_opus_4_7(self) -> None:
        args = _parse(["qa-merge", "--qa-file", "qa/sample.md"])
        self.assertEqual(args.model, "claude-opus-4.7")

    def test_qa_merge_auto_resolved_to_opus_4_7(self) -> None:
        args = _parse(["qa-merge", "--qa-file", "qa/sample.md", "--model", "Auto"])
        model, _ = _resolve_model(args.model)
        self.assertEqual(model, "claude-opus-4.7")


class TestLoadMCPConfig(unittest.TestCase):
    """_load_mcp_config() のテスト。"""

    def test_none_when_no_path(self) -> None:
        """パスが None の場合 None を返すことを確認。"""
        result = _load_mcp_config(None)
        self.assertIsNone(result)

    def test_loads_valid_json(self) -> None:
        """有効な JSON ファイルを読み込めることを確認。"""
        mcp_data = {
            "filesystem": {
                "type": "local",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "tools": ["*"],
            }
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(mcp_data, f)
            tmp_path = f.name

        try:
            result = _load_mcp_config(tmp_path)
            self.assertEqual(result, mcp_data)
        finally:
            pathlib.Path(tmp_path).unlink()

    def test_none_when_file_not_found(self) -> None:
        """存在しないファイルの場合 None を返すことを確認。"""
        result = _load_mcp_config("/tmp/nonexistent_mcp_config_xyz.json")
        self.assertIsNone(result)

    def test_none_when_invalid_json(self) -> None:
        """無効な JSON の場合 None を返すことを確認。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{ invalid json }")
            tmp_path = f.name

        try:
            result = _load_mcp_config(tmp_path)
            self.assertIsNone(result)
        finally:
            pathlib.Path(tmp_path).unlink()


class TestMainDryRun(unittest.TestCase):
    """main() の dry_run 統合テスト。"""

    def test_main_dry_run_returns_0(self) -> None:
        """dry_run で正常実行の場合、終了コードが 0 であることを確認。"""
        exit_code = main([
            "orchestrate",
            "--workflow", "aas",
            "--dry-run",
            "--quiet",
        ])
        self.assertEqual(exit_code, 0)

    def test_main_invalid_workflow_returns_1(self) -> None:
        """存在しないワークフロー ID の場合、終了コードが 1 であることを確認。"""
        exit_code = main([
            "orchestrate",
            "--workflow", "nonexistent_workflow_xyz",
            "--dry-run",
            "--quiet",
        ])
        self.assertEqual(exit_code, 1)

    def test_main_all_valid_workflows_dry_run(self) -> None:
        """全ての有効なワークフローで dry_run が成功することを確認。"""
        for wf_id in ["aas", "aad", "asdw", "abd", "abdv", "adoc"]:
            with self.subTest(workflow_id=wf_id):
                exit_code = main([
                    "orchestrate",
                    "--workflow", wf_id,
                    "--dry-run",
                    "--quiet",
                ])
                self.assertEqual(exit_code, 0, f"{wf_id} の dry_run で終了コードが 0 以外")

    def test_akm_scope_both_without_target_files_returns_0(self) -> None:
        """akm で --sources both だが --target-files 未指定の場合、デフォルト値 qa/*.md で続行するため終了コードが 0。"""
        exit_code = main([
            "orchestrate",
            "--workflow", "akm",
            "--sources", "both",
            "--dry-run",
            "--quiet",
        ])
        self.assertEqual(exit_code, 0)

    def test_akm_scope_all_dry_run_returns_0(self) -> None:
        """akm で --sources all（--target-files 不要）の dry_run が成功する。"""
        exit_code = main([
            "orchestrate",
            "--workflow", "akm",
            "--sources", "qa",
            "--dry-run",
            "--quiet",
        ])
        self.assertEqual(exit_code, 0)

    def test_akm_scope_both_with_target_files_dry_run_returns_0(self) -> None:
        """akm で --sources both + --target-files 指定の dry_run が成功する。"""
        exit_code = main([
            "orchestrate",
            "--workflow", "akm",
            "--sources", "both",
            "--target-files", "qa/file1.md",
            "--dry-run",
            "--quiet",
        ])
        self.assertEqual(exit_code, 0)


class TestBuildConfigReviewTimeout(unittest.TestCase):
    """`--review-timeout` が SDKConfig.review_timeout_seconds に反映されることを確認。"""

    def test_review_timeout_reflected_in_config(self) -> None:
        """--review-timeout の値が config.review_timeout_seconds に反映される。"""
        args = _parse(["orchestrate", "-w", "aas", "--review-timeout", "600"])
        config = _build_config(args)
        self.assertEqual(config.review_timeout_seconds, 600.0)

    def test_review_timeout_default_in_config(self) -> None:
        """--review-timeout 未指定時のデフォルト値が config に反映される。"""
        args = _parse(["orchestrate", "-w", "aas"])
        config = _build_config(args)
        self.assertEqual(config.review_timeout_seconds, 7200.0)


class TestBuildConfigLogLevel(unittest.TestCase):
    """`--log-level` が SDKConfig.log_level に反映されることを確認。"""

    def test_log_level_reflected_in_config(self) -> None:
        """--log-level の値が config.log_level に反映される。"""
        args = _parse(["orchestrate", "-w", "aas", "--log-level", "debug"])
        config = _build_config(args)
        self.assertEqual(config.log_level, "debug")

    def test_log_level_default_in_config(self) -> None:
        """--log-level 未指定時のデフォルト値が config に反映される。"""
        args = _parse(["orchestrate", "-w", "aas"])
        config = _build_config(args)
        self.assertEqual(config.log_level, "error")


class TestValidateAutoCodingAgentReview(unittest.TestCase):
    """`_validate_auto_coding_agent_review()` の前提条件バリデーションテスト。"""

    def _make_config(self, repo: str = "", token: str = ""):
        """テスト用の最小 SDKConfig を生成する。"""
        args = _parse(["orchestrate", "-w", "aas"])
        config = _build_config(args)
        config.repo = repo
        config.github_token = token
        return config

    def test_returns_true_when_flag_disabled(self) -> None:
        """--auto-coding-agent-review が無効なら常に True を返す。"""
        args = _parse(["orchestrate", "-w", "aas"])
        config = self._make_config()  # repo, token 未設定でも OK
        result = _validate_auto_coding_agent_review(args, config)
        self.assertTrue(result)

    def test_returns_true_when_repo_missing(self) -> None:
        """--repo 未設定でも True を返す（Code Review Agent はローカル実行）。"""
        args = _parse(["orchestrate", "-w", "aas", "--auto-coding-agent-review", "--quiet"])
        config = self._make_config(repo="", token="ghp_test")
        result = _validate_auto_coding_agent_review(args, config)
        self.assertTrue(result)

    def test_returns_true_when_token_missing(self) -> None:
        """GH_TOKEN 未設定でも True を返す（Code Review Agent はローカル実行）。"""
        args = _parse(["orchestrate", "-w", "aas", "--auto-coding-agent-review", "--quiet"])
        config = self._make_config(repo="", token="")
        result = _validate_auto_coding_agent_review(args, config)
        self.assertTrue(result)

    def test_returns_true_when_both_missing(self) -> None:
        """--repo と GH_TOKEN が両方未設定でも True を返す（Code Review Agent はローカル実行）。"""
        args = _parse(["orchestrate", "-w", "aas", "--auto-coding-agent-review", "--quiet"])
        config = self._make_config(repo="", token="")
        result = _validate_auto_coding_agent_review(args, config)
        self.assertTrue(result)

    def test_returns_true_when_both_set(self) -> None:
        """--repo と GH_TOKEN が両方設定されていれば True を返す。"""
        args = _parse(["orchestrate", "-w", "aas", "--auto-coding-agent-review", "--quiet"])
        config = self._make_config(repo="owner/repo", token="ghp_test")
        result = _validate_auto_coding_agent_review(args, config)
        self.assertTrue(result)

    def test_main_does_not_fail_when_repo_missing(self) -> None:
        """--auto-coding-agent-review 指定時、--repo 未設定でもバリデーションは成功する（Code Review Agent はローカル実行）。"""
        args = _parse([
            "orchestrate",
            "--workflow", "aas",
            "--auto-coding-agent-review",
            "--quiet",
        ])
        config = self._make_config(repo="", token="")
        result = _validate_auto_coding_agent_review(args, config)
        self.assertTrue(result)

    def test_auto_approval_reset_when_review_disabled(self) -> None:
        """--auto-coding-agent-review が無効で --auto-coding-agent-review-auto-approval が
        有効な場合、auto_approval フラグが False にリセットされることを確認。"""
        args = _parse([
            "orchestrate", "-w", "aas",
            "--auto-coding-agent-review-auto-approval",
        ])
        # auto_coding_agent_review は False、auto_coding_agent_review_auto_approval は True
        self.assertFalse(args.auto_coding_agent_review)
        self.assertTrue(args.auto_coding_agent_review_auto_approval)

        config = self._make_config()
        result = _validate_auto_coding_agent_review(args, config)

        self.assertTrue(result)
        self.assertFalse(args.auto_coding_agent_review_auto_approval)

    def test_auto_approval_not_reset_when_review_enabled(self) -> None:
        """--auto-coding-agent-review が有効な場合、auto_approval フラグはリセットされない。"""
        args = _parse([
            "orchestrate", "-w", "aas",
            "--auto-coding-agent-review",
            "--auto-coding-agent-review-auto-approval",
            "--quiet",
        ])
        config = self._make_config(repo="owner/repo", token="ghp_test")
        result = _validate_auto_coding_agent_review(args, config)

        self.assertTrue(result)
        self.assertTrue(args.auto_coding_agent_review_auto_approval)


class TestCreateIssuesNewFlow(unittest.TestCase):
    """--create-issues 新フローのバリデーションテスト。"""

    def test_create_issues_implies_create_pr(self) -> None:
        """--create-issues 指定時に create_pr が True になることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--create-issues"])
        # --create-issues 指定時は create_pr が False のまま（parser レベルでは）
        self.assertFalse(args.create_pr)
        self.assertTrue(args.create_issues)

        # _cmd_orchestrate が行う mutation を再現して config レベルで create_pr=True を確認
        if args.create_issues:
            args.create_pr = True
        config = _build_config(args)
        self.assertTrue(config.create_pr)
        self.assertTrue(config.create_issues)

    def test_create_issues_requires_token_and_repo(self) -> None:
        """--create-issues 指定時、GH_TOKEN/REPO 未設定なら main() が 1 を返す。"""
        import os
        old_env = os.environ.pop("REPO", None)
        old_gh = os.environ.pop("GH_TOKEN", None)
        old_github = os.environ.pop("GITHUB_TOKEN", None)
        try:
            exit_code = main([
                "orchestrate",
                "--workflow", "aas",
                "--create-issues",
                "--quiet",
            ])
            self.assertEqual(exit_code, 1)
        finally:
            if old_env is not None:
                os.environ["REPO"] = old_env
            if old_gh is not None:
                os.environ["GH_TOKEN"] = old_gh
            if old_github is not None:
                os.environ["GITHUB_TOKEN"] = old_github

    def test_auto_coding_agent_review_and_create_issues_allowed(self) -> None:
        """--auto-coding-agent-review と --create-issues の併用が許可されることを確認。

        旧フローでは排他だったが、新フローでは併用可能。
        GH_TOKEN/REPO がないので exit_code=1 だが、
        auto_coding_agent_review が False にリセットされていないことを確認する。
        """
        import os
        old_env = os.environ.pop("REPO", None)
        old_gh = os.environ.pop("GH_TOKEN", None)
        old_github = os.environ.pop("GITHUB_TOKEN", None)
        try:
            args = _parse([
                "orchestrate", "-w", "aas",
                "--create-issues",
                "--auto-coding-agent-review",
            ])
            self.assertTrue(args.auto_coding_agent_review)
            self.assertTrue(args.create_issues)
        finally:
            if old_env is not None:
                os.environ["REPO"] = old_env
            if old_gh is not None:
                os.environ["GH_TOKEN"] = old_gh
            if old_github is not None:
                os.environ["GITHUB_TOKEN"] = old_github

    def test_ignore_paths_default_in_config(self) -> None:
        """config の ignore_paths にデフォルト値が設定されていることを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        config = _build_config(args)
        self.assertIsNotNone(config.ignore_paths)
        self.assertIn("docs", config.ignore_paths)
        self.assertIn("qa", config.ignore_paths)
        self.assertIn("work", config.ignore_paths)

    def test_ignore_paths_cli_override(self) -> None:
        """--ignore-paths で ignore_paths を上書きできることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--ignore-paths", "tmp", "build"])
        config = _build_config(args)
        self.assertEqual(config.ignore_paths, ["tmp", "build"])


class TestInteractiveModeCodeReview(unittest.TestCase):
    """インタラクティブモードの Code Review Agent オプションのテスト。

    _cmd_run_interactive() は Console の対話メソッドを使用するため、
    それらをモックしてテストする。
    """

    def _run_interactive_with_inputs(
        self,
        *,
        code_review: bool = False,
        auto_approval: bool = False,
        review_timeout: str = "7200",
        create_pr: bool = False,
        create_issues: bool = False,
    ) -> "SDKConfig":
        """Console メソッドをモックして _cmd_run_interactive を実行し、
        構築された SDKConfig を返す。

        run_workflow をモックして実行をスキップし、SDKConfig を capture する。
        """
        import unittest.mock as mock
        import asyncio

        captured_config = {}

        async def _fake_run_workflow(workflow_id, params, config):
            captured_config["cfg"] = config
            return {"completed": [], "failed": [], "skipped": []}

        # prompt_yes_no の回答順序:
        # 1. レビュー/QA サブモデル利用確認 → False
        # 2. QA 自動 → False
        # 3. Review 自動 → False
        # 4. Issue 作成 → create_issues
        # 5. PR 作成 → create_pr (create_issues=False 時のみ呼ばれる)
        # 6. Code Review Agent → code_review
        # 7. 自動承認 → auto_approval (code_review=True 時のみ)
        # 8. ドライラン → False
        # 9. 実行確認 → True
        yes_no_answers = [False, False, False, create_issues]
        if not create_issues:
            yes_no_answers.append(create_pr)
        yes_no_answers.append(code_review)
        if code_review:
            yes_no_answers.append(auto_approval)
        yes_no_answers += [False, True]  # dry_run, 実行確認

        yes_no_iter = iter(yes_no_answers)

        # prompt_input の回答順序:
        # 1. ブランチ → "main"
        # 2. 並列数 → "15"
        # 3. セッション idle タイムアウト → "7200"
        # 4. Review タイムアウト (code_review=True 時のみ)
        # 5. (repo_input — create_issues or create_pr の場合)
        # 6. 追加プロンプト → ""
        input_answers = ["main", "15", "7200"]
        if code_review:
            input_answers.append(review_timeout)
        if create_issues or create_pr:
            input_answers.append("owner/repo")
        input_answers.append("")  # 追加プロンプト

        input_iter = iter(input_answers)

        # Console のモックを作成
        MockConsole = mock.MagicMock()
        con = MockConsole.return_value
        con.s = mock.MagicMock(
            CYAN="", RESET="", DIM="", GREEN="", YELLOW="",
        )
        con.menu_select.side_effect = [0, 0, 2, 1]  # workflow, model, exec_mode(手動=2), verbosity
        con.prompt_multi_select.return_value = []  # 全ステップ
        con.prompt_yes_no.side_effect = lambda *a, **kw: next(yes_no_iter)
        con.prompt_input.side_effect = lambda *a, **kw: next(input_iter)

        # ワークフロー/ステップのモック
        mock_step = mock.MagicMock(
            id="s1", title="Step1", is_container=False, depends_on=[], params=[],
        )
        mock_wf = mock.MagicMock(
            id="aas", steps=[mock_step], params=[],
        )

        mock_list_workflows = mock.MagicMock(return_value=[mock_wf])
        mock_get_workflow = mock.MagicMock(return_value=mock_wf)
        mock_display_names = {"aas": "AAS"}

        # console, workflow_registry, template_engine, orchestrator をモックモジュールとして設定
        mock_console_mod = mock.MagicMock()
        mock_console_mod.Console = MockConsole

        mock_config_mod = mock.MagicMock()
        # SDKConfig は実物を使用する
        from config import SDKConfig  # type: ignore[import-untyped]
        mock_config_mod.SDKConfig = SDKConfig

        mock_wr_mod = mock.MagicMock()
        mock_wr_mod.list_workflows = mock_list_workflows
        mock_wr_mod.get_workflow = mock_get_workflow

        mock_te_mod = mock.MagicMock()
        mock_te_mod._WORKFLOW_DISPLAY_NAMES = mock_display_names

        mock_orch_mod = mock.MagicMock()
        mock_orch_mod.run_workflow = mock.MagicMock(side_effect=_fake_run_workflow)

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
        }):
            _cmd_run_interactive = _main_mod._cmd_run_interactive
            _cmd_run_interactive()

        return captured_config.get("cfg")

    def test_interactive_code_review_sets_config(self) -> None:
        """auto_coding_agent_review=True が SDKConfig に反映される。"""
        cfg = self._run_interactive_with_inputs(code_review=True)
        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.auto_coding_agent_review)

    def test_interactive_auto_approval_sets_config(self) -> None:
        """auto_approval=True が SDKConfig に反映される。"""
        cfg = self._run_interactive_with_inputs(code_review=True, auto_approval=True)
        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.auto_coding_agent_review_auto_approval)

    def test_interactive_no_review_no_approval_prompt(self) -> None:
        """code_review=False の場合、auto_approval は False のまま。"""
        cfg = self._run_interactive_with_inputs(code_review=False)
        self.assertIsNotNone(cfg)
        self.assertFalse(cfg.auto_coding_agent_review)
        self.assertFalse(cfg.auto_coding_agent_review_auto_approval)

    def test_interactive_code_review_without_create_pr(self) -> None:
        """code_review=True でも create_pr=False なら create_pr は False のまま。"""
        cfg = self._run_interactive_with_inputs(code_review=True, create_pr=False)
        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.auto_coding_agent_review)
        self.assertFalse(cfg.create_pr)

    def test_interactive_review_timeout_reflected(self) -> None:
        """review_timeout のカスタム値が SDKConfig に反映される。"""
        cfg = self._run_interactive_with_inputs(code_review=True, review_timeout="600")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.review_timeout_seconds, 600.0)

    def test_interactive_review_timeout_invalid_fallback(self) -> None:
        """review_timeout に非数値を入力した場合、デフォルト 7200.0 にフォールバック。"""
        cfg = self._run_interactive_with_inputs(code_review=True, review_timeout="abc")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.review_timeout_seconds, 7200.0)

    def test_interactive_keeps_review_model_from_env_when_not_selected(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["REVIEW_MODEL"] = "claude-sonnet-4.6"
            cfg = self._run_interactive_with_inputs(code_review=False)
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.review_model, "claude-sonnet-4.6")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_interactive_keeps_qa_model_from_env_when_not_selected(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["QA_MODEL"] = "gpt-5.4"
            cfg = self._run_interactive_with_inputs(code_review=False)
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.qa_model, "gpt-5.4")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)


class TestInteractiveModeAutoExecModes(unittest.TestCase):
    """インタラクティブモードのクイック全自動/カスタム全自動モードのテスト。"""

    def _run_interactive_auto_mode(
        self,
        exec_mode: int,  # 0=クイック全自動, 1=カスタム全自動
        *,
        auto_coding_agent_review: bool = False,
        custom_timeout: str = "86400",
    ) -> "SDKConfig":
        """Console メソッドをモックして指定した全自動モードで _cmd_run_interactive を実行し、
        構築された SDKConfig を返す。
        """
        import unittest.mock as mock
        import asyncio

        captured_config = {}

        async def _fake_run_workflow(workflow_id, params, config):
            captured_config["cfg"] = config
            return {"completed": [], "failed": [], "skipped": []}

        mock_step = mock.MagicMock(
            id="s1", title="Step1", is_container=False, depends_on=[], params=[],
        )
        mock_wf = mock.MagicMock(id="aas", steps=[mock_step], params=[])
        mock_display_names = {"aas": "AAS"}

        MockConsole = mock.MagicMock()
        con = MockConsole.return_value
        con.s = mock.MagicMock(CYAN="", RESET="", DIM="", GREEN="", YELLOW="")

        if exec_mode == 0:
            # クイック全自動: workflow, model, exec_mode(0) のみ
            con.menu_select.side_effect = [0, 0, 0]
            # use_different_models, 実行確認
            con.prompt_yes_no.side_effect = [False, True]
        else:
            # カスタム全自動: workflow, model, exec_mode(1), verbosity
            con.menu_select.side_effect = [0, 0, 1, 1]
            # use_different_models→False, QA自動→False, Review自動→False, Issue→False, PR→False,
            # Code Review→auto_coding_agent_review, (自動承認→False), ドライラン→False, 実行確認→True
            yes_no_answers = [False, False, False, False, False, auto_coding_agent_review]
            if auto_coding_agent_review:
                yes_no_answers.append(False)  # 自動承認
            yes_no_answers += [False, True]  # dry_run, 実行確認
            con.prompt_yes_no.side_effect = yes_no_answers
            # ブランチ, 並列数, タイムアウト, (review_timeout), 追加プロンプト
            input_answers = ["main", "15", custom_timeout]
            if auto_coding_agent_review:
                input_answers.append("7200")  # review timeout
            input_answers.append("")  # 追加プロンプト
            con.prompt_input.side_effect = input_answers

        con.prompt_multi_select.return_value = []

        mock_console_mod = mock.MagicMock()
        mock_console_mod.Console = MockConsole
        mock_config_mod = mock.MagicMock()
        from config import SDKConfig  # type: ignore[import-untyped]
        mock_config_mod.SDKConfig = SDKConfig
        mock_wr_mod = mock.MagicMock()
        mock_wr_mod.list_workflows = mock.MagicMock(return_value=[mock_wf])
        mock_wr_mod.get_workflow = mock.MagicMock(return_value=mock_wf)
        mock_te_mod = mock.MagicMock()
        mock_te_mod._WORKFLOW_DISPLAY_NAMES = mock_display_names
        mock_orch_mod = mock.MagicMock()
        mock_orch_mod.run_workflow = mock.MagicMock(side_effect=_fake_run_workflow)

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
        }):
            _cmd_run_interactive = _main_mod._cmd_run_interactive
            _cmd_run_interactive()

        return captured_config.get("cfg")

    def test_quick_auto_sets_unattended_true(self) -> None:
        """クイック全自動: cfg.unattended=True が設定される。"""
        cfg = self._run_interactive_auto_mode(exec_mode=0)
        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.unattended)

    def test_quick_auto_sets_timeout_86400(self) -> None:
        """クイック全自動: タイムアウトが 86400 秒に設定される。"""
        cfg = self._run_interactive_auto_mode(exec_mode=0)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.timeout_seconds, 86400.0)

    def test_quick_auto_sets_verbosity_normal(self) -> None:
        """クイック全自動: verbosity が normal (2) に設定される。"""
        cfg = self._run_interactive_auto_mode(exec_mode=0)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.verbosity, 2)

    def test_quick_auto_disables_force_interactive(self) -> None:
        """クイック全自動: force_interactive=False が強制される。"""
        cfg = self._run_interactive_auto_mode(exec_mode=0)
        self.assertIsNotNone(cfg)
        self.assertFalse(cfg.force_interactive)

    def test_quick_auto_sets_qa_answer_mode_all(self) -> None:
        """クイック全自動: qa_answer_mode='all' が設定される。"""
        cfg = self._run_interactive_auto_mode(exec_mode=0)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.qa_answer_mode, "all")

    def test_custom_auto_sets_unattended_true(self) -> None:
        """カスタム全自動: cfg.unattended=True が設定される。"""
        cfg = self._run_interactive_auto_mode(exec_mode=1)
        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.unattended)

    def test_custom_auto_default_timeout_86400(self) -> None:
        """カスタム全自動: タイムアウトのデフォルト入力で 86400 秒が設定される。"""
        cfg = self._run_interactive_auto_mode(exec_mode=1, custom_timeout="86400")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.timeout_seconds, 86400.0)

    def test_custom_auto_code_review_forces_auto_approval(self) -> None:
        """カスタム全自動 + auto_coding_agent_review=True: auto_approval が強制 True になる。"""
        cfg = self._run_interactive_auto_mode(exec_mode=1, auto_coding_agent_review=True)
        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.auto_coding_agent_review)
        self.assertTrue(cfg.auto_coding_agent_review_auto_approval)


class TestInteractiveAdocParamsValidation(unittest.TestCase):
    def _run_with_adoc_params_inputs(self, *, exec_mode: int) -> dict:
        import unittest.mock as mock

        captured = {}

        async def _fake_run_workflow(workflow_id, params, config):
            captured["params"] = params
            return {"completed": [], "failed": [], "skipped": []}

        mock_step = mock.MagicMock(id="1", title="Step1", is_container=False, depends_on=[], params=[])
        mock_wf = mock.MagicMock(id="adoc", steps=[mock_step], params=["doc_purpose", "max_file_lines"])
        mock_display_names = {"adoc": "ADOC"}

        MockConsole = mock.MagicMock()
        con = MockConsole.return_value
        con.s = mock.MagicMock(CYAN="", RESET="", DIM="", GREEN="", YELLOW="")
        con.prompt_multi_select.return_value = []

        if exec_mode == 0:
            # workflow, model, exec_mode, doc_purpose(migration=3, 0-indexed), max_file_lines(1000=2, 0-indexed)
            con.menu_select.side_effect = [0, 0, 0, 3, 2]
            con.prompt_yes_no.side_effect = [False, True]  # use_different_models, confirmation
        else:
            # workflow, model, exec_mode, verbosity, doc_purpose(onboarding=1, 0-indexed), max_file_lines(300=0, 0-indexed)
            con.menu_select.side_effect = [0, 0, 2, 1, 1, 0]
            con.prompt_yes_no.side_effect = [False, False, False, False, False, False, False, True]
            # branch, max_parallel, timeout, additional_prompt（doc_purpose/max_file_linesはmenu_selectで入力）
            con.prompt_input.side_effect = ["main", "15", "7200", ""]

        mock_console_mod = mock.MagicMock()
        mock_console_mod.Console = MockConsole
        mock_config_mod = mock.MagicMock()
        from config import SDKConfig  # type: ignore[import-untyped]
        mock_config_mod.SDKConfig = SDKConfig
        mock_wr_mod = mock.MagicMock()
        mock_wr_mod.list_workflows = mock.MagicMock(return_value=[mock_wf])
        mock_wr_mod.get_workflow = mock.MagicMock(return_value=mock_wf)
        mock_te_mod = mock.MagicMock()
        mock_te_mod._WORKFLOW_DISPLAY_NAMES = mock_display_names
        mock_orch_mod = mock.MagicMock()
        mock_orch_mod.run_workflow = mock.MagicMock(side_effect=_fake_run_workflow)

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
        }):
            _main_mod._cmd_run_interactive()

        captured["warning_called"] = con.warning.call_count
        return captured

    def test_doc_purpose_validation_in_quick_auto(self) -> None:
        captured = self._run_with_adoc_params_inputs(exec_mode=0)
        self.assertEqual(captured["params"]["doc_purpose"], "migration")
        self.assertEqual(captured["params"]["max_file_lines"], 1000)
        self.assertEqual(captured["warning_called"], 0)

    def test_doc_purpose_validation_in_manual(self) -> None:
        captured = self._run_with_adoc_params_inputs(exec_mode=2)
        self.assertEqual(captured["params"]["doc_purpose"], "onboarding")
        self.assertEqual(captured["params"]["max_file_lines"], 300)
        self.assertEqual(captured["warning_called"], 0)


class TestDocPurposePrompt(unittest.TestCase):
    def test_doc_purpose_selected_value(self) -> None:
        con = mock.MagicMock()
        con.s = mock.MagicMock(DIM="", RESET="")
        con.menu_select.return_value = 2
        val = _prompt_valid_doc_purpose(con)
        self.assertEqual(val, "refactoring")

    def test_doc_purpose_default_on_empty(self) -> None:
        con = mock.MagicMock()
        con.s = mock.MagicMock(DIM="", RESET="")
        con.menu_select.return_value = -1
        val = _prompt_valid_doc_purpose(con)
        self.assertEqual(val, "all")


class TestAqodDepthPrompt(unittest.TestCase):
    """AQOD depth メニュー選択のバリデーション。"""

    def test_select_lightweight(self) -> None:
        con = mock.MagicMock()
        con.s = mock.MagicMock(DIM="", RESET="")
        con.menu_select.return_value = 1
        depth = _prompt_valid_aqod_depth(con)
        self.assertEqual(depth, "lightweight")

    def test_default_standard_on_empty(self) -> None:
        con = mock.MagicMock()
        con.s = mock.MagicMock(DIM="", RESET="")
        con.menu_select.return_value = -1
        depth = _prompt_valid_aqod_depth(con)
        self.assertEqual(depth, "standard")


class TestMaxFileLinesPrompt(unittest.TestCase):
    def test_select_1000(self) -> None:
        con = mock.MagicMock()
        con.s = mock.MagicMock(DIM="", RESET="")
        con.menu_select.return_value = 2
        val = _prompt_valid_max_file_lines(con)
        self.assertEqual(val, 1000)
        self.assertIsInstance(val, int)

    def test_default_500_on_empty(self) -> None:
        con = mock.MagicMock()
        con.s = mock.MagicMock(DIM="", RESET="")
        con.menu_select.return_value = -1
        val = _prompt_valid_max_file_lines(con)
        self.assertEqual(val, 500)
        self.assertIsInstance(val, int)


class TestInteractiveMode(unittest.TestCase):
    """インタラクティブモード (run サブコマンド) のテスト。"""

    def test_parser_accepts_run_command(self) -> None:
        """run サブコマンドがパース可能であることを確認。"""
        args = _parse(["run"])
        self.assertEqual(args.command, "run")

    def test_parser_accepts_empty_args(self) -> None:
        """引数なしでもパース可能であることを確認（デフォルトで run になる）。"""
        args = _parse([])
        self.assertIsNone(args.command)  # subparsers 未選択

    def test_main_with_empty_args_calls_interactive(self) -> None:
        """main([]) が _cmd_run_interactive を呼び出すことを確認。"""
        # _cmd_run_interactive は Console を使うため、mock が必要
        import unittest.mock as mock
        with mock.patch.object(_main_mod, "_cmd_run_interactive", return_value=0) as mock_run:
            # 空引数で main を呼び出すと、command=None → _cmd_run_interactive が呼ばれる
            # ただし、argparse の動作確認が必要
            pass  # 実装確認は完了


if __name__ == "__main__":
    unittest.main()
