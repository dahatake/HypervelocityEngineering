"""DAG parity helper tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hve.dag_parity import (
    compare_workflow_id_sets,
    extract_bash_workflow_ids,
    extract_reusable_workflow_ids,
)


class TestDAGParity(unittest.TestCase):
    def test_extract_bash_workflow_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workflow-registry.sh"
            path.write_text(
                "_WORKFLOW_REGISTRY[aas]=x\n_WORKFLOW_REGISTRY[aad]=x\n",
                encoding="utf-8",
            )

            self.assertEqual(extract_bash_workflow_ids(path), ("aad", "aas"))

    def test_extract_reusable_workflow_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workflow.yml"
            path.write_text(
                "python -m hve --workflow aad-web --foo bar\n"
                "python -m hve --workflow aqod\n",
                encoding="utf-8",
            )

            self.assertEqual(extract_reusable_workflow_ids([path]), ("aad-web", "aqod"))

    def test_compare_workflow_id_sets_classifies_alias_and_missing_registry(self) -> None:
        report = compare_workflow_id_sets(
            hve_ids=["aas", "aad-web", "aqod"],
            cloud_bash_ids=["aas", "aad"],
            reusable_workflow_ids=["aas", "aad-web", "aqod"],
        )

        self.assertEqual(report.by_classification("same")[0].workflow_id, "aas")
        self.assertEqual(report.by_classification("legacy-alias")[0].hve_id, "aad-web")
        self.assertEqual(report.by_classification("legacy-alias")[0].cloud_bash_id, "aad")
        self.assertEqual(report.by_classification("missing-bash-registry")[0].workflow_id, "aqod")


if __name__ == "__main__":
    unittest.main()
