"""FR-CLI-84 / FR-CLI-85: Phase 1 リクエストのサイズ計画。

Phase 1 メインタスクの送信前にプロンプトの UTF-8 バイト数を計測し、HVE 内部予算と
照合して Phase 1 のモデル呼び出し回数を 1 回または 0 回に確定する契約を検証する。

実 Copilot セッションは一切生成しない。Fake セッションで「送信回数 0」を検証する。
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hve import runner as runner_module
from hve.config import SDKConfig
from hve.phase1_request_plan import (
    DEFAULT_PHASE1_PROMPT_BUDGET_BYTES,
    Phase1RequestPlan,
    plan_phase1_request,
)


class TestPlanPhase1Request(unittest.TestCase):
    """FR-CLI-84: 計測・予算照合・呼び出し回数決定。"""

    def test_measures_utf8_bytes_not_characters(self) -> None:
        """日本語は 1 文字 3 バイトとして計測される（文字数では超過を検出できない）。"""
        prompt = "あ" * 10
        plan = plan_phase1_request(prompt, budget_bytes=1_000)
        self.assertEqual(plan.prompt_utf8_bytes, 30)
        self.assertNotEqual(plan.prompt_utf8_bytes, len(prompt))

    def test_within_budget_plans_exactly_one_request(self) -> None:
        """予算内は `planned_phase1_requests == 1`。"""
        plan = plan_phase1_request("hello", budget_bytes=1_000)
        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.planned_phase1_requests, 1)

    def test_over_budget_plans_zero_requests(self) -> None:
        """予算超過は `planned_phase1_requests == 0`。"""
        plan = plan_phase1_request("x" * 1_001, budget_bytes=1_000)
        self.assertEqual(plan.status, "blocked")
        self.assertEqual(plan.planned_phase1_requests, 0)

    def test_exactly_at_budget_is_within_budget(self) -> None:
        """予算ちょうどは超過ではない（境界条件）。"""
        plan = plan_phase1_request("x" * 1_000, budget_bytes=1_000)
        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.planned_phase1_requests, 1)

    def test_does_not_modify_prompt(self) -> None:
        """自動切り詰め・自動要約を行わない。Plan はプロンプト本文を保持しない。"""
        plan = plan_phase1_request("x" * 5_000, budget_bytes=1_000)
        for value in vars(plan).values():
            if isinstance(value, str):
                self.assertNotIn("xxxxx", value)

    def test_component_bytes_are_recorded(self) -> None:
        """成分名ごとのバイト数を保持する。"""
        plan = plan_phase1_request(
            "あいう",
            budget_bytes=1_000,
            components=(("agent_prompt", "あ"), ("additional_prompt", "いう")),
        )
        self.assertEqual(dict(plan.component_bytes), {"agent_prompt": 3, "additional_prompt": 6})

    def test_component_bytes_empty_when_not_supplied(self) -> None:
        """成分が与えられない場合は空。捏造した内訳を作らない。"""
        plan = plan_phase1_request("abc", budget_bytes=1_000)
        self.assertEqual(plan.component_bytes, ())

    def test_default_budget_is_an_internal_constant(self) -> None:
        """予算は HVE 内部の定数。既定値が定義されている。"""
        self.assertIsInstance(DEFAULT_PHASE1_PROMPT_BUDGET_BYTES, int)
        self.assertGreater(DEFAULT_PHASE1_PROMPT_BUDGET_BYTES, 0)

    def test_plan_is_frozen(self) -> None:
        """Plan は不変。呼び出し側が判定結果を書き換えられない。"""
        plan = plan_phase1_request("abc", budget_bytes=1_000)
        self.assertIsInstance(plan, Phase1RequestPlan)
        with self.assertRaises(Exception):
            plan.status = "ready"  # type: ignore[misc]

    def test_composed_component_bytes_equal_final_prompt_bytes(self) -> None:
        """区切り・見出し・suffix を含む成分合計は最終 Prompt と一致する。"""
        prompt, components = runner_module._compose_phase1_prompt(
            agent_prefix="agent",
            step_prompt="main",
            pre_qa_context="事前確認",
            execution_mode_suffix="\n\nmode",
            tdd_suffix="\n\ntdd",
            review_suffix="\n\nreview",
        )
        plan = plan_phase1_request(
            prompt,
            budget_bytes=10_000,
            components=components,
        )
        self.assertEqual(
            sum(size for _name, size in plan.component_bytes),
            plan.prompt_utf8_bytes,
        )
        self.assertEqual(
            [name for name, _size in plan.component_bytes],
            [
                "agent_prefix",
                "pre_qa_heading",
                "pre_qa_context",
                "main_task_heading",
                "step_prompt",
                "execution_mode_suffix",
                "tdd_suffix",
                "review_suffix",
            ],
        )


class TestBudgetExceededMessage(unittest.TestCase):
    """FR-CLI-84: 通知はメタ情報のみ（FR-RTO-04 / NFR-SEC-01）。"""

    def _message(self, secret: str) -> str:
        plan = plan_phase1_request(
            secret,
            budget_bytes=10,
            components=(("additional_prompt", secret),),
        )
        return plan.describe()

    def test_message_excludes_prompt_body(self) -> None:
        """プロンプト本文を通知へ含めない。"""
        secret = "SENSITIVE-PROMPT-BODY-" + "z" * 100
        self.assertNotIn(secret, self._message(secret))
        self.assertNotIn("SENSITIVE-PROMPT-BODY", self._message(secret))

    def test_message_includes_only_metadata(self) -> None:
        """状態・バイト数・予算・予定呼び出し回数・成分別バイト数を含む。"""
        message = self._message("y" * 200)
        self.assertIn("blocked", message)
        self.assertIn("200", message)
        self.assertIn("10", message)
        self.assertIn("additional_prompt", message)

    def test_message_excludes_credentials(self) -> None:
        """認証情報を通知へ含めない。"""
        token = "ghp_" + "A" * 36
        self.assertNotIn(token, self._message(token))


class TestSingleImplementation(unittest.TestCase):
    """FR-MAINT-07: 判定と計画の実装は単一モジュールに限る。"""

    def test_runner_does_not_reimplement_budget_comparison(self) -> None:
        """runner.py が予算定数を再定義していないこと。"""
        from pathlib import Path

        runner_src = Path(__file__).resolve().parents[1] / "runner.py"
        text = runner_src.read_text(encoding="utf-8")
        self.assertNotIn("DEFAULT_PHASE1_PROMPT_BUDGET_BYTES =", text)

    def test_no_new_cli_option_is_added(self) -> None:
        """新規 CLI オプション / 環境変数を追加しない。"""
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        main_src = (root / "hve" / "__main__.py").read_text(encoding="utf-8")
        self.assertNotIn("phase1-prompt-budget", main_src)
        self.assertNotIn("HVE_PHASE1_PROMPT_BUDGET", main_src)

        plan_src = (root / "hve" / "phase1_request_plan.py").read_text(encoding="utf-8")
        self.assertNotIn("os.environ", plan_src)
        self.assertNotIn("getenv", plan_src)


class _FakeClient:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


class _FakeSession:
    def on(self, _handler):
        return None

    async def disconnect(self) -> None:
        return None


class TestRunStepBudgetGuard(unittest.TestCase):
    """FR-CLI-84: Phase 1 の送信回数と Step 終端を動的に検証する。"""

    @staticmethod
    def _console():
        console = mock.MagicMock()
        console.show_stream = False
        return console

    def test_received_over_budget_stops_before_sdk_qa_and_phase1(self) -> None:
        runner = runner_module.StepRunner(
            config=SDKConfig(auto_qa=True),
            console=self._console(),
        )
        oversized = "x" * (DEFAULT_PHASE1_PROMPT_BUDGET_BYTES + 1)
        with mock.patch(
            "hve.copilot_client_factory.create_copilot_client"
        ) as create_client, mock.patch.object(
            runner, "_create_main_session", new=mock.AsyncMock()
        ) as create_session, mock.patch.object(
            runner, "_run_pre_execution_qa", new=mock.AsyncMock()
        ) as pre_qa, mock.patch.object(
            runner,
            "_send_and_wait_with_model_call_failure_guard",
            new=mock.AsyncMock(),
        ) as phase1_send:
            result = asyncio.run(runner.run_step("2", "test", oversized))

        self.assertFalse(result)
        create_client.assert_not_called()
        create_session.assert_not_awaited()
        pre_qa.assert_not_awaited()
        phase1_send.assert_not_awaited()

    def test_dry_run_keeps_existing_no_sdk_success_for_large_prompt(self) -> None:
        runner = runner_module.StepRunner(
            config=SDKConfig(dry_run=True),
            console=self._console(),
        )
        oversized = "x" * (DEFAULT_PHASE1_PROMPT_BUDGET_BYTES + 1)
        with mock.patch(
            "hve.copilot_client_factory.create_copilot_client"
        ) as create_client:
            result = asyncio.run(runner.run_step("2", "test", oversized))

        self.assertTrue(result)
        create_client.assert_not_called()

    def test_deterministic_prefix_over_budget_stops_before_session_and_pre_qa(self) -> None:
        console = self._console()
        runner = runner_module.StepRunner(
            config=SDKConfig(auto_qa=True, tool_search=False),
            console=console,
        )
        client = _FakeClient()
        oversized_agent_prompt = "a" * DEFAULT_PHASE1_PROMPT_BUDGET_BYTES
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "hve.copilot_client_factory.create_copilot_client",
            return_value=client,
        ), mock.patch(
            "hve.prompt_loader.load_prompt", return_value=oversized_agent_prompt
        ), mock.patch.object(
            runner, "_create_main_session", new=mock.AsyncMock()
        ) as create_session, mock.patch.object(
            runner, "_run_pre_execution_qa", new=mock.AsyncMock()
        ) as pre_qa, mock.patch.object(
            runner,
            "_send_and_wait_with_model_call_failure_guard",
            new=mock.AsyncMock(),
        ) as phase1_send, mock.patch.object(
            runner_module, "_ensure_step_work_dir", return_value=Path(td)
        ):
            result = asyncio.run(
                runner.run_step("2", "test", "small", custom_agent="Fake-Agent")
            )

        self.assertFalse(result)
        self.assertEqual(client.start_calls, 1)
        self.assertEqual(client.stop_calls, 1)
        create_session.assert_not_awaited()
        pre_qa.assert_not_awaited()
        phase1_send.assert_not_awaited()
        console.step_end.assert_called_once()
        self.assertEqual(console.step_end.call_args.args[:2], ("2", "failed"))

    def test_final_over_budget_records_failed_step_end_without_phase1_send(self) -> None:
        console = self._console()
        runner = runner_module.StepRunner(
            config=SDKConfig(auto_qa=True, tool_search=False),
            console=console,
        )
        client = _FakeClient()
        session = _FakeSession()
        large_pre_qa = "q" * DEFAULT_PHASE1_PROMPT_BUDGET_BYTES
        with tempfile.TemporaryDirectory() as td, mock.patch(
            "hve.copilot_client_factory.create_copilot_client",
            return_value=client,
        ), mock.patch.object(
            runner,
            "_create_main_session",
            new=mock.AsyncMock(return_value=session),
        ), mock.patch.object(
            runner,
            "_run_pre_execution_qa",
            new=mock.AsyncMock(return_value=large_pre_qa),
        ), mock.patch.object(
            runner,
            "_send_and_wait_with_model_call_failure_guard",
            new=mock.AsyncMock(),
        ) as phase1_send, mock.patch.object(
            runner_module, "_ensure_step_work_dir", return_value=Path(td)
        ):
            result = asyncio.run(runner.run_step("2", "test", "small"))

        self.assertFalse(result)
        phase1_send.assert_not_awaited()
        console.step_end.assert_called_once()
        self.assertEqual(console.step_end.call_args.args[:2], ("2", "failed"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
