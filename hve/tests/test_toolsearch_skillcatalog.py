"""FR-TS-06: Skill をツールカタログへ合流させることのテスト。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.toolsearch.policy import ToolSearchPolicy
from hve.toolsearch.skill_catalog import (
    MAX_SKILL_BODY_CHARS,
    SkillDescriptor,
    build_skill_entries,
    build_skill_tools,
    discover_skills,
    parse_skill_file,
    read_skill_body,
    skill_manifest_pins,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPO_SKILLS = _REPO_ROOT / ".github" / "skills"

_FRONTMATTER_BLOCK = """---
name: sample-skill
description: >
  ブロック形式の説明。 USE FOR: sample. DO NOT USE FOR: other.
metadata:
  origin: user
---

# sample-skill

本文。
"""

_FRONTMATTER_INLINE = """---
name: inline-skill
description: 一行形式の説明
---

本文。
"""


def _write(tmp: Path, relative: str, text: str) -> Path:
    path = tmp / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestParseSkillFile(unittest.TestCase):
    def test_parses_block_scalar_description(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "sample/SKILL.md", _FRONTMATTER_BLOCK)
            descriptor = parse_skill_file(path)
        assert descriptor is not None
        self.assertEqual(descriptor.name, "sample-skill")
        self.assertIn("USE FOR: sample", descriptor.description)

    def test_parses_inline_description(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "inline/SKILL.md", _FRONTMATTER_INLINE)
            descriptor = parse_skill_file(path)
        assert descriptor is not None
        self.assertEqual(descriptor.description, "一行形式の説明")

    def test_returns_none_without_frontmatter(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "bare/SKILL.md", "# no frontmatter\n")
            self.assertIsNone(parse_skill_file(path))

    def test_tool_name_and_entry_id_follow_the_convention(self) -> None:
        descriptor = SkillDescriptor(name="adversarial-review", description="", path=Path("x"))
        self.assertEqual(descriptor.tool_name, "skill_adversarial-review")
        self.assertEqual(descriptor.entry_id, "skill:skills:skill_adversarial-review")


class TestDiscoverSkills(unittest.TestCase):
    def test_discovers_nested_skills_and_records_category(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "flat/SKILL.md", _FRONTMATTER_BLOCK)
            _write(root, "harness/nested/SKILL.md", _FRONTMATTER_INLINE)
            skills = {s.name: s for s in discover_skills([root])}
        self.assertEqual(skills["sample-skill"].category, "")
        self.assertEqual(skills["inline-skill"].category, "harness")

    def test_first_root_wins_on_duplicate_names(self) -> None:
        with TemporaryDirectory() as a, TemporaryDirectory() as b:
            _write(Path(a), "x/SKILL.md", _FRONTMATTER_INLINE)
            _write(Path(b), "y/SKILL.md", _FRONTMATTER_INLINE.replace("一行形式の説明", "外部側"))
            skills = discover_skills([a, b])
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].description, "一行形式の説明")

    def test_ignores_missing_roots(self) -> None:
        self.assertEqual(discover_skills([Path("does-not-exist-xyz")]), ())

    def test_discovers_the_real_repository_skills(self) -> None:
        skills = discover_skills([_REPO_SKILLS])
        names = {s.name for s in skills}
        self.assertGreaterEqual(len(skills), 30)
        self.assertIn("adversarial-review", names)
        self.assertIn("work-artifacts-layout", names)
        for skill in skills:
            self.assertTrue(skill.description, msg=f"{skill.name} has no description")


class TestBuildSkillEntries(unittest.TestCase):
    def test_entries_are_skill_kind_and_default_to_auto(self) -> None:
        skills = (SkillDescriptor(name="a", description="d", path=Path("a")),)
        entry = build_skill_entries(skills)[0]
        self.assertEqual(entry.kind, "skill")
        self.assertEqual(entry.server, "skills")
        self.assertEqual(entry.pin, "auto")
        self.assertTrue(entry.deferred)

    def test_core_skills_are_pinned_and_not_deferred(self) -> None:
        policy = ToolSearchPolicy.load()
        skills = (
            SkillDescriptor(name="work-artifacts-layout", description="d", path=Path("a")),
            SkillDescriptor(name="azure-kusto", description="d", path=Path("b")),
        )
        entries = {e.name: e for e in build_skill_entries(skills, pin_for=policy.pin_for)}
        self.assertEqual(entries["skill_work-artifacts-layout"].pin, "always")
        self.assertFalse(entries["skill_work-artifacts-layout"].deferred)
        self.assertEqual(entries["skill_azure-kusto"].pin, "auto")
        self.assertTrue(entries["skill_azure-kusto"].deferred)


class TestReadSkillBody(unittest.TestCase):
    def test_returns_full_body_when_small(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "s/SKILL.md", _FRONTMATTER_INLINE)
            body = read_skill_body(SkillDescriptor(name="x", description="", path=path))
        self.assertIn("本文。", body)

    def test_truncates_and_points_at_the_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "s/SKILL.md", "x" * (MAX_SKILL_BODY_CHARS + 500))
            body = read_skill_body(SkillDescriptor(name="x", description="", path=path))
        self.assertIn("truncated at", body)
        self.assertIn(path.as_posix(), body)

    def test_missing_file_is_reported_not_raised(self) -> None:
        body = read_skill_body(SkillDescriptor(name="x", description="", path=Path("nope/SKILL.md")))
        self.assertIn("could not be read", body)


class TestBuildSkillTools(unittest.TestCase):
    def test_core_skills_are_never_deferred_and_others_are_auto(self) -> None:
        skills = (
            SkillDescriptor(name="core", description="c", path=Path("a")),
            SkillDescriptor(name="tail", description="t", path=Path("b")),
        )
        tools = {t.name: t for t in build_skill_tools(skills, core_skill_names={"core"})}
        self.assertEqual(tools["skill_core"].defer, "never")
        self.assertEqual(tools["skill_tail"].defer, "auto")

    def test_tool_description_falls_back_to_the_skill_name(self) -> None:
        skills = (SkillDescriptor(name="bare", description="", path=Path("a")),)
        tool = build_skill_tools(skills)[0]
        self.assertIn("bare", tool.description)

    def test_handler_returns_the_skill_body(self) -> None:
        import asyncio
        from types import SimpleNamespace

        with TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "s/SKILL.md", _FRONTMATTER_INLINE)
            skills = (SkillDescriptor(name="inline-skill", description="d", path=path),)
            tool = build_skill_tools(skills)[0]
            # define_tool は handler を 1 引数 (invocation) 形式へラップする。
            result = asyncio.run(tool.handler(SimpleNamespace(arguments={})))
        body = getattr(result, "text_result_for_llm", result)
        self.assertIn("本文。", body)


class TestSkillManifestPins(unittest.TestCase):
    """FR-TS-03: skill_manifest.json の必須 Skill を pin として取り込む。"""

    def setUp(self) -> None:
        self.manifest = json.loads(
            (_REPO_ROOT / "hve" / "skill_manifest.json").read_text(encoding="utf-8")
        )

    def test_workflow_defaults_become_always_pins(self) -> None:
        pins = skill_manifest_pins(self.manifest, "akm", "1")
        self.assertEqual(pins.get("skill:skills:skill_knowledge-management"), "always")

    def test_step_required_skills_become_always_pins(self) -> None:
        pins = skill_manifest_pins(self.manifest, "asdw-web", "1.2")
        self.assertEqual(pins.get("skill:skills:skill_azure-cli-deploy-scripts"), "always")

    def test_optional_skills_are_not_pinned(self) -> None:
        pins = skill_manifest_pins(self.manifest, "asdw-web", "1.2")
        self.assertNotIn("skill:skills:skill_azure-storage", pins)

    def test_unknown_workflow_yields_no_pins(self) -> None:
        self.assertEqual(skill_manifest_pins(self.manifest, "no-such-workflow", "1"), {})

    def test_missing_workflow_id_yields_no_pins(self) -> None:
        self.assertEqual(skill_manifest_pins(self.manifest, None, "1"), {})


class TestDisabledSkillsIsNotTheOnlyLever(unittest.TestCase):
    """FR-TS-06: long-tail Skill が検索で発見できること（一括無効化に頼らない）。"""

    def test_non_core_skills_remain_in_the_searchable_catalog(self) -> None:
        from hve.toolsearch.policy import apply_policy

        policy = ToolSearchPolicy.load()
        skills = discover_skills([_REPO_SKILLS])
        entries = build_skill_entries(skills, pin_for=policy.pin_for)
        decision = apply_policy(entries, policy)
        searchable = {e.name for e in decision.searchable}
        self.assertIn("skill_adversarial-review", searchable)
        self.assertIn("skill_repo-onboarding-fast", searchable)
        self.assertEqual(decision.dropped, ())


if __name__ == "__main__":
    unittest.main()
