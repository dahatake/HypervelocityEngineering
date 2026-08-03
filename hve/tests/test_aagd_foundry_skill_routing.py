"""AAGDのFoundry固定Stepに対するrequired Skill routing契約。"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from hve.skill_resolver import (
    get_required_skills_for_step,
    load_skill_manifest,
    validate_skill_names,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _REPO_ROOT / "hve" / "skill_manifest.json"


def _write_external_foundry_skill(
    root: Path,
    *,
    directory_name: str = "microsoft-foundry",
    declared_name: str = "microsoft-foundry",
) -> None:
    skill_dir = root / directory_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {declared_name}\n---\n# Test Foundry skill\n",
        encoding="utf-8",
    )


def test_aagd_foundry_steps_require_meta_skill_only() -> None:
    load_skill_manifest.cache_clear()
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    aagd_required = manifest["required_skills"]["aagd"]

    for step_id in ("2.3", "3"):
        assert aagd_required[step_id] == ["microsoft-foundry"]
        required = get_required_skills_for_step("aagd", step_id)
        assert "microsoft-foundry" in required

    foundry_coordinates = {
        step_id
        for step_id, skills in aagd_required.items()
        if "microsoft-foundry" in skills
    }
    assert foundry_coordinates == {"2.3", "3"}


def test_aagd_non_foundry_steps_do_not_require_meta_skill() -> None:
    load_skill_manifest.cache_clear()
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))

    for step_id in ("1", "2.1", "2.2"):
        assert "microsoft-foundry" not in get_required_skills_for_step(
            "aagd", step_id
        )

    assert manifest["required_skills"]["aagd"] == {
        "2.3": ["microsoft-foundry"],
        "3": ["microsoft-foundry"],
    }


def test_aagd_manifest_keeps_foundry_meta_skill_out_of_optional_candidates() -> None:
    load_skill_manifest.cache_clear()
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["optional_skills"]["aagd"] == {
        "2.3": ["azure-ai", "entra-agent-id"],
        "3": ["azure-diagnostics"],
    }
    foundry_coordinates = {
        step_id
        for section_name in ("required_skills", "optional_skills")
        for step_id, skills in manifest[section_name].get("aagd", {}).items()
        if "microsoft-foundry" in skills
    }
    assert foundry_coordinates == {"2.3", "3"}


def test_aagd_foundry_required_skill_validates_from_exact_external_directory() -> None:
    load_skill_manifest.cache_clear()
    required = get_required_skills_for_step("aagd", "2.3")

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_external_foundry_skill(root)
        missing, _, _ = validate_skill_names(
            required,
            external_skills_root=root,
        )

    assert missing == []


def test_aagd_foundry_required_skill_is_missing_without_external_directory() -> None:
    load_skill_manifest.cache_clear()
    required = get_required_skills_for_step("aagd", "3")

    with TemporaryDirectory() as temp_dir:
        missing, _, _ = validate_skill_names(
            required,
            external_skills_root=Path(temp_dir),
        )

    assert missing == ["microsoft-foundry"]


def test_aagd_foundry_required_skill_rejects_similarly_named_external_directory() -> None:
    load_skill_manifest.cache_clear()
    required = get_required_skills_for_step("aagd", "3")

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_external_foundry_skill(
            root,
            directory_name="microsoft-foundry-copy",
        )
        missing, _, _ = validate_skill_names(
            required,
            external_skills_root=root,
        )

    assert missing == ["microsoft-foundry"]


def test_aagd_foundry_required_skill_rejects_mismatched_external_frontmatter() -> None:
    load_skill_manifest.cache_clear()
    required = get_required_skills_for_step("aagd", "3")

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_external_foundry_skill(root, declared_name="another-skill")
        missing, _, _ = validate_skill_names(
            required,
            external_skills_root=root,
        )

    assert missing == ["microsoft-foundry"]


@pytest.mark.parametrize(
    "skill_content",
    [
        "# Missing frontmatter\n",
        "---\ndescription: Missing name\n---\n# Missing name\n",
    ],
)
def test_aagd_foundry_required_skill_rejects_missing_external_name(
    skill_content: str,
) -> None:
    load_skill_manifest.cache_clear()
    required = get_required_skills_for_step("aagd", "3")

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        skill_dir = root / "microsoft-foundry"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")
        missing, _, _ = validate_skill_names(
            required,
            external_skills_root=root,
        )

    assert missing == ["microsoft-foundry"]
