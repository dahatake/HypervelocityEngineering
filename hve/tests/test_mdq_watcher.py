"""Tests for hve.mdq.indexer per-file helpers and (optionally) MdqWatcher.

watchdog 未導入の場合、watcher 統合テストは skip される（CI 環境互換）。
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from hve.mdq import indexer, store


SAMPLE_MD = """---
title: ABC
tags: [t1]
---

# Heading One

本文 A。

# Heading Two

本文 B。
"""


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ─────────────────────────────────────────────────────────
# index_one_file / delete_one_file（単体）
# ─────────────────────────────────────────────────────────

def test_index_one_file_creates_chunks(tmp_path: Path):
    repo = tmp_path
    md = repo / "docs" / "x.md"
    _write(md, SAMPLE_MD)
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    res = indexer.index_one_file(repo, md, conn)
    conn.commit()
    assert res["action"] == "indexed"
    assert res["chunks"] >= 2
    assert store.stats(conn)["files"] == 1
    conn.close()


def test_index_one_file_skips_unchanged(tmp_path: Path):
    repo = tmp_path
    md = repo / "docs" / "x.md"
    _write(md, SAMPLE_MD)
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    indexer.index_one_file(repo, md, conn)
    conn.commit()
    res2 = indexer.index_one_file(repo, md, conn)
    assert res2["action"] == "skipped"
    assert res2["chunks"] == 0
    conn.close()


def test_index_one_file_updates_changed(tmp_path: Path):
    repo = tmp_path
    md = repo / "docs" / "x.md"
    _write(md, SAMPLE_MD)
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    indexer.index_one_file(repo, md, conn)
    conn.commit()
    _write(md, SAMPLE_MD + "\n\n# Heading Three\n\n本文 C。\n")
    res = indexer.index_one_file(repo, md, conn)
    conn.commit()
    assert res["action"] == "indexed"
    assert store.stats(conn)["chunks"] >= 3
    conn.close()


def test_index_one_file_missing(tmp_path: Path):
    repo = tmp_path
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    res = indexer.index_one_file(repo, repo / "docs" / "nope.md", conn)
    assert res["action"] == "missing"
    assert res["chunks"] == 0
    conn.close()


def test_delete_one_file_removes_chunks(tmp_path: Path):
    repo = tmp_path
    md = repo / "docs" / "x.md"
    _write(md, SAMPLE_MD)
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    indexer.index_one_file(repo, md, conn)
    conn.commit()
    assert store.stats(conn)["files"] == 1
    res = indexer.delete_one_file("docs/x.md", conn)
    conn.commit()
    assert res["action"] == "deleted"
    assert res["chunks"] >= 1
    assert store.stats(conn)["files"] == 0
    # 二度目はもう存在しない
    res2 = indexer.delete_one_file("docs/x.md", conn)
    assert res2["action"] == "absent"
    conn.close()


def test_build_index_uses_per_file_helper_no_regression(tmp_path: Path):
    """build_index が index_one_file 抽出後も同じ件数を生成することを確認。"""
    repo = tmp_path
    _write(repo / "docs" / "a.md", SAMPLE_MD)
    _write(repo / "docs" / "b.md", SAMPLE_MD)
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    summary = indexer.build_index(repo, ["docs"], conn)
    assert summary["files_indexed"] == 2
    assert summary["files_skipped"] == 0
    assert summary["chunks_written"] >= 4
    # 2 回目は全件 skip
    summary2 = indexer.build_index(repo, ["docs"], conn)
    assert summary2["files_indexed"] == 0
    assert summary2["files_skipped"] == 2
    conn.close()


# ─────────────────────────────────────────────────────────
# MdqWatcher 統合（watchdog 未導入なら skip）
# ─────────────────────────────────────────────────────────

watchdog = pytest.importorskip("watchdog", reason="watchdog 未導入: watcher テストは skip")


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.1) -> bool:
    """``predicate()`` が True になるまで待つ。タイムアウト時 False。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_watcher_detects_create_modify_delete(tmp_path: Path):
    from hve.mdq import watcher as watcher_mod

    repo = tmp_path
    (repo / "docs").mkdir()
    db = repo / ".hve" / "mdq.sqlite"

    w = watcher_mod.MdqWatcher(
        repo_root=repo,
        roots=["docs"],
        db_path=db,
        debounce_ms=100,
    )
    assert w.start() is True
    try:
        target = repo / "docs" / "watch_me.md"
        _write(target, "# Hello\n\n本文。\n")

        def _has_file(rel: str) -> bool:
            conn = store.open_store(db)
            try:
                return rel in store.list_all_paths(conn)
            finally:
                conn.close()

        assert _wait_until(lambda: _has_file("docs/watch_me.md"), timeout=5.0), \
            "create event が反映されなかった"

        # modify
        _write(target, "# Hello\n\n本文（更新）。\n")

        def _has_keyword() -> bool:
            conn = store.open_store(db)
            try:
                cur = conn.execute(
                    "SELECT 1 FROM chunks WHERE path=? AND text LIKE ? LIMIT 1",
                    ("docs/watch_me.md", "%更新%"),
                )
                return cur.fetchone() is not None
            finally:
                conn.close()

        assert _wait_until(_has_keyword, timeout=5.0), \
            "modify event が反映されなかった"

        # delete
        target.unlink()
        assert _wait_until(lambda: not _has_file("docs/watch_me.md"), timeout=5.0), \
            "delete event が反映されなかった"
    finally:
        w.stop()


def test_watcher_ignores_out_of_scope(tmp_path: Path):
    from hve.mdq import watcher as watcher_mod

    repo = tmp_path
    (repo / "docs").mkdir()
    (repo / "outside").mkdir()
    db = repo / ".hve" / "mdq.sqlite"

    w = watcher_mod.MdqWatcher(
        repo_root=repo, roots=["docs"], db_path=db, debounce_ms=100,
    )
    assert w.start() is True
    try:
        _write(repo / "outside" / "x.md", "# z\n")
        time.sleep(0.8)
        conn = store.open_store(db)
        try:
            assert store.stats(conn)["files"] == 0
        finally:
            conn.close()
    finally:
        w.stop()


def test_watcher_start_returns_false_when_watchdog_missing(tmp_path: Path, monkeypatch):
    """watchdog import 失敗を擬似して、警告だけで失敗復帰することを確認。"""
    import sys
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("watchdog"):
            raise ImportError("simulated")
        return real_import(name, *a, **k)

    # 既に import 済みの場合は sys.modules から外す
    for k in list(sys.modules):
        if k.startswith("watchdog"):
            monkeypatch.delitem(sys.modules, k, raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    from hve.mdq import watcher as watcher_mod

    w = watcher_mod.MdqWatcher(repo_root=tmp_path, roots=["docs"],
                               db_path=tmp_path / ".hve" / "mdq.sqlite")
    assert w.start() is False
    w.stop()  # 二重停止安全性
