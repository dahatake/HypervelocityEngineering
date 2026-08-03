"""Deterministic tests for the AAGD Cloud Issue-tree gate."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from hve.cloud_aagd_gate import GitHubIssueReader, validate_aagd_issue_tree


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


if __name__ == "__main__":
    unittest.main()
