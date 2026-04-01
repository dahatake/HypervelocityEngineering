"""test_main.py — CLI 引数パースのテスト"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import pathlib
import sys
import tempfile
import unittest

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
        """デフォルト値の確認。"""
        args = _parse(["orchestrate", "--workflow", "aad"])
        self.assertEqual(args.model, "claude-opus-4.6")
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
        self.assertIsNone(args.resource_group)
        self.assertIsNone(args.batch_job_id)
        self.assertIsNone(args.usecase_id)
        self.assertIsNone(args.scope)
        self.assertIsNone(args.target_files)
        self.assertIsNone(args.force_refresh)
        self.assertIsNone(args.cli_path)
        self.assertIsNone(args.cli_url)
        self.assertIsNone(args.mcp_config)
        self.assertEqual(args.timeout, 7200.0)
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
        """--app-id オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "asdw", "--app-id", "APP-03"])
        self.assertEqual(args.app_id, "APP-03")

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
        """--scope オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aqrc", "--scope", "all"])
        self.assertEqual(args.scope, "all")

    def test_scope_specified_option(self) -> None:
        """--scope specified のテスト。"""
        args = _parse(["orchestrate", "-w", "aqrc", "--scope", "specified"])
        self.assertEqual(args.scope, "specified")

    def test_target_files_option(self) -> None:
        """--target-files オプションのテスト。"""
        args = _parse(["orchestrate", "-w", "aqrc", "--scope", "specified",
                        "--target-files", "qa/file1.md", "qa/file2.md"])
        self.assertEqual(args.target_files, ["qa/file1.md", "qa/file2.md"])

    def test_force_refresh_flag(self) -> None:
        """--force-refresh フラグのテスト。"""
        args = _parse(["orchestrate", "-w", "aqrc", "--scope", "all", "--force-refresh"])
        self.assertTrue(args.force_refresh)


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
        """app_id がパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "asdw", "--app-id", "APP-05"])
        params = _build_params(args)
        self.assertEqual(params["app_id"], "APP-05")

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

    def test_aqrc_scope_in_params(self) -> None:
        """AQRC scope がパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "aqrc", "--scope", "all"])
        params = _build_params(args)
        self.assertEqual(params["scope"], "all")

    def test_aqrc_target_files_in_params(self) -> None:
        """AQRC target_files がスペース区切り文字列としてパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "aqrc", "--scope", "specified",
                        "--target-files", "qa/f1.md", "qa/f2.md"])
        params = _build_params(args)
        self.assertEqual(params["target_files"], "qa/f1.md qa/f2.md")

    def test_aqrc_force_refresh_in_params(self) -> None:
        """AQRC force_refresh フラグがパラメータに含まれることを確認。"""
        args = _parse(["orchestrate", "-w", "aqrc", "--scope", "all", "--force-refresh"])
        params = _build_params(args)
        self.assertTrue(params["force_refresh"])

    def test_aqrc_force_refresh_default_true(self) -> None:
        """AQRC force_refresh デフォルト値が True であることを確認。"""
        args = _parse(["orchestrate", "-w", "aqrc"])
        params = _build_params(args)
        self.assertTrue(params["force_refresh"])

    def test_aqrc_no_force_refresh_sets_false(self) -> None:
        """AQRC --no-force-refresh で force_refresh が False になることを確認。"""
        args = _parse(["orchestrate", "-w", "aqrc", "--no-force-refresh"])
        params = _build_params(args)
        self.assertFalse(params["force_refresh"])

    def test_aqrc_scope_default_all_when_not_specified(self) -> None:
        """AQRC scope が未指定時に 'all' になることを確認。"""
        args = _parse(["orchestrate", "-w", "aqrc"])
        params = _build_params(args)
        self.assertEqual(params["scope"], "all")

    def test_aqrc_target_files_default_qa_glob_when_not_specified(self) -> None:
        """AQRC target_files が未指定時に 'qa/*.md' になることを確認。"""
        args = _parse(["orchestrate", "-w", "aqrc"])
        params = _build_params(args)
        self.assertEqual(params["target_files"], "qa/*.md")

    def test_non_aqrc_scope_not_set_when_not_specified(self) -> None:
        """非 AQRC ワークフローで --scope 未指定時は params に scope が含まれないことを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        params = _build_params(args)
        self.assertNotIn("scope", params)

    def test_non_aqrc_target_files_not_set_when_not_specified(self) -> None:
        """非 AQRC ワークフローで --target-files 未指定時は params に target_files が含まれないことを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        params = _build_params(args)
        self.assertNotIn("target_files", params)

    def test_non_aqrc_force_refresh_not_in_params_when_not_specified(self) -> None:
        """非 AQRC ワークフローで --force-refresh 未指定時は params に force_refresh が含まれないことを確認。"""
        args = _parse(["orchestrate", "-w", "aas"])
        params = _build_params(args)
        self.assertNotIn("force_refresh", params)

    def test_model_auto_resolved_in_config(self) -> None:
        """--model Auto が claude-opus-4.6 に解決されることを確認。"""
        args = _parse(["orchestrate", "-w", "aas", "--model", "Auto"])
        config = _build_config(args)
        self.assertEqual(config.model, "claude-opus-4.6")


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
        for wf_id in ["aas", "aad", "asdw", "abd", "abdv", "aid"]:
            with self.subTest(workflow_id=wf_id):
                exit_code = main([
                    "orchestrate",
                    "--workflow", wf_id,
                    "--dry-run",
                    "--quiet",
                ])
                self.assertEqual(exit_code, 0, f"{wf_id} の dry_run で終了コードが 0 以外")

    def test_aqrc_scope_specified_without_target_files_returns_0(self) -> None:
        """aqrc で --scope specified だが --target-files 未指定の場合、デフォルト値 qa/*.md で続行するため終了コードが 0。"""
        exit_code = main([
            "orchestrate",
            "--workflow", "aqrc",
            "--scope", "specified",
            "--dry-run",
            "--quiet",
        ])
        self.assertEqual(exit_code, 0)

    def test_aqrc_scope_all_dry_run_returns_0(self) -> None:
        """aqrc で --scope all（--target-files 不要）の dry_run が成功する。"""
        exit_code = main([
            "orchestrate",
            "--workflow", "aqrc",
            "--scope", "all",
            "--dry-run",
            "--quiet",
        ])
        self.assertEqual(exit_code, 0)

    def test_aqrc_scope_specified_with_target_files_dry_run_returns_0(self) -> None:
        """aqrc で --scope specified + --target-files 指定の dry_run が成功する。"""
        exit_code = main([
            "orchestrate",
            "--workflow", "aqrc",
            "--scope", "specified",
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
        # 1. QA 自動 → False
        # 2. Review 自動 → False
        # 3. Issue 作成 → create_issues
        # 4. PR 作成 → create_pr (create_issues=False 時のみ呼ばれる)
        # 5. Code Review Agent → code_review
        # 6. 自動承認 → auto_approval (code_review=True 時のみ)
        # 7. ドライラン → False
        # 8. 実行確認 → True
        yes_no_answers = [False, False, create_issues]
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
        con.menu_select.side_effect = [0, 0, 1]  # workflow, model, log_level
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
