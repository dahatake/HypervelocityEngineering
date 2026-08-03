"""JavaScript symbol extraction without third-party parsers (FR-CQ-11).

Brace-aware so that methods are attributed to their enclosing class rather than
reported as free functions. TypeScript reuses :func:`scan` with its own pattern
table (see :mod:`cq.languages.typescript`).
"""

from __future__ import annotations

import re

from cq.languages import RawSymbol
from cq.languages.linescan import brace_delta

_CLASS_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+(?P<name>\w+)")
_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(?P<name>\w+)\s*\("
)
_ASSIGNED_FN_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*"
    r"(?:async\s*)?(?:function\s*\*?\s*\w*\s*\(|\([^)]*\)\s*=>|\w+\s*=>)"
)
_METHOD_RE = re.compile(
    r"^\s*(?:static\s+)?(?:async\s+)?(?:get\s+|set\s+)?(?P<name>[A-Za-z_#$][\w$]*)\s*\([^;=]*\)\s*\{"
)
_CONTROL_KEYWORDS = frozenset({
    "if", "for", "while", "switch", "catch", "return", "function", "class",
    "do", "else", "try", "finally", "with", "constructor",
})

# (pattern, kind, opens a scope, requires an enclosing scope)
Rule = tuple[re.Pattern, str, bool, bool]

JS_RULES: tuple[Rule, ...] = (
    (_CLASS_RE, "class", True, False),
    (_FUNCTION_RE, "function", False, False),
    (_ASSIGNED_FN_RE, "function", False, False),
    (_METHOD_RE, "method", False, True),
)


def extract(source: str) -> tuple[RawSymbol, ...]:
    return scan(source, JS_RULES)


def scan(source: str, rules: tuple[Rule, ...]) -> tuple[RawSymbol, ...]:
    lines = source.splitlines()
    found: list[RawSymbol] = []
    scope_stack: list[list] = []  # (qualname, 宣言時の深さ, 本体を見たか)
    depth = 0

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith(("//", "*", "/*")):
            parent = scope_stack[-1][0] if scope_stack else None
            symbol, opens_scope = _match_symbol(line, index + 1, parent, rules)
            if symbol is not None:
                found.append(symbol)
                if opens_scope:
                    scope_stack.append([symbol.qualname, depth, False])

        depth += brace_delta(line)
        for entry in scope_stack:
            if not entry[2] and depth > entry[1]:
                entry[2] = True
        while scope_stack and scope_stack[-1][2] and depth <= scope_stack[-1][1]:
            scope_stack.pop()

    found.sort(key=lambda s: (s.start_line, s.qualname))
    return tuple(found)


def _match_symbol(
    line: str, number: int, parent: str | None, rules: tuple[Rule, ...]
) -> tuple[RawSymbol | None, bool]:
    for pattern, kind, opens_scope, needs_parent in rules:
        if needs_parent and parent is None:
            continue
        match = pattern.match(line)
        if match and match.group("name") not in _CONTROL_KEYWORDS:
            return _make(match.group("name"), parent, kind, number, line), opens_scope
    return None, False


def _make(name: str, parent: str | None, kind: str, number: int, line: str) -> RawSymbol:
    qualname = f"{parent}.{name}" if parent else name
    return RawSymbol(
        name=name,
        qualname=qualname,
        kind=kind,
        start_line=number,
        end_line=number,
        signature=line.strip().rstrip("{").strip()[:300],
        parent=parent,
        is_test=name.startswith("test") or name.startswith("Test"),
    )


_IMPORT_RE = re.compile(r"""^\s*(?:import\b[^'"]*from\s*|import\s*|.*\brequire\s*\()['"](?P<module>[^'"]+)['"]""")
_CALL_RE = re.compile(r"(?<![\w$])(?P<name>[A-Za-z_$][\w$]*)\s*\(")
_DECL_KEYWORDS = _CONTROL_KEYWORDS | {"new", "typeof", "await", "throw", "import", "require"}


def extract_graph(source: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return ``(references, imports)`` as ``(line, name)`` pairs."""
    declaration_lines = {s.start_line for s in extract(source)}
    refs: list[tuple[int, str]] = []
    imports: list[tuple[int, str]] = []
    for number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "*", "/*")):
            continue
        module = _IMPORT_RE.match(line)
        if module:
            imports.append((number, module.group("module")))
            continue
        if number in declaration_lines:
            continue
        for match in _CALL_RE.finditer(line):
            name = match.group("name")
            if name not in _DECL_KEYWORDS:
                refs.append((number, name))
    return refs, imports
