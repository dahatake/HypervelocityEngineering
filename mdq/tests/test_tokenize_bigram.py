"""FR-MDQ-08 (1): 語彙照合の単位（CJK は隣接 2 文字を 1 語とする）。"""
from __future__ import annotations

from mdq import tokenize as tk


def test_cjk_run_becomes_adjacent_bigrams() -> None:
    assert tk.scoring_terms("業務要件") == ["業務", "務要", "要件"]


def test_katakana_run_becomes_adjacent_bigrams() -> None:
    assert tk.scoring_terms("ランク") == ["ラン", "ンク"]


def test_isolated_cjk_char_stays_a_unigram() -> None:
    assert tk.scoring_terms("A を B") == ["a", "を", "b"]


def test_bigram_and_unigram_are_not_emitted_for_the_same_span() -> None:
    terms = tk.scoring_terms("業務要件")
    assert [t for t in terms if len(t) == 1] == []


def test_ascii_run_is_not_split() -> None:
    assert tk.scoring_terms("markdown_query FR-MDQ-08") == [
        "markdown_query", "fr", "mdq", "08",
    ]


def test_script_boundary_does_not_form_a_bigram() -> None:
    assert tk.scoring_terms("3件") == ["3", "件"]
    assert tk.scoring_terms("aあ") == ["a", "あ"]


def test_cjk_char_ranges_are_published_as_a_single_definition() -> None:
    ranges = tk.CJK_CHAR_RANGES
    assert ranges, "CJK の範囲は単一の定義として公開されていること"
    for low, high in ranges:
        assert len(low) == 1 and len(high) == 1
        assert low <= high


def test_empty_and_symbol_only_input_yields_no_terms() -> None:
    assert tk.scoring_terms("") == []
    assert tk.scoring_terms("---  |") == []


def test_excerpt_tokenizer_shares_the_published_cjk_definition() -> None:
    """`search` 側の抜粋用トークナイザが同じ CJK 定義から作られていること。"""
    from mdq import search as searcher

    for char in ("あ", "ア", "漢", "ー"):
        assert searcher.tokenize(char) == [char]
        assert tk.scoring_terms(char) == [char]
    for char in ("A", "1", "-"):
        assert tk.scoring_terms(char) == searcher.tokenize(char)
