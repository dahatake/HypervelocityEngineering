"""FR-TS-09: Tool Search の実行時統計収集。

収集は best-effort（書けなくても Step を落とさない）で、検索専用語彙を記録しない。
集計は収集済みイベントだけから決定的に算出する。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.toolsearch.metatool import ToolSearchContext, search_catalog
from hve.toolsearch.policy import ToolSearchPolicy
from hve.toolsearch.stats import (
    EVENT_CATALOG,
    EVENT_MISS,
    EVENT_QUERY,
    SCHEMA_VERSION,
    DashboardSnapshot,
    StatsCollector,
    aggregate,
    default_events_path,
    load_events,
)
from hve.toolsearch.types import ToolEntry
from hve.toolsearch.usage import UsageRecord


def _policy() -> ToolSearchPolicy:
    return ToolSearchPolicy.load()


def _entry(name: str, description: str = "", *, pin: str = "auto") -> ToolEntry:
    return ToolEntry(
        id=ToolEntry.make_id("mcp", "azure", name),
        kind="mcp",
        server="azure",
        name=name,
        description=description or f"{name} description",
        additional_search_text="社外秘の検索語彙",
        pin=pin,  # type: ignore[arg-type]
    )


class _Meta:
    """SDK の `CurrentToolMetadata` 相当（属性アクセスのみ使われる）。"""

    def __init__(self, name: str, description: str = "", *, deferred: bool = True) -> None:
        self.name = name
        self.description = description or f"{name} description"
        self.defer_loading = deferred
        self.input_schema = {"properties": {"path": {"description": "ファイルパス"}}}
        self.mcp_server_name = "azure"
        self.mcp_tool_name = name
        self.namespaced_name = f"azure/{name}"


class TestEventsPath(unittest.TestCase):
    def test_default_path_is_repo_scoped(self) -> None:
        import os

        original = os.environ.pop("HVE_TOOLSEARCH_EVENTS", None)
        cwd = os.getcwd()
        try:
            with TemporaryDirectory() as tmp:
                os.chdir(tmp)
                try:
                    path = default_events_path()
                    self.assertEqual(path.name, "events.jsonl")
                    self.assertEqual(path.parent.name, ".toolsearch")
                    self.assertEqual(path.parent.parent, Path.cwd())
                finally:
                    os.chdir(cwd)
        finally:
            if original is not None:
                os.environ["HVE_TOOLSEARCH_EVENTS"] = original

    def test_default_path_accepts_an_explicit_repo_root(self) -> None:
        import os

        original = os.environ.pop("HVE_TOOLSEARCH_EVENTS", None)
        try:
            with TemporaryDirectory() as tmp:
                self.assertEqual(
                    default_events_path(repo_root=Path(tmp)),
                    Path(tmp) / ".toolsearch" / "events.jsonl",
                )
        finally:
            if original is not None:
                os.environ["HVE_TOOLSEARCH_EVENTS"] = original

    def test_environment_override(self) -> None:
        import os

        original = os.environ.get("HVE_TOOLSEARCH_EVENTS")
        os.environ["HVE_TOOLSEARCH_EVENTS"] = str(Path("x") / "y.jsonl")
        try:
            self.assertEqual(default_events_path(), Path("x") / "y.jsonl")
            # 明示 repo_root より環境変数が優先される（利用者の明示的な逃げ道）。
            self.assertEqual(default_events_path(repo_root=Path("z")), Path("x") / "y.jsonl")
        finally:
            if original is None:
                os.environ.pop("HVE_TOOLSEARCH_EVENTS", None)
            else:
                os.environ["HVE_TOOLSEARCH_EVENTS"] = original


class TestStatsCollector(unittest.TestCase):
    def test_is_usable_as_on_event_callback(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            collector = StatsCollector(path=path, run_id="r1")
            collector(EVENT_QUERY, {"query": "検索", "hits": ["a"]})
            events = load_events(path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], EVENT_QUERY)

    def test_records_schema_version_and_timestamp(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            StatsCollector(path=path, run_id="r1")(EVENT_QUERY, {"query": "q"})
            event = load_events(path)[0]
        self.assertEqual(event["schema_version"], SCHEMA_VERSION)
        self.assertTrue(event["ts"].endswith("Z"))

    def test_carries_run_id(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            StatsCollector(path=path, run_id="20260804-1")(EVENT_QUERY, {"query": "q"})
            self.assertEqual(load_events(path)[0]["run_id"], "20260804-1")

    def test_appends_rather_than_truncates(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            collector = StatsCollector(path=path, run_id="r1")
            collector(EVENT_QUERY, {"query": "1"})
            collector(EVENT_QUERY, {"query": "2"})
            self.assertEqual(len(load_events(path)), 2)

    def test_write_failure_is_swallowed(self) -> None:
        with TemporaryDirectory() as tmp:
            # ディレクトリを指定 → open に失敗するが例外を投げない。
            collector = StatsCollector(path=Path(tmp), run_id="r1")
            collector(EVENT_QUERY, {"query": "q"})

    def test_unknown_event_names_are_ignored(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            StatsCollector(path=path, run_id="r1")("something.else", {"query": "q"})
            self.assertEqual(load_events(path), ())

    def test_live_snapshot_without_rereading_the_file(self) -> None:
        with TemporaryDirectory() as tmp:
            collector = StatsCollector(path=Path(tmp) / "e.jsonl", run_id="r1")
            collector(EVENT_QUERY, {"query": "a", "hits": ["t1"]})
            collector(EVENT_QUERY, {"query": "b", "hits": []})
            collector(EVENT_MISS, {"query": "b"})
            snapshot = collector.snapshot()
        self.assertEqual(snapshot.queries, 2)
        self.assertEqual(snapshot.misses, 1)


class TestEventSchema(unittest.TestCase):
    """FR-TS-09: 検索専用語彙を記録しない。"""

    def _emit_one(self, tmp: str) -> dict:
        path = Path(tmp) / "events.jsonl"
        context = ToolSearchContext(
            policy=_policy(),
            skill_entries=(_entry("secret_tool", "リソースを一覧する"),),
            workflow_id="ard",
            step_id="1.1",
            on_event=StatsCollector(path=path, run_id="r1"),
        )
        search_catalog(context, [_Meta("azure_list")], "リソースを一覧したい")
        return next(e for e in load_events(path) if e["kind"] == EVENT_QUERY)

    def test_query_event_has_the_required_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            event = self._emit_one(tmp)
        for key in (
            "ts",
            "schema_version",
            "kind",
            "run_id",
            "workflow_id",
            "step_id",
            "query",
            "hits",
            "scores",
            "latency_ms",
            "catalog",
            "tokens",
            "warnings",
        ):
            self.assertIn(key, event, key)

    def test_catalog_breakdown_is_recorded(self) -> None:
        with TemporaryDirectory() as tmp:
            event = self._emit_one(tmp)
        catalog = event["catalog"]
        for key in ("total", "pinned", "searchable", "dropped", "deferred", "mcp", "native", "skill"):
            self.assertIn(key, catalog, key)

    def test_token_estimates_are_recorded(self) -> None:
        with TemporaryDirectory() as tmp:
            event = self._emit_one(tmp)
        self.assertIn("baseline", event["tokens"])
        self.assertIn("exposed", event["tokens"])
        self.assertGreater(event["tokens"]["baseline"], 0)

    def test_additional_search_text_is_never_recorded(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            context = ToolSearchContext(
                policy=_policy(),
                skill_entries=(_entry("secret_tool", "リソースを一覧する"),),
                on_event=StatsCollector(path=path, run_id="r1"),
            )
            search_catalog(context, [_Meta("azure_list")], "リソース")
            raw = path.read_text(encoding="utf-8")
        self.assertNotIn("社外秘の検索語彙", raw)

    def test_catalog_event_is_emitted_once_per_catalog(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            context = ToolSearchContext(
                policy=_policy(),
                skill_entries=(_entry("a"), _entry("b")),
                on_event=StatsCollector(path=path, run_id="r1"),
            )
            search_catalog(context, [_Meta("azure_list")], "q1")
            search_catalog(context, [_Meta("azure_list")], "q2")
            catalogs = [e for e in load_events(path) if e["kind"] == EVENT_CATALOG]
        self.assertEqual(len(catalogs), 1)

    def test_catalog_event_carries_entry_ids(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            context = ToolSearchContext(
                policy=_policy(),
                skill_entries=(_entry("a"),),
                on_event=StatsCollector(path=path, run_id="r1"),
            )
            search_catalog(context, [_Meta("azure_list")], "q")
            catalog = next(e for e in load_events(path) if e["kind"] == EVENT_CATALOG)
        self.assertIn("mcp:azure:a", catalog["entry_ids"])

    def test_latency_is_measured(self) -> None:
        with TemporaryDirectory() as tmp:
            event = self._emit_one(tmp)
        self.assertIsInstance(event["latency_ms"], float)
        self.assertGreaterEqual(event["latency_ms"], 0.0)


class TestLoadEvents(unittest.TestCase):
    def test_missing_file_yields_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertEqual(load_events(Path(tmp) / "nope.jsonl"), ())

    def test_broken_lines_are_dropped(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "e.jsonl"
            path.write_text(
                json.dumps({"kind": EVENT_QUERY, "ts": "2026-08-04T00:00:00Z"})
                + "\n{ not json\n\n",
                encoding="utf-8",
            )
            self.assertEqual(len(load_events(path)), 1)


def _query_event(**kwargs) -> dict:
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_QUERY,
        "ts": "2026-08-04T00:00:00Z",
        "run_id": "r1",
        "workflow_id": "ard",
        "step_id": "1.1",
        "query": "q",
        "limit": 5,
        "hits": ["t1"],
        "scores": [1.0],
        "latency_ms": 10.0,
        "catalog": {
            "total": 10,
            "pinned": 2,
            "searchable": 8,
            "dropped": 0,
            "deferred": 8,
            "mcp": 5,
            "native": 2,
            "skill": 3,
        },
        "tokens": {"baseline": 1000, "exposed": 300},
        "warnings": [],
    }
    base.update(kwargs)
    return base


class TestAggregate(unittest.TestCase):
    def test_empty_input_reports_no_data(self) -> None:
        snapshot = aggregate(())
        self.assertIsInstance(snapshot, DashboardSnapshot)
        self.assertEqual(snapshot.queries, 0)
        self.assertIsNone(snapshot.hit_rate)
        self.assertIsNone(snapshot.latency_p50_ms)

    def test_counts_queries_and_misses(self) -> None:
        events = (
            _query_event(),
            _query_event(hits=[], scores=[]),
            {"kind": EVENT_MISS, "ts": "2026-08-04T00:00:01Z", "query": "q2"},
        )
        snapshot = aggregate(events)
        self.assertEqual(snapshot.queries, 2)
        self.assertEqual(snapshot.misses, 1)
        self.assertAlmostEqual(snapshot.hit_rate or 0.0, 0.5)

    def test_latency_percentiles(self) -> None:
        events = tuple(_query_event(latency_ms=float(v)) for v in range(1, 101))
        snapshot = aggregate(events)
        self.assertAlmostEqual(snapshot.latency_p50_ms or 0.0, 50.5, places=1)
        self.assertGreater(snapshot.latency_p95_ms or 0.0, snapshot.latency_p50_ms or 0.0)

    def test_token_reduction_uses_the_latest_catalog(self) -> None:
        events = (_query_event(tokens={"baseline": 1000, "exposed": 250}),)
        snapshot = aggregate(events)
        self.assertAlmostEqual(snapshot.token_reduction or 0.0, 0.75)

    def test_deferral_inactive_rate(self) -> None:
        from hve.toolsearch.metatool import NO_DEFERRED_TOOLS_WARNING

        events = (
            _query_event(warnings=[NO_DEFERRED_TOOLS_WARNING]),
            _query_event(),
        )
        self.assertAlmostEqual(aggregate(events).deferral_inactive_rate or 0.0, 0.5)

    def test_other_warnings_do_not_count_as_inactive_deferral(self) -> None:
        """FR-TS-08 の警告以外を混ぜると指標の意味が壊れる。"""
        from hve.toolsearch.metatool import EMPTY_CATALOG_MESSAGE

        events = (_query_event(warnings=[EMPTY_CATALOG_MESSAGE]),)
        snapshot = aggregate(events)
        self.assertEqual(snapshot.deferral_inactive_rate, 0.0)
        self.assertEqual(snapshot.warnings[0][0], EMPTY_CATALOG_MESSAGE)

    def test_top_queries_and_tools_are_deterministic(self) -> None:
        events = (
            _query_event(query="a", hits=["t1"]),
            _query_event(query="a", hits=["t1", "t2"]),
            _query_event(query="b", hits=["t2"]),
        )
        snapshot = aggregate(events)
        self.assertEqual(snapshot.top_queries[0], ("a", 2))
        self.assertEqual(snapshot.top_hit_tools[0], ("t1", 2))

    def test_miss_queries_are_listed(self) -> None:
        events = (
            _query_event(),
            {"kind": EVENT_MISS, "ts": "2026-08-04T00:00:01Z", "query": "見つからない語"},
        )
        self.assertIn("見つからない語", [q for q, _ in aggregate(events).top_miss_queries])

    def test_never_hit_tools_need_a_catalog_event(self) -> None:
        events = (
            {
                "kind": EVENT_CATALOG,
                "ts": "2026-08-04T00:00:00Z",
                "entry_ids": ["mcp:azure:t1", "mcp:azure:t2"],
                "names": {"mcp:azure:t1": "t1", "mcp:azure:t2": "t2"},
            },
            _query_event(hits=["t1"]),
        )
        self.assertEqual(aggregate(events).never_hit_tools, ("t2",))

    def test_never_hit_tools_is_empty_without_a_catalog_event(self) -> None:
        self.assertEqual(aggregate((_query_event(),)).never_hit_tools, ())

    def test_scope_breakdown_by_workflow_step(self) -> None:
        events = (
            _query_event(workflow_id="ard", step_id="1.1"),
            _query_event(workflow_id="ard", step_id="1.2"),
            _query_event(workflow_id="ard", step_id="1.1"),
        )
        scopes = dict(aggregate(events).queries_by_scope)
        self.assertEqual(scopes["ard:1.1"], 2)
        self.assertEqual(scopes["ard:1.2"], 1)

    def test_autopin_progress_comes_from_usage_records(self) -> None:
        usage = tuple(
            UsageRecord(session_id=f"s{i}", workflow_id="ard", step_id="1.1", tool_id="mcp:azure:t1")
            for i in range(5)
        )
        snapshot = aggregate((_query_event(),), usage_records=usage)
        progress = {p.scope: p for p in snapshot.autopin_progress}
        self.assertEqual(progress["ard:1.1"].sessions, 5)
        self.assertEqual(progress["ard:1.1"].warmup_sessions, 20)
        self.assertEqual(progress["ard:1.1"].promoted, ())

    def test_adoption_rate_joins_hits_with_usage(self) -> None:
        events = (
            {
                "kind": EVENT_CATALOG,
                "ts": "2026-08-04T00:00:00Z",
                "entry_ids": ["mcp:azure:t1", "mcp:azure:t2"],
                "names": {"mcp:azure:t1": "t1", "mcp:azure:t2": "t2"},
            },
            _query_event(hits=["t1", "t2"]),
        )
        usage = (
            UsageRecord(session_id="s1", workflow_id="ard", step_id="1.1", tool_id="mcp:azure:t1"),
        )
        self.assertAlmostEqual(aggregate(events, usage_records=usage).adoption_rate or 0.0, 0.5)

    def test_adoption_rate_is_unknown_without_a_catalog_event(self) -> None:
        self.assertIsNone(aggregate((_query_event(),)).adoption_rate)

    def test_since_also_filters_the_usage_side_of_adoption(self) -> None:
        """窓を切ったのに「呼ばれた側」だけ全期間だと採用率が高く出る。"""
        events = (
            {
                "kind": EVENT_CATALOG,
                "ts": "2026-08-04T00:00:00Z",
                "entry_ids": ["mcp:azure:t1", "mcp:azure:t2"],
                "names": {"mcp:azure:t1": "t1", "mcp:azure:t2": "t2"},
            },
            _query_event(hits=["t1", "t2"]),
        )
        usage = (
            UsageRecord(
                session_id="old",
                workflow_id="ard",
                step_id="1.1",
                tool_id="mcp:azure:t1",
                ts="2026-07-01T00:00:00Z",
            ),
            UsageRecord(
                session_id="new",
                workflow_id="ard",
                step_id="1.1",
                tool_id="mcp:azure:t2",
                ts="2026-08-04T00:00:00Z",
            ),
        )
        windowed = aggregate(events, usage_records=usage, since="2026-08-01T00:00:00Z")
        self.assertAlmostEqual(windowed.adoption_rate or 0.0, 0.5)
        self.assertAlmostEqual(aggregate(events, usage_records=usage).adoption_rate or 0.0, 1.0)

    def test_undated_usage_is_excluded_when_a_window_is_given(self) -> None:
        """時刻を持たない旧レコードは窓の内側だと証明できないので数えない。"""
        events = (
            {
                "kind": EVENT_CATALOG,
                "ts": "2026-08-04T00:00:00Z",
                "entry_ids": ["mcp:azure:t1"],
                "names": {"mcp:azure:t1": "t1"},
            },
            _query_event(hits=["t1"]),
        )
        usage = (
            UsageRecord(
                session_id="legacy", workflow_id="ard", step_id="1.1", tool_id="mcp:azure:t1"
            ),
        )
        self.assertEqual(aggregate(events, usage_records=usage, since="2026-08-01T00:00:00Z").adoption_rate, 0.0)
        self.assertAlmostEqual(aggregate(events, usage_records=usage).adoption_rate or 0.0, 1.0)

    def test_snapshot_is_json_serialisable(self) -> None:
        json.dumps(aggregate((_query_event(),)).to_dict(), ensure_ascii=False)

    def test_window_filters_by_timestamp(self) -> None:
        events = (
            _query_event(ts="2026-08-01T00:00:00Z"),
            _query_event(ts="2026-08-04T00:00:00Z"),
        )
        snapshot = aggregate(events, since="2026-08-03T00:00:00Z")
        self.assertEqual(snapshot.queries, 1)

    def test_events_without_a_run_id_do_not_inflate_session_count(self) -> None:
        events = (
            _query_event(run_id="r1", step_id="1.1"),
            {"kind": EVENT_MISS, "ts": "2026-08-04T00:00:01Z", "query": "q"},
        )
        self.assertEqual(aggregate(events).sessions, 1)


class TestLiveBuffer(unittest.TestCase):
    def test_in_memory_buffer_is_bounded(self) -> None:
        from hve.toolsearch.stats import MAX_LIVE_EVENTS

        with TemporaryDirectory() as tmp:
            collector = StatsCollector(path=Path(tmp) / "e.jsonl", run_id="r1")
            for i in range(MAX_LIVE_EVENTS + 25):
                collector(EVENT_QUERY, {"query": str(i)})
            self.assertEqual(collector.snapshot().queries, MAX_LIVE_EVENTS)
            # ファイルには全件残る。
            self.assertEqual(len(load_events(Path(tmp) / "e.jsonl")), MAX_LIVE_EVENTS + 25)


if __name__ == "__main__":
    unittest.main()
