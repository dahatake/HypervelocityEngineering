"""Bash 抽出の契約（FR-CQ-04 / FR-CQ-05 / FR-CQ-07 / FR-CQ-11）。

レジストリ登録前でも成立するよう、モジュールを直接呼び出す。
"""

from __future__ import annotations

from collections import Counter

import pytest

from cq import languages
from cq.languages import shell, treesitter as ts

SOURCE = """\
#!/usr/bin/env bash
set -euo pipefail

source ./lib/common.sh

# Deploy the app to Azure.
deploy_app() {
  local rg="$1"
  az group create --name "$rg"
  log_info "done"
}

function retry_once {
  deploy_app "$1" || deploy_app "$1"
}
"""


def _symbols():
    return shell.extract(SOURCE)


class TestSymbolContract:
    def test_both_function_forms_are_extracted(self) -> None:
        got = Counter((s.kind, s.qualname) for s in _symbols())
        assert got == Counter([("function", "deploy_app"), ("function", "retry_once")])

    def test_line_ranges_stay_inside_the_file(self) -> None:
        total = len(SOURCE.splitlines())
        for symbol in _symbols():
            assert 1 <= symbol.start_line <= symbol.end_line <= total

    def test_extraction_is_deterministic(self) -> None:
        assert _symbols() == _symbols()

    def test_signature_stops_before_the_body(self) -> None:
        signatures = {s.name: s.signature for s in _symbols()}
        assert signatures == {"deploy_app": "deploy_app()", "retry_once": "function retry_once"}

    def test_preceding_comment_becomes_the_doc_head(self) -> None:
        docs = {s.name: s.doc_head for s in _symbols()}
        # `#` は共有の doc_head が剥がす marker 集合に含まれないため残る。
        assert docs["deploy_app"] == "# Deploy the app to Azure."
        assert docs["retry_once"] is None


class TestChunkContract:
    def test_each_function_gets_its_own_span(self) -> None:
        spans = shell.chunk_spans(SOURCE, SOURCE.splitlines(), 2000)
        named = {(s.name, s.start, s.end) for s in spans if s.name}
        assert named == {("deploy_app", 7, 11), ("retry_once", 13, 15)}

    def test_spans_stay_inside_the_file(self) -> None:
        """重複の除去は core の責任。言語側はファイル内に収めることだけを保証する。"""
        total = len(SOURCE.splitlines())
        for span in shell.chunk_spans(SOURCE, SOURCE.splitlines(), 200):
            assert 1 <= span.start <= span.end <= total

    def test_chunking_is_deterministic(self) -> None:
        lines = SOURCE.splitlines()
        assert shell.chunk_spans(SOURCE, lines, 200) == shell.chunk_spans(SOURCE, lines, 200)


class TestGraphContract:
    def test_commands_become_references(self) -> None:
        refs, _ = shell.extract_graph(SOURCE)
        assert (9, "az") in refs
        assert (10, "log_info") in refs
        assert refs.count((14, "deploy_app")) == 2

    def test_variable_declaration_is_not_a_reference(self) -> None:
        refs, _ = shell.extract_graph(SOURCE)
        assert "local" not in {name for _, name in refs}

    def test_source_is_reported_as_a_call_not_an_import(self) -> None:
        """`source` は文法上ただの command なので参照側に出る。"""
        refs, imports = shell.extract_graph(SOURCE)
        assert (4, "source") in refs
        assert imports == ()


class TestDegradation:
    def test_absent_grammar_raises_extraction_error(self, monkeypatch) -> None:
        """文法未導入の環境では indexer が lite へ降格できる形で失敗する。"""
        monkeypatch.setitem(
            ts._PARSERS,
            ts.cache_key(shell.GRAMMAR),
            languages.ExtractionError("simulated missing grammar"),
        )
        with pytest.raises(languages.ExtractionError):
            shell.extract(SOURCE)
