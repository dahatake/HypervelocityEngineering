"""Contracts for the FTS5 lexical / ranking layers over chunks (FR-CQ-05)."""

from __future__ import annotations

import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from cq import config, indexer, store


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(
        'def resolveUserProfile(db_path):\n'
        '    """Return the stored profile."""\n'
        '    return {"x-ms-version": db_path}\n',
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "b.py").write_text(
        "class LedgerService:\n    def grant_points(self):\n        return 1\n",
        encoding="utf-8",
    )
    return tmp_path


def _db(repo: Path) -> Path:
    return repo / ".cq" / "index-test.sqlite"


def _index(repo: Path, **kwargs) -> indexer.IndexReport:
    profile = config.resolve_profile(repo, "test")
    return indexer.build_index(repo, profile, db_path=_db(repo), **kwargs)


def _query(repo: Path, sql: str, *params) -> list[tuple]:
    with closing(store.open_store(_db(repo), create=False)) as conn:
        return [tuple(r) for r in conn.execute(sql, params)]


class TestChunkPopulation:
    def test_chunks_are_written_for_every_file(self, repo: Path) -> None:
        report = _index(repo)
        assert report.chunks > 0
        paths = {r[0] for r in _query(repo, "SELECT DISTINCT path FROM chunks")}
        assert paths == {"pkg/a.py", "pkg/b.py"}

    def test_chunks_are_pruned_with_their_file(self, repo: Path) -> None:
        _index(repo)
        (repo / "pkg" / "b.py").unlink()
        _index(repo)
        assert _query(repo, "SELECT count(*) FROM chunks WHERE path='pkg/b.py'") == [(0,)]

    def test_chunk_ids_are_unique(self, repo: Path) -> None:
        _index(repo)
        counts = _query(repo, "SELECT count(*), count(DISTINCT chunk_id) FROM chunks")[0]
        assert counts[0] == counts[1]


class TestSubstringLayer:
    def test_indexed_like_finds_a_substring_inside_a_token(self, repo: Path) -> None:
        _index(repo)
        rows = _query(
            repo,
            "SELECT c.path FROM chunks_tri t JOIN chunks c ON c.rowid = t.rowid"
            " WHERE t.text LIKE ?",
            "%ms-version%",
        )
        assert rows == [("pkg/a.py",)]

    def test_substring_layer_is_updated_on_reindex(self, repo: Path) -> None:
        _index(repo)
        (repo / "pkg" / "a.py").write_text("def other():\n    return 0\n", encoding="utf-8")
        _index(repo)
        rows = _query(
            repo,
            "SELECT c.path FROM chunks_tri t JOIN chunks c ON c.rowid = t.rowid"
            " WHERE t.text LIKE ?",
            "%ms-version%",
        )
        assert rows == []


class TestRankingLayer:
    def test_split_identifier_words_are_searchable(self, repo: Path) -> None:
        """`resolveUserProfile` へ語単位クエリで到達できる（FR-CQ-05）。"""
        _index(repo)
        rows = _query(
            repo,
            "SELECT c.path FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid"
            " WHERE chunks_fts MATCH ? ORDER BY rank",
            "user profile",
        )
        assert ("pkg/a.py",) in rows

    def test_underscore_identifiers_are_searchable_as_words(self, repo: Path) -> None:
        _index(repo)
        rows = _query(
            repo,
            "SELECT c.path FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid"
            " WHERE chunks_fts MATCH ? ORDER BY rank",
            "grant points",
        )
        assert ("pkg/b.py",) in rows

    def test_underscore_is_part_of_a_token(self, repo: Path) -> None:
        _index(repo)
        rows = _query(
            repo,
            "SELECT c.path FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid"
            " WHERE chunks_fts MATCH ?",
            "grant_points",
        )
        assert ("pkg/b.py",) in rows

    def test_ranking_happens_inside_sqlite(self, repo: Path) -> None:
        _index(repo)
        rows = _query(
            repo,
            "SELECT c.path, bm25(chunks_fts, 10.0, 5.0, 3.0, 1.0) AS score"
            " FROM chunks_fts f JOIN chunks c ON c.rowid = f.rowid"
            " WHERE chunks_fts MATCH ? ORDER BY rank LIMIT 5",
            "profile",
        )
        assert rows
        assert isinstance(rows[0][1], float)

    def test_phrase_queries_are_unsupported_by_design(self, repo: Path) -> None:
        """`detail=column` の帰結。検索層（FR-CQ-06）はフレーズを送出してはならない。

        完全一致の隣接検索は trigram 層が担うため、ここでフレーズを諦めても
        機能は失われず、索引サイズを削減できる。
        """
        _index(repo)
        with pytest.raises(sqlite3.OperationalError, match="phrase queries are not supported"):
            _query(
                repo,
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?",
                '"user profile"',
            )
