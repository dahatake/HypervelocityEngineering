"""FR-KD-07 / FR-KD-08: AKM / ARD の知識探索 phase。"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest import mock

from hve import knowledge_discovery as kd
from hve import knowledge_files as kf
from hve import orchestrator as orch
from hve.config import SDKConfig
from hve.console import Console


def _qa_with_answer(root: Path) -> str:
    text = (
        "# t\n\n## 質問項目\n\n| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 | ユーザー回答 |\n"
        "|-----|------|--------|-----------|----------------|------------|\n| 1 | 業務は？ |  |  |  |  |\n"
    )
    sha = kf.write_file(root, "qa/r-ard-knowledge-discovery-qa.md", text, base_sha256=None, kind="qa")
    kf.update_qa_research(
        root, "qa/r-ard-knowledge-discovery-qa.md", base_sha256=sha,
        answers=[kf.ResearchAnswer(no=1, answer="受注|出荷", status="Confirmed")], sources=[],
    )
    return "qa/r-ard-knowledge-discovery-qa.md"


def test_akm_and_ard_extra_sources_and_phase_plan() -> None:
    assert orch._knowledge_discovery_extra_sources("akm", {"sources": "qa,workiq"}) == ["workiq"]
    assert orch._knowledge_discovery_extra_sources("akm", {"sources": "qa"}) == []
    assert orch._knowledge_discovery_extra_sources("ard", {"ard_workiq_enabled": True}) == ["workiq"]
    assert orch._knowledge_discovery_extra_sources("aas", {"sources": "workiq"}) == []
    cfg = SDKConfig()
    assert orch._planned_knowledge_discovery_phase("akm", cfg, {"sources": "qa"}) is None
    assert orch._planned_knowledge_discovery_phase("akm", cfg, {"sources": "workiq,qa"}) == "AKM 知識探索"
    assert orch._planned_knowledge_discovery_phase("ard", SDKConfig(knowledge_sources=["jira"]), {}) == "ARD 知識探索"
    assert orch._planned_knowledge_discovery_phase("aas", SDKConfig(workiq_enabled=True), {}) is None
    assert orch._planned_knowledge_discovery_phase("akm", SDKConfig(workiq_enabled=True, dry_run=True), {}) is None


def test_akm_goal_reflects_sources() -> None:
    assert "`qa/`" in orch._akm_knowledge_discovery_goal({"sources": "qa"})
    goal = orch._akm_knowledge_discovery_goal({"sources": "qa,original-docs"})
    assert "`docs-original/`" in goal and "Unknown / Tentative" in goal
    assert "リポジトリ内の入力なし" in orch._akm_knowledge_discovery_goal({"sources": "workiq"})


def test_ard_goal_contains_company(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    assert "「未指定」" in orch._ard_knowledge_discovery_goal({})
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "company-business-requirement.md").write_text("x", encoding="utf-8")
    goal = orch._ard_knowledge_discovery_goal({"company_name": "Contoso"})
    assert "「Contoso」" in goal and "docs/company-business-requirement.md" in goal


def test_orchestrator_discovery_runs_one_session(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    captured: Dict[str, Any] = {}

    async def fake_run(request: kd.DiscoveryRequest, **kw: Any) -> Any:
        captured["request"] = request
        captured["kw"] = kw
        session = await kw["create_session"]({"x": 1})
        await kw["disconnect"](session)
        return kd.DiscoveryResult(ran=True, qa_paths=["qa/a.md"])

    client = SimpleNamespace(start=mock.AsyncMock(), stop=mock.AsyncMock())
    create = mock.AsyncMock(return_value=SimpleNamespace(disconnect=mock.AsyncMock()))
    cfg = SDKConfig(workiq_enabled=True, run_id="r1", reasoning_effort="high")
    with mock.patch.object(orch, "discover_sdk_resources", return_value=SimpleNamespace(mcp_state="ready", mcp_servers=[])), \
         mock.patch.object(orch, "_create_copilot_client_from_config", return_value=client), \
         mock.patch.object(orch, "_create_session_with_auto_reasoning_fallback", new=create), \
         mock.patch("hve.knowledge_discovery.run_knowledge_discovery", new=fake_run):
        result = asyncio.run(orch._run_orchestrator_knowledge_discovery(
            cfg, Console(quiet=True), mode="knowledge", label="akm", goal="G", extra_sources=["jira", "workiq"],
        ))
    assert result.qa_paths == ["qa/a.md"]
    req = captured["request"]
    assert (req.mode, req.label, req.goal, list(req.sources)) == ("knowledge", "akm", "G", ["workiq", "jira"])
    assert captured["kw"]["base_session_options"]["reasoning_effort"] == "high"
    kwargs = create.await_args.kwargs
    assert kwargs["use_resource_routing"] is False and kwargs["allow_cloud_session_injection"] is False
    client.start.assert_awaited_once()


def test_orchestrator_discovery_without_sources_returns_none() -> None:
    result = asyncio.run(orch._run_orchestrator_knowledge_discovery(
        SDKConfig(), Console(quiet=True), mode="knowledge", label="akm", goal="G",
    ))
    assert result is None


def test_ard_comment_posted_once(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    rel = _qa_with_answer(tmp_path)
    posts: List[Dict[str, Any]] = []
    with mock.patch.object(orch, "post_comment", side_effect=lambda **kw: posts.append(kw)):
        orch._post_ard_discovery_comment(
            kd.DiscoveryResult(ran=True, qa_paths=[rel]), console=Console(quiet=True),
            step2_issue_num=12, repo="o/r", token="t",
        )
    assert len(posts) == 1 and posts[0]["issue_num"] == 12
    assert posts[0]["body"].startswith("## ARD 知識探索: ユースケース参照情報")
    assert "| 1 | 業務は？ | Confirmed | 受注&#124;出荷 |" in posts[0]["body"]


def test_ard_comment_not_posted_without_answers_or_issue(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    rel = _qa_with_answer(tmp_path)
    with mock.patch.object(orch, "post_comment") as post:
        orch._post_ard_discovery_comment(
            kd.DiscoveryResult(ran=True, qa_paths=[rel]), console=Console(quiet=True),
            step2_issue_num=None, repo="o/r", token="t",
        )
        orch._post_ard_discovery_comment(
            kd.DiscoveryResult(ran=True, qa_paths=[]), console=Console(quiet=True),
            step2_issue_num=12, repo="o/r", token="t",
        )
    post.assert_not_called()


def test_run_workflow_wires_discovery_before_dag_without_legacy_phases() -> None:
    src = inspect.getsource(orch._run_workflow_body)
    idx_kd = src.index("_kd_result = await _run_orchestrator_knowledge_discovery(")
    idx_dag = src.index("# --- 5. StepRunner 準備 + DAG 実行 ---")
    assert idx_kd < idx_dag
    assert src.count("await _run_orchestrator_knowledge_discovery(") == 1
    assert "_planned_knowledge_discovery_phase(workflow_id, config, params)" in src
    assert "知識探索 中にエラーが発生しました" not in src
    assert "中にエラーが発生しました（無視して続行）" in src
    for name in (
        "_run_akm_workiq_ingest", "_run_akm_workiq_verification", "_run_ard_workiq_usecase",
        "_create_orchestrator_workiq_session", "_trusted_akm_workiq_content", "_WorkIQEventEvidence",
    ):
        assert not hasattr(orch, name), name
        assert name not in src
