"""PowerShell 抽出の契約（FR-CQ-04 / FR-CQ-05 / FR-CQ-07 / FR-CQ-11）。

レジストリ登録前でも成立するよう、モジュールを直接呼び出す。
"""

from __future__ import annotations

import shutil
from collections import Counter

import pytest

from cq import languages
from cq.languages import powershell, treesitter as ts

needs_pwsh = pytest.mark.skipif(
    shutil.which("pwsh") is None, reason="pwsh (PowerShell 7+) is not installed"
)


@pytest.fixture(autouse=True)
def _clear_analysis_cache():
    """`_analyse` は source をキーにキャッシュするので、差し替え検証の前に消す。"""
    powershell._analyse.cache_clear()
    yield
    powershell._analyse.cache_clear()

SOURCE = """\
#Requires -Version 7
Import-Module Az.Accounts

# Grants royalty points.
function Get-Royalty {
    param([string] $Name)
    Write-Host $Name
    Invoke-Helper -Name $Name
}

function script:BuildSection {
    'section'
}

enum Tier {
    Bronze
    Gold
}

class Royalty {
    [string] $Name
    [void] Reset() { $this.Name = '' }
    static [int] Zero() { return 0 }
}

filter Short { $_ }

Get-Royalty -Name 'a'
"""


class TestSymbolContract:
    def test_expected_symbols_are_extracted(self) -> None:
        got = Counter((s.kind, s.qualname) for s in powershell.extract(SOURCE))
        assert got == Counter([
            ("function", "Get-Royalty"),
            ("function", "script:BuildSection"),
            ("enum", "Tier"),
            ("class", "Royalty"),
            ("method", "Royalty.Reset"),
            ("method", "Royalty.Zero"),
            ("function", "Short"),
        ])

    def test_scope_qualified_function_name_is_kept_whole(self) -> None:
        """lite の正規表現は `script:BuildSection` を `script` で切ってしまう。"""
        names = {s.name for s in powershell.extract(SOURCE)}
        assert "script:BuildSection" in names and "script" not in names

    def test_class_members_become_methods_of_their_class(self) -> None:
        methods = {s.qualname: s.parent for s in powershell.extract(SOURCE) if s.kind == "method"}
        assert methods == {"Royalty.Reset": "Royalty", "Royalty.Zero": "Royalty"}

    def test_class_property_is_out_of_scope(self) -> None:
        """プロパティは最小 kind 語彙の対象外（Scala の `val` と同方針）。"""
        assert "Name" not in {s.name for s in powershell.extract(SOURCE)}

    def test_signature_stops_before_the_body(self) -> None:
        signatures = {s.name: s.signature for s in powershell.extract(SOURCE)}
        assert signatures["Get-Royalty"] == "function Get-Royalty"
        assert signatures["Zero"] == "static [int] Zero()"
        assert signatures["Royalty"] == "class Royalty"
        assert signatures["Tier"] == "enum Tier"

    def test_preceding_comment_becomes_the_doc_head(self) -> None:
        docs = {s.name: s.doc_head for s in powershell.extract(SOURCE)}
        assert docs["Get-Royalty"] == "# Grants royalty points."

    def test_line_ranges_stay_inside_the_file(self) -> None:
        total = len(SOURCE.splitlines())
        for symbol in powershell.extract(SOURCE):
            assert 1 <= symbol.start_line <= symbol.end_line <= total

    def test_extraction_is_deterministic(self) -> None:
        assert powershell.extract(SOURCE) == powershell.extract(SOURCE)


class TestGraphContract:
    def test_commands_become_references(self) -> None:
        refs, _ = powershell.extract_graph(SOURCE)
        assert (7, "Write-Host") in refs
        assert (8, "Invoke-Helper") in refs
        assert (28, "Get-Royalty") in refs

    def test_module_import_is_reported_as_a_call(self) -> None:
        """`Import-Module` も文法上はただの command。"""
        refs, imports = powershell.extract_graph(SOURCE)
        assert (2, "Import-Module") in refs
        assert imports == ()


class TestChunkContract:
    def test_definitions_get_named_spans_once_the_budget_forces_recursion(self) -> None:
        """トップレベルは `statement_list` 1 個なので、予算を超えて初めて定義単位になる。"""
        source = "function Get-Royalty {\n    Write-Host 'a'\n}\n\nclass Royalty {\n    [void] Reset() { }\n}\n"
        spans = powershell.chunk_spans(source, source.splitlines(), 60)
        assert [(s.start, s.end, s.name) for s in spans] == [
            (1, 3, "Get-Royalty"),
            (5, 7, "Royalty"),
        ]

    def test_spans_stay_inside_the_file(self) -> None:
        total = len(SOURCE.splitlines())
        for span in powershell.chunk_spans(SOURCE, SOURCE.splitlines(), 200):
            assert 1 <= span.start <= span.end <= total

    def test_chunking_is_deterministic(self) -> None:
        lines = SOURCE.splitlines()
        assert powershell.chunk_spans(SOURCE, lines, 200) == powershell.chunk_spans(SOURCE, lines, 200)


class TestDegradation:
    def test_absent_grammar_raises_extraction_error(self, monkeypatch) -> None:
        """文法未導入の環境では indexer が lite へ降格できる形で失敗する。"""
        monkeypatch.setitem(
            ts._PARSERS, "powershell", languages.ExtractionError("simulated missing grammar")
        )
        with pytest.raises(languages.ExtractionError):
            powershell.extract(SOURCE)


# `--input - 2>&1` を tree-sitter-powershell が誤って ERROR にする。実リポジトリの
# `.github/scripts/powershell/lib/gh-api.ps1` で観測した構文の最小再現。
BROKEN = """\
# Sends a request.
function Invoke-Thing {
    gh api --input - 2>&1
}

# Reads the answer.
function Get-Second {
    'ok'
}
"""


class TestOfficialParserEscalation:
    def test_the_grammar_really_fails_on_this_source(self) -> None:
        assert ts.parse(powershell.GRAMMAR, BROKEN).root_node.has_error

    def test_clean_source_does_not_spawn_the_official_parser(self, monkeypatch) -> None:
        """回復ノードが無ければ外部プロセスを起動しない。"""
        calls = []
        monkeypatch.setattr(powershell, "_official_ast", lambda source: calls.append(source))
        powershell.extract(SOURCE)
        assert calls == []

    def test_absent_pwsh_keeps_the_grammar_result(self, monkeypatch) -> None:
        """`pwsh` が無い環境でも tree-sitter の結果で索引を続ける。"""
        monkeypatch.setattr(powershell, "_official_ast", lambda source: None)
        assert {s.name for s in powershell.extract(BROKEN)} == {"Invoke-Thing", "Get-Second"}

    @needs_pwsh
    def test_official_parser_fixes_the_misattributed_doc_comment(self) -> None:
        """ERROR ノードが挟まると tree-sitter は隣の定義の doc を取り違える。"""
        from_grammar = {s.name: s.doc_head for s in ts.extract(powershell.GRAMMAR, BROKEN)}
        assert from_grammar == {"Invoke-Thing": None, "Get-Second": "# Sends a request."}

        docs = {s.name: s.doc_head for s in powershell.extract(BROKEN)}
        assert docs == {"Invoke-Thing": "# Sends a request.", "Get-Second": "# Reads the answer."}

    @needs_pwsh
    def test_escalated_symbols_keep_the_same_shape(self) -> None:
        symbols = powershell.extract(BROKEN)
        assert [(s.kind, s.qualname, s.start_line, s.end_line, s.signature) for s in symbols] == [
            ("function", "Invoke-Thing", 2, 4, "function Invoke-Thing"),
            ("function", "Get-Second", 7, 9, "function Get-Second"),
        ]

    def test_escalated_spans_stay_inside_the_file(self) -> None:
        total = len(BROKEN.splitlines())
        for span in powershell.chunk_spans(BROKEN, BROKEN.splitlines(), 1600):
            assert 1 <= span.start <= span.end <= total
