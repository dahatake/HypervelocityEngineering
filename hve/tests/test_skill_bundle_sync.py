"""FR-KIT-02: Skill 定義の正本は 1 箇所で、配布キットのコピーは生成物とする。

根拠: hve-dev/requirement-definition.md §3.10 FR-KIT-02

RED（実装前）:
  - `tools/skills/code_query/skill-template/SKILL.md` が別文面で二重管理されている
  - 配布キットに `skill/` が存在しない
  - `code-query` の Skill 定義がリポジトリ固有記述を本体へ直書きしている
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# (canonical skill directory, distribution kit directory)
_BUNDLES = (
    (".github/skills/code-query", "tools/skills/code_query"),
    (".github/skills/markdown-query", "tools/skills/markdown_query"),
)

_REPO_SPECIFIC = "repo-specific"


def _distributed_files(canonical: Path) -> list[str]:
    return sorted(
        p.relative_to(canonical).as_posix()
        for p in canonical.rglob("*")
        if p.is_file() and _REPO_SPECIFIC not in p.relative_to(canonical).parts
    )


@pytest.mark.parametrize("canonical_rel,kit_rel", _BUNDLES)
class TestSkillBundleIsGeneratedFromTheCanonicalDefinition:
    def test_kit_ships_the_skill_definition(
        self, canonical_rel: str, kit_rel: str
    ) -> None:
        assert (_REPO_ROOT / kit_rel / "skill" / "SKILL.md").is_file()

    def test_every_distributed_file_matches_byte_for_byte(
        self, canonical_rel: str, kit_rel: str
    ) -> None:
        canonical = _REPO_ROOT / canonical_rel
        kit_skill = _REPO_ROOT / kit_rel / "skill"
        for name in _distributed_files(canonical):
            shipped = kit_skill / name
            assert shipped.is_file(), (
                f"{kit_rel}/skill/{name} is missing; run sync-vendor to "
                "regenerate the Skill definition"
            )
            assert shipped.read_bytes() == (canonical / name).read_bytes(), (
                f"{kit_rel}/skill/{name} drifted from {canonical_rel}/{name}; "
                "edit the canonical definition and re-run sync-vendor"
            )

    def test_kit_carries_no_file_beyond_the_canonical_definition(
        self, canonical_rel: str, kit_rel: str
    ) -> None:
        canonical = _REPO_ROOT / canonical_rel
        kit_skill = _REPO_ROOT / kit_rel / "skill"
        shipped = sorted(
            p.relative_to(kit_skill).as_posix()
            for p in kit_skill.rglob("*")
            if p.is_file()
        )
        assert shipped == _distributed_files(canonical)

    def test_repository_specific_material_is_not_shipped(
        self, canonical_rel: str, kit_rel: str
    ) -> None:
        kit_skill = _REPO_ROOT / kit_rel / "skill"
        offenders = [
            p.relative_to(kit_skill).as_posix()
            for p in kit_skill.rglob("*")
            if _REPO_SPECIFIC in p.relative_to(kit_skill).parts
        ]
        assert offenders == []

    def test_canonical_definition_isolates_repository_specific_material(
        self, canonical_rel: str, kit_rel: str
    ) -> None:
        canonical = _REPO_ROOT / canonical_rel
        assert (canonical / "references" / _REPO_SPECIFIC).is_dir()
        body = (canonical / "SKILL.md").read_text(encoding="utf-8")
        assert f"references/{_REPO_SPECIFIC}/" in body, (
            "SKILL.md must point at the isolated repository-specific appendix"
        )


class TestNoSecondSkillDefinition:
    def test_skill_template_is_removed(self) -> None:
        assert not (
            _REPO_ROOT / "tools" / "skills" / "code_query" / "skill-template"
        ).exists()

    @pytest.mark.parametrize("kit_rel", [rel for _, rel in _BUNDLES])
    def test_setup_scripts_do_not_reference_the_removed_template(
        self, kit_rel: str
    ) -> None:
        for script in ("setup.ps1", "setup.sh"):
            text = (_REPO_ROOT / kit_rel / script).read_text(encoding="utf-8")
            assert "skill-template" not in text

    def test_shared_setup_installs_from_the_generated_copy(self) -> None:
        """Skill 配置の判断は共有実装 1 箇所に置く（FR-KIT-03）。"""
        text = (
            _REPO_ROOT / "tools" / "skills" / "_kit" / "kit_setup.py"
        ).read_text(encoding="utf-8")
        assert 'kit_dir / "skill"' in text
        assert '".github" / "skills"' in text
