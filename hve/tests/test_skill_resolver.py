from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hve.skill_resolver import (
    discover_available_skills,
    get_external_skill_directory,
    get_optional_skills_for_step,
    get_skill_directory,
    get_required_skills_for_step,
    get_skill_subpaths_for_workflow,
    get_workflow_default_skills,
    load_skill_manifest,
    parse_skill_name_from_file,
    resolve_skill_alias,
    validate_skill_names,
)
from hve.workflow_registry import get_step, list_workflows

_MANIFEST = Path(__file__).resolve().parents[1] / "skill_manifest.json"
_SKILLS_ROOT = _MANIFEST.parents[1] / ".github" / "skills"
_RETIRED_SKILLS = {
    "karpathy-guidelines",
    "appinsights-instrumentation",
    "test-strategy-template",
    "mcp-server-design",
    "svg-renderer",
    "atg",
}


class TestSkillResolver(unittest.TestCase):
    def setUp(self) -> None:
        for cached in (load_skill_manifest, discover_available_skills):
            cached.cache_clear()
            self.addCleanup(cached.cache_clear)

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
        # ARD の実在 Step。step_declared_required を空にして manifest 由来だけを見る。
        req = get_required_skills_for_step("ard", "1", step_declared_required=[])
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
        self.assertEqual(skills.get("azure-ac-verification"), "azure-ac-verification")
        self.assertEqual(skills.get("azure-cli-deploy-scripts"), "azure-cli-deploy-scripts")
        self.assertEqual(skills.get("azure-region-policy"), "azure-region-policy")

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
        self.assertEqual(
            required,
            ["microservice-design-guide", "application-requirement-traceability", *expected_step_skills],
        )
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

    def test_adfdv_aagd_defaults_replace_test_strategy_with_tdd_reality(self) -> None:
        manifest = load_skill_manifest()
        expected_defaults = {
            "adfdv": [
                "dataflow-design-guide",
                "tdd-red-green-reality",
                "application-requirement-traceability",
            ],
            "aagd": [
                "tdd-red-green-reality",
                "ai-agent-capability-contract",
                "application-requirement-traceability",
            ],
        }
        for workflow_id, expected in expected_defaults.items():
            with self.subTest(workflow=workflow_id, source="defaults"):
                self.assertEqual(manifest["workflow_defaults"][workflow_id], expected)
                self.assertEqual(get_workflow_default_skills(workflow_id), expected)
            steps = [
                step for workflow in list_workflows() if workflow.id == workflow_id
                for step in workflow.steps if not step.is_container
            ]
            self.assertTrue(steps, workflow_id)
            for step in steps:
                with self.subTest(workflow=workflow_id, step=step.id):
                    required = get_required_skills_for_step(
                        workflow_id, step.id, step_declared_required=step.required_skills
                    )
                    self.assertEqual(required[:len(expected)], expected)
                    self.assertNotIn("test-strategy-template", required)

    def test_all_workflow_required_skills_resolve_after_pruning(self) -> None:
        manifest = load_skill_manifest()
        available = discover_available_skills()
        retained = {name: path for name, path in available.items() if name not in _RETIRED_SKILLS}
        # FR-CLI-73: preserve known core Skills without freezing the full catalog.
        core_skills = {
            "agent-common-preamble",
            "agentic-retrieval-contract",
            "ai-agent-capability-contract",
            "app-scope-resolution",
            "application-requirement-traceability",
            "code-query",
            "foundry-toolbox-contract",
            "hve-prompt-edition",
            "hve-requirement-traceability",
            "input-file-validation",
            "knowledge-lookup",
            "knowledge-management",
            "markdown-query",
            "task-dag-planning",
            "work-artifacts-layout",
        }
        self.assertLessEqual(core_skills, retained.keys())
        workflows = list_workflows()
        self.assertEqual({workflow.id for workflow in workflows}, set(manifest["workflow_defaults"]))
        with TemporaryDirectory() as temp_dir, patch(
            "hve.skill_resolver._external_skills_root",
            side_effect=AssertionError("V01 must not use home-profile Skills"),
        ):
            root = Path(temp_dir)
            external = self._write_external_skill(root, "microsoft-foundry", "microsoft-foundry")
            for name, subpath in retained.items():
                with self.subTest(retained_skill=name):
                    expected_dir = _SKILLS_ROOT / subpath
                    self.assertTrue((expected_dir / "SKILL.md").is_file())
                    self.assertTrue((expected_dir / "SKILL.md").resolve().is_relative_to(_SKILLS_ROOT.resolve()))
                    self.assertEqual(get_skill_directory(name, external_skills_root=root), expected_dir)
            external_required = set()
            for workflow in workflows:
                steps = [step for step in workflow.steps if not step.is_container]
                self.assertTrue(steps, workflow.id)
                for step in steps:
                    with self.subTest(workflow=workflow.id, step=step.id):
                        declared = [
                            *manifest["workflow_defaults"][workflow.id],
                            *manifest["required_skills"].get(workflow.id, {}).get(step.id, []),
                            *step.required_skills,
                        ]
                        expected = list(dict.fromkeys(resolve_skill_alias(name) for name in declared))
                        required = get_required_skills_for_step(
                            workflow.id, step.id, step_declared_required=step.required_skills
                        )
                        self.assertTrue(required)
                        self.assertEqual(required, expected)
                        external_required.update(set(required) - available.keys())
                        self.assertLessEqual(set(required) - available.keys(), {"microsoft-foundry"})
                        missing, _, _ = validate_skill_names(required, external_skills_root=root)
                        self.assertEqual(missing, [])
                        for name in required:
                            expected_dir = _SKILLS_ROOT / available[name] if name in available else external
                            self.assertEqual(get_skill_directory(name, external_skills_root=root), expected_dir, name)
            self.assertEqual(external_required, {"microsoft-foundry"})

    def test_retired_repository_skills_have_no_active_dependencies(self) -> None:
        remaining_files = sorted(
            skill_file.relative_to(_SKILLS_ROOT).as_posix()
            for skill_file in _SKILLS_ROOT.glob("**/SKILL.md")
            if skill_file.parent.name in _RETIRED_SKILLS
            or parse_skill_name_from_file(skill_file) in _RETIRED_SKILLS
        )
        with self.subTest(source="actual repository SKILL.md files"):
            self.assertEqual(remaining_files, [])
        manifest = load_skill_manifest()
        declarations = {
            f"defaults:{workflow_id}": names
            for workflow_id, names in manifest["workflow_defaults"].items()
        }
        for section in ("required_skills", "optional_skills"):
            declarations.update({
                f"{section}:{workflow_id}/{step_id}": names
                for workflow_id, steps in manifest[section].items()
                for step_id, names in steps.items()
            })
        declarations.update({
            f"inline:{workflow.id}/{step.id}": step.required_skills
            for workflow in list_workflows() for step in workflow.steps
            if not step.is_container
        })
        declarations["aliases"] = list(manifest["aliases"]) + list(manifest["aliases"].values())
        for source, names in declarations.items():
            with self.subTest(source=source):
                self.assertFalse(_RETIRED_SKILLS.intersection(
                    set(names) | {resolve_skill_alias(name) for name in names}
                ))

    def test_declared_skill_mappings_and_resolution_policies_are_applied(self) -> None:
        """Check current declarations, not their equality to a pre-change snapshot."""
        manifest = load_skill_manifest()
        for workflow_id, names in manifest["workflow_defaults"].items():
            if workflow_id in ("adfdv", "aagd"):
                continue
            with self.subTest(workflow=workflow_id):
                self.assertEqual(get_workflow_default_skills(workflow_id), names)
        for alias, canonical in manifest["aliases"].items():
            with self.subTest(alias=alias):
                self.assertEqual(resolve_skill_alias(alias), canonical)
                self.assertEqual(resolve_skill_alias(alias.upper()), canonical)
        for workflow_id, steps in manifest["optional_skills"].items():
            for step_id, names in steps.items():
                with self.subTest(optional=f"{workflow_id}/{step_id}"):
                    self.assertEqual(get_optional_skills_for_step(workflow_id, step_id), names)
                    self.assertEqual(get_optional_skills_for_step(workflow_id, f"{step_id}/APP-009"), names)
        with TemporaryDirectory() as temp_dir, patch(
            "hve.skill_resolver._external_skills_root",
            side_effect=AssertionError("V01 must not use home-profile Skills"),
        ):
            root = Path(temp_dir)
            missing, _, _ = validate_skill_names(["microsoft-foundry"], external_skills_root=root)
            self.assertEqual(missing, ["microsoft-foundry"])
            self.assertIsNone(get_skill_directory("microsoft-foundry", external_skills_root=root))
            external = self._write_external_skill(root, "microsoft-foundry", "microsoft-foundry")
            self.assertEqual(get_external_skill_directory("microsoft-foundry", external_skills_root=root), external)
            self.assertIsNone(get_skill_directory("microsoft-foundr", external_skills_root=root))
            with patch(
                "hve.skill_resolver.get_external_skill_directory",
                side_effect=AssertionError("repository Skill must take precedence"),
            ):
                self.assertEqual(
                    get_skill_directory("KnowledgeManager", external_skills_root=root),
                    _SKILLS_ROOT / "knowledge-management",
                )


class TestManifestMatchesRegistry(unittest.TestCase):
    """skill_manifest.json の参照先は registry に実在する。

    到達しない Step ID は実行時エラーにならず、Skill が黙って適用されない。
    """

    def setUp(self) -> None:
        self.manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        self.registry = {w.id: {s.id for s in w.steps} for w in list_workflows()}

    def test_referenced_workflow_ids_exist(self) -> None:
        for section in ("workflow_defaults", "required_skills", "optional_skills"):
            for workflow_id in self.manifest.get(section) or {}:
                self.assertIn(workflow_id, self.registry, f"{section}.{workflow_id}")

    def test_referenced_step_ids_exist(self) -> None:
        unknown: dict[str, list[str]] = {}
        for section in ("required_skills", "optional_skills"):
            for workflow_id, steps in (self.manifest.get(section) or {}).items():
                known = self.registry.get(workflow_id, set())
                missing = sorted(step_id for step_id in steps if step_id not in known)
                if missing:
                    unknown[f"{section}.{workflow_id}"] = missing
        self.assertEqual(unknown, {})


if __name__ == "__main__":
    unittest.main()
