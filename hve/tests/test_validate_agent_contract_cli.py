"""`validate-agent-contract.py` CLI wrapper のテスト。

FR-WF-AAG-01: Tool Search 方針が CLI から validator まで届くこと。
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "skills"
    / "ai-agent-capability-contract"
    / "scripts"
    / "validate-agent-contract.py"
)


def _load_cli():
    spec = importlib.util.spec_from_file_location("validate_agent_contract_cli", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestToolSearchPolicyOption(unittest.TestCase):
    def setUp(self) -> None:
        self.cli = _load_cli()

    def _run(self, argv: list) -> dict:
        with patch.object(self.cli, "validate_ai_agent_capability_artifacts", return_value=[]) as m:
            self.cli.main(argv)
        return m.call_args.kwargs

    def test_policy_defaults_to_auto(self) -> None:
        kwargs = self._run(["--workflow", "aag", "--design", "d.md", "--json"])
        self.assertEqual(kwargs.get("tool_search_policy"), "auto")

    def test_policy_is_forwarded(self) -> None:
        for policy in ("auto", "yes", "no"):
            with self.subTest(policy=policy):
                kwargs = self._run(
                    ["--workflow", "aag", "--design", "d.md", "--tool-search-policy", policy, "--json"]
                )
                self.assertEqual(kwargs.get("tool_search_policy"), policy)

    def test_unknown_policy_is_rejected(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            self.cli.main(["--workflow", "aag", "--design", "d.md", "--tool-search-policy", "ON"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
