"""日本語クエリに対する FTS5 経路の回帰テスト。

`ja-jp` 索引の `chunks_fts` は ``trigram`` トークナイザで作られる。trigram は
3 文字未満を索引せず、``detail=none`` ではフレーズクエリも使えない。一方
``mdq.search.tokenize`` は CJK を 1 文字へ分解するため、素直に OR 結合すると
日本語クエリが常に 0 件になる。ここではその契約を固定する。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mdq import search as searcher, store

_TARGET = "PR body に検証マーカーを記載すること"
# 検証マーカー のトリグラム 4 つを非連続に含むだけのおとり。
# トリグラム AND だけで絞ると偽陽性として混入する。
_DECOY = "ーカー と マーカ と 証マー と 検証マ を個別に含む文"
_ENGLISH = "body with ftsuniquetoken here"


def _store_with_docs(tmp_path: Path, lang: str = "ja-jp"):
    conn = store.open_store(tmp_path / f"index-{lang}.sqlite", lang=lang)
    store.upsert_file(conn, "a.md", "sha", 1.0, 10, None)
    rows = [
        ("c-target", "a.md", "# 検証", 1, 1, 1, 1, _TARGET, None),
        ("c-decoy", "a.md", "# おとり", 1, 2, 2, 1, _DECOY, None),
        ("c-english", "a.md", "# English", 1, 3, 3, 1, _ENGLISH, None),
    ]
    store.insert_chunks(conn, rows)
    conn.commit()
    return conn


def _skip_without_fts5(conn) -> None:
    if not store.has_fts5(conn):
        pytest.skip("SQLite build does not provide FTS5")


def test_japanese_query_hits_via_fts5(tmp_path: Path) -> None:
    conn = _store_with_docs(tmp_path)
    try:
        _skip_without_fts5(conn)
        hits = searcher.search(conn, "検証マーカー", engine="fts5", top_k=5)
        assert hits, "FTS5 経路が日本語クエリで 0 件を返した"
        assert hits[0].chunk_id == "c-target"
    finally:
        conn.close()


def test_fts5_excludes_non_contiguous_trigram_matches(tmp_path: Path) -> None:
    """トリグラム AND だけでは通ってしまうおとりを確定照合で除外すること。"""
    conn = _store_with_docs(tmp_path)
    try:
        _skip_without_fts5(conn)
        hits = searcher.search(conn, "検証マーカー", engine="fts5", top_k=5)
        assert [h.chunk_id for h in hits] == ["c-target"]
    finally:
        conn.close()


def test_fts5_does_not_lose_documents_that_bm25_finds(tmp_path: Path) -> None:
    """FTS5 経路が in-memory BM25 の再現率を落とさないこと。

    順位までは一致しない。in-memory BM25 は CJK を 1 文字へ分解するため、
    トリグラムを非連続に含むだけのおとりが語の出現回数で上位に来る
    （実測: decoy 0.2200 > target 0.1802）。FTS5 経路は確定照合を行うので
    おとりを落とす。ここでは「見つけられること」だけを固定する。
    """
    conn = _store_with_docs(tmp_path)
    try:
        _skip_without_fts5(conn)
        fts5 = searcher.search(conn, "検証マーカー", engine="fts5", top_k=5)
        bm25 = searcher.search(conn, "検証マーカー", engine="bm25", top_k=5)
        assert "c-target" in [h.chunk_id for h in bm25]
        assert "c-target" in [h.chunk_id for h in fts5]
    finally:
        conn.close()


def test_short_japanese_query_falls_back_to_in_memory_bm25(tmp_path: Path) -> None:
    """2 文字は trigram 索引で表現できないため、0 件で返さずフォールバックする。

    見ているのは「0 件にならない」ことまで。どの経路を通ったかは
    `Hit` に現れないため、フォールバックの発動自体は直接には検証していない。
    """
    conn = _store_with_docs(tmp_path)
    try:
        _skip_without_fts5(conn)
        hits = searcher.search(conn, "検証", engine="fts5", top_k=5)
        assert hits, "3 文字未満のクエリが 0 件になった（フォールバック未実装）"
    finally:
        conn.close()


def test_english_query_still_hits_via_fts5(tmp_path: Path) -> None:
    """ja-jp 索引でも ASCII 語は引き続きヒットすること。"""
    conn = _store_with_docs(tmp_path)
    try:
        _skip_without_fts5(conn)
        hits = searcher.search(conn, "ftsuniquetoken", engine="fts5", top_k=5)
        assert hits, "ASCII クエリが 0 件になった"
        assert hits[0].chunk_id == "c-english"
    finally:
        conn.close()


def test_en_us_index_is_unaffected(tmp_path: Path) -> None:
    """unicode61 側は現行の OR 結合のまま動くこと。"""
    conn = _store_with_docs(tmp_path, lang="en-us")
    try:
        _skip_without_fts5(conn)
        hits = searcher.search(conn, "ftsuniquetoken", engine="fts5", top_k=5)
        assert hits
        assert hits[0].chunk_id == "c-english"
    finally:
        conn.close()


def test_like_metacharacters_do_not_widen_the_verification(tmp_path: Path) -> None:
    """`_` / `%` を LIKE のワイルドカードとして解釈させないこと。

    確定照合は素の LIKE では成立しない。``ab_de`` のトリグラムを非連続に含み、
    かつ ``abXde`` を持つ文書は、トリグラム AND を通過したうえで ``_`` が
    任意 1 文字として働くため、literal ``ab_de`` が無いのにヒットしてしまう。
    """
    conn = store.open_store(tmp_path / "meta.sqlite", lang="ja-jp")
    try:
        _skip_without_fts5(conn)
        store.upsert_file(conn, "a.md", "sha", 1.0, 10, None)
        rows = [
            ("c-leak", "a.md", "# Leak", 1, 1, 1, 1, "ab_ b_d _de and abXde", None),
            ("c-real", "a.md", "# Real", 1, 2, 2, 1, "the literal ab_de appears", None),
        ]
        rows += [
            (f"c-fill-{i}", "a.md", f"# F{i}", 1, 10 + i, 10 + i, 1,
             f"unrelated filler {i}", None)
            for i in range(8)
        ]
        store.insert_chunks(conn, rows)
        conn.commit()
        hits = searcher.search(conn, "ab_de", engine="fts5", top_k=5)
        assert [h.chunk_id for h in hits] == ["c-real"]
    finally:
        conn.close()


def test_percent_in_query_is_not_a_like_wildcard(tmp_path: Path) -> None:
    conn = store.open_store(tmp_path / "pct.sqlite", lang="ja-jp")
    try:
        _skip_without_fts5(conn)
        store.upsert_file(conn, "a.md", "sha", 1.0, 10, None)
        rows = [
            ("c-leak", "a.md", "# Leak", 1, 1, 1, 1, "a%c c%e and aZZZe", None),
            ("c-real", "a.md", "# Real", 1, 2, 2, 1, "the literal a%c%e appears", None),
        ]
        rows += [
            (f"c-fill-{i}", "a.md", f"# F{i}", 1, 10 + i, 10 + i, 1,
             f"unrelated filler {i}", None)
            for i in range(8)
        ]
        store.insert_chunks(conn, rows)
        conn.commit()
        hits = searcher.search(conn, "a%c%e", engine="fts5", top_k=5)
        assert [h.chunk_id for h in hits] == ["c-real"]
    finally:
        conn.close()
