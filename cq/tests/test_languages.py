"""Contracts for the language registry and parser degradation (FR-CQ-11)."""

from __future__ import annotations

import ast
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from cq import config, discovery, indexer, languages, store

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

    def test_fidelity_is_reported_per_file(self, tmp_path: Path) -> None:
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
