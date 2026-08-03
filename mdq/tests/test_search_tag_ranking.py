"""Regression tests for exact machine-tag ranking (FR-CQ-12 / INV-01)."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from mdq import indexer, search as searcher, store


def _index_feature_inventory(tmp_path: Path):
    repo = tmp_path / "repo"
    target = repo / "hve-dev" / "hve-feature-inventory.csv"
    target.parent.mkdir(parents=True)
    rows = [{
        "feature_kind": "FR",
        "feature_id": "FR-MDQ-01",
        "active_status": "active-or-described",
        "details": "canonical requirement row",
    }]
    rows.extend({
        "feature_kind": "FR",
        "feature_id": f"FR-NOISE-{number:02d}",
        "active_status": "active-or-described",
        "details": (
            "FR-MDQ-01 active requirement inventory reference " * (number + 1)
        ).strip(),
    } for number in range(8))
    rows.extend({
        "feature_kind": "FR",
        "feature_id": f"FR-OTHER-{number:02d}",
        "active_status": "active-or-described",
        "details": "unrelated workflow configuration",
    } for number in range(20))
    with target.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    conn = store.open_store(tmp_path / "index.sqlite", lang="ja-jp")
    indexer.build_index(
        repo,
        [],
        conn,
        rebuild=True,
        tabular_globs=["hve-dev/hve-feature-inventory.csv"],
    )
    return conn


@pytest.mark.parametrize("engine", ["bm25", "fts5"])
def test_exact_identifier_tag_outranks_repeated_body_references(
    tmp_path: Path, engine: str
) -> None:
    conn = _index_feature_inventory(tmp_path)
    try:
        if engine == "fts5" and not store.has_fts5(conn):
            pytest.skip("SQLite build does not provide FTS5")
        hits = searcher.search(
            conn,
            "FR-MDQ-01 active requirement inventory",
            mode="bm25",
            engine=engine,
            top_k=5,
            max_tokens=5000,
        )
        assert hits
        assert "feature_id=FR-MDQ-01" in hits[0].heading_path
    finally:
        conn.close()


def test_generic_tag_values_do_not_receive_identifier_priority() -> None:
    tags = '["feature_kind=FR", "active_status=active-or-described"]'
    assert searcher._exact_identifier_tag_priority(
        tags, "active requirement inventory"
    ) == 0


def test_exact_identifier_tag_matching_is_case_insensitive() -> None:
    tags = '["feature_id=FR-MDQ-01"]'
    assert searcher._exact_identifier_tag_priority(tags, "fr-mdq-01 details") == 1


def test_exact_identifier_tag_priority_applies_to_grep_results(tmp_path: Path) -> None:
    conn = _index_feature_inventory(tmp_path)
    try:
        hits = searcher.search(
            conn,
            "FR-MDQ-01",
            mode="grep",
            top_k=5,
            max_tokens=5000,
        )
        assert hits
        assert "feature_id=FR-MDQ-01" in hits[0].heading_path
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("tags", "query", "expected"),
    [
        ('["feature_id=FR_MDQ_01"]', "FR_MDQ_01 details", 1),
        ('["feature_id=FR-MDQ-01"]', "XFR-MDQ-01 details", 0),
        ('["feature_id="]', "details", 0),
        ('["malformed"]', "malformed", 0),
        ("not-json", "FR-MDQ-01", 0),
    ],
)
def test_identifier_priority_boundaries_and_malformed_tags(
    tags: str, query: str, expected: int
) -> None:
    assert searcher._exact_identifier_tag_priority(tags, query) == expected


def test_scored_ties_use_chunk_id_as_final_deterministic_key() -> None:
    scored = [
        (1.0, {"tags": "[]", "path": "same", "start_line": 1, "chunk_id": "b"}),
        (1.0, {"tags": "[]", "path": "same", "start_line": 1, "chunk_id": "a"}),
    ]
    searcher._sort_scored(scored, "query")
    assert [row["chunk_id"] for _, row in scored] == ["a", "b"]
