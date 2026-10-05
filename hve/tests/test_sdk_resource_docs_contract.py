"""SDK ResourceSnapshot runtime documentation contract.

現在の HVE runtime surface は Copilot CLI 側で設定済みの Plugin / MCP / Skill を
SDK ResourceSnapshot と policy route で読み取る。旧 `.github/.mcp.json` /
`--mcp-config` 手順が users-guide に残ると、利用者が存在しない手順を前提にして
切り分けを誤るため、対象ガイドを固定する。
"""

from __future__ import annotations

from pathlib import Path

from hve.__main__ import _build_parser


_REPO = Path(__file__).resolve().parents[2]
_GUIDES = {
    "readme": _REPO / "README.md",
    "tool_search": _REPO / "users-guide" / "tool-search.md",
    "plugin_mcp_auth": _REPO / "users-guide" / "plugin-mcp-auth.md",
    "cli": _REPO / "users-guide" / "hve-cli-orchestrator-guide.md",
    "prompt": _REPO / "users-guide" / "hve-prompt-getting-started.md",
    "gui": _REPO / "users-guide" / "hve-gui-orchestrator-guide.md",
    "architecture": _REPO / "users-guide" / "hve-technical-architecture.md",
    "playwright_mcp": _REPO / "users-guide" / "setup-playwright-mcp.md",
    "readme_architecture_detail_svg": (
        _REPO / "users-guide" / "images" / "readme-app-architecture-detail.svg"
    ),
    "troubleshooting": _REPO / "users-guide" / "troubleshooting.md",
    "workflow_reference": _REPO / "users-guide" / "workflow-reference.md",
}


def _read(name: str) -> str:
    path = _GUIDES[name]
    assert path.exists(), f"missing guide: {path}"
    return path.read_text(encoding="utf-8")


def _between(name: str, start: str, end: str) -> str:
    text = _read(name)
    assert start in text, f"{name}: missing section {start!r}"
    body = text.split(start, 1)[1]
    assert end in body, f"{name}: missing section boundary {end!r}"
    return body.split(end, 1)[0]


class TestLegacyRuntimeInstructionsAreRemoved:
    def test_current_runtime_guides_do_not_mention_removed_local_mcp_config_surface(self) -> None:
        for name in (
            "tool_search",
            "plugin_mcp_auth",
            "cli",
            "prompt",
            "gui",
            "architecture",
            "readme",
            "playwright_mcp",
            "readme_architecture_detail_svg",
            "troubleshooting",
            "workflow_reference",
        ):
            text = _read(name)
            assert "--mcp-config" not in text, name
            assert ".github/.mcp.json" not in text, name

    def test_current_runtime_guides_do_not_send_users_to_cli_resource_listing_or_gui_auth_buttons(self) -> None:
        for name in ("plugin_mcp_auth", "gui", "architecture"):
            text = _read(name)
            assert "copilot plugins list --kind plugin --kind mcp --json" not in text, name
            assert "認証手順..." not in text, name


class TestToolSearchGuideTracksSdkSnapshotRouting:
    def test_toolsearch_guide_mentions_context_flags_and_comparison_contract(self) -> None:
        text = _read("tool_search")
        for needle in (
            "hve toolsearch context --workflow ard",
            "--compare",
            "比較不能",
            "ResourceSnapshot",
            "no-prompt",
            "同じ ResourceSnapshot",
            "同じ model",
            "同じ context tier",
            "同じ policy route",
            "runtime drift",
            "comparable: false",
            "削減率は 0 で捏造せず `null`",
        ):
            assert needle in text

    def test_toolsearch_guide_lists_the_four_runtime_classifications(self) -> None:
        text = _read("tool_search")
        for classification in (
            "knowledge",
            "software-engineering",
            "both",
            "unclassified",
        ):
            assert classification in text


class TestPluginAndRuntimeGuidesDescribeSdkResources:
    def test_plugin_mcp_auth_guide_describes_generic_snapshot_and_safe_fields(self) -> None:
        text = _read("plugin_mcp_auth")
        for needle in (
            "Plugin / MCP / Skill",
            "ResourceSnapshot",
            "kind",
            "name",
            "source_kind",
            "plugin_marketplace",
            "owner_plugin",
            "enabled",
            "effective_category",
            "individual_override",
            "C7",
            "Tool-Search",
            "Copilot CLI の責務",
            "snapshot projection",
            "exact `workiq`",
            "ask",
        ):
            assert needle in text

    def test_cli_gui_and_architecture_guides_explain_one_process_snapshot_and_boundaries(self) -> None:
        cli = _read("cli")
        gui = _read("gui")
        architecture = _read("architecture")

        for needle in (
            "ResourceSnapshot",
            "Copilot CLI 側で事前設定",
            "CLI の責務",
        ):
            assert needle in cli

        for needle in (
            "process-wide",
            "同じ ResourceSnapshot",
            "force_refresh=true",
            "safe editor",
            "Cloud Session は未対応",
            "SDK Resources",
        ):
            assert needle in gui

        for needle in (
            "single SDK ResourceSnapshot",
            "force_refresh",
            "Cloud Session は未対応",
            "runtime drift",
        ):
            assert needle in architecture


class TestTroubleshootingAndWorkflowReference:
    def test_troubleshooting_guide_covers_unverified_required_failure_and_runtime_drift(self) -> None:
        text = _read("troubleshooting")
        for needle in (
            "unverified",
            "required resource failure",
            "runtime drift",
        ):
            assert needle in text

    def test_workflow_reference_removes_raw_per_key_override_example_and_uses_generic_workiq_route(self) -> None:
        text = _read("workflow_reference")
        assert "per_key_mcp_servers" not in text
        assert "raw per-key override は廃止" in text
        assert "Work IQ は generic route" in text


class TestToolsearchContextFlagsExistInTheParser:
    def test_docs_only_reference_existing_toolsearch_context_flags(self) -> None:
        parser = _build_parser()
        command = next(
            action
            for action in parser._actions
            if hasattr(action, "choices") and isinstance(action.choices, dict)
        ).choices["toolsearch"]
        context_parser = next(
            action
            for action in command._actions
            if hasattr(action, "choices") and isinstance(action.choices, dict)
        ).choices["context"]
        help_text = context_parser.format_help()

        for needle in ("context", "--workflow", "--compare", "--json"):
            assert needle in help_text


class TestT19PromptAndCliRuntimeContracts:
    """FR-TS-13 / FR-CLI-91 / FR-PROMPT-04/10 — 文書だけの受入契約。"""

    def test_t19_prompt_plan_runtime_and_reapproval_are_separate(self) -> None:
        plan = _between(
            "prompt",
            "\n## Step 3. 提示された計画を読む（書き込みなし）",
            "\n## Step 4.",
        )
        for needle in (
            "計画成功は runtime 初期化・接続・query 成功を意味しません",
            "plan では実働 session の初期化も query も行いません",
            "discovery の `ready` は runtime の `connected` を意味しません",
        ):
            assert needle in plan, needle

        approval = _between("prompt", "\n## Step 4.", "\n## 中断した標準ローカル実行")
        for needle in (
            "最初のモデル送信前",
            "初期化・readiness",
            "必要な options 更新の ACK",
            "新しい計画内容と plan SHA-256",
            "別 turn の明示承認",
            "変更や drift がなければ再planは不要",
            "転記する必要はありません",
        ):
            assert needle in approval, needle

        troubleshooting = _between("prompt", "\n## うまくいかないとき", "\n## 対象外")
        for needle in (
            "上流成果物の不足だけとは限りません",
            "runtime",
            "fail-closed",
            "`needs-auth`",
            "Copilot CLI",
            "`/mcp`",
            "静的チェックは、実接続・実 query・Prompt 実行の実測ではありません",
            "採用成功や本番相当の動作実績へ読み替えません",
        ):
            assert needle in troubleshooting, needle

    def test_t19_cli_runtime_gate_preserves_conditional_ack_and_auth_boundary(self) -> None:
        runtime = _between(
            "cli", "\n### SDK ResourceSnapshot routing（現行 runtime）", "\n### MCP 通信ログ"
        )
        for needle in (
            "最初のモデル送信前",
            "session.rpc.tools.initialize_and_validate()",
            "初期化 → readiness → `list_tools` → 必要な options 更新の ACK",
            "初期化の正常復帰だけでは接続済みと判定しません",
            "`success is True` だけを ACK 成功",
            "required MCP または caller filter がある場合は fail-closed",
            "選択 MCP がすべて optional かつ caller filter がない場合",
            "共有 deadline の残時間内に全選択 MCP の disable が成功した場合だけ継続",
            "期限切れ・cancel は停止",
            "実効選択 MCP が 0 件",
            "required Skill の runtime 検証と caller filter の適用確認は省略しません",
        ):
            assert needle in runtime, needle

        workiq = _between(
            "cli", "\n#### SDK discovery capability", "\n#### 知識探索エージェント"
        )
        for needle in (
            "discovery の `ready` は runtime の `connected` を意味しません",
            "initialize_and_validate",
            "knowledge_tool_allowlists",
            "知識源 <名前> を除外します",
            "usable が 0 件",
            "`retrieve` / `ask` / `fetch`",
        ):
            assert needle in workiq, needle

        troubleshooting = _between(
            "cli", "\n### MCP Server が接続できない", "\n### 並列実行でメモリ不足"
        )
        for needle in (
            "`MCP host not initialized`",
            "`needs-auth`",
            "fail-closed",
            "HVE 内で認証を再試行しません",
            "live E2E は未実施",
        ):
            assert needle in troubleshooting, needle

    def test_t19_resume_documents_cold_exclusion_resident_limits_and_skill_wire(self) -> None:
        for name, start, end in (
            ("prompt", "\n### 再開時の実行順と保証範囲", "\n## 承認後の完全実行範囲"),
            ("cli", "\n## 中断と再開（Resume）", "\n### Legacy `orchestrate --resume-run`"),
        ):
            resume = _between(name, start, end)
            for needle in (
                "cold resume",
                "`disabled_mcp_servers`",
                "除外サーバーを起動しません",
                "resident session",
                "既に起動済みのプロセスを取り消すことはできません",
                "SDK 1.0.11",
                "`disabled_skills=[]`",
                "`disabledSkills`",
                "wire payload では省略",
                "required Skill は runtime で確認",
                "fail-closed",
            ):
                assert needle in resume, f"{name}: {needle}"

    def test_t19_workiq_adoption_uses_knowledge_discovery_source_verification(self) -> None:
        evidence = _between(
            "cli", "\n#### 知識探索エージェント", "\n#### 事前 QA / AKM / ARD での使われ方"
        )
        for needle in (
            "1 つの Copilot SDK session",
            "読み取り専用 MCP tool",
            "hve_read_file",
            "hve_qa_create",
            "hve_qa_answer",
            "hve_knowledge_write",
            "検証済み",
            "Confirmed",
            "Unknown",
            "知識探索 [<label>]",
        ):
            assert needle in evidence, needle

        sessions = _between(
            "cli", "\n#### 実行時確認と利用不可時の動作", "\n#### 知識探索エージェント"
        )
        assert "knowledge_tool_allowlists" in sessions
        assert "`create_entity` / `update_entity` / `delete_entity`" in sessions