"""test_session_context_tier.py — context_tier のセッション注入テスト。

`_create_session_with_auto_reasoning_fallback`（runner / orchestrator 双方）が
SDKConfig.context_tier を create_session へ注入すること、未指定時は注入しないこと、
未サポート SDK（TypeError）時に context_tier を剥がして再試行することを検証する。
"""

from __future__ import annotations

import os
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # type: ignore  # noqa: E402
import runner  # type: ignore  # noqa: E402
import orchestrator  # type: ignore  # noqa: E402


class _RecordingClient:
    """create_session の呼び出し kwargs を記録する fake client。"""

    def __init__(self, *, fail_on_context_tier: bool = False) -> None:
        self.calls: list[dict] = []
        self._fail_on_context_tier = fail_on_context_tier

    async def create_session(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self._fail_on_context_tier and "context_tier" in kwargs:
            raise TypeError(
                "create_session() got an unexpected keyword argument 'context_tier'"
            )
        return "session"


class _ContextTierInjectionMixin:
    """runner / orchestrator 共通の検証ロジック。サブクラスで module を指定する。"""

    module = None  # type: ignore[assignment]

    async def _call(self, client, config):
        return await self.module._create_session_with_auto_reasoning_fallback(
            client,
            {"model": "auto"},
            config=config,
            step_id="s1",
            subtask_kind="main",
        )

    async def test_injects_long_context(self) -> None:
        client = _RecordingClient()
        result = await self._call(client, SDKConfig(context_tier="long_context"))
        self.assertEqual(result, "session")
        self.assertEqual(client.calls[0].get("context_tier"), "long_context")

    async def test_injects_default(self) -> None:
        client = _RecordingClient()
        await self._call(client, SDKConfig(context_tier="default"))
        self.assertEqual(client.calls[0].get("context_tier"), "default")

    async def test_omits_when_none(self) -> None:
        client = _RecordingClient()
        await self._call(client, SDKConfig(context_tier=None))
        self.assertNotIn("context_tier", client.calls[0])

    async def test_strips_on_unsupported_sdk(self) -> None:
        client = _RecordingClient(fail_on_context_tier=True)
        result = await self._call(client, SDKConfig(context_tier="long_context"))
        self.assertEqual(result, "session")
        # 1回目は context_tier 付きで TypeError → 2回目は剥がして成功
        self.assertIn("context_tier", client.calls[0])
        self.assertNotIn("context_tier", client.calls[1])


class TestRunnerContextTierInjection(_ContextTierInjectionMixin, unittest.IsolatedAsyncioTestCase):
    module = runner


class TestOrchestratorContextTierInjection(_ContextTierInjectionMixin, unittest.IsolatedAsyncioTestCase):
    module = orchestrator


if __name__ == "__main__":
    unittest.main()
