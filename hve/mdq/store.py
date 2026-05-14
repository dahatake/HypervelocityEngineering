"""SQLite-backed persistent store for the Markdown index.

Schema is intentionally small. BM25 ranking is computed at query time over
the chunks loaded from this store (small/medium corpora).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

DEFAULT_DB_PATH = Path(".hve") / "mdq.sqlite"

# Schema version - bump whenever the migration code adds/changes columns
# or changes chunk_id derivation (forcing a rebuild).
# v1: introduced part_index / part_total columns.
# v2: chunk_id derivation changed to use occurrence_index instead of
#     start_line, making IDs stable against line shifts. v1 chunk rows are
#     dropped and rebuilt from source on first open.
# v3: optional FTS5 mirror table `chunks_fts` + sync triggers. Builds an
#     empty FTS index initially; rebuild is requested on upgrade. Falls back
#     silently when the SQLite build lacks FTS5.
SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  path        TEXT PRIMARY KEY,
  sha1        TEXT NOT NULL,
  mtime       REAL NOT NULL,
  size_bytes  INTEGER NOT NULL,
  frontmatter TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
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
CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
"""


def has_fts5(conn: sqlite3.Connection) -> bool:
    """Return True if this SQLite build supports FTS5."""
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)"
        )
        conn.execute("DROP TABLE IF EXISTS _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, content='chunks', content_rowid='rowid', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.rowid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.rowid, old.text);
  INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply lightweight ADD COLUMN migrations for legacy DBs.

    Idempotent: safe to call on every open_store(). We rely on PRAGMA
    table_info() rather than user_version alone so that DBs created before
    user_version was introduced are still upgraded.
    """
    cur = conn.execute("PRAGMA table_info(chunks)")
    cols = {row[1] for row in cur}
    if "chunks" and cols:
        if "part_index" not in cols:
            conn.execute(
                "ALTER TABLE chunks ADD COLUMN part_index INTEGER NOT NULL DEFAULT 0"
            )
        if "part_total" not in cols:
            conn.execute(
                "ALTER TABLE chunks ADD COLUMN part_total INTEGER NOT NULL DEFAULT 1"
            )
    # v1 -> v2: chunk_id derivation changed. Drop chunks and clear file SHA-1
    # so the next index run rebuilds everything with stable IDs. files rows
    # are preserved (frontmatter, mtime) but sha1 is wiped to force re-scan.
    prev_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if prev_version < 2 and cols:
        conn.execute("DELETE FROM chunks")
        conn.execute("UPDATE files SET sha1 = ''")
    # v* -> v3: install FTS5 mirror (best effort; SQLite without FTS5 simply
    # continues to use the BM25 fallback path).
    if has_fts5(conn):
        conn.executescript(_FTS_SCHEMA)
        if prev_version < 3:
            try:
                conn.execute(
                    "INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')"
                )
            except sqlite3.OperationalError:
                pass
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def open_store(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def upsert_file(conn: sqlite3.Connection, path: str, sha1: str, mtime: float,
                size_bytes: int, frontmatter_json: str | None) -> None:
    conn.execute(
        "INSERT INTO files(path, sha1, mtime, size_bytes, frontmatter) VALUES(?,?,?,?,?) "
        "ON CONFLICT(path) DO UPDATE SET sha1=excluded.sha1, mtime=excluded.mtime, "
        "size_bytes=excluded.size_bytes, frontmatter=excluded.frontmatter",
        (path, sha1, mtime, size_bytes, frontmatter_json),
    )


def delete_chunks_for(conn: sqlite3.Connection, path: str) -> None:
    conn.execute("DELETE FROM chunks WHERE path = ?", (path,))


def insert_chunks(conn: sqlite3.Connection, rows: Iterable[tuple]) -> None:
    """Insert chunk rows.

    Accepts either 9-tuples (legacy: through token_est..tags) or 11-tuples
    that additionally include (part_index, part_total). 9-tuples default to
    part_index=0, part_total=1 for backward compatibility.
    """
    materialised = []
    for r in rows:
        if len(r) == 9:
            materialised.append((*r, 0, 1))
        else:
            materialised.append(tuple(r))
    conn.executemany(
        "INSERT OR REPLACE INTO chunks(chunk_id, path, heading_path, level, "
        "start_line, end_line, token_est, text, tags, part_index, part_total) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        materialised,
    )


def get_file_meta(conn: sqlite3.Connection, path: str) -> tuple[str, float] | None:
    cur = conn.execute("SELECT sha1, mtime FROM files WHERE path = ?", (path,))
    row = cur.fetchone()
    return (row[0], row[1]) if row else None


def all_chunks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return list(conn.execute(
        "SELECT chunk_id, path, heading_path, level, start_line, end_line, "
        "token_est, text, tags, part_index, part_total FROM chunks"
    ))


def list_all_paths(conn: sqlite3.Connection) -> set[str]:
    """Return all file paths currently registered in the store."""
    return {row[0] for row in conn.execute("SELECT path FROM files")}


def delete_file(conn: sqlite3.Connection, path: str) -> int:
    """Delete a file row (chunks are removed via ON DELETE CASCADE).

    Returns the number of chunk rows removed.
    """
    n = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE path = ?", (path,)
    ).fetchone()[0]
    conn.execute("DELETE FROM files WHERE path = ?", (path,))
    return int(n)


def stats(conn: sqlite3.Connection) -> dict:
    f = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    c = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    return {"files": f, "chunks": c}
