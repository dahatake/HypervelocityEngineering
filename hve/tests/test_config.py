"""test_config.py — SDKConfig のデフォルト値テスト"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import MODEL_CHOICES, SDKConfig


class TestSDKConfigDefaults(unittest.TestCase):
    """SDKConfig のデフォルト値を検証する。"""

    def setUp(self) -> None:
        self.cfg = SDKConfig()

    def test_model_default(self) -> None:
        self.assertEqual(self.cfg.model, "claude-opus-4-7")

    def test_default_model_is_opus_4_7(self) -> None:
        self.assertEqual(SDKConfig().model, "claude-opus-4-7")

    def test_model_choices_contains_both_46_and_47(self) -> None:
        self.assertIn("claude-opus-4-7", MODEL_CHOICES)
        self.assertIn("claude-opus-4.6", MODEL_CHOICES)

    def test_timeout_default(self) -> None:
        self.assertEqual(self.cfg.timeout_seconds, 21600.0)

    def test_review_timeout_default(self) -> None:
        self.assertEqual(self.cfg.review_timeout_seconds, 7200.0)

    def test_base_branch_default(self) -> None:
        self.assertEqual(self.cfg.base_branch, "main")

    def test_cli_path_default(self) -> None:
        self.assertIsNone(self.cfg.cli_path)

    def test_cli_url_default(self) -> None:
        self.assertIsNone(self.cfg.cli_url)

    def test_github_token_default(self) -> None:
        self.assertEqual(self.cfg.github_token, "")

    def test_repo_default(self) -> None:
        self.assertEqual(self.cfg.repo, "")

    def test_max_parallel_default(self) -> None:
        self.assertEqual(self.cfg.max_parallel, 15)

    def test_auto_qa_default(self) -> None:
        self.assertFalse(self.cfg.auto_qa)

    def test_auto_contents_review_default(self) -> None:
        self.assertFalse(self.cfg.auto_contents_review)

    def test_auto_coding_agent_review_default(self) -> None:
        self.assertFalse(self.cfg.auto_coding_agent_review)

    def test_auto_coding_agent_review_auto_approval_default(self) -> None:
        self.assertFalse(self.cfg.auto_coding_agent_review_auto_approval)

    def test_create_issues_default(self) -> None:
        self.assertFalse(self.cfg.create_issues)

    def test_create_pr_default(self) -> None:
        self.assertFalse(self.cfg.create_pr)

    def test_verbose_default(self) -> None:
        self.assertTrue(self.cfg.verbose)

    def test_quiet_default(self) -> None:
        self.assertFalse(self.cfg.quiet)

    def test_mcp_servers_default(self) -> None:
        self.assertIsNone(self.cfg.mcp_servers)

    def test_custom_agents_config_default(self) -> None:
        self.assertIsNone(self.cfg.custom_agents_config)

    def test_dry_run_default(self) -> None:
        self.assertFalse(self.cfg.dry_run)

    def test_log_level_default(self) -> None:
        self.assertEqual(self.cfg.log_level, "error")


class TestSDKConfigFromEnv(unittest.TestCase):
    """from_env() の動作を検証する。"""

    def test_from_env_uses_gh_token(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["GH_TOKEN"] = "test-token-gh"
            os.environ.pop("GITHUB_TOKEN", None)
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.github_token, "test-token-gh")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_uses_github_token_fallback(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ.pop("GH_TOKEN", None)
            os.environ["GITHUB_TOKEN"] = "test-token-github"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.github_token, "test-token-github")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_uses_repo(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["REPO"] = "owner/repo"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.repo, "owner/repo")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_uses_cli_path(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["COPILOT_CLI_PATH"] = "/usr/local/bin/copilot"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.cli_path, "/usr/local/bin/copilot")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)


class TestSDKConfigResolveToken(unittest.TestCase):
    """resolve_token() の動作を検証する。"""

    def test_resolve_returns_explicit_token(self) -> None:
        cfg = SDKConfig(github_token="explicit-token")
        self.assertEqual(cfg.resolve_token(), "explicit-token")

    def test_resolve_falls_back_to_env(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["GH_TOKEN"] = "env-token"
            cfg = SDKConfig(github_token="")
            self.assertEqual(cfg.resolve_token(), "env-token")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)


class TestSDKConfigModelResolution(unittest.TestCase):
    """レビュー/QA モデル解決の動作を検証する。"""

    def test_review_model_default_is_none(self) -> None:
        self.assertIsNone(SDKConfig().review_model)

    def test_qa_model_default_is_none(self) -> None:
        self.assertIsNone(SDKConfig().qa_model)

    def test_get_review_model_fallback(self) -> None:
        self.assertEqual(SDKConfig(model="gpt-5.4").get_review_model(), "gpt-5.4")

    def test_get_review_model_explicit(self) -> None:
        cfg = SDKConfig(model="gpt-5.4", review_model="claude-opus-4.6")
        self.assertEqual(cfg.get_review_model(), "claude-opus-4.6")

    def test_get_qa_model_fallback(self) -> None:
        self.assertEqual(SDKConfig(model="gpt-5.4").get_qa_model(), "gpt-5.4")

    def test_get_qa_model_explicit(self) -> None:
        cfg = SDKConfig(model="gpt-5.4", qa_model="claude-opus-4.6")
        self.assertEqual(cfg.get_qa_model(), "claude-opus-4.6")

    def test_from_env_reads_review_model(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["REVIEW_MODEL"] = "claude-opus-4.6"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.review_model, "claude-opus-4.6")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_reads_qa_model(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["QA_MODEL"] = "gpt-5.4"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.qa_model, "gpt-5.4")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)


if __name__ == "__main__":
    unittest.main()
