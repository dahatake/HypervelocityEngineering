"""コマンド入力ペイン: controller のディスパッチ動作テスト。"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from hve.workbench.controller import WorkbenchController
from hve.workbench.state import WorkbenchState


def _ctrl() -> WorkbenchController:
    state = WorkbenchState(workflow_id="aad", run_id="r1", model="m")
    return WorkbenchController(state, flush_on_exit=False)


class TestCommandDispatch(unittest.TestCase):
    def test_unknown_command_adds_warn_action(self):
        c = _ctrl()
        c.cmd_enter()
        for ch in "/nope":
            c.cmd_append(ch)
        c.cmd_submit()
        self.assertEqual(len(c.state.user_actions), 1)
        self.assertEqual(c.state.user_actions[0].level, "WARN")
        self.assertIn("unknown command", c.state.user_actions[0].message)

    def test_help_command_lists_keys_and_commands(self):
        c = _ctrl()
        c.cmd_enter()
        for ch in "/help":
            c.cmd_append(ch)
        c.cmd_submit()
        self.assertEqual(len(c.state.user_actions), 1)
        msg = c.state.user_actions[0].message
        self.assertIn("/help", msg)
        self.assertNotIn("/session-store", msg)
        self.assertEqual(c.state.user_actions[0].level, "INFO")

    def test_empty_submit_is_noop(self):
        c = _ctrl()
        c.cmd_enter()
        c.cmd_submit()  # 空入力
        self.assertEqual(len(c.state.user_actions), 0)

    def test_exit_before_all_done_is_warned(self):
        c = _ctrl()
        c.cmd_enter()
        for ch in "/exit":
            c.cmd_append(ch)
        c.cmd_submit()
        levels = [a.level for a in c.state.user_actions]
        self.assertIn("WARN", levels)
        self.assertFalse(c.state.exit_requested)

    def test_exit_after_all_done_requests_exit(self):
        c = _ctrl()
        c.state.all_done = True
        c.cmd_enter()
        for ch in "/exit":
            c.cmd_append(ch)
        c.cmd_submit()
        self.assertTrue(c.state.exit_requested)


class TestActionScroll(unittest.TestCase):
    def test_scroll_actions_up_down(self):
        c = _ctrl()
        for i in range(10):
            c.append_user_action("INFO", f"m{i}")
        # max_offset = 10 - 5 = 5
        c.scroll_actions_up(3)
        self.assertEqual(c.state.user_actions_scroll, 3)
        c.scroll_actions_up(10)  # cap
        self.assertEqual(c.state.user_actions_scroll, 5)
        c.scroll_actions_down(2)
        self.assertEqual(c.state.user_actions_scroll, 3)
        c.scroll_actions_down(100)  # 下限
        self.assertEqual(c.state.user_actions_scroll, 0)


if __name__ == "__main__":
    unittest.main()
