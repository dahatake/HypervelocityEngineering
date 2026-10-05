"""FR-KD-06: 事前 QA を知識探索で回答する（人への回答待ちをしない）。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List
from unittest import mock

from hve import knowledge_discovery as kd
from hve import knowledge_files as kf
from hve import runner as runner_module
from hve.config import SDKConfig
from hve.console import Console
from hve.qa_merger import QAMerger

_QUESTIONNAIRE = """\
# 事前 QA

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

[Q03]
- 分類項目: 投稿先
- 重要度: 中
- 質問文: 投稿先は？
- 選択肢:
  A. Teams
  B. なし
- 未回答時の既定値候補: B. なし
- 既定値候補の理由: 未確認
- 未回答のまま進めた場合の影響: なし
"""


class _QaSession:
    def __init__(self) -> None:
        self.prompts: List[str] = []
        self.disconnect_count = 0

    async def send_and_wait(self, prompt: str, timeout: float) -> Any:
        self.prompts.append(prompt)
        return SimpleNamespace(data=SimpleNamespace(content=_QUESTIONNAIRE))

    async def disconnect(self) -> None:
        self.disconnect_count += 1

    def on(self, _handler: Any) -> None:
        return None


def _config(run_id: str, **kw: Any) -> SDKConfig:
    base = dict(
        model="claude-opus-5.5", qa_model="gpt-5.5", run_id=run_id, workiq_enabled=True,
        qa_answer_mode=None, unattended=False, force_interactive=True,
    )
    base.update(kw)
    return SDKConfig(**base)


def _run(tmp_path: Path, cfg: SDKConfig, discovery: Any, *, collect: Any = None, calibration: Any = None) -> tuple:
    submitted: List[Path] = []
    runner = runner_module.StepRunner(
        config=cfg, console=Console(verbose=False, quiet=True), qa_akm_dispatcher=submitted.append,
    )
    qa_session = _QaSession()

    async def fake_create(_client: Any, options: Any, **_kw: Any) -> Any:
        return qa_session

    collect_mock = mock.AsyncMock(side_effect=collect or AssertionError("回答待ちをしてはならない"))
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with mock.patch.object(runner_module, "_create_session_with_auto_reasoning_fallback", new=mock.AsyncMock(side_effect=fake_create)), \
             mock.patch.object(runner_module, "_collect_qa_answers", new=collect_mock), \
             mock.patch.object(runner_module, "discover_sdk_resources", return_value=SimpleNamespace(mcp_state="ready", mcp_servers=[])), \
             mock.patch.object(runner_module, "run_knowledge_discovery", new=discovery), \
             mock.patch.object(QAMerger, "append_calibration_log", new=calibration or mock.Mock()) as cal:
            context = asyncio.run(runner._run_pre_execution_qa(
                session=SimpleNamespace(), client=SimpleNamespace(), step_id="1",
                original_prompt="AAS Step.1", custom_agent=None, workflow_id="aas",
                current_phase=1, total_phases=2,
            ))
    finally:
        os.chdir(cwd)
    return context, submitted, collect_mock, cal


def _answer(request: kd.DiscoveryRequest, no: int, answer: str, status: str) -> None:
    current = kf.read_file(request.repo_root, request.qa_path)
    kf.update_qa_research(
        request.repo_root, request.qa_path, base_sha256=current["sha256"],
        answers=[kf.ResearchAnswer(no=no, answer=answer, status=status)], sources=[],
    )


def test_research_answers_are_adopted_without_waiting(tmp_path: Path) -> None:
    seen: dict = {}

    async def discovery(request: kd.DiscoveryRequest, **kw: Any) -> Any:
        seen["request"] = request
        seen["kw"] = kw
        text = (request.repo_root / request.qa_path).read_text(encoding="utf-8")
        assert "既存成果物の更新方針は？" in text and "| 調査状態 |" not in text
        _answer(request, 1, "A) 差分マージ", "Confirmed")
        _answer(request, 2, "", "Unknown")
        return kd.DiscoveryResult(ran=True)

    context, submitted, collect_mock, cal = _run(tmp_path, _config("r1"), discovery)
    request = seen["request"]
    assert (request.mode, request.label, list(request.sources)) == ("qa", "1", ["workiq"])
    assert request.qa_path == "qa/r1-1-pre-execution-qa.md"
    assert seen["kw"]["base_session_options"]["model"] == "gpt-5.5"
    answered = tmp_path / "qa" / "r1-1-pre-execution-qa.md"
    doc = QAMerger.parse_qa_file(answered)
    assert [q.user_answer for q in doc.questions] == ["A) 差分マージ", "A. CRM", "B. なし"]
    assert doc.status == "回答済み"
    assert QAMerger.validate_answered_file(answered, expected_questions=3) == []
    assert context == "## 事前 QA 確認済み情報\n\n" + answered.read_text(encoding="utf-8")
    collect_mock.assert_not_called()
    cal.assert_not_called()
    assert [p.name for p in submitted] == ["r1-1-pre-execution-qa.md"]


def test_discovery_failure_still_does_not_wait(tmp_path: Path) -> None:
    async def discovery(request: kd.DiscoveryRequest, **_kw: Any) -> Any:
        _answer(request, 3, "A) Teams", "Tentative")
        raise RuntimeError("session failed")

    _context, _s, collect_mock, _c = _run(tmp_path, _config("r2"), discovery)
    doc = QAMerger.parse_qa_file(tmp_path / "qa" / "r2-1-pre-execution-qa.md")
    assert [q.user_answer for q in doc.questions] == ["B. 全面再生成", "A. CRM", "A) Teams"]
    collect_mock.assert_not_called()


def test_no_usable_source_falls_back_to_answer_collection(tmp_path: Path) -> None:
    async def discovery(request: kd.DiscoveryRequest, **_kw: Any) -> Any:
        return kd.DiscoveryResult(ran=False, reason="no-usable-source")

    async def collect(_console: Any, _doc: Any, _step: str, _cfg: Any) -> tuple:
        return "1: A", False

    _context, _s, collect_mock, cal = _run(tmp_path, _config("r3"), discovery, collect=collect)
    collect_mock.assert_awaited_once()
    doc = QAMerger.parse_qa_file(tmp_path / "qa" / "r3-1-pre-execution-qa.md")
    assert doc.questions[0].user_answer == "A) 差分マージ"
    cal.assert_called_once()


def test_without_sources_discovery_is_not_called(tmp_path: Path) -> None:
    discovery = mock.AsyncMock(side_effect=AssertionError("must not run"))

    async def collect(_console: Any, _doc: Any, _step: str, _cfg: Any) -> tuple:
        return "", True

    _run(tmp_path, _config("r4", workiq_enabled=False), discovery, collect=collect)
    discovery.assert_not_called()


def test_dry_run_does_not_discover(tmp_path: Path) -> None:
    discovery = mock.AsyncMock(side_effect=AssertionError("must not run"))

    async def collect(_console: Any, _doc: Any, _step: str, _cfg: Any) -> tuple:
        return "", True

    _run(tmp_path, _config("r5", dry_run=True), discovery, collect=collect)
    discovery.assert_not_called()
