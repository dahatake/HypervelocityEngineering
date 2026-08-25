"""test_runner_pre_qa.py — Phase 0 (事前 QA) 実装の静的検証テスト"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from console import Console
from qa_merger import QADocument, QAMerger, QAQuestion
from workiq import WorkIQQueryResult
import runner as runner_module


class TestRunnerPreQaSourceInspection(unittest.TestCase):
    """runner.py のソースコードを検査し、Phase 0 実装が含まれることを確認する。"""

    def _get_runner_source(self) -> str:
        runner_path = os.path.join(os.path.dirname(__file__), "..", "runner.py")
        with open(runner_path, encoding="utf-8") as f:
            return f.read()

    def test_pre_execution_qa_prompt_imported(self) -> None:
        src = self._get_runner_source()
        self.assertIn("PRE_EXECUTION_QA_PROMPT_V2", src)

    def test_run_pre_execution_qa_method_defined(self) -> None:
        src = self._get_runner_source()
        self.assertIn("_run_pre_execution_qa", src)

    def test_phase0_called_before_phase1(self) -> None:
        src = self._get_runner_source()
        idx_phase0 = src.find("await self._run_pre_execution_qa(")
        idx_phase1 = src.find('"メインタスク"')
        self.assertGreater(idx_phase0, 0, "_run_pre_execution_qa 呼び出しが見つかりません")
        self.assertGreater(idx_phase1, 0, "メインタスク phase start が見つかりません")
        self.assertLess(
            idx_phase0, idx_phase1,
            "Phase 0 (事前 QA) は Phase 1 (メインタスク) より前に配置されなければなりません"
        )

    def test_pre_execution_qa_suffix_constant_defined(self) -> None:
        src = self._get_runner_source()
        self.assertIn("_PRE_EXECUTION_QA_SUFFIX", src)
        self.assertIn("pre-execution-qa.md", src)

    def test_pre_qa_context_injected_into_main_prompt(self) -> None:
        src = self._get_runner_source()
        self.assertIn("事前確認済みの前提条件・補足情報", src)
        self.assertIn("_injected_prompt", src)

    def test_context_injection_uses_sdkconfig_limit(self) -> None:
        src = self._get_runner_source()
        self.assertIn("context_injection_max_chars", src)
        self.assertNotIn("_MAX_CONTEXT_INJECTION_LENGTH", src)


# ---------------------------------------------------------------------------
# FR-QA-03: 事前 QA 保存成功後の AKM dispatch hook
# ---------------------------------------------------------------------------

class TestPreQaAkmDispatch(unittest.TestCase):
    """FR-QA-03: 保存検証成功後のファイル単位 dispatch、0 問スキップ、AKM 再帰防止。

    production の dispatch hook（想定: _dispatch_qa_akm_sync 等）を
    fake/mock 経由で検証する動的テスト。
    """

    @staticmethod
    def _doc() -> QADocument:
        return QADocument(
            title="事前 QA",
            status="回答待ち",
            header_fields=[("状態", "回答待ち")],
            questions=[QAQuestion(no=1, question="方式は？", default_answer="A")],
        )

    def _call(self, *, workflow_id: str = "aas", dispatcher=None, doc=None):
        persist = getattr(runner_module, "_persist_answered_qa_and_dispatch")
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "answered.md"
            content = persist(
                doc=doc if doc is not None else self._doc(),
                user_answers_raw="",
                use_defaults=True,
                output_path=path,
                workflow_id=workflow_id,
                dispatcher=dispatcher,
            )
            return content, path.exists()

    def test_dispatch_called_after_save_success(self) -> None:
        submitted: list[Path] = []
        content, exists = self._call(dispatcher=submitted.append)
        self.assertTrue(exists)
        self.assertIn("回答済み", content)
        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0].name, "answered.md")

    def test_dispatch_not_called_on_zero_questions(self) -> None:
        submitted: list[Path] = []
        content, exists = self._call(
            dispatcher=submitted.append,
            doc=QADocument(questions=[]),
        )
        self.assertEqual(content, "")
        self.assertFalse(exists)
        self.assertEqual(submitted, [])

    def test_dispatch_not_called_on_save_failure(self) -> None:
        submitted: list[Path] = []
        with patch.object(QAMerger, "save_merged", return_value=False):
            with self.assertRaises(RuntimeError):
                self._call(dispatcher=submitted.append)
        self.assertEqual(submitted, [])

    def test_dispatch_returns_without_waiting_for_completion(self) -> None:
        class NonWaitingDispatcher:
            def __init__(self) -> None:
                self.paths: list[Path] = []

            def submit(self, path: Path) -> None:
                self.paths.append(path)

        dispatcher = NonWaitingDispatcher()
        content, _ = self._call(dispatcher=dispatcher.submit)
        self.assertTrue(content)
        self.assertEqual(len(dispatcher.paths), 1)

    def test_akm_workflow_does_not_dispatch(self) -> None:
        submitted: list[Path] = []
        content, exists = self._call(
            workflow_id="akm",
            dispatcher=submitted.append,
        )
        self.assertTrue(content)
        self.assertTrue(exists)
        self.assertEqual(submitted, [])


class _PreQaWorkiqHarness:
    """事前 QA の Work IQ 経路を実行するための共通ハーネス。"""

    _QUESTIONNAIRE = """\
# 事前 QA

[Q01]
- 分類項目: 正本
- 重要度: 最重要
- 質問文: 正本はどれですか。
- 選択肢:
  A. QA
  B. カタログ
- 未回答時の既定値候補: A. QA
- 既定値候補の理由: 未回答を事実化しないため
- 未回答のまま進めた場合の影響: QAを正とする

[Q02]
- 分類項目: SoR
- 重要度: 最重要
- 質問文: SoR根拠はありますか。
- 選択肢:
  A. ある
  B. ない
- 未回答時の既定値候補: B. ない
- 既定値候補の理由: 根拠未確認のため
- 未回答のまま進めた場合の影響: TBDで進める

[Q03]
- 分類項目: 投稿先
- 重要度: 高
- 質問文: 投稿先はありますか。
- 選択肢:
  A. ある
  B. ない
- 未回答時の既定値候補: B. ない
- 既定値候補の理由: 投稿先未確認のため
- 未回答のまま進めた場合の影響: ローカル記録のみ
"""

    class _FakeSession:
        def __init__(self, questionnaire: str) -> None:
            self.questionnaire = questionnaire
            self.handlers: list = []
            self.rpc = SimpleNamespace(
                mcp=SimpleNamespace(
                    list=mock.AsyncMock(return_value=SimpleNamespace(
                        servers=[SimpleNamespace(name="_hve_workiq")],
                    ))
                )
            )

        def on(self, handler) -> None:
            self.handlers.append(handler)

        async def send_and_wait(self, _prompt: str, *, timeout: float):
            del timeout
            return SimpleNamespace(content=self.questionnaire, data=None)

        async def disconnect(self) -> None:
            return None

        def emit_internal_workiq_event(self) -> None:
            event = SimpleNamespace(
                type=SimpleNamespace(value="tool.execution_start"),
                data=SimpleNamespace(
                    mcp_tool_name="ask",
                    mcp_server_name="_hve_workiq",
                    arguments={"question": "redacted"},
                ),
            )
            for handler in self.handlers:
                handler(event)

    @staticmethod
    def _config(run_id: str) -> SDKConfig:
        return SDKConfig(
            model="gpt-5.5",
            qa_model="gpt-5.5",
            run_id=run_id,
            workiq_enabled=True,
            workiq_qa_enabled=True,
            workiq_max_draft_questions=3,
            qa_answer_mode="autopilot",
            unattended=True,
        )

    async def _run_case(
        self,
        repo_root: Path,
        *,
        run_id: str,
        responses: dict[int, str],
        verified_questions: set[int],
        submitted: list[Path],
        console: Console | None = None,
        observed_tools: dict[int, str] | None = None,
    ) -> tuple[str, Path, Path]:
        runner = runner_module.StepRunner(
            config=self._config(run_id),
            console=console or Console(verbose=False, quiet=True),
            qa_akm_dispatcher=submitted.append,
        )
        session = self._FakeSession(self._QUESTIONNAIRE)

        async def fake_query(_session, query: str, timeout: float):
            del _session, timeout
            question_no = next(
                no for no in (1, 2, 3) if f"- No: Q{no}" in query
            )
            if question_no in verified_questions:
                session.emit_internal_workiq_event()
            elif observed_tools and question_no in observed_tools:
                runner._toolsearch_called_tools.append(observed_tools[question_no])
            return WorkIQQueryResult(content=responses[question_no])

        original_cwd = Path.cwd()
        try:
            os.chdir(repo_root)
            with mock.patch.object(runner_module, "is_workiq_available", return_value=True), \
                 mock.patch.object(
                     runner_module,
                     "_create_session_with_auto_reasoning_fallback",
                     new=mock.AsyncMock(return_value=session),
                 ), \
                 mock.patch.object(runner_module, "query_workiq_detailed", new=fake_query):
                context = await runner._run_pre_execution_qa(
                    session=SimpleNamespace(),
                    client=SimpleNamespace(),
                    step_id="1",
                    original_prompt="AAS Step.1 テスト",
                    custom_agent="Arch-ApplicationAnalytics",
                    workflow_id="aas",
                    current_phase=1,
                    total_phases=2,
                )
        finally:
            os.chdir(original_cwd)

        answered_path = repo_root / "qa" / f"{run_id}-1-pre-execution-qa.md"
        draft_path = repo_root / "qa" / f"{run_id}-1-workiq-pre-qa-draft.md"
        self.assertTrue(answered_path.is_file())
        self.assertTrue(draft_path.is_file())
        return context, answered_path, draft_path


class TestPreQaWorkiqRoundTrip(_PreQaWorkiqHarness, unittest.TestCase):
    """FR-QA-03: verified Work IQ 結果だけを回答済み QA へ統合する。"""

    def test_only_verified_found_result_is_merged_and_saved_round_trip(self) -> None:
        submitted: list[Path] = []

        import asyncio

        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            context, answered_path, draft_path = asyncio.run(self._run_case(
                repo_root,
                run_id="pre-qa-workiq-roundtrip",
                responses={
                    1: "STATUS: NOT_FOUND\n関連情報は見つかりませんでした。",
                    2: (
                        "STATUS: FOUND\n"
                        "| 種別 | 情報ソース | 日時 | パス/場所 | 関連観点 |\n"
                        "|---|---|---:|---|---|\n"
                        "| ファイル | 要件定義書 | 2026-08-15 | SharePoint | SoR根拠 |"
                    ),
                    3: "STATUS: NOT_FOUND\n関連情報は見つかりませんでした。",
                },
                verified_questions={2},
                submitted=submitted,
            ))
            answered_doc = QAMerger.parse_qa_file(answered_path)
            draft = draft_path.read_text(encoding="utf-8")

        self.assertEqual([q.no for q in answered_doc.questions], [1, 2, 3])
        self.assertTrue(all((q.user_answer or "").strip() for q in answered_doc.questions))
        self.assertEqual(answered_doc.questions[0].workiq_answer, "")
        self.assertIn("STATUS: FOUND", answered_doc.questions[1].workiq_answer)
        self.assertEqual(answered_doc.questions[2].workiq_answer, "")
        self.assertIn("（Work IQ: ツール呼び出しなし）", draft)
        self.assertIn("STATUS: NOT_FOUND", draft)
        self.assertIn("## 事前 QA 確認済み情報", context)
        self.assertEqual(len(submitted), 1)

    def test_partial_is_merged_but_unavailable_and_unverified_found_are_draft_only(self) -> None:
        import asyncio

        submitted: list[Path] = []
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            _, answered_path, draft_path = asyncio.run(self._run_case(
                repo_root,
                run_id="pre-qa-workiq-statuses",
                responses={
                    1: "STATUS: UNAVAILABLE\nツール未接続",
                    2: "STATUS: PARTIAL\n一部の一次情報だけ確認",
                    3: "STATUS: FOUND\n本文はあるが tool event 未確認",
                },
                verified_questions={1, 2},
                submitted=submitted,
            ))
            answered_doc = QAMerger.parse_qa_file(answered_path)
            draft = draft_path.read_text(encoding="utf-8")

        self.assertEqual(answered_doc.questions[0].workiq_answer, "")
        self.assertIn("STATUS: PARTIAL", answered_doc.questions[1].workiq_answer)
        self.assertEqual(answered_doc.questions[2].workiq_answer, "")
        self.assertIn("STATUS: UNAVAILABLE", draft)
        self.assertIn("tool event 未確認", draft)
        self.assertEqual(len(submitted), 1)


class _RecordingConsole(Console):
    """warning / status の呼び出しを記録する Console。"""

    def __init__(self) -> None:
        super().__init__(verbose=False, quiet=True)
        self.warnings: list[str] = []
        self.statuses: list[str] = []

    def warning(self, message: str, *args, **kwargs) -> None:  # type: ignore[override]
        self.warnings.append(str(message))

    def status(self, message: str, *args, **kwargs) -> None:  # type: ignore[override]
        self.statuses.append(str(message))


class TestPreQaWorkiqDetectionMissWarning(_PreQaWorkiqHarness, unittest.TestCase):
    """FR-QA-06: tool 実行未確認を成功記号で報告しない。"""

    _FOUND_BODY = "STATUS: FOUND\n機微な一次情報の本文がここに入る"
    _NOT_FOUND_BODY = "STATUS: NOT_FOUND\n関連情報は見つかりませんでした。"

    def _run(
        self,
        *,
        run_id: str,
        responses: dict[int, str],
        verified_questions: set[int],
        observed_tools: dict[int, str] | None = None,
    ) -> _RecordingConsole:
        import asyncio

        console = _RecordingConsole()
        with tempfile.TemporaryDirectory() as td:
            asyncio.run(self._run_case(
                Path(td),
                run_id=run_id,
                responses=responses,
                verified_questions=verified_questions,
                submitted=[],
                console=console,
                observed_tools=observed_tools,
            ))
        return console

    @staticmethod
    def _detection_warnings(console: _RecordingConsole) -> list[str]:
        return [w for w in console.warnings if "確認できませんでした" in w]

    def test_warns_when_found_status_without_tool_evidence(self) -> None:
        console = self._run(
            run_id="pre-qa-workiq-miss-found",
            responses={
                1: self._NOT_FOUND_BODY,
                2: self._FOUND_BODY,
                3: "STATUS: PARTIAL\n一部だけ確認",
            },
            verified_questions=set(),
        )
        warnings = self._detection_warnings(console)
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any("Q2" in w for w in warnings))
        self.assertTrue(any("Q3" in w for w in warnings))

    def test_does_not_warn_for_not_found_status(self) -> None:
        console = self._run(
            run_id="pre-qa-workiq-miss-notfound",
            responses={
                1: self._NOT_FOUND_BODY,
                2: "STATUS: UNAVAILABLE\nツール未接続",
                3: "本文だけで status なし",
            },
            verified_questions=set(),
        )
        self.assertEqual(self._detection_warnings(console), [])

    def test_warning_includes_observed_tool_names(self) -> None:
        console = self._run(
            run_id="pre-qa-workiq-miss-tools",
            responses={
                1: self._NOT_FOUND_BODY,
                2: self._FOUND_BODY,
                3: self._NOT_FOUND_BODY,
            },
            verified_questions=set(),
            observed_tools={2: "retrieve"},
        )
        warnings = self._detection_warnings(console)
        self.assertEqual(len(warnings), 1)
        self.assertIn("retrieve", warnings[0])

    def test_warning_includes_diagnostic_command(self) -> None:
        console = self._run(
            run_id="pre-qa-workiq-miss-diag",
            responses={
                1: self._NOT_FOUND_BODY,
                2: self._FOUND_BODY,
                3: self._NOT_FOUND_BODY,
            },
            verified_questions=set(),
        )
        self.assertIn("python -m hve workiq-doctor", self._detection_warnings(console)[0])

    def test_warning_excludes_response_body(self) -> None:
        console = self._run(
            run_id="pre-qa-workiq-miss-body",
            responses={
                1: self._NOT_FOUND_BODY,
                2: self._FOUND_BODY,
                3: self._NOT_FOUND_BODY,
            },
            verified_questions=set(),
        )
        for warning in self._detection_warnings(console):
            self.assertNotIn("機微な一次情報の本文", warning)

    def test_zero_merge_summary_is_warning(self) -> None:
        console = self._run(
            run_id="pre-qa-workiq-miss-summary",
            responses={
                1: self._NOT_FOUND_BODY,
                2: self._FOUND_BODY,
                3: self._NOT_FOUND_BODY,
            },
            verified_questions=set(),
        )
        summary_status = [s for s in console.statuses if "回答案を統合" in s]
        summary_warn = [w for w in console.warnings if "回答案を統合" in w]
        self.assertEqual(summary_status, [])
        self.assertEqual(len(summary_warn), 1)
        self.assertNotIn("✅", summary_warn[0])

    def test_nonzero_merge_summary_stays_status(self) -> None:
        console = self._run(
            run_id="pre-qa-workiq-merge-summary",
            responses={
                1: self._NOT_FOUND_BODY,
                2: self._FOUND_BODY,
                3: self._NOT_FOUND_BODY,
            },
            verified_questions={2},
        )
        summary_status = [s for s in console.statuses if "回答案を統合" in s]
        summary_warn = [w for w in console.warnings if "回答案を統合" in w]
        self.assertEqual(len(summary_status), 1)
        self.assertIn("✅", summary_status[0])
        self.assertEqual(summary_warn, [])


if __name__ == "__main__":
    unittest.main()

