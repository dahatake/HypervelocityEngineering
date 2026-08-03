"""Tests for store schema migration (v3 -> v7)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mdq import store


def _fts_ddl(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
    ).fetchone()
    return (row[0] if row else "") or ""


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
        assert v == 7
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
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
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


def test_ja_jp_fts5_mirror_uses_detail_none(tmp_path: Path) -> None:
    """trigram ミラーは detail=none で作る（索引サイズ削減）。"""
    conn = store.open_store(tmp_path / "ja.sqlite", lang="ja-jp")
    try:
        if not store.has_fts5(conn):
            pytest.skip("SQLite build lacks FTS5")
        ddl = _fts_ddl(conn)
        assert "tokenize='trigram'" in ddl
        assert "detail=none" in ddl, f"detail=none missing from trigram mirror: {ddl}"
    finally:
        conn.close()


def test_en_us_fts5_mirror_keeps_positional_detail(tmp_path: Path) -> None:
    """unicode61 側には肥大の実測が無いので detail は既定のまま据え置く。"""
    conn = store.open_store(tmp_path / "en.sqlite", lang="en-us")
    try:
        if not store.has_fts5(conn):
            pytest.skip("SQLite build lacks FTS5")
        ddl = _fts_ddl(conn)
        assert "tokenize='unicode61'" in ddl
        assert "detail=" not in ddl, f"unexpected detail option on unicode61 mirror: {ddl}"
    finally:
        conn.close()


def test_legacy_trigram_mirror_without_detail_none_is_rebuilt(tmp_path: Path) -> None:
    """detail 指定だけが変わった旧 DB も作り直され、再び検索できること。

    ``_migrate`` はトークナイザ名だけを比較していたため、``detail`` の変更を
    検知できず旧ミラーが無言で残る。残ると FTS5 検索が 0 件のままになる。
    """
    db = tmp_path / "legacy-detail.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    if not store.has_fts5(conn):
        conn.close()
        pytest.skip("SQLite build lacks FTS5")
    store.upsert_file(conn, "a.md", "sha", 1.0, 10, None)
    store.insert_chunks(conn, [
        ("cid", "a.md", "# A", 1, 1, 1, 1, "PR body に検証マーカーを記載", None),
    ])
    conn.commit()
    # 旧 DDL（detail 未指定 = full）へ差し戻し、v6 の状態を再現する。
    for stmt in ("DROP TRIGGER IF EXISTS chunks_ai",
                 "DROP TRIGGER IF EXISTS chunks_ad",
                 "DROP TRIGGER IF EXISTS chunks_au",
                 "DROP TABLE IF EXISTS chunks_fts"):
        conn.execute(stmt)
    conn.executescript(
        "CREATE VIRTUAL TABLE chunks_fts USING fts5("
        "  text, content='chunks', content_rowid='rowid', tokenize='trigram'"
        ");"
        "INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');"
        "PRAGMA user_version = 6;"
    )
    conn.commit()
    conn.close()

    conn = store.open_store(db, lang="ja-jp")
    try:
        ddl = _fts_ddl(conn)
        assert "detail=none" in ddl, f"legacy mirror was not rebuilt: {ddl}"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        hits = conn.execute(
            "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ('"検証マ"',),
        ).fetchone()[0]
        assert hits == 1, "rebuilt mirror lost its content"
    finally:
        conn.close()


def test_detail_mismatch_is_detected_without_a_version_bump(tmp_path: Path) -> None:
    """user_version が最新でも detail 不一致だけでミラーを作り直せること。

    バージョン差で救われるとスキーマ比較の欠陥が隠れる。``_migrate`` の
    DDL 比較そのものを固定するために version は据え置いて検査する。
    """
    db = tmp_path / "detail-only.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    if not store.has_fts5(conn):
        conn.close()
        pytest.skip("SQLite build lacks FTS5")
    store.upsert_file(conn, "a.md", "sha", 1.0, 10, None)
    store.insert_chunks(conn, [
        ("cid", "a.md", "# A", 1, 1, 1, 1, "PR body に検証マーカーを記載", None),
    ])
    conn.commit()
    for stmt in ("DROP TRIGGER IF EXISTS chunks_ai",
                 "DROP TRIGGER IF EXISTS chunks_ad",
                 "DROP TRIGGER IF EXISTS chunks_au",
                 "DROP TABLE IF EXISTS chunks_fts"):
        conn.execute(stmt)
    conn.executescript(
        "CREATE VIRTUAL TABLE chunks_fts USING fts5("
        "  text, content='chunks', content_rowid='rowid', tokenize='trigram'"
        ");"
        "INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');"
        f"PRAGMA user_version = {store.SCHEMA_VERSION};"
    )
    conn.commit()
    conn.close()

    conn = store.open_store(db, lang="ja-jp")
    try:
        assert "detail=none" in _fts_ddl(conn), "detail mismatch went undetected"
        hits = conn.execute(
            "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
            ('"検証マ"',),
        ).fetchone()[0]
        assert hits == 1, "rebuilt mirror lost its content"
    finally:
        conn.close()
