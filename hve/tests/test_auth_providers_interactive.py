"""hve/tests/test_auth_providers_interactive.py — プロバイダのインタラクティブ拡張テスト。

PySide6 必須 (CommandSpec が PySide6 に依存)。
"""

from __future__ import annotations

import pytest

try:
    from PySide6.QtCore import QObject  # noqa: F401
except ImportError:  # pragma: no cover
    pytest.skip("PySide6 not installed", allow_module_level=True)

from hve.gui.auth_providers import (
    InteractivePlan,
    provider_supports_interactive,
)
from hve.gui.auth_providers.external_cli_provider import ExternalCliProvider
from hve.gui.auth_providers.github_provider import GitHubProvider
from hve.gui.auth_providers.mcp_generic_provider import McpGenericProvider
from hve.gui.auth_providers.workiq_provider import WorkIQProvider


# ---------------------------------------------------------------------------
# provider_supports_interactive ヘルパ
# ---------------------------------------------------------------------------


def test_github_provider_not_interactive() -> None:
    """GitHubProvider はインタラクティブ拡張未対応 (既存フローを維持)。"""
    assert not provider_supports_interactive(GitHubProvider())


def test_workiq_provider_not_interactive() -> None:
    """WorkIQProvider もインタラクティブ拡張未対応 (既存フローを維持)。"""
    assert not provider_supports_interactive(WorkIQProvider(tenant_id="abc"))


def test_mcp_provider_supports_interactive() -> None:
    """McpGenericProvider はインタラクティブ拡張対応。"""
    p = McpGenericProvider("azure", {"command": "dummy"})
    assert provider_supports_interactive(p)


def test_external_cli_supports_interactive() -> None:
    """ExternalCliProvider もインタラクティブ拡張対応。"""
    assert provider_supports_interactive(ExternalCliProvider("localhost:4321"))


# ---------------------------------------------------------------------------
# build_interactive_plan
# ---------------------------------------------------------------------------


def test_mcp_azure_builds_plan_from_manifest() -> None:
    """azure サーバ名 → azure_mcp manifest が読まれて az login が pre_commands に入る。"""
    p = McpGenericProvider("azure", {"command": "dummy"})
    plan = p.build_interactive_plan({})
    assert plan is not None
    assert isinstance(plan, InteractivePlan)
    assert plan.source_manifest_id == "azure_mcp"
    assert plan.pre_commands, "azure_mcp manifest must define pre_auth_commands"
    assert plan.pre_commands[0].argv[0] == "az"


def test_mcp_github_builds_plan_from_manifest() -> None:
    p = McpGenericProvider("github", {"command": "dummy"})
    plan = p.build_interactive_plan({})
    assert plan is not None
    assert plan.source_manifest_id == "github_mcp"
    assert plan.pre_commands[0].argv[:2] == ["gh", "auth"]


def test_mcp_unknown_server_falls_back_to_default_manifest() -> None:
    """未知の MCP サーバは _default manifest を取得する。"""
    p = McpGenericProvider("unknown_xyz_server", {"command": "dummy"})
    plan = p.build_interactive_plan({})
    assert plan is not None
    assert plan.source_manifest_id == "_default"
    # _default は pre_auth_commands を持たない
    assert plan.pre_commands == []


def test_external_cli_returns_none_when_no_manifest_matches() -> None:
    """外部 CLI URL に該当する manifest が無ければ None。

    `_default` は provider_id=external_cli ともマッチしうるが、pre_auth_commands
    を持たない manifest は ``ExternalCliProvider.build_interactive_plan`` 側で
    意図的に None 扱いする (PTY を立てる意味が無いため)。
    """
    plan = ExternalCliProvider("localhost:4321").build_interactive_plan({})
    assert plan is None


def test_interactive_plan_is_frozen() -> None:
    """InteractivePlan は frozen dataclass。"""
    plan = InteractivePlan(display_name="x")
    with pytest.raises((AttributeError, Exception)):
        plan.display_name = "y"  # type: ignore[misc]
