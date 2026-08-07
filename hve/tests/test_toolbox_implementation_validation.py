"""TB-CAP 実装 gate の validator テスト。

FR-WF-AAGD-01。
設計 TB-CAP → Agent config → System Prompt → test spec の値が一致することを
決定的に検証し、Prompt の自己申告で通過させない。
SDK シンボル名や API version は検証対象にしない（設定契約だけを見る）。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.artifact_validation import validate_ai_agent_implementation_artifacts

from hve.tests.test_ai_agent_capability_validation import (
    _design_text,
    _mcp_source,
    _python_source,
    _system_prompt,
    _test_spec,
)

# 最小設計の Tool 集合（REST 2 + MCP 1 + 経路 1）。
_REST_IDS = ["order-read", "order-update"]
_MCP_IDS = ["get_schema"]
_ROUTE_IDS = ["orders-search"]
_ALL_IDS = _REST_IDS + _MCP_IDS + _ROUTE_IDS
_PINNED = _REST_IDS[0]

_TOOL_SEARCH_INSTRUCTION = "能力が存在しないと結論する前に必ず tool_search を呼ぶ。"


def _tb_blocks(*, limit: int = 5) -> str:
    rows = "".join(
        f"| {tool_id} | yes | （pin のため不要） | — |\n"
        if tool_id == _PINNED
        else f"| {tool_id} | no | notes orders lookup | 注文を調べたい |\n"
        for tool_id in _ALL_IDS
    )
    return f"""#### 7.5.1 Tool Inventory（TB-CAP-01）
- Status: selected
- Total tools: {len(_ALL_IDS)}
- REST tools: {len(_REST_IDS)}
- MCP allowlist tools: {len(_MCP_IDS)}
- Distinct search routes: {len(_ROUTE_IDS)}
- Counting source: AG-CAP-03 / AG-CAP-04 / AG-CAP-05
- Checked at: 2026-08-05

#### 7.5.2 Toolbox Decision（TB-CAP-02）
- Status: selected
- Toolbox: adopted
- Tool search: enabled
- Connection topology: via-toolbox
- Threshold basis: operator policy
- Checked at: 2026-08-05

#### 7.5.3 Pinning Policy（TB-CAP-03）
- Status: selected
- Pinned tools: {_PINNED}
- Pin rationale: Called first in every workflow.
- Unpinned scope: Long tail tools used less than monthly.
- Wildcard pin: not used
- Checked at: 2026-08-05

#### 7.5.4 Search Metadata（TB-CAP-04）
| Tool ID | Pinned | Additional search text | 想定ユーザー語彙 |
|---|---|---|---|
{rows}
#### 7.5.5 Discovery Budget（TB-CAP-05）
- Status: selected
- limit: {limit}
- Expected tool_search calls per turn: 1 to 2
- Overflow behavior: Report capability missing after 3 searches.
- System prompt requirement: Always call tool_search before concluding a capability is missing.
- Checked at: 2026-08-05
"""


def _disabled_blocks() -> str:
    """`no` 方針で許される形（TB-CAP-01/02 + 理由付き N/A の 03〜05）。"""
    tail = (
        "- Reason: The tool catalog stays small and every tool is used in almost every turn.\n"
        "- Decision source: docs/agent/agent-architecture.md#Tool-Boundary\n"
        "- Recheck condition: Revisit when the tool count exceeds 15.\n"
    )
    blocks = f"""#### 7.5.1 Tool Inventory（TB-CAP-01）
- Status: selected
- Total tools: {len(_ALL_IDS)}
- REST tools: {len(_REST_IDS)}
- MCP allowlist tools: {len(_MCP_IDS)}
- Distinct search routes: {len(_ROUTE_IDS)}
- Counting source: AG-CAP-03 / AG-CAP-04 / AG-CAP-05
- Checked at: 2026-08-05

#### 7.5.2 Toolbox Decision（TB-CAP-02）
- Status: selected
- Toolbox: not adopted
- Tool search: disabled
- Connection topology: direct-kb
- Reason: The operator disabled tool search for this Agent.
- Checked at: 2026-08-05

"""
    for heading in (
        "7.5.3 Pinning Policy（TB-CAP-03）",
        "7.5.4 Search Metadata（TB-CAP-04）",
        "7.5.5 Discovery Budget（TB-CAP-05）",
    ):
        blocks += f"#### {heading}\n- Status: N/A\n{tail}\n"
    return blocks


def _toolbox_config(
    *,
    tool_search: str = "enabled",
    limit: int = 5,
    pinned: list | None = None,
    search_text: dict | None = None,
) -> dict:
    return {
        "tool_search": tool_search,
        "connection_topology": "via-toolbox",
        "tool_search_limit": limit,
        "pinned_tools": [_PINNED] if pinned is None else pinned,
        "additional_search_text": (
            {tool_id: "notes orders lookup" for tool_id in _ALL_IDS if tool_id != _PINNED}
            if search_text is None
            else search_text
        ),
    }


_TB_CAP_TRACE_ROWS = "".join(
    f"| TEST-TB-CAP-0{index} | TB-CAP-0{index} | tool search assertion log |\n"
    for index in range(1, 6)
)


def _write_fixture(
    root: Path,
    *,
    tb_blocks: str,
    toolbox_config: dict | None,
    tool_search_instruction: str = _TOOL_SEARCH_INSTRUCTION,
    tb_cap_trace: str = _TB_CAP_TRACE_ROWS,
) -> tuple[Path, Path, Path]:
    detail = root / "docs" / "agent" / "agent-detail-AG-01.md"
    detail.parent.mkdir(parents=True, exist_ok=True)
    detail.write_text(_design_text() + "\n" + tb_blocks, encoding="utf-8")

    agent_dir = root / "src" / "agent" / "AG-01"
    prompt_path = agent_dir / "prompts" / "system-prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(
        _system_prompt() + tool_search_instruction + "\n", encoding="utf-8"
    )

    config: dict = {
        "max_iterations": 3,
        "selected_routes": [
            {
                "request_class": "operational-api-read",
                "preferred_route": "orders-search",
                "fallback_route": "none",
            }
        ],
        "rest_tools": [
            {"tool_id": "order-read", "method": "GET", "path": "/orders/{id}"},
            {"tool_id": "order-update", "method": "PATCH", "path": "/orders/{id}"},
        ],
        "mcp_servers": [
            {"server_label": "orders-schema", "tool_allowlist": ["get_schema"]}
        ],
    }
    if toolbox_config is not None:
        config["toolbox"] = toolbox_config
    (agent_dir / "agent-config.json").write_text(json.dumps(config), encoding="utf-8")
    (agent_dir / "agent.py").write_text(_python_source(), encoding="utf-8")
    (agent_dir / "mcp_client.py").write_text(_mcp_source(), encoding="utf-8")

    test_spec = root / "docs" / "test-specs" / "AG-01-test-spec.md"
    test_spec.parent.mkdir(parents=True, exist_ok=True)
    test_spec.write_text(_test_spec() + tb_cap_trace, encoding="utf-8")
    return detail, agent_dir, test_spec


def _tb_errors(errors: list) -> list:
    return [error for error in errors if "TB-CAP" in error]


def _validate(policy: str = "yes", **kwargs) -> list:
    with TemporaryDirectory() as temp_dir:
        detail, agent_dir, test_spec = _write_fixture(Path(temp_dir), **kwargs)
        return validate_ai_agent_implementation_artifacts(
            detail, agent_dir, test_spec, policy
        )


class TestToolboxImplementationGate(unittest.TestCase):
    def test_matching_implementation_passes(self) -> None:
        errors = _tb_errors(
            _validate(tb_blocks=_tb_blocks(), toolbox_config=_toolbox_config())
        )
        self.assertEqual(errors, [], errors)

    def test_missing_toolbox_configuration_fails(self) -> None:
        errors = _tb_errors(_validate(tb_blocks=_tb_blocks(), toolbox_config=None))
        self.assertTrue(errors, "TB-CAP 設定欠落を検出していない")

    def test_limit_mismatch_fails(self) -> None:
        errors = _tb_errors(
            _validate(tb_blocks=_tb_blocks(limit=5), toolbox_config=_toolbox_config(limit=9))
        )
        self.assertTrue(any("limit" in e for e in errors), errors)

    def test_pin_mismatch_fails(self) -> None:
        errors = _tb_errors(
            _validate(
                tb_blocks=_tb_blocks(),
                toolbox_config=_toolbox_config(pinned=["order-update"]),
            )
        )
        self.assertTrue(any("pin" in e.lower() for e in errors), errors)

    def test_wildcard_pin_fails(self) -> None:
        errors = _tb_errors(
            _validate(tb_blocks=_tb_blocks(), toolbox_config=_toolbox_config(pinned=["*"]))
        )
        self.assertTrue(any("wildcard" in e.lower() for e in errors), errors)

    def test_missing_search_text_fails(self) -> None:
        errors = _tb_errors(
            _validate(
                tb_blocks=_tb_blocks(),
                toolbox_config=_toolbox_config(search_text={"order-update": "notes"}),
            )
        )
        self.assertTrue(any("search text" in e.lower() for e in errors), errors)

    def test_system_prompt_must_require_tool_search_first(self) -> None:
        errors = _tb_errors(
            _validate(
                tb_blocks=_tb_blocks(),
                toolbox_config=_toolbox_config(),
                tool_search_instruction="",
            )
        )
        self.assertTrue(any("system prompt" in e.lower() for e in errors), errors)

    def test_missing_test_trace_fails(self) -> None:
        errors = _tb_errors(
            _validate(
                tb_blocks=_tb_blocks(),
                toolbox_config=_toolbox_config(),
                tb_cap_trace="",
            )
        )
        self.assertTrue(any("test" in e.lower() for e in errors), errors)


class TestDisabledToolSearch(unittest.TestCase):
    def test_disabled_without_toolbox_artifacts_passes(self) -> None:
        errors = _tb_errors(
            _validate(
                policy="no",
                tb_blocks=_disabled_blocks(),
                toolbox_config=None,
                tool_search_instruction="",
            )
        )
        self.assertEqual(errors, [], errors)

    def test_disabled_with_toolbox_configuration_fails(self) -> None:
        errors = _tb_errors(
            _validate(
                policy="no",
                tb_blocks=_disabled_blocks(),
                toolbox_config=_toolbox_config(tool_search="disabled"),
                tool_search_instruction="",
            )
        )
        self.assertTrue(any("must not" in e.lower() for e in errors), errors)


class TestNoSdkSymbolCoupling(unittest.TestCase):
    def test_validator_does_not_pin_sdk_symbols(self) -> None:
        """プレビューで変動する SDK 名・API version を validator へ固定しない。"""
        source = (
            Path(__file__).resolve().parents[1] / "artifact_validation.py"
        ).read_text(encoding="utf-8")
        for symbol in ("ToolSearchToolboxTool", "V1Preview", "azure-ai-projects"):
            self.assertNotIn(symbol, source)


if __name__ == "__main__":
    unittest.main()
