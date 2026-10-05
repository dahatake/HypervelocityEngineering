"""FR-KD-13: 実行後の不明点調査の受入テスト（AC-017）。"""

from __future__ import annotations

import asyncio
import inspect
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List
from unittest import mock

import pytest

from hve import knowledge_discovery as kd
from hve import knowledge_files as kf
from hve import runner as runner_module
from hve.config import SDKConfig
from hve.console import Console
from hve.prompts import QA_PROMPT_V2
from hve.qa_merger import QAMerger

_QUESTIONNAIRE = """\
[Q01]
- 分類項目: 更新方針
- 重要度: 最重要
- 質問文: 既存成果物の更新方針は？
- 選択肢:
  A. 差分マージ
  B. 全面再生成
- 未回答時の既定値候補: B. 全面再生成
- 既定値候補の理由: 安全側
- 未回答のまま進めた場合の影響: 再生成

[Q02]
- 分類項目: SoR
- 重要度: 高
- 質問文: SoR はどれ？
- 選択肢:
  A. CRM
  B. ERP
- 未回答時の既定値候補: A. CRM
- 既定値候補の理由: 既存資料
- 未回答のまま進めた場合の影響: CRM
"""


class _MainSession:
    def __init__(self, reply: Any) -> None:
        self.prompts: List[str] = []
        self._reply = reply

    async def send_and_wait(self, prompt: str, timeout: float) -> Any:
        self.prompts.append(prompt)
        if isinstance(self._reply, BaseException):
            raise self._reply
        return SimpleNamespace(data=SimpleNamespace(content=self._reply))


def _config(**kw: Any) -> SDKConfig:
    base = dict(model="claude-opus-5.5", qa_model="gpt-5.5", run_id="r1", auto_qa=True,
                workiq_enabled=True, qa_answer_mode=None, force_interactive=True)
    base.update(kw)
    return SDKConfig(**base)


def _run(tmp_path: Path, cfg: SDKConfig, session: _MainSession, discovery: Any) -> tuple:
    submitted: List[Path] = []
    console = Console(verbose=False, quiet=True)
    runner = runner_module.StepRunner(config=cfg, console=console, qa_akm_dispatcher=submitted.append)
    collect = mock.AsyncMock(side_effect=AssertionError("回答待ちをしてはならない"))
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with mock.patch.object(runner_module, "_collect_qa_answers", new=collect), \
             mock.patch.object(runner_module, "discover_sdk_resources", return_value=SimpleNamespace(mcp_state="ready", mcp_servers=[])), \
             mock.patch.object(runner_module, "run_knowledge_discovery", new=discovery), \
             mock.patch.object(console, "warning") as warning, \
             mock.patch.object(QAMerger, "append_calibration_log", new=mock.Mock()) as cal:
            asyncio.run(runner._run_post_execution_discovery(
                session=session, client=SimpleNamespace(), step_id="1",
                original_prompt="AAS Step.1", custom_agent=None, workflow_id="aas",
                current_phase=2, total_phases=3,
            ))
    finally:
        os.chdir(cwd)
    return submitted, collect, cal, warning


def _answer(request: kd.DiscoveryRequest, no: int, answer: str, status: str) -> None:
    current = kf.read_file(request.repo_root, request.qa_path)
    kf.update_qa_research(
        request.repo_root, request.qa_path, base_sha256=current["sha256"],
        answers=[kf.ResearchAnswer(no=no, answer=answer, status=status)], sources=[],
    )


def test_post_execution_questionnaire_is_researched_and_saved(tmp_path: Path) -> None:
    seen: dict = {}

    async def discovery(request: kd.DiscoveryRequest, **kw: Any) -> Any:
        seen["request"] = request
        seen["kw"] = kw
        _answer(request, 1, "A) 差分マージ", "Confirmed")
        _answer(request, 2, "", "Unknown")
        return kd.DiscoveryResult(ran=True, usable=["workiq"])

    session = _MainSession(_QUESTIONNAIRE)
    submitted, collect, cal, _warning = _run(tmp_path, _config(), session, discovery)
    assert len(session.prompts) == 1
    assert QA_PROMPT_V2 in session.prompts[0] and "質問なし" in session.prompts[0]
    request = seen["request"]
    assert (request.mode, request.label, list(request.sources)) == ("qa", "1", ["workiq"])
    assert request.qa_path == "qa/r1-1-post-execution-qa.md"
    assert seen["kw"]["base_session_options"]["session_id"].endswith("post-qa-discovery")
    saved = tmp_path / "qa" / "r1-1-post-execution-qa.md"
    doc = QAMerger.parse_qa_file(saved)
    assert [q.user_answer for q in doc.questions] == ["A) 差分マージ", "A. CRM"]
    assert QAMerger.validate_answered_file(saved, expected_questions=2) == []
    assert "| workiq | 利用 | - |" in saved.read_text(encoding="utf-8")
    collect.assert_not_called()
    cal.assert_not_called()
    assert [p.name for p in submitted] == ["r1-1-post-execution-qa.md"]


def test_post_execution_without_sources_saves_defaults(tmp_path: Path) -> None:
    discovery = mock.AsyncMock(side_effect=AssertionError("知識源が無ければ探索しない"))
    submitted, collect, cal, _w = _run(tmp_path, _config(workiq_enabled=False), _MainSession(_QUESTIONNAIRE), discovery)
    saved = tmp_path / "qa" / "r1-1-post-execution-qa.md"
    doc = QAMerger.parse_qa_file(saved)
    assert [q.user_answer for q in doc.questions] == ["B. 全面再生成", "A. CRM"]
    assert "## 知識探索の状況" not in saved.read_text(encoding="utf-8")
    discovery.assert_not_called()
    collect.assert_not_called()
    cal.assert_not_called()
    assert len(submitted) == 1


def test_post_execution_no_questions_creates_no_file(tmp_path: Path) -> None:
    discovery = mock.AsyncMock(side_effect=AssertionError("must not run"))
    submitted, _c, _cal, warning = _run(tmp_path, _config(), _MainSession("質問なし"), discovery)
    assert not (tmp_path / "qa").exists()
    discovery.assert_not_called()
    warning.assert_not_called()
    assert submitted == []


def test_post_execution_failure_is_warning_only(tmp_path: Path) -> None:
    discovery = mock.AsyncMock(side_effect=AssertionError("must not run"))
    _s, _c, _cal, warning = _run(tmp_path, _config(), _MainSession(TimeoutError()), discovery)
    messages = [str(call.args[0]) for call in warning.call_args_list]
    assert "実行後の不明点調査 [1] を完了できませんでした（TimeoutError）。" in messages


def test_post_execution_discovery_error_keeps_record(tmp_path: Path) -> None:
    discovery = mock.AsyncMock(side_effect=RuntimeError("boom"))
    submitted, _c, _cal, _w = _run(tmp_path, _config(), _MainSession(_QUESTIONNAIRE), discovery)
    text = (tmp_path / "qa" / "r1-1-post-execution-qa.md").read_text(encoding="utf-8")
    assert "| workiq | 不明 | discovery-error |" in text
    assert len(submitted) == 1


@pytest.mark.parametrize(("auto_qa", "dry_run", "reuse", "expected"), [
    (True, False, False, True),
    (False, False, False, False),
    (True, True, False, False),
    (True, False, True, False),
])
def test_post_execution_conditions(auto_qa: bool, dry_run: bool, reuse: bool, expected: bool) -> None:
    assert runner_module._should_run_post_execution_discovery(
        auto_qa=auto_qa, dry_run=dry_run, reuse_session=reuse,
    ) is expected


def test_post_execution_phase_runs_after_main_gates_and_before_review() -> None:
    source = inspect.getsource(runner_module.StepRunner.run_step)
    gate = source.index("post_main_contract_errors")
    call = source.index("self._run_post_execution_discovery(")
    review = source.index("# Phase 3: 敵対的レビュー")
    assert gate < call < review
