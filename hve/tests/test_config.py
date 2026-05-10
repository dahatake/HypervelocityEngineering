"""test_config.py — SDKConfig のデフォルト値テスト"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    DEFAULT_MODEL,
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
        self.assertNotIn("claude-opus-4-7", MODEL_CHOICES)
        self.assertIn("claude-opus-4.7", MODEL_CHOICES)
        self.assertIn("claude-opus-4.6", MODEL_CHOICES)

    def test_model_choices_contains_gpt_5_5(self) -> None:
        self.assertIn("gpt-5.5", MODEL_CHOICES)

    def test_model_choices_gpt_5_5_before_claude(self) -> None:
        self.assertLess(MODEL_CHOICES.index("claude-opus-4.7"), MODEL_CHOICES.index("gpt-5.5"))

    def test_default_model_constant(self) -> None:
        self.assertEqual(DEFAULT_MODEL, "claude-opus-4.7")

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
        self.assertEqual(self.cfg.workiq_per_question_timeout, 1200.0)
        self.assertEqual(self.cfg.workiq_max_draft_questions, 10)  # Wave 2: 30→10 に削減

    def test_auto_self_improve_default_false(self) -> None:
        self.assertFalse(self.cfg.auto_self_improve)

    def test_max_diff_chars_default(self) -> None:
        self.assertEqual(self.cfg.max_diff_chars, 80_000)

    def test_context_injection_max_chars_default(self) -> None:
        self.assertEqual(self.cfg.context_injection_max_chars, 20_000)

    def test_reuse_context_filtering_none_falls_back_to_true(self) -> None:
        cfg = SDKConfig(reuse_context_filtering=None)
        self.assertTrue(cfg.reuse_context_filtering)


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

    def test_from_env_workiq_per_question_timeout_default_is_1200(self) -> None:
        """環境変数 WORKIQ_PER_QUESTION_TIMEOUT 未設定時の既定値が 1200.0（20 分）であること。"""
        env_backup = os.environ.copy()
        try:
            os.environ.pop("WORKIQ_PER_QUESTION_TIMEOUT", None)
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.workiq_per_question_timeout, 1200.0)
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

    def test_from_env_hve_max_diff_chars(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["HVE_MAX_DIFF_CHARS"] = "12345"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.max_diff_chars, 12345)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_hve_max_diff_chars_default(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ.pop("HVE_MAX_DIFF_CHARS", None)
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.max_diff_chars, 80_000)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_hve_max_diff_chars_invalid_fallback(self) -> None:
        """無効値（非数値）の場合は 80_000 にフォールバックすること。"""
        env_backup = os.environ.copy()
        try:
            os.environ["HVE_MAX_DIFF_CHARS"] = "not_a_number"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.max_diff_chars, 80_000)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_hve_context_injection_max_chars(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["HVE_CONTEXT_INJECTION_MAX_CHARS"] = "12345"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.context_injection_max_chars, 12345)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_hve_context_injection_max_chars_invalid_fallback(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["HVE_CONTEXT_INJECTION_MAX_CHARS"] = "invalid"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.context_injection_max_chars, 20_000)
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


class TestSDKConfigModelOverride(unittest.TestCase):
    """HVE_MODEL_OVERRIDE の動作を検証する。"""

    def setUp(self) -> None:
        self._backup = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._backup)

    def test_model_override_default_is_none(self) -> None:
        self.assertIsNone(SDKConfig().model_override)

    def test_model_override_applies_when_set(self) -> None:
        """HVE_MODEL_OVERRIDE が設定された場合、model フィールドが上書きされる。"""
        os.environ["HVE_MODEL_OVERRIDE"] = "gpt-5.4"
        cfg = SDKConfig.from_env()
        self.assertEqual(cfg.model, "gpt-5.4")
        self.assertEqual(cfg.model_override, "gpt-5.4")

    def test_model_override_takes_precedence_over_model_env(self) -> None:
        """HVE_MODEL_OVERRIDE は MODEL 環境変数より優先される。"""
        os.environ["MODEL"] = "claude-opus-4.7"
        os.environ["HVE_MODEL_OVERRIDE"] = "gpt-5.5"
        cfg = SDKConfig.from_env()
        self.assertEqual(cfg.model, "gpt-5.5")

    def test_model_override_takes_precedence_over_auto(self) -> None:
        """HVE_MODEL_OVERRIDE は Auto（未指定）より優先される。"""
        os.environ.pop("MODEL", None)
        os.environ["HVE_MODEL_OVERRIDE"] = "claude-opus-4.7"
        cfg = SDKConfig.from_env()
        self.assertEqual(cfg.model, "claude-opus-4.7")

    def test_model_override_unset_does_not_affect_model(self) -> None:
        """HVE_MODEL_OVERRIDE 未設定時は通常の MODEL 環境変数が使われる。"""
        os.environ.pop("HVE_MODEL_OVERRIDE", None)
        os.environ["MODEL"] = "claude-opus-4.6"
        cfg = SDKConfig.from_env()
        self.assertEqual(cfg.model, "claude-opus-4.6")
        self.assertIsNone(cfg.model_override)

    def test_model_override_empty_string_ignored(self) -> None:
        """HVE_MODEL_OVERRIDE が空文字の場合は無視される。"""
        os.environ["HVE_MODEL_OVERRIDE"] = ""
        os.environ["MODEL"] = "claude-opus-4.7"
        cfg = SDKConfig.from_env()
        self.assertEqual(cfg.model, "claude-opus-4.7")


class TestSDKConfigArtifactImprovementDefaults(unittest.TestCase):
    """apply_*_improvements_to_main フィールドのデフォルト値を検証する。"""

    def setUp(self) -> None:
        self.cfg = SDKConfig()

    def test_apply_qa_improvements_to_main_default_false(self) -> None:
        self.assertFalse(self.cfg.apply_qa_improvements_to_main)

    def test_apply_review_improvements_to_main_default_true(self) -> None:
        self.assertTrue(self.cfg.apply_review_improvements_to_main)

    def test_apply_self_improve_to_main_default_true(self) -> None:
        self.assertTrue(self.cfg.apply_self_improve_to_main)


class TestSDKConfigArtifactImprovementFromEnv(unittest.TestCase):
    """apply_*_improvements_to_main 環境変数読み取りの検証。"""

    def setUp(self) -> None:
        self._backup = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._backup)

    def test_apply_qa_improvements_enabled_by_env(self) -> None:
        os.environ["HVE_APPLY_QA_IMPROVEMENTS_TO_MAIN"] = "true"
        cfg = SDKConfig.from_env()
        self.assertTrue(cfg.apply_qa_improvements_to_main)

    def test_apply_qa_improvements_default_false_when_unset(self) -> None:
        os.environ.pop("HVE_APPLY_QA_IMPROVEMENTS_TO_MAIN", None)
        cfg = SDKConfig.from_env()
        self.assertFalse(cfg.apply_qa_improvements_to_main)

    def test_apply_review_improvements_disabled_by_env(self) -> None:
        os.environ["HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN"] = "false"
        cfg = SDKConfig.from_env()
        self.assertFalse(cfg.apply_review_improvements_to_main)

    def test_apply_review_improvements_default_true_when_unset(self) -> None:
        os.environ.pop("HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN", None)
        cfg = SDKConfig.from_env()
        self.assertTrue(cfg.apply_review_improvements_to_main)

    def test_apply_self_improve_disabled_by_env(self) -> None:
        os.environ["HVE_APPLY_SELF_IMPROVE_TO_MAIN"] = "false"
        cfg = SDKConfig.from_env()
        self.assertFalse(cfg.apply_self_improve_to_main)

    def test_apply_self_improve_default_true_when_unset(self) -> None:
        os.environ.pop("HVE_APPLY_SELF_IMPROVE_TO_MAIN", None)
        cfg = SDKConfig.from_env()
        self.assertTrue(cfg.apply_self_improve_to_main)

    def test_apply_review_improvements_disabled_by_zero(self) -> None:
        os.environ["HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN"] = "0"
        cfg = SDKConfig.from_env()
        self.assertFalse(cfg.apply_review_improvements_to_main)

    def test_apply_self_improve_disabled_by_no(self) -> None:
        os.environ["HVE_APPLY_SELF_IMPROVE_TO_MAIN"] = "no"
        cfg = SDKConfig.from_env()
        self.assertFalse(cfg.apply_self_improve_to_main)

    def test_apply_review_improvements_enabled_by_yes(self) -> None:
        os.environ["HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN"] = "yes"
        cfg = SDKConfig.from_env()
        self.assertTrue(cfg.apply_review_improvements_to_main)

    def test_apply_review_improvements_disabled_by_empty_string(self) -> None:
        os.environ["HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN"] = ""
        cfg = SDKConfig.from_env()
        self.assertFalse(cfg.apply_review_improvements_to_main)


class TestSelfImproveWorkflowSdkConfig(unittest.TestCase):
    """Issue Template 起動の self-improve ジョブで SDKConfig.from_env() を使う際の
    github_token / cli_path / model 等が正しく渡されることを検証する。"""

    def setUp(self):
        self._env_backup = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_from_env_provides_github_token_for_self_improve(self) -> None:
        """GH_TOKEN が set されている場合、from_env() が github_token を取得すること。"""
        os.environ["GH_TOKEN"] = "ghp_test_token"
        os.environ.pop("GITHUB_TOKEN", None)
        cfg = SDKConfig.from_env()
        cfg.auto_self_improve = True
        cfg.self_improve_max_iterations = 3
        self.assertEqual(cfg.github_token, "ghp_test_token")
        self.assertTrue(cfg.auto_self_improve)
        self.assertEqual(cfg.self_improve_max_iterations, 3)

    def test_from_env_provides_cli_path_for_self_improve(self) -> None:
        """COPILOT_CLI_PATH が set されている場合、from_env() が cli_path を取得すること。"""
        os.environ["COPILOT_CLI_PATH"] = "/usr/local/bin/copilot"
        cfg = SDKConfig.from_env()
        cfg.auto_self_improve = True
        self.assertEqual(cfg.cli_path, "/usr/local/bin/copilot")

    def test_from_env_provides_model_for_self_improve(self) -> None:
        """MODEL が set されている場合、from_env() が model を取得すること。"""
        os.environ["MODEL"] = "claude-opus-4.6"
        cfg = SDKConfig.from_env()
        cfg.auto_self_improve = True
        self.assertEqual(cfg.model, "claude-opus-4.6")

    def test_from_env_with_quality_threshold_override(self) -> None:
        """from_env() + quality_threshold 上書きが正しく動作すること。"""
        os.environ["GH_TOKEN"] = "ghp_test"
        cfg = SDKConfig.from_env()
        cfg.auto_self_improve = True
        cfg.self_improve_max_iterations = 5
        cfg.self_improve_quality_threshold = 90
        self.assertEqual(cfg.self_improve_quality_threshold, 90)
        self.assertEqual(cfg.self_improve_max_iterations, 5)
        self.assertEqual(cfg.github_token, "ghp_test")


class TestNormalizeModelWithWarning(unittest.TestCase):
    """_normalize_model_with_warning の動作を検証する（Phase 9+ 追加）。"""

    def setUp(self) -> None:
        from config import _normalize_model_with_warning  # type: ignore
        self._normalize = _normalize_model_with_warning

    def test_normalize_model_with_warning_falls_back_to_auto_for_unknown_model(self) -> None:
        """未知モデル名 → WARNING + MODEL_AUTO_VALUE を返すこと。"""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = self._normalize("claude-sonnet-4.6")
        self.assertEqual(result, MODEL_AUTO_VALUE)
        self.assertEqual(len(w), 1)
        self.assertIn("claude-sonnet-4.6", str(w[0].message))

    def test_normalize_model_with_warning_passes_through_known_model(self) -> None:
        """MODEL_CHOICES 内の値はそのまま返すこと。"""
        import warnings
        for model in MODEL_CHOICES:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = self._normalize(model)
            self.assertEqual(result, model, f"{model} should pass through")
            self.assertEqual(len(w), 0, f"{model} should not warn")

    def test_normalize_model_with_warning_passes_through_auto(self) -> None:
        """Auto はそのまま返すこと。"""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = self._normalize(MODEL_AUTO_VALUE)
        self.assertEqual(result, MODEL_AUTO_VALUE)
        self.assertEqual(len(w), 0)

    def test_post_init_falls_back_to_auto_for_legacy_claude_sonnet_4_6(self) -> None:
        """SDKConfig(model='claude-sonnet-4.6') → 後方互換でフォールバック検証。"""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = SDKConfig(model="claude-sonnet-4.6")
        self.assertEqual(cfg.model, MODEL_AUTO_VALUE)
        self.assertTrue(any("claude-sonnet-4.6" in str(warning.message) for warning in w))


if __name__ == "__main__":
    unittest.main()
