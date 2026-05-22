"""Tests for .github/scripts/validate-skill-routing.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / ".github/scripts/validate-skill-routing.py"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _routing_md(*references: str) -> str:
    rows = "\n".join(
        f"| test | `{Path(ref).parent.name}` | `{ref}` | sample |" for ref in references
    )
    return (
        "---\n"
        "name: _routing\n"
        "description: test\n"
        "metadata:\n"
        "  version: 1.0.0\n"
        "---\n\n"
        "| フェーズ / トリガー | 参照 Skill | パス | 説明 |\n"
        "|---|---|---|---|\n"
        f"{rows}\n"
    )


def _skill_md(name: str, include_version: bool = True) -> str:
    version_block = "  version: 1.0.0\n" if include_version else ""
    return (
        "---\n"
        f"name: {name}\n"
        "description: test skill\n"
        "metadata:\n"
        f"{version_block}"
        "---\n\n"
        "# test\n"
    )


def _run_validator(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--root",
            str(tmp_path),
            *args,
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_missing_reference_detected(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/skills/_routing/SKILL.md",
        _routing_md(".github/skills/missing-skill/SKILL.md"),
    )

    result = _run_validator(tmp_path)

    assert result.returncode == 1
    assert "MISSING_REFERENCE" in result.stderr


def test_outside_root_reference_detected(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/skills/_routing/SKILL.md",
        _routing_md("../../../../external/skill/SKILL.md"),
    )

    result = _run_validator(tmp_path)

    assert result.returncode == 1
    assert "MISSING_REFERENCE" in result.stderr
    assert "リポジトリ外を参照" in result.stderr


def test_unreferenced_skill_warned(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/skills/_routing/SKILL.md",
        _routing_md(".github/skills/task-a/SKILL.md"),
    )
    _write(
        tmp_path / ".github/skills/task-a/SKILL.md",
        _skill_md("task-a"),
    )
    _write(
        tmp_path / ".github/skills/task-b/SKILL.md",
        _skill_md("task-b"),
    )

    result = _run_validator(tmp_path)

    assert result.returncode == 0
    assert "UNREFERENCED_SKILL" in result.stderr
    assert ".github/skills/task-b/SKILL.md" in result.stderr


def test_duplicate_skill_name_detected(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/skills/_routing/SKILL.md",
        _routing_md(
            ".github/skills/azure-skills/appinsights-instrumentation/SKILL.md",
            ".github/skills/observability/appinsights-instrumentation/SKILL.md",
        ),
    )
    _write(
        tmp_path / ".github/skills/azure-skills/appinsights-instrumentation/SKILL.md",
        _skill_md("appinsights-instrumentation"),
    )
    _write(
        tmp_path / ".github/skills/observability/appinsights-instrumentation/SKILL.md",
        _skill_md("appinsights-instrumentation"),
    )

    result = _run_validator(tmp_path)

    assert result.returncode == 1
    assert "DUPLICATE_SKILL_NAME" in result.stderr
    assert "appinsights-instrumentation" in result.stderr


def test_missing_frontmatter_version_detected(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github/skills/_routing/SKILL.md",
        _routing_md(".github/skills/karpathy-guidelines/SKILL.md"),
    )
    _write(
        tmp_path / ".github/skills/karpathy-guidelines/SKILL.md",
        _skill_md("karpathy-guidelines", include_version=False),
    )

    result = _run_validator(tmp_path)

    assert result.returncode == 1
    assert "MISSING_FRONTMATTER" in result.stderr
    assert "metadata.version" in result.stderr
