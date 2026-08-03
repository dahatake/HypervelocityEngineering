"""FR-MDQ-05 / FR-MDQ-06: ランキングの語彙照合対象と文書長正規化。"""
from __future__ import annotations

from pathlib import Path

from mdq import search as searcher, store

_HEADING_TERM = "headingonlyterm"
_BODY = "\n".join(
    [
        "first body line about unrelated matters",
        "second body line about unrelated matters",
        "third body line about unrelated matters",
    ]
)


def _store_with_heading_only_term(tmp_path: Path):
    """見出しにだけ ``_HEADING_TERM`` を持つチャンクと、十分な数の filler。

    BM25 の IDF は語が文書の半数超に現れると負になるため、filler を置いて
    退化を避ける（`test_search_return_unit.py` と同じ理由）。
    """
    conn = store.open_store(tmp_path / "index.sqlite", lang="ja-jp")
    store.upsert_file(conn, "a.md", "sha", 1.0, 10, None)
    rows = [
        ("c-target", "a.md", f"# {_HEADING_TERM} section", 1, 1, 3, 20, _BODY, None),
    ]
    rows.extend(
        (
            f"c-filler-{i}",
            "a.md",
            f"# Filler {i}",
            1,
            10 + i,
            10 + i,
            10,
            f"unrelated filler paragraph number {i}",
            None,
        )
        for i in range(10)
    )
    store.insert_chunks(conn, rows)
    conn.commit()
    return conn


def test_term_present_only_in_the_heading_reaches_the_chunk(tmp_path: Path) -> None:
    conn = _store_with_heading_only_term(tmp_path)
    try:
        hits = searcher.search(conn, _HEADING_TERM, top_k=5, max_tokens=100000)
        assert any(h.chunk_id == "c-target" for h in hits), [h.chunk_id for h in hits]
    finally:
        conn.close()


def test_heading_text_does_not_leak_into_the_excerpt(tmp_path: Path) -> None:
    conn = _store_with_heading_only_term(tmp_path)
    try:
        hits = searcher.search(conn, _HEADING_TERM, top_k=5, max_tokens=100000)
        hit = next(h for h in hits if h.chunk_id == "c-target")
        assert _HEADING_TERM not in hit.snippet
        assert hit.snippet in _BODY
    finally:
        conn.close()


def test_grep_mode_matches_the_body_only(tmp_path: Path) -> None:
    """完全一致検索は本文だけを照合する（FR-MDQ-05 の対象外）。"""
    conn = _store_with_heading_only_term(tmp_path)
    try:
        hits = searcher.search(
            conn, _HEADING_TERM, mode="grep", top_k=5, max_tokens=100000
        )
        assert all(h.chunk_id != "c-target" for h in hits)
    finally:
        conn.close()


def test_length_normalisation_is_declared_as_a_single_constant() -> None:
    """FR-MDQ-06: 係数は実装内の単一定数。値は回帰計測で決めたものを固定する。"""
    assert isinstance(searcher.LENGTH_NORM_B, float)
    assert 0.0 <= searcher.LENGTH_NORM_B <= 1.0
    assert searcher.LENGTH_NORM_B == 0.2


def _capture_bm25_kwargs(monkeypatch, attribute: str) -> list[dict]:
    captured: list[dict] = []

    class _Fake:
        def __init__(self, corpus, **kwargs):
            captured.append(kwargs)
            self._size = len(corpus)

        def get_scores(self, query):
            return [1.0] * self._size

    monkeypatch.setattr(searcher, attribute, _Fake)
    return captured


def test_rank_bm25_receives_the_shared_constant(tmp_path: Path, monkeypatch) -> None:
    conn = _store_with_heading_only_term(tmp_path)
    try:
        monkeypatch.setattr(searcher, "HAS_RANK_BM25", True)
        captured = _capture_bm25_kwargs(monkeypatch, "BM25Okapi")
        searcher.search(conn, _HEADING_TERM, top_k=5, max_tokens=100000)
        assert captured
        assert all(kwargs.get("b") == searcher.LENGTH_NORM_B for kwargs in captured)
    finally:
        conn.close()


def test_builtin_bm25_receives_the_shared_constant(tmp_path: Path, monkeypatch) -> None:
    conn = _store_with_heading_only_term(tmp_path)
    try:
        monkeypatch.setattr(searcher, "HAS_RANK_BM25", False)
        captured = _capture_bm25_kwargs(monkeypatch, "_MiniBM25")
        searcher.search(conn, _HEADING_TERM, top_k=5, max_tokens=100000)
        assert captured
        assert all(kwargs.get("b") == searcher.LENGTH_NORM_B for kwargs in captured)
    finally:
        conn.close()
