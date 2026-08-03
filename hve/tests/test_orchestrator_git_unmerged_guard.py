"""Git unmerged index guard tests for orchestrator branch creation."""

from __future__ import annotations

import importlib
import types
import unittest
from unittest.mock import Mock, patch

_orchestrator = importlib.import_module("hve.orchestrator")


class TestGitCheckoutNewBranchUnmergedGuard(unittest.TestCase):
    """_git_checkout_new_branch must fail fast when Git index has unmerged entries."""

    def test_unmerged_index_blocks_fetch_and_checkout(self) -> None:
        console = Mock()
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(list(args))
            if list(args) == ["git", "diff", "--name-only", "--diff-filter=U"]:
                return types.SimpleNamespace(
                    returncode=0,
                    stdout="src/api/SVC-13/Functions.cs\nsrc/api/SVC-16/Svc16Functions.cs\n",
                    stderr="",
                )
            self.fail(f"unexpected git command after unmerged index detection: {args!r}")

        with patch.object(_orchestrator.subprocess, "run", side_effect=fake_run):
            result = _orchestrator._git_checkout_new_branch(
                "copilot-sdk/asdw-web-step-3-4-deadbeef",
                "main",
                console,
            )

        self.assertFalse(result)
        self.assertEqual(calls, [["git", "diff", "--name-only", "--diff-filter=U"]])
        console.error.assert_called_once()
        message = console.error.call_args.args[0]
        self.assertIn("Git index", message)
        self.assertIn("src/api/SVC-13/Functions.cs", message)
        self.assertIn("src/api/SVC-16/Svc16Functions.cs", message)


if __name__ == "__main__":
    unittest.main()