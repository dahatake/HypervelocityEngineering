"""hve.gui.tests.test_copilot_cli_bridge — CopilotCliBridge ユニットテスト。

subprocess 呼び出しは ``unittest.mock.patch`` で差し替え、実 CLI は呼ばない。
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from hve.gui.copilot_cli_bridge import CopilotCliBridge, PluginInfo


_FAKE_EXE = "/fake/bin/copilot"


def _mock_completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ---------------------------------------------------------------------------
# find_binary / is_available
# ---------------------------------------------------------------------------
class TestFindBinary:
    def test_returns_none_when_underlying_returns_none(self) -> None:
        with patch("hve.auth.find_copilot_binary", return_value=None):
            assert CopilotCliBridge.find_binary() is None
            assert CopilotCliBridge.is_available() is False

    def test_returns_path_when_found(self) -> None:
        with patch("hve.auth.find_copilot_binary", return_value=_FAKE_EXE):
            assert CopilotCliBridge.find_binary() == _FAKE_EXE
            assert CopilotCliBridge.is_available() is True


# ---------------------------------------------------------------------------
# list_mcp_servers
# ---------------------------------------------------------------------------
class TestListMcpServers:
    def test_returns_empty_when_binary_missing(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=None):
            assert CopilotCliBridge.list_mcp_servers() == {}

    def test_parses_real_json_schema(self) -> None:
        stdout = json.dumps(
            {
                "mcpServers": {
                    "azure-mcp": {
                        "tools": ["*"],
                        "type": "local",
                        "command": "npx",
                        "args": ["-y", "@azure/mcp@latest", "server", "start"],
                        "source": "user",
                    },
                    "github": {
                        "type": "http",
                        "url": "https://api.githubcopilot.com/mcp/",
                        "source": "builtin",
                    },
                }
            }
        )
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", return_value=_mock_completed(stdout=stdout)):
            servers = CopilotCliBridge.list_mcp_servers()
        assert set(servers.keys()) == {"azure-mcp", "github"}
        assert servers["azure-mcp"]["command"] == "npx"
        assert servers["azure-mcp"]["source"] == "user"
        assert servers["github"]["url"].endswith("/mcp/")

    def test_invalid_json_returns_empty(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", return_value=_mock_completed(stdout="not json")):
            assert CopilotCliBridge.list_mcp_servers() == {}

    def test_nonzero_returncode_returns_empty(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", return_value=_mock_completed(returncode=1, stderr="boom")):
            assert CopilotCliBridge.list_mcp_servers() == {}

    def test_timeout_returns_empty(self) -> None:
        def _raise(*_a, **_kw):
            raise subprocess.TimeoutExpired(cmd="copilot", timeout=1)
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", side_effect=_raise):
            assert CopilotCliBridge.list_mcp_servers(timeout=1.0) == {}

    def test_missing_mcpservers_key_returns_empty(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", return_value=_mock_completed(stdout="{}")):
            assert CopilotCliBridge.list_mcp_servers() == {}


# ---------------------------------------------------------------------------
# get_mcp_server
# ---------------------------------------------------------------------------
class TestGetMcpServer:
    def test_parses_real_json_schema(self) -> None:
        stdout = json.dumps(
            {
                "azure-mcp": {
                    "tools": ["*"],
                    "type": "local",
                    "command": "npx",
                    "args": ["-y", "@azure/mcp@latest", "server", "start"],
                    "source": "user",
                }
            }
        )
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", return_value=_mock_completed(stdout=stdout)) as mrun:
            defn = CopilotCliBridge.get_mcp_server("azure-mcp")
        assert defn is not None
        assert defn["command"] == "npx"
        # argv チェック: copilot mcp get azure-mcp --json
        argv = mrun.call_args.args[0]
        assert argv[1:] == ["mcp", "get", "azure-mcp", "--json"]

    def test_returns_none_for_empty_name(self) -> None:
        assert CopilotCliBridge.get_mcp_server("") is None

    def test_returns_none_when_unknown(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", return_value=_mock_completed(returncode=1)):
            assert CopilotCliBridge.get_mcp_server("nope") is None


# ---------------------------------------------------------------------------
# list_plugins
# ---------------------------------------------------------------------------
class TestListPlugins:
    # 実機 stdout サンプル (T00 調査結果より)。bullet は U+2022。
    _REAL_STDOUT = (
        "Installed plugins:\n"
        "  \u2022 workiq@work-iq (v1.0.0)\n"
        "  \u2022 microsoft-365-agents-toolkit@work-iq (v1.3.0)\n"
        "  \u2022 workiq-productivity@work-iq (v1.0.0)\n"
    )

    def test_parses_real_text_format(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", return_value=_mock_completed(stdout=self._REAL_STDOUT)):
            plugins = CopilotCliBridge.list_plugins()
        assert plugins == [
            PluginInfo(name="workiq", source="work-iq", version="1.0.0"),
            PluginInfo(name="microsoft-365-agents-toolkit", source="work-iq", version="1.3.0"),
            PluginInfo(name="workiq-productivity", source="work-iq", version="1.0.0"),
        ]

    def test_tolerates_other_bullet_chars(self) -> None:
        # Windows コンソールのコードページによっては bullet が "*" / "-" 等に化ける
        stdout = (
            "Installed plugins:\n"
            "  * workiq@work-iq (v1.0.0)\n"
            "  - other@other (v2.0.0)\n"
        )
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", return_value=_mock_completed(stdout=stdout)):
            plugins = CopilotCliBridge.list_plugins()
        names = [p.name for p in plugins]
        assert "workiq" in names
        assert "other" in names

    def test_empty_when_binary_missing(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=None):
            assert CopilotCliBridge.list_plugins() == []

    def test_ignores_non_matching_lines(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("subprocess.run", return_value=_mock_completed(stdout="No plugins installed\n")):
            assert CopilotCliBridge.list_plugins() == []


# ---------------------------------------------------------------------------
# is_logged_in / run_login_blocking
# ---------------------------------------------------------------------------
class TestAuthHelpers:
    def test_is_logged_in_true(self) -> None:
        with patch("hve.auth.is_authenticated", return_value=True):
            assert CopilotCliBridge.is_logged_in() is True

    def test_is_logged_in_swallows_exception(self) -> None:
        with patch("hve.auth.is_authenticated", side_effect=RuntimeError("boom")):
            assert CopilotCliBridge.is_logged_in() is False

    def test_run_login_returns_minus_one_when_binary_missing(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=None):
            assert CopilotCliBridge.run_login_blocking() == -1

    def test_run_login_returns_minus_two_on_timeout(self) -> None:
        def _raise(*_a, **_kw):
            raise subprocess.TimeoutExpired(cmd="copilot", timeout=1)
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("hve.auth.run_login", side_effect=_raise):
            assert CopilotCliBridge.run_login_blocking(timeout=1.0) == -2

    def test_run_login_returns_subprocess_rc(self) -> None:
        with patch.object(CopilotCliBridge, "find_binary", return_value=_FAKE_EXE), \
             patch("hve.auth.run_login", return_value=0):
            assert CopilotCliBridge.run_login_blocking() == 0
