"""hve.gui.tests.test_provider_is_required — T13 (Wave 5).

各 AuthProvider の ``is_required(settings)`` の真偽パターンを網羅する。
モジュールレベル: PySide6 や copilot SDK 依存は注入しない単体テスト。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hve.gui.auth_providers import provider_is_required
from hve.gui.auth_providers.external_cli_provider import ExternalCliProvider
from hve.gui.auth_providers.github_provider import GitHubProvider
from hve.gui.auth_providers.mcp_generic_provider import McpGenericProvider
from hve.gui.auth_providers.workiq_provider import WorkIQProvider


# ---------------------------------------------------------------------------
# GitHubProvider
# ---------------------------------------------------------------------------
class TestGitHubIsRequired:
    def test_always_true_empty_settings(self) -> None:
        assert GitHubProvider().is_required({}) is True

    def test_always_true_arbitrary_settings(self) -> None:
        assert GitHubProvider().is_required({"options": {"workiq": False}}) is True

    def test_helper_returns_true(self) -> None:
        assert provider_is_required(GitHubProvider(), {}) is True


# ---------------------------------------------------------------------------
# WorkIQProvider (B1: いずれかの workiq 設定 ON / 値あり → True)
# ---------------------------------------------------------------------------
class TestWorkIQIsRequired:
    def _settings(self, **opts: object) -> dict:
        return {"options": opts}

    def test_all_off_returns_false(self) -> None:
        s = self._settings(
            workiq=False,
            workiq_akm_review="",
            workiq_akm_ingest="",
            workiq_draft=False,
            workiq_dxx="",
            workiq_draft_output_dir="",
            workiq_prompt_qa="",
            workiq_prompt_km="",
            workiq_prompt_review="",
            workiq_per_question_timeout=0.0,
        )
        assert WorkIQProvider().is_required(s) is False

    def test_workiq_master_on(self) -> None:
        assert WorkIQProvider().is_required(self._settings(workiq=True)) is True

    def test_workiq_master_on_string(self) -> None:
        assert WorkIQProvider().is_required(self._settings(workiq="true")) is True

    def test_workiq_draft_on(self) -> None:
        assert WorkIQProvider().is_required(self._settings(workiq_draft=True)) is True

    def test_akm_review_tristate_true(self) -> None:
        assert WorkIQProvider().is_required(
            self._settings(workiq_akm_review="true")
        ) is True

    def test_akm_review_tristate_false_returns_false(self) -> None:
        assert WorkIQProvider().is_required(
            self._settings(workiq_akm_review="false")
        ) is False

    def test_dxx_non_empty(self) -> None:
        assert WorkIQProvider().is_required(self._settings(workiq_dxx="D01")) is True

    def test_dxx_whitespace_only_returns_false(self) -> None:
        assert WorkIQProvider().is_required(self._settings(workiq_dxx="   ")) is False

    def test_prompt_qa_override(self) -> None:
        assert WorkIQProvider().is_required(
            self._settings(workiq_prompt_qa="custom prompt")
        ) is True

    def test_per_question_timeout_positive(self) -> None:
        assert WorkIQProvider().is_required(
            self._settings(workiq_per_question_timeout=300.0)
        ) is True

    def test_per_question_timeout_zero_returns_false(self) -> None:
        assert WorkIQProvider().is_required(
            self._settings(workiq_per_question_timeout=0.0)
        ) is False

    def test_empty_settings_returns_false(self) -> None:
        assert WorkIQProvider().is_required({}) is False


# ---------------------------------------------------------------------------
# McpGenericProvider (C2 + E2: mcp_enabled[name] ON かつ manifest.auth_required)
# ---------------------------------------------------------------------------
class _FakeManifest:
    def __init__(self, auth_required: bool) -> None:
        self.auth_required = auth_required


class TestMcpGenericIsRequired:
    def _provider(self, name: str = "azure") -> McpGenericProvider:
        return McpGenericProvider(name, {})

    def test_mcp_enabled_missing_returns_false(self) -> None:
        assert self._provider().is_required({}) is False

    def test_mcp_enabled_false_returns_false(self) -> None:
        s = {"mcp_enabled": {"azure": False}}
        assert self._provider().is_required(s) is False

    def test_mcp_enabled_other_server_returns_false(self) -> None:
        s = {"mcp_enabled": {"other": True}}
        assert self._provider().is_required(s) is False

    def test_mcp_enabled_true_and_auth_required_true(self) -> None:
        s = {"mcp_enabled": {"azure": True}}
        with patch(
            "hve.gui.auth_providers.manifests.load_manifest_for",
            return_value=_FakeManifest(auth_required=True),
        ):
            assert self._provider().is_required(s) is True

    def test_mcp_enabled_true_and_auth_required_false(self) -> None:
        """Microsoft Learn ケース: auth_required=False の manifest なら除外。"""
        s = {"mcp_enabled": {"microsoft-learn": True}}
        with patch(
            "hve.gui.auth_providers.manifests.load_manifest_for",
            return_value=_FakeManifest(auth_required=False),
        ):
            assert self._provider("microsoft-learn").is_required(s) is False

    def test_mcp_enabled_true_manifest_none_safe_default_true(self) -> None:
        """manifest が見つからない場合は安全側で必須扱い。"""
        s = {"mcp_enabled": {"unknown-mcp": True}}
        with patch(
            "hve.gui.auth_providers.manifests.load_manifest_for",
            return_value=None,
        ):
            assert self._provider("unknown-mcp").is_required(s) is True

    def test_string_true_in_settings(self) -> None:
        s = {"mcp_enabled": {"azure": "true"}}
        with patch(
            "hve.gui.auth_providers.manifests.load_manifest_for",
            return_value=_FakeManifest(auth_required=True),
        ):
            assert self._provider().is_required(s) is True


# ---------------------------------------------------------------------------
# ExternalCliProvider
# ---------------------------------------------------------------------------
class TestExternalCliIsRequired:
    def test_no_cli_url_returns_false(self) -> None:
        assert ExternalCliProvider("").is_required({"options": {"cli_url": ""}}) is False

    def test_cli_url_in_options(self) -> None:
        assert ExternalCliProvider("").is_required(
            {"options": {"cli_url": "localhost:4321"}}
        ) is True

    def test_cli_url_in_constructor(self) -> None:
        assert ExternalCliProvider("localhost:4321").is_required({}) is True


# ---------------------------------------------------------------------------
# provider_is_required ヘルパ
# ---------------------------------------------------------------------------
class TestProviderIsRequiredHelper:
    def test_legacy_provider_with_required_attr(self) -> None:
        class _Legacy:
            id = "legacy"
            required = True

        assert provider_is_required(_Legacy(), {}) is True

    def test_legacy_provider_required_false(self) -> None:
        class _Legacy:
            id = "legacy"
            required = False

        assert provider_is_required(_Legacy(), {}) is False

    def test_no_required_attr_returns_false(self) -> None:
        class _NoAttr:
            id = "noattr"

        assert provider_is_required(_NoAttr(), {}) is False

    def test_is_required_method_overrides_attr(self) -> None:
        class _Both:
            id = "both"
            required = False

            def is_required(self, settings: dict) -> bool:  # noqa: ARG002
                return True

        assert provider_is_required(_Both(), {}) is True
