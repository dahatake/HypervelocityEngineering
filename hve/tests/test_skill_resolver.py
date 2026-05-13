from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skill_resolver import (
    discover_available_skills,
    get_required_skills_for_step,
    get_skill_subpaths_for_workflow,
    resolve_skill_alias,
    validate_skill_names,
)


class TestSkillResolver(unittest.TestCase):
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
        self.assertIn("knowledge-management", req)

    def test_alias_resolution(self) -> None:
        self.assertEqual(resolve_skill_alias("KnowledgeManager"), "knowledge-management")

    def test_workflow_skill_subpath(self) -> None:
        subpaths = get_skill_subpaths_for_workflow("aqod")
        self.assertIn("planning/knowledge-lookup", subpaths)

    def test_validate_skill_names_missing(self) -> None:
        missing, _, suggestions = validate_skill_names(["missing-skill-xyz"])
        self.assertEqual(missing, ["missing-skill-xyz"])
        self.assertIn("missing-skill-xyz", suggestions)


if __name__ == "__main__":
    unittest.main()
