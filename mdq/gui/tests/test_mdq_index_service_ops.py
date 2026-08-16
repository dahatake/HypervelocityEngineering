"""Tests for the new index-service operations (Phase 1 / T04).

Coverage:
  - delete_index_db: existing / missing file, idempotency
  - rebuild_index force=True passes rebuild flag through
  - rebuild_index installs semantic_options into runtime config
  - search_preview returns [] for missing DB and dict rows otherwise
  - get_index_stats never materialises an index as a side effect (FR-GUI-05)
"""
from __future__ import annotations

from pathlib import Path

import pytest

# We test the standalone copy directly; HVE mirror is exercised separately.
from mdq.gui import index_service as svc
from mdq import store


def _seed_index(tmp_path: Path, strategy: str = "heading") -> dict:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text(
        "# Heading\n\nAlpha content paragraph.\n", encoding="utf-8"
    )
    # Patch resolve_effective_roots so we don't depend on cwd settings.
    return svc.rebuild_index(
        tmp_path,
        roots=["docs"],
        strategy=strategy,
    )


def test_delete_index_db_existing(tmp_path: Path):
    _seed_index(tmp_path)
    db = tmp_path / ".mdq" / "index-ja-jp-heading.sqlite"
    assert db.exists()
    r = svc.delete_index_db(tmp_path, strategy="heading")
    assert r["deleted"] is True
    assert not db.exists()


def test_delete_index_db_missing_is_noop(tmp_path: Path):
    r = svc.delete_index_db(tmp_path, strategy="heading")
    assert r["deleted"] is False
    assert "db_path" in r


def test_rebuild_index_force_flag(tmp_path: Path):
    # First build (incremental).
    s1 = _seed_index(tmp_path)
    assert s1["force_rebuild"] is False
    # Second build with force=True; should still succeed and report flag.
    s2 = svc.rebuild_index(
        tmp_path, roots=["docs"], strategy="heading", force=True
    )
    assert s2["force_rebuild"] is True
    # Force always re-indexes existing files (files_indexed >= 1).
    assert s2["files_indexed"] >= 1


def test_rebuild_index_semantic_options_installed(tmp_path: Path, monkeypatch):
    """semantic_options must propagate to strategies_semantic runtime config."""
    captured: dict = {}

    # Patch set_runtime_config to capture the kwargs passed.
    try:
        from mdq import strategies_semantic as sem
    except Exception:
        pytest.skip("strategies_semantic not importable")

    monkeypatch.setattr(sem, "clear_runtime_config", lambda: None)

    def _capture(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(sem, "set_runtime_config", _capture)
    # Force the NullProvider so the build doesn't hit fastembed.
    monkeypatch.setenv("MDQ_EMBED_PROVIDER", "null")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text(
        "# H\n\nfirst sentence. second sentence. third sentence.\n",
        encoding="utf-8",
    )
    svc.rebuild_index(
        tmp_path, roots=["docs"], strategy="semantic_paragraph",
        semantic_options={
            "max_chars": 500,
            "embed_provider": "null",
            "contextualize": False,
        },
    )
    assert captured["max_chars"] == 500
    assert captured["embed_provider"] == "null"
    assert captured["contextualize"] is False


def test_search_preview_returns_empty_for_missing_db(tmp_path: Path):
    rows = svc.search_preview(tmp_path, "anything", strategy="heading")
    assert rows == []


def test_search_preview_returns_rows(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    # Need >=3 docs for BM25 IDF to surface (see mdq.search semantics).
    (tmp_path / "docs" / "a.md").write_text(
        "# A\n\nalpha topic about caches.\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "b.md").write_text(
        "# B\n\ncompletely different beta payload.\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "c.md").write_text(
        "# C\n\nthird unrelated gamma section.\n", encoding="utf-8"
    )
    svc.rebuild_index(tmp_path, roots=["docs"], strategy="heading")
    rows = svc.search_preview(
        tmp_path, "alpha topic", strategy="heading", top_k=3
    )
    assert rows, "expected at least one hit"
    first = rows[0]
    assert set(first) >= {"path", "heading_path", "score", "snippet"}
    assert first["path"] == "docs/a.md"


def test_rebuild_index_progress_callback(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# A\n\nbody A.", encoding="utf-8")
    (tmp_path / "docs" / "b.md").write_text("# B\n\nbody B.", encoding="utf-8")
    events: list[tuple[str, int, int]] = []
    svc.rebuild_index(
        tmp_path, roots=["docs"], strategy="heading",
        progress_callback=lambda rel, cur, total: events.append((rel, cur, total)),
    )
    assert len(events) == 2
    assert events[-1][1] == 2  # current
    assert events[-1][2] == 2  # total


# ---------------------------------------------------------------------------
# FR-GUI-05: 統計取得は索引を新規作成してはならない
# ---------------------------------------------------------------------------


def test_get_index_stats_does_not_create_db(tmp_path: Path):
    """未ビルドの strategy の統計取得が索引 DB を物理生成しないこと。

    GUI は起動時と Strategy 切替時に単一 strategy の統計を取得するため、
    ここで DB が生成されると「DB 有り / 0 件」の false green になる。
    """
    stats = svc.get_index_stats(tmp_path, strategy="heading_recursive")

    db = tmp_path / ".mdq" / "index-ja-jp-heading_recursive.sqlite"
    assert not db.exists(), "統計取得が索引 DB を新規作成した"
    assert stats["db_exists"] is False
    assert stats["files"] == 0
    assert stats["chunks"] == 0
    assert stats["strategy"] == "heading_recursive"
    assert stats["db_path"] == str(db.resolve())


def test_get_index_stats_does_not_create_mdq_dir(tmp_path: Path):
    """索引ディレクトリ自体も統計取得では作らないこと。"""
    svc.get_index_stats(tmp_path, strategy="heading")
    assert not (tmp_path / ".mdq").exists()


def test_get_index_stats_after_delete_does_not_recreate(tmp_path: Path):
    """DB 削除直後の統計取得が削除済み索引を復活させないこと。

    GUI の「DB 削除」は削除後に統計を再取得するため、ここで再生成されると
    削除操作が実質的に無効化される。
    """
    _seed_index(tmp_path)
    db = tmp_path / ".mdq" / "index-ja-jp-heading.sqlite"
    assert db.exists()

    assert svc.delete_index_db(tmp_path, strategy="heading")["deleted"] is True
    stats = svc.get_index_stats(tmp_path, strategy="heading")

    assert not db.exists(), "削除直後の統計取得が索引 DB を再生成した"
    assert stats["db_exists"] is False


def test_get_index_stats_missing_matches_all_strategies(tmp_path: Path):
    """単一取得と一括取得で未ビルド判定が食い違わないこと (FR-MAINT-07)。"""
    single = svc.get_index_stats(tmp_path, strategy="pageindex")
    bulk = svc.get_index_stats_all_strategies(tmp_path)["pageindex"]
    assert single == bulk
