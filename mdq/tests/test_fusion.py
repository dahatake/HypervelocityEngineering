"""Tests for late-chunking + linear-weighted fusion (Q9=B).

We bypass the real embedding provider by populating chunk_embedding bytes
directly and monkeypatching :func:`mdq.embeddings.get_provider` to return
a deterministic NullProvider. This exercises the fusion blending math
without any fastembed/network dependency.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mdq import search as searcher
from mdq import store
from mdq import embeddings as emb


def _setup_store(tmp_path: Path):
    db = tmp_path / "fusion.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    store.upsert_file(conn, "a.md", "sha", 1.0, 10, None)
    # Three chunks (BM25 IDF degenerates to 0 with 2 docs / 1 hit).
    null = emb.NullProvider(dim=16)
    text_a = "alpha topic about embeddings"
    text_b = "completely different beta content"
    text_c = "third unrelated gamma material"
    vecs = null.embed([text_a, text_b, text_c])
    store.insert_chunks(conn, [
        ("c_a", "a.md", "# A", 1, 1, 1, 1, text_a, None, 0, 1, None,
         None, vecs[0].tobytes()),
        ("c_b", "a.md", "# B", 1, 2, 2, 1, text_b, None, 0, 1, None,
         None, vecs[1].tobytes()),
        ("c_c", "a.md", "# C", 1, 3, 3, 1, text_c, None, 0, 1, None,
         None, vecs[2].tobytes()),
    ])
    conn.commit()
    return conn


def test_fusion_disabled_when_alpha_none(tmp_path, monkeypatch):
    conn = _setup_store(tmp_path)
    # No fusion_alpha -> pure BM25 path.
    hits = searcher.search(conn, "alpha topic", fusion_alpha=None)
    assert hits  # at least one BM25 hit
    # c_a has direct lexical match → it must rank first.
    assert hits[0].chunk_id == "c_a"


def test_fusion_blends_bm25_and_cosine(tmp_path, monkeypatch):
    conn = _setup_store(tmp_path)
    # Force the search-time provider to be the same NullProvider used at
    # index time so cosine_sim between "alpha topic about embeddings" and
    # the query equals the stored vector dotted with itself (= 1.0).
    monkeypatch.setattr(emb, "get_provider", lambda *a, **kw: emb.NullProvider(dim=16))
    hits = searcher.search(conn, "alpha topic about embeddings", fusion_alpha=0.5)
    assert hits
    # The chunk whose embedding identically matches the query must rank
    # first under any 0 <= alpha < 1 blend, because cosine_sim = 1 dominates.
    assert hits[0].chunk_id == "c_a"


def test_fusion_alpha_zero_pure_cosine(tmp_path, monkeypatch):
    conn = _setup_store(tmp_path)
    monkeypatch.setattr(emb, "get_provider", lambda *a, **kw: emb.NullProvider(dim=16))
    # alpha=0 means score is purely cosine. We query with c_b's exact text
    # so c_b must come first even though "alpha" lexical match is absent.
    hits = searcher.search(
        conn, "completely different beta content", fusion_alpha=0.0
    )
    assert hits
    assert hits[0].chunk_id == "c_b"


def test_fusion_skipped_when_no_embeddings(tmp_path, monkeypatch):
    """If no row has a chunk_embedding, fusion is a no-op even with alpha set."""
    db = tmp_path / "no_emb.sqlite"
    conn = store.open_store(db, lang="ja-jp")
    store.upsert_file(conn, "x.md", "sha", 1.0, 10, None)
    # Need >=3 chunks for BM25 IDF to surface a positive score (see
    # _setup_store doc).
    store.insert_chunks(conn, [
        ("c1", "x.md", "# A", 1, 1, 1, 1, "alpha text", None, 0, 1, None,
         None, None),
        ("c2", "x.md", "# B", 1, 2, 2, 1, "beta foo", None, 0, 1, None,
         None, None),
        ("c3", "x.md", "# C", 1, 3, 3, 1, "gamma bar", None, 0, 1, None,
         None, None),
    ])
    conn.commit()
    # Even if get_provider would fail, fusion_skip must short-circuit first.
    def _boom(*a, **kw):
        raise RuntimeError("must not be called when no embeddings present")
    monkeypatch.setattr(emb, "get_provider", _boom)
    hits = searcher.search(conn, "alpha", fusion_alpha=0.5)
    assert hits
    assert hits[0].chunk_id == "c1"


def test_fusion_falls_back_when_provider_unavailable(tmp_path, monkeypatch):
    conn = _setup_store(tmp_path)
    def _boom(*a, **kw):
        raise emb.EmbeddingsUnavailable("forced for test")
    monkeypatch.setattr(emb, "get_provider", _boom)
    # Should not raise; should silently fall back to BM25-only.
    hits = searcher.search(conn, "alpha topic", fusion_alpha=0.5)
    assert hits
    assert hits[0].chunk_id == "c_a"
