"""recreate-existing の判定と削除計画テスト。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hve.recreate_existing import (
    apply_recreate_existing_plan,
    build_recreate_existing_prompt_section,
    collect_recreate_existing_plan,
    resolve_recreate_existing,
)
from hve.workflow_registry import StepDef


class TestResolveRecreateExisting(unittest.TestCase):
    def test_detects_prompt_body_label_and_comment(self) -> None:
        decision = resolve_recreate_existing(
            issue_body="hello\n<!-- recreate-existing: true -->",
            labels=["auto-app-selection", "recreate-existing"],
            prompt_inputs=["再作成して"],
            comments=[
                {
                    "body": "@copilot recreate",
                    "author_association": "MEMBER",
                    "user_type": "User",
                    "user_login": "octocat",
                }
            ],
        )
        self.assertTrue(decision.enabled)
        self.assertEqual(decision.sources, ["body", "label", "comment", "prompt"])

    def test_ignores_unauthorized_or_bot_comment(self) -> None:
        decision = resolve_recreate_existing(
            comments=[
                {
                    "body": "@copilot recreate",
                    "author_association": "NONE",
                    "user_type": "User",
                    "user_login": "outsider",
                },
                {
                    "body": "@copilot recreate",
                    "author_association": "MEMBER",
                    "user_type": "Bot",
                    "user_login": "copilot[bot]",
                },
            ]
        )
        self.assertFalse(decision.enabled)
        self.assertEqual(decision.sources, [])


class TestRecreateExistingPlan(unittest.TestCase):
    def test_existing_output_paths_are_deleted_and_templates_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            target = repo_root / "docs" / "catalog" / "domain-analytics.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("before", encoding="utf-8")

            step = StepDef(
                id="1",
                title="x",
                custom_agent=None,
                consumed_artifacts=[],
                output_paths=[
                    "docs/catalog/domain-analytics.md",
                    "docs/catalog/service-catalog.md",
                ],
                output_paths_template=["docs/services/{key}-spec.md"],
            )

            plan = collect_recreate_existing_plan(step, repo_root)
            self.assertEqual(plan.delete_paths, ["docs/catalog/domain-analytics.md"])
            self.assertEqual(plan.missing_paths, ["docs/catalog/service-catalog.md"])
            self.assertEqual(plan.skipped_templates, ["docs/services/{key}-spec.md"])

            section = build_recreate_existing_prompt_section(
                resolve_recreate_existing(prompt_inputs=["再作成して"]),
                plan,
            )
            self.assertIn("recreate_existing=true", section)
            self.assertIn("docs/catalog/domain-analytics.md", section)
            self.assertIn("dynamic output template は保守的に削除スキップ", section)

            apply_recreate_existing_plan(plan, repo_root)
            self.assertFalse(target.exists())
