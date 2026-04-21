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

    def test_track_tool_files_edit_file_calls_file_io_read_write(self) -> None:
        runner = self._make_runner()
        runner._track_tool_files("1", "edit_file", {"path": "src/main.py"})
        runner.console.track_file.assert_any_call("1", os.path.normpath("src/main.py"), "read")
        runner.console.track_file.assert_any_call("1", os.path.normpath("src/main.py"), "write")
        runner.console.file_io.assert_any_call("1", os.path.normpath("src/main.py"), "read")
        runner.console.file_io.assert_any_call("1", os.path.normpath("src/main.py"), "write")


if __name__ == "__main__":
    unittest.main()
