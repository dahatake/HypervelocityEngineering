"""test_cloud_session_runtime.py — Runner runtime Cloud Session fallback tests."""

from __future__ import annotations

import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore  # noqa: E402
import runner  # type: ignore  # noqa: E402


class _FakeCloud:
    pass


class _Console:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)


class TestRunnerCloudSessionRuntime(unittest.IsolatedAsyncioTestCase):
    async def test_runner_helper_injects_cloud_and_streaming(self) -> None:
        calls: list[dict] = []

        class Client:
            async def create_session(self, **kwargs):
                calls.append(dict(kwargs))
                return "ok"

        with unittest.mock.patch.object(runner, "build_cloud_session_options", return_value=_FakeCloud()):
            result = await runner._create_session_with_auto_reasoning_fallback(
                Client(),
                {"model": "auto"},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="1",
                subtask_kind="main",
            )

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 1)
        self.assertIn("cloud", calls[0])
        self.assertTrue(calls[0]["streaming"])

    async def test_runner_helper_cloud_fallback_restores_explicit_streaming_false(self) -> None:
        calls: list[dict] = []
        console = _Console()

        class Client:
            async def create_session(self, **kwargs):
                calls.append(dict(kwargs))
                if "cloud" in kwargs:
                    raise TypeError("create_session() got an unexpected keyword argument 'cloud'")
                return "ok"

        with unittest.mock.patch.object(runner, "build_cloud_session_options", return_value=_FakeCloud()):
            result = await runner._create_session_with_auto_reasoning_fallback(
                Client(),
                {"model": "auto", "streaming": False},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="1",
                subtask_kind="main",
                console=console,
            )

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 2)
        self.assertIn("cloud", calls[0])
        self.assertNotIn("cloud", calls[1])
        self.assertFalse(calls[1]["streaming"])
        self.assertTrue(console.warnings)

    async def test_runner_helper_policy_blocked_raises_without_retry(self) -> None:
        calls: list[dict] = []
        console = _Console()

        class Client:
            async def create_session(self, **kwargs):
                calls.append(dict(kwargs))
                raise RuntimeError("policy_blocked")

        with self.assertRaises(RuntimeError):
            await runner._create_session_with_auto_reasoning_fallback(
                Client(),
                {"model": "auto"},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="1",
                subtask_kind="main",
                console=console,
            )

        self.assertEqual(len(calls), 1)
        self.assertTrue(console.warnings)

    async def test_runner_helper_non_policy_cloud_error_falls_back_to_local(self) -> None:
        calls: list[dict] = []
        console = _Console()

        class Client:
            async def create_session(self, **kwargs):
                calls.append(dict(kwargs))
                if "cloud" in kwargs:
                    raise RuntimeError("temporary network error")
                return "ok"

        with unittest.mock.patch.object(runner, "build_cloud_session_options", return_value=_FakeCloud()):
            result = await runner._create_session_with_auto_reasoning_fallback(
                Client(),
                {"model": "auto"},
                config=SDKConfig(cloud_session_enabled=True),
                step_id="1",
                subtask_kind="main",
                console=console,
            )

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 2)
        self.assertIn("cloud", calls[0])
        self.assertNotIn("cloud", calls[1])
        self.assertTrue(console.warnings)


if __name__ == "__main__":
    unittest.main()
