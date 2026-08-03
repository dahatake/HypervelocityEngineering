"""Contracts for cq token counting (NFR-CQ-01)."""

from __future__ import annotations

import ast
from pathlib import Path

from cq import tokens

SOURCE = Path(__file__).resolve().parents[1] / "tokens.py"


class TestCounter:
    def test_empty_text_is_zero(self) -> None:
        assert tokens.count_tokens("") == 0

    def test_longer_text_costs_more(self) -> None:
        assert tokens.count_tokens("def resolve(x): return x" * 20) > tokens.count_tokens("x")

    def test_counter_name_is_reported(self) -> None:
        assert tokens.counter_name() in {"tiktoken/cl100k_base", "chars/4-approx"}

    def test_counter_name_matches_counting_behaviour(self) -> None:
        """近似値を厳密値として提示しないため、名称と実際の計数器を一致させる。"""
        name = tokens.counter_name()
        approx = max(1, int(len("hello world example") / 4.0))
        if name == "chars/4-approx":
            assert tokens.count_tokens("hello world example") == approx


class TestLazyImport:
    def test_tiktoken_is_not_imported_at_module_import_time(self) -> None:
        """検索経路の起動コストを増やさないため、tiktoken は関数内で import する。"""
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        top_level = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert "tiktoken" not in top_level
