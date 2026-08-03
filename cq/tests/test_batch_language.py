"""Windows batch 抽出の契約（FR-CQ-04 / FR-CQ-07 / FR-CQ-11）。

レジストリ登録前でも成立するよう、モジュールを直接呼び出す。
"""

from __future__ import annotations

from collections import Counter

import pytest

from cq import languages
from cq.languages import batch, treesitter as ts

SOURCE = """\
@echo off
REM Deploys the app.
:deploy
echo deploying %1
call other.cmd
call :cleanup
exit /b 0

:: helper
:cleanup
echo done
"""


class TestSymbolContract:
    def test_labels_are_the_only_definitions(self) -> None:
        """この文法に関数の概念は無く、`call :name` の飛び先だけが定義単位。"""
        got = Counter((s.kind, s.qualname) for s in batch.extract(SOURCE))
        assert got == Counter([("function", "deploy"), ("function", "cleanup")])

    def test_double_colon_comment_is_not_taken_for_a_label(self) -> None:
        assert "helper" not in {s.name for s in batch.extract(SOURCE)}

    def test_both_comment_forms_become_doc_heads(self) -> None:
        docs = {s.name: s.doc_head for s in batch.extract(SOURCE)}
        assert docs == {"deploy": "REM Deploys the app.", "cleanup": ":: helper"}

    def test_line_ranges_stay_inside_the_file(self) -> None:
        total = len(SOURCE.splitlines())
        for symbol in batch.extract(SOURCE):
            assert 1 <= symbol.start_line <= symbol.end_line <= total

    def test_extraction_is_deterministic(self) -> None:
        assert batch.extract(SOURCE) == batch.extract(SOURCE)


class TestGraphContract:
    def test_commands_and_both_call_forms_become_references(self) -> None:
        refs, imports = batch.extract_graph(SOURCE)
        assert refs == ((4, "echo"), (5, "other.cmd"), (6, "cleanup"), (11, "echo"))
        assert imports == ()

    def test_label_call_drops_the_leading_colon(self) -> None:
        """`call :cleanup` は command_name を持たないので生テキストから解決する。"""
        refs, _ = batch.extract_graph(SOURCE)
        assert (6, "cleanup") in refs and (6, ":cleanup") not in refs


class TestChunkContract:
    def test_labels_get_named_spans(self) -> None:
        spans = batch.chunk_spans(SOURCE, SOURCE.splitlines(), 200)
        assert {(s.name, s.start) for s in spans if s.name} == {("deploy", 3), ("cleanup", 10)}

    def test_spans_stay_inside_the_file(self) -> None:
        total = len(SOURCE.splitlines())
        for span in batch.chunk_spans(SOURCE, SOURCE.splitlines(), 200):
            assert 1 <= span.start <= span.end <= total


class TestDegradation:
    def test_absent_grammar_raises_extraction_error(self, monkeypatch) -> None:
        """文法未導入の環境では indexer が lite へ降格できる形で失敗する。"""
        monkeypatch.setitem(
            ts._PARSERS, "batch", languages.ExtractionError("simulated missing grammar")
        )
        with pytest.raises(languages.ExtractionError):
            batch.extract(SOURCE)
