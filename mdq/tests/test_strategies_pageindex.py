"""Tests for mdq.strategies_pageindex.

The pageindex strategy is LLM-free and deterministic. We verify:
  - Summaries are populated on every chunk.
  - 'head' vs 'first_paragraph' produce distinct outputs.
  - The summary_chars override clips correctly.
  - Files with zero headings still produce a single chunk + summary.
  - Runtime config installed via set_runtime_config is honoured and can
    be cleared.
  - Code-fence safety: the heading line itself is not duplicated into
    the summary.
"""
from __future__ import annotations

from pathlib import Path

from mdq import strategies_pageindex as pi
from mdq import strategies as st


SAMPLE_MD = """# Top Heading

First paragraph of the top section. It has multiple sentences.
A second sentence continues the same paragraph.

A second paragraph after a blank line.

## Sub A

Sub A body paragraph one.

## Sub B

Sub B body paragraph one.
Sub B body paragraph one continues.
"""

NO_HEADING_MD = """Just a plain text file.

With two paragraphs and no markdown headings at all.
"""


def _write(tmp_path: Path, content: str, name: str = "doc.md") -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def setup_function(_func):
    pi.clear_runtime_config()


def teardown_function(_func):
    pi.clear_runtime_config()


def test_pageindex_attaches_summary_to_every_chunk(tmp_path):
    f = _write(tmp_path, SAMPLE_MD)
    fm, chunks = pi.scan_file_pageindex(tmp_path, f)
    assert len(chunks) >= 3  # Top + Sub A + Sub B
    for c in chunks:
        assert c.summary is not None
        assert c.summary  # non-empty for non-empty bodies


def test_pageindex_head_mode_default_200(tmp_path):
    f = _write(tmp_path, SAMPLE_MD)
    fm, chunks = pi.scan_file_pageindex(tmp_path, f)
    top = next(c for c in chunks if c.heading_path == "Top Heading")
    # default mode is "head": summary starts with the first paragraph text.
    assert top.summary.startswith("First paragraph of the top section.")
    # 'head' is purely length-bounded, so the blank line + second paragraph
    # may also be included up to 200 chars (no paragraph cap).
    assert len(top.summary) <= st.PAGEINDEX_SUMMARY_CHARS


def test_pageindex_first_paragraph_mode_stops_at_blank_line(tmp_path):
    pi.set_runtime_config(summary_mode="first_paragraph")
    f = _write(tmp_path, SAMPLE_MD)
    fm, chunks = pi.scan_file_pageindex(tmp_path, f)
    top = next(c for c in chunks if c.heading_path == "Top Heading")
    # In first_paragraph mode, only the first paragraph is taken.
    assert top.summary.startswith("First paragraph of the top section.")
    assert "second paragraph" not in top.summary.lower()


def test_pageindex_summary_chars_override(tmp_path):
    pi.set_runtime_config(summary_chars=30)
    f = _write(tmp_path, SAMPLE_MD)
    fm, chunks = pi.scan_file_pageindex(tmp_path, f)
    for c in chunks:
        assert len(c.summary) <= 30


def test_pageindex_no_headings_single_chunk(tmp_path):
    f = _write(tmp_path, NO_HEADING_MD, name="plain.md")
    fm, chunks = pi.scan_file_pageindex(tmp_path, f)
    assert len(chunks) == 1
    assert chunks[0].summary.startswith("Just a plain text file.")


def test_pageindex_heading_line_not_in_summary(tmp_path):
    f = _write(tmp_path, SAMPLE_MD)
    fm, chunks = pi.scan_file_pageindex(tmp_path, f)
    for c in chunks:
        # The first line of the chunk body is the heading marker
        # (e.g. "# Top Heading"); summary must not start with '#'.
        assert not c.summary.startswith("#")


def test_pageindex_clear_runtime_config(tmp_path):
    pi.set_runtime_config(summary_chars=10)
    pi.clear_runtime_config()
    f = _write(tmp_path, SAMPLE_MD)
    fm, chunks = pi.scan_file_pageindex(tmp_path, f)
    top = next(c for c in chunks if c.heading_path == "Top Heading")
    # Reverted to module default (200).
    assert len(top.summary) > 10


def test_pageindex_summary_skips_none_values_for_empty_body(tmp_path):
    """An empty body (heading-only file) yields an empty-string summary."""
    f = _write(tmp_path, "# Only Heading\n", name="empty.md")
    fm, chunks = pi.scan_file_pageindex(tmp_path, f)
    # A heading-only file may still produce a single chunk; summary is "".
    assert len(chunks) == 1
    assert chunks[0].summary == ""


def test_pageindex_registered_in_all_strategies():
    assert "pageindex" in st.ALL_STRATEGIES
    assert st.normalize("pageindex") == "pageindex"


def test_pageindex_dispatcher_routes_correctly(tmp_path):
    """scan_file_for_strategy must dispatch 'pageindex' to the new module."""
    f = _write(tmp_path, SAMPLE_MD)
    fm, chunks = st.scan_file_for_strategy(tmp_path, f, "pageindex")
    assert chunks
    assert all(c.summary for c in chunks)
