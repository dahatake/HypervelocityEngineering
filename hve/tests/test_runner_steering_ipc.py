"""test_runner_steering_ipc.py — StepRunner._poll_steering_ipc の単体テスト

T3（hve/runner.py の _poll_steering_ipc 新規追加 + _send_and_wait_with_model_call_failure_guard
拡張）に対応するテスト。既存 hve/tests/test_runner.py の import/ヘルパーパターンを踏襲する。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from console import Console
from runner import StepRunner


def _run(coro):
    return asyncio.run(coro)


def _make_runner(steering_ipc_dir: str | None) -> StepRunner:
    cfg = SDKConfig(dry_run=True, steering_ipc_dir=steering_ipc_dir)
    console = Console(verbose=False, quiet=True, show_stream=False, show_reasoning=False)
    return StepRunner(config=cfg, console=console)


class _FakeSession:
    """`send(mode="immediate")` の呼び出しを記録するだけのフェイクセッション。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str | None]] = []

    async def send(self, text: str, *, mode: str | None = None) -> str:
        self.sent.append((text, mode))
        return "msg-id"


def _write_request(ipc_dir: Path, step_id: str, text: str, epoch_ms: int) -> Path:
    path = ipc_dir / f"steering-{step_id}-{epoch_ms}.request.json"
    path.write_text(json.dumps({"text": text}), encoding="utf-8")
    return path


class TestPollSteeringIpcDisabled(unittest.TestCase):
    """steering_ipc_dir 未設定時は即座に終了する（機能無効）。"""

    def test_returns_immediately_when_dir_not_set(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(steering_ipc_dir=None)
            session = _FakeSession()
            # steering_ipc_dir=None なら polling ループへ入らず即 return するはず。
            # 即座に完了しなければ wait_for がタイムアウトして失敗する。
            await asyncio.wait_for(
                runner._poll_steering_ipc(session, "1.1"), timeout=2.0
            )
            self.assertEqual(session.sent, [])

        _run(scenario())


class TestPollSteeringIpcEnabled(unittest.TestCase):
    """steering_ipc_dir 設定時の polling 動作を検証する。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.ipc_dir = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_sends_immediate_message_and_deletes_file(self) -> None:
        """検出したリクエストファイルの text を mode="immediate" で送信し、ファイルを削除する。"""
        async def scenario() -> None:
            runner = _make_runner(steering_ipc_dir=str(self.ipc_dir))
            session = _FakeSession()
            req_path = _write_request(
                self.ipc_dir, "1.1", "Actually, stop using Synapse.", epoch_ms=1000
            )

            task = asyncio.create_task(runner._poll_steering_ipc(session, "1.1"))
            # polling 間隔(1秒)を跨いで1回のスキャンが完了するのを待つ。
            await asyncio.sleep(1.3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            self.assertEqual(
                session.sent, [("Actually, stop using Synapse.", "immediate")]
            )
            self.assertFalse(req_path.exists())

        _run(scenario())

    def test_ignores_requests_for_other_step_ids(self) -> None:
        """別 step_id 宛のリクエストファイルは無視する。"""
        async def scenario() -> None:
            runner = _make_runner(steering_ipc_dir=str(self.ipc_dir))
            session = _FakeSession()
            other_path = _write_request(
                self.ipc_dir, "2.1", "for another step", epoch_ms=1000
            )

            task = asyncio.create_task(runner._poll_steering_ipc(session, "1.1"))
            await asyncio.sleep(1.3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            self.assertEqual(session.sent, [])
            # 他 step 宛のファイルは消費されず残ったままのはず
            self.assertTrue(other_path.exists())

        _run(scenario())

    def test_processes_multiple_requests_in_epoch_order(self) -> None:
        """複数リクエストは epoch_ms 昇順（作成順）で処理される。"""
        async def scenario() -> None:
            runner = _make_runner(steering_ipc_dir=str(self.ipc_dir))
            session = _FakeSession()
            _write_request(self.ipc_dir, "1.1", "second", epoch_ms=2000)
            _write_request(self.ipc_dir, "1.1", "first", epoch_ms=1000)

            task = asyncio.create_task(runner._poll_steering_ipc(session, "1.1"))
            await asyncio.sleep(1.3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            self.assertEqual(
                [text for text, _mode in session.sent], ["first", "second"]
            )

        _run(scenario())

    def test_survives_invalid_json_file(self) -> None:
        """不正な JSON ファイルがあっても polling ループはクラッシュせず継続する。"""
        async def scenario() -> None:
            runner = _make_runner(steering_ipc_dir=str(self.ipc_dir))
            session = _FakeSession()
            bad_path = self.ipc_dir / "steering-1.1-1000.request.json"
            bad_path.write_text("{not valid json", encoding="utf-8")

            task = asyncio.create_task(runner._poll_steering_ipc(session, "1.1"))
            await asyncio.sleep(1.3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            # 不正ファイルは送信されず、削除される（text=="" のためスキップしファイルのみ除去）。
            self.assertEqual(session.sent, [])
            self.assertFalse(bad_path.exists())

        _run(scenario())


class TestSendAndWaitGuardWithSteering(unittest.TestCase):
    """_send_and_wait_with_model_call_failure_guard 拡張後の既存動作を確認する。"""

    def test_returns_send_and_wait_result_when_steering_dir_unset(self) -> None:
        """steering_ipc_dir 未設定時、既存の send_and_wait 結果がそのまま返る（回帰確認）。"""
        class _OkSession:
            async def send_and_wait(self, *_args, **_kwargs):
                return "ok-result"

        async def scenario() -> str:
            runner = _make_runner(steering_ipc_dir=None)
            return await runner._send_and_wait_with_model_call_failure_guard(
                _OkSession(), "prompt", timeout=5.0, step_id="1.1"
            )

        self.assertEqual(_run(scenario()), "ok-result")

    def test_steering_task_is_cancelled_after_main_task_completes(self) -> None:
        """steering_ipc_dir 設定時でも、メインタスク完了後に steering polling タスクが
        キャンセルされ、send_and_wait の結果に影響しないことを確認する。
        """
        class _OkSession:
            async def send_and_wait(self, *_args, **_kwargs):
                return "ok-result"

        async def scenario(tmp_dir: str) -> str:
            runner = _make_runner(steering_ipc_dir=tmp_dir)
            return await runner._send_and_wait_with_model_call_failure_guard(
                _OkSession(), "prompt", timeout=5.0, step_id="1.1"
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            self.assertEqual(_run(scenario(tmp_dir)), "ok-result")


if __name__ == "__main__":
    unittest.main()
