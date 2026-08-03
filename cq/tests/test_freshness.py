"""Contracts for index freshness: watcher and stat-only staleness guard (FR-CQ-08)."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from cq import config, freshness, indexer, search

watchdog = pytest.importorskip("watchdog", reason="cq watch needs the watchdog extra")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    for name in ("a", "b", "c"):
        (tmp_path / "pkg" / f"{name}.py").write_text(
            f"def {name}_one():\n    return 1\n", encoding="utf-8"
        )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / ".cq" / "index-test.sqlite")
    return tmp_path


def _db(repo: Path) -> Path:
    return repo / ".cq" / "index-test.sqlite"


def _profile(repo: Path):
    return config.resolve_profile(repo, "test")


class TestStaleDetection:
    def test_untouched_index_is_fresh(self, repo: Path) -> None:
        report = freshness.check(repo, _profile(repo), _db(repo))
        assert report.changed == ()
        assert report.is_fresh is True

    def test_modified_file_is_detected(self, repo: Path) -> None:
        (repo / "pkg" / "a.py").write_text("def a_two():\n    return 2\n", encoding="utf-8")
        report = freshness.check(repo, _profile(repo), _db(repo))
        assert report.changed == ("pkg/a.py",)

    def test_new_file_is_detected_only_when_requested(self, repo: Path) -> None:
        """新規ファイル検出は git 列挙が必要なため既定 OFF（NFR-CQ-01）。"""
        (repo / "pkg" / "d.py").write_text("def d():\n    return 4\n", encoding="utf-8")
        assert freshness.check(repo, _profile(repo), _db(repo)).changed == ()
        thorough = freshness.check(repo, _profile(repo), _db(repo), include_new=True)
        assert "pkg/d.py" in thorough.changed

    def test_deleted_file_is_detected(self, repo: Path) -> None:
        (repo / "pkg" / "b.py").unlink()
        assert "pkg/b.py" in freshness.check(repo, _profile(repo), _db(repo)).changed

    def test_check_is_cheap_enough_for_every_query(self, repo: Path) -> None:
        started = time.perf_counter()
        freshness.check(repo, _profile(repo), _db(repo))
        assert (time.perf_counter() - started) < 0.2

    def test_check_does_not_hash_file_contents(self) -> None:
        """更新時刻とサイズだけで突合する（FR-CQ-08）。"""
        source = (Path(__file__).resolve().parents[1] / "freshness.py").read_text(encoding="utf-8")
        assert "sha1" not in source
        assert "read_bytes" not in source


class TestAutoReindex:
    def test_small_drift_is_reindexed_before_answering(self, repo: Path) -> None:
        (repo / "pkg" / "a.py").write_text(
            "def brand_new_symbol():\n    return 9\n", encoding="utf-8"
        )
        hits = search.search(
            repo, "test", query="brand_new_symbol", db_path=_db(repo), auto_reindex_limit=50
        )
        assert hits and hits[0].path == "pkg/a.py"

    def test_reindex_is_skipped_above_the_limit(self, repo: Path) -> None:
        for name in ("a", "b", "c"):
            (repo / "pkg" / f"{name}.py").write_text(
                f"def {name}_changed():\n    return 0\n", encoding="utf-8"
            )
        hits = search.search(
            repo, "test", query="a_one", db_path=_db(repo), auto_reindex_limit=1
        )
        assert search.last_staleness() is not None
        assert search.last_staleness()["changed"] == 3

    def test_fresh_index_reports_no_staleness(self, repo: Path) -> None:
        search.search(repo, "test", query="a_one", db_path=_db(repo))
        assert search.last_staleness() is None

    def test_guard_is_on_by_default(self, repo: Path) -> None:
        """stale を黙って返さない（FR-CQ-08）。"""
        (repo / "pkg" / "a.py").write_text(
            "def default_guard_symbol():\n    return 5\n", encoding="utf-8"
        )
        hits = search.search(repo, "test", query="default_guard_symbol", db_path=_db(repo))
        assert hits and hits[0].path == "pkg/a.py"

    def test_guard_can_be_disabled(self, repo: Path) -> None:
        (repo / "pkg" / "a.py").write_text(
            "def disabled_guard_symbol():\n    return 6\n", encoding="utf-8"
        )
        assert search.search(
            repo, "test", query="disabled_guard_symbol", db_path=_db(repo),
            auto_reindex_limit=-1,
        ) == []

    def test_single_file_reindex_is_fast(self, repo: Path) -> None:
        (repo / "pkg" / "a.py").write_text("def a_three():\n    return 3\n", encoding="utf-8")
        started = time.perf_counter()
        freshness.refresh(repo, _profile(repo), _db(repo), ("pkg/a.py",))
        assert (time.perf_counter() - started) < 0.2


class TestCliStalenessLine:
    def test_stale_warning_is_the_last_jsonl_line(self, repo: Path, capsys) -> None:
        from cq import cli

        for name in ("a", "b", "c"):
            (repo / "pkg" / f"{name}.py").write_text(
                f"def {name}_changed():\n    return 0\n", encoding="utf-8"
            )
        code = cli.main([
            "search", "--q", "a_one", "--profile", "test", "--repo-root", str(repo),
            "--db", str(_db(repo)), "--auto-reindex-limit", "1",
        ])
        assert code == 0
        import json

        last = json.loads(capsys.readouterr().out.splitlines()[-1])
        assert last["warning"] == "stale"
        assert last["changed"] == 3


class TestWatcher:
    def test_watcher_reflects_a_saved_file(self, repo: Path) -> None:
        from cq.watcher import CqWatcher

        watcher = CqWatcher(repo, _profile(repo), db_path=_db(repo), debounce_ms=50)
        assert watcher.start() is True
        try:
            (repo / "pkg" / "a.py").write_text(
                "def watched_symbol():\n    return 7\n", encoding="utf-8"
            )
            deadline = time.time() + 5.0
            hits = []
            while time.time() < deadline:
                watcher.wait_idle(timeout=1.0)
                hits = search.search(
                    repo, "test", query="watched_symbol", db_path=_db(repo),
                    auto_reindex_limit=-1,
                )
                if hits:
                    break
                time.sleep(0.05)
            assert hits and hits[0].path == "pkg/a.py"
        finally:
            watcher.stop()

    def test_stop_is_idempotent(self, repo: Path) -> None:
        from cq.watcher import CqWatcher

        watcher = CqWatcher(repo, _profile(repo), db_path=_db(repo))
        watcher.start()
        watcher.stop()
        watcher.stop()
        assert watcher.is_running is False

    def test_non_source_files_are_ignored(self, repo: Path) -> None:
        from cq.watcher import CqWatcher

        watcher = CqWatcher(repo, _profile(repo), db_path=_db(repo))
        assert watcher.is_relevant(repo / "pkg" / "a.py") is True
        assert watcher.is_relevant(repo / "pkg" / "notes.md") is False
        assert watcher.is_relevant(repo / "outside" / "x.py") is False
