"""End-to-end tests for the `pageindex` chunking strategy.

Verifies:
  - `mdq index --strategy pageindex` builds a DB that stores per-chunk
    summaries (SCHEMA v6 `chunks.summary`).
  - `mdq search ... --pageindex-tree-depth N` returns
    ``expansion.tree_path`` with the root-first chain of nodes.
  - `_FALLBACK_ORDER` lists pageindex first; rule 4 selects pageindex.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mdq import indexer, search as searcher, store, query_router as qr


def _build_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    body = (
        "# Project Overview\n\n"
        "This project provides ...\n\n"
        "## Architecture\n\n"
        "The system is split into ...\n\n"
        "### API Layer\n\n"
        "The API layer handles unique-token requests.\n"
    )
    (repo / "docs" / "overview.md").write_text(body, encoding="utf-8")
    return repo


def test_pageindex_index_stores_summary_column(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    db = tmp_path / "pi.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        indexer.build_index(repo, ["docs"], conn, strategy="pageindex")
        rows = list(conn.execute(
            "SELECT heading_path, summary FROM chunks ORDER BY start_line"
        ))
        assert rows
        for hp, summary in rows:
            assert summary is not None
            assert summary  # non-empty
    finally:
        conn.close()


def test_pageindex_search_tree_path(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    db = tmp_path / "pi.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        indexer.build_index(repo, ["docs"], conn, strategy="pageindex")
        hits = searcher.search(
            conn, "unique-token",
            pageindex_tree_depth=3, top_k=5,
        )
        assert hits
        h = hits[0]
        assert h.expansion is not None
        nodes = h.expansion.get("tree_path")
        assert isinstance(nodes, list)
        assert len(nodes) >= 2
        # root-first; final node == hit chunk itself
        assert nodes[-1]["chunk_id"] == h.chunk_id
        # Each node carries heading_path and summary.
        for n in nodes:
            assert "heading_path" in n
            assert "summary" in n
        # At least the hit node has a summary (pageindex DB).
        assert nodes[-1]["summary"]
    finally:
        conn.close()


def test_pageindex_search_without_depth_no_tree_path(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    db = tmp_path / "pi.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        indexer.build_index(repo, ["docs"], conn, strategy="pageindex")
        hits = searcher.search(conn, "unique-token", top_k=5)
        assert hits
        if hits[0].expansion is not None:
            assert "tree_path" not in hits[0].expansion
    finally:
        conn.close()


def test_fallback_order_lists_pageindex_first() -> None:
    assert qr._FALLBACK_ORDER[0] == "pageindex"


# NOTE: rule 4 concept_overview routing and fallback behaviour are tested
# in test_query_router.py (test_concept_overview_route /
# test_concept_overview_falls_back_when_pageindex_missing). Keeping this
# file focused on end-to-end indexing + search rather than duplicating
# pure router-rule assertions.
