"""C# symbol extraction without third-party parsers (FR-CQ-11).

`tree-sitter-language-pack` was evaluated and rejected: it downloads grammars
over the network on first use, which breaks the local-only guarantee this Skill
inherits from `markdown-query` and fails closed in offline agent environments.

This extractor is brace-aware rather than line-based, so multi-line signatures
and nested types resolve correctly.
"""

from __future__ import annotations

import re

from cq.languages import RawSymbol
from cq.languages.linescan import brace_delta

_TYPE_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*"
    r"(?:(?:public|private|protected|internal|static|sealed|abstract|partial|readonly|new)\s+)*"
    r"(?P<kw>class|record|struct|interface|enum)\s+(?P<name>\w+)"
)
_METHOD_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*"
    r"(?:(?:public|private|protected|internal|static|async|override|virtual|sealed|"
    r"abstract|extern|partial|new|unsafe)\s+)+"
    r"(?P<ret>[\w<>,\[\]\?\.\s]+?)\s+(?P<name>\w+)\s*\("
)
_CTOR_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static)\s+)+(?P<name>\w+)\s*\([^;]*\)\s*(?:\{|:|$)"
)
_DOC_RE = re.compile(r"^\s*///\s*(?:<summary>)?\s*(?P<text>[^<]+)")
_CONTROL_KEYWORDS = frozenset({"if", "for", "foreach", "while", "switch", "catch",
                               "using", "lock", "fixed", "return", "yield", "get", "set"})

# `record` has no kind of its own in the shared vocabulary, so it stays a class.
_KIND_BY_KEYWORD = {
    "class": "class",
    "record": "class",
    "struct": "struct",
    "interface": "interface",
    "enum": "enum",
}
_TYPE_KINDS = frozenset(_KIND_BY_KEYWORD.values())


def extract(source: str) -> tuple[RawSymbol, ...]:
    lines = source.splitlines()
    found: list[RawSymbol] = []
    # (qualname, 宣言時の深さ, 本体の `{` を見たか)
    type_stack: list[list] = []
    depth = 0
    pending_doc: str | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        doc = _DOC_RE.match(line)
        if doc:
            pending_doc = doc.group("text").strip() or pending_doc
        elif stripped and not stripped.startswith("//"):
            parent = type_stack[-1][0] if type_stack else None
            symbol = _match_symbol(line, index + 1, parent, pending_doc)
            if symbol is not None:
                found.append(symbol)
                if symbol.kind in _TYPE_KINDS:
                    type_stack.append([symbol.qualname, depth, False])
            pending_doc = None

        depth += brace_delta(line)
        # 宣言行の次に `{` が来る書き方があるため、本体を見るまで pop しない。
        for entry in type_stack:
            if not entry[2] and depth > entry[1]:
                entry[2] = True
        while type_stack and type_stack[-1][2] and depth <= type_stack[-1][1]:
            type_stack.pop()

    found.sort(key=lambda s: (s.start_line, s.qualname))
    return tuple(found)


def _match_symbol(
    line: str, number: int, parent: str | None, doc: str | None
) -> RawSymbol | None:
    type_match = _TYPE_RE.match(line)
    if type_match:
        kind = _KIND_BY_KEYWORD[type_match.group("kw")]
        return _make(type_match.group("name"), parent, kind, number, line, doc)

    method = _METHOD_RE.match(line)
    if method and method.group("name") not in _CONTROL_KEYWORDS:
        return _make(method.group("name"), parent, _kind(parent), number, line, doc)

    ctor = _CTOR_RE.match(line)
    if ctor and parent and ctor.group("name") == parent.rpartition(".")[2]:
        return _make(ctor.group("name"), parent, "method", number, line, doc)
    return None


def _kind(parent: str | None) -> str:
    return "method" if parent else "function"


def _make(
    name: str, parent: str | None, kind: str, number: int, line: str, doc: str | None
) -> RawSymbol:
    qualname = f"{parent}.{name}" if parent else name
    return RawSymbol(
        name=name,
        qualname=qualname,
        kind=kind,
        start_line=number,
        end_line=number,
        signature=line.strip().rstrip("{").strip()[:300],
        parent=parent,
        doc_head=doc,
        is_test=name.startswith("Test") or name.endswith("Tests"),
    )


_USING_RE = re.compile(r"^\s*using\s+(?:static\s+)?(?P<module>[\w.]+)\s*;")
_CALL_RE = re.compile(r"(?<![\w])(?P<name>[A-Za-z_]\w*)\s*\(")
_DECL_KEYWORDS = _CONTROL_KEYWORDS | {"new", "typeof", "nameof", "sizeof", "await", "throw"}


def extract_graph(source: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return ``(references, imports)`` as ``(line, name)`` pairs."""
    declaration_lines = {s.start_line for s in extract(source)}
    refs: list[tuple[int, str]] = []
    imports: list[tuple[int, str]] = []
    for number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "///", "*", "/*")):
            continue
        using = _USING_RE.match(line)
        if using:
            imports.append((number, using.group("module").split(".")[0]))
            continue
        if number in declaration_lines:
            continue
        for match in _CALL_RE.finditer(line):
            name = match.group("name")
            if name not in _DECL_KEYWORDS:
                refs.append((number, name))
    return refs, imports
