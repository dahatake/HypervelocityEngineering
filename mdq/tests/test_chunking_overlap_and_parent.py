"""Tests for paragraph-level overlap in heading_recursive strategy and
parent_chunk_id assignment.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mdq import indexer, store, strategies


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    return repo


def test_overlap_paragraphs_creates_overlap(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # Build a long heading whose body has 4 distinct paragraphs so the
    # subdivider produces multiple sub-chunks.
    p1 = "AAA " * 50
    p2 = "BBB " * 50
    p3 = "CCC " * 50
    p4 = "DDD " * 50
    body = f"# Section\n\n{p1}\n\n{p2}\n\n{p3}\n\n{p4}\n"
    f = repo / "docs" / "long.md"
    f.write_text(body, encoding="utf-8")

    db = tmp_path / "db.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        # heading_recursive with small max_chunk_chars to force splitting,
        # overlap_paragraphs=1.
        indexer.build_index(repo, ["docs"], conn,
                            strategy="heading_recursive",
                            max_chunk_chars=300,
                            overlap_paragraphs=1)
        rows = list(conn.execute(
            "SELECT part_index, part_total, text FROM chunks "
            "WHERE heading_path LIKE '%Section%' ORDER BY start_line"
        ))
        assert len(rows) >= 2, "expected multiple sub-chunks"
        # The 2nd sub-chunk should contain the trailing paragraph of the 1st.
        first = rows[0][2]
        second = rows[1][2]
        # The donor paragraph should reappear at the head of the second sub.
        # Pick the LAST paragraph that appears in the first sub and ensure it
        # is a prefix-ish presence in the second.
        first_paragraphs = [p.strip() for p in first.split("\n\n") if p.strip()]
        last_para_of_first = first_paragraphs[-1] if first_paragraphs else ""
        assert last_para_of_first and last_para_of_first in second, (
            "overlap paragraph did not appear at the start of next sub-chunk"
        )
    finally:
        conn.close()


def test_zero_overlap_disables_overlap(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    p1 = "AAA " * 50
    p2 = "BBB " * 50
    p3 = "CCC " * 50
    body = f"# H\n\n{p1}\n\n{p2}\n\n{p3}\n"
    (repo / "docs" / "f.md").write_text(body, encoding="utf-8")
    db = tmp_path / "db.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        indexer.build_index(repo, ["docs"], conn,
                            strategy="heading_recursive",
                            max_chunk_chars=300,
                            overlap_paragraphs=0)
        rows = list(conn.execute(
            "SELECT text FROM chunks ORDER BY start_line"
        ))
        assert len(rows) >= 2, "expected multiple sub-chunks"
        # No adjacent pair of sub-chunks should share a non-trivial paragraph.
        for i in range(len(rows) - 1):
            cur_paras = {
                p.strip()
                for p in rows[i][0].split("\n\n")
                if len(p.strip()) >= 10
            }
            next_paras = {
                p.strip()
                for p in rows[i + 1][0].split("\n\n")
                if len(p.strip()) >= 10
            }
            common = cur_paras & next_paras
            assert not common, (
                f"overlap leaked between chunks {i} and {i + 1}: {common}"
            )
    finally:
        conn.close()


def test_parent_chunk_id_populated(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    body = (
        "# Top\n\nintro body line\n\n"
        "## Child\n\nchild body line\n\n"
        "### Grand\n\ngrand body line\n"
    )
    (repo / "docs" / "f.md").write_text(body, encoding="utf-8")
    db = tmp_path / "db.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        indexer.build_index(repo, ["docs"], conn, strategy="heading")
        rows = {
            r[0]: (r[1], r[2])
            for r in conn.execute(
                "SELECT heading_path, chunk_id, parent_chunk_id FROM chunks"
            )
        }
        # Top has no parent.
        assert "Top" in rows
        assert rows["Top"][1] is None
        # Child's parent should be Top.
        assert "Top > Child" in rows
        assert rows["Top > Child"][1] == rows["Top"][0]
        # Grand's parent should be Top > Child.
        assert "Top > Child > Grand" in rows
        assert rows["Top > Child > Grand"][1] == rows["Top > Child"][0]
    finally:
        conn.close()


def test_fixed_window_has_no_parent(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    body = "# H\n\nbody " * 30
    (repo / "docs" / "f.md").write_text(body, encoding="utf-8")
    db = tmp_path / "db_fw.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        indexer.build_index(repo, ["docs"], conn, strategy="fixed_window")
        for hp, parent in conn.execute(
            "SELECT heading_path, parent_chunk_id FROM chunks"
        ):
            assert hp == "(window)"
            assert parent is None
    finally:
        conn.close()
