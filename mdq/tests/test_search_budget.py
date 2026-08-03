"""FR-MDQ-07: 応答トークン予算は返す機械可読表現で判定する。"""
from __future__ import annotations

import json
from pathlib import Path

from mdq import search as searcher, store, tokens

_TERM = "budgetneedle"
_BODY = "\n".join(f"line {i} with {_TERM} inside and some more words" for i in range(3))


def _store_with_hits(tmp_path: Path):
    conn = store.open_store(tmp_path / "index.sqlite", lang="ja-jp")
    store.upsert_file(conn, "docs/very/long/path/to/a/document.md", "sha", 1.0, 10, None)
    rows = [
        (
            f"c-hit-{i}",
            "docs/very/long/path/to/a/document.md",
            f"# Chapter {i} > ## Section {i} > ### Subsection {i}",
            3,
            1 + i * 5,
            3 + i * 5,
            30,
            _BODY,
            None,
        )
        for i in range(6)
    ]
    rows.extend(
        (
            f"c-filler-{i}",
            "docs/very/long/path/to/a/document.md",
            f"# Filler {i}",
            1,
            200 + i,
            200 + i,
            10,
            f"unrelated filler paragraph number {i}",
            None,
        )
        for i in range(10)
    )
    store.insert_chunks(conn, rows)
    conn.commit()
    return conn


def test_budget_counts_the_serialised_hit_not_only_the_excerpt(tmp_path: Path) -> None:
    conn = _store_with_hits(tmp_path)
    try:
        hits = searcher.search(conn, _TERM, top_k=6, max_tokens=400)
        payload = "\n".join(
            json.dumps(h.to_dict(), ensure_ascii=False) for h in hits
        )
        excerpt_only = "\n".join(h.snippet for h in hits)
        assert tokens.count_tokens(payload) <= 400
        assert tokens.count_tokens(payload) > tokens.count_tokens(excerpt_only)
    finally:
        conn.close()


def test_first_hit_survives_a_tiny_budget(tmp_path: Path) -> None:
    """FR-MDQ-03 と同じ規則: 予算超過でも先頭 1 件は必ず返す。"""
    conn = _store_with_hits(tmp_path)
    try:
        assert len(searcher.search(conn, _TERM, top_k=6, max_tokens=1)) == 1
    finally:
        conn.close()


def test_metadata_cost_reduces_the_number_of_hits(tmp_path: Path) -> None:
    """metadata を含めた分だけ、抜粋のみの算定より少ない件数で打ち切られる。"""
    conn = _store_with_hits(tmp_path)
    try:
        hits = searcher.search(conn, _TERM, top_k=6, max_tokens=400)
        excerpt_budget = sum(max(1, len(h.snippet) // 4) for h in hits)
        assert excerpt_budget < 400
        assert len(hits) < 6
    finally:
        conn.close()
