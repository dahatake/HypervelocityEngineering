"""FR-KIT-01: vendored code-query modules must track their upstream source.

`hve/tests/test_mdq_vendor_sync.py` の cq 版。配布キットはエンジン実体を同梱し
版管理下に置く必要があるため、`tools/skills/code_query/vendor/cq/` は
`.gitignore` の対象であってはならない。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_UPSTREAM = _REPO_ROOT / "cq"
_VENDOR = _REPO_ROOT / "tools" / "skills" / "code_query" / "vendor" / "cq"

# Tied to this repository, so sync-vendor keeps it out of the portable engine.
# ``tests`` is matched at **any** depth.
_EXCLUDED_DIR_NAMES = ("tests", "__pycache__")
_EXCLUDED_FILE_NAMES = ("golden-queries.json", "golden-queries-holdout.json")
_EXCLUDED_FROM_VENDOR = ("tests", *_EXCLUDED_FILE_NAMES)


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
    vendored = _VENDOR / name
    assert vendored.is_file(), (
        f"vendor/cq/{name} is missing; run sync-vendor in "
        "tools/skills/code_query/ to refresh the portable Skill"
    )
    assert vendored.read_bytes() == (_UPSTREAM / name).read_bytes(), (
        f"vendor/cq/{name} drifted from cq/{name}; fix the upstream file "
        "first, then re-run sync-vendor"
    )


def test_vendor_carries_no_file_beyond_upstream() -> None:
    extra = sorted(_relative_files(_VENDOR) - set(_distributed_paths()))
    assert not extra, f"vendor/cq ships files absent from cq/: {extra}"


@pytest.mark.parametrize("name", (*_EXCLUDED_FROM_VENDOR, "gui/tests"))
def test_vendor_excludes_repository_specific_material(name: str) -> None:
    assert not (_VENDOR / name).exists(), (
        f"vendor/cq/{name} must not ship: sync-vendor excludes it"
    )


def test_vendor_is_version_controlled() -> None:
    """FR-KIT-01: 同梱物は版管理下に置く（`.gitignore` 対象にしない）。"""
    probe = "tools/skills/code_query/vendor/cq/cli.py"
    result = subprocess.run(
        ["git", "check-ignore", "-v", probe],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        f"{probe} is git-ignored ({result.stdout.strip()}); "
        "the vendored engine must be committed so a copied kit works"
    )


def test_vendor_is_tracked_by_git() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--", "tools/skills/code_query/vendor/cq"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [line for line in result.stdout.splitlines() if line.strip()]
    assert tracked, "vendor/cq has no tracked file; commit the synced engine"


def test_upstream_stamp_is_not_regenerated() -> None:
    """時刻入りスタンプは毎回差分を生むため廃止する。"""
    assert not (_VENDOR.parent / "UPSTREAM.txt").exists()
