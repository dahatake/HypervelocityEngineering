"""Contracts for Python symbol extraction (FR-CQ-04)."""

from __future__ import annotations

import pytest

from cq.languages import ExtractionError, python

SOURCE = '''\
"""Module docstring."""
import os


CONST = 1


def top(a, b=1) -> int:
    """Top level helper."""
    def nested():
        pass
    return a


class Widget(Base):
    """A widget."""

    attr = 2

    @property
    def size(self):
        return 1

    async def load(self, *, timeout: float = 1.0) -> None:
        raise NotImplementedError


async def fetch(url):
    pass
'''


@pytest.fixture(scope="module")
def symbols():
    return {s.qualname: s for s in python.extract(SOURCE)}


class TestShape:
    def test_module_level_function(self, symbols) -> None:
        symbol = symbols["top"]
        assert symbol.name == "top"
        assert symbol.kind == "function"
        assert symbol.parent is None
        assert symbol.signature == "def top(a, b=1) -> int"
        assert symbol.doc_head == "Top level helper."

    def test_line_range_covers_the_whole_definition(self, symbols) -> None:
        symbol = symbols["top"]
        assert symbol.start_line == 8
        assert symbol.end_line == 12

    def test_class_and_method_qualnames(self, symbols) -> None:
        assert symbols["Widget"].kind == "class"
        assert symbols["Widget"].signature == "class Widget(Base)"
        assert symbols["Widget.size"].kind == "method"
        assert symbols["Widget.size"].parent == "Widget"

    def test_nested_function_qualname(self, symbols) -> None:
        assert symbols["top.nested"].parent == "top"
        assert symbols["top.nested"].kind == "function"

    def test_async_definitions_keep_the_async_keyword(self, symbols) -> None:
        assert symbols["fetch"].signature == "async def fetch(url)"
        assert symbols["Widget.load"].signature == (
            "async def load(self, *, timeout: float=1.0) -> None"
        )

    def test_decorators_are_captured(self, symbols) -> None:
        assert symbols["Widget.size"].decorators == ("property",)
        assert symbols["top"].decorators == ()

    def test_module_constants_are_not_symbols(self, symbols) -> None:
        assert "CONST" not in symbols
        assert "Widget.attr" not in symbols


class TestTestDetection:
    def test_test_functions_are_flagged(self) -> None:
        found = {s.qualname: s for s in python.extract("def test_a():\n    pass\n")}
        assert found["test_a"].is_test is True

    def test_test_classes_and_their_methods_are_flagged(self) -> None:
        found = {
            s.qualname: s
            for s in python.extract("class TestThing:\n    def check(self):\n        pass\n")
        }
        assert found["TestThing"].is_test is True
        assert found["TestThing.check"].is_test is True

    def test_regular_definitions_are_not_flagged(self) -> None:
        found = {s.qualname: s for s in python.extract("def latest():\n    pass\n")}
        assert found["latest"].is_test is False


class TestRobustness:
    def test_syntax_error_is_reported_for_degradation(self) -> None:
        with pytest.raises(ExtractionError):
            python.extract("def broken(:\n")

    def test_extraction_is_deterministic(self) -> None:
        first = python.extract(SOURCE)
        second = python.extract(SOURCE)
        assert first == second

    def test_symbols_are_ordered_by_position(self, symbols) -> None:
        ordered = python.extract(SOURCE)
        assert [s.start_line for s in ordered] == sorted(s.start_line for s in ordered)

    def test_empty_source_yields_nothing(self) -> None:
        assert python.extract("") == ()
