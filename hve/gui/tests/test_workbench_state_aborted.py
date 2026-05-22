"""WorkbenchState.mark_aborted の挙動テスト。"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.workbench_state import WorkbenchState  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


class TestWorkbenchStateAborted(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.state = WorkbenchState(
            workflow_id="wf_test",
            run_id="run_test",
            model="auto",
        )

    def test_initial_state(self) -> None:
        self.assertFalse(self.state.all_done)
        self.assertFalse(self.state.aborted)

    def test_mark_aborted_sets_flags_and_emits(self) -> None:
        received: list = []
        self.state.signals().all_done.connect(lambda: received.append(True))
        self.state.mark_aborted()
        self.assertTrue(self.state.aborted)
        self.assertTrue(self.state.all_done)
        self.assertEqual(received, [True])

    def test_mark_aborted_is_idempotent(self) -> None:
        received: list = []
        self.state.signals().all_done.connect(lambda: received.append(True))
        self.state.mark_aborted()
        self.state.mark_aborted()
        self.assertEqual(received, [True])

    def test_mark_aborted_then_root_status_failed(self) -> None:
        from hve.gui.workbench_state import SimpleTaskNode
        self.state.task_tree.add_root(
            SimpleTaskNode(id="root", title="root", status="running")
        )
        self.state.mark_aborted()
        root = self.state.task_tree.root
        assert root is not None
        self.assertEqual(root.status, "failed")


if __name__ == "__main__":
    unittest.main()
