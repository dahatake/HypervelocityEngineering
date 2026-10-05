"""OrchestratorContext のユニットテスト。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator_context import OrchestratorContext, is_active  # type: ignore[import-not-found]


class TestOrchestratorContext(unittest.TestCase):
    def test_defaults(self):
        ctx = OrchestratorContext()
        self.assertFalse(ctx.continue_on_error)

    def test_continue_on_error_can_be_enabled(self):
        ctx = OrchestratorContext(continue_on_error=True)
        self.assertTrue(ctx.continue_on_error)

    def test_is_active(self):
        self.assertFalse(is_active(None))
        self.assertTrue(is_active(OrchestratorContext()))

    def test_durable_versions_reject_negative_values(self):
        with self.assertRaises(ValueError):
            OrchestratorContext(expected_state_version=-1)
        with self.assertRaises(ValueError):
            OrchestratorContext(lease_owner="owner", lease_generation=-1)

    def test_lease_owner_and_generation_are_atomic(self):
        with self.assertRaises(ValueError):
            OrchestratorContext(lease_owner="owner")
        with self.assertRaises(ValueError):
            OrchestratorContext(lease_generation=1)
        ctx = OrchestratorContext(lease_owner="owner", lease_generation=1)
        self.assertEqual((ctx.lease_owner, ctx.lease_generation), ("owner", 1))

    def test_recovery_action_uses_the_fixed_allowlist(self):
        with self.assertRaises(ValueError):
            OrchestratorContext(recovery_action="continue")


if __name__ == "__main__":
    unittest.main()
