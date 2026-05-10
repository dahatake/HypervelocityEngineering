from __future__ import annotations

import asyncio
import importlib.util
import tempfile
import sys
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "tools"


def _load_tool_module(filename: str, module_name: str):
    target = _TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _FakeEventType:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeEvent:
    def __init__(self, etype: str, data) -> None:
        self.type = _FakeEventType(etype)
        self.data = data


class _FakeUsageData:
    def __init__(self) -> None:
        self.current_tokens = 123
        self.token_limit = 200000
        self.messages_length = 1


class _FakeSession:
    def __init__(self, emit_usage: bool = True, use_attr_data: bool = False) -> None:
        self._callback = None
        self.emit_usage = emit_usage
        self.use_attr_data = use_attr_data
        self.disconnected = False

    def on(self, callback):
        self._callback = callback

    async def send_and_wait(self, _prompt, timeout=180.0):
        if self.emit_usage and self._callback is not None:
            usage_data = (
                _FakeUsageData()
                if self.use_attr_data
                else {
                    "current_tokens": 123,
                    "token_limit": 200000,
                    "messages_length": 1,
                }
            )
            self._callback(
                _FakeEvent(
                    "session.usage_info",
                    usage_data,
                )
            )
        return {"ok": True, "timeout": timeout}

    async def disconnect(self):
        self.disconnected = True


class TestMeasureStartupTokens(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_tool_module("measure_startup_tokens.py", "measure_startup_tokens_mod")

    def test_measure_single_session_captures_usage_info(self) -> None:
        session = _FakeSession(emit_usage=True)
        result = asyncio.run(self.mod.measure_single_session(session, "hello", 30.0))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["current_tokens"], 123)
        self.assertEqual(result["token_limit"], 200000)
        self.assertTrue(session.disconnected)

    def test_measure_single_session_captures_usage_info_from_attributes(self) -> None:
        session = _FakeSession(emit_usage=True, use_attr_data=True)
        result = asyncio.run(self.mod.measure_single_session(session, "hello", 30.0))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["current_tokens"], 123)
        self.assertEqual(result["token_limit"], 200000)
        self.assertTrue(session.disconnected)

    def test_measure_single_session_marks_missing_usage(self) -> None:
        session = _FakeSession(emit_usage=False)
        result = asyncio.run(self.mod.measure_single_session(session, "hello", 30.0))
        self.assertEqual(result["status"], "usage_info_not_observed")
        self.assertIsNone(result["current_tokens"])
        self.assertTrue(session.disconnected)

    def test_write_measurement_sanitizes_label(self) -> None:
        payload = {"status": "ok"}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            path = self.mod._write_measurement(payload, output_dir, "../unsafe/label")
            self.assertEqual(path.parent.resolve(), output_dir.resolve())
            self.assertNotIn("/", path.name)
            self.assertIn("label", path.name)


class TestCompareStartupTokens(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_tool_module("compare_startup_tokens.py", "compare_startup_tokens_mod")

    def test_build_comparison(self) -> None:
        before = {
            "measurements": {
                "cli_only": {"current_tokens": 100},
                "hve": {"configurations": {"default": {"phases": {"main": {"current_tokens": 200}}}}},
            }
        }
        after = {
            "measurements": {
                "cli_only": {"current_tokens": 120},
                "hve": {"configurations": {"default": {"phases": {"main": {"current_tokens": 180}}}}},
            }
        }

        rows = self.mod.build_comparison(before, after)
        rows_by_metric = {row[0]: row for row in rows}

        self.assertEqual(rows_by_metric["cli_only"][1], 100)
        self.assertEqual(rows_by_metric["cli_only"][2], 120)
        self.assertEqual(rows_by_metric["cli_only"][3], 20)
        self.assertEqual(rows_by_metric["hve.configurations.default.phases.main"][3], -20)

    def test_build_comparison_with_missing_metrics_uses_none(self) -> None:
        before = {"measurements": {"cli_only": {"current_tokens": 100}}}
        after = {"measurements": {"hve": {"current_tokens": 200}}}
        rows = self.mod.build_comparison(before, after)
        rows_by_metric = {row[0]: row for row in rows}

        self.assertEqual(rows_by_metric["cli_only"][1], 100)
        self.assertIsNone(rows_by_metric["cli_only"][2])
        self.assertIsNone(rows_by_metric["cli_only"][3])
        self.assertIsNone(rows_by_metric["cli_only"][4])
        self.assertIsNone(rows_by_metric["hve"][1])

    def test_render_markdown(self) -> None:
        rows = [("cli_only", 100, 90, -10, -10.0)]
        markdown = self.mod.render_markdown(rows, "before", "after")
        self.assertIn("Startup Token Comparison", markdown)
        self.assertIn("`cli_only`", markdown)
        self.assertIn("-10.00%", markdown)

    def test_render_markdown_with_missing_metrics(self) -> None:
        rows = [("cli_only", 100, None, None, None)]
        markdown = self.mod.render_markdown(rows, "before", "after")
        self.assertIn("| `cli_only` | 100 | N/A | N/A | N/A |", markdown)


if __name__ == "__main__":
    unittest.main()
