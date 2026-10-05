"""FR-KD-11 / FR-KD-12 / FR-KD-02（v3.42 追補）/ FR-KD-14 の受入テスト（AC-014〜AC-016・AC-018）。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List
from unittest import mock

import pytest

from hve import knowledge_discovery as kd
from hve import prompt_execution, resume_service, workiq
from hve import runner as runner_module
from hve.__main__ import _build_config, _build_parser
from hve.config import SDKConfig
from hve.console import Console
from hve.gui import settings_store
from hve.gui.orchestrate_args import OrchestrateArgs, args_from_settings
from hve.prompt_request import PromptRequestError, parse_request
from hve.qa_akm_dispatch import QaAkmCoordinator
from hve.qa_merger import QAMerger
from hve.toolsearch.policy import ToolSearchPolicy

_REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- FR-KD-11（AC-014）


def _cli_config(argv: list, monkeypatch: pytest.MonkeyPatch, env: Any = None) -> SDKConfig:
    monkeypatch.delenv("HVE_KNOWLEDGE_SOURCES", raising=False)
    if env is None:
        monkeypatch.delenv("WORKIQ_ENABLED", raising=False)
    else:
        monkeypatch.setenv("WORKIQ_ENABLED", env)
    return _build_config(_build_parser().parse_args(["orchestrate", "--workflow", "aas", *argv]))


def test_defaults_cli_enables_auto_qa_and_workiq(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cli_config([], monkeypatch)
    assert (cfg.auto_qa, cfg.workiq_enabled) == (True, True)
    assert cfg.effective_knowledge_sources() == ["workiq"]


def test_defaults_cli_no_flags_disable(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cli_config(["--no-auto-qa", "--no-workiq"], monkeypatch)
    assert (cfg.auto_qa, cfg.workiq_enabled) == (False, False)
    assert cfg.effective_knowledge_sources() == []


@pytest.mark.parametrize(
    ("env", "argv", "expected"),
    [
        ("No", [], False),
        (" 0 ", [], False),
        ("false", [], False),
        ("", [], True),
        ("yes", [], True),
        ("false", ["--workiq"], True),
        ("true", ["--no-workiq"], False),
    ],
)
def test_defaults_workiq_env(monkeypatch: pytest.MonkeyPatch, env: str, argv: list, expected: bool) -> None:
    assert _cli_config(argv, monkeypatch, env=env).workiq_enabled is expected


def test_defaults_from_env_and_dataclass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKIQ_ENABLED", raising=False)
    assert SDKConfig.from_env().workiq_enabled is True
    monkeypatch.setenv("WORKIQ_ENABLED", "FALSE")
    assert SDKConfig.from_env().workiq_enabled is False
    plain = SDKConfig()
    assert (plain.auto_qa, plain.workiq_enabled) == (False, False)


def test_defaults_orchestrate_args_emit_explicit_switches() -> None:
    on = OrchestrateArgs(workflow="aas").to_argv()
    assert "--auto-qa" in on and "--workiq" in on
    assert "--no-auto-qa" not in on and "--no-workiq" not in on
    off = OrchestrateArgs(workflow="aas", auto_qa=False, workiq=False).to_argv()
    assert "--no-auto-qa" in off and "--no-workiq" in off
    assert "--auto-qa" not in off and "--workiq" not in off


@pytest.mark.parametrize(("saved", "expected"), [("", True), ("on", True), ("off", False), (None, True)])
def test_defaults_prompt_settings_auto_qa(saved: Any, expected: bool) -> None:
    settings = settings_store.defaults()
    if saved is None:
        settings["options"].pop("auto_qa", None)
    else:
        settings["options"]["auto_qa"] = saved
    args = args_from_settings(settings, workflow="aas", repo_root=_REPO_ROOT)
    assert args.auto_qa is expected


def test_defaults_gui_settings_workiq_default_is_true() -> None:
    assert settings_store.defaults()["options"]["workiq"] is True
    settings = settings_store.defaults()
    settings["options"].pop("workiq")
    assert args_from_settings(settings, workflow="aas", repo_root=_REPO_ROOT).workiq is True


def test_defaults_qa_akm_child_disables_auto_qa_and_workiq(tmp_path: Path) -> None:
    coordinator = QaAkmCoordinator(SDKConfig(auto_qa=True, workiq_enabled=True), repo_root=tmp_path)
    argv = coordinator._build_argv([tmp_path / "qa" / "a.md"], tmp_path)
    assert "--no-auto-qa" in argv and "--no-workiq" in argv
    assert "--auto-qa" not in argv and "--workiq" not in argv


@pytest.mark.parametrize(("value", "flags", "absent"), [
    (False, ("--no-auto-qa", "--no-workiq"), ("--auto-qa", "--workiq")),
    (True, ("--auto-qa", "--workiq"), ("--no-auto-qa", "--no-workiq")),
])
def test_defaults_resume_replay_is_explicit(tmp_path: Path, value: bool, flags: tuple, absent: tuple) -> None:
    cfg = SDKConfig(auto_qa=value, workiq_enabled=value)
    argv = resume_service.build_resolved_replay_argv("aas", cfg, {})
    for flag in flags:
        assert flag in argv
    for flag in absent:
        assert flag not in argv
    repo = tmp_path / "repo"
    repo.mkdir()
    safe, _missing = resume_service.ResumeService(SimpleNamespace(), repo).sanitize_argv(argv)
    for flag in flags:
        assert flag in safe
    parsed = _build_parser().parse_args(list(safe))
    assert (parsed.auto_qa, parsed.workiq) == (value, value)


# --------------------------------------------------------------------------- FR-KD-12（AC-015）


def test_needs_auth_warning_has_guidance() -> None:
    message = kd.format_exclusion_warning("workiq", "server-needs-auth")
    assert message == (
        "知識源 workiq を除外します（server-needs-auth）。"
        "GitHub Copilot CLI で /mcp auth workiq を実行して認証し、HVE を再起動してください。"
    )
    assert kd.format_exclusion_warning("jira", "not-configured") == "知識源 jira を除外します（not-configured）"


class _AuthRpc:
    async def initialize_and_validate(self, *, timeout: Any = None) -> Any:
        return SimpleNamespace()

    async def list(self, *, timeout: Any = None) -> Any:
        return SimpleNamespace(servers=[SimpleNamespace(name="workiq", status="needs-auth")])

    async def list_tools(self, request: Any, *, timeout: Any = None) -> Any:
        raise AssertionError("needs-auth の server の tool は列挙しない")


def test_status_discovery_result_reports_exclusions(tmp_path: Path) -> None:
    warnings: List[str] = []
    rpc = _AuthRpc()
    snapshot = SimpleNamespace(
        mcp_state="ready",
        mcp_servers=[SimpleNamespace(name="workiq", enabled=True), SimpleNamespace(name="jira", enabled=True)],
    )

    async def _create(_opts: Any) -> Any:
        return SimpleNamespace(rpc=SimpleNamespace(mcp=rpc, tools=rpc))

    async def _disconnect(_s: Any) -> None:
        return None

    result = asyncio.run(kd.run_knowledge_discovery(
        kd.DiscoveryRequest(mode="qa", repo_root=tmp_path, run_id="r", label="l", goal="g",
                            sources=["workiq", "jira"], qa_path="qa/a.md"),
        snapshot=snapshot, allowlist_for=lambda n: ("retrieve",) if n == "workiq" else (),
        base_session_options={}, create_session=_create, disconnect=_disconnect,
        warn=warnings.append, status=lambda _s: None, timeout=1,
    ))
    assert result.ran is False and result.usable == []
    assert result.excluded == [("jira", "no-readonly-allowlist"), ("workiq", "server-needs-auth")]
    assert any("/mcp auth workiq" in w for w in warnings)


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
"""


class _QaSession:
    async def send_and_wait(self, prompt: str, timeout: float) -> Any:
        return SimpleNamespace(data=SimpleNamespace(content=_QUESTIONNAIRE))

    async def disconnect(self) -> None:
        return None

    def on(self, _handler: Any) -> None:
        return None


def _run_pre_qa(tmp_path: Path, discovery: Any) -> str:
    cfg = SDKConfig(model="claude-opus-5.5", qa_model="gpt-5.5", run_id="r1", workiq_enabled=True,
                    knowledge_sources=["jira"], qa_answer_mode=None, force_interactive=True)
    runner = runner_module.StepRunner(config=cfg, console=Console(verbose=False, quiet=True))

    async def fake_create(_client: Any, _options: Any, **_kw: Any) -> Any:
        return _QaSession()

    async def collect(_console: Any, _doc: Any, _step: str, _cfg: Any) -> tuple:
        return "", True

    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        with mock.patch.object(runner_module, "_create_session_with_auto_reasoning_fallback", new=mock.AsyncMock(side_effect=fake_create)), \
             mock.patch.object(runner_module, "_collect_qa_answers", new=mock.AsyncMock(side_effect=collect)), \
             mock.patch.object(runner_module, "discover_sdk_resources", return_value=SimpleNamespace(mcp_state="ready", mcp_servers=[])), \
             mock.patch.object(runner_module, "run_knowledge_discovery", new=discovery), \
             mock.patch.object(QAMerger, "append_calibration_log", new=mock.Mock()):
            asyncio.run(runner._run_pre_execution_qa(
                session=SimpleNamespace(), client=SimpleNamespace(), step_id="1",
                original_prompt="AAS Step.1", custom_agent=None, workflow_id="aas",
                current_phase=1, total_phases=2,
            ))
    finally:
        os.chdir(cwd)
    return (tmp_path / "qa" / "r1-1-pre-execution-qa.md").read_text(encoding="utf-8")


def test_status_section_records_excluded_and_used_sources(tmp_path: Path) -> None:
    async def discovery(_request: kd.DiscoveryRequest, **_kw: Any) -> Any:
        return kd.DiscoveryResult(ran=False, reason="no-usable-source",
                                  excluded=[("workiq", "server-needs-auth"), ("jira", "not-configured")])

    text = _run_pre_qa(tmp_path, discovery)
    assert "## 知識探索の状況" in text
    assert "| 知識源 | 状態 | 理由コード |" in text
    assert "| workiq | 除外 | server-needs-auth |" in text
    assert "| jira | 除外 | not-configured |" in text
    doc = QAMerger.parse_qa_file(tmp_path / "qa" / "r1-1-pre-execution-qa.md")
    assert [q.user_answer for q in doc.questions] == ["B. 全面再生成"]


def test_status_section_marks_usable_and_unreported(tmp_path: Path) -> None:
    async def discovery(_request: kd.DiscoveryRequest, **_kw: Any) -> Any:
        return kd.DiscoveryResult(ran=True, usable=["workiq"])

    text = _run_pre_qa(tmp_path, discovery)
    assert "| workiq | 利用 | - |" in text
    assert "| jira | 不明 | not-reported |" in text


def test_status_section_on_discovery_error(tmp_path: Path) -> None:
    discovery = mock.AsyncMock(side_effect=RuntimeError("boom"))
    text = _run_pre_qa(tmp_path, discovery)
    assert "| workiq | 不明 | discovery-error |" in text
    assert "| jira | 不明 | discovery-error |" in text


# --------------------------------------------------------------------------- FR-KD-02 追補（AC-016）


def test_allowlist_defaults_include_microsoft_learn_only() -> None:
    policy = ToolSearchPolicy.load(_REPO_ROOT / "hve" / "toolsearch" / "policy.json")
    assert policy.tool_allowlist_for("knowledge", "microsoft-learn") == (
        "microsoft_docs_search", "microsoft_docs_fetch", "microsoft_code_sample_search",
    )
    # FR-CLI-91: workiq-preview を workiq の代替として扱わないため既定に加えない。
    assert policy.tool_allowlist_for("knowledge", "workiq-preview") == ()
    forbidden = {"*", "create_entity", "update_entity", "delete_entity", "do_action", "call_function", "fetch_blob"}
    assert not forbidden & set(policy.tool_allowlist_for("knowledge", "microsoft-learn"))
    assert policy.resource_classifications["mcp_servers"]["microsoft-learn"] == "software-engineering"


# --------------------------------------------------------------------------- FR-KD-14（AC-018）


def _prompt_plan(tmp_path: Path, overrides: dict) -> Any:
    request = parse_request({
        "schema_version": 1, "goal": "設計を進める",
        "workflows": [{"workflow_id": "aas"}], "settings_overrides": overrides,
    })
    settings = settings_store.defaults()
    settings["options"]["workiq"] = True
    return prompt_execution.build_execution_plan(
        request, settings=settings, repo_root=tmp_path, head_commit="a" * 40,
        workiq_capability=workiq.WorkIQCapability(state="ready", reason_code="ready", enabled_server_names=("workiq",)),
    )


def test_prompt_overrides_workiq_false(tmp_path: Path) -> None:
    argv = list(_prompt_plan(tmp_path, {"workiq": False}).workflows[0].argv)
    assert "--no-workiq" in argv and "--workiq" not in argv


def test_prompt_overrides_knowledge_sources(tmp_path: Path) -> None:
    argv = list(_prompt_plan(tmp_path, {"knowledge_sources": "microsoft-learn"}).workflows[0].argv)
    index = argv.index("--knowledge-source")
    assert argv[index + 1] == "microsoft-learn"
    assert "--workiq" in argv


@pytest.mark.parametrize("overrides", [
    {"workiq": "yes"},
    {"workiq": 1},
    {"knowledge_sources": "bad name"},
    {"knowledge_sources": "ok,a/b"},
    {"knowledge_sources": 3},
])
def test_prompt_overrides_invalid_values_fail_closed(overrides: dict) -> None:
    with pytest.raises(PromptRequestError):
        parse_request({
            "schema_version": 1, "goal": "g",
            "workflows": [{"workflow_id": "aas"}], "settings_overrides": overrides,
        })


def test_prompt_overrides_empty_knowledge_sources_is_accepted() -> None:
    request = parse_request({
        "schema_version": 1, "goal": "g",
        "workflows": [{"workflow_id": "aas"}], "settings_overrides": {"knowledge_sources": ""},
    })
    assert request.settings_overrides == {"knowledge_sources": ""}
