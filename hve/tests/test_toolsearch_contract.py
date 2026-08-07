"""FR-TS-01 / FR-TS-02: Tool Search 契約型のテスト。

根拠: work/hve-tool-search/contracts/spike-result.md（Copilot SDK 1.0.7 実測）
"""

from __future__ import annotations

import dataclasses
import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from hve.toolsearch import (
    MAX_ARG_SCHEMA_DEPTH,
    TOOL_SEARCH_TOOL_NAME,
    ToolCard,
    ToolEntry,
    ToolSearchContractError,
    build_catalog,
    flatten_schema_terms,
    resolve_policy_value,
)
from hve.toolsearch.policy import POLICY_KEY_RE as _POLICY_KEY_RE

_POLICY_PATH = Path(__file__).resolve().parents[1] / "toolsearch" / "policy.json"


def _meta(
    name: str,
    *,
    description: str = "",
    mcp_server_name: str | None = None,
    input_schema: dict | None = None,
    defer_loading: bool | None = None,
) -> SimpleNamespace:
    """SDK の CurrentToolMetadata と同じ属性を持つスタブ。"""
    return SimpleNamespace(
        name=name,
        description=description,
        mcp_server_name=mcp_server_name,
        mcp_tool_name=None,
        namespaced_name=None,
        input_schema=input_schema,
        defer_loading=defer_loading,
    )


class TestSdkContract(unittest.TestCase):
    """FR-TS-01: 差し替え対象名が SDK 側の定数と一致すること。"""

    def test_tool_search_tool_name_matches_sdk_constant(self) -> None:
        # SDK のプライベート定数へ意図的に依存する。SDK がこの名前を変えたら差し替えが
        # 無言で無効化されるため、壊れたときに気付けるようにここで固定する。
        from copilot import session as copilot_session

        self.assertEqual(
            TOOL_SEARCH_TOOL_NAME,
            copilot_session._TOOL_SEARCH_TOOL_NAME,
        )

    def test_sdk_exposes_override_and_reference_primitives(self) -> None:
        """override / tool_references / available_tools が SDK に存在すること。"""
        import inspect

        import copilot
        from copilot.tools import ToolInvocation, ToolResult

        params = inspect.signature(copilot.define_tool).parameters
        self.assertIn("overrides_built_in_tool", params)
        self.assertIn("defer", params)
        self.assertIn("tool_references", {f.name for f in dataclasses.fields(ToolResult)})
        self.assertIn("available_tools", {f.name for f in dataclasses.fields(ToolInvocation)})


class TestFlattenSchemaTerms(unittest.TestCase):
    """FR-TS-02: 引数名・引数説明をネスト 3 階層まで語彙化する。"""

    def test_returns_empty_for_non_mapping(self) -> None:
        self.assertEqual(flatten_schema_terms(None), ())
        self.assertEqual(flatten_schema_terms("not a schema"), ())

    def test_collects_property_names_and_descriptions(self) -> None:
        terms = flatten_schema_terms(
            {
                "type": "object",
                "description": "リソースグループを一覧する",
                "properties": {
                    "subscription": {"type": "string", "description": "サブスクリプション ID"},
                },
            }
        )
        self.assertIn("subscription", terms)
        self.assertIn("サブスクリプション ID", terms)
        self.assertIn("リソースグループを一覧する", terms)

    def test_stops_at_max_depth(self) -> None:
        schema: dict = {"properties": {"lv1": {"properties": {"lv2": {"properties": {"lv3": {"properties": {"lv4": {}}}}}}}}}
        terms = flatten_schema_terms(schema)
        self.assertIn("lv1", terms)
        self.assertIn("lv2", terms)
        self.assertNotIn("lv4", terms)
        self.assertEqual(MAX_ARG_SCHEMA_DEPTH, 3)

    def test_deduplicates_preserving_order(self) -> None:
        terms = flatten_schema_terms(
            {
                "properties": {
                    "a": {"description": "dup"},
                    "b": {"description": "dup"},
                }
            }
        )
        self.assertEqual(terms.count("dup"), 1)
        self.assertLess(terms.index("a"), terms.index("b"))


class TestToolEntry(unittest.TestCase):
    def test_mcp_tool_is_namespaced_by_server(self) -> None:
        entry = ToolEntry.from_current_tool_metadata(
            _meta("azmcp_group_list", mcp_server_name="azure", defer_loading=True)
        )
        self.assertEqual(entry.kind, "mcp")
        self.assertEqual(entry.server, "azure")
        self.assertEqual(entry.id, "mcp:azure:azmcp_group_list")
        self.assertTrue(entry.deferred)

    def test_native_tool_falls_back_to_hve_server(self) -> None:
        entry = ToolEntry.from_current_tool_metadata(_meta("search_markdown"))
        self.assertEqual(entry.kind, "native")
        self.assertEqual(entry.server, "hve")
        self.assertEqual(entry.id, "native:hve:search_markdown")
        self.assertFalse(entry.deferred)

    def test_rejects_empty_name(self) -> None:
        with self.assertRaises(ToolSearchContractError):
            ToolEntry.from_current_tool_metadata(_meta(""))

    def test_rejects_invalid_pin_mode(self) -> None:
        with self.assertRaises(ToolSearchContractError):
            ToolEntry(id="x", kind="native", server="hve", name="x", description="", pin="pinned")  # type: ignore[arg-type]


class TestToolCard(unittest.TestCase):
    """FR-TS-02: additional_search_text をモデルへ返さない。"""

    def test_card_has_no_additional_search_text_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(ToolCard)}
        self.assertNotIn("additional_search_text", field_names)

    def test_from_entry_drops_search_only_vocabulary(self) -> None:
        entry = ToolEntry(
            id="mcp:azure:x",
            kind="mcp",
            server="azure",
            name="x",
            description="desc",
            additional_search_text="秘匿すべき検索専用語彙",
        )
        card = ToolCard.from_entry(entry, score=1.5)
        self.assertNotIn("秘匿すべき検索専用語彙", repr(card))
        self.assertEqual(card.description, "desc")
        self.assertEqual(card.score, 1.5)


class TestBuildCatalog(unittest.TestCase):
    def test_none_snapshot_yields_empty_catalog(self) -> None:
        self.assertEqual(build_catalog(None), ())

    def test_applies_additional_search_text_and_pins(self) -> None:
        catalog = build_catalog(
            [_meta("azmcp_group_list", mcp_server_name="azure")],
            additional_search_text={"mcp:azure:azmcp_group_list": "棚卸し inventory"},
            pins={"mcp:azure:azmcp_group_list": "always"},
        )
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].additional_search_text, "棚卸し inventory")
        self.assertEqual(catalog[0].pin, "always")
    def test_deduplicates_by_id(self) -> None:
        catalog = build_catalog(
            [
                _meta("dup", mcp_server_name="azure"),
                _meta("dup", mcp_server_name="azure"),
            ]
        )
        self.assertEqual(len(catalog), 1)

    def test_bare_tool_name_key_does_not_apply(self) -> None:
        """FR-TS-03: ツール名だけのキーは効かない（別サーバーの同名ツールへの誤適用を防ぐ）。"""
        catalog = build_catalog(
            [_meta("list", mcp_server_name="azure")],
            pins={"list": "always"},
            additional_search_text={"list": "誤適用されてはならない"},
        )
        self.assertEqual(catalog[0].pin, "auto")
        self.assertEqual(catalog[0].additional_search_text, "")

    def test_server_wildcard_key_applies(self) -> None:
        catalog = build_catalog(
            [_meta("anything", mcp_server_name="azure")],
            pins={"mcp:azure:*": "never"},
        )
        self.assertEqual(catalog[0].pin, "never")


class TestResolvePolicyValue(unittest.TestCase):
    def test_exact_key_wins_over_wildcard(self) -> None:
        table = {"mcp:azure:x": "always", "mcp:azure:*": "never"}
        self.assertEqual(resolve_policy_value("mcp:azure:x", table), "always")

    def test_wildcard_is_scoped_to_its_server(self) -> None:
        table = {"mcp:azure:*": "never"}
        self.assertEqual(resolve_policy_value("mcp:other:x", table, "auto"), "auto")

    def test_returns_default_when_absent(self) -> None:
        self.assertEqual(resolve_policy_value("native:hve:x", {}, "auto"), "auto")


class TestPolicyDocument(unittest.TestCase):
    """FR-TS-03: policy.json の形式を固定する。"""

    def setUp(self) -> None:
        self.policy = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))

    def test_required_fields_present(self) -> None:
        for key in ("version", "limit", "max_limit", "tau", "field_weights",
                    "pins", "additional_search_text", "step_overrides"):
            self.assertIn(key, self.policy)

    def test_limits_follow_foundry_parity(self) -> None:
        self.assertEqual(self.policy["limit"], 5)
        self.assertEqual(self.policy["max_limit"], 10)
        self.assertLessEqual(self.policy["limit"], self.policy["max_limit"])

    def test_field_weights_cover_every_indexed_field(self) -> None:
        self.assertEqual(
            set(self.policy["field_weights"]),
            {"name", "additional_search_text", "description", "arg_terms"},
        )

    def test_all_keys_use_entry_id_or_server_wildcard(self) -> None:
        for table_name in ("pins", "additional_search_text"):
            for key in self.policy[table_name]:
                self.assertRegex(key, _POLICY_KEY_RE, msg=f"{table_name}.{key}")

    def test_pin_values_are_valid_modes(self) -> None:
        for key, value in self.policy["pins"].items():
            self.assertIn(value, ("always", "auto", "never"), msg=key)


if __name__ == "__main__":
    unittest.main()
