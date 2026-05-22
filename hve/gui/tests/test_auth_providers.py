"""hve.gui.tests.test_auth_providers — auth_providers パッケージのユニットテスト。

ネットワーク・SDK 実呼び出しを伴う処理は全てモックする。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hve.gui.auth_providers import AuthState, AuthStatus
from hve.gui.auth_providers.external_cli_provider import ExternalCliProvider, _parse_host_port
from hve.gui.auth_providers.github_provider import GitHubProvider
from hve.gui.auth_providers.mcp_generic_provider import McpGenericProvider
from hve.gui.auth_providers.registry import discover_providers
from hve.gui.auth_providers.workiq_provider import WorkIQProvider
from hve.gui.copilot_cli_bridge import PluginInfo


# ---------------------------------------------------------------------------
# AuthState
# ---------------------------------------------------------------------------
class TestAuthState:
    def test_is_ok_only_for_authenticated(self) -> None:
        assert AuthState.AUTHENTICATED.is_ok is True
        for st in (
            AuthState.NOT_AUTHENTICATED,
            AuthState.EXPIRED,
            AuthState.UNKNOWN,
            AuthState.CHECKING,
            AuthState.NOT_APPLICABLE,
        ):
            assert st.is_ok is False


# ---------------------------------------------------------------------------
# GitHubProvider
# ---------------------------------------------------------------------------
class TestGitHubProvider:
    def test_required_true(self) -> None:
        assert GitHubProvider().required is True

    def test_is_applicable_always_true(self) -> None:
        assert GitHubProvider().is_applicable({}) is True

    def test_check_status_authenticated(self) -> None:
        class _Info:
            is_authenticated = True
            login = "alice"

        with patch("hve.auth.get_auth_status", return_value=_Info()):
            st = GitHubProvider().check_status()
        assert st.state is AuthState.AUTHENTICATED
        assert st.detail == "alice"

    def test_check_status_not_authenticated(self) -> None:
        class _Info:
            is_authenticated = False
            login = None
            status_message = "no token"

        with patch("hve.auth.get_auth_status", return_value=_Info()):
            st = GitHubProvider().check_status()
        assert st.state is AuthState.NOT_AUTHENTICATED

    def test_check_status_timeout_returns_unknown(self) -> None:
        class _Info:
            is_authenticated = False
            login = None
            status_message = "timeout after 15s"

        with patch("hve.auth.get_auth_status", return_value=_Info()):
            st = GitHubProvider().check_status()
        assert st.state is AuthState.UNKNOWN

    def test_authenticate_no_binary(self) -> None:
        with patch("hve.auth.find_copilot_binary", return_value=None):
            res = GitHubProvider().authenticate(timeout=1.0)
        assert res.success is False
        assert res.state is AuthState.NOT_AUTHENTICATED

    def test_authenticate_success_with_camelcase_sdk_response(self) -> None:
        """SDK が camelCase (isAuthenticated) を返す現実形式で authenticate() が成功すること。

        これは「ブラウザ側で認証成功しても GUI が not_authenticated を表示する」
        既知バグ ([hve/auth.py](hve/auth.py)) の回帰テスト。
        """
        from types import SimpleNamespace

        camel_status = SimpleNamespace(
            isAuthenticated=True,
            login="dahatake",
            statusMessage=None,
            host="https://github.com",
        )

        class _FakeClient:
            async def start(self) -> None: return None
            async def stop(self) -> None: return None
            async def get_auth_status(self):  # noqa: ANN202
                return camel_status

        with patch("hve.auth.find_copilot_binary", return_value="/tmp/copilot"), \
             patch("hve.auth.run_login", return_value=0), \
             patch("copilot.CopilotClient", return_value=_FakeClient()):
            res = GitHubProvider().authenticate(timeout=5.0)

        assert res.success is True
        assert res.state is AuthState.AUTHENTICATED


# ---------------------------------------------------------------------------
# WorkIQProvider
# ---------------------------------------------------------------------------
class TestWorkIQProvider:
    def test_required_false(self) -> None:
        assert WorkIQProvider().required is False

    def test_is_applicable_always_true(self) -> None:
        # registry が plugin 検出時のみインスタンス化するため、
        # is_applicable は生成された時点で常に True。
        assert WorkIQProvider().is_applicable({}) is True

    def test_check_status_authenticated(self) -> None:
        with patch("hve.workiq.is_workiq_available", return_value=True):
            st = WorkIQProvider().check_status()
        assert st.state is AuthState.AUTHENTICATED

    def test_check_status_unavailable(self) -> None:
        with patch("hve.workiq.is_workiq_available", return_value=False):
            st = WorkIQProvider().check_status()
        assert st.state is AuthState.NOT_AUTHENTICATED


# ---------------------------------------------------------------------------
# McpGenericProvider
# ---------------------------------------------------------------------------
class TestMcpGenericProvider:
    def test_id_and_name(self) -> None:
        p = McpGenericProvider("foo", {"command": "npx", "args": ["foo"]})
        assert p.id == "mcp:foo"
        assert p.display_name == "MCP: foo"
        assert p.required is False

    def test_check_status_success(self) -> None:
        with patch(
            "hve.gui.auth_providers.mcp_generic_provider._probe_session",
            return_value=(True, "ok"),
        ):
            st = McpGenericProvider("foo", {}).check_status()
        assert st.state is AuthState.AUTHENTICATED

    def test_check_status_failure(self) -> None:
        with patch(
            "hve.gui.auth_providers.mcp_generic_provider._probe_session",
            return_value=(False, "boom"),
        ):
            st = McpGenericProvider("foo", {}).check_status()
        assert st.state is AuthState.NOT_AUTHENTICATED


# ---------------------------------------------------------------------------
# ExternalCliProvider
# ---------------------------------------------------------------------------
class TestExternalCliProvider:
    def test_parse_host_port_bare(self) -> None:
        assert _parse_host_port("localhost:4321") == ("localhost", 4321)

    def test_parse_host_port_with_scheme(self) -> None:
        assert _parse_host_port("http://example.com:8080") == ("example.com", 8080)

    def test_is_applicable(self) -> None:
        assert ExternalCliProvider("").is_applicable({}) is False
        assert ExternalCliProvider("localhost:4321").is_applicable({}) is True
        assert ExternalCliProvider("").is_applicable({"cli_url": "x:1"}) is True


# ---------------------------------------------------------------------------
# Registry (Copilot CLI bridge 経由)
# ---------------------------------------------------------------------------
class TestDiscoverProviders:
    def _mock_bridge(self, *, plugins=None, servers=None):
        from unittest.mock import patch as _patch

        return (
            _patch(
                "hve.gui.auth_providers.registry.CopilotCliBridge.list_plugins",
                return_value=plugins or [],
            ),
            _patch(
                "hve.gui.auth_providers.registry.CopilotCliBridge.list_mcp_servers",
                return_value=servers or {},
            ),
        )

    def test_minimal_only_github(self) -> None:
        p_plugins, p_servers = self._mock_bridge()
        with p_plugins, p_servers:
            providers = discover_providers({})
        ids = [p.id for p in providers]
        assert ids == ["github"]

    def test_with_workiq_plugin(self) -> None:
        p_plugins, p_servers = self._mock_bridge(
            plugins=[PluginInfo(name="workiq", source="work-iq", version="1.0.0")]
        )
        with p_plugins, p_servers:
            providers = discover_providers({})
        ids = [p.id for p in providers]
        assert ids == ["github", "workiq"]

    def test_workiq_excludes_related_plugins(self) -> None:
        # サブプラグイン (workiq-productivity 等) は Work IQ 認証行を生成しない
        p_plugins, p_servers = self._mock_bridge(
            plugins=[
                PluginInfo(name="workiq-productivity", source="work-iq", version="1.0.0"),
            ]
        )
        with p_plugins, p_servers:
            providers = discover_providers({})
        ids = [p.id for p in providers]
        assert "workiq" not in ids

    def test_mcp_servers_alphabetical(self) -> None:
        p_plugins, p_servers = self._mock_bridge(
            servers={"beta": {"command": "x"}, "alpha": {"command": "y"}}
        )
        with p_plugins, p_servers:
            providers = discover_providers({})
        ids = [pv.id for pv in providers]
        assert ids == ["github", "mcp:alpha", "mcp:beta"]

    def test_with_cli_url_external(self) -> None:
        p_plugins, p_servers = self._mock_bridge()
        with p_plugins, p_servers:
            providers = discover_providers({"cli_url": "localhost:4321"})
        ids = [p.id for p in providers]
        assert "external_cli" in ids

    def test_nested_settings_flattened_for_cli_url(self) -> None:
        p_plugins, p_servers = self._mock_bridge()
        with p_plugins, p_servers:
            providers = discover_providers(
                {"options": {"cli_url": "localhost:1"}}
            )
        ids = [p.id for p in providers]
        assert "external_cli" in ids

    def test_bridge_failure_falls_back_to_github_only(self) -> None:
        from unittest.mock import patch as _patch

        with _patch(
            "hve.gui.auth_providers.registry.CopilotCliBridge.list_plugins",
            side_effect=RuntimeError("boom"),
        ), _patch(
            "hve.gui.auth_providers.registry.CopilotCliBridge.list_mcp_servers",
            side_effect=RuntimeError("boom"),
        ):
            providers = discover_providers({})
        ids = [p.id for p in providers]
        assert ids == ["github"]
