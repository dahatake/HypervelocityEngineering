"""Python symbol extraction via the standard library `ast` (FR-CQ-04).

No third-party parser is involved, so the HVE application itself — 644 tracked
Python files — is always indexable at full fidelity.
"""

from __future__ import annotations

import ast

from cq.languages import ChunkSpan, ExtractionError, RawSymbol

_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def extract(source: str) -> tuple[RawSymbol, ...]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ExtractionError(f"cannot parse python source: {exc}") from exc

    found: list[RawSymbol] = []
    _walk(tree.body, parent=None, in_class=False, inherited_test=False, out=found)
    found.sort(key=lambda s: (s.start_line, s.qualname))
    return tuple(found)


def _walk(
    body: list[ast.stmt],
    *,
    parent: str | None,
    in_class: bool,
    inherited_test: bool,
    out: list[RawSymbol],
) -> None:
    for node in body:
        if not isinstance(node, _DEF_NODES):
            continue
        qualname = f"{parent}.{node.name}" if parent else node.name
        is_class = isinstance(node, ast.ClassDef)
        is_test = inherited_test or _looks_like_test(node.name)
        out.append(RawSymbol(
            name=node.name,
            qualname=qualname,
            kind="class" if is_class else ("method" if in_class else "function"),
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
            signature=_signature(node),
            parent=parent,
            doc_head=_doc_head(node),
            decorators=tuple(_decorator_name(d) for d in node.decorator_list),
            is_test=is_test,
        ))
        _walk(
            node.body,
            parent=qualname,
            in_class=is_class,
            inherited_test=is_test,
            out=out,
        )


def _looks_like_test(name: str) -> bool:
    return name.startswith("test_") or name.startswith("Test")


def _signature(node: ast.stmt) -> str:
    if isinstance(node, ast.ClassDef):
        bases = [ast.unparse(b) for b in node.bases]
        bases += [f"{kw.arg}={ast.unparse(kw.value)}" for kw in node.keywords if kw.arg]
        return f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({ast.unparse(node.args)}){returns}"


def _doc_head(node: ast.stmt) -> str | None:
    doc = ast.get_docstring(node)
    if not doc:
        return None
    head = doc.strip().splitlines()[0].strip()
    return head or None


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    try:
        return ast.unparse(node)
    except Exception:
        return "<unparsable>"


def chunk_spans(source: str, lines: list[str], max_chars: int) -> tuple[ChunkSpan, ...]:
    """Structural chunk boundaries for Python (FR-CQ-05).

    Definitions are the unit; a definition larger than ``max_chars`` is split
    into its own header plus its body statements.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ExtractionError(f"cannot parse python source: {exc}") from exc
    return tuple(
        _spans(tree.body, lines, max_chars, start_line=1, end_line=len(lines))
    )


def _spans(
    body: list[ast.stmt], lines: list[str], max_chars: int, *, start_line: int, end_line: int
) -> list[ChunkSpan]:
    """Cover ``start_line..end_line`` exactly once, splitting oversized definitions."""
    spans: list[ChunkSpan] = []
    cursor = start_line
    for node in body:
        start = getattr(node, "lineno", cursor)
        end = getattr(node, "end_lineno", start) or start
        decorators = getattr(node, "decorator_list", [])
        if decorators:
            start = min(start, min(d.lineno for d in decorators))
        if start > cursor:
            spans.append(ChunkSpan(cursor, start - 1))
        if isinstance(node, _DEF_NODES):
            spans.extend(_split_definition(node, start, end, lines, max_chars))
        else:
            spans.append(ChunkSpan(start, end))
        cursor = end + 1
    if cursor <= end_line:
        spans.append(ChunkSpan(cursor, end_line))
    return spans


def _split_definition(
    node: ast.stmt, start: int, end: int, lines: list[str], max_chars: int
) -> list[ChunkSpan]:
    name = node.name
    signature = lines[start - 1].strip() if 0 < start <= len(lines) else ""
    size = sum(len(lines[i]) + 1 for i in range(start - 1, min(end, len(lines))))
    if size <= max_chars or not getattr(node, "body", None):
        return [ChunkSpan(start, end, name, signature)]
    header_end = max(start, min(node.body[0].lineno - 1, end))
    spans = [ChunkSpan(start, header_end, name, signature)]
    spans.extend(_spans(node.body, lines, max_chars, start_line=header_end + 1, end_line=end))
    return spans
