"""Vendored markdown-query modules that must track their upstream source."""
from __future__ import annotations

from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_UPSTREAM = _REPO_ROOT / "mdq"
_VENDOR = _REPO_ROOT / "tools" / "skills" / "markdown_query" / "vendor" / "mdq"

# Tied to this repository, so sync-vendor keeps it out of the portable engine.
# Directory names are matched at **any** depth: the GUI package under
# ``mdq/gui/`` carries its own test package, and generated caches must not ship.
_EXCLUDED_DIR_NAMES = ("tests", "__pycache__", ".mypy_cache", ".pytest_cache")
_EXCLUDED_FILE_NAMES = ("golden-queries.json", "golden-queries-holdout.json")
_EXCLUDED_FROM_VENDOR = ("tests", ".mypy_cache", *_EXCLUDED_FILE_NAMES)


def _is_distributed(relative: Path) -> bool:
    parts = relative.parts
    if any(name in parts for name in _EXCLUDED_DIR_NAMES):
        return False
    return relative.as_posix() not in _EXCLUDED_FILE_NAMES


def _relative_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and _is_distributed(path.relative_to(root))
    }


def _distributed_paths() -> list[str]:
    paths = sorted(_relative_files(_UPSTREAM))
    if not paths:
        raise RuntimeError(f"no distributable file found under {_UPSTREAM}")
    return paths


@pytest.mark.parametrize("name", _distributed_paths())
def test_vendored_file_matches_upstream_byte_for_byte(name: str) -> None:
    """配布複製を上流から分岐させない（FR-MDQ-01 / FR-CQ-12 の判定実装を含む）。"""
    vendored = _VENDOR / name
    assert vendored.is_file(), (
        f"vendor/mdq/{name} is missing; run sync-vendor in "
        "tools/skills/markdown_query/ to refresh the portable Skill"
    )
    assert vendored.read_bytes() == (_UPSTREAM / name).read_bytes(), (
        f"vendor/mdq/{name} drifted from mdq/{name}; fix the upstream file "
        "first, then re-run sync-vendor"
    )


def test_vendor_carries_no_file_beyond_upstream() -> None:
    extra = sorted(_relative_files(_VENDOR) - set(_distributed_paths()))
    assert not extra, f"vendor/mdq ships files absent from mdq/: {extra}"


@pytest.mark.parametrize(
    "name", (*_EXCLUDED_FROM_VENDOR, "gui/tests")
)
def test_vendor_excludes_repository_specific_material(name: str) -> None:
    assert not (_VENDOR / name).exists(), (
        f"vendor/mdq/{name} must not ship: sync-vendor excludes it"
    )
