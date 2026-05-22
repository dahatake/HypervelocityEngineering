"""Tests for the optional progress_callback added to mdq.indexer.build_index
(Phase 0 / T03). Verifies:
  - The callback is invoked exactly once per file.
  - ``current`` is 1-based and monotonically increasing.
  - ``total`` is constant across calls.
  - Callback exceptions do not propagate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mdq import indexer, store


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_progress_callback_receives_each_file(tmp_path: Path):
    repo = tmp_path
    _write(repo / "a.md", "# A\n\nbody A.")
    _write(repo / "b.md", "# B\n\nbody B.")
    _write(repo / "c.md", "# C\n\nbody C.")

    db = repo / "index.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        events: list[tuple[str, int, int]] = []
        indexer.build_index(
            repo, ["."], conn, rebuild=True, prune=False,
            progress_callback=lambda rel, cur, total: events.append((rel, cur, total)),
        )
        assert len(events) == 3
        # current is 1-based and monotonically increasing.
        currents = [e[1] for e in events]
        assert currents == [1, 2, 3]
        # total is constant.
        totals = {e[2] for e in events}
        assert totals == {3}
        # path is relative POSIX.
        paths = {e[0] for e in events}
        assert paths == {"a.md", "b.md", "c.md"}
    finally:
        conn.close()


def test_progress_callback_exceptions_swallowed(tmp_path: Path):
    repo = tmp_path
    _write(repo / "a.md", "# A\n\nbody A.")
    db = repo / "index.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        def _boom(*_a, **_k):
            raise RuntimeError("forced for test")
        # Indexing must complete without raising.
        summary = indexer.build_index(
            repo, ["."], conn, rebuild=True, prune=False,
            progress_callback=_boom,
        )
        assert summary["files_indexed"] == 1
    finally:
        conn.close()


def test_progress_callback_none_is_noop(tmp_path: Path):
    """Back-compat: omitting callback must not change behaviour."""
    repo = tmp_path
    _write(repo / "a.md", "# A\n\nbody")
    db = repo / "index.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        summary = indexer.build_index(repo, ["."], conn, rebuild=True, prune=False)
        assert summary["files_indexed"] == 1
    finally:
        conn.close()


def test_progress_callback_total_zero_when_no_files(tmp_path: Path):
    repo = tmp_path
    (repo / "empty").mkdir()
    db = repo / "index.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        events: list[tuple[str, int, int]] = []
        indexer.build_index(
            repo, ["empty"], conn, rebuild=True, prune=False,
            progress_callback=lambda *a: events.append(a),
        )
        assert events == []
    finally:
        conn.close()
