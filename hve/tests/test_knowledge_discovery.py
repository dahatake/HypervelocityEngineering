"""FR-KD-02 / 03 / 04 / 09 / NFR-KD-01: 知識探索エージェントの契約テスト。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from hve import knowledge_discovery as kd
from hve import knowledge_files as kf
from hve.qa_merger import QAMerger
from hve.toolsearch.policy import ToolSearchPolicy

_REPO_ROOT = Path(__file__).resolve().parents[2]
_URL = "https://contoso.sharepoint.com/sites/p/Plan.docx"


def _snapshot(*servers: tuple, ready: bool = True) -> Any:
    return SimpleNamespace(
        mcp_state="ready" if ready else "unverified",
        mcp_servers=[SimpleNamespace(name=n, enabled=e) for n, e in servers],
    )


_ALLOW = {"workiq": ("retrieve", "ask"), "jira": ("search",)}


def _allowlist_for(name: str) -> tuple:
    return _ALLOW.get(name, ())


def _qa_text(count: int = 3) -> str:
    rows = "\n".join(
        f"| {n} | 質問{n} | A) はい / B) いいえ | A) はい | 理由{n} |  |" for n in range(1, count + 1)
    )
    return (
        "# 事前 QA\n\n**状態**: 回答待ち\n\n---\n\n## 質問項目\n\n"
        "| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 | ユーザー回答 |\n"
        "|-----|------|--------|-----------|----------------|------------|\n"
        f"{rows}\n"
    )


def _start(call_id: str, server: str = "workiq", tool: str = "retrieve") -> Dict[str, Any]:
    return {
        "type": "tool.execution_start",
        "data": {"tool_call_id": call_id, "mcp_server_name": server, "mcp_tool_name": tool, "tool_name": f"{server}-{tool}"},
    }


def _complete(call_id: str, content: str, success: bool = True) -> Dict[str, Any]:
    return {
        "type": "tool.execution_complete",
        "data": {"tool_call_id": call_id, "success": success, "result": {"content": content}},
    }


# --------------------------------------------------------------------------- source_resolution


def test_source_resolution_classifies_each_source() -> None:
    snap = _snapshot(("workiq", True), ("jira", True), ("nolist", True), ("off", False))
    res = kd.resolve_sources(["workiq", "jira", "nolist", "off", "missing"], snap, _allowlist_for)
    assert res.usable == ("workiq", "jira")
    assert dict(res.excluded) == {
        "nolist": "no-readonly-allowlist",
        "off": "not-configured",
        "missing": "not-configured",
    }
    assert res.enabled_server_names == ("jira", "nolist", "workiq")


def test_source_resolution_unverified_snapshot() -> None:
    res = kd.resolve_sources(["workiq"], _snapshot(("workiq", True), ready=False), _allowlist_for)
    assert res.usable == () and res.excluded == (("workiq", "unverified"),)


def test_source_resolution_default_policy_workiq_allowlist_is_readonly() -> None:
    policy = ToolSearchPolicy.load(_REPO_ROOT / "hve" / "toolsearch" / "policy.json")
    tools = policy.tool_allowlist_for("knowledge", "workiq")
    assert tools == ("retrieve", "ask", "fetch", "search_paths", "get_schema", "list_agents")
    forbidden = {"create_entity", "update_entity", "delete_entity", "do_action", "call_function", "fetch_blob"}
    assert not forbidden & set(tools)


def test_source_resolution_exclusion_warning_format() -> None:
    assert kd.format_exclusion_warning("jira", "not-configured") == "知識源 jira を除外します（not-configured）"


class _FakeMcpRpc:
    """SDK と同じく、MCP host は ``initialize_and_validate`` 前は空の一覧を返す。"""

    def __init__(
        self,
        servers: Dict[str, Any],
        tools: Dict[str, List[str]],
        fail: bool = False,
        init_fail: bool = False,
    ) -> None:
        self._servers = servers  # 値は status 文字列、または list_ 呼出しごとの status 列
        self._tools = tools
        self._fail = fail
        self._init_fail = init_fail
        self.initialized = False
        self.list_calls = 0
        self.timeouts: List[Any] = []

    async def initialize_and_validate(self, *, timeout: Any = None) -> Any:
        self.timeouts.append(timeout)
        if self._init_fail:
            raise RuntimeError("init boom")
        self.initialized = True
        return SimpleNamespace()

    def _status(self, value: Any) -> str:
        if isinstance(value, list):
            return value[min(self.list_calls - 1, len(value) - 1)]
        return value

    async def list(self, *, timeout: Any = None) -> Any:
        self.timeouts.append(timeout)
        if self._fail:
            raise RuntimeError("boom")
        if not self.initialized:
            return SimpleNamespace(servers=[])
        self.list_calls += 1
        return SimpleNamespace(servers=[SimpleNamespace(name=n, status=self._status(s)) for n, s in self._servers.items()])

    async def list_tools(self, request: Any, *, timeout: Any = None) -> Any:
        self.timeouts.append(timeout)
        assert self.initialized
        return SimpleNamespace(tools=[SimpleNamespace(name=t) for t in self._tools.get(request.server_name, [])])


def _session_with(rpc: _FakeMcpRpc) -> Any:
    return SimpleNamespace(rpc=SimpleNamespace(mcp=rpc, tools=rpc))


def test_runtime_inspection_filters_sources() -> None:
    rpc = _FakeMcpRpc(
        {"workiq": "connected", "jira": "needs-auth", "x": "connected"},
        {"workiq": ["retrieve", "create_entity"], "x": ["write"]},
    )
    usable, excluded = asyncio.run(
        kd.inspect_runtime_sources(_session_with(rpc), ["workiq", "jira", "x"], {"workiq": ("retrieve",), "jira": ("search",), "x": ("search",)})
    )
    assert usable == ("workiq",)
    assert dict(excluded) == {"jira": "server-needs-auth", "x": "no-allowlisted-tool-exposed"}
    assert rpc.initialized, "MCP host must be initialized before listing (FR-KD-03)"
    assert all(isinstance(value, float) and value > 0 for value in rpc.timeouts)


def test_runtime_inspection_waits_for_pending_sources(monkeypatch) -> None:
    monkeypatch.setattr(kd, "RUNTIME_INSPECT_POLL_SECONDS", 0.0)
    rpc = _FakeMcpRpc({"workiq": ["pending", "pending", "connected"]}, {"workiq": ["ask"]})
    usable, excluded = asyncio.run(
        kd.inspect_runtime_sources(_session_with(rpc), ["workiq"], {"workiq": ("ask",)})
    )
    assert usable == ("workiq",) and excluded == ()
    assert rpc.list_calls == 3


def test_runtime_inspection_pending_until_deadline_is_excluded(monkeypatch) -> None:
    monkeypatch.setattr(kd, "RUNTIME_INSPECT_POLL_SECONDS", 0.01)
    rpc = _FakeMcpRpc({"workiq": "pending"}, {"workiq": ["ask"]})
    usable, excluded = asyncio.run(
        kd.inspect_runtime_sources(_session_with(rpc), ["workiq"], {"workiq": ("ask",)}, timeout=0.05)
    )
    assert usable == () and excluded == (("workiq", "server-pending"),)


def test_runtime_inspection_rpc_failure_is_unverified() -> None:
    usable, excluded = asyncio.run(
        kd.inspect_runtime_sources(_session_with(_FakeMcpRpc({}, {}, fail=True)), ["workiq"], {"workiq": ("ask",)})
    )
    assert usable == () and excluded == (("workiq", "unverified"),)


def test_runtime_inspection_initialization_failure_is_unverified() -> None:
    rpc = _FakeMcpRpc({"workiq": "connected"}, {"workiq": ["ask"]}, init_fail=True)
    usable, excluded = asyncio.run(
        kd.inspect_runtime_sources(_session_with(rpc), ["workiq"], {"workiq": ("ask",)})
    )
    assert usable == () and excluded == (("workiq", "unverified"),)


# --------------------------------------------------------------------------- evidence / source_verification


def test_evidence_correlates_successful_calls_only() -> None:
    ev = kd.SourceEvidence()
    ev.handle_event(_start("c1"))
    ev.handle_event(_complete("c1", f"資料: {_URL}"))
    ev.handle_event(_start("c2", tool="ask"))
    ev.handle_event(_complete("c2", "https://other.example/x", success=False))
    ev.handle_event(_complete("orphan", "https://orphan.example/y"))
    assert ev.successful_call_count("workiq", "retrieve") == 1
    assert ev.successful_call_count("workiq", "ask") == 0
    assert ev.locator_found("workiq", _URL)
    assert not ev.locator_found("workiq", "https://orphan.example/y")


def test_evidence_duplicate_call_id_is_ambiguous() -> None:
    ev = kd.SourceEvidence()
    ev.handle_event(_start("dup"))
    ev.handle_event(_start("dup"))
    ev.handle_event(_complete("dup", _URL))
    assert ev.successful_call_count("workiq", "retrieve") == 0


def test_evidence_locator_normalization() -> None:
    ev = kd.SourceEvidence()
    ev.handle_event(_start("c1"))
    ev.handle_event(_complete("c1", "Path: https:\\/\\/Contoso.sharepoint.com\\/sites\\/p\\/Plan.docx   ok"))
    assert ev.locator_found("workiq", _URL)


def _entry(**kw: Any) -> kf.SourceEntry:
    base = dict(id="S1", kind="mcp", server="workiq", tool="retrieve", locator=_URL, summary="s")
    base.update(kw)
    return kf.SourceEntry(**base)


@pytest.mark.parametrize(
    "entry,reason",
    [
        (_entry(), None),
        (_entry(locator="https://contoso.sharepoint.com/sites/p/Other.docx"), "locator-not-found"),
        (_entry(tool="ask"), "no-successful-call"),
        (_entry(tool="create_entity"), "tool-not-allowlisted"),
        (_entry(server="jira"), "server-not-usable"),
        (_entry(locator=" a "), "locator-too-short"),
        (_entry(kind="web"), "unknown-source-kind"),
        (_entry(kind="repo", locator="README.md"), None),
        (_entry(kind="repo", locator="no/such/file.md"), "repo-path-missing"),
        (_entry(kind="repo", locator="../outside.md"), "repo-path-invalid"),
        (_entry(kind="repo", locator=".git/config"), "repo-path-invalid"),
    ],
)
def test_source_verification_rules(entry: kf.SourceEntry, reason: Any) -> None:
    ev = kd.SourceEvidence()
    ev.handle_event(_start("c1"))
    ev.handle_event(_complete("c1", f"資料: {_URL}"))
    got = kd.verify_source(
        entry, repo_root=_REPO_ROOT, usable=("workiq",), allowlists={"workiq": ("retrieve", "ask")}, evidence=ev,
    )
    assert got == reason


def _toolset(tmp_path: Path, mode: str = "qa", qa_path: Any = "qa/a.md", ev: Any = None) -> kd.DiscoveryToolset:
    evidence = ev or kd.SourceEvidence()
    return kd.DiscoveryToolset(
        mode=mode, repo_root=tmp_path, run_id="r1", label="1", usable=("workiq",),
        allowlists={"workiq": ("retrieve",)}, evidence=evidence, qa_path=qa_path,
        validator_path=_REPO_ROOT / ".github" / "scripts" / "validate-knowledge-files.py",
    )


def test_source_verification_qa_answer_accepts_verified_source(tmp_path: Path) -> None:
    sha = kf.write_file(tmp_path, "qa/a.md", _qa_text(), base_sha256=None, kind="qa")
    ev = kd.SourceEvidence()
    ev.handle_event(_start("c1"))
    ev.handle_event(_complete("c1", f"秘密の本文 {_URL}"))
    ts = _toolset(tmp_path, ev=ev)
    result = ts.handle(kd.TOOL_QA_ANSWER, {
        "path": "qa/a.md", "base_sha256": sha,
        "answers": [{"no": 1, "answer": "A) はい", "status": "Confirmed", "source_ids": ["L1"]}],
        "sources": [{"id": "L1", "kind": "mcp", "server": "workiq", "tool": "retrieve", "locator": _URL, "summary": "計画書"}],
    })
    assert result["ok"] is True
    text = (tmp_path / "qa" / "a.md").read_text(encoding="utf-8")
    assert _URL in text and "秘密の本文" not in text
    q1 = QAMerger.parse_qa_content(text).questions[0]
    assert (q1.research_status, q1.research_sources) == ("Confirmed", "S1")


def test_source_verification_rejects_without_changing_file(tmp_path: Path) -> None:
    sha = kf.write_file(tmp_path, "qa/a.md", _qa_text(), base_sha256=None, kind="qa")
    ev = kd.SourceEvidence()
    ev.handle_event(_start("c1"))
    ev.handle_event(_complete("c1", "秘密の本文 SECRET-CONTENT"))
    ts = _toolset(tmp_path, ev=ev)
    before = (tmp_path / "qa" / "a.md").read_bytes()
    result = ts.handle(kd.TOOL_QA_ANSWER, {
        "path": "qa/a.md", "base_sha256": sha,
        "answers": [
            {"no": 1, "answer": "A", "status": "Confirmed", "source_ids": ["L1"]},
            {"no": 2, "answer": "B", "status": "Confirmed", "source_ids": []},
            {"no": 3, "answer": "B", "status": "Tentative", "source_ids": ["L9"]},
        ],
        "sources": [{"id": "L1", "kind": "mcp", "server": "workiq", "tool": "retrieve", "locator": "https://nowhere.example/x", "summary": "s"}],
    })
    assert result["ok"] is False and result["code"] == "source-verification-failed"
    reasons = {v["reason"] for v in result["violations"]}
    assert {"locator-not-found", "confirmed-without-source", "unknown-source-id"} <= reasons
    assert "SECRET-CONTENT" not in json.dumps(result, ensure_ascii=False)
    assert (tmp_path / "qa" / "a.md").read_bytes() == before
    assert ts.failures == 1


def test_source_verification_qa_answer_rejects_foreign_path(tmp_path: Path) -> None:
    kf.write_file(tmp_path, "qa/other.md", _qa_text(), base_sha256=None, kind="qa")
    result = _toolset(tmp_path).handle(kd.TOOL_QA_ANSWER, {
        "path": "qa/other.md", "base_sha256": "x", "answers": [{"no": 1, "answer": "", "status": "Unknown"}],
    })
    assert result["code"] == "path-denied"


def test_source_verification_knowledge_write_tool(tmp_path: Path) -> None:
    (tmp_path / "docs-original").mkdir()
    (tmp_path / "docs-original" / "a.md").write_text("x", encoding="utf-8")
    ts = _toolset(tmp_path, mode="knowledge", qa_path=None)
    assert kd.TOOL_KNOWLEDGE_WRITE in ts.tool_names()
    result = ts.handle(kd.TOOL_KNOWLEDGE_WRITE, {
        "path": kf.KNOWLEDGE_STATUS_FILE, "base_sha256": None, "content": "# status\n", "summary": "s",
        "sources": [{"id": "L1", "kind": "repo", "locator": "docs-original/a.md", "summary": "s"}],
    })
    assert result["ok"] is True and ts.knowledge_written == [kf.KNOWLEDGE_STATUS_FILE]
    denied = _toolset(tmp_path, mode="qa").handle(kd.TOOL_KNOWLEDGE_WRITE, {})
    assert denied["code"] == "unknown-tool"


# --------------------------------------------------------------------------- session_options / permission / prompt


def test_session_options_contract(tmp_path: Path) -> None:
    ts = _toolset(tmp_path, mode="knowledge", qa_path=None)
    opts = kd.build_session_options(
        base={"model": "m", "on_user_input_request": object(), "session_id": "s"},
        usable=("workiq",), allowlists={"workiq": ("retrieve", "ask")},
        enabled_server_names=("azure", "workiq", "jira"), toolset=ts, tools=["T"],
        permission_handler=lambda r, i: None, on_event=lambda e: None,
    )
    assert "on_user_input_request" not in opts
    assert opts["enable_config_discovery"] is True
    assert opts["disabled_mcp_servers"] == ["azure", "jira"]
    assert opts["available_tools"] == [
        "builtin:view", "builtin:grep", "builtin:glob", "builtin:skill",
        "custom:hve_read_file", "custom:hve_qa_create", "custom:hve_qa_answer", "custom:hve_knowledge_write",
        "mcp:workiq-retrieve", "mcp:workiq-ask",
    ]
    assert opts["infinite_sessions"] == {"enabled": True}
    assert opts["streaming"] is True and opts["model"] == "m" and opts["tools"] == ["T"]
    qa_opts = kd.build_session_options(
        base={}, usable=("workiq",), allowlists={"workiq": ("ask",)}, enabled_server_names=("workiq",),
        toolset=_toolset(tmp_path), tools=[], permission_handler=lambda r, i: None, on_event=lambda e: None,
    )
    assert "custom:hve_knowledge_write" not in qa_opts["available_tools"]


def _req(kind: str, **kw: Any) -> Any:
    return SimpleNamespace(kind=kind, **kw)


@pytest.mark.parametrize(
    "request_,allowed",
    [
        (_req("read", path="README.md"), True),
        (_req("read", path="docs/x.md"), True),
        (_req("read", path=".git/config"), False),
        (_req("read", path=".hve/locks/a.lock"), False),
        (_req("read", path=".env.local"), False),
        (_req("read", path="../outside.txt"), False),
        (_req("read", path="README.md", request_sandbox_bypass=True), False),
        (_req("mcp", server_name="workiq", tool_name="retrieve"), True),
        (_req("mcp", server_name="workiq", tool_name="create_entity"), False),
        (_req("mcp", server_name="jira", tool_name="search"), False),
        (_req("mcp", server_name="workiq", tool_name="retrieve", managed_approval_required=True), False),
        (_req("custom-tool", tool_name="hve_qa_answer"), True),
        (_req("custom-tool", tool_name="other"), False),
        (_req("write", file_name="qa/a.md"), False),
        (_req("shell", full_command_text="ls"), False),
        (_req("url", url="https://x"), False),
        (_req("memory"), False),
    ],
)
def test_permission_decisions(request_: Any, allowed: bool) -> None:
    assert kd.decide_permission(
        request_, repo_root=_REPO_ROOT, usable=("workiq",), allowlists={"workiq": ("retrieve",)},
        custom_tools=("hve_read_file", "hve_qa_create", "hve_qa_answer"),
    ) is allowed


@pytest.mark.parametrize("mode", kd.DISCOVERY_MODES)
def test_prompt_has_goal_and_no_fixed_format(mode: str) -> None:
    prompt = kd.build_goal_prompt(
        mode=mode, goal="目的X", usable=("workiq",), allowlists={"workiq": ("retrieve", "ask")},
        run_id="r1", qa_path="qa/a.md",
    )
    assert "目的X" in prompt and "- workiq: retrieve, ask" in prompt and "r1" in prompt
    assert "STATUS:" not in prompt and "{goal}" not in prompt
    for banned in ("最大 5", "1〜5", "最大10", "10 問"):
        assert banned not in prompt
    if mode == "qa":
        assert "qa/a.md" in prompt


def test_prompt_qa_create_limit(tmp_path: Path) -> None:
    ts = _toolset(tmp_path, mode="research", qa_path=None)
    payload = {"title": "t", "questions": [{"question": "q"}]}
    results = [ts.handle(kd.TOOL_QA_CREATE, payload) for _ in range(6)]
    assert [r["ok"] for r in results] == [True] * 5 + [False]
    assert results[-1]["code"] == "limit-exceeded"
    assert len(ts.created_qa) == 5


# --------------------------------------------------------------------------- repair / run


class _FakeSession:
    def __init__(self, toolset_ref: Dict[str, Any], behaviour: Any) -> None:
        mcp = _FakeMcpRpc({"workiq": "connected"}, {"workiq": ["retrieve"]})
        self.rpc = SimpleNamespace(mcp=mcp, tools=mcp)
        self.prompts: List[str] = []
        self._ref = toolset_ref
        self._behaviour = behaviour

    async def send_and_wait(self, prompt: str, timeout: float) -> None:
        self.prompts.append(prompt)
        await self._behaviour(self, len(self.prompts))


def _run(tmp_path: Path, mode: str, behaviour: Any, *, qa_path: Any = None) -> tuple:
    warnings: List[str] = []
    statuses: List[str] = []
    holder: Dict[str, Any] = {}

    async def _create(opts: Dict[str, Any]) -> Any:
        holder["opts"] = opts
        holder["session"] = _FakeSession(holder, behaviour)
        holder["tools"] = {t.name: t for t in opts["tools"]}
        return holder["session"]

    async def _disconnect(_s: Any) -> None:
        holder["disconnected"] = True

    result = asyncio.run(kd.run_knowledge_discovery(
        kd.DiscoveryRequest(mode=mode, repo_root=tmp_path, run_id="r1", label="lbl", goal="g", sources=["workiq"], qa_path=qa_path),
        snapshot=_snapshot(("workiq", True)), allowlist_for=lambda n: ("retrieve",),
        base_session_options={}, create_session=_create, disconnect=_disconnect,
        warn=warnings.append, status=statuses.append, timeout=5,
    ))
    return result, holder, warnings, statuses


async def _call(holder: Dict[str, Any], name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    res = await holder["tools"][name].handler(SimpleNamespace(arguments=args))
    return json.loads(res.text_result_for_llm)


def test_repair_qa_mode_marks_rest_unknown(tmp_path: Path) -> None:
    kf.write_file(tmp_path, "qa/a.md", _qa_text(3), base_sha256=None, kind="qa")

    async def behaviour(session: _FakeSession, n: int) -> None:
        if n == 1:
            holder = session._ref
            sha = (await _call(holder, kd.TOOL_READ, {"path": "qa/a.md"}))["sha256"]
            await _call(holder, kd.TOOL_QA_ANSWER, {
                "path": "qa/a.md", "base_sha256": sha,
                "answers": [{"no": 1, "answer": "A) はい", "status": "Tentative"}],
            })

    result, holder, _w, statuses = _run(tmp_path, "qa", behaviour, qa_path="qa/a.md")
    prompts = holder["session"].prompts
    assert len(prompts) == 3 and result.repairs == 2
    assert "qa/a.md Q2" in prompts[1] and "qa/a.md Q3" in prompts[1] and "Q1" not in prompts[1]
    doc = QAMerger.parse_qa_file(tmp_path / "qa" / "a.md")
    assert [q.research_status for q in doc.questions] == ["Tentative", "Unknown", "Unknown"]
    assert statuses[-1] == "知識探索 [lbl]: Confirmed=0 Tentative=1 Unknown=2 修復=2 tool失敗=0"
    assert holder.get("disconnected") is True
    assert "on_user_input_request" not in holder["opts"]


def test_repair_research_mode_requires_qa(tmp_path: Path) -> None:
    async def behaviour(session: _FakeSession, n: int) -> None:
        if n == 2:
            created = await _call(session._ref, kd.TOOL_QA_CREATE, {"title": "t", "questions": [{"question": "q1"}, {"question": "q2"}]})
            await _call(session._ref, kd.TOOL_QA_ANSWER, {
                "path": created["path"], "base_sha256": created["sha256"],
                "answers": [{"no": 1, "answer": "回答", "status": "Tentative"}],
            })

    result, holder, _w, _s = _run(tmp_path, "research", behaviour)
    prompts = holder["session"].prompts
    assert "QA 未作成" in prompts[1]
    assert result.repairs == 2 and len(result.qa_paths) == 1
    doc = QAMerger.parse_qa_file(tmp_path / result.qa_paths[0])
    assert doc.status == "調査済み"
    assert [q.research_status for q in doc.questions] == ["Tentative", "Unknown"]
    assert doc.questions[0].user_answer == "回答"


def test_repair_not_needed_and_failure_is_warned(tmp_path: Path) -> None:
    kf.write_file(tmp_path, "qa/a.md", _qa_text(1), base_sha256=None, kind="qa")

    async def behaviour(session: _FakeSession, n: int) -> None:
        raise TimeoutError()

    result, holder, warnings, _s = _run(tmp_path, "qa", behaviour, qa_path="qa/a.md")
    assert result.ran is True and result.error == "TimeoutError" and result.repairs == 0
    assert any("途中で終了" in w for w in warnings)
    assert QAMerger.parse_qa_file(tmp_path / "qa" / "a.md").questions[0].research_status == "Unknown"


def test_repair_no_usable_source_does_not_create_session(tmp_path: Path) -> None:
    async def _create(opts: Dict[str, Any]) -> Any:
        raise AssertionError("must not create")

    warnings: List[str] = []
    result = asyncio.run(kd.run_knowledge_discovery(
        kd.DiscoveryRequest(mode="qa", repo_root=tmp_path, run_id="r", label="l", goal="g", sources=["jira"], qa_path="qa/a.md"),
        snapshot=_snapshot(("workiq", True)), allowlist_for=lambda n: ("x",), base_session_options={},
        create_session=_create, disconnect=lambda s: None, warn=warnings.append, status=lambda s: None, timeout=1,
    ))
    assert result.ran is False and result.reason == "no-usable-source"
    assert warnings == ["知識源 jira を除外します（not-configured）"]


# --------------------------------------------------------------------------- ARD comment (FR-KD-08)


def test_ard_comment_format(tmp_path: Path) -> None:
    sha = kf.write_file(tmp_path, "qa/a.md", _qa_text(2), base_sha256=None, kind="qa")
    kf.update_qa_research(
        tmp_path, "qa/a.md", base_sha256=sha,
        answers=[kf.ResearchAnswer(no=1, answer="a|b\n<script>", status="Confirmed", source_ids=("L1",)),
                 kf.ResearchAnswer(no=2, answer="", status="Unknown")],
        sources=[kf.SourceEntry(id="L1", kind="repo", server="", tool="", locator="docs/<x>.md", summary="s")],
    )
    body = kd.build_ard_comment(tmp_path, ["qa/a.md"])
    assert body is not None
    assert body.startswith("## ARD 知識探索: ユースケース参照情報\n")
    assert "QA: `qa/a.md`" in body
    assert "| No. | 質問 | 調査状態 | 調査回答 | 調査出典 |" in body
    assert "| 1 | 質問1 | Confirmed | a&#124;b<br>&lt;script&gt; | S1 |" in body
    assert "| 2 |" not in body
    assert "docs/&lt;x&gt;.md" in body and "<script>" not in body


def test_ard_comment_none_without_answers(tmp_path: Path) -> None:
    kf.write_file(tmp_path, "qa/a.md", _qa_text(1), base_sha256=None, kind="qa")
    assert kd.build_ard_comment(tmp_path, ["qa/a.md"]) is None
