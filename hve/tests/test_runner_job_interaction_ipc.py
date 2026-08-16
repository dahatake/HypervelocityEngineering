"""test_runner_job_interaction_ipc.py — FR-GUI-12 の実行側受入テスト。

`queue` / `steer` / `stop_and_send` の SDK 呼び出し写像、`stop_and_send` 後の
再待機、ACK が要求本文を複製しないこと、および原子的 claim による重複処理の
防止を固定する。実 SDK / モデル呼び出しは行わない。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import runner as runner_module  # noqa: E402
from config import SDKConfig  # noqa: E402
from console import Console  # noqa: E402
from runner import StepRunner  # noqa: E402

from hve.job_interaction_ipc import (  # noqa: E402
    ACTION_QUEUE,
    ACTION_STEER,
    ACTION_STOP_AND_SEND,
    claim_request,
    list_acks,
    read_request,
    write_request,
)

_SECRET = "stop using Synapse token=ghp_MustNotLeak"


def _run(coro):
    return asyncio.run(coro)


def _make_runner(ipc_dir: Optional[str]) -> StepRunner:
    cfg = SDKConfig(dry_run=True, steering_ipc_dir=ipc_dir)
    console = Console(verbose=False, quiet=True, show_stream=False, show_reasoning=False)
    return StepRunner(config=cfg, console=console)


class _FakeSession:
    """`send` / `abort` / `send_and_wait` を記録するフェイクセッション。"""

    def __init__(self) -> None:
        self.sent: List[Tuple[str, Optional[str]]] = []
        self.aborted = 0
        self.turns: List[str] = []
        self.send_error: Optional[Exception] = None
        self.main_turn_error: Optional[Exception] = None
        self.on_redirect_turn: Optional[Any] = None
        self._released = asyncio.Event()

    async def send(self, text: str, *, mode: Optional[str] = None) -> str:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append((text, mode))
        return "msg-id"

    async def abort(self) -> None:
        self.aborted += 1
        self._released.set()

    async def send_and_wait(self, prompt: str, *, timeout: float = 60.0, **_kw: Any):
        self.turns.append(prompt)
        if self.aborted == 0:
            # 主タスクは abort されるまで idle にならない。
            await self._released.wait()
            if self.main_turn_error is not None:
                raise self.main_turn_error
            return "main-partial"
        if self.on_redirect_turn is not None:
            self.on_redirect_turn()
        return f"redirect:{prompt}"


async def _drain_once(runner: StepRunner, session: Any, step_id: str, *, seconds: float = 0.4) -> None:
    """polling タスクを短時間だけ動かして 1 巡させる。"""
    task = asyncio.create_task(runner._poll_steering_ipc(session, step_id))
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


class _IpcTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.ipc_dir = Path(self._tmpdir.name)
        self._original_interval = runner_module._STEERING_POLL_INTERVAL_SECONDS
        runner_module._STEERING_POLL_INTERVAL_SECONDS = 0.02

    def tearDown(self) -> None:
        runner_module._STEERING_POLL_INTERVAL_SECONDS = self._original_interval
        self._tmpdir.cleanup()


class TestActionMapping(_IpcTestBase):
    def test_queue_is_sent_as_enqueue(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            write_request(self.ipc_dir, "1.1", "later", action=ACTION_QUEUE)
            await _drain_once(runner, session, "1.1")
            self.assertEqual(session.sent, [("later", "enqueue")])
            self.assertEqual(session.aborted, 0)

        _run(scenario())

    def test_steer_is_sent_as_immediate(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            write_request(self.ipc_dir, "1.1", "now", action=ACTION_STEER)
            await _drain_once(runner, session, "1.1")
            self.assertEqual(session.sent, [("now", "immediate")])
            self.assertEqual(session.aborted, 0)

        _run(scenario())

    def test_stop_and_send_aborts_and_defers_the_text_to_a_new_turn(self) -> None:
        """`stop_and_send` は abort のみを行い、本文は再待機側へ引き渡す。"""

        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            path = write_request(
                self.ipc_dir, "1.1", "redirect me", action=ACTION_STOP_AND_SEND
            )
            request = read_request(path)
            assert request is not None
            await _drain_once(runner, session, "1.1")
            self.assertEqual(session.aborted, 1)
            self.assertEqual(session.sent, [])
            self.assertEqual(
                runner._pop_pending_job_redirect("1.1"),
                (request.request_id, "redirect me"),
            )
            self.assertIsNone(runner._pop_pending_job_redirect("1.1"))

        _run(scenario())

    def test_legacy_text_only_request_is_treated_as_steer(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            legacy = self.ipc_dir / "steering-1.1-1000.request.json"
            legacy.write_text(json.dumps({"text": "legacy"}), encoding="utf-8")
            await _drain_once(runner, session, "1.1")
            self.assertEqual(session.sent, [("legacy", "immediate")])

        _run(scenario())

    def test_requests_for_other_steps_are_ignored(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            other = write_request(self.ipc_dir, "2.1", "not mine", action=ACTION_STEER)
            await _drain_once(runner, session, "1.1")
            self.assertEqual(session.sent, [])
            self.assertTrue(other.exists())

        _run(scenario())

    def test_requests_are_processed_in_creation_order(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            for name in ("first", "second", "third"):
                write_request(self.ipc_dir, "1.1", name, action=ACTION_STEER)
            await _drain_once(runner, session, "1.1")
            self.assertEqual([t for t, _ in session.sent], ["first", "second", "third"])

        _run(scenario())

    def test_disabled_when_ipc_dir_is_unset(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(None)
            session = _FakeSession()
            await asyncio.wait_for(runner._poll_steering_ipc(session, "1.1"), timeout=2.0)
            self.assertEqual(session.sent, [])

        _run(scenario())


class TestAcknowledgement(_IpcTestBase):
    def test_accepted_ack_is_written_without_the_prompt(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            path = write_request(self.ipc_dir, "1.1", _SECRET, action=ACTION_STEER)
            request = read_request(path)
            assert request is not None
            await _drain_once(runner, session, "1.1")
            acks = {a["request_id"]: a for a in list_acks(self.ipc_dir)}
            self.assertIn(request.request_id, acks)
            self.assertEqual(acks[request.request_id]["status"], "accepted")
            for ack_file in self.ipc_dir.glob("ack-*.json"):
                self.assertNotIn(_SECRET, ack_file.read_text(encoding="utf-8"))

        _run(scenario())

    def test_failed_send_is_acknowledged_and_polling_continues(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            session.send_error = RuntimeError("session closed")
            first = write_request(self.ipc_dir, "1.1", "boom", action=ACTION_STEER)
            request = read_request(first)
            assert request is not None
            await _drain_once(runner, session, "1.1")
            acks = {a["request_id"]: a for a in list_acks(self.ipc_dir)}
            self.assertEqual(acks[request.request_id]["status"], "failed")

            # 失敗後も polling は継続し、後続要求を処理できる。
            session.send_error = None
            write_request(self.ipc_dir, "1.1", "next", action=ACTION_STEER)
            await _drain_once(runner, session, "1.1")
            self.assertEqual(session.sent, [("next", "immediate")])

        _run(scenario())

    def test_malformed_request_is_removed_and_polling_continues(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            broken = self.ipc_dir / "steering-1.1-1000.request.json"
            broken.write_text("{not json", encoding="utf-8")
            write_request(self.ipc_dir, "1.1", "good", action=ACTION_STEER)
            await _drain_once(runner, session, "1.1")
            self.assertFalse(broken.exists())
            self.assertEqual(session.sent, [("good", "immediate")])

        _run(scenario())


class TestClaimSemantics(_IpcTestBase):
    def test_already_claimed_request_is_not_processed_again(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            path = write_request(self.ipc_dir, "1.1", "once", action=ACTION_STEER)
            self.assertIsNotNone(claim_request(path))
            await _drain_once(runner, session, "1.1")
            self.assertEqual(session.sent, [])

        _run(scenario())

    def test_each_request_is_consumed_exactly_once(self) -> None:
        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            write_request(self.ipc_dir, "1.1", "only", action=ACTION_STEER)
            await _drain_once(runner, session, "1.1", seconds=0.5)
            self.assertEqual(session.sent, [("only", "immediate")])

        _run(scenario())


class TestGuardRedirect(_IpcTestBase):
    def test_stop_and_send_becomes_the_main_response(self) -> None:
        """abort で主タスクが復帰しても、指示テキストの応答を待って主応答にする。"""

        async def scenario() -> str:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            write_request(self.ipc_dir, "1.1", "do this instead", action=ACTION_STOP_AND_SEND)
            return await runner._send_and_wait_with_model_call_failure_guard(
                session, "main prompt", timeout=5.0, step_id="1.1"
            )

        result = _run(scenario())
        self.assertEqual(result, "redirect:do this instead")

    def test_without_redirect_the_main_result_is_returned(self) -> None:
        class _OkSession:
            async def send_and_wait(self, *_args, **_kwargs):
                return "ok-result"

        async def scenario() -> str:
            runner = _make_runner(str(self.ipc_dir))
            return await runner._send_and_wait_with_model_call_failure_guard(
                _OkSession(), "main prompt", timeout=5.0, step_id="1.1"
            )

        self.assertEqual(_run(scenario()), "ok-result")

    def test_stop_and_send_is_acknowledged_only_after_the_new_turn_is_sent(self) -> None:
        """abort 成功だけで accepted にせず、指示が実際に送信された時点で ACK する。"""

        async def until_abort() -> str:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            write_request(self.ipc_dir, "1.1", "redirect me", action=ACTION_STOP_AND_SEND)
            await _drain_once(runner, session, "1.1")
            self.assertEqual(session.aborted, 1)
            # 送信前は accepted を主張しない。
            self.assertEqual(list_acks(self.ipc_dir), [])
            return await runner._drain_pending_job_redirects(
                session, "1.1", "main-partial", timeout=5.0
            )

        result = _run(until_abort())
        self.assertEqual(result, "redirect:redirect me")
        acks = list_acks(self.ipc_dir)
        self.assertEqual([a["status"] for a in acks], ["accepted"])
        self.assertEqual(acks[0]["action"], ACTION_STOP_AND_SEND)

    def test_dropped_stop_and_send_is_acknowledged_as_failed(self) -> None:
        """主タスクが例外復帰して指示を送れなかった場合、accepted を残さない。"""

        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()
            session.main_turn_error = RuntimeError("Session error: aborted")
            write_request(self.ipc_dir, "1.1", "lost instruction", action=ACTION_STOP_AND_SEND)
            with self.assertRaises(RuntimeError):
                await runner._send_and_wait_with_model_call_failure_guard(
                    session, "main prompt", timeout=5.0, step_id="1.1"
                )

        _run(scenario())
        acks = list_acks(self.ipc_dir)
        self.assertEqual([a["status"] for a in acks], ["failed"])
        for ack_file in self.ipc_dir.glob("ack-*.json"):
            self.assertNotIn("lost instruction", ack_file.read_text(encoding="utf-8"))

    def test_model_call_failure_during_the_redirect_turn_fails_fast(self) -> None:
        """再待機ターンでも model.call_failure の閾値超過で即失敗する。"""

        async def scenario() -> None:
            runner = _make_runner(str(self.ipc_dir))
            session = _FakeSession()

            def _raise_call_failures() -> None:
                runner._model_call_failure_counts["1.1"] = 3
                event = runner._model_call_failure_events.get("1.1")
                if event is not None:
                    event.set()

            session.on_redirect_turn = _raise_call_failures
            write_request(self.ipc_dir, "1.1", "keep going", action=ACTION_STOP_AND_SEND)
            with self.assertRaises(RuntimeError) as ctx:
                await runner._send_and_wait_with_model_call_failure_guard(
                    session, "main prompt", timeout=5.0, step_id="1.1"
                )
            self.assertIn("model.call_failure", str(ctx.exception))

        _run(scenario())


if __name__ == "__main__":
    unittest.main()
