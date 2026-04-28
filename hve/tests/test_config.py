"""test_config.py — SDKConfig のデフォルト値テスト"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    DEFAULT_MODEL,
    LEGACY_MODEL_ID,
    MODEL_AUTO_VALUE,
    MODEL_CHOICES,
    SDKConfig,
    normalize_model,
)


class TestSDKConfigDefaults(unittest.TestCase):
    """SDKConfig のデフォルト値を検証する。"""

    def setUp(self) -> None:
        self.cfg = SDKConfig()

    def test_model_default(self) -> None:
        self.assertEqual(self.cfg.model, "claude-opus-4.7")

    def test_default_model_is_opus_4_7(self) -> None:
        self.assertEqual(SDKConfig().model, "claude-opus-4.7")

    def test_model_choices_contains_both_46_and_47(self) -> None:
        self.assertNotIn(LEGACY_MODEL_ID, MODEL_CHOICES)
        self.assertIn("claude-opus-4.7", MODEL_CHOICES)
        self.assertIn("claude-opus-4.6", MODEL_CHOICES)

    def test_model_choices_contains_gpt_5_5(self) -> None:
        self.assertIn("gpt-5.5", MODEL_CHOICES)

    def test_model_choices_gpt_5_5_before_claude(self) -> None:
        self.assertLess(MODEL_CHOICES.index("gpt-5.5"), MODEL_CHOICES.index("claude-opus-4.7"))

    def test_default_model_constant(self) -> None:
        self.assertEqual(DEFAULT_MODEL, "claude-opus-4.7")

    def test_normalize_model_legacy(self) -> None:
        self.assertEqual(normalize_model(LEGACY_MODEL_ID), "claude-opus-4.7")

    def test_normalize_model_current(self) -> None:
        self.assertEqual(normalize_model("claude-opus-4.7"), "claude-opus-4.7")

    def test_normalize_model_passthrough(self) -> None:
        self.assertEqual(normalize_model("gpt-5.4"), "gpt-5.4")

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

    def test_workiq_default_disabled(self) -> None:
        self.assertFalse(self.cfg.workiq_enabled)
        self.assertFalse(self.cfg.is_workiq_qa_enabled())
        self.assertFalse(self.cfg.is_workiq_akm_review_enabled())

    def test_workiq_explicit_flags_override_legacy(self) -> None:
        cfg = SDKConfig(
            workiq_enabled=True,
            workiq_qa_enabled=False,
            workiq_akm_review_enabled=True,
        )
        self.assertFalse(cfg.is_workiq_qa_enabled())
        self.assertTrue(cfg.is_workiq_akm_review_enabled())

    def test_workiq_legacy_flag_enables_both_explicit_scopes_by_default(self) -> None:
        cfg = SDKConfig(workiq_enabled=True)
        self.assertTrue(cfg.is_workiq_qa_enabled())
        self.assertTrue(cfg.is_workiq_akm_review_enabled())

    def test_show_reasoning_default_true(self) -> None:
        self.assertTrue(self.cfg.show_reasoning)

    def test_workiq_draft_defaults(self) -> None:
        self.assertFalse(self.cfg.workiq_draft_mode)
        self.assertEqual(self.cfg.workiq_draft_output_dir, "qa")
        self.assertEqual(self.cfg.workiq_per_question_timeout, 600.0)
        self.assertEqual(self.cfg.workiq_max_draft_questions, 30)

    def test_auto_self_improve_default_false(self) -> None:
        self.assertFalse(self.cfg.auto_self_improve)


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

    def test_from_env_reads_workiq_options(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["WORKIQ_ENABLED"] = "true"
            os.environ["WORKIQ_QA_ENABLED"] = "false"
            os.environ["WORKIQ_AKM_REVIEW_ENABLED"] = "true"
            os.environ["WORKIQ_TENANT_ID"] = "tenant-001"
            os.environ["WORKIQ_PROMPT_QA"] = "qa"
            os.environ["WORKIQ_PROMPT_KM"] = "km"
            os.environ["WORKIQ_PROMPT_REVIEW"] = "review"
            os.environ["WORKIQ_DRAFT_MODE"] = "true"
            os.environ["WORKIQ_DRAFT_OUTPUT_DIR"] = "qa-drafts"
            os.environ["WORKIQ_PER_QUESTION_TIMEOUT"] = "45"
            os.environ["WORKIQ_MAX_DRAFT_QUESTIONS"] = "12"
            cfg = SDKConfig.from_env()
            self.assertTrue(cfg.workiq_enabled)
            self.assertFalse(cfg.is_workiq_qa_enabled())
            self.assertTrue(cfg.is_workiq_akm_review_enabled())
            self.assertEqual(cfg.workiq_tenant_id, "tenant-001")
            self.assertEqual(cfg.workiq_prompt_qa, "qa")
            self.assertEqual(cfg.workiq_prompt_km, "km")
            self.assertEqual(cfg.workiq_prompt_review, "review")
            self.assertTrue(cfg.workiq_draft_mode)
            self.assertEqual(cfg.workiq_draft_output_dir, "qa-drafts")
            self.assertEqual(cfg.workiq_per_question_timeout, 45.0)
            self.assertEqual(cfg.workiq_max_draft_questions, 12)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_uses_auto_when_model_unset(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ.pop("MODEL", None)
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.model, MODEL_AUTO_VALUE)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_uses_auto_when_model_empty(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["MODEL"] = ""
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.model, MODEL_AUTO_VALUE)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_hve_auto_self_improve_true(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["HVE_AUTO_SELF_IMPROVE"] = "true"
            cfg = SDKConfig.from_env()
            self.assertTrue(cfg.auto_self_improve)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_reads_show_reasoning(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["SHOW_REASONING"] = "false"
            cfg = SDKConfig.from_env()
            self.assertFalse(cfg.show_reasoning)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_hve_auto_self_improve_true_variants(self) -> None:
        env_backup = os.environ.copy()
        try:
            for value in ("true", "1", "yes"):
                with self.subTest(value=value):
                    os.environ["HVE_AUTO_SELF_IMPROVE"] = value
                    cfg = SDKConfig.from_env()
                    self.assertTrue(cfg.auto_self_improve)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_hve_auto_self_improve_false_variants(self) -> None:
        env_backup = os.environ.copy()
        try:
            for value in ("false", "0", "no", ""):
                with self.subTest(value=value):
                    os.environ["HVE_AUTO_SELF_IMPROVE"] = value
                    cfg = SDKConfig.from_env()
                    self.assertFalse(cfg.auto_self_improve)
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
