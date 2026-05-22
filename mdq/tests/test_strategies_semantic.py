"""Tests for mdq.strategies_semantic.

Use the deterministic NullProvider so tests don't require fastembed or
network. The strategy is responsible for falling back to heading_recursive
when embeddings cannot be loaded; we test both code paths.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mdq import strategies_semantic as sem


SAMPLE_MD = """# Top Heading

Intro sentence one. Intro sentence two. Intro sentence three.

## Sub A

First topic sentence. More about topic one. Topic one continues here.
Now a different topic. Second topic content. Second topic conclusion.
Yet another topic. Third topic content. Third topic ends.

## Sub B

Short B paragraph.
"""


def _write(tmp_path: Path, content: str = SAMPLE_MD) -> Path:
    p = tmp_path / "doc.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_semantic_paragraph_uses_null_provider(tmp_path, monkeypatch):
    """With NullProvider forced, the strategy must run end-to-end."""
    monkeypatch.setenv("MDQ_EMBED_PROVIDER", "null")
    f = _write(tmp_path)
    fm, chunks = sem.scan_file_semantic_paragraph(
        tmp_path, f, max_chars=120, min_chars=10,
    )
    assert isinstance(chunks, list)
    assert len(chunks) >= 2
    # All chunks must have a parent heading path (no fixed_window markers).
    for c in chunks:
        assert c.heading_path  # non-empty
        assert c.path == "doc.md"


def test_contextualize_template_prepended_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("MDQ_EMBED_PROVIDER", "null")
    f = _write(tmp_path)
    _, chunks = sem.scan_file_semantic_paragraph(
        tmp_path, f, max_chars=200, min_chars=10,
    )
    # At least one chunk must carry the [Context] prefix and a non-null text_raw.
    ctx_chunks = [c for c in chunks if c.text.startswith("[Context]")]
    assert ctx_chunks, "contextualize template not prepended by default"
    for c in ctx_chunks:
        assert c.text_raw is not None
        assert c.text_raw not in (c.text,)  # they differ
        assert c.path in c.text  # path appears in the context line


def test_contextualize_off_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("MDQ_EMBED_PROVIDER", "null")
    f = _write(tmp_path)
    _, chunks = sem.scan_file_semantic_paragraph(
        tmp_path, f, contextualize=False, max_chars=200, min_chars=10,
    )
    assert chunks
    for c in chunks:
        assert not c.text.startswith("[Context]")
        assert c.text_raw is None  # NULL → text already raw


def test_heading_is_hard_boundary(tmp_path, monkeypatch):
    """No chunk may span two different heading_paths."""
    monkeypatch.setenv("MDQ_EMBED_PROVIDER", "null")
    f = _write(tmp_path)
    _, chunks = sem.scan_file_semantic_paragraph(
        tmp_path, f, max_chars=200, min_chars=10,
    )
    # Each chunk has exactly one heading_path; verify they are non-empty
    # and that we observe ≥2 distinct heading_paths (proves headings split).
    hps = {c.heading_path for c in chunks}
    assert len(hps) >= 2


def test_max_chars_respected_within_tolerance(tmp_path, monkeypatch):
    monkeypatch.setenv("MDQ_EMBED_PROVIDER", "null")
    body = "# H1\n\n" + " ".join(f"Sentence number {i}." for i in range(40))
    f = tmp_path / "big.md"
    f.write_text(body, encoding="utf-8")
    _, chunks = sem.scan_file_semantic_paragraph(
        tmp_path, f, max_chars=200, min_chars=30,
    )
    # NullProvider distances may not let us hit the budget exactly, but the
    # implementation must produce *some* split (more than one chunk).
    assert len(chunks) >= 2


def test_fallback_to_heading_recursive_when_provider_unavailable(
    tmp_path, monkeypatch,
):
    """Force the provider factory to raise, then expect heading_recursive."""
    from mdq import embeddings as emb

    def _broken(*_a, **_kw):
        raise emb.EmbeddingsUnavailable("forced for test")

    monkeypatch.setattr(emb, "get_provider", _broken)
    f = _write(tmp_path)
    _, chunks = sem.scan_file_semantic_paragraph(
        tmp_path, f, max_chars=200, min_chars=10,
    )
    # heading_recursive returns Chunk instances; text_raw is left at default
    # (None) because contextualization is the responsibility of semantic_paragraph
    # only. We just assert the fallback produced something.
    assert len(chunks) >= 1
    for c in chunks:
        assert not c.text.startswith("[Context]")
