from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hve.skill_resolver import (
    discover_available_skills,
    get_external_skill_directory,
    get_optional_skills_for_step,
    get_skill_directory,
    get_required_skills_for_step,
    get_skill_subpaths_for_workflow,
    resolve_skill_alias,
    validate_skill_names,
)
from hve.workflow_registry import get_step


class TestSkillResolver(unittest.TestCase):
    @staticmethod
    def _write_external_skill(
        root: Path,
        directory_name: str,
        declared_name: str,
    ) -> Path:
        skill_dir = root / directory_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {declared_name}\n---\n# Test skill\n",
            encoding="utf-8",
        )
        return skill_dir

    def test_discover_available_skills_contains_knowledge(self) -> None:
        skills = discover_available_skills()
        self.assertIn("knowledge-management", skills)
        self.assertIn("knowledge-lookup", skills)

    def test_required_skill_from_manifest_for_akm(self) -> None:
        req = get_required_skills_for_step("akm", "1", step_declared_required=[])
        self.assertIn("knowledge-management", req)

    def test_workflow_default_skill_applies_to_ard_step(self) -> None:
        req = get_required_skills_for_step("ard", "3.1", step_declared_required=[])
        self.assertIn("task-dag-planning", req)
        self.assertNotIn("knowledge-management", req)

    def test_required_skill_from_manifest_for_ard_step(self) -> None:
        req = get_required_skills_for_step("ard", "3", step_declared_required=[])
        self.assertIn("task-dag-planning", req)
        self.assertIn("knowledge-management", req)

    def test_alias_resolution(self) -> None:
        self.assertEqual(resolve_skill_alias("KnowledgeManager"), "knowledge-management")

    def test_workflow_skill_subpath(self) -> None:
        subpaths = get_skill_subpaths_for_workflow("adi")
        self.assertIn("knowledge-lookup", subpaths)

    def test_adi_questionnaire_steps_require_knowledge_lookup(self) -> None:
        for step_id in ("1.1", "1.2"):
            required = get_required_skills_for_step(
                "adi", step_id, step_declared_required=["knowledge-lookup"]
            )
            self.assertIn("knowledge-lookup", required)

    def test_discover_available_skills_contains_repo_owned_azure_skills(self) -> None:
        skills = discover_available_skills()
        self.assertEqual(skills.get("azure-ac-verification"), "azure-skills/azure-ac-verification")
        self.assertEqual(skills.get("azure-cli-deploy-scripts"), "azure-skills/azure-cli-deploy-scripts")
        self.assertEqual(skills.get("azure-region-policy"), "azure-skills/azure-region-policy")

    def test_asdw_addservice_deploy_required_skills_resolve_without_missing(self) -> None:
        step = get_step("asdw-web", "2.2")
        assert step is not None
        declared = list(step.required_skills)
        required = get_required_skills_for_step(
            "asdw-web", "2.2", step_declared_required=declared
        )
        expected_step_skills = (
            "azure-cli-deploy-scripts",
            "azure-ac-verification",
            "azure-region-policy",
        )
        self.assertEqual(required, ["microservice-design-guide", *expected_step_skills])
        for skill in expected_step_skills:
            self.assertIn(skill, required)
        missing, _, _ = validate_skill_names(required)
        self.assertEqual(missing, [])

    def test_validate_skill_names_missing(self) -> None:
        missing, _, suggestions = validate_skill_names(["missing-skill-xyz"])
        self.assertEqual(missing, ["missing-skill-xyz"])
        self.assertIn("missing-skill-xyz", suggestions)

    def test_external_skill_directory_requires_exact_directory_and_name(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = self._write_external_skill(
                root,
                "microsoft-foundry",
                "microsoft-foundry",
            )

            self.assertEqual(
                get_external_skill_directory(
                    "microsoft-foundry",
                    external_skills_root=root,
                ),
                expected,
            )
            self.assertIsNone(
                get_external_skill_directory(
                    "missing-skill",
                    external_skills_root=root,
                )
            )

    def test_external_skill_directory_rejects_mismatched_frontmatter_name(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_external_skill(
                root,
                "microsoft-foundry",
                "another-skill",
            )

            self.assertIsNone(
                get_external_skill_directory(
                    "microsoft-foundry",
                    external_skills_root=root,
                )
            )

    def test_external_skill_directory_rejects_path_traversal_names(self) -> None:
        with TemporaryDirectory() as temp_dir:
            container = Path(temp_dir)
            root = container / "skills"
            root.mkdir()
            self._write_external_skill(
                container,
                "outside-skill",
                "outside-skill",
            )

            self.assertIsNone(
                get_external_skill_directory(
                    "../outside-skill",
                    external_skills_root=root,
                )
            )
            self.assertIsNone(
                get_external_skill_directory(
                    "..\\outside-skill",
                    external_skills_root=root,
                )
            )

    def test_external_skill_directory_rejects_linked_skill_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            container = Path(temp_dir)
            root = container / "skills"
            skill_dir = root / "microsoft-foundry"
            root.mkdir()
            skill_dir.mkdir()
            external_skill_file = container / "outside-skill.md"
            external_skill_file.write_text(
                "---\nname: microsoft-foundry\n---\n# Outside skill\n",
                encoding="utf-8",
            )
            try:
                os.symlink(external_skill_file, skill_dir / "SKILL.md")
            except OSError as exc:
                self.skipTest(f"file symlink is unavailable: {exc}")

            self.assertIsNone(
                get_external_skill_directory(
                    "microsoft-foundry",
                    external_skills_root=root,
                )
            )

    def test_skill_directory_prefers_repository_skill_over_external_duplicate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            external = self._write_external_skill(
                root,
                "knowledge-management",
                "knowledge-management",
            )

            resolved = get_skill_directory(
                "knowledge-management",
                external_skills_root=root,
            )

            self.assertIsNotNone(resolved)
            assert resolved is not None
            self.assertNotEqual(resolved, external)
            self.assertEqual(resolved / "SKILL.md", Path(__file__).parents[2] / ".github" / "skills" / "knowledge-management" / "SKILL.md")

    def test_validate_skill_names_accepts_exact_external_skill(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_external_skill(
                root,
                "microsoft-foundry",
                "microsoft-foundry",
            )

            missing, resolved, _ = validate_skill_names(
                ["microsoft-foundry"],
                external_skills_root=root,
            )

            self.assertEqual(missing, [])
            self.assertEqual(resolved, {"microsoft-foundry": "microsoft-foundry"})

    def test_optional_skills_are_scoped_to_exact_active_step(self) -> None:
        self.assertEqual(
            get_optional_skills_for_step("asdw-web", "2.2"),
            [
                "microsoft-foundry",
                "azure-ai",
                "azure-aigateway",
                "azure-messaging",
                "entra-app-registration",
                "azure-rbac",
                "azure-quotas",
            ],
        )
        self.assertEqual(
            get_optional_skills_for_step("asdw-web", "1.3"),
            [],
        )

    def test_optional_skills_canonicalize_workflow_alias_and_fanout_step(self) -> None:
        self.assertEqual(
            get_optional_skills_for_step("asdw", "5.1/APP-009"),
            [
                "azure-resource-lookup",
                "azure-resource-visualizer",
                "azure-compliance",
                "azure-reliability",
                "azure-cost",
            ],
        )

    def test_optional_skills_do_not_add_unrelated_or_generic_deploy_skills(self) -> None:
        self.assertEqual(get_optional_skills_for_step("asdw-web", "4.2"), [])
        add_service = get_optional_skills_for_step("asdw-web", "2.2")
        self.assertNotIn("azure-prepare", add_service)
        self.assertNotIn("azure-deploy", add_service)
        self.assertNotIn("azure-validate", add_service)

    def test_optional_skills_unknown_coordinate_is_empty(self) -> None:
        self.assertEqual(get_optional_skills_for_step("unknown", "1"), [])
        self.assertEqual(get_optional_skills_for_step("aagd", "99"), [])


if __name__ == "__main__":
    unittest.main()
