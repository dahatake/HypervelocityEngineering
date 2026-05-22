"""Tests for Markdown chunking strategies and per-(lang, strategy) DB layout."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from mdq import indexer, store, strategies, tokenize


SAMPLE_MD = """\
---
tags: [demo]
---

# Top heading

Intro paragraph one. Some words here.

## Sub A

Sub A body line one.
Sub A body line two.

## Sub B

""" + ("Sub B long body. " * 200) + "\n"


def _write_sample(repo_root: Path) -> Path:
    docs = repo_root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    p = docs / "sample.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")
    return p


def test_db_path_for_lang_strategy_naming() -> None:
    p = store.db_path_for("ja-jp", "heading")
    assert p.as_posix().endswith("/.mdq/index-ja-jp-heading.sqlite") or \
        str(p).endswith(os.sep + "index-ja-jp-heading.sqlite")
    p2 = store.db_path_for("en-us", "fixed_window")
    assert str(p2).endswith("index-en-us-fixed_window.sqlite")


def test_normalize_lang_and_strategy() -> None:
    assert tokenize.normalize("ja_JP") == "ja-jp"
    assert tokenize.normalize("EN-US") == "en-us"
    assert tokenize.normalize("xx") == "ja-jp"  # default
    assert strategies.normalize("fixed_window") == "fixed_window"
    assert strategies.normalize("bogus") == "heading"


def test_strategies_produce_distinct_chunk_sets(tmp_path: Path) -> None:
    p = _write_sample(tmp_path)
    fm_h, chunks_h = strategies.scan_file_for_strategy(tmp_path, p, "heading")
    fm_r, chunks_r = strategies.scan_file_for_strategy(
        tmp_path, p, "heading_recursive"
    )
    fm_f, chunks_f = strategies.scan_file_for_strategy(
        tmp_path, p, "fixed_window"
    )

    assert chunks_h, "heading strategy must yield chunks"
    assert chunks_r, "heading_recursive strategy must yield chunks"
    assert chunks_f, "fixed_window strategy must yield chunks"

    # heading_recursive should split the long 'Sub B' chunk into multiple parts.
    sub_b_parts_h = [c for c in chunks_h if "Sub B" in c.heading_path]
    sub_b_parts_r = [c for c in chunks_r if "Sub B" in c.heading_path]
    assert len(sub_b_parts_r) > len(sub_b_parts_h), \
        "heading_recursive must produce more parts for the oversized Sub B"

    # fixed_window assigns heading_path='(window)' for all chunks.
    assert all(c.heading_path == "(window)" for c in chunks_f)
    # fixed_window splits the large body into multiple windows.
    assert len(chunks_f) >= 2


def test_build_index_uses_strategy_parameter(tmp_path: Path) -> None:
    _write_sample(tmp_path)
    db = tmp_path / store.db_path_for("ja-jp", "fixed_window")
    conn = store.open_store(db, lang="ja-jp")
    try:
        summary = indexer.build_index(
            tmp_path, ["docs"], conn,
            rebuild=True, prune=True, strategy="fixed_window",
        )
    finally:
        conn.close()
    assert summary["files_indexed"] == 1
    assert summary["chunks_written"] >= 2

    # Re-open and verify the stored chunks all have heading_path='(window)'.
    conn = store.open_store(db, lang="ja-jp")
    try:
        rows = conn.execute(
            "SELECT heading_path FROM chunks"
        ).fetchall()
    finally:
        conn.close()
    assert rows and all(r[0] == "(window)" for r in rows)


def test_open_store_with_lang_does_not_raise(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    try:
        # FTS5 mirror should exist when SQLite supports it.
        if store.has_fts5(conn):
            row = conn.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name='chunks_fts'"
            ).fetchone()
            assert row is not None
            sql = row[0] or ""
            # Either trigram or unicode61 — both are acceptable.
            assert "tokenize=" in sql
    finally:
        conn.close()
