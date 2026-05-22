"""hve.gui.auth_providers.registry — Copilot CLI から有効プロバイダ一覧を構築する。

呼び出し側 (``PluginAuthDialog`` / ``AuthMonitor``) は本モジュールの
``discover_providers()`` のみを呼び、内部実装には依存しない。

設計方針:
    - **GitHub Copilot CLI を唯一の信頼ソース** として扱う。
    - GUI 独自の ``mcp_config`` JSON / ``workiq_tenant_id`` 設定は廃止済み。
    - ``copilot mcp list --json`` の結果から MCP サーバ群を構築。
    - ``copilot plugin list`` の結果から Work IQ 等プラグイン認証行を構築。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..copilot_cli_bridge import CopilotCliBridge
from . import AuthProvider
from .external_cli_provider import ExternalCliProvider
from .github_provider import GitHubProvider
from .mcp_generic_provider import McpGenericProvider
from .workiq_provider import WorkIQProvider

__all__ = ["discover_providers"]


def _looks_like_workiq_plugin(plugin_name: str) -> bool:
    """``copilot plugin list`` 由来のプラグイン名が Work IQ 中核プラグインか判定。

    Work IQ は ``workiq@work-iq`` 単独だけでなく ``workiq-productivity`` /
    ``microsoft-365-agents-toolkit`` 等の派生も同じソースで配布されるが、
    GUI 認証行は中核 1 件のみ表示するため厳密一致とする。
    """
    return plugin_name == "workiq"


def discover_providers(
    settings: Optional[Dict[str, Any]] = None,  # noqa: ARG001 - 後方互換用に残置
) -> List[AuthProvider]:
    """Copilot CLI に基づき有効な ``AuthProvider`` のリストを返す。

    表示順:
        1. GitHub Copilot (常に有効)
        2. Work IQ (``copilot plugin list`` に ``workiq`` プラグインがある場合のみ)
        3. ``copilot mcp list`` の各サーバー (alphabetical)

    引数 ``settings`` は後方互換のため受け取るが現在は未使用。
    """
    providers: List[AuthProvider] = [GitHubProvider()]

    # --- Work IQ プラグイン検出 (Q4-再=β) ---
    try:
        plugins = CopilotCliBridge.list_plugins()
    except Exception:
        plugins = []
    if any(_looks_like_workiq_plugin(p.name) for p in plugins):
        providers.append(WorkIQProvider())

    # --- MCP サーバ列挙 ---
    try:
        servers = CopilotCliBridge.list_mcp_servers()
    except Exception:
        servers = {}
    for name in sorted(servers.keys()):
        providers.append(McpGenericProvider(name, servers[name]))

    # --- 外部 CLI サーバー (Copilot SDK External Server。GUI 設定 ``cli_url`` を保持) ---
    flat: Dict[str, Any] = {}
    if settings:
        for v in settings.values():
            if isinstance(v, dict):
                flat.update(v)
        if not flat:
            flat = dict(settings)
    cli_url = flat.get("cli_url") or None
    if cli_url:
        cli = ExternalCliProvider(str(cli_url))
        if cli.is_applicable(flat):
            providers.append(cli)

    return providers
