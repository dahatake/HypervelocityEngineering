"""HeaderBar.mark_aborted / mark_completed の状態遷移テスト。"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.header_bar import HeaderBar  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


class TestHeaderBarAbortedState(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.bar = HeaderBar()

    def test_initial_state(self) -> None:
        self.assertFalse(self.bar.is_all_completed())
        self.assertFalse(self.bar.is_aborted())

    def test_mark_completed_sets_flag(self) -> None:
        self.bar.mark_completed(True)
        self.assertTrue(self.bar.is_all_completed())
        self.assertFalse(self.bar.is_aborted())

    def test_mark_aborted_sets_flag(self) -> None:
        self.bar.mark_aborted(True)
        self.assertTrue(self.bar.is_aborted())
        self.assertFalse(self.bar.is_all_completed())

    def test_completed_and_aborted_are_mutually_exclusive(self) -> None:
        self.bar.mark_completed(True)
        self.bar.mark_aborted(True)
        self.assertTrue(self.bar.is_aborted())
        self.assertFalse(self.bar.is_all_completed())
        self.bar.mark_completed(True)
        self.assertTrue(self.bar.is_all_completed())
        self.assertFalse(self.bar.is_aborted())

    def test_set_current_step_clears_both_flags(self) -> None:
        self.bar.mark_aborted(True)
        self.bar.set_current_step(0)
        self.assertFalse(self.bar.is_aborted())
        self.bar.mark_completed(True)
        self.bar.set_current_step(1)
        self.assertFalse(self.bar.is_all_completed())

    def test_mark_aborted_false_clears_flag(self) -> None:
        self.bar.mark_aborted(True)
        self.bar.mark_aborted(False)
        self.assertFalse(self.bar.is_aborted())


if __name__ == "__main__":
    unittest.main()
