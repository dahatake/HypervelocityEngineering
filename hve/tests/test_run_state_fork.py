"""test_run_state_fork.py — Fork-integration T4.2.

`StepState` のフォーク親子リンク列（`retry_count` / `forked_session_id`）と
`RunState` 永続化の後方互換を検証する。

DoD (T4.2):
- 新フィールドの save → load round-trip
- 旧 state.json（フォーク関連フィールド無し）でも load 成功（後方互換）
- 新フィールド既定値（0 / None）が `__post_init__` で適切に正規化される
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from run_state import RunState, StepState, SCHEMA_VERSION  # type: ignore[import-not-found]


def _make_state(work_dir: Path) -> RunState:
    return RunState.new(
        run_id="20260512T031415-fork01",
        workflow_id="asdw-web",
        config=SDKConfig(),
        params={},
        selected_step_ids=["2.3", "3.1"],
        work_dir=work_dir,
    )


class TestStepStateForkFields(unittest.TestCase):
    """`StepState` の新フィールド既定値・検証。"""

    def test_default_values(self) -> None:
        st = StepState()
        self.assertEqual(st.retry_count, 0)
        self.assertIsNone(st.forked_session_id)

    def test_negative_retry_count_normalized_to_zero(self) -> None:
        st = StepState(retry_count=-5)
        self.assertEqual(st.retry_count, 0)

    def test_non_integer_retry_count_normalized_to_zero(self) -> None:
        st = StepState(retry_count="oops")  # type: ignore[arg-type]
        self.assertEqual(st.retry_count, 0)

    def test_set_retry_count(self) -> None:
        st = StepState(retry_count=1, forked_session_id="hve-x-step-1.1-fork1")
        self.assertEqual(st.retry_count, 1)
        self.assertEqual(st.forked_session_id, "hve-x-step-1.1-fork1")


class TestRunStateForkRoundTrip(unittest.TestCase):
    """save → load round-trip でフォーク列が保持されること。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_fork_fields_persist_via_update_step(self) -> None:
        state = _make_state(self.work_dir)
        state.update_step(
            "2.3",
            status="completed",
            retry_count=1,
            forked_session_id="hve-20260512T031415-fork01-step-2.3-fork1",
        )
        # ファイル経由でロード
        loaded = RunState.load(state.run_id, work_dir=self.work_dir)
        self.assertEqual(loaded.step_states["2.3"].retry_count, 1)
        self.assertEqual(
            loaded.step_states["2.3"].forked_session_id,
            "hve-20260512T031415-fork01-step-2.3-fork1",
        )


class TestRunStateBackwardCompat(unittest.TestCase):
    """旧 state.json（フォークフィールド無し）でも load 成功すること。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name) / "runs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_load_legacy_state_json(self) -> None:
        # フォーク列を含まない旧 state.json を手動で構築
        run_id = "20260101T000000-legacy"
        run_dir = self.work_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        legacy = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "workflow_id": "akm",
            "status": "completed",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_updated_at": "2026-01-01T00:01:00+00:00",
            "host": {},
            "config_snapshot": {},
            "params_snapshot": {},
            "selected_step_ids": ["1", "2"],
            "step_states": {
                "1": {
                    "status": "completed",
                    "session_id": "hve-legacy-step-1",
                    "elapsed_seconds": 12.3,
                },
                "2": {"status": "pending"},
            },
        }
        (run_dir / "state.json").write_text(
            json.dumps(legacy, ensure_ascii=False), encoding="utf-8"
        )

        loaded = RunState.load(run_id, work_dir=self.work_dir)
        # フォーク列は既定値で読み込まれる
        self.assertEqual(loaded.step_states["1"].retry_count, 0)
        self.assertIsNone(loaded.step_states["1"].forked_session_id)
        self.assertEqual(loaded.step_states["2"].retry_count, 0)

        # 上書き save しても破壊しない
        loaded.save()
        reloaded = RunState.load(run_id, work_dir=self.work_dir)
        self.assertEqual(reloaded.step_states["1"].retry_count, 0)

    def test_load_legacy_config_snapshot_without_fork_on_retry(self) -> None:
        """M16: 旧 config_snapshot（fork_on_retry キー無し）でも resume できること。"""
        run_id = "20260101T000000-legacy-cfg"
        run_dir = self.work_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        legacy = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "workflow_id": "akm",
            "status": "completed",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_updated_at": "2026-01-01T00:01:00+00:00",
            "host": {},
            # fork_on_retry を持たない旧 snapshot
            "config_snapshot": {"model": "claude-opus-4.7", "max_parallel": 15},
            "params_snapshot": {},
            "selected_step_ids": ["1"],
            "step_states": {"1": {"status": "completed"}},
        }
        (run_dir / "state.json").write_text(
            json.dumps(legacy, ensure_ascii=False), encoding="utf-8"
        )
        loaded = RunState.load(run_id, work_dir=self.work_dir)
        # snapshot に fork_on_retry が無くても load 成功
        self.assertNotIn("fork_on_retry", loaded.config_snapshot)
        self.assertEqual(loaded.config_snapshot.get("model"), "claude-opus-4.7")


if __name__ == "__main__":
    unittest.main()
