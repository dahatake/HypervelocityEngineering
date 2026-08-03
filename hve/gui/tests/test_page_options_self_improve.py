"""GUI Self-Improve tri-state option contract tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.page_options import OptionsPage  # noqa: E402


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class TestSelfImproveTriState(unittest.TestCase):
    def setUp(self) -> None:
        _get_app()
        self.page = OptionsPage()

    def tearDown(self) -> None:
        self.page.deleteLater()

    def test_inherit_emits_no_flag_for_aag_default(self) -> None:
        self.page.c3.self_improve.set_tristate(None)
        args = self.page.build_args_for_workflow("aag")
        self.assertFalse(args.self_improve)
        self.assertFalse(args.no_self_improve)
        argv = args.to_argv()
        self.assertNotIn("--self-improve", argv)
        self.assertNotIn("--no-self-improve", argv)

    def test_explicit_on_emits_self_improve(self) -> None:
        self.page.c3.self_improve.set_tristate(True)
        args = self.page.build_args_for_workflow("aag")
        self.assertTrue(args.self_improve)
        self.assertFalse(args.no_self_improve)
        self.assertIn("--self-improve", args.to_argv())

    def test_explicit_off_emits_emergency_opt_out(self) -> None:
        self.page.c3.self_improve.set_tristate(False)
        args = self.page.build_args_for_workflow("aag")
        self.assertFalse(args.self_improve)
        self.assertTrue(args.no_self_improve)
        self.assertIn("--no-self-improve", args.to_argv())


if __name__ == "__main__":
    unittest.main()
