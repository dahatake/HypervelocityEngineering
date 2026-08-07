"""FR-MDQ-10: 本文を含めない返却単位。"""
from __future__ import annotations

from pathlib import Path

from mdq import search as searcher, store

_TERM = "locationsneedle"
_BODY = "\n".join(
    f"line {i} mentions {_TERM} and some more words to pad the chunk"
    for i in range(6)
)


def _store_with_hits(tmp_path: Path):
    conn = store.open_store(tmp_path / "index.sqlite", lang="ja-jp")
    store.upsert_file(conn, "docs/deep/path/to/a/document.md", "sha", 1.0, 10, None)
    rows = [
        (
            f"c-hit-{i}",
            "docs/deep/path/to/a/document.md",
            f"# Chapter {i} > ## Section {i}",
            2,
            1 + i * 10,
            6 + i * 10,
            40,
            _BODY,
            None,
        )
        for i in range(8)
    ]
    rows.extend(
        (
            f"c-filler-{i}",
            "docs/deep/path/to/a/document.md",
            f"# Filler {i}",
            1,
            200 + i,
            200 + i,
            10,
            f"unrelated filler paragraph number {i}",
            None,
        )
        for i in range(12)
    )
    store.insert_chunks(conn, rows)
    conn.commit()
    return conn


def test_locations_unit_omits_the_snippet(tmp_path: Path) -> None:
    conn = _store_with_hits(tmp_path)
    try:
        hits = searcher.search(conn, _TERM, top_k=3, max_tokens=100000,
                               return_unit="locations")
        assert hits
        for hit in hits:
            assert "snippet" not in hit.to_dict()
    finally:
        conn.close()


def test_locations_unit_keeps_the_location_fields(tmp_path: Path) -> None:
    conn = _store_with_hits(tmp_path)
    try:
        hit = searcher.search(conn, _TERM, top_k=1, max_tokens=100000,
                              return_unit="locations")[0].to_dict()
        assert set(hit) == {"chunk_id", "path", "heading_path", "lines", "score"}
        assert hit["lines"] == [1, 6] or len(hit["lines"]) == 2
    finally:
        conn.close()


def test_default_unit_still_returns_a_snippet(tmp_path: Path) -> None:
    conn = _store_with_hits(tmp_path)
    try:
        hit = searcher.search(conn, _TERM, top_k=1, max_tokens=100000)[0].to_dict()
        assert hit["snippet"]
    finally:
        conn.close()


def test_ranking_matches_the_line_unit_with_a_generous_budget(
    tmp_path: Path,
) -> None:
    conn = _store_with_hits(tmp_path)
    try:
        line = searcher.search(conn, _TERM, top_k=5, max_tokens=100000)
        loc = searcher.search(conn, _TERM, top_k=5, max_tokens=100000,
                              return_unit="locations")
        assert [h.chunk_id for h in loc] == [h.chunk_id for h in line]
    finally:
        conn.close()


def test_same_budget_returns_at_least_as_many_hits(tmp_path: Path) -> None:
    conn = _store_with_hits(tmp_path)
    try:
        line = searcher.search(conn, _TERM, top_k=8, max_tokens=800)
        loc = searcher.search(conn, _TERM, top_k=8, max_tokens=800,
                              return_unit="locations")
        assert len(loc) > len(line), (len(loc), len(line))
    finally:
        conn.close()


def test_returned_identifier_resolves_with_get_chunk(tmp_path: Path) -> None:
    conn = _store_with_hits(tmp_path)
    try:
        hit = searcher.search(conn, _TERM, top_k=1, max_tokens=100000,
                              return_unit="locations")[0]
        chunk = searcher.get_chunk(conn, hit.chunk_id)
        assert chunk and chunk.get("text")
    finally:
        conn.close()


def test_expansion_carries_no_body_in_the_locations_unit(tmp_path: Path) -> None:
    conn = _store_with_hits(tmp_path)
    try:
        hits = searcher.search(conn, _TERM, top_k=3, max_tokens=100000,
                               return_unit="locations", expand_neighbors=1)
        expanded = [h for h in hits if h.expansion]
        assert expanded, "近傍拡張が 1 件も付与されていない"
        for hit in expanded:
            for entries in hit.expansion.values():
                rows = entries if isinstance(entries, list) else [entries]
                for row in rows:
                    assert "text" not in row, row
                    assert {"chunk_id", "path", "lines"} <= set(row)
    finally:
        conn.close()


def test_cli_accepts_the_locations_unit() -> None:
    from mdq import cli

    args = cli.build_parser().parse_args(
        ["search", "--q", "x", "--return-unit", "locations"]
    )
    assert args.return_unit == "locations"
