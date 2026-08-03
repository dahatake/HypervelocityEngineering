"""Language plug-in contract for cq (FR-CQ-04 / FR-CQ-11).

Adding a language means adding one module here plus one entry in
:func:`_registry`; the store, indexer and search layers stay untouched. A
:class:`LanguageSupport` carries everything the core needs: the fidelity name to
record per file, the symbol extractor, the optional structure chunker and the
optional reference extractor.

Languages without a dedicated module fall back to :mod:`cq.languages.lite`, and
any extractor that raises :class:`ExtractionError` degrades the same way. The
degradation is recorded per file so that callers can see the reduced fidelity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class ExtractionError(ValueError):
    """Raised when a source file cannot be parsed at full fidelity."""


@dataclass(frozen=True)
class RawSymbol:
    name: str
    qualname: str
    kind: str
    start_line: int
    end_line: int
    signature: str
    parent: str | None = None
    doc_head: str | None = None
    decorators: tuple[str, ...] = ()
    is_test: bool = False


@dataclass(frozen=True)
class ChunkSpan:
    """A structural region proposed by a language module (FR-CQ-05).

    Spans are advisory: the core clamps them to the file and removes overlaps so
    that chunks always partition the lines.
    """

    start: int
    end: int
    name: str = ""
    signature: str = ""


@dataclass(frozen=True)
class LanguageSupport:
    parser: str
    extract: Callable[[str], tuple[RawSymbol, ...]]
    chunk: Callable[[str, list[str], int], tuple[ChunkSpan, ...]] | None = None
    graph: Callable[[str], tuple] | None = None


# 拡張子 → 言語。`.md` と CSV / TSV は mdq の担当（FR-CQ-01）なので載せてはならない。
LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".cs": "csharp",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".sh": "shell",
    ".bash": "shell",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".cmd": "batch",
    ".bat": "batch",
    ".scala": "scala",
    ".sql": "sql",
}


def _registry() -> dict[str, LanguageSupport]:
    from cq.languages import (
        batch,
        cfamily,
        csharp,
        go,
        java,
        javascript,
        powershell,
        python,
        rust,
        scala,
        shell,
        sql,
        typescript,
    )

    return {
        "python": LanguageSupport(
            parser="ast",
            extract=python.extract,
            chunk=python.chunk_spans,
        ),
        "csharp": LanguageSupport(
            parser="regex",
            extract=csharp.extract,
            graph=csharp.extract_graph,
        ),
        "javascript": LanguageSupport(
            parser="regex",
            extract=javascript.extract,
            graph=javascript.extract_graph,
        ),
        "typescript": LanguageSupport(
            parser="regex",
            extract=typescript.extract,
            graph=typescript.extract_graph,
        ),
        "java": LanguageSupport(
            parser="tree-sitter",
            extract=java.extract,
            chunk=java.chunk_spans,
            graph=java.extract_graph,
        ),
        "go": LanguageSupport(
            parser="tree-sitter",
            extract=go.extract,
            chunk=go.chunk_spans,
            graph=go.extract_graph,
        ),
        "rust": LanguageSupport(
            parser="tree-sitter",
            extract=rust.extract,
            chunk=rust.chunk_spans,
            graph=rust.extract_graph,
        ),
        "c": LanguageSupport(
            parser="tree-sitter",
            extract=cfamily.extract_c,
            chunk=cfamily.chunk_spans_c,
            graph=cfamily.extract_graph_c,
        ),
        "cpp": LanguageSupport(
            parser="tree-sitter",
            extract=cfamily.extract_cpp,
            chunk=cfamily.chunk_spans_cpp,
            graph=cfamily.extract_graph_cpp,
        ),
        "shell": LanguageSupport(
            parser="tree-sitter",
            extract=shell.extract,
            chunk=shell.chunk_spans,
            graph=shell.extract_graph,
        ),
        "powershell": LanguageSupport(
            parser="tree-sitter",
            extract=powershell.extract,
            chunk=powershell.chunk_spans,
            graph=powershell.extract_graph,
        ),
        "batch": LanguageSupport(
            parser="tree-sitter",
            extract=batch.extract,
            chunk=batch.chunk_spans,
            graph=batch.extract_graph,
        ),
        "scala": LanguageSupport(
            parser="tree-sitter",
            extract=scala.extract,
            chunk=scala.chunk_spans,
            graph=scala.extract_graph,
        ),
        # sqlglot 主、本体を構造化できないときだけ sqlfluff。どちらが走ったかで
        # フィデリティは変わらないので、`tree-sitter` と同じ粒度で `sql` と記録する。
        "sql": LanguageSupport(
            parser="sql",
            extract=sql.extract,
            chunk=sql.chunk_spans,
            graph=sql.extract_graph,
        ),
    }


def _disambiguators() -> dict[str, Callable[[str], str]]:
    """Suffixes whose language can only be decided by reading the file."""
    from cq.languages import cfamily

    return {".h": cfamily.language_for_header}


def support_for(lang: str) -> LanguageSupport | None:
    """Return the registry entry for ``lang``, or ``None`` when absent."""
    return _registry().get(lang)


def indexable_suffixes() -> frozenset[str]:
    """Suffixes cq may index, including the ones resolved by content."""
    return frozenset(LANGUAGE_BY_SUFFIX) | frozenset(_disambiguators())


def resolve_language(suffix: str, read_source: Callable[[], str]) -> str | None:
    """Language for ``suffix``. ``read_source`` runs only for ambiguous suffixes."""
    decide = _disambiguators().get(suffix)
    if decide is not None:
        return decide(read_source())
    return LANGUAGE_BY_SUFFIX.get(suffix)


def extractor_for(lang: str):
    """Return the dedicated extractor for ``lang``, or ``None`` when absent."""
    support = support_for(lang)
    return support.extract if support else None


def graph_extractor_for(lang: str):
    """Return the reference / import extractor for ``lang``, or ``None``."""
    support = support_for(lang)
    return support.graph if support else None
