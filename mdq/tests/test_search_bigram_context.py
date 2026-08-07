"""FR-MDQ-08: 照合対象への path / 見出し重みの付与と、CJK bigram の適用。"""
from __future__ import annotations

from pathlib import Path

from mdq import search as searcher, store

_PATH_TERM = "pathonlyterm"
_TERM = "sharedterm"
_TWO_LINE_BODY = "filler line one\nfiller line two"


def _insert_fillers(rows: list, count: int = 10) -> None:
    """BM25 の IDF が退化しないだけの filler を置く（test_search_ranking と同理由）。"""
    rows.extend(
        (
            f"c-filler-{i}",
            "filler.md",
            f"# Filler {i}",
            1,
            10 + i,
            10 + i,
            10,
            f"unrelated filler paragraph number {i}",
            None,
        )
        for i in range(count)
    )


def _store_with_context(tmp_path: Path):
    conn = store.open_store(tmp_path / "index.sqlite", lang="ja-jp")
    for path in (f"{_PATH_TERM}.md", "heading.md", "body.md", "filler.md"):
        store.upsert_file(conn, path, "sha", 1.0, 10, None)
    rows = [
        # path にだけ対象語を持つ
        ("c-path", f"{_PATH_TERM}.md", "# plain section", 1, 1, 2, 20,
         _TWO_LINE_BODY, None),
        # 見出しにだけ対象語を持つ
        ("c-heading", "heading.md", f"# {_TERM}", 1, 1, 2, 20,
         _TWO_LINE_BODY, None),
        # 本文にだけ対象語を持つ（行数は c-heading と同じ）
        ("c-body", "body.md", "# plain section", 1, 1, 2, 20,
         f"{_TERM}\nfiller line two", None),
    ]
    _insert_fillers(rows)
    store.insert_chunks(conn, rows)
    conn.commit()
    return conn


def _store_with_japanese(tmp_path: Path):
    conn = store.open_store(tmp_path / "index.sqlite", lang="ja-jp")
    for path in ("member.md", "insurance.md", "filler.md"):
        store.upsert_file(conn, path, "sha", 1.0, 10, None)
    rows = [
        ("c-member", "member.md", "# 手順", 1, 1, 1, 20, "会員登録の手順", None),
        # 「会」と「員」を含むが「会員」という隣接 2 文字は現れない
        ("c-insurance", "insurance.md", "# 制度", 1, 1, 1, 20, "社会保険と委員会", None),
    ]
    _insert_fillers(rows)
    store.insert_chunks(conn, rows)
    conn.commit()
    return conn


def test_heading_weight_is_declared_as_a_single_constant() -> None:
    assert isinstance(searcher.HEADING_WEIGHT, int)
    assert searcher.HEADING_WEIGHT > 1


def test_term_present_only_in_the_path_reaches_the_chunk(tmp_path: Path) -> None:
    conn = _store_with_context(tmp_path)
    try:
        hits = searcher.search(conn, _PATH_TERM, top_k=5, max_tokens=100000)
        assert any(h.chunk_id == "c-path" for h in hits), [h.chunk_id for h in hits]
    finally:
        conn.close()


def test_heading_term_outranks_the_same_term_in_the_body(tmp_path: Path) -> None:
    conn = _store_with_context(tmp_path)
    try:
        hits = searcher.search(conn, _TERM, top_k=5, max_tokens=100000)
        scores = {h.chunk_id: h.score for h in hits}
        assert "c-heading" in scores and "c-body" in scores, scores
        assert scores["c-heading"] > scores["c-body"], scores
    finally:
        conn.close()


def test_path_and_heading_do_not_leak_into_the_excerpt(tmp_path: Path) -> None:
    conn = _store_with_context(tmp_path)
    try:
        hits = searcher.search(conn, _PATH_TERM, top_k=5, max_tokens=100000)
        hit = next(h for h in hits if h.chunk_id == "c-path")
        assert _PATH_TERM not in hit.snippet
        assert "plain section" not in hit.snippet
    finally:
        conn.close()


def test_line_range_is_unchanged_by_the_added_context(tmp_path: Path) -> None:
    conn = _store_with_context(tmp_path)
    try:
        hits = searcher.search(conn, _TERM, top_k=5, max_tokens=100000)
        hit = next(h for h in hits if h.chunk_id == "c-heading")
        assert [hit.start_line, hit.end_line] == [1, 2]
    finally:
        conn.close()


def test_grep_mode_ignores_the_path_and_the_heading(tmp_path: Path) -> None:
    conn = _store_with_context(tmp_path)
    try:
        hits = searcher.search(conn, _PATH_TERM, mode="grep", top_k=5,
                               max_tokens=100000)
        assert [h.chunk_id for h in hits] == []
    finally:
        conn.close()


def test_cjk_bigram_excludes_a_chunk_that_only_shares_single_characters(
    tmp_path: Path,
) -> None:
    conn = _store_with_japanese(tmp_path)
    try:
        hits = searcher.search(conn, "会員", top_k=5, max_tokens=100000)
        ids = [h.chunk_id for h in hits]
        assert "c-member" in ids, ids
        assert "c-insurance" not in ids, ids
    finally:
        conn.close()
