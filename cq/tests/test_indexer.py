"""Contracts for the cq indexer: incremental update, prune, degradation (FR-CQ-04)."""

from __future__ import annotations

import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from cq import config, indexer, store


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(
        "def alpha():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "b.py").write_text(
        "class Beta:\n    def run(self):\n        return 2\n", encoding="utf-8"
    )
    return tmp_path


def _db(repo: Path) -> Path:
    return repo / ".cq" / "index-test.sqlite"


def _rows(repo: Path, sql: str) -> list[tuple]:
    with closing(store.open_store(_db(repo), create=False)) as conn:
        return [tuple(r) for r in conn.execute(sql)]


def _index(repo: Path, **kwargs) -> indexer.IndexReport:
    profile = config.resolve_profile(repo, "test")
    return indexer.build_index(repo, profile, db_path=_db(repo), **kwargs)


class TestFirstRun:
    def test_files_and_symbols_are_recorded(self, repo: Path) -> None:
        report = _index(repo)
        assert report.indexed == 2
        assert report.symbols == 3
        assert _rows(repo, "SELECT path FROM files ORDER BY path") == [
            ("pkg/a.py",), ("pkg/b.py",)
        ]
        assert {r[0] for r in _rows(repo, "SELECT qualname FROM symbols")} == {
            "alpha", "Beta", "Beta.run"
        }

    def test_file_identity_is_recorded(self, repo: Path) -> None:
        _index(repo)
        row = _rows(repo, "SELECT lang, sha1, parser, size_bytes FROM files WHERE path='pkg/a.py'")[0]
        assert row[0] == "python"
        assert len(row[1]) == 40
        assert row[2] == "ast"
        assert row[3] > 0


class TestIncremental:
    def test_unchanged_files_are_skipped(self, repo: Path) -> None:
        _index(repo)
        report = _index(repo)
        assert report.skipped == 2
        assert report.indexed == 0

    def test_changed_file_is_reindexed(self, repo: Path) -> None:
        _index(repo)
        (repo / "pkg" / "a.py").write_text(
            "def alpha():\n    return 1\n\n\ndef gamma():\n    return 3\n", encoding="utf-8"
        )
        report = _index(repo)
        assert report.indexed == 1
        assert report.skipped == 1
        assert {r[0] for r in _rows(repo, "SELECT qualname FROM symbols WHERE path='pkg/a.py'")} == {
            "alpha", "gamma"
        }

    def test_stale_symbols_are_replaced_not_duplicated(self, repo: Path) -> None:
        _index(repo)
        (repo / "pkg" / "a.py").write_text("def renamed():\n    return 1\n", encoding="utf-8")
        _index(repo)
        assert {r[0] for r in _rows(repo, "SELECT qualname FROM symbols WHERE path='pkg/a.py'")} == {
            "renamed"
        }

    def test_deleted_files_are_pruned(self, repo: Path) -> None:
        _index(repo)
        (repo / "pkg" / "b.py").unlink()
        report = _index(repo)
        assert report.pruned == 1
        assert _rows(repo, "SELECT path FROM files ORDER BY path") == [("pkg/a.py",)]
        assert _rows(repo, "SELECT count(*) FROM symbols WHERE path='pkg/b.py'") == [(0,)]

    def test_rebuild_discards_the_previous_index(self, repo: Path) -> None:
        _index(repo)
        report = _index(repo, rebuild=True)
        assert report.indexed == 2
        assert report.skipped == 0


class TestDegradation:
    def test_byte_order_mark_does_not_cause_degradation(self, repo: Path) -> None:
        """BOM 付きの正当な Python を構文エラー扱いしない（実リポジトリに 7 件存在）。"""
        (repo / "pkg" / "bom.py").write_bytes(
            "\ufeffdef with_bom():\n    return 1\n".encode("utf-8")
        )
        report = _index(repo)
        assert report.degraded == 0
        assert _rows(repo, "SELECT parser FROM files WHERE path='pkg/bom.py'") == [("ast",)]
        assert _rows(repo, "SELECT qualname FROM symbols WHERE path='pkg/bom.py'") == [
            ("with_bom",)
        ]

    def test_unparsable_file_is_kept_with_a_lite_parser(self, repo: Path) -> None:
        (repo / "pkg" / "broken.py").write_text(
            "def broken(:\n    pass\n\nclass Half:\n    pass\n", encoding="utf-8"
        )
        report = _index(repo)
        assert report.degraded == 1
        assert _rows(repo, "SELECT parser FROM files WHERE path='pkg/broken.py'") == [("lite",)]

    def test_degraded_file_still_yields_symbols(self, repo: Path) -> None:
        (repo / "pkg" / "broken.py").write_text(
            "def broken(:\n    pass\n\nclass Half:\n    pass\n", encoding="utf-8"
        )
        _index(repo)
        found = {r[0] for r in _rows(repo, "SELECT name FROM symbols WHERE path='pkg/broken.py'")}
        assert "Half" in found

    def test_degradation_does_not_fail_the_whole_run(self, repo: Path) -> None:
        (repo / "pkg" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
        report = _index(repo)
        assert report.indexed == 3
        assert report.errors == 0


class TestDeterminism:
    def test_symbol_ids_are_stable_across_runs(self, repo: Path) -> None:
        _index(repo)
        before = sorted(r[0] for r in _rows(repo, "SELECT symbol_id FROM symbols"))
        _index(repo, rebuild=True)
        after = sorted(r[0] for r in _rows(repo, "SELECT symbol_id FROM symbols"))
        assert before == after

    def test_symbol_ids_are_unique(self, repo: Path) -> None:
        _index(repo)
        rows = _rows(repo, "SELECT count(*), count(DISTINCT symbol_id) FROM symbols")[0]
        assert rows[0] == rows[1]
