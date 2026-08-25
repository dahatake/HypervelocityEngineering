"""test_runner_file_tracking.py — StepRunner PowerShell file tracking tests."""

from __future__ import annotations

import os
import sys
import unittest
import unittest.mock
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from runner import StepRunner


class TestTrackPowershellFiles(unittest.TestCase):
    """Tests for _track_powershell_files."""

    def _make_runner(self, **kwargs: Any) -> StepRunner:
        config = SDKConfig(**kwargs) if kwargs else SDKConfig()
        console = unittest.mock.MagicMock()
        return StepRunner(config=config, console=console)

    def test_get_childitem_path(self) -> None:
        runner = self._make_runner()
        runner._track_powershell_files("1", "Get-ChildItem -Path docs/input")
        runner.console.track_file.assert_any_call("1", os.path.normpath("docs/input"), "read")
        runner.console.file_io.assert_any_call("1", os.path.normpath("docs/input"), "read")

    def test_out_file_filepath(self) -> None:
        runner = self._make_runner()
        runner._track_powershell_files("1", "Get-Content in.txt | Out-File -FilePath out.txt")
        runner.console.track_file.assert_any_call("1", os.path.normpath("out.txt"), "write")
        runner.console.file_io.assert_any_call("1", os.path.normpath("out.txt"), "write")

    def test_set_content_path(self) -> None:
        runner = self._make_runner()
        runner._track_powershell_files("1", "Set-Content -Path out2.txt -Value hello")
        runner.console.track_file.assert_any_call("1", os.path.normpath("out2.txt"), "write")
        runner.console.file_io.assert_any_call("1", os.path.normpath("out2.txt"), "write")

    def test_redirect_operator(self) -> None:
        runner = self._make_runner()
        runner._track_powershell_files("1", "Write-Output hello > out3.txt")
        runner.console.track_file.assert_any_call("1", os.path.normpath("out3.txt"), "write")
        runner.console.file_io.assert_any_call("1", os.path.normpath("out3.txt"), "write")

    def test_copy_item_source_read_and_destination_write(self) -> None:
        runner = self._make_runner()
        runner._track_powershell_files(
            "1", "Copy-Item -Path input.txt -Destination output.txt"
        )
        self.assertEqual(
            runner.console.track_file.call_args_list,
            [
                unittest.mock.call("1", os.path.normpath("input.txt"), "read"),
                unittest.mock.call("1", os.path.normpath("output.txt"), "write"),
            ],
        )
        self.assertEqual(
            runner.console.file_io.call_args_list,
            [
                unittest.mock.call("1", os.path.normpath("input.txt"), "read"),
                unittest.mock.call("1", os.path.normpath("output.txt"), "write"),
            ],
        )

    def test_pipeline_path_read_and_filepath_write(self) -> None:
        runner = self._make_runner()
        runner._track_powershell_files(
            "1", "Get-Content -Path in.txt | Out-File -FilePath out.txt"
        )
        self.assertEqual(
            runner.console.track_file.call_args_list,
            [
                unittest.mock.call("1", os.path.normpath("in.txt"), "read"),
                unittest.mock.call("1", os.path.normpath("out.txt"), "write"),
            ],
        )
        self.assertEqual(
            runner.console.file_io.call_args_list,
            [
                unittest.mock.call("1", os.path.normpath("in.txt"), "read"),
                unittest.mock.call("1", os.path.normpath("out.txt"), "write"),
            ],
        )

    def test_no_path_param_no_capture(self) -> None:
        runner = self._make_runner()
        runner._track_powershell_files("1", "Get-ChildItem docs")
        runner.console.track_file.assert_not_called()
        runner.console.file_io.assert_not_called()

    def test_switch_param_not_captured_as_path(self) -> None:
        runner = self._make_runner()
        runner._track_powershell_files("1", "Get-ChildItem -Recurse -Force")
        runner.console.track_file.assert_not_called()
        runner.console.file_io.assert_not_called()

    def test_variable_and_expression_tokens_not_captured_as_path(self) -> None:
        """シェル変数・式トークンをパスとして追跡しない。"""
        for command in (
            "Get-Content -Path $p",
            "Set-Content -Path $p -Value x",
            "Get-Content -Path `$p))",
            "Get-Content -Path 'docs/architectural-requirements-app-006.md')",
        ):
            runner = self._make_runner()
            runner._track_powershell_files("2/APP-006", command)
            runner.console.track_file.assert_not_called()
            runner.console.file_io.assert_not_called()

    def test_quoted_literal_path_is_still_captured(self) -> None:
        runner = self._make_runner()
        runner._track_powershell_files("1", "Get-Content -Path 'docs/input.md'")
        runner.console.track_file.assert_any_call("1", os.path.normpath("docs/input.md"), "read")

    def test_track_tool_files_edit_file_calls_file_io_read_write(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "edit_file", {"path": "src/main.py"})
        runner.console.track_file.assert_any_call("1", os.path.normpath("src/main.py"), "read")
        runner.console.track_file.assert_any_call("1", os.path.normpath("src/main.py"), "write")
        runner.console.file_io.assert_any_call("1", os.path.normpath("src/main.py"), "read")
        runner.console.file_io.assert_any_call("1", os.path.normpath("src/main.py"), "write")

    def test_track_tool_files_apply_patch_headers_as_writes(self) -> None:
        runner = self._make_runner()
        patch_text = """*** Begin Patch
*** Update File: src/main.py
@@
-old
+new
*** Add File: docs/new.md
+text
*** Delete File: tmp/old.txt
*** End Patch
"""
        runner._track_tool_files("1", "apply_patch", {"input": patch_text})
        runner.console.track_file.assert_any_call("1", os.path.normpath("src/main.py"), "write")
        runner.console.track_file.assert_any_call("1", os.path.normpath("docs/new.md"), "write")
        runner.console.track_file.assert_any_call("1", os.path.normpath("tmp/old.txt"), "write")
        runner.console.file_io.assert_any_call("1", os.path.normpath("src/main.py"), "write")
        runner.console.file_io.assert_any_call("1", os.path.normpath("docs/new.md"), "write")
        runner.console.file_io.assert_any_call("1", os.path.normpath("tmp/old.txt"), "write")

    def test_track_tool_files_apply_patch_ignores_body_lines(self) -> None:
        runner = self._make_runner()
        patch_text = """*** Begin Patch
+*** Update File: not-a-header.md
*** End Patch
"""
        runner._track_tool_files("1", "apply_patch", {"input": patch_text})
        runner.console.track_file.assert_not_called()
        runner.console.file_io.assert_not_called()


class TestTrackToolFilesSDKAliases(unittest.TestCase):
    """Sub-017 RED: SDK ツール別名 (create/edit/view) の I/O 分類契約。

    Copilot SDK は書き込み系ツールを短縮名 ``create`` / ``edit`` / ``view`` で
    通知する場合がある。これらが未分類だと ``create`` / ``edit`` が read 扱いに
    フォールバックし、書き込みが provenance に記録されない。本テスト群は
    別名集合の不足だけを理由に RED になる（既存 tool 名の挙動は不変）。
    """

    def _make_runner(self) -> StepRunner:
        console = unittest.mock.MagicMock()
        return StepRunner(config=SDKConfig(), console=console)

    def _tracked_actions(self, runner: StepRunner, path: str) -> set[str]:
        norm = os.path.normpath(path)
        return {
            call.args[2]
            for call in runner.console.track_file.call_args_list
            if call.args[1] == norm
        }

    def test_create_alias_tracked_as_write_only(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "create", {"path": "src/new.py"})
        actions = self._tracked_actions(runner, "src/new.py")
        self.assertIn("write", actions)
        self.assertNotIn("read", actions)

    def test_edit_alias_tracked_as_read_and_write(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "edit", {"path": "src/edit.py"})
        actions = self._tracked_actions(runner, "src/edit.py")
        self.assertIn("read", actions)
        self.assertIn("write", actions)

    def test_view_alias_tracked_as_read_only(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "view", {"path": "src/view.py"})
        actions = self._tracked_actions(runner, "src/view.py")
        self.assertIn("read", actions)
        self.assertNotIn("write", actions)

    def test_existing_create_file_still_write_only(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "create_file", {"path": "src/legacy.py"})
        actions = self._tracked_actions(runner, "src/legacy.py")
        self.assertEqual(actions, {"write"})

    def test_existing_edit_file_still_read_write(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "edit_file", {"path": "src/legacy_edit.py"})
        actions = self._tracked_actions(runner, "src/legacy_edit.py")
        self.assertEqual(actions, {"read", "write"})


if __name__ == "__main__":
    unittest.main()
