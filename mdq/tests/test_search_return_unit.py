"""FR-MDQ-03: 検索応答の返却単位を呼び出し側が選べること。

既定はヒット行を中心とする行範囲（Context Window 消費の最小化）。
チャンク単位を選ぶと、ヒットを含むチャンクの本文全体を切り詰めずに返す。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mdq import cli as mdq_cli, search as searcher, store

_NEEDLE = "returnunitneedle"
# 400 字（既定の snippet 上限）を確実に超え、ヒット行の前後にも行があるチャンク。
_LONG_BODY = "\n".join(
    [f"filler line {i} " + "x" * 40 for i in range(10)]
    + [f"target line with {_NEEDLE} inside"]
    + [f"trailer line {i} " + "y" * 40 for i in range(10)]
)
_OTHER = "\n".join(f"another chunk {i} {_NEEDLE} tail" for i in range(3))


def _store_with_long_chunks(tmp_path: Path):
    conn = store.open_store(tmp_path / "index.sqlite", lang="ja-jp")
    store.upsert_file(conn, "a.md", "sha", 1.0, 10, None)
    rows = [
        ("c-long", "a.md", "# Long", 1, 1, 21, 200, _LONG_BODY, None),
        ("c-other", "a.md", "# Other", 1, 30, 32, 20, _OTHER, None),
    ]
    # BM25 の IDF は語が文書の半数超に現れると負になり、mdq は非正スコアを
    # 落とす。ヒットを含まない文書を十分に置いて退化を避ける。
    rows.extend(
        (f"c-filler-{i}", "a.md", f"# Filler {i}", 1, 100 + i, 100 + i, 10,
         f"unrelated filler paragraph number {i} without the token", None)
        for i in range(10)
    )
    store.insert_chunks(conn, rows)
    conn.commit()
    return conn


def test_default_return_unit_is_a_line_window(tmp_path: Path) -> None:
    conn = _store_with_long_chunks(tmp_path)
    try:
        hits = searcher.search(conn, _NEEDLE, top_k=5, max_tokens=100000)
        long_hit = next(h for h in hits if h.chunk_id == "c-long")
        assert _NEEDLE in long_hit.snippet
        assert long_hit.snippet != _LONG_BODY
        assert len(long_hit.snippet) <= 400
    finally:
        conn.close()


def test_chunk_unit_returns_the_whole_chunk_body(tmp_path: Path) -> None:
    conn = _store_with_long_chunks(tmp_path)
    try:
        hits = searcher.search(
            conn, _NEEDLE, top_k=5, max_tokens=100000, return_unit="chunk"
        )
        long_hit = next(h for h in hits if h.chunk_id == "c-long")
        assert long_hit.snippet == _LONG_BODY
        assert len(long_hit.snippet) > 400, "400 字の切り詰めが残っている"
    finally:
        conn.close()


def test_ranking_is_identical_across_units(tmp_path: Path) -> None:
    """単位は抜粋の広さだけを変え、順位や対象チャンクを変えないこと。"""
    conn = _store_with_long_chunks(tmp_path)
    try:
        line = searcher.search(conn, _NEEDLE, top_k=5, max_tokens=100000)
        chunk = searcher.search(
            conn, _NEEDLE, top_k=5, max_tokens=100000, return_unit="chunk"
        )
        assert [h.chunk_id for h in line] == [h.chunk_id for h in chunk]
        assert [round(h.score, 6) for h in line] == [round(h.score, 6) for h in chunk]
    finally:
        conn.close()


def test_first_hit_survives_a_tiny_budget(tmp_path: Path) -> None:
    conn = _store_with_long_chunks(tmp_path)
    try:
        hits = searcher.search(
            conn, _NEEDLE, top_k=5, max_tokens=1, return_unit="chunk"
        )
        assert len(hits) == 1
    finally:
        conn.close()


def test_chunk_unit_never_returns_more_hits_than_line_unit(tmp_path: Path) -> None:
    """同一予算では抜粋が長い分だけ件数が減る（増えてはならない）。"""
    conn = _store_with_long_chunks(tmp_path)
    try:
        line = searcher.search(conn, _NEEDLE, top_k=5, max_tokens=120)
        chunk = searcher.search(
            conn, _NEEDLE, top_k=5, max_tokens=120, return_unit="chunk"
        )
        assert len(chunk) <= len(line)
    finally:
        conn.close()


def test_return_unit_applies_on_the_fts5_path(tmp_path: Path) -> None:
    conn = _store_with_long_chunks(tmp_path)
    try:
        if not store.has_fts5(conn):
            pytest.skip("SQLite build does not provide FTS5")
        hits = searcher.search(
            conn, _NEEDLE, top_k=5, max_tokens=100000,
            engine="fts5", return_unit="chunk",
        )
        long_hit = next(h for h in hits if h.chunk_id == "c-long")
        assert long_hit.snippet == _LONG_BODY
    finally:
        conn.close()


def test_cli_exposes_return_unit_defaulting_to_line() -> None:
    parser = mdq_cli.build_parser()
    args = parser.parse_args(["search", "--q", "x"])
    assert args.return_unit == "line"
    args = parser.parse_args(["search", "--q", "x", "--return-unit", "chunk"])
    assert args.return_unit == "chunk"
    with pytest.raises(SystemExit):
        parser.parse_args(["search", "--q", "x", "--return-unit", "bogus"])
