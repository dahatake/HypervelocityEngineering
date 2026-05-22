"""test_main_entrypoints.py — `python -m hve` のエントリポイント挙動を検証する。

検証内容:
- `cli` サブコマンドのパースが成功する
- `gui` サブコマンドのパースが成功する
- `main()` が引数なし時に GUI を起動しようとする（`run_gui` がモック呼び出しされる）
- PySide6 未導入（ImportError）時は `_cmd_run_interactive` にフォールバックする
- `cli` 指定時は `_cmd_run_interactive` が呼ばれる
"""

from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# __main__.py は Python の __main__ と名前が衝突するため importlib で直接ロードする
_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_entrypoints", os.path.abspath(_main_path))
hve_main = _ilu.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(hve_main)


class TestParser(unittest.TestCase):
    def test_cli_subcommand_parses(self) -> None:
        parser = hve_main._build_parser()
        args = parser.parse_args(["cli"])
        self.assertEqual(args.command, "cli")

    def test_gui_subcommand_parses(self) -> None:
        parser = hve_main._build_parser()
        args = parser.parse_args(["gui"])
        self.assertEqual(args.command, "gui")

    def test_no_args_command_is_none(self) -> None:
        parser = hve_main._build_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.command)


class TestMainDispatch(unittest.TestCase):
    def _patch_startup_recovery(self):
        return mock.patch.object(hve_main, "_run_startup_recovery", lambda: None)

    def test_no_args_launches_gui(self) -> None:
        """引数なし → GUI を起動する。"""
        fake_gui = types.ModuleType("hve.gui")
        fake_gui.run_gui = mock.MagicMock(return_value=0)  # type: ignore[attr-defined]
        with self._patch_startup_recovery(), mock.patch.dict(
            sys.modules, {"hve.gui": fake_gui, "gui": fake_gui}
        ):
            # `from .gui import run_gui` を成功させるため hve パッケージ経由をフックする
            with mock.patch.object(hve_main, "_cmd_run_interactive") as fallback:
                # __main__ が `from .gui import run_gui` する経路をモックで差し替える
                with mock.patch("builtins.__import__", side_effect=self._make_import_hook(fake_gui)):
                    rc = hve_main.main([])
                self.assertEqual(rc, 0)
                fake_gui.run_gui.assert_called_once()
                fallback.assert_not_called()

    def test_no_args_fallback_when_pyside6_missing(self) -> None:
        """PySide6 未導入時は CLI 対話ウィザードへフォールバックする。"""
        with self._patch_startup_recovery(), mock.patch.object(
            hve_main, "_cmd_run_interactive", return_value=42
        ) as fallback:
            with mock.patch(
                "builtins.__import__",
                side_effect=self._make_import_hook(raise_for_gui=True),
            ):
                rc = hve_main.main([])
            self.assertEqual(rc, 42)
            fallback.assert_called_once()

    def test_cli_subcommand_calls_interactive(self) -> None:
        with self._patch_startup_recovery(), mock.patch.object(
            hve_main, "_cmd_run_interactive", return_value=7
        ) as interactive:
            rc = hve_main.main(["cli"])
            self.assertEqual(rc, 7)
            interactive.assert_called_once()

    def test_gui_subcommand_calls_run_gui(self) -> None:
        fake_gui = types.ModuleType("hve.gui")
        fake_gui.run_gui = mock.MagicMock(return_value=0)  # type: ignore[attr-defined]
        with self._patch_startup_recovery():
            with mock.patch(
                "builtins.__import__",
                side_effect=self._make_import_hook(fake_gui),
            ):
                rc = hve_main.main(["gui"])
            self.assertEqual(rc, 0)
            fake_gui.run_gui.assert_called_once()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _make_import_hook(fake_gui: types.ModuleType | None = None, *, raise_for_gui: bool = False):
        """`from .gui import run_gui` をフックする __import__ ラッパーを返す。

        - `name` が `*.gui` （絶対 `hve.gui` or 相対 `gui`）の場合のみ介入する
        - それ以外は通常の `__import__` に委譲する
        """
        real_import = __import__

        def hook(name, globals=None, locals=None, fromlist=(), level=0):
            is_gui_request = (
                (level > 0 and name == "gui")
                or name.endswith(".gui")
                or name == "gui"
            ) and fromlist and "run_gui" in fromlist
            if is_gui_request:
                if raise_for_gui:
                    raise ImportError("PySide6 not installed (simulated)")
                assert fake_gui is not None
                return fake_gui
            return real_import(name, globals, locals, fromlist, level)

        return hook


if __name__ == "__main__":
    unittest.main()
