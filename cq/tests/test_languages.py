"""Contracts for the language registry and parser degradation (FR-CQ-11)."""

from __future__ import annotations

import ast
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from cq import config, chunking, discovery, indexer, languages, store

REPO_ROOT = Path(__file__).resolve().parents[2]
LANGUAGES_DIR = REPO_ROOT / "cq" / "languages"
CORE_MODULES = ("indexer.py", "search.py", "store.py", "chunking.py", "discovery.py")

CSHARP = """\
namespace Svc;

public sealed class LedgerService : ILedger
{
    private readonly int _seed;

    public GrantResult GrantPoints(
        GrantCommand command,
        int attempts)
    {
        return new GrantResult(attempts);
    }

    public void Reset() { }
}

public sealed record GrantCommand(string Id, int Amount);
"""

CSHARP_DECLARATION_KEYWORDS = """\
namespace Svc;

public interface ILedger
{
}

public struct Points
{
}

public enum Status
{
    Active,
}

public sealed record GrantCommand(string Id, int Amount);

public class LedgerService
{
}
"""

JAVASCRIPT = """\
import { helper } from './helper.js';

export function mountScreen(container, deps) {
  return container;
}

class KnowledgeSearchView {
  render(items) {
    return items;
  }
}

const resolveAuthResult = (result) => result;
export default KnowledgeSearchView;
"""


class TestRegistry:
    def test_language_modules_are_self_contained(self) -> None:
        """言語追加は 1 ファイル追加で済む（FR-CQ-11）。"""
        assert (LANGUAGES_DIR / "python.py").is_file()
        assert (LANGUAGES_DIR / "lite.py").is_file()

    def test_registry_maps_every_discoverable_language(self) -> None:
        for lang in set(languages.LANGUAGE_BY_SUFFIX.values()):
            assert languages.extractor_for(lang) is not None

    @pytest.mark.parametrize("module", CORE_MODULES)
    def test_core_modules_do_not_branch_on_language_names(self, module: str) -> None:
        """中核実装に言語名を散らかさない。"""
        source = (REPO_ROOT / "cq" / module).read_text(encoding="utf-8")
        tree = ast.parse(source)
        literals = {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert "csharp" not in literals
        assert "javascript" not in literals


class TestCSharp:
    def _symbols(self):
        extractor = languages.extractor_for("csharp")
        return {s.name: s for s in extractor(CSHARP)}

    def test_sealed_class_is_extracted(self) -> None:
        symbol = self._symbols()["LedgerService"]
        assert symbol.kind == "class"
        assert symbol.start_line == 3

    def test_record_is_extracted(self) -> None:
        assert self._symbols()["GrantCommand"].kind == "class"

    @pytest.mark.parametrize(
        ("name", "kind"),
        [
            ("ILedger", "interface"),
            ("Points", "struct"),
            ("Status", "enum"),
            ("GrantCommand", "class"),
            ("LedgerService", "class"),
        ],
    )
    def test_declaration_keyword_decides_the_kind(self, name: str, kind: str) -> None:
        """FR-CQ-04: `record` has no kind of its own, but the rest must not collapse."""
        extractor = languages.extractor_for("csharp")
        symbols = {s.name: s for s in extractor(CSHARP_DECLARATION_KEYWORDS)}
        assert symbols[name].kind == kind

    def test_members_of_a_non_class_type_keep_their_parent(self) -> None:
        extractor = languages.extractor_for("csharp")
        source = "public interface ILedger\n{\n    public void Grant() { }\n}\n"
        symbols = {s.name: s for s in extractor(source)}
        assert symbols["Grant"].qualname == "ILedger.Grant"

    def test_multiline_signature_method_is_extracted(self) -> None:
        symbol = self._symbols()["GrantPoints"]
        assert symbol.kind == "method"
        assert symbol.start_line == 7

    def test_single_line_method_is_extracted(self) -> None:
        assert self._symbols()["Reset"].kind == "method"

    def test_fields_are_not_symbols(self) -> None:
        assert "_seed" not in self._symbols()


class TestJavaScript:
    def _symbols(self):
        extractor = languages.extractor_for("javascript")
        return {s.name: s for s in extractor(JAVASCRIPT)}

    def test_exported_function_is_extracted(self) -> None:
        assert self._symbols()["mountScreen"].kind == "function"

    def test_class_is_extracted(self) -> None:
        assert self._symbols()["KnowledgeSearchView"].kind == "class"

    def test_class_method_is_extracted(self) -> None:
        assert self._symbols()["render"].kind == "method"

    def test_arrow_function_constant_is_extracted(self) -> None:
        assert self._symbols()["resolveAuthResult"].kind == "function"

    def test_import_statements_are_not_symbols(self) -> None:
        assert "helper" not in self._symbols()


JAVASCRIPT_TESTS = """\
import { render } from './portal.js';

describe('tab navigation', () => {
  it('moves focus to the next tab', () => {
    expect(render()).toBeTruthy();
  });

  test('wraps around at the end', async () => {
    expect(true).toBe(true);
  });

  it.skip('is temporarily disabled', () => {});
});

notATest('should not be indexed', () => {});
"""


class TestJavaScriptTestBlocks:
    """`describe` / `it` / `test` はブロック名で引けなければならない（FR-CQ-04）。

    実測: src/ の JS 76 ファイル中 46 がシンボル 0 で、そのうち 42 ファイル・
    120 個がこの形のテストブロックだった。宣言構文ではないため 1 件も拾えていなかった。
    """

    def _symbols(self):
        return {s.name: s for s in languages.extractor_for("javascript")(JAVASCRIPT_TESTS)}

    @pytest.mark.parametrize(
        "name",
        [
            "tab navigation",
            "moves focus to the next tab",
            "wraps around at the end",
            "is temporarily disabled",
        ],
    )
    def test_test_blocks_are_extracted_by_their_label(self, name: str) -> None:
        assert name in self._symbols()

    def test_test_blocks_are_flagged_as_tests(self) -> None:
        assert self._symbols()["moves focus to the next tab"].is_test

    def test_ordinary_calls_are_not_symbols(self) -> None:
        """`call_expression` を丸ごと拾うと索引が雑音で埋まる。"""
        symbols = self._symbols()
        assert "should not be indexed" not in symbols
        assert "render" not in symbols

    def test_the_block_chunk_carries_the_label(self) -> None:
        """チャンクの `name` は BM25 の最大重み（10.0）列なので、空だと順位が付かない。

        シンボルだけ増やしてもチャンクが無名のままでは検索順位は改善しない。
        """
        chunks = chunking.chunk_source(JAVASCRIPT_TESTS, "javascript", max_chars=1200)
        assert "tab navigation" in {c.name for c in chunks}


class TestDegradation:
    def test_extraction_error_degrades_instead_of_failing(self, monkeypatch) -> None:
        """専用抽出器が失敗しても索引処理全体を落とさない（FR-CQ-11）。"""
        def broken(_source: str):
            raise languages.ExtractionError("simulated parser outage")

        support = languages.LanguageSupport(parser="regex", extract=broken)
        monkeypatch.setattr(languages, "_registry", lambda: {"csharp": support})
        symbols, parser = indexer._extract("csharp", CSHARP)
        assert parser == "lite"
        assert symbols

    def test_languages_without_a_module_use_the_lite_parser(self) -> None:
        """未登録の言語は専用抽出器を持たず lite へ降格する（FR-CQ-11）。"""
        assert languages.extractor_for("nothing-registered") is None
        symbols, parser = indexer._extract("nothing-registered", "def a():\n    return 1\n")
        assert parser == "lite"
        assert {s.name for s in symbols} >= {"a"}

    def test_fidelity_is_reported_per_file(self, tmp_path: Path, monkeypatch) -> None:
        """FR-CQ-04: different fidelities coexist in the same index. C# is
        forced onto its regex fallback here, since Phase 2 made tree-sitter
        its default whenever the grammar is installed (as it is in dev/CI)."""
        from cq.languages import csharp, treesitter as ts

        monkeypatch.setitem(
            ts._PARSERS,
            ts.cache_key(csharp.GRAMMAR),
            languages.ExtractionError("simulated missing grammar"),
        )
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        (tmp_path / "cq.toml").write_text("[profiles.test]\nroots = ['pkg']\n", encoding="utf-8")
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        (tmp_path / "pkg" / "b.cs").write_text(CSHARP, encoding="utf-8")
        (tmp_path / "pkg" / "c.sh").write_text("run_it() {\n  echo hi\n}\n", encoding="utf-8")
        profile = config.resolve_profile(tmp_path, "test")
        db = tmp_path / ".cq" / "index-test.sqlite"
        indexer.build_index(tmp_path, profile, db_path=db)
        with closing(store.open_store(db, create=False)) as conn:
            parsers = dict(conn.execute("SELECT path, parser FROM files"))
        assert parsers["pkg/a.py"] == "ast"
        assert parsers["pkg/b.cs"] == "regex"
        assert parsers["pkg/c.sh"] == "tree-sitter"

    def test_csharp_uses_tree_sitter_when_the_grammar_is_installed(self) -> None:
        """Phase 2 (FR-CQ-11): the grammar is preferred whenever it is available."""
        symbols, parser = indexer._extract("csharp", CSHARP)
        assert parser == "tree-sitter"
        assert symbols

    def test_python_only_environment_still_works(self) -> None:
        """任意依存が未導入でも標準ライブラリだけで成立する言語は動く。"""
        assert languages.extractor_for("python") is not None


class TestGraphExtraction:
    def test_csharp_using_becomes_an_import(self) -> None:
        refs, imports = languages.graph_extractor_for("csharp")(
            "using System.Text;\npublic class A { void M() { Helper.Do(); } }\n"
        )
        assert (1, "System") in imports

    def test_csharp_call_sites_become_references(self) -> None:
        refs, _ = languages.graph_extractor_for("csharp")(
            "public class A\n{\n    void M()\n    {\n        Helper.Do();\n    }\n}\n"
        )
        assert (5, "Do") in refs

    def test_javascript_import_becomes_an_import(self) -> None:
        _, imports = languages.graph_extractor_for("javascript")(
            "import { helper } from './helper.js';\n"
        )
        assert (1, "./helper.js") in imports

    def test_javascript_call_sites_become_references(self) -> None:
        refs, _ = languages.graph_extractor_for("javascript")(
            "function a() {\n  return helper(1);\n}\n"
        )
        assert (2, "helper") in refs

    def test_declarations_are_not_counted_as_references(self) -> None:
        refs, _ = languages.graph_extractor_for("javascript")(
            "export function mountScreen(container) {\n  return container;\n}\n"
        )
        assert not any(name == "mountScreen" for _, name in refs)

    def test_graph_dispatch_covers_the_registry(self) -> None:
        from cq import graph

        for lang in ("python", "csharp", "javascript", "typescript"):
            refs, imports = graph.extract("function f(){ g(); }\n", lang)
            assert isinstance(refs, tuple) and isinstance(imports, tuple)

    def test_unknown_language_yields_nothing(self) -> None:
        from cq import graph

        assert graph.extract("echo hi\n", "nothing-registered") == ((), ())

    def test_python_syntax_error_still_yields_refs_via_tree_sitter(self) -> None:
        """Phase 5 (FR-CQ-11): `ast.parse` failing must not cost the graph rows
        outright when the optional tree-sitter-python grammar can recover them."""
        from cq import graph

        refs, imports = graph.extract(
            "import os\n\ndef broken(:\n    return os.getenv('X')\n", "python"
        )
        assert any(imp.line == 1 and imp.module == "os" for imp in imports)
        assert any(ref.name == "getenv" for ref in refs)

    def test_python_clean_source_still_uses_the_ast_path(self, monkeypatch) -> None:
        """The tree-sitter fallback must not run when `ast` already succeeded."""
        from cq import graph
        from cq.languages import python as python_lang

        calls = []
        monkeypatch.setattr(python_lang, "extract_graph", lambda source: calls.append(source))
        graph.extract("def f():\n    return g()\n", "python")
        assert calls == []

    def test_python_syntax_error_degrades_when_the_grammar_is_absent(self, monkeypatch) -> None:
        """The graph fallback must degrade like the symbol extractor, not raise
        (FR-CQ-11), when the optional tree-sitter-python grammar is unavailable."""
        from cq import graph
        from cq.languages import python as python_lang, treesitter as ts

        key = ts.cache_key(python_lang.GRAMMAR)
        monkeypatch.setitem(ts._PARSERS, key, ts.ExtractionError("simulated missing grammar"))
        assert graph.extract("def broken(:\n    return g()\n", "python") == ((), ())


class TestRealSources:
    def test_csharp_services_yield_symbols(self) -> None:
        target = REPO_ROOT / "src" / "api" / "SVC-03-reward-management-service" / "Domain" / "RewardManagementService.cs"
        symbols = {s.name for s in languages.extractor_for("csharp")(
            target.read_text(encoding="utf-8-sig")
        )}
        assert {"RewardManagementService", "EvaluateEligibility"} <= symbols

    def test_javascript_screens_yield_symbols(self) -> None:
        target = REPO_ROOT / "src" / "app" / "APP-009-S004" / "support-history-screen.js"
        symbols = {s.name for s in languages.extractor_for("javascript")(
            target.read_text(encoding="utf-8-sig")
        )}
        assert {"isResolvedCaseConsistent", "redactInvalidCaseIdentity"} <= symbols


class TestPhase2TreeSitterUpgrade:
    """FR-CQ-11 Phase 2: C# / JavaScript / TypeScript gain end_line, doc_head,
    references and structure chunks through tree-sitter, none of which the
    regex tier (still the fallback) ever produced."""

    CSHARP_DOC = """\
namespace Svc;

public sealed class RewardService
{
    /// <summary>Grants points to a member.</summary>
    public GrantResult Grant(
        GrantCommand command)
    {
        return Helper.Compute(command);
    }
}
"""

    JAVASCRIPT_DOC = """\
/**
 * Grants reward points.
 */
export class RewardService {
  grant(
    command
  ) {
    return helper.compute(command);
  }
}
"""

    TYPESCRIPT_DOC = """\
export interface Ledger {
  grant(id: string): boolean;
}

export class RewardService implements Ledger {
  /**
   * Grants points to a member.
   */
  grant(
    id: string
  ): boolean {
    return helper.compute(id);
  }
}
"""

    def test_csharp_multiline_signature_and_doc_are_recovered(self) -> None:
        from cq.languages import csharp

        symbols, parser = csharp.extract_ex(self.CSHARP_DOC)
        method = next(s for s in symbols if s.name == "Grant")
        assert parser == "tree-sitter"
        assert (method.start_line, method.end_line) == (6, 10)
        assert method.doc_head == "Grants points to a member."
        refs, _imports = csharp.extract_graph(self.CSHARP_DOC)
        assert any(name == "Compute" for _line, name in refs)
        assert csharp.chunk_spans(self.CSHARP_DOC, self.CSHARP_DOC.splitlines(), 40)

    def test_javascript_multiline_signature_and_doc_are_recovered(self) -> None:
        from cq.languages import javascript

        symbols, parser = javascript.extract_ex(self.JAVASCRIPT_DOC)
        method = next(s for s in symbols if s.name == "grant")
        assert parser == "tree-sitter"
        assert method.end_line > method.start_line
        refs, _imports = javascript.extract_graph(self.JAVASCRIPT_DOC)
        assert any(name == "compute" for _line, name in refs)
        assert javascript.chunk_spans(self.JAVASCRIPT_DOC, self.JAVASCRIPT_DOC.splitlines(), 40)

    def test_typescript_multiline_signature_and_doc_are_recovered(self) -> None:
        from cq.languages import typescript

        symbols, parser = typescript.extract_ex(self.TYPESCRIPT_DOC)
        by_qualname = {s.qualname: s for s in symbols}
        assert parser == "tree-sitter"
        assert by_qualname["Ledger.grant"].kind == "method"
        method = by_qualname["RewardService.grant"]
        assert method.end_line > method.start_line
        assert method.doc_head == "Grants points to a member."
        refs, _imports = typescript.extract_graph(self.TYPESCRIPT_DOC)
        assert any(name == "compute" for _line, name in refs)
        assert typescript.chunk_spans(self.TYPESCRIPT_DOC, self.TYPESCRIPT_DOC.splitlines(), 40)

    def test_tsx_suffix_resolves_to_its_own_language(self) -> None:
        assert languages.LANGUAGE_BY_SUFFIX[".tsx"] == "tsx"
        support = languages.support_for("tsx")
        assert support is not None and support.parser == "regex"

    def test_tsx_grammar_uses_the_tsx_factory(self) -> None:
        from cq.languages import typescript

        assert typescript.GRAMMAR.lang == "typescript"
        assert typescript.GRAMMAR.language_func == "language_typescript"
        assert typescript.TSX_GRAMMAR.lang == "tsx"
        assert typescript.TSX_GRAMMAR.language_func == "language_tsx"

    def test_tsx_extracts_symbols_through_its_own_grammar(self) -> None:
        from cq.languages import typescript

        source = "export function Widget(props: { id: string }) {\n  return null;\n}\n"
        symbols, parser = typescript.extract_ex_tsx(source)
        assert parser == "tree-sitter"
        assert {s.name for s in symbols} == {"Widget"}

    def test_javascript_falls_back_to_regex_when_the_grammar_is_absent(self, monkeypatch) -> None:
        """The regex tier can only match a method signature that fits on one
        line, so this uses a single-line fixture rather than `JAVASCRIPT_DOC`
        (whose whole point is exercising tree-sitter's multi-line recovery)."""
        from cq.languages import javascript, treesitter as ts

        monkeypatch.setitem(
            ts._PARSERS,
            ts.cache_key(javascript.GRAMMAR),
            languages.ExtractionError("simulated missing grammar"),
        )
        source = "class RewardService {\n  grant(command) {\n    return helper.compute(command);\n  }\n}\n"
        symbols, parser = javascript.extract_ex(source)
        assert parser == "regex"
        assert {s.name for s in symbols} == {"RewardService", "grant"}

    def test_typescript_falls_back_to_regex_when_the_grammar_is_absent(self, monkeypatch) -> None:
        from cq.languages import typescript, treesitter as ts

        monkeypatch.setitem(
            ts._PARSERS,
            ts.cache_key(typescript.GRAMMAR),
            languages.ExtractionError("simulated missing grammar"),
        )
        symbols, parser = typescript.extract_ex(self.TYPESCRIPT_DOC)
        assert parser == "regex"
        assert {s.name for s in symbols} >= {"Ledger", "RewardService"}
