"""hve.gui.tests.test_page_workbench_job_interaction

FR-GUI-13 の受入テスト。

`WorkbenchPage` が Copilot パネルへ公開する読み取り専用のジョブ対話 API
（宛先列挙・チャネル登録・ログ増分参照）の契約を固定する。
"""

from __future__ import annotations

import dataclasses
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.job_interaction_model import JobTarget  # noqa: E402
from hve.gui.page_workbench import WorkbenchPage  # noqa: E402
from hve.gui.workbench_state import WorkflowInstanceSeed  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


class _JobInteractionTestBase(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()

    def tearDown(self) -> None:
        self.page.cleanup()

    def _seed(self, instance_id: str, workflow_id: str, steps) -> None:
        self.page._state.prepopulate_workflow_instances(
            [
                WorkflowInstanceSeed(
                    instance_id=instance_id,
                    workflow_id=workflow_id,
                    label=workflow_id.upper(),
                    app_id=None,
                    steps=list(steps),
                )
            ]
        )


class TestJobChannelRegistry(_JobInteractionTestBase):
    def test_unregistered_instance_has_no_channel(self) -> None:
        self.assertIsNone(self.page.job_channel_dir("asdw-web"))

    def test_registered_channel_is_returned(self) -> None:
        self.page.register_job_channel("asdw-web", "/tmp/chan-a")
        self.assertEqual(self.page.job_channel_dir("asdw-web"), "/tmp/chan-a")

    def test_channels_are_isolated_per_instance(self) -> None:
        self.page.register_job_channel("aad-web#APP-001", "/tmp/chan-a")
        self.page.register_job_channel("aad-web#APP-002", "/tmp/chan-b")
        self.assertEqual(self.page.job_channel_dir("aad-web#APP-001"), "/tmp/chan-a")
        self.assertEqual(self.page.job_channel_dir("aad-web#APP-002"), "/tmp/chan-b")

    def test_relaunch_replaces_the_channel(self) -> None:
        self.page.register_job_channel("aad-web#APP-001", "/tmp/chan-a")
        self.page.register_job_channel("aad-web#APP-001", "/tmp/chan-b")
        self.assertEqual(self.page.job_channel_dir("aad-web#APP-001"), "/tmp/chan-b")

    def test_registering_none_clears_the_channel(self) -> None:
        self.page.register_job_channel("asdw-web", "/tmp/chan-a")
        self.page.register_job_channel("asdw-web", None)
        self.assertIsNone(self.page.job_channel_dir("asdw-web"))


class TestJobTargets(_JobInteractionTestBase):
    def test_no_instances_means_no_targets(self) -> None:
        self.assertEqual(self.page.job_targets(), [])

    def test_running_step_is_a_sendable_target(self) -> None:
        self._seed("asdw-web", "asdw-web", [("1.1", "設計"), ("1.2", "RED")])
        self.page.register_job_channel("asdw-web", "/tmp/chan")
        self.page._state.update_step_status_in_instance("asdw-web", "1.1", "running")
        targets = [t for t in self.page.job_targets() if t.step_id == "1.1"]
        self.assertEqual(len(targets), 1)
        self.assertTrue(targets[0].is_sendable())
        self.assertEqual(targets[0].channel_dir, "/tmp/chan")

    def test_all_parallel_running_steps_are_listed(self) -> None:
        """並列実行中でも宛先が消えない（単一 step 限定にしない）。"""
        self._seed("asdw-web", "asdw-web", [("1.1", "a"), ("1.2", "b"), ("1.3", "c")])
        self.page.register_job_channel("asdw-web", "/tmp/chan")
        for step_id in ("1.1", "1.2", "1.3"):
            self.page._state.update_step_status_in_instance("asdw-web", step_id, "running")
        running = sorted(t.step_id for t in self.page.job_targets() if t.step_id)
        self.assertEqual(running, ["1.1", "1.2", "1.3"])
        self.assertTrue(all(t.is_sendable() for t in self.page.job_targets() if t.step_id))

    def test_running_step_without_channel_is_not_sendable(self) -> None:
        self._seed("asdw-web", "asdw-web", [("1.1", "a")])
        self.page._state.update_step_status_in_instance("asdw-web", "1.1", "running")
        target = next(t for t in self.page.job_targets() if t.step_id == "1.1")
        self.assertFalse(target.is_sendable())

    def test_multiple_instances_are_listed_separately(self) -> None:
        self._seed("aad-web#APP-001", "aad-web", [("1.1", "a")])
        self._seed("aad-web#APP-002", "aad-web", [("1.1", "a")])
        self.page.register_job_channel("aad-web#APP-001", "/tmp/a")
        self.page.register_job_channel("aad-web#APP-002", "/tmp/b")
        self.page._state.update_step_status_in_instance("aad-web#APP-001", "1.1", "running")
        self.page._state.update_step_status_in_instance("aad-web#APP-002", "1.1", "running")
        channels = sorted(t.channel_dir for t in self.page.job_targets() if t.step_id)
        self.assertEqual(channels, ["/tmp/a", "/tmp/b"])

    def test_finished_instance_is_listed_but_not_sendable(self) -> None:
        self._seed("asdw-web", "asdw-web", [("1.1", "a")])
        self.page.register_job_channel("asdw-web", "/tmp/chan")
        self.page._state.update_step_status_in_instance("asdw-web", "1.1", "done")
        self.page._state.mark_workflow_instance_finished("asdw-web", 0)
        completed = [t for t in self.page.job_targets() if t.step_id is None]
        self.assertEqual(len(completed), 1)
        self.assertFalse(completed[0].is_sendable())

    def test_completed_step_is_not_offered_as_a_send_target(self) -> None:
        self._seed("asdw-web", "asdw-web", [("1.1", "a")])
        self.page.register_job_channel("asdw-web", "/tmp/chan")
        self.page._state.update_step_status_in_instance("asdw-web", "1.1", "running")
        self.page._state.update_step_status_in_instance("asdw-web", "1.1", "done")
        self.assertEqual([t for t in self.page.job_targets() if t.step_id == "1.1"], [])

    def test_targets_are_plain_value_objects(self) -> None:
        self._seed("asdw-web", "asdw-web", [("1.1", "a")])
        self.page._state.update_step_status_in_instance("asdw-web", "1.1", "running")
        target = self.page.job_targets()[0]
        self.assertIsInstance(target, JobTarget)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            target.step_id = "9.9"  # type: ignore[misc]


class TestJobLogAccess(_JobInteractionTestBase):
    def test_step_snapshot_returns_only_that_step(self) -> None:
        self._seed("asdw-web", "asdw-web", [("1.1", "a"), ("1.2", "b")])
        self.page._state.update_step_status_in_instance("asdw-web", "1.1", "running")
        self.page._state.append_workflow_log("asdw-web", "1.1", "line for 1.1")
        self.page._state.append_workflow_log("asdw-web", "1.2", "line for 1.2")
        target = next(t for t in self.page.job_targets() if t.step_id == "1.1")
        snapshot = self.page.job_log_snapshot(target)
        self.assertTrue(any("line for 1.1" in line for line in snapshot))
        self.assertFalse(any("line for 1.2" in line for line in snapshot))

    def test_instance_snapshot_returns_the_whole_job(self) -> None:
        self._seed("asdw-web", "asdw-web", [("1.1", "a")])
        self.page._state.append_workflow_log("asdw-web", "1.1", "alpha")
        self.page._state.append_workflow_log("asdw-web", None, "beta")
        self.page._state.mark_workflow_instance_finished("asdw-web", 0)
        target = next(t for t in self.page.job_targets() if t.step_id is None)
        snapshot = self.page.job_log_snapshot(target)
        self.assertTrue(any("alpha" in line for line in snapshot))
        self.assertTrue(any("beta" in line for line in snapshot))

    def test_snapshot_is_a_copy(self) -> None:
        self._seed("asdw-web", "asdw-web", [("1.1", "a")])
        self.page._state.update_step_status_in_instance("asdw-web", "1.1", "running")
        self.page._state.append_workflow_log("asdw-web", "1.1", "alpha")
        target = next(t for t in self.page.job_targets() if t.step_id == "1.1")
        snapshot = self.page.job_log_snapshot(target)
        snapshot.append("injected")
        self.assertNotIn("injected", self.page.job_log_snapshot(target))

    def test_unknown_instance_snapshot_is_empty(self) -> None:
        ghost = JobTarget(
            instance_id="missing",
            workflow_id="missing",
            label="missing",
            step_id=None,
            step_title="",
            status="done",
            channel_dir=None,
        )
        self.assertEqual(self.page.job_log_snapshot(ghost), [])

    def test_job_log_line_signal_relays_incremental_lines(self) -> None:
        received = []
        self.page.job_log_line.connect(
            lambda instance_id, step_id, line: received.append((instance_id, step_id, line))
        )
        self._seed("asdw-web", "asdw-web", [("1.1", "a")])
        self.page._state.append_workflow_log("asdw-web", "1.1", "streamed")
        self.assertTrue(received)
        self.assertEqual(received[-1][0], "asdw-web")
        self.assertEqual(received[-1][1], "1.1")
        self.assertIn("streamed", received[-1][2])

    def test_unattributed_line_is_not_assigned_to_a_step(self) -> None:
        """帰属不明の行を特定 step へ推測で割り当てない。"""
        self._seed("asdw-web", "asdw-web", [("1.1", "a")])
        self.page._state.update_step_status_in_instance("asdw-web", "1.1", "running")
        self.page._state.append_workflow_log("asdw-web", None, "orphan line")
        target = next(t for t in self.page.job_targets() if t.step_id == "1.1")
        self.assertFalse(any("orphan line" in line for line in self.page.job_log_snapshot(target)))


class TestPostRunAccess(_JobInteractionTestBase):
    def test_session_work_root_is_exposed_read_only(self) -> None:
        self.assertIsNone(self.page.session_work_root())
        run_dir = Path.cwd()
        self.page.set_session_work_root(run_dir)
        self.assertEqual(self.page.session_work_root(), run_dir)

    def test_completed_target_keeps_its_return_code(self) -> None:
        self._seed("asdw-web", "asdw-web", [("1.1", "a")])
        self.page._state.mark_workflow_instance_finished("asdw-web", 3)
        target = next(t for t in self.page.job_targets() if t.step_id is None)
        self.assertEqual(target.returncode, 3)


class TestPlanModeChannelRegistration(_JobInteractionTestBase):
    def test_start_next_in_queue_registers_the_channel_for_the_workflow(self) -> None:
        """通常実行経路でも workflow instance ごとにチャネルを登録する。"""
        import shutil
        import tempfile
        from unittest.mock import MagicMock

        tmp_repo = Path(tempfile.mkdtemp(prefix="job-channel-test-"))
        try:
            args = MagicMock()
            args.repo_root = tmp_repo
            args.workflow = "asdw-web"
            args.model = None
            args.to_argv.side_effect = ValueError("stop before spawning")
            self.page._args_queue = [args]
            self.page._queue_index = 0
            self.page._start_next_in_queue()

            channel = self.page.job_channel_dir("asdw-web")
            self.assertIsNotNone(channel)
            assert channel is not None
            self.assertTrue(Path(channel).is_dir())
            self.assertEqual(channel, self.page.active_steering_ipc_dir())
        finally:
            shutil.rmtree(tmp_repo, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
