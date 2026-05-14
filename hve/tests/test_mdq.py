import json
import tempfile
from pathlib import Path

import pytest

from hve.mdq import indexer, search as searcher, store


SAMPLE_MD = """---
title: Sample
tags: [demo, alpha]
---

# 概要

これはサンプルです。

## 範囲

- A
- B

## 注意

```python
# This hash is inside a code fence and must not become a heading
print("hello")
```

詳細は別途。

# 別の章

bm25 と grep の挙動を確認する。
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "sample.md").write_text(SAMPLE_MD, encoding="utf-8")
    return tmp_path


def test_scan_extracts_frontmatter_and_chunks(repo: Path):
    fm, chunks = indexer.scan_file(repo, repo / "docs" / "sample.md")
    assert fm.get("title") == "Sample"
    assert "demo" in fm.get("tags", [])

    headings = [c.heading_path for c in chunks]
    # 概要 / 範囲 / 注意 / 別の章 が見出しとして検出される
    assert any(h.endswith("概要") for h in headings)
    assert any("範囲" in h for h in headings)
    assert any("注意" in h for h in headings)
    assert any("別の章" in h for h in headings)

    # コードフェンス内の '#' が見出しになっていないこと
    for c in chunks:
        assert "This hash is inside a code fence" not in c.heading_path


def test_build_index_and_bm25_search(repo: Path, monkeypatch):
    monkeypatch.chdir(repo)
    db = repo / ".hve" / "mdq.sqlite"
    conn = store.open_store(db)

    summary = indexer.build_index(repo, ["docs"], conn)
    assert summary["files_indexed"] == 1
    assert summary["chunks_written"] >= 3

    hits = searcher.search(conn, "bm25 grep", top_k=3)
    assert hits, "expected at least one hit"
    assert hits[0].path == "docs/sample.md"
    assert hits[0].snippet  # not empty


def test_grep_mode_and_path_filter(repo: Path, monkeypatch):
    monkeypatch.chdir(repo)
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    indexer.build_index(repo, ["docs"], conn)

    hits = searcher.search(conn, "範囲", mode="grep", path_globs=["docs/*"])
    assert any("範囲" in h.heading_path or "範囲" in h.snippet for h in hits)


def test_tag_filter(repo: Path, monkeypatch):
    monkeypatch.chdir(repo)
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    indexer.build_index(repo, ["docs"], conn)

    hits = searcher.search(conn, "サンプル", tags=["demo"])
    assert hits
    hits_none = searcher.search(conn, "サンプル", tags=["doesnotexist"])
    assert hits_none == []


def test_incremental_skip(repo: Path, monkeypatch):
    monkeypatch.chdir(repo)
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    s1 = indexer.build_index(repo, ["docs"], conn)
    assert s1["files_indexed"] == 1
    s2 = indexer.build_index(repo, ["docs"], conn)
    assert s2["files_indexed"] == 0
    assert s2["files_skipped"] == 1


def test_prune_removes_deleted_files(repo: Path, monkeypatch):
    monkeypatch.chdir(repo)
    second = repo / "docs" / "second.md"
    second.write_text("# Second\n\nbody\n", encoding="utf-8")
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    s1 = indexer.build_index(repo, ["docs"], conn)
    assert s1["files_indexed"] == 2

    # Delete one file and re-index
    second.unlink()
    s2 = indexer.build_index(repo, ["docs"], conn)
    assert s2["pruned_files"] == 1
    assert s2["pruned_chunks"] >= 1
    assert store.stats(conn)["files"] == 1


def test_prune_disabled(repo: Path, monkeypatch):
    monkeypatch.chdir(repo)
    second = repo / "docs" / "second.md"
    second.write_text("# Second\n\nbody\n", encoding="utf-8")
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    indexer.build_index(repo, ["docs"], conn)
    second.unlink()
    s = indexer.build_index(repo, ["docs"], conn, prune=False)
    assert s["pruned_files"] == 0
    assert store.stats(conn)["files"] == 2


def test_prune_respects_root_scope(repo: Path, monkeypatch):
    """Files outside the requested roots must not be pruned."""
    monkeypatch.chdir(repo)
    other_root = repo / "knowledge"
    other_root.mkdir()
    other_file = other_root / "k.md"
    other_file.write_text("# K\n\nkbody\n", encoding="utf-8")
    conn = store.open_store(repo / ".hve" / "mdq.sqlite")
    # Index both roots first
    indexer.build_index(repo, ["docs", "knowledge"], conn)
    assert store.stats(conn)["files"] == 2
    # Re-index only docs root - knowledge/k.md must be preserved
    s = indexer.build_index(repo, ["docs"], conn)
    assert s["pruned_files"] == 0
    assert store.stats(conn)["files"] == 2


def test_cli_search_jsonl(repo: Path, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    from hve.mdq import cli
    assert cli.main(["index"]) == 0
    capsys.readouterr()
    assert cli.main(["search", "--q", "概要", "--top-k", "2"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out, "expected JSONL output"
    parsed = json.loads(out[0])
    assert "chunk_id" in parsed and "snippet" in parsed


def test_cli_index_max_chunk_chars(tmp_path: Path, monkeypatch, capsys):
    """--max-chunk-chars が指定されると大きなチャンクが分割される。"""
    body = "\n\n".join(["X" * 80 for _ in range(10)])
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "big.md").write_text(f"# H\n\n{body}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    from hve.mdq import cli
    assert cli.main(["index", "--root", "docs", "--max-chunk-chars", "150"]) == 0
    out = capsys.readouterr().out.strip()
    summary = json.loads(out)
    assert summary["chunks_written"] >= 3


def test_cli_search_include_parent(tmp_path: Path, monkeypatch, capsys):
    """--include-parent で expansion.parent が JSON 出力に含まれる。"""
    md = (
        "# A\n\nintro\n\n## B\n\nfiller B\n\n### C\n\n"
        "body of C with searchunique token\n"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text(md, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    from hve.mdq import cli
    assert cli.main(["index"]) == 0
    capsys.readouterr()
    rc = cli.main([
        "search", "--q", "searchunique", "--top-k", "3", "--include-parent",
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out
    found = False
    for line in out:
        d = json.loads(line)
        if d.get("expansion", {}).get("parent"):
            found = True
            break
    assert found, "expected at least one hit with expansion.parent"


# ---------------------------------------------------------------------------
# T01: schema migration - part_index / part_total columns
# ---------------------------------------------------------------------------

def test_schema_has_part_columns(tmp_path: Path):
    """新規 DB は chunks テーブルに part_index / part_total を持つ。"""
    conn = store.open_store(tmp_path / "mdq.sqlite")
    cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
    assert "part_index" in cols
    assert "part_total" in cols


def test_schema_user_version_set(tmp_path: Path):
    """マイグレーション識別用に PRAGMA user_version が 1 以上に設定される。"""
    conn = store.open_store(tmp_path / "mdq.sqlite")
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    assert v >= 1


def test_schema_migrates_legacy_db(tmp_path: Path):
    """part_* カラムを持たない旧 DB を開いた際に ALTER TABLE で追加される。"""
    import sqlite3
    db = tmp_path / "legacy.sqlite"
    legacy_schema = """
    CREATE TABLE files (
      path TEXT PRIMARY KEY, sha1 TEXT NOT NULL, mtime REAL NOT NULL,
      size_bytes INTEGER NOT NULL, frontmatter TEXT
    );
    CREATE TABLE chunks (
      chunk_id TEXT PRIMARY KEY, path TEXT NOT NULL,
      heading_path TEXT NOT NULL, level INTEGER NOT NULL,
      start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
      token_est INTEGER NOT NULL, text TEXT NOT NULL, tags TEXT
    );
    """
    raw = sqlite3.connect(str(db))
    raw.executescript(legacy_schema)
    raw.execute(
        "INSERT INTO chunks VALUES('abc','docs/x.md','# H',1,1,5,3,'body','[]')"
    )
    raw.commit()
    raw.close()

    conn = store.open_store(db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
    assert "part_index" in cols
    assert "part_total" in cols
    # v2 migration drops legacy chunk rows (chunk_id 算出規則が変わるため)。
    # files 側は保持され、sha1 がクリアされて次回 index で再構築対象になる。
    n = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    assert n == 0


def test_chunk_dataclass_has_part_fields():
    """Chunk dataclass に part_index / part_total が追加される。"""
    c = indexer.Chunk(
        path="docs/x.md", heading_path="# H", level=1,
        start_line=1, end_line=3, text="body",
    )
    assert c.part_index == 0
    assert c.part_total == 1


def test_insert_chunks_persists_part_fields(tmp_path: Path, monkeypatch):
    """build_index 経由で part_index / part_total が永続化される。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "s.md").write_text("# H\n\nbody\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    conn = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    indexer.build_index(tmp_path, ["docs"], conn)
    rows = list(conn.execute(
        "SELECT part_index, part_total FROM chunks"
    ))
    assert rows, "expected at least one chunk row"
    # 既定の subdivide 無効 (max_chunk_chars=0) では part_total=1
    for pi, pt in rows:
        assert pi == 0
        assert pt == 1


# ---------------------------------------------------------------------------
# T02: _subdivide - large chunk secondary splitting
# ---------------------------------------------------------------------------

def test_subdivide_disabled_returns_single(tmp_path: Path):
    """max_chars<=0 では分割されず 1 件のみ返す（start/end_line は不変）。"""
    text = "para1\n\npara2\n\npara3"
    parts = indexer._subdivide(text, start_line=10, max_chars=0)
    assert len(parts) == 1
    t, s, e = parts[0]
    assert t == text
    assert s == 10
    # end_line は start_line + (行数 - 1)
    assert e == 10 + text.count("\n")


def test_subdivide_short_text_returns_single(tmp_path: Path):
    """MAX 以下の短文は分割されない。"""
    text = "short body"
    parts = indexer._subdivide(text, start_line=1, max_chars=1000)
    assert len(parts) == 1
    assert parts[0][0] == text


def test_subdivide_splits_on_paragraph_boundary(tmp_path: Path):
    """段落区切り (\\n\\n) で MAX を超えないようまとまる。"""
    p1 = "A" * 50
    p2 = "B" * 50
    p3 = "C" * 50
    text = f"{p1}\n\n{p2}\n\n{p3}"
    parts = indexer._subdivide(text, start_line=1, max_chars=70)
    # 各段落 50 chars < 70 だが 2 段落結合 (~102) は超えるため、
    # 個別段落ごとに分割される
    assert len(parts) == 3
    bodies = [p[0] for p in parts]
    assert p1 in bodies[0]
    assert p2 in bodies[1]
    assert p3 in bodies[2]
    # start_line は単調増加
    assert parts[0][1] <= parts[1][1] <= parts[2][1]
    # 各 part の end_line >= start_line
    for body, s, e in parts:
        assert e >= s


def test_subdivide_keeps_fenced_code_block_intact(tmp_path: Path):
    """フェンス内に \\n\\n があってもフェンス全体は不可分。"""
    fence = "```\n" + "x\n\ny\n" * 20 + "```"
    text = f"intro\n\n{fence}\n\noutro"
    parts = indexer._subdivide(text, start_line=1, max_chars=50)
    # フェンスを含む part が 1 つ残ること（途中で切れない）
    fence_parts = [p[0] for p in parts if "```" in p[0]]
    assert len(fence_parts) == 1
    # フェンス開始と終了が同じ part に含まれる
    fp = fence_parts[0]
    assert fp.count("```") >= 2


def test_subdivide_falls_back_to_line_split_for_huge_paragraph(tmp_path: Path):
    """単一段落が MAX を大幅に超える場合は行で分割される。"""
    big = "\n".join([f"line-{i}" for i in range(100)])  # 1 段落 100 行
    parts = indexer._subdivide(big, start_line=1, max_chars=100)
    assert len(parts) >= 2
    # 連結すれば元のテキストを再構成できる（行順保持）
    rejoined = "\n".join(p[0] for p in parts)
    assert rejoined.replace("\n", "") == big.replace("\n", "")


# ---------------------------------------------------------------------------
# T03: _split_chunks integration with _subdivide
# ---------------------------------------------------------------------------

def test_build_index_subdivides_large_chunks(tmp_path: Path, monkeypatch):
    """max_chunk_chars 指定時、大きな見出しチャンクが 2 次分割される。"""
    # 1 つの見出し配下に大量段落を持つドキュメント
    body = "\n\n".join([f"paragraph {i} " + "x" * 80 for i in range(20)])
    md = f"# Big\n\n{body}\n"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "big.md").write_text(md, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    conn = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    summary = indexer.build_index(tmp_path, ["docs"], conn, max_chunk_chars=200)
    assert summary["files_indexed"] == 1
    # 同一 heading_path のチャンクが複数ある
    rows = list(conn.execute(
        "SELECT heading_path, part_index, part_total, start_line, end_line "
        "FROM chunks WHERE heading_path = ? ORDER BY part_index",
        ("Big",),
    ))
    assert len(rows) >= 2, f"expected multi-part chunks, got {rows}"
    # part_total はすべて同じで、件数と一致
    totals = {r[2] for r in rows}
    assert totals == {len(rows)}
    # part_index は 0..N-1 で連番
    assert [r[1] for r in rows] == list(range(len(rows)))
    # start_line は単調増加
    starts = [r[3] for r in rows]
    assert starts == sorted(starts)


def test_build_index_default_no_subdivision(tmp_path: Path, monkeypatch):
    """max_chunk_chars 既定 (0) では従来通り分割されない。"""
    body = "para\n\n" * 50
    md = f"# H\n\n{body}\n"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text(md, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    conn = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    indexer.build_index(tmp_path, ["docs"], conn)
    rows = list(conn.execute(
        "SELECT part_index, part_total FROM chunks WHERE heading_path = ?",
        ("H",),
    ))
    assert rows
    for pi, pt in rows:
        assert pi == 0 and pt == 1


def test_subdivided_chunks_have_unique_ids(tmp_path: Path, monkeypatch):
    """2 次分割後も chunk_id は重複しない（start_line がずれるため）。"""
    body = "\n\n".join(["X" * 80 for _ in range(10)])
    md = f"# H\n\n{body}\n"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "y.md").write_text(md, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    conn = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    indexer.build_index(tmp_path, ["docs"], conn, max_chunk_chars=150)
    ids = [r[0] for r in conn.execute("SELECT chunk_id FROM chunks")]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# T07: chunk_id stability across line shifts + duplicate heading handling
# ---------------------------------------------------------------------------

def test_chunk_id_stable_across_line_shift(tmp_path: Path, monkeypatch):
    """前置行を追加して start_line が変わっても chunk_id は維持される。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    f = tmp_path / "docs" / "stable.md"
    f.write_text("# A\n\nbody A\n\n## B\n\nbody B\n", encoding="utf-8")
    conn1 = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    indexer.build_index(tmp_path, ["docs"], conn1)
    before = {
        r["heading_path"]: r["chunk_id"]
        for r in store.all_chunks(conn1)
    }
    conn1.close()

    # 前置に空行を 3 行追加 (start_line が +3 シフトする)
    f.write_text("\n\n\n# A\n\nbody A\n\n## B\n\nbody B\n", encoding="utf-8")
    conn2 = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    indexer.build_index(tmp_path, ["docs"], conn2, rebuild=True)
    after = {
        r["heading_path"]: r["chunk_id"]
        for r in store.all_chunks(conn2)
    }
    assert before["A"] == after["A"]
    assert before["A > B"] == after["A > B"]


def test_chunk_id_disambiguates_duplicate_heading(tmp_path: Path, monkeypatch):
    """同一ファイル内の重複見出しは別 chunk_id を持つ。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "dup.md").write_text(
        "# H\n\nfirst\n\n# H\n\nsecond\n", encoding="utf-8"
    )
    conn = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    indexer.build_index(tmp_path, ["docs"], conn)
    ids = [r["chunk_id"] for r in store.all_chunks(conn)]
    assert len(ids) == len(set(ids)), "重複 chunk_id 検出"


def test_schema_v2_drops_legacy_chunks(tmp_path: Path):
    """v1 で作られた chunk_id (start_line ベース) は v2 オープン時に再構築対象になる。"""
    import sqlite3
    db = tmp_path / "legacy_v1.sqlite"
    raw = sqlite3.connect(str(db))
    raw.executescript(
        """
        CREATE TABLE files (
          path TEXT PRIMARY KEY, sha1 TEXT NOT NULL, mtime REAL NOT NULL,
          size_bytes INTEGER NOT NULL, frontmatter TEXT
        );
        CREATE TABLE chunks (
          chunk_id TEXT PRIMARY KEY, path TEXT NOT NULL,
          heading_path TEXT NOT NULL, level INTEGER NOT NULL,
          start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
          token_est INTEGER NOT NULL, text TEXT NOT NULL, tags TEXT,
          part_index INTEGER NOT NULL DEFAULT 0,
          part_total INTEGER NOT NULL DEFAULT 1
        );
        PRAGMA user_version = 1;
        INSERT INTO files VALUES ('docs/legacy.md', 'oldsha', 0.0, 10, NULL);
        INSERT INTO chunks VALUES (
          'legacyid', 'docs/legacy.md', 'X', 1, 1, 1, 1, 'x', NULL, 0, 1
        );
        """
    )
    raw.commit()
    raw.close()

    conn = store.open_store(db)
    n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    sha = conn.execute("SELECT sha1 FROM files").fetchone()[0]
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    assert v >= 2
    assert n_chunks == 0  # v1 chunks dropped
    assert sha == ""  # forces re-scan on next index


# ---------------------------------------------------------------------------
# T08: optional FTS5 engine
# ---------------------------------------------------------------------------

def test_fts5_engine_returns_hits_when_available(tmp_path: Path, monkeypatch):
    """engine='fts5' (利用可能環境) で BM25 同等のヒットが返る。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "f.md").write_text(
        "# A\n\nintro\n\n## B\n\nbody with ftsuniquetoken here\n",
        encoding="utf-8",
    )
    conn = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    if not store.has_fts5(conn):
        pytest.skip("FTS5 not available in this SQLite build")
    indexer.build_index(tmp_path, ["docs"], conn)
    # explicit engine override
    hits = searcher.search(conn, "ftsuniquetoken", top_k=3, engine="fts5")
    assert hits, "FTS5 経路でヒットが返らない"
    assert any("ftsuniquetoken" in h.snippet for h in hits)


def test_fts5_engine_silently_falls_back_when_unsupported(tmp_path: Path, monkeypatch):
    """engine='fts5' でも FTS5 非対応なら BM25 経路にフォールバックする。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "g.md").write_text(
        "# H\n\nfallbacktoken sentence\n\n## H2\n\nother content\n\n"
        "## H3\n\nmore filler\n",
        encoding="utf-8",
    )
    conn = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    indexer.build_index(tmp_path, ["docs"], conn)

    # has_fts5 を強制的に False にして BM25 経路を確認
    monkeypatch.setattr(store, "has_fts5", lambda c: False)
    hits = searcher.search(conn, "fallbacktoken", top_k=3, engine="fts5")
    assert hits  # BM25 でもヒットすること


# ---------------------------------------------------------------------------
# T04: search expansion - parent / neighbors / parts
# ---------------------------------------------------------------------------

EXPANSION_MD = """# A

intro A

## B

body of B normal content here
clear marker line

### C

body of C with zebraunique token only

## D

body of D normal text

## E

body of E filler

## F

body of F filler text
"""


@pytest.fixture()
def expand_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "exp.md").write_text(EXPANSION_MD, encoding="utf-8")
    return tmp_path


def test_search_include_parent_returns_parent_chunk(expand_repo, monkeypatch):
    """include_parent=True で親見出しチャンクが expansion.parent に入る。"""
    monkeypatch.chdir(expand_repo)
    conn = store.open_store(expand_repo / ".hve" / "mdq.sqlite")
    indexer.build_index(expand_repo, ["docs"], conn)
    hits = searcher.search(
        conn, "zebraunique", top_k=5, include_parent=True
    )
    assert hits
    # C ヒット (heading_path = "A > B > C") には親 "A > B" が含まれる
    c_hit = next((h for h in hits if h.heading_path.endswith("> C")), None)
    assert c_hit is not None, [h.heading_path for h in hits]
    assert c_hit.expansion is not None
    parent = c_hit.expansion.get("parent")
    assert parent is not None
    assert parent["heading_path"] == "A > B"


def test_search_expand_neighbors_returns_adjacent(expand_repo, monkeypatch):
    """expand_neighbors=N で同一ファイル内の前後 N チャンクを同梱。"""
    monkeypatch.chdir(expand_repo)
    conn = store.open_store(expand_repo / ".hve" / "mdq.sqlite")
    indexer.build_index(expand_repo, ["docs"], conn)
    hits = searcher.search(
        conn, "zebraunique", top_k=5, expand_neighbors=1
    )
    assert hits
    top = hits[0]
    assert top.expansion is not None
    neigh = top.expansion.get("neighbors", [])
    # 隣接が 1〜2 件含まれる (ファイル境界に依存)
    assert 1 <= len(neigh) <= 2
    # neighbors の chunk_id はヒット本体と異なる
    for n in neigh:
        assert n["chunk_id"] != top.chunk_id


def test_search_merge_parts_returns_sibling_parts(tmp_path: Path, monkeypatch):
    """merge_parts=True で part_total>1 の他 part が同梱される。"""
    # 1 つの段落にだけ希少語を入れ、他段落はフィラー
    paragraphs = ["FILLER " + "X" * 80 for _ in range(8)]
    paragraphs[3] = "zebraunique " + "X" * 80
    body = "\n\n".join(paragraphs)
    md = f"# H\n\n{body}\n"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "p.md").write_text(md, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    conn = store.open_store(tmp_path / ".hve" / "mdq.sqlite")
    indexer.build_index(tmp_path, ["docs"], conn, max_chunk_chars=200)
    hits = searcher.search(
        conn, "zebraunique", top_k=1, merge_parts=True
    )
    assert hits
    top = hits[0]
    assert top.expansion is not None
    parts = top.expansion.get("parts", [])
    assert len(parts) >= 1
    # 全 part の chunk_id は本体と異なる
    for p in parts:
        assert p["chunk_id"] != top.chunk_id


def test_search_expansion_disabled_by_default(expand_repo, monkeypatch):
    """既定 (オプションなし) では expansion キーが付かない。"""
    monkeypatch.chdir(expand_repo)
    conn = store.open_store(expand_repo / ".hve" / "mdq.sqlite")
    indexer.build_index(expand_repo, ["docs"], conn)
    hits = searcher.search(conn, "zebraunique", top_k=3)
    assert hits
    for h in hits:
        d = h.to_dict()
        assert "expansion" not in d
