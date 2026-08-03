"""Contracts for the cq index store (FR-CQ-01 / FR-CQ-03)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from cq import store

EXPECTED_TABLES = {"meta", "files", "symbols", "chunks", "refs", "imports", "traces"}
EXPECTED_FTS = {"chunks_tri", "chunks_fts"}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


class TestDatabaseLayout:
    def test_db_path_is_profile_scoped_under_dot_cq(self) -> None:
        assert store.db_path_for("hve") == Path(".cq") / "index-hve.sqlite"
        assert store.db_path_for("app") == Path(".cq") / "index-app.sqlite"

    def test_profiles_do_not_share_a_database(self) -> None:
        assert store.db_path_for("hve") != store.db_path_for("app")

    def test_database_is_not_inside_the_markdown_query_index(self) -> None:
        """FR-CQ-01: mdq と物理的に別ファイルの索引にする。"""
        assert store.db_path_for("hve").parts[0] == ".cq"

    def test_profile_name_is_validated(self) -> None:
        for bad in ("../evil", "a/b", "", "hve.sqlite"):
            with pytest.raises(store.StoreError):
                store.db_path_for(bad)


class TestSchema:
    def test_open_creates_every_table(self, tmp_path: Path) -> None:
        with closing(store.open_store(tmp_path / "index.sqlite")) as conn:
            assert EXPECTED_TABLES <= _tables(conn)

    def test_open_creates_the_fts_mirrors(self, tmp_path: Path) -> None:
        with closing(store.open_store(tmp_path / "index.sqlite")) as conn:
            names = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert EXPECTED_FTS <= names

    def test_substring_mirror_uses_the_trigram_tokenizer(self, tmp_path: Path) -> None:
        with closing(store.open_store(tmp_path / "index.sqlite")) as conn:
            sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='chunks_tri'"
            ).fetchone()[0]
            assert "trigram" in sql
            assert "detail=none" in sql

    def test_ranking_mirror_indexes_identifier_fields(self, tmp_path: Path) -> None:
        with closing(store.open_store(tmp_path / "index.sqlite")) as conn:
            sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='chunks_fts'"
            ).fetchone()[0]
            for column in ("name", "signature", "ident_text", "text"):
                assert column in sql
            assert "unicode61" in sql

    def test_schema_version_is_recorded(self, tmp_path: Path) -> None:
        with closing(store.open_store(tmp_path / "index.sqlite")) as conn:
            assert store.schema_version(conn) == store.SCHEMA_VERSION

    def test_foreign_rows_cascade_on_file_delete(self, tmp_path: Path) -> None:
        with closing(store.open_store(tmp_path / "index.sqlite")) as conn:
            conn.execute(
                "INSERT INTO files(path, lang, sha1, mtime, size_bytes, parser)"
                " VALUES ('a.py', 'python', 'x', 1.0, 10, 'ast')"
            )
            conn.execute(
                "INSERT INTO symbols(symbol_id, path, qualname, name, kind,"
                " start_line, end_line, signature) VALUES"
                " ('s1', 'a.py', 'f', 'f', 'function', 1, 2, 'def f()')"
            )
            conn.execute("DELETE FROM files WHERE path='a.py'")
            assert conn.execute("SELECT count(*) FROM symbols").fetchone()[0] == 0


class TestRebuildOnSchemaChange:
    def test_older_schema_is_rejected_with_a_rebuild_instruction(self, tmp_path: Path) -> None:
        db = tmp_path / "index.sqlite"
        with closing(store.open_store(db)) as conn:
            conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", ("0",))
            conn.commit()
        with pytest.raises(store.SchemaVersionError, match="rebuild"):
            store.open_store(db)

    def test_missing_database_is_reported_when_creation_is_disabled(self, tmp_path: Path) -> None:
        with pytest.raises(store.StoreError, match="cq index"):
            store.open_store(tmp_path / "absent.sqlite", create=False)


class TestRepositoryHygiene:
    def test_index_directory_is_git_ignored(self) -> None:
        text = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(encoding="utf-8")
        assert any(line.strip() == ".cq/" for line in text.splitlines())
