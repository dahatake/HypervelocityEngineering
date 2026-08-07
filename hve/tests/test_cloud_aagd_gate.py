"""Deterministic tests for the AAGD Cloud Issue-tree gate."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hve.cloud_aagd_gate import GitHubIssueReader, validate_aagd_issue_tree

from hve.tests.test_toolbox_deploy_validation import _CREATE_SCRIPT, _VERIFY_SCRIPT
from hve.tests.test_toolbox_eval_report_validation import _NA_REPORT, _report
from hve.tests.test_toolbox_implementation_validation import (
    _disabled_blocks,
    _tb_blocks,
    _toolbox_config,
    _write_fixture,
)

_CLEAN_SCRIPT = "#!/usr/bin/env bash\nset -euo pipefail\naz account show\n"


def _write_agent(
    root: Path,
    *,
    design_ok: bool = True,
    disabled: bool = False,
    eval_report: bool = True,
    deploy_creates_toolbox: bool = False,
) -> None:
    """Cloud gate が読む checkout 済み repo の最小構成を作る。"""
    blocks = _disabled_blocks() if disabled else _tb_blocks()
    if not design_ok:
        blocks = blocks.replace("- Wildcard pin: not used", '- Wildcard pin: "*" pins every tool')
    _write_fixture(
        root,
        tb_blocks=blocks,
        toolbox_config=None if disabled else _toolbox_config(),
    )

    infra = root / "src" / "infra" / "azure"
    infra.mkdir(parents=True, exist_ok=True)
    use_toolbox = deploy_creates_toolbox or not disabled
    (infra / "create-azure-agent-resources.sh").write_text(
        _CREATE_SCRIPT if use_toolbox else _CLEAN_SCRIPT, encoding="utf-8"
    )
    (infra / "verify-agent-resources.sh").write_text(
        _VERIFY_SCRIPT if use_toolbox else _CLEAN_SCRIPT, encoding="utf-8"
    )

    if eval_report:
        report = root / "docs" / "agent" / "tool-search-eval" / "AG-01-eval-report.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(_NA_REPORT if disabled else _report(), encoding="utf-8")


class TestValidateAagdIssueTree(unittest.TestCase):
    @staticmethod
    def _reader(issues, children):
        return (
            lambda number: issues[number],
            lambda number: list(children.get(number, [])),
        )

    def test_complete_nested_tree_passes(self) -> None:
        issues = {
            1: {"labels": []},
            2: {"labels": [{"name": "aagd:done"}]},
            3: {"labels": [{"name": "aagd:done"}]},
            4: {"labels": [{"name": "aagd:done"}]},
        }
        children = {
            1: [{"number": 2}],
            2: [{"number": 3}, {"number": 4}],
        }
        fetch_issue, fetch_children = self._reader(issues, children)
        self.assertEqual(
            validate_aagd_issue_tree(1, fetch_issue, fetch_children),
            [],
        )

    def test_deep_blocked_and_test_failed_are_reported(self) -> None:
        issues = {
            1: {"labels": []},
            2: {"labels": [{"name": "aagd:done"}]},
            3: {
                "labels": [
                    {"name": "aagd:done"},
                    {"name": "aagd:blocked"},
                    {"name": "aagd:test-failed"},
                ]
            },
        }
        children = {1: [{"number": 2}], 2: [{"number": 3}]}
        fetch_issue, fetch_children = self._reader(issues, children)
        violations = validate_aagd_issue_tree(1, fetch_issue, fetch_children)
        self.assertTrue(any("#3:blocking-labels=" in item for item in violations))
        self.assertTrue(any("aagd:blocked" in item for item in violations))
        self.assertTrue(any("aagd:test-failed" in item for item in violations))

    def test_missing_done_and_empty_tree_are_reported(self) -> None:
        issues: dict[int, dict[str, object]] = {
            1: {"labels": []},
            2: {"labels": []},
        }
        fetch_issue, fetch_children = self._reader(
            issues,
            {1: [{"number": 2}]},
        )
        self.assertIn(
            "#2:missing-aagd:done",
            validate_aagd_issue_tree(1, fetch_issue, fetch_children),
        )

        empty_fetch_issue, empty_fetch_children = self._reader(
            {1: {"labels": []}},
            {},
        )
        self.assertEqual(
            validate_aagd_issue_tree(
                1,
                empty_fetch_issue,
                empty_fetch_children,
            ),
            ["#1:no-descendant-issues"],
        )

    def test_root_self_improve_blocked_is_allowed_only_for_retry(self) -> None:
        issues = {
            1: {"labels": [{"name": "aagd:blocked"}]},
            2: {"labels": [{"name": "aagd:done"}]},
        }
        fetch_issue, fetch_children = self._reader(
            issues,
            {1: [{"number": 2}]},
        )
        self.assertTrue(
            validate_aagd_issue_tree(1, fetch_issue, fetch_children)
        )
        self.assertEqual(
            validate_aagd_issue_tree(
                1,
                fetch_issue,
                fetch_children,
                allow_root_self_improve_blocked=True,
            ),
            [],
        )

    def test_cycle_is_deduplicated(self) -> None:
        issues = {
            1: {"labels": []},
            2: {"labels": [{"name": "aagd:done"}]},
        }
        fetch_issue, fetch_children = self._reader(
            issues,
            {1: [{"number": 2}], 2: [{"number": 1}]},
        )
        self.assertEqual(
            validate_aagd_issue_tree(1, fetch_issue, fetch_children),
            [],
        )


class TestGitHubIssueReaderPagination(unittest.TestCase):
    def test_fetch_children_reads_more_than_one_page(self) -> None:
        reader = GitHubIssueReader("owner/repo", "token")
        first = [{"number": index} for index in range(1, 101)]
        second = [{"number": 101}]
        responses = [first, second]
        with patch.object(reader, "_get", side_effect=responses) as mock_get:
            children = list(reader.fetch_children(42))
        self.assertEqual(len(children), 101)
        self.assertEqual(mock_get.call_count, 2)
        self.assertIn("page=1", mock_get.call_args_list[0].args[0])
        self.assertIn("page=2", mock_get.call_args_list[1].args[0])


class TestArtifactRevalidation(unittest.TestCase):
    """FR-WF-AAGD-04: label が全 done でも artifact が不正なら止める。"""

    @staticmethod
    def _tree():
        issues = {1: {"labels": []}, 2: {"labels": [{"name": "aagd:done"}]}}
        children = {1: [{"number": 2}]}
        return (
            lambda number: issues[number],
            lambda number: list(children.get(number, [])),
        )

    def _run(self, repo_root, policy="auto"):
        fetch_issue, fetch_children = self._tree()
        return validate_aagd_issue_tree(
            1,
            fetch_issue,
            fetch_children,
            repo_root=repo_root,
            tool_search_policy=policy,
        )

    def test_repo_root_is_optional_for_backward_compatibility(self) -> None:
        fetch_issue, fetch_children = self._tree()
        self.assertEqual(validate_aagd_issue_tree(1, fetch_issue, fetch_children), [])

    def test_label_tree_green_but_broken_artifact_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_agent(root, design_ok=False)
            violations = self._run(root, policy="yes")
        self.assertTrue(any("TB-CAP" in item for item in violations), violations)

    def test_complete_artifacts_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_agent(root)
            violations = self._run(root, policy="yes")
        self.assertEqual(violations, [], violations)

    def test_missing_eval_report_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_agent(root, eval_report=False)
            violations = self._run(root, policy="yes")
        self.assertTrue(any("eval" in item.lower() for item in violations), violations)

    def test_policy_no_accepts_absent_toolbox_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_agent(root, disabled=True)
            violations = self._run(root, policy="no")
        self.assertEqual(violations, [], violations)

    def test_policy_no_rejects_toolbox_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_agent(root, disabled=True, deploy_creates_toolbox=True)
            violations = self._run(root, policy="no")
        self.assertTrue(any("must not" in item.lower() for item in violations), violations)

    def test_unknown_policy_fails_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_agent(root)
            violations = self._run(root, policy="ON")
        self.assertTrue(any("policy" in item.lower() for item in violations), violations)

    def test_no_agent_design_is_reported(self) -> None:
        with TemporaryDirectory() as temp_dir:
            violations = self._run(Path(temp_dir), policy="yes")
        self.assertTrue(
            any("agent-detail" in item for item in violations), violations
        )


if __name__ == "__main__":
    unittest.main()
