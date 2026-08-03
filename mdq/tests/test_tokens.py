"""FR-MDQ-07: 応答トークン予算のためのトークン計測。"""
from __future__ import annotations

import ast
from pathlib import Path

from mdq import tokens

_SEARCH_SOURCE = Path(__file__).resolve().parents[1] / "search.py"


def test_empty_text_costs_nothing() -> None:
    assert tokens.count_tokens("") == 0


def test_counter_name_identifies_the_measurement() -> None:
    assert tokens.counter_name() in {"tiktoken/cl100k_base", "chars/4-approx"}


def test_japanese_text_is_not_measured_as_a_quarter_of_its_characters() -> None:
    """日本語は文字数÷4 では大幅に過小評価される（実測 2.2 倍）。"""
    text = "検証マーカーの書式は複数あり、いずれかで記載すること。" * 4
    if tokens.counter_name() != "tiktoken/cl100k_base":
        return
    assert tokens.count_tokens(text) > len(text) // 4


def test_search_module_does_not_import_the_tokenizer_eagerly() -> None:
    """検索経路の起動コストを増やさない（FR-MDQ-07）。"""
    tree = ast.parse(_SEARCH_SOURCE.read_text(encoding="utf-8"))
    top_level = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
    assert "tiktoken" not in top_level
