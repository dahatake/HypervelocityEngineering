"""End-to-end: search with --with-parent-depth resolves ancestor chunks."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mdq import indexer, search as searcher, store


def test_with_parent_depth_returns_chain(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    body = (
        "# Authentication\n\noauth intro paragraph\n\n"
        "## OAuth Flow\n\nflow description\n\n"
        "### Token Refresh\n\ntoken refresh details unique-needle\n"
    )
    (repo / "docs" / "auth.md").write_text(body, encoding="utf-8")
    db = tmp_path / "db.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        indexer.build_index(repo, ["docs"], conn, strategy="heading")

        # depth=1 -> expansion.parent is dict (single direct parent),
        # expansion.parents is NOT present.
        hits = searcher.search(conn, "unique-needle", parent_depth=1, top_k=5)
        assert hits
        h = hits[0]
        assert h.expansion is not None
        assert "parent" in h.expansion
        assert isinstance(h.expansion["parent"], dict)
        assert "OAuth Flow" in h.expansion["parent"]["heading_path"]
        assert "parents" not in h.expansion

        # depth=2 -> expansion.parent is still dict (direct parent),
        # AND expansion.parents is a list ordered [direct, ..., root-most].
        hits2 = searcher.search(conn, "unique-needle", parent_depth=2, top_k=5)
        assert hits2[0].expansion is not None
        assert isinstance(hits2[0].expansion["parent"], dict)
        assert "OAuth Flow" in hits2[0].expansion["parent"]["heading_path"]
        chain = hits2[0].expansion["parents"]
        assert isinstance(chain, list)
        assert len(chain) == 2
        assert "OAuth Flow" in chain[0]["heading_path"]
        assert "Authentication" in chain[1]["heading_path"]

        # include_parent (legacy) acts as depth=1 -> dict only
        hits3 = searcher.search(conn, "unique-needle", include_parent=True,
                                top_k=5)
        assert hits3[0].expansion is not None
        assert isinstance(hits3[0].expansion["parent"], dict)
        assert "parents" not in hits3[0].expansion
    finally:
        conn.close()


def test_search_dedups_by_line_range(tmp_path: Path) -> None:
    """Overlap-induced duplicates should be merged by (path, start, end)."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    # Long content so heading_recursive subdivides, with overlap_paragraphs.
    p1 = "alpha keyword " * 30
    p2 = "beta keyword " * 30
    p3 = "gamma keyword " * 30
    body = f"# H\n\n{p1}\n\n{p2}\n\n{p3}\n"
    (repo / "docs" / "x.md").write_text(body, encoding="utf-8")
    db = tmp_path / "db.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        indexer.build_index(repo, ["docs"], conn,
                            strategy="heading_recursive",
                            max_chunk_chars=300,
                            overlap_paragraphs=1)
        hits = searcher.search(conn, "keyword", top_k=10)
        # No two hits should report the same (path, start, end).
        seen = set()
        for h in hits:
            key = (h.path, h.start_line, h.end_line)
            assert key not in seen, f"duplicate hit range: {key}"
            seen.add(key)
    finally:
        conn.close()
