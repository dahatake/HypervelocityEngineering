"""RunState.fatal / fatal_reason フィールドの永続化と復元のテスト。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hve.run_state import RunState


class TestRunStateFatalField(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_state(self, **overrides) -> RunState:
        defaults = dict(run_id="test-run-001", workflow_id="aad")
        defaults.update(overrides)
        return RunState.new(
            run_id=defaults["run_id"],
            workflow_id=defaults["workflow_id"],
            session_name=defaults.get("session_name", "test"),
            work_dir=self.work_dir,
        )

    def test_default_fatal_is_false(self) -> None:
        state = self._make_state()
        self.assertFalse(state.fatal)
        self.assertIsNone(state.fatal_reason)

    def test_fatal_persists_through_save_load(self) -> None:
        state = self._make_state()
        state.fatal = True
        state.fatal_reason = "FileNotFoundError: foo.yaml"
        state.save()
        loaded = RunState.load(state.run_id, work_dir=self.work_dir)
        self.assertTrue(loaded.fatal)
        self.assertEqual(loaded.fatal_reason, "FileNotFoundError: foo.yaml")

    def test_from_dict_without_fatal_keys_defaults_false(self) -> None:
        state = self._make_state()
        state.save()
        with open(state.state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.pop("fatal", None)
        data.pop("fatal_reason", None)
        with open(state.state_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        loaded = RunState.load(state.run_id, work_dir=self.work_dir)
        self.assertFalse(loaded.fatal)
        self.assertIsNone(loaded.fatal_reason)

    def test_to_dict_includes_fatal_fields(self) -> None:
        state = self._make_state()
        state.fatal = True
        state.fatal_reason = "X: y"
        d = state.to_dict()
        self.assertEqual(d.get("fatal"), True)
        self.assertEqual(d.get("fatal_reason"), "X: y")


if __name__ == "__main__":
    unittest.main()
