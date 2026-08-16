"""FR-TS-11: コンテキスト内訳の実測レポート。

整形部分は純関数なので、ランタイムのスナップショット相当を直接与えて検証する。
セッション生成を伴う収集部分（`collect`）はソース検査で契約だけを固定する。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from hve.toolsearch.context_report import build_report, render_json, render_text

_MODULE = Path(__file__).resolve().parents[1] / "toolsearch" / "context_report.py"

_CONTEXT_INFO = {
    "modelName": "claude-sonnet-4.5",
    "limit": 128000,
    "totalTokens": 43702,
    "systemTokens": 15168,
    "toolDefinitionsTokens": 28763,
    "mcpToolsTokens": 17217,
    "conversationTokens": 0,
}

_ENTRIES = [
    {"id": "system:systemPrompt", "kind": "system", "label": "systemPrompt", "tokens": 13790},
    {"id": "system:toolDefinitions", "kind": "system", "label": "toolDefinitions", "tokens": 26000},
    {"id": "toolDefinition:skill", "kind": "toolDefinition", "label": "skill", "tokens": 5527},
    {"id": "toolDefinition:view", "kind": "toolDefinition", "label": "view", "tokens": 371},
    {"id": "toolDefinition:azure-compute", "kind": "toolDefinition", "label": "azure-compute", "tokens": 372},
    {"id": "toolDefinition:azure-storage", "kind": "toolDefinition", "label": "azure-storage", "tokens": 289},
    {
        "id": "toolDefinition:microsoft-learn-microsoft_docs_search",
        "kind": "toolDefinition",
        "label": "microsoft-learn-microsoft_docs_search",
        "tokens": 250,
    },
]

_TOOLS = [
    SimpleNamespace(name="skill", mcp_server_name=None),
    SimpleNamespace(name="view", mcp_server_name=None),
    SimpleNamespace(name="azure-compute", mcp_server_name="azure"),
    SimpleNamespace(name="azure-storage", mcp_server_name="azure"),
    SimpleNamespace(name="microsoft-learn-microsoft_docs_search", mcp_server_name="microsoft-learn"),
]


def _report(**overrides):
    kwargs = {
        "context_info": _CONTEXT_INFO,
        "entries": _ENTRIES,
        "tools": _TOOLS,
        "connected": ("azure", "microsoft-learn"),
        "declared": ("azure", "microsoft-learn"),
    }
    kwargs.update(overrides)
    return build_report(**kwargs)


class TestBuildReport(unittest.TestCase):
    def test_renders_layers_from_the_runtime_snapshot(self) -> None:
        text = render_text(_report())
        self.assertIn("システムプロンプト", text)
        self.assertIn("15,168", text)  # contextInfo.systemTokens
        self.assertIn("組み込み", text)
        self.assertIn("azure", text)
        self.assertIn("microsoft-learn", text)

    def test_groups_tool_definitions_by_server(self) -> None:
        report = _report()
        layers = {layer.name: layer for layer in report.layers}
        self.assertEqual(layers["azure"].tool_count, 2)
        self.assertEqual(layers["azure"].tokens, 372 + 289)
        self.assertEqual(layers["microsoft-learn"].tool_count, 1)

    def test_counts_builtin_tools_separately(self) -> None:
        report = _report()
        layers = {layer.name: layer for layer in report.layers}
        self.assertEqual(layers["(builtin)"].tool_count, 2)
        self.assertEqual(layers["(builtin)"].tokens, 5527 + 371)

    def test_includes_the_model_name_used_for_tokenization(self) -> None:
        self.assertIn("claude-sonnet-4.5", render_text(_report()))
        self.assertEqual(json.loads(render_json(_report()))["model_name"], "claude-sonnet-4.5")

    def test_reports_declared_but_unconnected_servers(self) -> None:
        report = _report(connected=("microsoft-learn",))
        self.assertEqual(report.unconnected, ("azure",))
        text = render_text(report)
        self.assertIn("未接続", text)

    def test_unconnected_server_is_not_reported_as_zero_tokens(self) -> None:
        """未接続サーバーのツールは attribution にも metadata にも現れない。"""
        entries = [e for e in _ENTRIES if not e["id"].startswith("toolDefinition:azure-")]
        tools = [t for t in _TOOLS if t.mcp_server_name != "azure"]
        report = _report(entries=entries, tools=tools, connected=("microsoft-learn",))
        layers = {layer.name: layer for layer in report.layers}
        self.assertNotIn("azure", layers)
        self.assertEqual(report.unconnected, ("azure",))

    def test_tool_definitions_missing_from_metadata_are_not_dropped(self) -> None:
        """`web_search` のように attribution にだけ出るツールを欠落させない（実測）。"""
        entries = _ENTRIES + [
            {
                "id": "toolDefinition:web_search",
                "kind": "toolDefinition",
                "label": "web_search",
                "tokens": 413,
            }
        ]
        report = _report(entries=entries)
        layers = {layer.name: layer for layer in report.layers}
        self.assertEqual(layers["(builtin)"].tool_count, 3)
        self.assertEqual(layers["(builtin)"].tokens, 5527 + 371 + 413)

    def test_json_exposes_the_runtime_totals(self) -> None:
        payload = json.loads(render_json(_report()))
        self.assertEqual(payload["tool_definitions_tokens"], 28763)
        self.assertEqual(payload["mcp_tools_tokens"], 17217)
        self.assertEqual(payload["system_tokens"], 15168)


class TestSourceContract(unittest.TestCase):
    """推定トークンを使わず、収集経路でプロンプトを送らない。"""

    def setUp(self) -> None:
        self.source = _MODULE.read_text(encoding="utf-8")

    def test_does_not_use_estimated_tokens(self) -> None:
        for forbidden in ("estimate_tokens", "entry_definition_text", "from .eval import"):
            self.assertNotIn(forbidden, self.source)

    def test_collect_never_sends_a_prompt(self) -> None:
        self.assertIn("async def collect", self.source)
        for forbidden in (".send(", "send_and_wait"):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
