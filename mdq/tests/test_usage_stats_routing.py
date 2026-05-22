"""Tests for H1/H2 metrics aggregation in usage_stats."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mdq import usage_stats


def _make_record(args: dict, result: dict | None = None) -> dict:
    return {
        "ts": "2026-01-01T00:00:00+00:00",
        "command": "search",
        "args": args,
        "elapsed_ms": 10,
        "result": result or {"hit_count": 1, "snippet_chars": 100,
                              "source_file_chars": 1000},
        "exit_code": 0,
    }


def test_h1_distribution_and_fallback(tmp_path: Path) -> None:
    records = [
        _make_record({"q": "D03", "strategy": "auto",
                      "effective_strategy": "heading",
                      "router_reason": "id_lookup",
                      "router_rule_id": 1,
                      "router_fallback_used": False}),
        _make_record({"q": "概要", "strategy": "auto",
                      "effective_strategy": "heading",
                      "router_reason": "concept_overview",
                      "router_rule_id": 4,
                      "router_fallback_used": False}),
        _make_record({"q": "how", "strategy": "auto",
                      "effective_strategy": "heading_recursive",
                      "router_reason": "narrative_query",
                      "router_rule_id": 5,
                      "router_fallback_used": True}),
        _make_record({"q": "manual", "strategy": "heading"}),  # not auto
    ]
    out = usage_stats._group_routing(records)
    h1 = out["H1_auto_strategy_distribution"]
    assert h1["total_auto_search"] == 3
    assert h1["fallback_count"] == 1
    assert abs(h1["fallback_rate"] - 1 / 3) < 1e-3
    assert "id_lookup" in h1["by_reason"]
    assert h1["by_reason"]["id_lookup"]["count"] == 1
    assert h1["by_effective_strategy"]["heading"]["count"] == 2


def test_h1_empty_returns_none(tmp_path: Path) -> None:
    out = usage_stats._group_routing([])
    h1 = out["H1_auto_strategy_distribution"]
    assert h1["value"] is None
    assert h1["total_auto_search"] == 0


def test_h2_parent_expansion(tmp_path: Path) -> None:
    records = [
        _make_record(
            {"q": "x", "with_parent_depth": 1, "include_parent": True},
            {"hit_count": 5, "snippet_chars": 0, "source_file_chars": 0,
             "parent_expanded": 3},
        ),
        _make_record(
            {"q": "y", "with_parent_depth": 2, "include_parent": False},
            {"hit_count": 4, "snippet_chars": 0, "source_file_chars": 0,
             "parent_expanded": 4},
        ),
        _make_record(
            {"q": "z", "include_parent": True, "with_parent_depth": 0},
            {"hit_count": 2, "snippet_chars": 0, "source_file_chars": 0,
             # No parent_expanded => 0
             },
        ),
        _make_record({"q": "no parent", "include_parent": False,
                      "with_parent_depth": 0}),  # ignored
    ]
    out = usage_stats._group_routing(records)
    h2 = out["H2_parent_expansion_rate"]
    assert h2["total_parent_requests"] == 3
    assert h2["expanded_hits"] == 7
    assert h2["total_hits_in_parent_requests"] == 5 + 4 + 2
    # 2 of 3 requests had >0 parent_expanded
    assert abs(h2["request_expanded_rate"] - 2 / 3) < 1e-3
    assert abs(h2["hit_expanded_rate"] - 7 / 11) < 1e-3


def test_aggregate_schema_version_is_2(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = usage_stats.aggregate_usage_stats(repo, records=[])
    assert result["schema_version"] == 2
    assert "H1_auto_strategy_distribution" in result
    assert "H2_parent_expansion_rate" in result
