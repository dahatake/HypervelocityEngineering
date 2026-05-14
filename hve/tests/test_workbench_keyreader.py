"""Workbench KeyReader: 非 TTY / 環境変数による disabled 動作とディスパッチ。"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from hve.workbench.keyreader import KeyReader


class TestKeyReaderDisabled(unittest.TestCase):
    def test_disabled_when_no_keyreader_env_set(self):
        with patch.dict(os.environ, {"HVE_NO_KEYREADER": "1"}):
            kr = KeyReader(MagicMock())
            self.assertFalse(kr.enabled)
            kr.start()  # noop
            self.assertIsNone(kr._thread)

    def test_disabled_when_workbench_keyreader_zero(self):
        """後方互換: HVE_WORKBENCH_KEYREADER=0 で明示無効化できる。"""
        env = {"HVE_WORKBENCH_KEYREADER": "0"}
        env.pop("HVE_NO_KEYREADER", None)
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("HVE_NO_KEYREADER", None)
            kr = KeyReader(MagicMock())
            self.assertFalse(kr.enabled)

    def test_enabled_by_default_on_tty(self):
        """TTY 環境では opt-in なしでも有効。pytest 非 TTY では False。"""
        env = {}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("HVE_NO_KEYREADER", None)
            os.environ.pop("HVE_WORKBENCH_KEYREADER", None)
            with patch("hve.workbench.keyreader.sys.stdin") as fake_stdin:
                fake_stdin.isatty.return_value = True
                kr = KeyReader(MagicMock())
                self.assertTrue(kr.enabled)

    def test_disabled_when_not_tty(self):
        # pytest 配下では sys.stdin.isatty() は通常 False
        kr = KeyReader(MagicMock())
        if not kr.enabled:
            kr.start()
            self.assertIsNone(kr._thread)


class TestKeyReaderDispatch(unittest.TestCase):
    def _mk_wb(self) -> MagicMock:
        wb = MagicMock()
        # コマンドモードフラグを明示的に False にしてナビ動作を検証
        wb.state.cmd_mode = False
        wb.state.all_done = False
        return wb

    def test_dispatch_known_keys(self):
        wb = self._mk_wb()
        kr = KeyReader(wb)
        for key, method, args in [
            ("UP", "scroll_up", (1,)),
            ("k", "scroll_up", (1,)),
            ("DOWN", "scroll_down", (1,)),
            ("j", "scroll_down", (1,)),
            ("PGUP", "page_up", ()),
            ("b", "page_up", ()),
            ("PGDN", "page_down", ()),
            ("f", "page_down", ()),
            (" ", "page_down", ()),
            ("HOME", "home", ()),
            ("g", "home", ()),
            ("END", "end", ()),
            ("G", "end", ()),
        ]:
            wb.reset_mock()
            kr._dispatch(key)
            getattr(wb, method).assert_called_once_with(*args)

    def test_dispatch_q_sets_stop(self):
        kr = KeyReader(self._mk_wb())
        self.assertFalse(kr._stop_event.is_set())
        kr._dispatch("q")
        self.assertTrue(kr._stop_event.is_set())

    def test_dispatch_unknown_noop(self):
        wb = self._mk_wb()
        kr = KeyReader(wb)
        kr._dispatch("x")
        wb.scroll_up.assert_not_called()
        wb.scroll_down.assert_not_called()

    def test_dispatch_swallows_exceptions(self):
        wb = self._mk_wb()
        wb.scroll_up.side_effect = RuntimeError("boom")
        kr = KeyReader(wb)
        # 例外は黙殺される
        kr._dispatch("UP")

    def test_dispatch_open_bracket_scrolls_actions_up(self):
        wb = self._mk_wb()
        kr = KeyReader(wb)
        kr._dispatch("[")
        wb.scroll_actions_up.assert_called_once_with(1)

    def test_dispatch_close_bracket_scrolls_actions_down(self):
        wb = self._mk_wb()
        kr = KeyReader(wb)
        kr._dispatch("]")
        wb.scroll_actions_down.assert_called_once_with(1)

    def test_colon_enters_command_mode(self):
        wb = self._mk_wb()
        kr = KeyReader(wb)
        kr._dispatch(":")
        wb.cmd_enter.assert_called_once()

    def test_cmd_mode_routes_chars_to_buffer(self):
        wb = self._mk_wb()
        wb.state.cmd_mode = True
        kr = KeyReader(wb)
        kr._dispatch("a")
        wb.cmd_append.assert_called_once_with("a")

    def test_cmd_mode_enter_submits(self):
        wb = self._mk_wb()
        wb.state.cmd_mode = True
        kr = KeyReader(wb)
        kr._dispatch("ENTER")
        wb.cmd_submit.assert_called_once()

    def test_cmd_mode_esc_cancels(self):
        wb = self._mk_wb()
        wb.state.cmd_mode = True
        kr = KeyReader(wb)
        kr._dispatch("ESC")
        wb.cmd_cancel.assert_called_once()

    def test_cmd_mode_backspace(self):
        wb = self._mk_wb()
        wb.state.cmd_mode = True
        kr = KeyReader(wb)
        kr._dispatch("BACKSPACE")
        wb.cmd_backspace.assert_called_once()

    def test_cmd_mode_disables_nav(self):
        """コマンドモード中は j/k/UP/DOWN はスクロールしず、文字入力として取り込む。"""
        wb = self._mk_wb()
        wb.state.cmd_mode = True
        kr = KeyReader(wb)
        kr._dispatch("j")
        wb.scroll_down.assert_not_called()
        wb.cmd_append.assert_called_once_with("j")


if __name__ == "__main__":
    unittest.main()
