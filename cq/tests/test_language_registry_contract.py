"""Plug-in surface contracts required before new languages can be added.

Covers FR-CQ-04 (fidelity recorded per file), FR-CQ-05 (structure chunks are a
line partition), FR-CQ-11 (one declaration site per language, degradation never
aborts the index) and NFR-CQ-01 (optional parsers are imported lazily).
"""

from __future__ import annotations

import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from cq import chunking, config, indexer, languages, store

REPO_ROOT = Path(__file__).resolve().parents[2]

CSHARP = """\
namespace Svc;

public sealed class LedgerService
{
    public void Reset() { }
}
"""


def _repo(tmp_path: Path, files: dict[str, str], roots: str = "pkg") -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        f"[profiles.test]\nroots = ['{roots}']\n", encoding="utf-8"
    )
    for rel, body in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return tmp_path


def _index(tmp_path: Path) -> Path:
    profile = config.resolve_profile(tmp_path, "test")
    db = tmp_path / ".cq" / "index-test.sqlite"
    indexer.build_index(tmp_path, profile, db_path=db)
    return db


class TestParserFidelity:
    """FR-CQ-04: the recorded fidelity must name the parser that actually ran."""

    def test_regex_extractor_is_not_reported_as_ast(self) -> None:
        _, parser = indexer._extract("csharp", CSHARP)
        assert parser == "regex"

    def test_python_extractor_is_reported_as_ast(self) -> None:
        _, parser = indexer._extract("python", "def a():\n    return 1\n")
        assert parser == "ast"

    def test_every_registered_language_declares_its_parser(self) -> None:
        for lang in set(languages.LANGUAGE_BY_SUFFIX.values()):
            support = languages.support_for(lang)
            assert support is not None, lang
            assert support.parser and support.parser != "lite"


class TestChunkerRegistration:
    """FR-CQ-05 / FR-CQ-11: the structure chunker is supplied by the language."""

    def test_python_registers_a_structure_chunker(self) -> None:
        support = languages.support_for("python")
        assert support is not None and support.chunk is not None

    def test_language_without_a_chunker_falls_back_to_windows(self) -> None:
        chunks = chunking.chunk_source(CSHARP, "csharp")
        assert chunks and all(chunk.name == "" for chunk in chunks)


class TestChunkInvariants:
    """FR-CQ-05: chunks partition the file's lines exactly once."""

    SOURCE = "import os\n\n\ndef a():\n    return os\n\n\nclass B:\n    def c(self):\n        return 1\n"

    def test_chunk_ranges_stay_inside_the_file(self) -> None:
        total = len(self.SOURCE.splitlines())
        for chunk in chunking.chunk_source(self.SOURCE, "python", max_chars=40):
            assert 1 <= chunk.start_line <= chunk.end_line <= total

    def test_core_normalises_overlapping_language_spans(self, monkeypatch) -> None:
        """A language module must not be able to emit overlapping line ranges."""
        source = "a = 1\nb = 2\nc = 3\nd = 4\n"

        def broken(_source: str, _lines: list[str], _max_chars: int):
            # Overlaps line 2, nests inside the first span and claims a line past
            # the end of the file.
            return (
                languages.ChunkSpan(1, 2, "first", ""),
                languages.ChunkSpan(1, 1, "nested", ""),
                languages.ChunkSpan(2, 99, "second", ""),
            )

        support = languages.LanguageSupport(parser="fake", extract=lambda s: (), chunk=broken)
        monkeypatch.setattr(languages, "_registry", lambda: {"fake": support})
        chunks = chunking.chunk_source(source, "fake", max_chars=8)
        covered = [n for c in chunks for n in range(c.start_line, c.end_line + 1)]
        assert covered == list(range(1, 5))


class TestChunkLinkage:
    """FR-CQ-04: chunks.symbol_id must reference a row in symbols."""

    def test_chunk_symbol_id_references_an_existing_symbol(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, {"pkg/a.py": "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"})
        db = _index(repo)
        with closing(store.open_store(db, create=False)) as conn:
            orphans = conn.execute(
                "SELECT COUNT(*) FROM chunks c"
                " WHERE c.symbol_id IS NOT NULL"
                " AND NOT EXISTS (SELECT 1 FROM symbols s WHERE s.symbol_id = c.symbol_id)"
            ).fetchone()[0]
            linked = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE symbol_id IS NOT NULL"
            ).fetchone()[0]
        assert orphans == 0
        assert linked > 0

    def test_same_start_line_owner_is_the_smallest_enclosing_symbol(self) -> None:
        symbols = (
            languages.RawSymbol("Outer", "Outer", "class", 1, 20, "", None),
            languages.RawSymbol("inner", "Outer.inner", "method", 1, 3, "", "Outer"),
        )
        assert symbols[indexer._chunk_owner(symbols, 1, 3)].qualname == "Outer.inner"
        assert symbols[indexer._chunk_owner(symbols, 1, 20)].qualname == "Outer"
        assert indexer._chunk_owner(symbols, 7, 9) is None


class TestDegradation:
    """FR-CQ-11: degradation is recorded and never aborts the index."""

    def test_parser_load_failure_is_normalised_to_extraction_error(self, monkeypatch) -> None:
        def unavailable(_source: str):
            raise ImportError("grammar package is not installed")

        support = languages.LanguageSupport(parser="tree-sitter", extract=unavailable)
        monkeypatch.setattr(languages, "_registry", lambda: {"csharp": support})
        symbols, parser = indexer._extract("csharp", CSHARP)
        assert parser == "lite"
        assert symbols

    def test_failed_language_does_not_abort_the_whole_index(self, tmp_path: Path, monkeypatch) -> None:
        def unavailable(_source: str):
            raise ImportError("grammar package is not installed")

        original = languages._registry()
        broken = dict(original)
        broken["csharp"] = languages.LanguageSupport(parser="tree-sitter", extract=unavailable)
        monkeypatch.setattr(languages, "_registry", lambda: broken)
        repo = _repo(tmp_path, {"pkg/a.py": "def a():\n    return 1\n", "pkg/b.cs": CSHARP})
        db = _index(repo)
        with closing(store.open_store(db, create=False)) as conn:
            parsers = dict(conn.execute("SELECT path, parser FROM files"))
        assert parsers == {"pkg/a.py": "ast", "pkg/b.cs": "lite"}


class TestPersistedSemantics:
    """A parser/chunker change must invalidate databases built by older code."""

    def test_index_semantics_version_is_recorded(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, {"pkg/a.py": "def a():\n    return 1\n"})
        db = _index(repo)
        with closing(store.open_store(db, create=False)) as conn:
            assert store.schema_version(conn) == store.SCHEMA_VERSION
        assert store.SCHEMA_VERSION >= 3

    def test_older_database_demands_a_rebuild(self, tmp_path: Path) -> None:
        db = tmp_path / "old.sqlite"
        with closing(store.open_store(db)) as conn:
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                (str(store.SCHEMA_VERSION - 1),),
            )
            conn.commit()
        with pytest.raises(store.StoreError, match="rebuild"):
            store.open_store(db, create=False)


class TestCoreIsLanguageAgnostic:
    """FR-CQ-11: a new language is one registry entry, not a core edit."""

    def test_registering_a_language_needs_no_core_edit(self, tmp_path: Path, monkeypatch) -> None:
        def extract(source: str):
            return tuple(
                languages.RawSymbol(
                    name=line.split()[1],
                    qualname=line.split()[1],
                    kind="function",
                    start_line=number,
                    end_line=number,
                    signature=line.strip(),
                )
                for number, line in enumerate(source.splitlines(), start=1)
                if line.startswith("fn ")
            )

        def chunk(_source: str, lines: list[str], _max_chars: int):
            return tuple(
                languages.ChunkSpan(number, number, "", "")
                for number in range(1, len(lines) + 1)
            )

        support = languages.LanguageSupport(parser="fake", extract=extract, chunk=chunk)
        monkeypatch.setitem(languages.LANGUAGE_BY_SUFFIX, ".fake", "fake")
        monkeypatch.setattr(languages, "_registry", lambda: {"fake": support})

        repo = _repo(tmp_path, {"pkg/a.fake": "fn alpha\nfn beta\n"})
        db = _index(repo)
        with closing(store.open_store(db, create=False)) as conn:
            names = [r[0] for r in conn.execute("SELECT name FROM symbols ORDER BY name")]
            parser = conn.execute("SELECT parser FROM files").fetchone()[0]
        assert names == ["alpha", "beta"]
        assert parser == "fake"


class TestContentBasedLanguage:
    """Some suffixes cannot be resolved without reading the file (`.h`)."""

    def test_unambiguous_suffix_resolves_without_reading(self) -> None:
        def explode() -> str:
            raise AssertionError("source must not be read for an unambiguous suffix")

        assert languages.resolve_language(".py", explode) == "python"

    def test_ambiguous_suffix_is_resolved_from_content(self, monkeypatch) -> None:
        monkeypatch.setattr(
            languages,
            "_disambiguators",
            lambda: {".x": lambda source: "alpha" if "alpha" in source else "beta"},
        )
        assert languages.resolve_language(".x", lambda: "alpha marker") == "alpha"
        assert languages.resolve_language(".x", lambda: "nothing here") == "beta"

    def test_discovery_uses_the_resolver(self, tmp_path: Path, monkeypatch) -> None:
        support = languages.LanguageSupport(parser="fake", extract=lambda s: ())
        monkeypatch.setitem(languages.LANGUAGE_BY_SUFFIX, ".x", "alpha")
        monkeypatch.setattr(
            languages,
            "_disambiguators",
            lambda: {".x": lambda source: "beta" if "beta" in source else "alpha"},
        )
        monkeypatch.setattr(
            languages, "_registry", lambda: {"alpha": support, "beta": support}
        )
        from cq import discovery

        repo = _repo(tmp_path, {"pkg/a.x": "beta marker\n"})
        profile = config.resolve_profile(repo, "test")
        found = discovery.iter_files(repo, profile)
        assert [f.lang for f in found] == ["beta"]


class TestLazyOptionalParsers:
    """NFR-CQ-01: optional parsers must not load when the CLI is imported."""

    def test_cli_import_does_not_load_optional_grammars(self) -> None:
        code = (
            "import sys; import cq.search; import cq.__main__;"
            " print([m for m in sys.modules if m.startswith('tree_sitter')])"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "[]"

    def test_cli_import_does_not_load_the_sql_engines(self) -> None:
        code = (
            "import sys; import cq.search; import cq.__main__;"
            " print([m for m in sys.modules if m.split('.')[0] in ('sqlglot', 'sqlfluff')])"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "[]"


NEW_LANGUAGE_SOURCES = {
    "pkg/deploy.sh": "deploy_app() {\n  az group create --name rg\n}\n\ndeploy_app\n",
    "pkg/deploy.ps1": "function Get-Royalty {\n    Write-Host 'a'\n}\n\nGet-Royalty\n",
    "pkg/deploy.cmd": "@echo off\n:deploy\necho hi\ncall :deploy\n",
    "pkg/Job.scala": "package etl\n\nobject Job {\n  def run(): Unit = println(\"go\")\n}\n",
    "pkg/schema.sql": "CREATE TABLE dbo.member (id BIGINT);\n\nCREATE VIEW dbo.v AS SELECT id FROM dbo.member;\n",
}

NEW_LANGUAGE_PARSERS = {
    "pkg/deploy.sh": "tree-sitter",
    "pkg/deploy.ps1": "tree-sitter",
    "pkg/deploy.cmd": "tree-sitter",
    "pkg/Job.scala": "tree-sitter",
    "pkg/schema.sql": "sql",
}


@pytest.fixture(scope="module")
def new_language_db(tmp_path_factory) -> Path:
    repo = _repo(tmp_path_factory.mktemp("new-langs"), NEW_LANGUAGE_SOURCES)
    return _index(repo)


class TestNewLanguageIndexIntegration:
    """`.scala` と `.sql` はこのリポジトリに実ファイルが無く、`.cmd` は従来まったく
    索引対象外だったため、`build_index` 経路を temp corpus で押さえる。"""

    def test_every_new_suffix_records_its_fidelity(self, new_language_db: Path) -> None:
        with closing(store.open_store(new_language_db, create=False)) as conn:
            rows = dict(conn.execute("SELECT path, parser FROM files").fetchall())
        assert rows == NEW_LANGUAGE_PARSERS

    @pytest.mark.parametrize("path", sorted(NEW_LANGUAGE_SOURCES))
    def test_symbols_and_chunks_are_persisted(self, new_language_db: Path, path: str) -> None:
        with closing(store.open_store(new_language_db, create=False)) as conn:
            symbols = conn.execute(
                "SELECT COUNT(*) FROM symbols WHERE path = ?", (path,)
            ).fetchone()[0]
            chunks = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE path = ?", (path,)
            ).fetchone()[0]
        assert symbols > 0 and chunks > 0

    @pytest.mark.parametrize("path", sorted(NEW_LANGUAGE_SOURCES))
    def test_references_are_persisted(self, new_language_db: Path, path: str) -> None:
        with closing(store.open_store(new_language_db, create=False)) as conn:
            refs = conn.execute(
                "SELECT COUNT(*) FROM refs WHERE path = ?", (path,)
            ).fetchone()[0]
        assert refs > 0
