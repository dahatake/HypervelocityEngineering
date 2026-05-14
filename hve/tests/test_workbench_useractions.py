"""UserActions ペイン: state + controller + layout の単体検証。"""
from __future__ import annotations

import unittest

from rich.console import Console as RichConsole

from hve.workbench.layout import render_user_actions, render_user_interaction
from hve.workbench.state import (
    USER_ACTIONS_CAPACITY,
    USER_ACTIONS_VISIBLE,
    UserAction,
    WorkbenchState,
)


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="aad", run_id="r1", model="m")


class TestUserActionsState(unittest.TestCase):
    def test_append_basic(self):
        s = _state()
        s.append_user_action("WARN", "disk full", step_id="3")
        self.assertEqual(len(s.user_actions), 1)
        a = s.user_actions[0]
        self.assertEqual(a.level, "WARN")
        self.assertEqual(a.message, "disk full")
        self.assertEqual(a.step_id, "3")
        # スクロールは末尾追従に戻る
        self.assertEqual(s.user_actions_scroll, 0)

    def test_capacity_truncates_oldest(self):
        s = _state()
        for i in range(USER_ACTIONS_CAPACITY + 5):
            s.append_user_action("INFO", f"msg-{i}")
        self.assertEqual(len(s.user_actions), USER_ACTIONS_CAPACITY)
        # 最古は捨てられて 5 以降が残る
        self.assertEqual(s.user_actions[0].message, "msg-5")

    def test_view_returns_last_5(self):
        s = _state()
        for i in range(10):
            s.append_user_action("INFO", f"m{i}")
        view = s.user_actions_view()
        self.assertEqual(len(view), USER_ACTIONS_VISIBLE)
        # 末尾が最新
        self.assertEqual(view[-1].message, "m9")

    def test_view_with_scroll(self):
        s = _state()
        for i in range(10):
            s.append_user_action("INFO", f"m{i}")
        s.user_actions_scroll = 3  # 3 件過去方向へ
        view = s.user_actions_view()
        # 最新側を 3 件分手前へ巻き戻し、5 件取得
        self.assertEqual([a.message for a in view], ["m2", "m3", "m4", "m5", "m6"])

    def test_max_offset(self):
        s = _state()
        for i in range(8):
            s.append_user_action("INFO", f"m{i}")
        # 8 件 - 表示 5 = 最大 3
        self.assertEqual(s.user_actions_max_offset(), 3)


class TestUserActionsRender(unittest.TestCase):
    def _render_plain(self, panel) -> str:
        c = RichConsole(record=True, width=120, force_terminal=False, no_color=True)
        c.print(panel)
        return c.export_text()

    def test_empty_actions_shows_placeholder(self):
        s = _state()
        plain = self._render_plain(render_user_actions(s))
        self.assertIn("通知はまだありません", plain)
        self.assertIn("user actions", plain)

    def test_records_appear_in_panel(self):
        s = _state()
        s.append_user_action("ERROR", "boom!", step_id="3", timestamp="12:34:56")
        plain = self._render_plain(render_user_actions(s))
        self.assertIn("12:34:56", plain)
        self.assertIn("ERROR", plain)
        self.assertIn("boom!", plain)
        # 新フォーマット: "[HH:MM:SS] {step}: {category|level}: {message}"
        self.assertIn("3:", plain)

    def test_scroll_indicator_in_title(self):
        s = _state()
        for i in range(8):
            s.append_user_action("INFO", f"m{i}")
        s.user_actions_scroll = 2
        panel = render_user_actions(s)
        # Panel.title 属性で直接検証（端末幅依存を避ける）
        title = str(panel.title)
        self.assertIn("scroll", title)
        self.assertIn("-2", title)


class TestUserInteractionRender(unittest.TestCase):
    def _render_plain(self, panel) -> str:
        c = RichConsole(record=True, width=200, force_terminal=False, no_color=True)
        c.print(panel)
        return c.export_text()

    def test_help_shown_in_idle(self):
        s = _state()
        plain = self._render_plain(render_user_interaction(s))
        self.assertIn("Press `:`", plain)
        self.assertNotIn("/session-store", plain)
        self.assertIn("/help", plain)
        self.assertIn("userinteraction", plain)

    def test_buffer_shown_in_cmd_mode(self):
        s = _state()
        s.cmd_enter()
        s.cmd_append("/")
        s.cmd_append("h")
        s.cmd_append("e")
        s.cmd_append("l")
        s.cmd_append("p")
        plain = self._render_plain(render_user_interaction(s))
        self.assertIn("/help", plain)
        self.assertIn(">", plain)


class TestCommandInputState(unittest.TestCase):
    def test_enter_clears_buffer(self):
        s = _state()
        s.cmd_buffer = "leftover"
        s.cmd_enter()
        self.assertTrue(s.cmd_mode)
        self.assertEqual(s.cmd_buffer, "")

    def test_cancel(self):
        s = _state()
        s.cmd_enter()
        s.cmd_append("a")
        s.cmd_cancel()
        self.assertFalse(s.cmd_mode)
        self.assertEqual(s.cmd_buffer, "")

    def test_append_ignores_control_chars(self):
        s = _state()
        s.cmd_enter()
        s.cmd_append("\x01")  # SOH
        self.assertEqual(s.cmd_buffer, "")

    def test_append_ignores_when_not_in_cmd_mode(self):
        s = _state()
        s.cmd_append("a")
        self.assertEqual(s.cmd_buffer, "")

    def test_backspace(self):
        s = _state()
        s.cmd_enter()
        s.cmd_append("a")
        s.cmd_append("b")
        s.cmd_backspace()
        self.assertEqual(s.cmd_buffer, "a")

    def test_submit_returns_buffer_and_resets(self):
        s = _state()
        s.cmd_enter()
        s.cmd_append("/")
        s.cmd_append("h")
        s.cmd_append("e")
        s.cmd_append("l")
        s.cmd_append("p")
        text = s.cmd_submit()
        self.assertEqual(text, "/help")
        self.assertFalse(s.cmd_mode)
        self.assertEqual(s.cmd_buffer, "")


class TestUserActionRecord(unittest.TestCase):
    def test_dataclass_fields(self):
        a = UserAction(timestamp="12:00:00", level="INFO", message="hi")
        self.assertEqual(a.timestamp, "12:00:00")
        self.assertEqual(a.level, "INFO")
        self.assertEqual(a.message, "hi")
        self.assertIsNone(a.step_id)


if __name__ == "__main__":
    unittest.main()
