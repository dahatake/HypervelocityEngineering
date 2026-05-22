"""Stand-alone contextualizer module.

Per Q11=B: the default-on contextualizer prepends a fixed template
``[Context] {path} > {heading_path}`` to each chunk body. No LLM call is
made; the implementation is pure-Python and dependency-free.

The :mod:`mdq.strategies_semantic` module already inlines this template
for performance (avoids one import per chunk). This module exposes the
same logic for *external* callers (tests, future contextualizer variants,
documentation snippets) and serves as a single source of truth for the
template format.
"""
from __future__ import annotations

TEMPLATE: str = "[Context] {path} > {heading_path}\n\n{body}"


def contextualize(path: str, heading_path: str, body: str) -> str:
    """Return *body* with the contextualizer template prepended.

    *heading_path* defaults to ``(top)`` when empty so the rendered line is
    always informative.
    """
    return TEMPLATE.format(
        path=path,
        heading_path=heading_path or "(top)",
        body=body,
    )


__all__ = ["TEMPLATE", "contextualize"]
