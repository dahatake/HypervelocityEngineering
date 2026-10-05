"""FR-CLI-88: PR / Issue参照をSDK resource routingへ限定する契約。"""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_POLICY_JSON = _REPO_ROOT / "hve" / "toolsearch" / "policy.json"
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_REQUIREMENT_HISTORY = _REPO_ROOT / "hve-dev" / "requirement-definition-history.md"

#: 書き込み・状態変更を示す語。GitHub MCP の tool 名に現れたら参照系ではない。
WRITE_TOKENS = (
    "create",
    "update",
    "delete",
    "merge",
    "close",
    "push",
    "add",
    "remove",
    "assign",
    "dispatch",
    "write",
)


def _knowledge_allowlists() -> dict[str, list[str]]:
    payload = json.loads(_POLICY_JSON.read_text(encoding="utf-8"))
    allowlists = payload.get("knowledge_tool_allowlists")
    assert isinstance(allowlists, dict)
    return allowlists


def _requirement_block(requirement_id: str) -> str:
    lines = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(f"- **{requirement_id}**")]
    assert len(starts) == 1, f"{requirement_id} の定義行が {len(starts)} 件見つかった"
    block = [lines[starts[0]]]
    for line in lines[starts[0] + 1 :]:
        if not line.startswith("  "):
            break
        block.append(line)
    return "\n".join(block)


class TestSdkResourceRouting:
    def test_repository_owned_mcp_config_is_absent(self) -> None:
        assert not (_REPO_ROOT / ".github" / ".mcp.json").exists()

    def test_knowledge_allowlists_use_bare_exact_names_without_wildcards(self) -> None:
        offenders = []
        for server, tools in _knowledge_allowlists().items():
            assert isinstance(server, str) and server
            assert isinstance(tools, list)
            for tool in tools:
                if not isinstance(tool, str) or not tool or tool == "*" or ":" in tool:
                    offenders.append(f"{server}:{tool}")
        assert not offenders, f"bare exact tool名でないallowlist: {offenders}"

    def test_knowledge_allowlists_do_not_contain_state_changing_tools(self) -> None:
        offenders = []
        for server, tools in _knowledge_allowlists().items():
            for tool in tools:
                lowered = str(tool).lower()
                if any(token in lowered for token in WRITE_TOKENS):
                    offenders.append(f"{server}:{tool}")
        assert not offenders, f"knowledge allowlistに状態変更toolが含まれる: {offenders}"


class TestRequirementIsDeclared:
    def test_requirement_keeps_the_index_contracts_unchanged(self) -> None:
        block = _requirement_block("FR-CLI-88")
        assert "FR-CQ-01" in block
        assert "FR-MDQ-02" in block

    def test_requirement_uses_sdk_resource_routing_and_rejects_local_config(self) -> None:
        block = _requirement_block("FR-CLI-88")
        assert "FR-TS-12" in block
        assert "FR-TS-13" in block
        assert "raw MCP config" in block
        assert "状態変更tool" in block

    def test_revision_history_records_the_fr_cli_88_sdk_routing_migration(self) -> None:
        text = _REQUIREMENT_HISTORY.read_text(encoding="utf-8-sig")
        revision = next(
            (line for line in text.splitlines() if line.startswith("| 2.94 |")),
            "",
        )
        assert "FR-CLI-88" in revision
        assert ".github/.mcp.json" in revision
        assert "FR-TS-12 / FR-TS-13" in revision
