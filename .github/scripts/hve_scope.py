"""Single machine decision for the HVE scope boundary.

The boundary itself is specified by `hve-dev/requirement-definition.md` §3.7
("対象境界"). FR-MAINT-05 requires every consumer to reuse this module instead of
re-declaring the tables, so that the HVE application and the artifacts HVE generates
(`src/`, `docs/`, ...) never blur together.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

IN_SCOPE_PREFIXES = (
    "hve/", "mdq/", "cq/", "hve-dev/", "template/", "tools/skills/markdown_query/",
    "tools/skills/code_query/",
    "tools/runner/", "users-guide/", "hve/tests/", "hve/gui/tests/", "mdq/tests/",
    ".github/instructions/", ".github/skills/", ".github/prompts/", ".github/io-contracts/",
    ".github/scripts/", ".github/ISSUE_TEMPLATE/", "tests/bats/",
)
IN_SCOPE_EXACT = {
    ".github/copilot-instructions.md", "pyproject.toml", "mdq.toml", "cq.toml", "hve.cmd", "hve.sh",
    ".vscode/tasks.json",
}
OUT_OF_SCOPE_PREFIXES = (
    "src/", "docs/", "docs-generated/", "knowledge/", "qa/", "original-docs/", "sample/",
    "work/", "tests/run/", "hve.egg-info/", "tools/hve-app-cash/",
)
OUT_OF_SCOPE_EXACT = {
    "tools/gen_app04_test_specs.py", "package.json", "jest.config.js", "babel.config.js",
    "playwright.config.js", "CHANGELOG.md",
}


class ScopeError(ValueError):
    """Raised when a path cannot be normalised into a repository-relative form."""


def normalise_relative(value: str) -> str:
    if not value or "\\" in value or value.startswith("/") or value.startswith("./") or "//" in value:
        raise ScopeError(f"invalid repository-relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ScopeError(f"invalid repository-relative path: {value!r}")
    return str(path)


def is_out_of_scope(path: str) -> bool:
    if path in OUT_OF_SCOPE_EXACT or path.startswith(OUT_OF_SCOPE_PREFIXES):
        return True
    return (
        path.startswith(".github/workflows/deploy-")
        or path.startswith(".github/workflows/azure-static-web-apps-")
        or bool(re.fullmatch(r"\.github/workflows/app[0-9].*\.ya?ml", path))
    )


def is_in_scope(path: str) -> bool:
    if is_out_of_scope(path):
        return False
    if path in IN_SCOPE_EXACT or path.startswith(IN_SCOPE_PREFIXES):
        return True
    return (
        path.startswith(".github/workflows/")
        or bool(re.fullmatch(r"tools/[^/]+\.py", path))
    )
