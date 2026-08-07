"""FR-TS-01 / FR-TS-08: tool_search_tool 差し替えハンドラのテスト。"""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

from hve.toolsearch.metatool import (
    EMPTY_CATALOG_MESSAGE,
    NO_DEFERRED_TOOLS_WARNING,
    TOOL_SEARCH_DESCRIPTION,
    ToolSearchContext,
    ToolSearchParams,
    build_tool_search_tool,
    decide_catalog,
    render_summary,
    search_catalog,
)
from hve.toolsearch.policy import ToolSearchPolicy
from hve.toolsearch.skill_catalog import SkillDescriptor, build_skill_entries
from hve.toolsearch.types import TOOL_SEARCH_TOOL_NAME, ToolCard, ToolEntry


def _meta(name: str, description: str = "", *, server: str | None = "azure", deferred: bool = True):
    return SimpleNamespace(
        name=name,
        description=description,
        mcp_server_name=server,
        mcp_tool_name=None,
        namespaced_name=None,
        input_schema=None,
        defer_loading=deferred,
    )


def _context(**overrides) -> ToolSearchContext:
    base = {"policy": ToolSearchPolicy.load()}
    base.update(overrides)
    return ToolSearchContext(**base)  # type: ignore[arg-type]


class TestDecideCatalog(unittest.TestCase):
    def test_merges_live_catalog_with_skill_entries(self) -> None:
        skills = build_skill_entries(
            (SkillDescriptor(name="azure-kusto", description="KQL を書く", path=Path("x")),)
        )
        decision, _ = decide_catalog(_context(skill_entries=skills), [_meta("azmcp_group_list", "list groups")])
        names = {e.name for e in decision.searchable}
        self.assertIn("azmcp_group_list", names)
        self.assertIn("skill_azure-kusto", names)

    def test_warns_when_nothing_is_deferred(self) -> None:
        _, warnings = decide_catalog(_context(), [_meta("x", "d", deferred=False)])
        self.assertIn(NO_DEFERRED_TOOLS_WARNING, warnings)

    def test_does_not_warn_when_deferral_is_active(self) -> None:
        _, warnings = decide_catalog(_context(), [_meta("x", "d", deferred=True)])
        self.assertEqual(warnings, ())

    def test_warns_when_the_snapshot_is_unavailable(self) -> None:
        _, warnings = decide_catalog(_context(), None)
        self.assertIn(EMPTY_CATALOG_MESSAGE, warnings)

    def test_excluded_tools_are_dropped(self) -> None:
        decision, _ = decide_catalog(
            _context(excluded_tools=("blocked",)),
            [_meta("blocked", "d"), _meta("ok", "d")],
        )
        self.assertEqual([e.name for e in decision.searchable], ["ok"])

    def test_fail_closed_step_returns_no_searchable_entries(self) -> None:
        context = _context(workflow_id="asdw-web", step_id="1.2")
        decision, _ = decide_catalog(context, [_meta("azmcp_group_list", "list groups")])
        self.assertEqual(decision.searchable, ())

    def test_normal_step_keeps_searchable_entries(self) -> None:
        context = _context(workflow_id="asdw-web", step_id="2.1")
        decision, _ = decide_catalog(context, [_meta("azmcp_group_list", "list groups")])
        self.assertNotEqual(decision.searchable, ())

    def test_manifest_pins_move_skills_into_the_pinned_set(self) -> None:
        skills = build_skill_entries(
            (SkillDescriptor(name="knowledge-management", description="d", path=Path("x")),)
        )
        context = _context(
            skill_entries=skills,
            manifest_pins={"skill:skills:skill_knowledge-management": "always"},
        )
        decision, _ = decide_catalog(context, [])
        self.assertIn("skill_knowledge-management", {e.name for e in decision.pinned})


class TestSearchCatalog(unittest.TestCase):
    CATALOG = [
        _meta("azmcp_group_list", "List Azure resource groups in a subscription"),
        _meta("azmcp_storage_blob_upload", "Upload a blob to Azure Storage"),
        _meta("send_mail", "メールを送信します"),
    ]

    def test_returns_tool_references_by_name(self) -> None:
        outcome = search_catalog(_context(), self.CATALOG, "resource groups")
        self.assertIn("azmcp_group_list", outcome.references)

    def test_japanese_query_works(self) -> None:
        outcome = search_catalog(_context(), self.CATALOG, "メールを送りたい")
        self.assertIn("send_mail", outcome.references)

    def test_respects_the_policy_limit_ceiling(self) -> None:
        outcome = search_catalog(_context(), self.CATALOG, "azure", limit=99)
        self.assertLessEqual(len(outcome.references), 10)

    def test_no_match_returns_empty_references_with_guidance(self) -> None:
        outcome = search_catalog(_context(), self.CATALOG, "zzz-nothing-matches-this-token")
        self.assertEqual(outcome.references, ())
        self.assertIn("No tool matched", outcome.summary)

    def test_missing_snapshot_is_reported_not_raised(self) -> None:
        outcome = search_catalog(_context(), None, "anything")
        self.assertEqual(outcome.references, ())
        self.assertIn(EMPTY_CATALOG_MESSAGE, outcome.summary)

    def test_events_are_emitted_for_queries_and_misses(self) -> None:
        seen: list[tuple[str, dict]] = []
        context = _context(on_event=lambda name, payload: seen.append((name, dict(payload))))
        search_catalog(context, self.CATALOG, "zzz-nothing-matches-this-token")
        kinds = [name for name, _ in seen]
        self.assertIn("toolsearch.query", kinds)
        self.assertIn("toolsearch.miss", kinds)

    def test_event_callback_failure_does_not_break_search(self) -> None:
        def _boom(_name, _payload):
            raise RuntimeError("journal is down")

        outcome = search_catalog(_context(on_event=_boom), self.CATALOG, "resource groups")
        self.assertIn("azmcp_group_list", outcome.references)


class TestRenderSummary(unittest.TestCase):
    def test_summary_never_contains_search_only_vocabulary(self) -> None:
        entry = ToolEntry(
            id="mcp:azure:x",
            kind="mcp",
            server="azure",
            name="x",
            description="desc",
            additional_search_text="秘匿すべき検索専用語彙",
        )
        summary = render_summary([ToolCard.from_entry(entry, 1.0)])
        self.assertNotIn("秘匿すべき検索専用語彙", summary)
        self.assertIn("desc", summary)

    def test_warnings_are_surfaced_first(self) -> None:
        summary = render_summary([], warnings=[NO_DEFERRED_TOOLS_WARNING], query="q")
        self.assertTrue(summary.startswith("warning: "))


class TestToolFactory(unittest.TestCase):
    def test_tool_overrides_the_builtin_by_name(self) -> None:
        tool = build_tool_search_tool(_context())
        self.assertEqual(tool.name, TOOL_SEARCH_TOOL_NAME)
        self.assertTrue(tool.overrides_built_in_tool)

    def test_tool_is_not_deferred_itself(self) -> None:
        tool = build_tool_search_tool(_context())
        self.assertIn(tool.defer, (None, "never"))

    def test_description_tells_the_model_to_search_before_giving_up(self) -> None:
        self.assertIn("before concluding", TOOL_SEARCH_DESCRIPTION)

    def test_handler_returns_tool_references(self) -> None:
        tool = build_tool_search_tool(_context())
        invocation = SimpleNamespace(
            arguments={"query": "resource groups"},
            available_tools=TestSearchCatalog.CATALOG,
        )
        result = asyncio.run(tool.handler(invocation))
        self.assertIn("azmcp_group_list", result.tool_references)
        self.assertIn("azmcp_group_list", result.text_result_for_llm)


class TestParamsSchema(unittest.TestCase):
    def test_query_is_required_and_limit_is_optional(self) -> None:
        params = ToolSearchParams(query="x")
        self.assertIsNone(params.limit)
        with self.assertRaises(Exception):
            ToolSearchParams()  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
