"""FR-TS-07: 利用履歴に基づく自動 pin（workflow × step 単位の決定論）。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.toolsearch.policy import ToolSearchPolicy, apply_policy
from hve.toolsearch.types import ToolEntry
from hve.toolsearch.usage import (
    DEFAULT_TOP_N,
    DEFAULT_WARMUP_SESSIONS,
    UsageRecord,
    auto_pins,
    default_usage_path,
    load_usage,
    record_usage,
    session_count,
)

_BASE_POLICY = {
    "version": 1,
    "limit": 5,
    "max_limit": 10,
    "tau": 0.4,
    "field_weights": {"name": 3.0, "additional_search_text": 2.5, "description": 2.0, "arg_terms": 1.0},
    "pins": {},
    "additional_search_text": {},
    "step_overrides": {},
}


def _records(sessions: int, tools_per_session: dict[int, list[str]] | None = None) -> list[UsageRecord]:
    out: list[UsageRecord] = []
    for index in range(sessions):
        tools = (tools_per_session or {}).get(index, ["mcp:azure:a"])
        for tool_id in tools:
            out.append(
                UsageRecord(
                    session_id=f"s{index:03d}",
                    workflow_id="asdw-web",
                    step_id="2.1",
                    tool_id=tool_id,
                )
            )
    return out


def _entry(name: str) -> ToolEntry:
    return ToolEntry(
        id=ToolEntry.make_id("mcp", "azure", name),
        kind="mcp",
        server="azure",
        name=name,
        description="d",
    )


class TestRecordAndLoad(unittest.TestCase):
    def test_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            written = record_usage(
                ["mcp:azure:a", "mcp:azure:b"],
                session_id="s1",
                workflow_id="asdw-web",
                step_id="2.1",
                path=path,
            )
            self.assertEqual(written, 2)
            records = load_usage(path)
        self.assertEqual([r.tool_id for r in records], ["mcp:azure:a", "mcp:azure:b"])
        self.assertEqual(records[0].scope, "asdw-web:2.1")

    def test_duplicate_tool_ids_are_recorded_once_per_session(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            written = record_usage(
                ["mcp:azure:a", "mcp:azure:a"],
                session_id="s1",
                workflow_id="w",
                step_id="1",
                path=path,
            )
        self.assertEqual(written, 1)

    def test_empty_input_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            self.assertEqual(record_usage([], session_id="s", workflow_id="w", step_id="1", path=path), 0)
            self.assertFalse(path.exists())

    def test_missing_file_loads_as_empty(self) -> None:
        self.assertEqual(load_usage(Path("nope-usage-xyz.jsonl")), ())

    def test_records_carry_a_timestamp(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            record_usage(["mcp:azure:a"], session_id="s", workflow_id="w", step_id="1", path=path)
            record = load_usage(path)[0]
        self.assertTrue(record.ts.endswith("Z"))

    def test_legacy_records_without_a_timestamp_still_load(self) -> None:
        """時刻は後から足したフィールドなので、既存の履歴を捨てない。"""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "session_id": "s",
                        "workflow_id": "w",
                        "step_id": "1",
                        "tool_id": "mcp:azure:a",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            record = load_usage(path)[0]
        self.assertEqual(record.ts, "")
        self.assertEqual(record.tool_id, "mcp:azure:a")

    def test_corrupt_lines_are_skipped(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            path.write_text(
                "not json\n"
                + json.dumps({"session_id": "s", "workflow_id": "w", "step_id": "1", "tool_id": "t"})
                + "\n{}\n",
                encoding="utf-8",
            )
            records = load_usage(path)
        self.assertEqual([r.tool_id for r in records], ["t"])

    def test_unwritable_path_is_best_effort(self) -> None:
        # 既存ファイルをディレクトリ扱いさせて OSError を誘発する。
        with TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("x", encoding="utf-8")
            self.assertEqual(
                record_usage(["t"], session_id="s", workflow_id="w", step_id="1", path=blocker / "usage.jsonl"),
                0,
            )

    def test_default_path_is_repo_scoped(self) -> None:
        import os

        original = os.environ.pop("HVE_TOOLSEARCH_USAGE", None)
        cwd = os.getcwd()
        try:
            with TemporaryDirectory() as tmp:
                os.chdir(tmp)
                try:
                    path = default_usage_path()
                    self.assertEqual(path.name, "usage.jsonl")
                    self.assertEqual(path.parent.name, ".toolsearch")
                    self.assertEqual(path.parent.parent, Path.cwd())
                finally:
                    os.chdir(cwd)
            with TemporaryDirectory() as tmp:
                self.assertEqual(
                    default_usage_path(repo_root=Path(tmp)),
                    Path(tmp) / ".toolsearch" / "usage.jsonl",
                )
        finally:
            if original is not None:
                os.environ["HVE_TOOLSEARCH_USAGE"] = original

    def test_default_path_can_be_overridden_by_env(self) -> None:
        import os

        original = os.environ.get("HVE_TOOLSEARCH_USAGE")
        os.environ["HVE_TOOLSEARCH_USAGE"] = "C:/tmp/custom-usage.jsonl"
        try:
            self.assertEqual(default_usage_path(), Path("C:/tmp/custom-usage.jsonl"))
            self.assertEqual(
                default_usage_path(repo_root=Path("z")), Path("C:/tmp/custom-usage.jsonl")
            )
        finally:
            if original is None:
                del os.environ["HVE_TOOLSEARCH_USAGE"]
            else:
                os.environ["HVE_TOOLSEARCH_USAGE"] = original


class TestWarmup(unittest.TestCase):
    def test_below_warmup_yields_no_auto_pins(self) -> None:
        self.assertEqual(auto_pins(_records(DEFAULT_WARMUP_SESSIONS - 1), "asdw-web", "2.1"), ())

    def test_at_warmup_promotes(self) -> None:
        self.assertEqual(auto_pins(_records(DEFAULT_WARMUP_SESSIONS), "asdw-web", "2.1"), ("mcp:azure:a",))

    def test_session_count_is_by_distinct_session_id(self) -> None:
        self.assertEqual(session_count(_records(3), "asdw-web", "2.1"), 3)


class TestScoping(unittest.TestCase):
    def test_other_scopes_are_ignored(self) -> None:
        self.assertEqual(auto_pins(_records(30), "asdw-web", "9.9"), ())

    def test_missing_scope_yields_no_pins(self) -> None:
        self.assertEqual(auto_pins(_records(30), None, None), ())

    def test_empty_history_yields_no_pins(self) -> None:
        self.assertEqual(auto_pins([], "asdw-web", "2.1"), ())


class TestPromotionRanking(unittest.TestCase):
    def test_promotes_at_most_top_n(self) -> None:
        history = _records(25, {i: [f"mcp:azure:t{j}" for j in range(6)] for i in range(25)})
        self.assertEqual(len(auto_pins(history, "asdw-web", "2.1")), DEFAULT_TOP_N)

    def test_more_frequent_tools_win(self) -> None:
        history = _records(
            25,
            {i: (["mcp:azure:hot"] if i % 1 == 0 else []) + (["mcp:azure:cold"] if i < 3 else []) for i in range(25)},
        )
        self.assertEqual(auto_pins(history, "asdw-web", "2.1")[0], "mcp:azure:hot")

    def test_ties_are_broken_deterministically_by_id(self) -> None:
        history = _records(25, {i: ["mcp:azure:b", "mcp:azure:a"] for i in range(25)})
        first = auto_pins(history, "asdw-web", "2.1")
        second = auto_pins(list(reversed(history)), "asdw-web", "2.1")
        self.assertEqual(first, second)
        self.assertEqual(first[0], "mcp:azure:a")

    def test_result_is_stable_across_repeated_calls(self) -> None:
        history = _records(25, {i: ["mcp:azure:a", "mcp:azure:b"] for i in range(25)})
        self.assertEqual(auto_pins(history, "asdw-web", "2.1"), auto_pins(history, "asdw-web", "2.1"))


class TestExpiry(unittest.TestCase):
    def test_old_sessions_fall_out_of_the_window(self) -> None:
        history = _records(
            60,
            {i: (["mcp:azure:old"] if i < 10 else ["mcp:azure:new"]) for i in range(60)},
        )
        promoted = auto_pins(history, "asdw-web", "2.1", window_sessions=20)
        self.assertIn("mcp:azure:new", promoted)
        self.assertNotIn("mcp:azure:old", promoted)


class TestAutoPinPrecedence(unittest.TestCase):
    """FR-TS-03: auto pin は policy.pins の明示指定を上書きしない。"""

    def _policy(self, **overrides) -> ToolSearchPolicy:
        raw = dict(_BASE_POLICY)
        raw.update(overrides)
        return ToolSearchPolicy.from_dict(raw)

    def test_auto_entry_is_promoted(self) -> None:
        decision = apply_policy([_entry("a")], self._policy(), auto_pins=["mcp:azure:a"])
        self.assertEqual([e.name for e in decision.pinned], ["a"])

    def test_never_is_not_promoted(self) -> None:
        decision = apply_policy(
            [_entry("a")],
            self._policy(pins={"mcp:azure:a": "never"}),
            auto_pins=["mcp:azure:a"],
        )
        self.assertEqual(decision.pinned, ())
        self.assertEqual([e.name for e in decision.searchable], ["a"])

    def test_manifest_pin_still_wins(self) -> None:
        decision = apply_policy(
            [_entry("a")],
            self._policy(pins={"mcp:azure:a": "never"}),
            manifest_pins={"mcp:azure:a": "always"},
            auto_pins=[],
        )
        self.assertEqual([e.name for e in decision.pinned], ["a"])

    def test_unpromoted_entries_stay_searchable(self) -> None:
        decision = apply_policy([_entry("a"), _entry("b")], self._policy(), auto_pins=["mcp:azure:a"])
        self.assertEqual([e.name for e in decision.searchable], ["b"])


if __name__ == "__main__":
    unittest.main()
