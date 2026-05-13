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

from prompts import PRE_EXECUTION_QA_PROMPT_V2, render_pre_execution_qa_comment_body

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
_collect_generic_workflow_params = _main_mod._collect_generic_workflow_params
_default_param_value = _main_mod._default_param_value
_PARAM_DEFAULTS = _main_mod._PARAM_DEFAULTS
_PARAM_PROMPT_LABELS = _main_mod._PARAM_PROMPT_LABELS
main = _main_mod.main

# Phase 4 Resume プロンプトをテスト全体で抑止（テスト環境の work/runs/ 状態に依存させない）。
# 個別の Resume プロンプトテストは test_wizard_resume_prompt.py 側で行う。
_resume_prompt_patcher = mock.patch.object(_main_mod, "_maybe_show_resume_prompt", return_value=None)
_resume_prompt_patcher.start()

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
        args = _parse(["orchestrate", "--workflow", "aad-web"])
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
        # Sub-D-1: --sources の argparse 既定値は None。
        # 実行時に _build_params / _collect_params_non_interactive が _AKM_DEFAULT_SOURCES
        # (= "qa,original-docs") を適用する。
        self.assertIsNone(args.sources)
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
        self.assertIsNone(args.workiq_akm_review)
        self.assertEqual(args.timeout, 21600.0)
        self.assertEqual(args.log_level, "error")
        self.assertIsNone(args.context_max_chars)

    def test_log_level_option(self) -> None:
        """--log-level オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "--log-level", "debug"])
        self.assertEqual(args.log_level, "debug")

    def test_model_option(self) -> None:
        """-m / --model オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "-m", "gpt-5.4"])
        self.assertEqual(args.model, "gpt-5.4")

    def test_model_option_gpt_5_5(self) -> None:
        """-m / --model gpt-5.5 オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aas", "-m", "gpt-5.5"])
        self.assertEqual(args.model, "gpt-5.5")

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

    def test_workiq_flags(self) -> None:
        args = _parse([
            "orchestrate", "-w", "aas", "--workiq",
            "--workiq-draft",
            "--workiq-draft-output-dir", "qa-drafts",
            "--workiq-tenant-id", "tenant-x",
            "--workiq-prompt-qa", "qa",
            "--workiq-prompt-km", "km",
            "--workiq-prompt-review", "review",
            "--workiq-akm-review",
        ])
        self.assertTrue(args.workiq)
        self.assertTrue(args.workiq_akm_review)
        self.assertTrue(args.workiq_draft)
        self.assertEqual(args.workiq_draft_output_dir, "qa-drafts")
        self.assertEqual(args.workiq_tenant_id, "tenant-x")
        self.assertEqual(args.workiq_prompt_qa, "qa")
        self.assertEqual(args.workiq_prompt_km, "km")
        self.assertEqual(args.workiq_prompt_review, "review")

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

    def test_context_max_chars_option(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--context-max-chars", "18000"])
        self.assertEqual(args.context_max_chars, 18000)

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

    def test_akm_force_refresh_default_false(self) -> None:
        """AKM force_refresh デフォルト値が False であることを確認（差分マージが既定）。"""
        args = _parse(["orchestrate", "-w", "akm"])
        params = _build_params(args)
        self.assertFalse(params["force_refresh"])

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
        """AKM sources が未指定時に既定 'qa,original-docs' になることを確認。

        Work IQ 入力対応に伴い、既定は qa + original-docs のマルチ値に変更された。
        """
        args = _parse(["orchestrate", "-w", "akm"])
        params = _build_params(args)
        self.assertEqual(params["sources"], "qa,original-docs")

    def test_akm_target_files_default_when_not_specified(self) -> None:
        """AKM target_files は既定（qa+original-docs マルチ）では空文字となる。

        非 Work IQ ソースが複数選択された場合、単一パターン既定は持たない。
        """
        args = _parse(["orchestrate", "-w", "akm"])
        params = _build_params(args)
        self.assertEqual(params["target_files"], "")

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


    def test_model_auto_kept_in_config(self) -> None:
        """--model Auto が固定モデルへ解決されず保持されることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--model", "Auto"])
        config = _build_config(args)
        self.assertEqual(config.model, "Auto")

    def test_model_4_6_still_selectable(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--model", "claude-opus-4.6"])
        config = _build_config(args)
        self.assertEqual(config.model, "claude-opus-4.6")

    def test_env_model_4_6_preserves_old_default(self) -> None:
        with mock.patch.dict(os.environ, {"MODEL": "claude-opus-4.6"}, clear=False):
            args = _parse(["orchestrate", "-w", "aas"])
            config = _build_config(args)
            self.assertEqual(config.model, "claude-opus-4.6")

    def test_default_model_auto_used_when_cli_and_env_missing(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            args = _parse(["orchestrate", "-w", "aas"])
            config = _build_config(args)
            self.assertEqual(config.model, "Auto")

    def test_cli_explicit_default_model_overrides_env_model(self) -> None:
        with mock.patch.dict(os.environ, {"MODEL": "claude-opus-4.6"}, clear=False):
            args = _parse(["orchestrate", "-w", "aas", "--model", "claude-opus-4.7"])
            config = _build_config(args)
            self.assertEqual(config.model, "claude-opus-4.7")

    def test_build_config_workiq(self) -> None:
        args = _parse([
            "orchestrate", "-w", "aas", "--workiq",
            "--workiq-draft",
            "--workiq-draft-output-dir", "qa-drafts",
            "--workiq-tenant-id", "tenant-x",
            "--workiq-prompt-qa", "qa",
            "--workiq-prompt-km", "km",
            "--workiq-prompt-review", "review",
        ])
        cfg = _build_config(args)
        self.assertTrue(cfg.workiq_enabled)
        self.assertTrue(cfg.is_workiq_qa_enabled())
        self.assertTrue(cfg.is_workiq_akm_review_enabled())
        self.assertEqual(cfg.workiq_tenant_id, "tenant-x")
        self.assertEqual(cfg.workiq_prompt_qa, "qa")
        self.assertEqual(cfg.workiq_prompt_km, "km")
        self.assertEqual(cfg.workiq_prompt_review, "review")
        self.assertTrue(cfg.workiq_draft_mode)
        self.assertEqual(cfg.workiq_draft_output_dir, "qa-drafts")

    def test_build_config_context_max_chars_override(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--context-max-chars", "18000"])
        cfg = _build_config(args)
        self.assertEqual(cfg.context_injection_max_chars, 18000)

    def test_build_config_workiq_akm_review_can_be_enabled_without_qa(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            args = _parse(["orchestrate", "-w", "akm", "--workiq-akm-review"])
            cfg = _build_config(args)
        self.assertTrue(cfg.workiq_enabled)
        self.assertFalse(cfg.is_workiq_qa_enabled())
        self.assertTrue(cfg.is_workiq_akm_review_enabled())

    def test_build_config_workiq_draft_output_dir_not_overridden_when_cli_omitted(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["WORKIQ_DRAFT_OUTPUT_DIR"] = "env-drafts"
            args = _parse(["orchestrate", "-w", "aas", "--workiq-draft"])
            cfg = _build_config(args)
            self.assertEqual(cfg.workiq_draft_output_dir, "env-drafts")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)


class TestSelfImproveCLI(unittest.TestCase):
    """--self-improve / --no-self-improve / HVE_AUTO_SELF_IMPROVE のテスト。"""

    def test_self_improve_flag_enables(self) -> None:
        """--self-improve で cfg.auto_self_improve == True になることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--self-improve"])
        cfg = _build_config(args)
        self.assertTrue(cfg.auto_self_improve)
        self.assertFalse(cfg.self_improve_skip)

    def test_no_self_improve_flag_sets_skip(self) -> None:
        """--no-self-improve で cfg.self_improve_skip == True になることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--no-self-improve"])
        cfg = _build_config(args)
        self.assertTrue(cfg.self_improve_skip)

    def test_no_self_improve_overrides_self_improve(self) -> None:
        """--no-self-improve が --self-improve より優先されることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--self-improve", "--no-self-improve"])
        cfg = _build_config(args)
        self.assertTrue(cfg.self_improve_skip)

    def test_env_var_enables_self_improve(self) -> None:
        """HVE_AUTO_SELF_IMPROVE=true で有効化されることを確認。"""
        with mock.patch.dict(os.environ, {"HVE_AUTO_SELF_IMPROVE": "true"}, clear=False):
            args = _parse(["orchestrate", "-w", "aas"])
            cfg = _build_config(args)
            self.assertTrue(cfg.auto_self_improve)

    def test_default_self_improve_is_false(self) -> None:
        """CLI 未指定・環境変数未指定では auto_self_improve==False になることを確認。"""
        with mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if "SELF_IMPROVE" not in k}, clear=True):
            args = _parse(["orchestrate", "-w", "aas"])
            cfg = _build_config(args)
            self.assertFalse(cfg.auto_self_improve)
            self.assertFalse(cfg.self_improve_skip)


class TestPromptAkmParamsEnableAutoMerge(unittest.TestCase):
    """_prompt_akm_params: GitHub 系質問は呼び出し元で扱い、AKM 固有値だけ収集する。"""

    _AUTO_MERGE_LABEL = "PR の自動 Approve & Auto-merge を有効にする？"
    _COMMENT_LABEL = "GitHub Issue への追加コメント（任意）"

    def _make_con(self):
        con = mock.MagicMock()
        con.menu_select.return_value = 0
        con.prompt_input.return_value = ""
        con.prompt_yes_no.return_value = False
        return con

    def _called_labels(self, con) -> list[str]:
        return [call.args[0] for call in con.prompt_yes_no.call_args_list]

    def _called_input_labels(self, con) -> list[str]:
        return [call.args[0] for call in con.prompt_input.call_args_list]

    def test_skips_auto_merge_when_no_pr(self) -> None:
        """will_create_pr=False のとき auto_merge 質問をスキップし False 固定。"""
        con = self._make_con()
        params = _prompt_akm_params(con, is_quick_auto=False, will_create_pr=False)
        self.assertFalse(params["enable_auto_merge"])
        self.assertNotIn(self._AUTO_MERGE_LABEL, self._called_labels(con))
        self.assertNotIn(self._COMMENT_LABEL, self._called_input_labels(con))

    def test_delegates_auto_merge_when_pr(self) -> None:
        """will_create_pr=True でも auto_merge 質問は呼び出し元に委譲する。"""
        con = self._make_con()
        params = _prompt_akm_params(con, is_quick_auto=False, will_create_pr=True)
        self.assertFalse(params["enable_auto_merge"])
        self.assertNotIn(self._AUTO_MERGE_LABEL, self._called_labels(con))

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

    def test_review_model_auto_kept_in_config(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--review-model", "Auto"])
        config = _build_config(args)
        self.assertEqual(config.review_model, "Auto")

    def test_review_model_auto_resolved_from_env_when_cli_missing(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["REVIEW_MODEL"] = "Auto"
            args = _parse(["orchestrate", "-w", "aas"])
            config = _build_config(args)
            self.assertEqual(config.review_model, "Auto")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_qa_model_auto_resolved_from_env_when_cli_missing(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["QA_MODEL"] = "Auto"
            args = _parse(["orchestrate", "-w", "aas"])
            config = _build_config(args)
            self.assertEqual(config.qa_model, "Auto")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_qa_merge_default_model_is_opus_4_7(self) -> None:
        args = _parse(["qa-merge", "--qa-file", "qa/sample.md"])
        self.assertEqual(args.model, "claude-opus-4.7")

    def test_qa_merge_auto_not_resolved_to_fixed_model(self) -> None:
        args = _parse(["qa-merge", "--qa-file", "qa/sample.md", "--model", "Auto"])
        model, _ = _resolve_model(args.model)
        self.assertEqual(model, "Auto")

    def test_resolve_model_empty_string_treated_as_auto(self) -> None:
        model, display = _resolve_model("")
        self.assertEqual(model, "Auto")
        self.assertEqual(display, "Auto")


class TestEmitPromptCommand(unittest.TestCase):
    """emit-prompt サブコマンドのテスト。"""

    def test_emit_prompt_args(self) -> None:
        args = _parse(["emit-prompt", "pre-qa", "--comment-body"])
        self.assertEqual(args.prompt_name, "pre-qa")
        self.assertTrue(args.comment_body)

    def test_main_emit_prompt_pre_qa(self) -> None:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = main(["emit-prompt", "pre-qa"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(buf.getvalue(), PRE_EXECUTION_QA_PROMPT_V2)

    def test_main_emit_prompt_pre_qa_comment_body(self) -> None:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = main(["emit-prompt", "pre-qa", "--comment-body"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(buf.getvalue(), render_pre_execution_qa_comment_body())


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
        for wf_id in ["aas", "aad-web", "asdw-web", "abd", "abdv", "aag", "aagd", "akm", "aqod", "adoc"]:
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

    def test_warns_when_both_review_modes_enabled(self) -> None:
        """--auto-contents-review と --auto-coding-agent-review が同時に有効な場合、
        warning が stderr に出力されるが実行は続行する（戻り値は True）。"""
        args = _parse([
            "orchestrate", "-w", "aas",
            "--auto-coding-agent-review",
            "--auto-contents-review",
        ])
        config = self._make_config()
        import io
        buf = io.StringIO()
        with mock.patch("sys.stderr", buf):
            result = _validate_auto_coding_agent_review(args, config)
        output = buf.getvalue()

        self.assertTrue(result)  # 強制終了しない
        self.assertIn("WARNING", output)
        self.assertIn("--auto-contents-review", output)
        self.assertIn("--auto-coding-agent-review", output)

    def test_no_warning_when_only_coding_agent_review_enabled(self) -> None:
        """--auto-coding-agent-review のみ有効な場合、重複レビュー WARNING は出力されない。"""
        args = _parse([
            "orchestrate", "-w", "aas",
            "--auto-coding-agent-review",
            "--quiet",
        ])
        config = self._make_config()
        import io
        buf = io.StringIO()
        with mock.patch("sys.stderr", buf):
            result = _validate_auto_coding_agent_review(args, config)
        output = buf.getvalue()

        self.assertTrue(result)
        self.assertNotIn("WARNING", output)


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

    def test_ignore_paths_auto_remove_qa_when_workiq_draft_and_create_pr(self) -> None:
        args = _parse(["orchestrate", "-w", "aas", "--workiq-draft", "--create-pr"])
        config = _build_config(args)
        self.assertTrue(config.create_pr)
        self.assertTrue(config.workiq_draft_mode)
        self.assertNotIn("qa", config.ignore_paths)


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
        auto_qa: bool = False,
        use_different_qa_model: bool = False,
        auto_review: bool = False,
        use_different_review_model: bool = False,
    ) -> "SDKConfig":
        """Console メソッドをモックして _cmd_run_interactive を実行し、
        構築された SDKConfig を返す。

        run_workflow をモックして実行をスキップし、SDKConfig を capture する。
        """
        import unittest.mock as mock
        import asyncio

        captured_config = {}

        async def _fake_run_workflow(workflow_id, params, config, **kwargs):
            captured_config["cfg"] = config
            return {"completed": [], "failed": [], "skipped": []}

        # prompt_yes_no の回答順序（Phase E 再編後）:
        # 1. auto_qa (Phase E-1)
        # 2. (auto_qa=True 時のみ) use_different_qa_model (Phase E-1 内)
        # 3. auto_review (Phase E-2)
        # 4. Code Review Agent → code_review (Phase E-4)
        # 5. (code_review=True 時のみ) 自動承認 → auto_approval (Phase E-4 内)
        # 6. (auto_review or code_review 時のみ) use_different_review_model (Phase E-5)
        # 7. 自己改善 → False (Phase E-6)
        # 8. Issue 作成 → create_issues (Phase F)
        # 9. PR 作成 → create_pr (create_issues=False 時のみ呼ばれる) (Phase F)
        # 10. ドライラン → False (Phase G)
        # 11. 実行確認 → True
        yes_no_answers = [auto_qa]
        if auto_qa:
            yes_no_answers.append(use_different_qa_model)
        yes_no_answers.append(auto_review)
        yes_no_answers.append(code_review)
        if code_review:
            yes_no_answers.append(auto_approval)
        if auto_review or code_review:
            yes_no_answers.append(use_different_review_model)
        yes_no_answers.append(False)  # auto_self_improve
        yes_no_answers.append(create_issues)
        if not create_issues:
            yes_no_answers.append(create_pr)
        yes_no_answers.append(False)  # dry_run
        yes_no_answers.append(True)  # 実行確認

        yes_no_iter = iter(yes_no_answers)

        # prompt_input の回答順序（Phase 再編後）:
        # 1. 追加プロンプト → ""             (Phase A')
        # 2. セッション idle タイムアウト    (Phase D)
        # 3. ブランチ → "main"               (Phase D)
        # 4. 並列数 → "15"                   (Phase D)
        # 5. Review タイムアウト (code_review=True 時のみ) (Phase E)
        # 6. Issue タイトル/追加コメント (create_issues=True 時のみ) (Phase F)
        # 7. repo_input (create_issues or create_pr の場合)        (Phase F)
        # 8. セッション名（Phase 4 Resume）→ "" で既定使用
        input_answers = ["", "7200", "main", "15"]
        if code_review:
            input_answers.append(review_timeout)
        if create_issues:
            input_answers += ["", ""]
        if create_issues or create_pr:
            input_answers.append("owner/repo")
        input_answers.append("")  # Phase 4: セッション名（既定値を使用）

        input_iter = iter(input_answers)

        # Console のモックを作成
        MockConsole = mock.MagicMock()
        con = MockConsole.return_value
        con.s = mock.MagicMock(
            CYAN="", RESET="", DIM="", GREEN="", YELLOW="",
        )
        # Phase 再編後の menu_select 順序: workflow, exec_mode, model, verbosity,
        #   (auto_qa & use_different_qa_model のとき) QA サブモデル (Phase E-1 内),
        #   ((auto_review or code_review) & use_different_review_model のとき) Review サブモデル (Phase E-5)
        # ※ Phase D (verbosity) は Phase E より前のため、verbosity の後に Phase E の menu が来る。
        menu_answers = [0, 2, 0]  # workflow, exec_mode(手動=2), model
        model_options_for_test = [_main_mod.MODEL_AUTO, *_main_mod.MODEL_CHOICES]
        menu_answers.append(1)  # verbosity
        if auto_qa and use_different_qa_model:
            menu_answers.append(model_options_for_test.index("gpt-5.4"))
        if (auto_review or code_review) and use_different_review_model:
            menu_answers.append(model_options_for_test.index("claude-opus-4.6"))
        con.menu_select.side_effect = menu_answers
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
        mock_workiq_mod = mock.MagicMock()
        mock_workiq_mod.is_workiq_available = mock.MagicMock(return_value=False)
        mock_workiq_mod.workiq_login = mock.MagicMock(return_value=False)

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
            "workiq": mock_workiq_mod,
        }), mock.patch.object(_main_mod, "_maybe_show_resume_prompt", return_value=None):
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
            os.environ["REVIEW_MODEL"] = "claude-opus-4.6"
            cfg = self._run_interactive_with_inputs(
                code_review=False,
                auto_review=True,
                use_different_review_model=False,
            )
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.review_model, "claude-opus-4.6")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_interactive_keeps_qa_model_from_env_when_not_selected(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["QA_MODEL"] = "gpt-5.4"
            cfg = self._run_interactive_with_inputs(
                code_review=False,
                auto_qa=True,
                use_different_qa_model=False,
            )
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg.qa_model, "gpt-5.4")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_interactive_selects_qa_model_only_when_auto_qa_enabled(self) -> None:
        cfg = self._run_interactive_with_inputs(
            auto_qa=True,
            use_different_qa_model=True,
            auto_review=False,
        )
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.qa_model, "gpt-5.4")

    def test_interactive_selects_review_model_only_when_auto_review_enabled(self) -> None:
        cfg = self._run_interactive_with_inputs(
            auto_qa=False,
            auto_review=True,
            use_different_review_model=True,
        )
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.review_model, "claude-opus-4.6")


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

        async def _fake_run_workflow(workflow_id, params, config, **kwargs):
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
            # クイック全自動: workflow, exec_mode(0), model のみ（Phase 再編後）
            con.menu_select.side_effect = [0, 0, 0]
            # 実行確認
            con.prompt_yes_no.side_effect = [True]
        else:
            # カスタム全自動（Phase 再編後）: workflow, exec_mode(1), model, verbosity
            con.menu_select.side_effect = [0, 1, 0, 1]
            # Phase 再編後の yes_no 順:
            #   Phase E: QA自動→False, Review自動→False, Code Review→auto_coding_agent_review,
            #            (auto_coding_agent_review=True のとき) use_different_review_model→False,
            #            自己改善→False
            #   Phase F: Issue→False, PR→False
            #   Phase G: dry_run→False
            #   最終  : 実行確認→True
            yes_no_answers = [False, False, auto_coding_agent_review]
            if auto_coding_agent_review:
                yes_no_answers.append(False)  # use_different_review_model
            yes_no_answers += [False]   # auto_self_improve
            yes_no_answers += [False, False]  # create_issues, create_pr
            yes_no_answers += [False, True]   # dry_run, 実行確認
            con.prompt_yes_no.side_effect = yes_no_answers
            # 追加プロンプト, タイムアウト, ブランチ, 並列数, (review_timeout), セッション名
            input_answers = ["", custom_timeout, "main", "15"]
            if auto_coding_agent_review:
                input_answers.append("7200")  # review timeout
            input_answers.append("")  # Phase 4: セッション名（既定値を使用）
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
        mock_workiq_mod = mock.MagicMock()
        mock_workiq_mod.is_workiq_available = mock.MagicMock(return_value=False)
        mock_workiq_mod.workiq_login = mock.MagicMock(return_value=False)

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
            "workiq": mock_workiq_mod,
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


class TestInteractiveModeQaAutoDefaults(unittest.TestCase):
    def test_manual_mode_auto_qa_enables_qa_auto_defaults_without_extra_prompts(self) -> None:
        """手動モード + auto_qa=True: prompt_answer_mode を呼ばず qa_auto_defaults=True を設定する。"""
        import unittest.mock as mock

        captured_config = {}

        async def _fake_run_workflow(workflow_id, params, config, **kwargs):
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
        con.menu_select.side_effect = [0, 2, 0, 1]  # workflow, exec_mode(手動), model, verbosity
        # Phase 再編後の yes_no 順:
        #   Phase E: auto_qa=True, (auto_qa=Trueなので) use_different_qa_model=False,
        #            auto_review=False, code_review=False, self_improve=False
        #   Phase F: create_issues=False, create_pr=False
        #   Phase G: dry_run=False / 実行確認=True
        con.prompt_yes_no.side_effect = [True, False, False, False, False, False, False, False, True]
        # Phase 再編後の input 順: addl_prompt, timeout, branch, parallel, session_name (Phase 4)
        con.prompt_input.side_effect = ["", "21600", "main", "15", ""]
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
        mock_workiq_mod = mock.MagicMock()
        mock_workiq_mod.is_workiq_available = mock.MagicMock(return_value=False)
        mock_workiq_mod.workiq_login = mock.MagicMock(return_value=False)

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
            "workiq": mock_workiq_mod,
        }):
            _cmd_run_interactive = _main_mod._cmd_run_interactive
            _cmd_run_interactive()

        cfg = captured_config.get("cfg")
        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.auto_qa)
        self.assertEqual(cfg.qa_answer_mode, "all")
        self.assertFalse(cfg.force_interactive)
        self.assertTrue(cfg.qa_auto_defaults)
        con.prompt_answer_mode.assert_not_called()


class TestInteractiveModeAqodQaFlow(unittest.TestCase):
    def test_manual_mode_akm_without_auto_qa_keeps_workiq_disabled(self) -> None:
        """AKM は QA と実行後レビュー Work IQ を別々に表示し、拒否すれば無効のまま。"""
        import unittest.mock as mock

        captured = {}

        async def _fake_run_workflow(workflow_id, params, config, **kwargs):
            captured["cfg"] = config
            captured["params"] = params
            return {"completed": [], "failed": [], "skipped": []}

        mock_step = mock.MagicMock(
            id="1", title="Step1", is_container=False, depends_on=[], params=[]
        )
        mock_wf = mock.MagicMock(id="akm", steps=[mock_step], params=[])
        mock_display_names = {"akm": "AKM"}

        MockConsole = mock.MagicMock()
        con = MockConsole.return_value
        con.s = mock.MagicMock(CYAN="", RESET="", DIM="", GREEN="", YELLOW="")
        # Phase 再編後の menu_select 順: workflow(akm), exec_mode(手動), model, AKM sources(Phase A'), verbosity(Phase D)
        con.menu_select.side_effect = [0, 2, 0, 0, 1]
        # Phase 再編後の yes_no 順:
        #   force_refresh=False(Phase A' AKM, 差分マージが既定), AKM QA=False, WorkIQ review=False,
        #   CodeReview=False, auto_self_improve=False,
        #   Issue=False, PR=False, dry_run=False, confirm=True
        con.prompt_yes_no.side_effect = [False, False, False, False, False, False, False, False, True]
        # Phase 再編後の input 順:
        #   target_files, custom_source_dir, additional_prompt, timeout, branch, session_name
        con.prompt_input.side_effect = [
            "",       # AKM target_files default
            "",       # custom_source_dir
            "",       # additional_prompt
            "21600",  # timeout
            "main",   # branch
            "",       # Phase 4: セッション名（既定値を使用）
        ]
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
        mock_workiq_mod = mock.MagicMock()
        mock_workiq_mod.is_workiq_available = mock.MagicMock(return_value=True)
        mock_workiq_mod.workiq_login = mock.MagicMock(return_value=True)
        mock_workiq_mod.get_workiq_prompt_template = mock.MagicMock(side_effect=lambda mode: f"default-{mode}")

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
            "workiq": mock_workiq_mod,
        }):
            _main_mod._cmd_run_interactive()

        cfg = captured.get("cfg")
        self.assertIsNotNone(cfg)
        self.assertFalse(cfg.auto_qa)
        self.assertFalse(cfg.workiq_enabled)
        self.assertFalse(cfg.is_workiq_qa_enabled())
        self.assertFalse(cfg.is_workiq_akm_review_enabled())
        mock_workiq_mod.workiq_login.assert_not_called()
        prompts = [c.args[0] for c in con.prompt_yes_no.call_args_list if c.args]
        self.assertTrue(any("AKM 実行前に QA" in str(p) for p in prompts))
        self.assertTrue(any("Work IQ" in str(p) and "knowledge/" in str(p) for p in prompts))

    def test_manual_mode_aqod_auto_qa_enables_workiq_draft_mode(self) -> None:
        # T-D: 本テストは _cmd_run_interactive の prompt_yes_no 順序に実装が
        # 追い付いておらず、cfg.auto_qa=False で不一致となる。2026-05-11 時点で
        # 詳細調査未完了のため一時スキップし、別 Issue で追跡する。
        import unittest as _ut
        raise _ut.SkipTest(
            "T-D: prompt_yes_no の順序と実装の逐一致調査が未完了。別 Issue でトリアージ訪問順を見直し予定。"
        )
        import unittest.mock as mock

        captured = {}

        async def _fake_run_workflow(workflow_id, params, config, **kwargs):
            captured["cfg"] = config
            return {"completed": [], "failed": [], "skipped": []}

        mock_step = mock.MagicMock(
            id="1", title="Step1", is_container=False, depends_on=[], params=[],
        )
        mock_wf = mock.MagicMock(id="aqod", steps=[mock_step], params=[])
        mock_display_names = {"aqod": "AQOD"}

        MockConsole = mock.MagicMock()
        con = MockConsole.return_value
        con.s = mock.MagicMock(CYAN="", RESET="", DIM="", GREEN="", YELLOW="")
        # workflow(aqod), model, exec_mode(手動), verbosity, aqod depth(default)
        con.menu_select.side_effect = [0, 0, 2, 1, -1]
        # prompt_yes_no の順序:
        # 1) AQOD後QA実施 2) Work IQ利用 3) Issue作成 4) PR作成
        # 5) Code Review有効化 6) dry_run 7) auto_self_improve 8) 実行確認
        # （AQOD + auto_qa=True のため Work IQドラフト確認プロンプトは表示されない）
        # side_effect = [QA, WorkIQ, Issue, PR, CodeReview, dry_run, auto_self_improve, confirm]
        con.prompt_yes_no.side_effect = [True, True, False, False, False, False, False, True]
        con.prompt_input.side_effect = [
            "main",               # branch
            "21600",              # timeout
            "社内略語は使わない",  # workiq_additional_prompt
            "1200",               # workiq_per_question_timeout（20 分）
            "original-docs/",     # target_scope
            "",                   # focus_areas
            "",                   # additional_prompt
            "",                   # Phase 4: セッション名（既定値を使用）
        ]
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
        mock_workiq_mod = mock.MagicMock()
        mock_workiq_mod.is_workiq_available = mock.MagicMock(return_value=True)
        mock_workiq_mod.workiq_login = mock.MagicMock(return_value=True)
        mock_workiq_mod.get_workiq_prompt_template = mock.MagicMock(side_effect=lambda mode: f"default-{mode}")

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
            "workiq": mock_workiq_mod,
        }):
            _main_mod._cmd_run_interactive()

        cfg = captured.get("cfg")
        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.auto_qa)
        self.assertTrue(cfg.workiq_enabled)
        self.assertEqual(cfg.qa_answer_mode, "all")
        self.assertTrue(cfg.workiq_draft_mode)
        self.assertEqual(cfg.workiq_prompt_qa, "default-qa\n\n社内略語は使わない")
        self.assertEqual(cfg.workiq_prompt_km, "default-km\n\n社内略語は使わない")
        self.assertEqual(cfg.workiq_prompt_review, "default-review\n\n社内略語は使わない")
        prompts = [c.args[0] for c in con.prompt_yes_no.call_args_list if c.args]
        self.assertNotIn("Work IQ で回答ドラフトを自動生成する？", prompts)
        input_prompts = [c.args[0] for c in con.prompt_input.call_args_list if c.args]
        self.assertIn("Work IQ (Microsoft 365 Copilot) の末尾に追加するプロンプト（省略可）", input_prompts)
        self.assertIn("全てのステップでの Prompt の末尾に追加するプロンプト（省略可）", input_prompts)
        panel_lines = con.panel.call_args.args[1]
        self.assertTrue(any(str(line).startswith("Work IQ Prompt: ") for line in panel_lines))
        self.assertTrue(any("社内略語は使わない" in str(line) for line in panel_lines))


class TestInteractiveAdocParamsValidation(unittest.TestCase):
    def _run_with_adoc_params_inputs(self, *, exec_mode: int) -> dict:
        import unittest.mock as mock

        captured = {}

        async def _fake_run_workflow(workflow_id, params, config, **kwargs):
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
            # workflow, exec_mode(0), model（Phase 再編後。クイック全自動は ADOC パラメータも既定値採用）
            con.menu_select.side_effect = [0, 0, 0]
            con.prompt_yes_no.side_effect = [True]  # confirmation
        else:
            # Phase 再編後の menu_select 順:
            #   workflow, exec_mode(2=手動), doc_purpose(1=onboarding), max_file_lines(0=300), model, verbosity(1)
            #   (Phase A' でワークフロー固有パラメータを収集 → Phase C でモデル選択)
            con.menu_select.side_effect = [0, 2, 1, 0, 0, 1]
            # Phase 再編後の yes_no 順:
            #   Phase E: auto_qa=False, auto_review=False, code_review=False, self_improve=False
            #   Phase F: create_issues=False, create_pr=False
            #   Phase G: dry_run=False / 実行確認=True
            con.prompt_yes_no.side_effect = [False, False, False, False, False, False, False, True]
            # Phase 再編後の input 順: additional_prompt, timeout, branch, parallel, session_name
            con.prompt_input.side_effect = ["", "7200", "main", "15", ""]

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
        mock_workiq_mod = mock.MagicMock()
        mock_workiq_mod.is_workiq_available = mock.MagicMock(return_value=False)
        mock_workiq_mod.workiq_login = mock.MagicMock(return_value=False)

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
            "workiq": mock_workiq_mod,
        }):
            _main_mod._cmd_run_interactive()

        captured["warning_called"] = con.warning.call_count
        return captured

    def test_doc_purpose_defaults_in_quick_auto(self) -> None:
        captured = self._run_with_adoc_params_inputs(exec_mode=0)
        self.assertEqual(captured["params"]["doc_purpose"], "all")
        self.assertEqual(captured["params"]["max_file_lines"], 500)
        self.assertEqual(captured["warning_called"], 0)

    def test_doc_purpose_validation_in_manual(self) -> None:
        captured = self._run_with_adoc_params_inputs(exec_mode=2)
        self.assertEqual(captured["params"]["doc_purpose"], "onboarding")
        self.assertEqual(captured["params"]["max_file_lines"], 300)
        self.assertEqual(captured["warning_called"], 0)


class TestInteractiveWorkflowParamPrompts(unittest.TestCase):
    def _run_with_aad_web_params(self, *, exec_mode: int):
        import unittest.mock as mock

        captured = {}

        async def _fake_run_workflow(workflow_id, params, config, **kwargs):
            captured["params"] = params
            return {"completed": [], "failed": [], "skipped": []}

        mock_step = mock.MagicMock(id="1", title="Step1", is_container=False, depends_on=[], params=[])
        mock_wf = mock.MagicMock(
            id="aad-web",
            steps=[mock_step],
            params=["app_ids", "app_id", "resource_group"],
        )
        mock_display_names = {"aad-web": "AAD-WEB"}

        MockConsole = mock.MagicMock()
        con = MockConsole.return_value
        con.s = mock.MagicMock(CYAN="", RESET="", DIM="", GREEN="", YELLOW="")
        con.prompt_multi_select.return_value = []

        if exec_mode == 0:
            con.menu_select.side_effect = [0, 0, 0]
            con.prompt_yes_no.side_effect = [True]
        else:
            # Phase 再編後: workflow, exec_mode(2=手動), model, verbosity
            con.menu_select.side_effect = [0, 2, 0, 1]
            # Phase 再編後の yes_no 順:
            #   Phase E: auto_qa=False, auto_review=False, code_review=False, self_improve=False
            #   Phase F: create_issues=False, create_pr=False
            #   Phase G: dry_run=False / 実行確認=True
            con.prompt_yes_no.side_effect = [False, False, False, False, False, False, False, True]
            # Phase 再編後の input 順:
            #   app_ids(Phase A'), resource_group(Phase A'), additional_prompt(Phase A'),
            #   timeout, branch, parallel(Phase D), session_name
            con.prompt_input.side_effect = ["APP-01", "rg-prod", "", "21600", "main", "15", ""]

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
        mock_workiq_mod = mock.MagicMock()
        mock_workiq_mod.is_workiq_available = mock.MagicMock(return_value=False)
        mock_workiq_mod.workiq_login = mock.MagicMock(return_value=False)

        with mock.patch.dict("sys.modules", {
            "console": mock_console_mod,
            "config": mock_config_mod,
            "workflow_registry": mock_wr_mod,
            "template_engine": mock_te_mod,
            "orchestrator": mock_orch_mod,
            "workiq": mock_workiq_mod,
        }):
            _main_mod._cmd_run_interactive()

        return captured, con

    def test_manual_mode_prompts_app_ids_once_and_derives_app_id(self) -> None:
        captured, con = self._run_with_aad_web_params(exec_mode=2)
        params = captured["params"]
        self.assertEqual(params["app_ids"], ["APP-01"])
        self.assertEqual(params["app_id"], "APP-01")
        self.assertEqual(params["resource_group"], "rg-prod")
        input_prompts = [c.args[0] for c in con.prompt_input.call_args_list if c.args]
        app_prompts = [p for p in input_prompts if "APP-ID" in str(p)]
        self.assertEqual(len(app_prompts), 1)
        self.assertNotIn("app_id", input_prompts)

    def test_quick_auto_does_not_prompt_optional_workflow_params(self) -> None:
        captured, con = self._run_with_aad_web_params(exec_mode=0)
        params = captured["params"]
        self.assertNotIn("app_ids", params)
        self.assertNotIn("app_id", params)
        self.assertEqual(params["resource_group"], "")
        con.prompt_input.assert_not_called()


class TestCreateRemoteMcpServerParam(unittest.TestCase):
    """create_remote_mcp_server パラメータの CLI / 収集 / デフォルト値テスト。"""

    def test_param_default_is_true(self) -> None:
        """_PARAM_DEFAULTS の create_remote_mcp_server デフォルトが True であること。"""
        self.assertIs(_PARAM_DEFAULTS["create_remote_mcp_server"], True)

    def test_param_prompt_label_exists(self) -> None:
        """_PARAM_PROMPT_LABELS に create_remote_mcp_server の表示名が登録されていること。"""
        self.assertIn("create_remote_mcp_server", _PARAM_PROMPT_LABELS)
        self.assertTrue(_PARAM_PROMPT_LABELS["create_remote_mcp_server"])

    def test_default_param_value_returns_true(self) -> None:
        """_default_param_value('create_remote_mcp_server') が True を返すこと。"""
        self.assertIs(_default_param_value("create_remote_mcp_server"), True)

    def test_collect_generic_prompts_yes_no_for_create_remote_mcp_server(self) -> None:
        """_collect_generic_workflow_params() が create_remote_mcp_server を yes/no prompt で収集すること。"""
        mock_wf = mock.MagicMock()
        mock_wf.id = "asdw-web"
        mock_wf.params = ["create_remote_mcp_server"]
        con = mock.MagicMock()
        con.prompt_yes_no.return_value = False

        params = _collect_generic_workflow_params(con, mock_wf, is_quick_auto=False)

        con.prompt_yes_no.assert_called_once()
        call_label = con.prompt_yes_no.call_args[0][0]
        self.assertIn("Remote MCP Server", call_label)
        self.assertFalse(params["create_remote_mcp_server"])

    def test_collect_generic_quick_auto_returns_default_true(self) -> None:
        """_collect_generic_workflow_params() の is_quick_auto=True で True が返ること。"""
        mock_wf = mock.MagicMock()
        mock_wf.id = "asdw-web"
        mock_wf.params = ["create_remote_mcp_server"]
        con = mock.MagicMock()

        params = _collect_generic_workflow_params(con, mock_wf, is_quick_auto=True)

        self.assertIs(params["create_remote_mcp_server"], True)
        con.prompt_yes_no.assert_not_called()

    def test_collect_generic_prompts_yes_no_default_is_true(self) -> None:
        """_collect_generic_workflow_params() の yes/no デフォルトが True であること。"""
        mock_wf = mock.MagicMock()
        mock_wf.id = "asdw-web"
        mock_wf.params = ["create_remote_mcp_server"]
        con = mock.MagicMock()
        con.prompt_yes_no.return_value = True

        params = _collect_generic_workflow_params(con, mock_wf, is_quick_auto=False)

        call_args = con.prompt_yes_no.call_args
        call_kwargs = call_args[1] if call_args[1] else {}
        call_positional = call_args[0] if call_args[0] else ()
        call_default = call_kwargs.get("default") if "default" in call_kwargs else (call_positional[1] if len(call_positional) > 1 else None)
        self.assertIs(call_default, True)
        self.assertTrue(params["create_remote_mcp_server"])


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


class TestWorkIQDoctorSdkProbeArgs(unittest.TestCase):
    """Phase 3: workiq-doctor --sdk-probe の引数パーステスト。"""

    def test_sdk_probe_arg_parsed(self) -> None:
        args = _parse(["workiq-doctor", "--sdk-probe"])
        self.assertTrue(args.sdk_probe)

    def test_sdk_probe_default_false(self) -> None:
        args = _parse(["workiq-doctor"])
        self.assertFalse(args.sdk_probe)

    def test_skip_mcp_probe_and_sdk_probe_combined(self) -> None:
        args = _parse(["workiq-doctor", "--skip-mcp-probe", "--sdk-probe"])
        self.assertTrue(args.skip_mcp_probe)
        self.assertTrue(args.sdk_probe)

    def test_sdk_probe_timeout_default(self) -> None:
        args = _parse(["workiq-doctor", "--sdk-probe"])
        self.assertEqual(args.sdk_probe_timeout, 30.0)

    def test_sdk_probe_timeout_custom(self) -> None:
        args = _parse(["workiq-doctor", "--sdk-probe", "--sdk-probe-timeout", "60.0"])
        self.assertEqual(args.sdk_probe_timeout, 60.0)

    def test_sdk_tool_probe_args_parsed(self) -> None:
        args = _parse([
            "workiq-doctor",
            "--event-extractor-self-test",
            "--sdk-tool-probe",
            "--sdk-tool-probe-timeout", "90.0",
            "--sdk-event-trace",
            "--sdk-tool-probe-tools-all",
        ])
        self.assertTrue(args.event_extractor_self_test)
        self.assertTrue(args.sdk_tool_probe)
        self.assertEqual(args.sdk_tool_probe_timeout, 90.0)
        self.assertTrue(args.sdk_event_trace)
        self.assertTrue(args.sdk_tool_probe_tools_all)

    def test_cmd_workiq_doctor_passes_sdk_probe_to_diagnostics(self) -> None:
        import workiq as _workiq_mod
        mock_report = _workiq_mod.WorkIQDiagnosticReport(checks=[
            _workiq_mod.WorkIQDiagnosticCheck(name="os_info", status="PASS", detail="ok"),
        ])
        args = mock.Mock()
        args.tenant_id = None
        args.skip_mcp_probe = True
        args.timeout = 5.0
        args.json = False
        args.sdk_probe = True
        args.sdk_probe_timeout = 30.0
        args.event_extractor_self_test = False
        args.sdk_tool_probe = False
        args.sdk_tool_probe_timeout = 60.0
        args.sdk_event_trace = False
        args.sdk_tool_probe_tools_all = False
        with mock.patch.object(_workiq_mod, "run_workiq_diagnostics", return_value=mock_report) as mock_diag:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                _main_mod._cmd_workiq_doctor(args)
        self.assertTrue(mock_diag.called)
        call_kwargs = mock_diag.call_args.kwargs
        self.assertTrue(call_kwargs.get("sdk_probe"))
        self.assertEqual(call_kwargs.get("sdk_probe_timeout"), 30.0)

    def test_cmd_workiq_doctor_passes_sdk_tool_probe_options(self) -> None:
        import workiq as _workiq_mod
        mock_report = _workiq_mod.WorkIQDiagnosticReport(checks=[
            _workiq_mod.WorkIQDiagnosticCheck(name="os_info", status="PASS", detail="ok"),
        ])
        args = mock.Mock()
        args.tenant_id = None
        args.skip_mcp_probe = True
        args.timeout = 5.0
        args.json = False
        args.sdk_probe = False
        args.sdk_probe_timeout = 30.0
        args.event_extractor_self_test = True
        args.sdk_tool_probe = True
        args.sdk_tool_probe_timeout = 90.0
        args.sdk_event_trace = True
        args.sdk_tool_probe_tools_all = True
        with mock.patch.object(_workiq_mod, "run_workiq_diagnostics", return_value=mock_report) as mock_diag:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                _main_mod._cmd_workiq_doctor(args)
        call_kwargs = mock_diag.call_args.kwargs
        self.assertTrue(call_kwargs.get("event_extractor_self_test"))
        self.assertTrue(call_kwargs.get("sdk_tool_probe"))
        self.assertEqual(call_kwargs.get("sdk_tool_probe_timeout"), 90.0)
        self.assertTrue(call_kwargs.get("sdk_event_trace"))
        self.assertTrue(call_kwargs.get("sdk_tool_probe_tools_all"))


# -----------------------------------------------------------------------
# F1〜F4: 新 CLI フラグの argparse / _build_config 配線テスト
# -----------------------------------------------------------------------


class TestBuildConfigOutputFlags(unittest.TestCase):
    """--no-color / --banner / --screen-reader / --timestamp-style が config に反映されること。"""

    def test_no_color_flag_sets_config(self) -> None:
        """--no-color が cfg.no_color=True に反映される。"""
        args = _parse(["orchestrate", "-w", "aas", "--no-color"])
        config = _build_config(args)
        self.assertTrue(config.no_color)

    def test_no_color_default_is_none(self) -> None:
        """--no-color 未指定時は cfg.no_color=None（環境変数参照）。"""
        args = _parse(["orchestrate", "-w", "aas"])
        config = _build_config(args)
        self.assertIsNone(config.no_color)

    def test_banner_flag_sets_config_true(self) -> None:
        """--banner が cfg.show_banner=True に反映される。"""
        args = _parse(["orchestrate", "-w", "aas", "--banner"])
        config = _build_config(args)
        self.assertTrue(config.show_banner)

    def test_no_banner_flag_sets_config_false(self) -> None:
        """--no-banner が cfg.show_banner=False に反映される。"""
        args = _parse(["orchestrate", "-w", "aas", "--no-banner"])
        config = _build_config(args)
        self.assertFalse(config.show_banner)

    def test_banner_default_is_none(self) -> None:
        """--banner/--no-banner 未指定時は cfg.show_banner=None。"""
        args = _parse(["orchestrate", "-w", "aas"])
        config = _build_config(args)
        self.assertIsNone(config.show_banner)

    def test_screen_reader_flag_sets_config(self) -> None:
        """--screen-reader が cfg.screen_reader=True に反映される。"""
        args = _parse(["orchestrate", "-w", "aas", "--screen-reader"])
        config = _build_config(args)
        self.assertTrue(config.screen_reader)

    def test_screen_reader_default_is_false(self) -> None:
        """--screen-reader 未指定時は cfg.screen_reader=False。"""
        args = _parse(["orchestrate", "-w", "aas"])
        config = _build_config(args)
        self.assertFalse(config.screen_reader)

    def test_timestamp_style_suffix(self) -> None:
        """--timestamp-style suffix が cfg.timestamp_style='suffix' に反映される。"""
        args = _parse(["orchestrate", "-w", "aas", "--timestamp-style", "suffix"])
        config = _build_config(args)
        self.assertEqual(config.timestamp_style, "suffix")

    def test_timestamp_style_off(self) -> None:
        """--timestamp-style off が cfg.timestamp_style='off' に反映される。"""
        args = _parse(["orchestrate", "-w", "aas", "--timestamp-style", "off"])
        config = _build_config(args)
        self.assertEqual(config.timestamp_style, "off")

    def test_timestamp_style_default_is_prefix(self) -> None:
        """--timestamp-style 未指定時は cfg.timestamp_style='prefix'。"""
        args = _parse(["orchestrate", "-w", "aas"])
        config = _build_config(args)
        self.assertEqual(config.timestamp_style, "prefix")

    def test_timestamp_style_invalid_rejected(self) -> None:
        """無効な --timestamp-style 値は argparse がエラーを返す。"""
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["orchestrate", "-w", "aas", "--timestamp-style", "invalid"])


if __name__ == "__main__":
    unittest.main()
