"""Tests for store schema migration (v3 -> v6)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mdq import store


def test_open_store_creates_v5_schema(tmp_path: Path) -> None:
    db = tmp_path / "fresh.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        cur = conn.execute("PRAGMA table_info(chunks)")
        cols = {row[1] for row in cur}
        assert "parent_chunk_id" in cols, "v4 column missing on fresh DB"
        assert "text_raw" in cols, "v5 text_raw column missing on fresh DB"
        assert "chunk_embedding" in cols, "v5 chunk_embedding column missing on fresh DB"
        assert "summary" in cols, "v6 summary column missing on fresh DB"
        v = conn.execute("PRAGMA user_version").fetchone()[0]
        assert v == 6
    finally:
        conn.close()


def test_open_store_migrates_legacy_v3_db(tmp_path: Path) -> None:
    """v3 DB without parent_chunk_id should gain the column without data loss."""
    db = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE files (
          path TEXT PRIMARY KEY, sha1 TEXT NOT NULL, mtime REAL NOT NULL,
          size_bytes INTEGER NOT NULL, frontmatter TEXT
        );
        CREATE TABLE chunks (
          chunk_id     TEXT PRIMARY KEY,
          path         TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
          heading_path TEXT NOT NULL,
          level        INTEGER NOT NULL,
          start_line   INTEGER NOT NULL,
          end_line     INTEGER NOT NULL,
          token_est    INTEGER NOT NULL,
          text         TEXT NOT NULL,
          tags         TEXT,
          part_index   INTEGER NOT NULL DEFAULT 0,
          part_total   INTEGER NOT NULL DEFAULT 1
        );
        PRAGMA user_version = 3;
        """
    )
    conn.execute(
        "INSERT INTO files VALUES('a.md','sha',1.0,10,NULL)",
    )
    conn.execute(
        "INSERT INTO chunks(chunk_id,path,heading_path,level,start_line,"
        "end_line,token_est,text,tags,part_index,part_total) "
        "VALUES('cid','a.md','# A',1,1,1,1,'A',NULL,0,1)"
    )
    conn.commit()
    conn.close()

    # Reopen via store.open_store(); migration should add parent_chunk_id.
    conn = store.open_store(db, lang="ja-jp")
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chunks)")}
        assert "parent_chunk_id" in cols
        # Existing row preserved with NULL parent.
        row = conn.execute(
            "SELECT chunk_id, parent_chunk_id FROM chunks"
        ).fetchone()
        assert row[0] == "cid"
        assert row[1] is None
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
    finally:
        conn.close()


def test_insert_chunks_accepts_legacy_tuples(tmp_path: Path) -> None:
    db = tmp_path / "x.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        # files row required by FK.
        store.upsert_file(conn, "x.md", "sha", 1.0, 1, None)
        # 9-tuple (legacy): no parent / no part info
        store.insert_chunks(conn, [
            ("c1", "x.md", "# A", 1, 1, 1, 1, "A", None),
        ])
        # 11-tuple (post-v2): part info, no parent
        store.insert_chunks(conn, [
            ("c2", "x.md", "# B", 1, 2, 2, 1, "B", None, 0, 1),
        ])
        # 12-tuple (v4): with parent
        store.insert_chunks(conn, [
            ("c3", "x.md", "# B > ## C", 2, 3, 3, 1, "C", None, 0, 1, "c2"),
        ])
        # 14-tuple (v5): with text_raw + chunk_embedding
        store.insert_chunks(conn, [
            ("c4", "x.md", "# D", 1, 4, 4, 1, "[ctx] D", None, 0, 1, None,
             "D", b"\x00\x01\x02\x03"),
        ])
        conn.commit()
        rows = list(conn.execute(
            "SELECT chunk_id, parent_chunk_id, text_raw, chunk_embedding "
            "FROM chunks ORDER BY chunk_id"
        ))
        assert rows[0] == ("c1", None, None, None)
        assert rows[1] == ("c2", None, None, None)
        assert rows[2] == ("c3", "c2", None, None)
        assert rows[3] == ("c4", None, "D", b"\x00\x01\x02\x03")
    finally:
        conn.close()
