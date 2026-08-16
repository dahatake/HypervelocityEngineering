"""Single machine decision for the HVE scope boundary.

The boundary itself is specified by `hve-dev/requirement-definition.md` §3.7
("対象境界"). FR-MAINT-05 requires every consumer to reuse this module instead of
re-declaring the tables, so that the HVE application and the artifacts HVE generates
(`src/`, `docs/`, ...) never blur together.

The same §3.7 also specifies "版管理境界" (FR-MAINT-08): the paths whose change
requires bumping the HVE package version are a strict subset of the scope boundary,
decided by `requires_version_bump` below.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

IN_SCOPE_PREFIXES = (
    "hve/", "mdq/", "cq/", "hve-dev/", "template/", "tools/skills/markdown_query/",
    "tools/skills/code_query/",
    "tools/runner/", "hve/tests/", "hve/gui/tests/", "mdq/tests/",
    ".github/instructions/", ".github/skills/", ".github/prompts/", ".github/io-contracts/",
    ".github/scripts/", ".github/ISSUE_TEMPLATE/", "tests/bats/",
)
IN_SCOPE_EXACT = {
    ".github/copilot-instructions.md", "pyproject.toml", "mdq.toml", "cq.toml", "hve.cmd", "hve.sh",
    ".vscode/tasks.json",
}
OUT_OF_SCOPE_PREFIXES = (
    "src/", "docs/", "docs-generated/", "knowledge/", "qa/", "docs-original/",
    "sample/",
    "users-guide/",
    "work/", "tests/run/", "hve.egg-info/", "tools/hve-app-cash/",
)
OUT_OF_SCOPE_EXACT = {
    "package.json", "jest.config.js", "babel.config.js",
    "playwright.config.js", "CHANGELOG.md",
}

# Excluding the sync targets is what makes the rule satisfiable: `pyproject.toml` and
# `hve/__init__.py` are in scope, so a bump would otherwise demand a further bump.
# Kept in sync with `[tool.bumpversion]` in pyproject.toml.
VERSION_BUMP_FILES = frozenset({"pyproject.toml", "hve/__init__.py", "CHANGELOG.md"})
# Versioned independently per `hve-dev/hve-app-tools.md` §7.
INDEPENDENT_VERSION_PREFIXES = (
    "mdq/", "cq/", "tools/skills/markdown_query/", "tools/skills/code_query/",
)


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


def requires_version_bump(path: str) -> bool:
    """Whether changing `path` requires bumping the HVE package version (FR-MAINT-08)."""
    if not is_in_scope(path):
        return False
    return path not in VERSION_BUMP_FILES and not path.startswith(INDEPENDENT_VERSION_PREFIXES)
