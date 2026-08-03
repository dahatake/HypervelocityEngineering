"""Reference and import extraction for the graph layer (FR-CQ-07)."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from cq import languages


@dataclass(frozen=True)
class Reference:
    line: int
    name: str


@dataclass(frozen=True)
class Import:
    line: int
    module: str


def extract(source: str, lang: str) -> tuple[tuple[Reference, ...], tuple[Import, ...]]:
    """Dispatch to the language module; unknown languages yield nothing."""
    if lang == "python":
        return extract_python(source)
    extractor = languages.graph_extractor_for(lang)
    if extractor is None:
        return (), ()
    raw_refs, raw_imports = extractor(source)
    refs = tuple(sorted(
        (Reference(line, name) for line, name in raw_refs),
        key=lambda r: (r.line, r.name),
    ))
    imports = tuple(sorted(
        (Import(line, module) for line, module in raw_imports),
        key=lambda i: (i.line, i.module),
    ))
    return refs, imports


def extract_python(source: str) -> tuple[tuple[Reference, ...], tuple[Import, ...]]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return (), ()

    refs: list[Reference] = []
    imports: list[Import] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                Import(node.lineno, alias.name.split(".")[0]) for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]
            if module:
                imports.append(Import(node.lineno, module))
        elif isinstance(node, ast.Call):
            name = _called_name(node.func)
            if name:
                refs.append(Reference(node.lineno, name))
    refs.sort(key=lambda r: (r.line, r.name))
    imports.sort(key=lambda i: (i.line, i.module))
    return tuple(refs), tuple(imports)


def _called_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
