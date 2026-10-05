"""Work IQ SDK-only利用者文書の契約テスト。"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUB020_DOCS = (
    "users-guide/hve-cli-orchestrator-guide.md",
    "users-guide/plugin-mcp-auth.md",
    "users-guide/troubleshooting.md",
)
_T18_DOCS = (
    "users-guide/plugin-mcp-auth.md",
    "users-guide/troubleshooting.md",
)
_SUB020_FORBIDDEN = (
    "workiq-doctor",
    "@microsoft/workiq",
    "WORKIQ_NPX_COMMAND",
    "workiq@work-iq",
    "canonical Plugin",
    "--workiq-tenant-id",
    "WORKIQ_TENANT_ID",
    "--workiq-request-timeout",
    "WORKIQ_REQUEST_TIMEOUT",
    "--workiq-prompt-review",
    "WORKIQ_PROMPT_REVIEW",
    "session.rpc.mcp.oauth.login",
    "auth-failed",
    "WORKIQ_MCP_QUERY_TOOL_NAMES",
    "WORKIQ_MCP_SERVER_NAMES",
    "_hve_workiq",
    "workiq-preview",
    "Work IQ認証確認",
    "Work IQ 認証確認",
    "Work IQログイン成功",
    "Work IQ ログイン成功",
    "Work IQ 専用session（prefetch",
    "context-injection.prompt.md",
)


def _read(relative: str) -> str:
    return (_REPO_ROOT / relative).read_text(encoding="utf-8")


def _assert_absent(relative: str, *values: str) -> str:
    text = _read(relative)
    for value in values:
        assert value not in text, f"{relative}: {value}"
    return text


def _assert_present(relative: str, *values: str) -> str:
    text = _read(relative)
    for value in values:
        assert value in text, f"{relative}: {value}"
    return text


def test_sub020_cli_auth_and_troubleshooting_have_no_hve_owned_runtime_guidance() -> None:
    for relative in _SUB020_DOCS:
        text = _read(relative)
        for forbidden in _SUB020_FORBIDDEN:
            assert forbidden not in text, f"{relative}: {forbidden}"


def test_sub020_cli_auth_and_troubleshooting_describe_sdk_only_ownership() -> None:
    combined = "\n".join(_read(relative) for relative in _SUB020_DOCS)
    for required in (
        "Plugin または MCP Server",
        "exact `workiq`",
        "mcp.discover",
        "knowledge_tool_allowlists",
        "`retrieve` / `ask` / `fetch`",
        "検証済み出典",
        "`ready` / `not-configured` / `unverified`",
        "`/mcp`",
        "HVE は Work IQ の設定・認証を実行しません",
        "M365 の診断クエリを自動実行しません",
    ):
        assert required in combined, required


def test_t18_docs_distinguish_discovery_from_runtime_initialization() -> None:
    """FR-CLI-91 / FR-TS-13: discovery と初期化後の接続確認を区別する。"""
    for relative in _T18_DOCS:
        _assert_present(
            relative,
            "discovery の `ready` は runtime の `connected` を意味しません",
            "session.rpc.tools.initialize_and_validate()",
            "明示的な SDK 初期化 → 接続確認 → `list_tools`",
            "初期化の正常復帰だけでは接続済みと判定しません",
        )
        _assert_absent(
            relative,
            "接続のための追加操作はしません",
            "SDK discovery と一覧取得で読むだけです",
        )


def test_t18_docs_bound_routing_not_the_full_run_to_sixty_seconds() -> None:
    """FR-TS-13: 60 秒は各 RPC や run 全体ではなく routing の共有予算。"""
    for relative in _T18_DOCS:
        _assert_present(
            relative,
            "routing の共有 60 秒",
            "`apply_resource_route` の入口から出口まで",
            "API / server ごとに予算を再付与しません",
            "run 全体の timeout ではありません",
            "残時間がなくなった場合は optional でも続行しません",
        )


def test_t18_docs_preserve_caller_exclusions_and_conditional_ack_failure() -> None:
    """FR-TS-13: caller 制限を維持し、ACK 失敗の条件別分岐を説明する。"""
    for relative in _T18_DOCS:
        _assert_present(
            relative,
            "caller の `disabled_mcp_servers` / `disabled_skills` と route の除外は和集合",
            "caller が除外した optional resource は再有効化しません",
            "`success is True` だけを ACK 成功",
            "`success=False`",
            "選択 MCP がすべて optional かつ caller filter がない場合",
            "共有 deadline の残時間内に全選択 MCP の disable が成功した場合だけ継続",
            "required MCP または caller filter がある場合は fail-closed",
            "`available_tools` / `excluded_tools`",
        )


def test_t18_docs_separate_host_initialization_from_cli_owned_auth() -> None:
    """FR-CLI-91 / FR-TS-13: 初期化未完了を認証要求と混同しない。"""
    for relative in _T18_DOCS:
        _assert_present(
            relative,
            "`MCP host not initialized` は初期化未完了",
            "`needs-auth` は認証が必要な状態",
            "認証は GitHub Copilot CLI 側で行います",
            "`/mcp`",
            "HVE は Work IQ の設定・認証を実行しません",
            "新しい公開 flag・設定は追加しません",
        )
        _assert_absent(relative, *_SUB020_FORBIDDEN)


def test_gui_guide_describes_sdk_discovery_without_hve_authentication() -> None:
    relative = "users-guide/hve-gui-orchestrator-guide.md"
    _assert_absent(
        relative,
        "Work IQ 認証確認",
        "workiq@work-iq",
        "--workiq-tenant-id",
        "WORKIQ_TENANT_ID",
        "SDK OAuth",
    )
    _assert_present(
        relative,
        "Plugin または MCP Server",
        "exact `workiq`",
        "mcp.discover",
        "`ready`",
        "`not-configured`",
        "`unverified`",
        "HVE は Work IQ の設定・認証を実行しません",
        "HVE process を再起動",
        "Work IQ を知識源に加える",
        "知識源 MCP サーバー",
    )


def test_technical_architecture_assigns_workiq_auth_to_copilot_cli() -> None:
    relative = "users-guide/hve-technical-architecture.md"
    _assert_absent(
        relative,
        "Work IQ認証確認",
        "--workiq-tenant-id",
        "--workiq-request-timeout",
        "--workiq-prompt-review",
        "Work IQはHVEのSDK OAuth経路を使用",
    )
    _assert_present(
        relative,
        "Plugin または MCP Server",
        "exact `workiq`",
        "mcp.discover",
        "session.rpc.mcp.list()",
        "list_tools(server_name=<知識源名>)",
        "HVE は Work IQ の設定・認証を実行しない",
        "knowledge_tool_allowlists",
        "hve_knowledge_write",
        ".hve/locks/",
    )


def test_business_requirement_guide_uses_sdk_only_workiq_contract() -> None:
    relative = "users-guide/01-business-requirement.md"
    _assert_absent(relative, "workiq-doctor", "workiq@work-iq", "Work IQ 認証確認")
    _assert_present(
        relative,
        "Plugin または MCP Server",
        "exact `workiq`",
        "SDK discovery",
        "`/mcp`",
        "Copilot CLI 側で設定・認証",
    )


def test_workflow_reference_covers_all_sdk_only_workiq_phases() -> None:
    relative = "users-guide/workflow-reference.md"
    _assert_absent(relative, "未インストール時は自動スキップ", "ログイン成功後")
    _assert_present(
        relative,
        "事前 QA",
        "AKM 知識探索",
        "ARD 知識探索",
        "exact `workiq`",
        "`retrieve` / `ask` / `fetch`",
        "`not-configured`",
        "`unverified`",
        "該当知識源を除外",
        "qa/<run_id>-<step_id>-pre-execution-qa.md",
        "## ARD 知識探索: ユースケース参照情報",
    )


def test_km_guide_documents_workiq_source_fail_closed_behavior() -> None:
    relative = "users-guide/km-guide.md"
    _assert_present(
        relative,
        "Plugin または MCP Server",
        "exact `workiq`",
        "事前設定・認証",
        "`workiq` だけを除去",
        "他の source が残れば継続",
        "開始を拒否",
        "HVE は OAuth を実行せず",
        "Cloud 実行では利用できない",
        "AKM 知識探索",
        "hve_knowledge_write",
        ".hve/locks/",
    )


def test_knowledge_discovery_file_write_safety_is_documented_across_user_guides() -> None:
    for relative in (
        "users-guide/hve-cli-orchestrator-guide.md",
        "users-guide/hve-technical-architecture.md",
        "users-guide/workflow-reference.md",
        "users-guide/km-guide.md",
    ):
        _assert_present(
            relative,
            "hve_knowledge_write",
            ".hve/locks/",
            "SHA-256",
            "atomic replace",
        )

    for relative in (
        "users-guide/hve-cli-orchestrator-guide.md",
        "users-guide/hve-technical-architecture.md",
    ):
        _assert_present(
            relative,
            "knowledge_tool_allowlists",
            "読み取り専用",
            "`retrieve` / `ask` / `fetch`",
        )


def test_knowledge_discovery_source_verification_is_documented_across_guides() -> None:
    for relative in (
        "users-guide/hve-cli-orchestrator-guide.md",
        "users-guide/hve-technical-architecture.md",
        "users-guide/workflow-reference.md",
        "users-guide/km-guide.md",
        "users-guide/troubleshooting.md",
    ):
        _assert_present(
            relative,
            "Confirmed",
            "Tentative",
            "Unknown",
            "検証済み出典",
        )


def test_cloud_guide_keeps_workiq_local_and_decouples_node_requirement() -> None:
    relative = "users-guide/hve-cloud-getting-started.md"
    _assert_absent(relative, "MCP Server（filesystem 等）/ Work IQ", "workiq@work-iq")
    _assert_present(
        relative,
        "Plugin または MCP Server",
        "exact `workiq`",
        "Copilot CLI 側で事前設定・認証",
        "HVE ローカル CLI / GUI 専用",
    )


def test_root_readme_omits_removed_workiq_doctor_and_links_sdk_only_guide() -> None:
    relative = "README.md"
    _assert_absent(relative, "`workiq-doctor`")
    _assert_present(
        relative,
        "exact `workiq`",
        "Plugin または MCP Server",
        "hve-cli-orchestrator-guide.md#work-iq-plugin--mcp-server-連携オプション",
    )
