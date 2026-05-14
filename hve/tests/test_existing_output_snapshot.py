"""existing_artifact_snapshot のテスト。"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from hve.existing_artifact_snapshot import (
    build_existing_output_snapshot_section,
    summarize_knowledge_output_updates,
)
from hve.workflow_registry import StepDef


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "ci@example.com")
    _git(repo_root, "config", "user.name", "CI")


class TestExistingOutputSnapshot(unittest.TestCase):
    def test_snapshot_shows_existing_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)
            existing_path = repo_root / "docs" / "catalog" / "domain-analytics.md"
            existing_path.parent.mkdir(parents=True, exist_ok=True)
            existing_path.write_text("# domain\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "add domain analytics")
            commit_short = _git(repo_root, "rev-parse", "HEAD")[:7]

            step = StepDef(
                id="1",
                title="x",
                custom_agent=None,
                consumed_artifacts=[],
                output_paths=[
                    "docs/catalog/domain-analytics.md",
                    "docs/catalog/service-catalog.md",
                ],
            )
            snapshot = build_existing_output_snapshot_section(step, repo_root)
            self.assertIn("| docs/catalog/domain-analytics.md | existing |", snapshot)
            self.assertIn(commit_short, snapshot)
            self.assertIn("| docs/catalog/service-catalog.md | missing | - | missing |", snapshot)

    def test_snapshot_shows_dynamic_template_and_no_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)
            step_dynamic = StepDef(
                id="2",
                title="x",
                custom_agent=None,
                consumed_artifacts=[],
                output_paths_template=["docs/services/{key}-spec.md"],
            )
            dynamic_snapshot = build_existing_output_snapshot_section(step_dynamic, repo_root)
            self.assertIn("docs/services/{key}-spec.md", dynamic_snapshot)
            self.assertIn("| dynamic | - | dynamic output template |", dynamic_snapshot)

            step_empty = StepDef(
                id="3",
                title="x",
                custom_agent=None,
                consumed_artifacts=[],
            )
            empty_snapshot = build_existing_output_snapshot_section(step_empty, repo_root)
            self.assertIn("| - | n/a | - | no output_paths defined |", empty_snapshot)

    def test_knowledge_unchanged_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)

            knowledge_file = repo_root / "knowledge" / "D01-overview.md"
            knowledge_file.parent.mkdir(parents=True, exist_ok=True)
            knowledge_file.write_text("# D01\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "add knowledge")

            other_file = repo_root / "docs" / "catalog" / "app-catalog.md"
            other_file.parent.mkdir(parents=True, exist_ok=True)
            other_file.write_text("# app\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "change non knowledge")

            step = StepDef(
                id="4",
                title="x",
                custom_agent=None,
                consumed_artifacts=[],
                output_paths=["knowledge/D01-overview.md"],
            )
            snapshot = build_existing_output_snapshot_section(step, repo_root)
            self.assertIn("| knowledge/D01-overview.md | existing |", snapshot)
            self.assertIn("| unchanged（更新なし） |", snapshot)

            summary = summarize_knowledge_output_updates([step], repo_root, active_steps={"4"})
            self.assertEqual(summary["updated"], [])
            self.assertEqual(summary["unchanged"], ["knowledge/D01-overview.md"])
            self.assertEqual(summary["comparison_unavailable"], [])

    def test_knowledge_comparison_unavailable_without_previous_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)

            knowledge_file = repo_root / "knowledge" / "D01-overview.md"
            knowledge_file.parent.mkdir(parents=True, exist_ok=True)
            knowledge_file.write_text("# D01\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "initial knowledge")

            step = StepDef(
                id="5",
                title="x",
                custom_agent=None,
                consumed_artifacts=[],
                output_paths=["knowledge/D01-overview.md"],
            )
            snapshot = build_existing_output_snapshot_section(step, repo_root)
            self.assertIn("| comparison unavailable（比較対象なし） |", snapshot)

            summary = summarize_knowledge_output_updates([step], repo_root, active_steps={"5"})
            self.assertEqual(summary["updated"], [])
            self.assertEqual(summary["unchanged"], [])
            self.assertEqual(summary["comparison_unavailable"], ["knowledge/D01-overview.md"])

    def test_knowledge_summary_can_have_updated_unchanged_and_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            _init_repo(repo_root)

            d01 = repo_root / "knowledge" / "D01-overview.md"
            d02 = repo_root / "knowledge" / "D02-overview.md"
            d01.parent.mkdir(parents=True, exist_ok=True)
            d01.write_text("# D01\n", encoding="utf-8")
            d02.write_text("# D02\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "add D01 D02")

            # D01のみ更新して、D02は未更新のままにする
            d01.write_text("# D01 changed\n", encoding="utf-8")
            _git(repo_root, "add", ".")
            _git(repo_root, "commit", "-m", "update D01")

            step = StepDef(
                id="6",
                title="x",
                custom_agent=None,
                consumed_artifacts=[],
                output_paths=[
                    "knowledge/D01-overview.md",
                    "knowledge/D02-overview.md",
                    "knowledge/D99-missing.md",
                ],
            )
            summary = summarize_knowledge_output_updates([step], repo_root, active_steps={"6"})
            self.assertEqual(summary["updated"], ["knowledge/D01-overview.md"])
            self.assertEqual(summary["unchanged"], ["knowledge/D02-overview.md"])
            self.assertEqual(summary["comparison_unavailable"], ["knowledge/D99-missing.md"])
