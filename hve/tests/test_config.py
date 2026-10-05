"""test_config.py — SDKConfig のデフォルト値テスト"""

from __future__ import annotations

import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    DEFAULT_MODEL,
    MODEL_AUTO_VALUE,
    MODEL_AUTO_WIRE_VALUE,
    MODEL_CHOICES,
    SDKConfig,
    normalize_model,
    to_wire_model,
)


class TestSDKConfigDefaults(unittest.TestCase):
    """SDKConfig のデフォルト値を検証する。"""

    def setUp(self) -> None:
        self.cfg = SDKConfig()

    def test_model_default(self) -> None:
        self.assertEqual(self.cfg.model, "claude-opus-5.5")

    def test_default_model_is_opus_5_5(self) -> None:
        self.assertEqual(SDKConfig().model, "claude-opus-5.5")

    def test_model_choices_contains_both_46_and_47(self) -> None:
        self.assertNotIn("claude-opus-4-7", MODEL_CHOICES)
        self.assertIn("claude-opus-5.5", MODEL_CHOICES)
        self.assertIn("claude-opus-4.7", MODEL_CHOICES)
        self.assertIn("claude-opus-4.6", MODEL_CHOICES)

    def test_model_choices_contains_gpt_5_5(self) -> None:
        self.assertIn("gpt-5.5", MODEL_CHOICES)

    def test_model_choices_gpt_5_5_before_claude(self) -> None:
        self.assertLess(MODEL_CHOICES.index("claude-opus-4.7"), MODEL_CHOICES.index("gpt-5.5"))

    def test_default_model_constant(self) -> None:
        self.assertEqual(DEFAULT_MODEL, "claude-opus-5.5")

    def test_normalize_model_current(self) -> None:
        self.assertEqual(normalize_model("claude-opus-4.7"), "claude-opus-4.7")

    def test_normalize_model_passthrough(self) -> None:
        self.assertEqual(normalize_model("gpt-5.4"), "gpt-5.4")

    def test_timeout_default(self) -> None:
        self.assertEqual(self.cfg.timeout_seconds, 21600.0)

    def test_step_timeout_default(self) -> None:
        """per-step wall-clock タイムアウトの既定は 7200 秒（2h）。"""
        self.assertEqual(self.cfg.step_timeout_seconds, 7200.0)

    def test_step_timeout_zero_normalized_to_none(self) -> None:
        """0 は無効化（None）に正規化される。"""
        self.assertIsNone(SDKConfig(step_timeout_seconds=0).step_timeout_seconds)

    def test_step_timeout_negative_normalized_to_none(self) -> None:
        """負値は無効化（None）に正規化される。"""
        self.assertIsNone(SDKConfig(step_timeout_seconds=-5).step_timeout_seconds)

    def test_step_timeout_none_stays_none(self) -> None:
        """None は None のまま（無効）。"""
        self.assertIsNone(SDKConfig(step_timeout_seconds=None).step_timeout_seconds)

    def test_step_timeout_valid_value_passthrough(self) -> None:
        """正の値は float として保持される。"""
        self.assertEqual(SDKConfig(step_timeout_seconds=120).step_timeout_seconds, 120.0)

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

    def test_delete_local_merged_branch_default(self) -> None:
        """FR-CLI-34: マージ済みローカル作業ブランチ削除は既定で有効。"""
        self.assertTrue(self.cfg.delete_local_merged_branch)

    def test_verbose_default(self) -> None:
        self.assertTrue(self.cfg.verbose)

    def test_quiet_default(self) -> None:
        self.assertFalse(self.cfg.quiet)

    def test_mcp_servers_default(self) -> None:
        self.assertNotIn("mcp_servers", vars(self.cfg))

    def test_legacy_mcp_servers_input_is_not_retained_at_runtime(self) -> None:
        cfg = SDKConfig(mcp_servers={"legacy": {"command": "forbidden"}})

        self.assertNotIn("mcp_servers", vars(cfg))

    def test_legacy_mcp_servers_discard_is_documented(self) -> None:
        class_doc = SDKConfig.__doc__ or ""
        post_init_doc = SDKConfig.__post_init__.__doc__ or ""

        self.assertIn("mcp_servers", class_doc)
        self.assertIn("required_mcp_servers", post_init_doc)
        self.assertIn("破棄", post_init_doc)

    def test_dry_run_default(self) -> None:
        self.assertFalse(self.cfg.dry_run)

    def test_log_level_default(self) -> None:
        self.assertEqual(self.cfg.log_level, "error")

    def test_workiq_default_disabled(self) -> None:
        self.assertFalse(self.cfg.workiq_enabled)
        self.assertEqual(self.cfg.knowledge_sources, [])
        self.assertEqual(self.cfg.effective_knowledge_sources(), [])

    def test_effective_knowledge_sources_order_and_dedup(self) -> None:
        cfg = SDKConfig(workiq_enabled=True, knowledge_sources=["docs-mcp", "workiq"])
        self.assertEqual(cfg.effective_knowledge_sources("crm", "docs-mcp"), ["workiq", "docs-mcp", "crm"])

    def test_show_reasoning_default_true(self) -> None:
        self.assertTrue(self.cfg.show_reasoning)

    def test_removed_workiq_runtime_fields_are_rejected(self) -> None:
        for field_name, value in (
            ("workiq_tenant_id", "tenant"),
            ("workiq_request_timeout", 300.0),
            ("workiq_prompt_review", "review"),
            ("workiq_qa_enabled", True),
            ("workiq_akm_review_enabled", True),
            ("workiq_prompt_qa", "qa"),
            ("workiq_prompt_km", "km"),
            ("workiq_draft_mode", True),
            ("workiq_draft_output_dir", "qa"),
            ("workiq_per_question_timeout", 1200.0),
            ("workiq_max_draft_questions", 10),
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaises(TypeError):
                    SDKConfig(**{field_name: value})

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

    def test_from_env_uses_hve_run_id(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["HVE_RUN_ID"] = "20260605T123456-abcdef"
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.run_id, "20260605T123456-abcdef")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_reads_knowledge_source_options(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["WORKIQ_ENABLED"] = "true"
            os.environ["HVE_KNOWLEDGE_SOURCES"] = "docs-mcp, crm,,bad name"
            os.environ["WORKIQ_PROMPT_QA"] = "qa"
            os.environ["WORKIQ_DRAFT_MODE"] = "true"
            cfg = SDKConfig.from_env()
            self.assertTrue(cfg.workiq_enabled)
            self.assertEqual(cfg.knowledge_sources, ["docs-mcp", "crm"])
            self.assertEqual(cfg.effective_knowledge_sources(), ["workiq", "docs-mcp", "crm"])
            self.assertFalse(hasattr(cfg, "workiq_prompt_qa"))
            self.assertFalse(hasattr(cfg, "workiq_draft_mode"))
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_ignores_removed_workiq_runtime_environment(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["WORKIQ_TENANT_ID"] = "tenant-001"
            os.environ["WORKIQ_REQUEST_TIMEOUT"] = "600"
            os.environ["WORKIQ_PROMPT_REVIEW"] = "review"
            cfg = SDKConfig.from_env()
            self.assertFalse(hasattr(cfg, "workiq_tenant_id"))
            self.assertFalse(hasattr(cfg, "workiq_request_timeout"))
            self.assertFalse(hasattr(cfg, "workiq_prompt_review"))
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_uses_default_model_when_model_unset(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ.pop("MODEL", None)
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.model, DEFAULT_MODEL)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_from_env_uses_default_model_when_model_empty(self) -> None:
        env_backup = os.environ.copy()
        try:
            os.environ["MODEL"] = ""
            cfg = SDKConfig.from_env()
            self.assertEqual(cfg.model, DEFAULT_MODEL)
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

    def test_apply_review_improvements_disabled_by_zero(self) -> None:
        os.environ["HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN"] = "0"
        cfg = SDKConfig.from_env()
        self.assertFalse(cfg.apply_review_improvements_to_main)

    def test_apply_review_improvements_enabled_by_yes(self) -> None:
        os.environ["HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN"] = "yes"
        cfg = SDKConfig.from_env()
        self.assertTrue(cfg.apply_review_improvements_to_main)

    def test_apply_review_improvements_disabled_by_empty_string(self) -> None:
        os.environ["HVE_APPLY_REVIEW_IMPROVEMENTS_TO_MAIN"] = ""
        cfg = SDKConfig.from_env()
        self.assertFalse(cfg.apply_review_improvements_to_main)


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

    def test_normalize_model_with_warning_accepts_live_catalog_model(self) -> None:
        """FR-MODEL-03（v3.30）: SDK の model catalog（キャッシュ）にある ID は Auto へ丸めない。"""
        import warnings
        from unittest import mock
        import config as config_mod  # type: ignore

        with mock.patch.object(config_mod, "_catalog_model_ids", return_value=frozenset({"gpt-6-luna"})):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                self.assertEqual(self._normalize("gpt-6-luna"), "gpt-6-luna")
                self.assertEqual(self._normalize("claude-sonnet-4.6"), MODEL_AUTO_VALUE)
        self.assertEqual(len(w), 1)

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


# ---------------------------------------------------------------------------
# to_wire_model: hve 内部センチネル "Auto" → SDK wire 値 "auto" の変換
# ---------------------------------------------------------------------------

class TestToWireModel(unittest.TestCase):
    """to_wire_model の挙動を検証する。"""

    def test_auto_sentinel_converted_to_wire_value(self) -> None:
        """MODEL_AUTO_VALUE ("Auto") → MODEL_AUTO_WIRE_VALUE ("auto")。"""
        self.assertEqual(to_wire_model(MODEL_AUTO_VALUE), MODEL_AUTO_WIRE_VALUE)

    def test_explicit_model_passthrough(self) -> None:
        """明示モデル ID はそのまま返す。"""
        self.assertEqual(to_wire_model("claude-opus-4.7"), "claude-opus-4.7")
        self.assertEqual(to_wire_model("gpt-5.4"), "gpt-5.4")

    def test_none_returns_none(self) -> None:
        """None → None（呼び出し側で model キーを payload から省略）。"""
        self.assertIsNone(to_wire_model(None))

    def test_empty_string_returns_none(self) -> None:
        """空文字 → None（呼び出し側で model キーを payload から省略）。"""
        self.assertIsNone(to_wire_model(""))

    def test_wire_value_constant_is_auto(self) -> None:
        """MODEL_AUTO_WIRE_VALUE は SDK list_models() が返す正規 ID "auto"。"""
        self.assertEqual(MODEL_AUTO_WIRE_VALUE, "auto")

    def test_internal_sentinel_constant_is_capitalized_auto(self) -> None:
        """MODEL_AUTO_VALUE は UI / 既存 Issue 等で使われる大文字 "Auto"。"""
        self.assertEqual(MODEL_AUTO_VALUE, "Auto")


# ---------------------------------------------------------------------------
# T-20: HVE_AVAILABLE_TOOLS / HVE_EXCLUDED_TOOLS env exposure
# ---------------------------------------------------------------------------

class TestSDKConfigToolListFromEnv(unittest.TestCase):
    """available_tools / excluded_tools が環境変数から正しくロードされることを検証する。"""

    def test_unset_returns_none(self) -> None:
        import os
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            for k in ("HVE_AVAILABLE_TOOLS", "HVE_EXCLUDED_TOOLS"):
                os.environ.pop(k, None)
            cfg = SDKConfig.from_env()
        self.assertIsNone(cfg.available_tools)
        self.assertIsNone(cfg.excluded_tools)

    def test_empty_returns_none(self) -> None:
        import os
        with unittest.mock.patch.dict(
            os.environ, {"HVE_AVAILABLE_TOOLS": "", "HVE_EXCLUDED_TOOLS": "   "}
        ):
            cfg = SDKConfig.from_env()
        self.assertIsNone(cfg.available_tools)
        self.assertIsNone(cfg.excluded_tools)

    def test_single_tool(self) -> None:
        import os
        with unittest.mock.patch.dict(os.environ, {"HVE_AVAILABLE_TOOLS": "bash"}):
            cfg = SDKConfig.from_env()
        self.assertEqual(cfg.available_tools, ["bash"])

    def test_csv_and_whitespace(self) -> None:
        import os
        with unittest.mock.patch.dict(
            os.environ,
            {
                "HVE_AVAILABLE_TOOLS": "str_replace_editor, bash glob",
                "HVE_EXCLUDED_TOOLS": "web_search,fetch",
            },
        ):
            cfg = SDKConfig.from_env()
        self.assertEqual(cfg.available_tools, ["str_replace_editor", "bash", "glob"])
        self.assertEqual(cfg.excluded_tools, ["web_search", "fetch"])


# ---------------------------------------------------------------------------
# FR-MODEL-04: SDK tool_search (ツール定義の遅延ロード) の設定
# ---------------------------------------------------------------------------

class TestSDKConfigToolSearch(unittest.TestCase):
    """tool_search の既定値と HVE_TOOL_SEARCH env 読み取りを検証する。"""

    def test_default_is_true(self) -> None:
        """FR-MODEL-04: 既定は有効。"""
        self.assertTrue(SDKConfig().tool_search)

    def test_env_unset_is_true(self) -> None:
        """FR-MODEL-04: env 未指定でも有効。"""
        import os
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HVE_TOOL_SEARCH", None)
            cfg = SDKConfig.from_env()
        self.assertTrue(cfg.tool_search)

    def test_env_truthy_values(self) -> None:
        import os
        for raw in ("1", "true", "True", "yes"):
            with self.subTest(raw=raw):
                with unittest.mock.patch.dict(os.environ, {"HVE_TOOL_SEARCH": raw}):
                    cfg = SDKConfig.from_env()
                self.assertTrue(cfg.tool_search)

    def test_env_falsy_values(self) -> None:
        """FR-MODEL-06: 明示的な無効化は既定有効化で上書きされない。"""
        import os
        for raw in ("0", "false", "no", ""):
            with self.subTest(raw=raw):
                with unittest.mock.patch.dict(os.environ, {"HVE_TOOL_SEARCH": raw}):
                    cfg = SDKConfig.from_env()
                self.assertFalse(cfg.tool_search)


class TestIssueNumber(unittest.TestCase):
    """FR-GUI-25: 既存 Issue へ連携するための issue_number を検証する。"""

    def test_default_is_none(self) -> None:
        """未指定時は None（Root Issue を新規作成する既存挙動）。"""
        self.assertIsNone(SDKConfig().issue_number)

    def test_holds_explicit_value(self) -> None:
        self.assertEqual(SDKConfig(issue_number=1234).issue_number, 1234)

    def test_is_independent_from_create_issues(self) -> None:
        """create_issues の既定値を変えないこと。"""
        cfg = SDKConfig(issue_number=7)
        self.assertFalse(cfg.create_issues)
        self.assertFalse(cfg.create_pr)


if __name__ == "__main__":
    unittest.main()
