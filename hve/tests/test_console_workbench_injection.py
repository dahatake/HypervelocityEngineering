"""console.warning/error が Workbench attach 中に UserActions に注入されることの検証。"""
from __future__ import annotations

import io
import unittest
from unittest.mock import MagicMock

from hve.console import Console


class TestConsoleAttachInjectsUserActions(unittest.TestCase):
    def test_warning_injects_warn(self):
        c = Console(quiet=True)
        wb = MagicMock()
        c.attach_workbench(wb)
        c.warning("disk almost full")
        wb.append_user_action.assert_called_once_with("WARN", "disk almost full")

    def test_error_injects_error(self):
        c = Console(quiet=True)
        wb = MagicMock()
        c.attach_workbench(wb)
        c.error("step 3 failed")
        wb.append_user_action.assert_called_once_with("ERROR", "step 3 failed")

    def test_error_still_called_when_wb_raises(self):
        """wb.append_user_action 例外時も error() 本体は致命でない。"""
        c = Console(quiet=True)
        wb = MagicMock()
        wb.append_user_action.side_effect = RuntimeError("boom")
        c.attach_workbench(wb)
        # 例外伝播しないこと
        c.error("x")

    def test_no_wb_attached_does_not_crash(self):
        c = Console(quiet=True)
        c.warning("hi")  # 何も起きない
        c.error("hi")


if __name__ == "__main__":
    unittest.main()
