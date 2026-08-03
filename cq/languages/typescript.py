"""TypeScript symbol extraction without third-party parsers (FR-CQ-11).

Shares JavaScript's brace-aware scanner and adds the declarations that exist
only in TypeScript, plus method signatures carrying a return-type annotation.
"""

from __future__ import annotations

import re

from cq.languages import RawSymbol
from cq.languages import javascript

_INTERFACE_RE = re.compile(
    r"^\s*(?:export\s+)?(?:declare\s+)?interface\s+(?P<name>\w+)"
)
_TYPE_ALIAS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:declare\s+)?type\s+(?P<name>\w+)\s*(?:<[^>]*>)?\s*="
)
_ENUM_RE = re.compile(
    r"^\s*(?:export\s+)?(?:declare\s+)?(?:const\s+)?enum\s+(?P<name>\w+)"
)
_ABSTRACT_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?abstract\s+class\s+(?P<name>\w+)"
)
# A TypeScript method may carry a return type between `)` and `{`, and default
# parameter values put `=` inside the parameter list.
_ANNOTATED_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|readonly|static|abstract|async|override)\s+)*"
    r"(?:get\s+|set\s+)?(?P<name>[A-Za-z_#$][\w$]*)\s*(?:<[^>]*>)?\s*"
    r"\([^;]*\)\s*(?::\s*[^{;]+?)?\s*\{"
)
_SIGNATURE_RE = re.compile(
    r"^\s*(?:readonly\s+)?(?P<name>[A-Za-z_#$][\w$]*)\s*(?:<[^>]*>)?\s*"
    r"\([^;]*\)\s*:\s*[^{;]+;\s*$"
)

TS_RULES: tuple[javascript.Rule, ...] = (
    (_ABSTRACT_CLASS_RE, "class", True, False),
    (_INTERFACE_RE, "interface", True, False),
    (_ENUM_RE, "enum", True, False),
    (_TYPE_ALIAS_RE, "type", False, False),
    *javascript.JS_RULES,
    (_ANNOTATED_METHOD_RE, "method", False, True),
    (_SIGNATURE_RE, "method", False, True),
)


def extract(source: str) -> tuple[RawSymbol, ...]:
    return javascript.scan(source, TS_RULES)


def extract_graph(source: str):
    return javascript.extract_graph(source)
