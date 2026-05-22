"""Tests for mdq.sentence_splitter (regex fallback path; nltk path tested
opportunistically when fastembed/nltk extras are installed)."""
from __future__ import annotations

import importlib

import pytest

from mdq import sentence_splitter as ss


def test_empty_input_returns_empty_list():
    assert ss.split_sentences("") == []
    assert ss.split_with_offsets("") == []


def test_english_basic_split():
    text = "Hello world. This is a test. Final sentence!"
    sents = ss.split_sentences(text)
    assert len(sents) == 3
    assert sents[0].startswith("Hello")
    assert sents[-1].endswith("!")


def test_japanese_basic_split():
    text = "これは日本語です。次の文があります。最後の文！"
    sents = ss.split_sentences(text)
    assert len(sents) == 3
    assert "これは日本語です" in sents[0]
    assert sents[-1].endswith("！")


def test_fenced_code_block_is_atomic():
    text = (
        "Intro sentence. Another one.\n"
        "```python\n"
        "def f():\n"
        "    return 1. plus 2.\n"
        "```\n"
        "Tail sentence."
    )
    sents = ss.split_sentences(text)
    # The fence must appear as a single sentence (not split by the `.` inside).
    fence_sents = [s for s in sents if s.startswith("```python")]
    assert len(fence_sents) == 1
    assert "def f():" in fence_sents[0]
    assert "return 1. plus 2." in fence_sents[0]


def test_pipe_table_is_atomic():
    text = (
        "Heading prose.\n"
        "| a | b |\n"
        "|---|---|\n"
        "| 1 | 2 |\n"
        "Tail prose."
    )
    sents = ss.split_sentences(text)
    table_sents = [s for s in sents if s.startswith("| a |")]
    assert len(table_sents) == 1
    assert "| 1 | 2 |" in table_sents[0]


def test_offsets_locate_substrings_in_original_text():
    text = "First sentence. Second sentence."
    triples = ss.split_with_offsets(text)
    assert len(triples) == 2
    for start, end, sent in triples:
        assert text[start:end] == sent


def test_regex_fallback_when_nltk_unavailable(monkeypatch):
    """Force the nltk import to fail and confirm the splitter still works."""
    def _broken(*_a, **_k):
        raise RuntimeError("forced failure for test")

    monkeypatch.setattr(ss, "_nltk_tokenize", _broken)
    sents = ss.split_sentences("Alpha. Beta. Gamma.")
    assert len(sents) == 3
    assert sents == ["Alpha.", "Beta.", "Gamma."]


def test_japanese_in_regex_fallback(monkeypatch):
    def _broken(*_a, **_k):
        raise RuntimeError("forced failure for test")

    monkeypatch.setattr(ss, "_nltk_tokenize", _broken)
    sents = ss.split_sentences("これはテストです。次の文！")
    assert len(sents) == 2


def test_mixed_block_with_fence_and_prose():
    text = (
        "Prose A. Prose B.\n"
        "```\n"
        "code.line.with.dots\n"
        "```\n"
        "Prose C. Prose D."
    )
    sents = ss.split_sentences(text)
    # We expect at least: "Prose A.", "Prose B.", fence-as-one, "Prose C.", "Prose D."
    assert any(s.startswith("Prose A") for s in sents)
    assert any(s.startswith("Prose D") for s in sents)
    fence_sents = [s for s in sents if s.startswith("```")]
    assert len(fence_sents) == 1
