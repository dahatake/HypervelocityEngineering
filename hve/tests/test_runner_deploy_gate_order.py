"""ASDW-WEB Step 1.3 の実行境界と gate 順序の契約。

Step 1.3 は HVE-owned native pipeline へ移行済みで、Copilot SDK セッション
（およびその permission 境界）は production から到達しない。本ファイルは
「native pipeline が実際に通る経路」だけを検証し、旧 Agent permission /
MCP 経路への回帰を機械的に検出する。

native pipeline 自体の stage / evidence 契約は
`test_runner_asdw_data_pipeline.py`、producer 生成前後の順序は
`test_runner_asdw_data_producer_generation.py` が固定する。
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
import shutil
import types
import uuid

import pytest

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import (
    StepRunner,
    _create_session_with_auto_reasoning_fallback,
    _require_trusted_asdw_data_deploy_mcp_servers,
)


_DATA_DEPLOY_AGENT = "Dev-Microservice-Azure-DataDeploy"

# Step 1.3 は APP-009 固定 producer だけを描画できるため、scope guard と
# bootstrap context を満たす最小の workflow_params を共有する。
_DATA_DEPLOY_WORKFLOW_PARAMS = {
    "app_ids": ["APP-009"],
    "resource_group": "test-resource-group",
    "data_location": "japaneast",
    "data_resource_suffix": "app009",
    "data_vnet_cidr": "10.40.0.0/16",
    "data_private_endpoint_subnet_cidr": "10.40.1.0/24",
    "data_aci_subnet_cidr": "10.40.2.0/24",
}


def _successful_native_pipeline_results():
    """全 7 stage 成功の StageResult 列を返す。"""
    from hve.asdw_data_script_launcher import StageResult

    sequence = (
        ("prep", 1),
        ("create", 1),
        ("registration", 1),
        ("verify", 1),
        ("create", 2),
        ("registration", 2),
        ("verify", 2),
    )
    return tuple(
        StageResult(
            stage=stage,
            attempt=attempt,
            exit_code=0,
            reached=True,
            evidence=f"{stage}-{attempt}",
        )
        for stage, attempt in sequence
    )


def _patch_native_pipeline(monkeypatch, *, pipeline_results, calls=None) -> None:
    """HVE-owned native pipeline を副作用なしで差し替える。

    producer 生成・env snapshot・pipeline 実行だけを fake にし、
    gate 順序と分岐は production の実装をそのまま通す。
    `calls` を渡すと native pipeline の実行を `"native"` として記録し、
    「native まで到達したか」を先行 gate 失敗と区別できる。
    """
    monkeypatch.setattr(
        "hve.runner.ensure_asdw_data_producers",
        lambda *_args, **_kwargs: types.SimpleNamespace(
            status="reused",
            audit_mode="sql-ledger-digest",
        ),
    )
    monkeypatch.setattr(
        "hve.runner._resolve_asdw_data_deploy_subscription_id",
        lambda: "00000000-0000-0000-0000-000000000001",
    )
    monkeypatch.setattr(
        "hve.runner._build_asdw_data_deploy_environment_snapshot",
        lambda *_args, **_kwargs: {
            "RESOURCE_GROUP": "test-resource-group",
            "LOCATION": "japaneast",
            "RESOURCE_SUFFIX": "app009",
        },
    )

    def _fake_execute_pipeline(**_kwargs):
        if calls is not None:
            calls.append("native")
        return pipeline_results

    monkeypatch.setattr("hve.runner.execute_pipeline", _fake_execute_pipeline)


def _forbid_sdk_client(monkeypatch, sdk_calls: list[str]) -> None:
    """Step 1.3 が SDK client を作ろうとしたら即座に検出する。"""

    def unexpected_client(**_kwargs):
        sdk_calls.append("client")
        raise AssertionError("Step 1.3 must not construct a Copilot SDK client")

    monkeypatch.setattr(
        "hve.copilot_client_factory.create_copilot_client",
        unexpected_client,
    )


def _data_deploy_runner(run_id: str) -> StepRunner:
    return StepRunner(
        config=SDKConfig(run_id=run_id),
        console=Console(verbose=False, quiet=True),
        workflow_params=dict(_DATA_DEPLOY_WORKFLOW_PARAMS),
    )


# ---------------------------------------------------------------------------
# gate 順序（ソース契約）
# ---------------------------------------------------------------------------


def test_orchestrator_always_forwards_workflow_id_to_run_step() -> None:
    """Step 1.3 の native 経路は `workflow_id == "asdw-web"` に依存する。

    orchestrator が `workflow_id` を渡さなくなると Step 1.3 が旧 SDK 経路へ
    無音で落ちるため、呼び出し側が常に渡すことを機械的に固定する。
    """
    import hve.orchestrator as orchestrator_module

    source = Path(orchestrator_module.__file__).read_text(encoding="utf-8")
    call_index = source.index("await runner.run_step(")
    call_block = source[call_index:source.index(")", source.index("fanout_meta=", call_index))]

    assert source.count("await runner.run_step(") == 1
    assert "workflow_id=workflow_id," in call_block


def test_deploy_ac_gate_precedes_output_paths_gate_without_duplicate_invocation() -> None:
    """AC-1 failure must remain the primary failure when an output is also missing."""
    source = inspect.getsource(StepRunner.run_step)

    # ASDW native data pipeline 分岐は SDK 起動前に早期 return するため、
    # native 経路と SDK 経路は排他。各経路で AC gate は 1 回だけ呼ばれる。
    sdk_boundary = source.index("# --- SDK インポート確認 ---")
    native_path = source[:sdk_boundary]
    sdk_path = source[sdk_boundary:]

    assert native_path.count("_run_deploy_ac_gate(") == 1
    assert sdk_path.count("_run_deploy_ac_gate(") == 1
    assert "_check_output_paths_gate(" not in native_path
    assert sdk_path.index("_run_deploy_ac_gate(") < sdk_path.index("_check_output_paths_gate(")


def test_data_deploy_registration_gate_runs_only_after_main_task() -> None:
    """Step 1.3 producer outputs are first checked only after main creation."""
    source = inspect.getsource(StepRunner.run_step)
    main_task = source.index("main_response = await")
    pre_gate = source.index("include_registration=False")
    post_main_gate = source.index("post_main_contract_errors = (")
    split_fork = source.index("_maybe_run_split_fork(")

    assert pre_gate < main_task < post_main_gate < split_fork
    assert (
        source.index("self._run_asdw_data_producer_contract_gate(", post_main_gate)
        < split_fork
    )
    assert (
        inspect.signature(StepRunner._run_asdw_data_verify_contract_gate)
        .parameters["include_registration"].default
        is True
    )


def test_data_deploy_gate_guarantee_boundary_is_pre_verify_post_fresh_producer() -> None:
    """registrationはfreshness対応producer gateだけがpost/finalで検査する。"""
    source = inspect.getsource(StepRunner.run_step)

    assert source.count("_run_asdw_data_verify_contract_gate(") == 3
    assert source.count("include_registration=False") == 3
    assert source.index("include_registration=False") < source.index("main_response = await")
    assert source.index("post_main_contract_errors") > source.index("main_response = await")
    assert source.rindex("verify_contract_errors =") > source.index("_maybe_run_split_fork(")


def test_permission_gate_is_installed_before_main_session() -> None:
    source = inspect.getsource(StepRunner.run_step)

    permission_gate = source.index("self._build_step_permission_handler(")
    session_creation = source.index("self._create_main_session(")

    assert permission_gate < session_creation


# ---------------------------------------------------------------------------
# 旧 Agent permission / MCP dead path が復活していないこと
# ---------------------------------------------------------------------------


def test_data_deploy_agent_permission_and_mcp_dead_path_stay_removed() -> None:
    """Step 1.3 は native 化により Agent permission / MCP 境界を持たない。

    native pipeline は SDK import より前に `return` するため、これらの
    シンボルは production から到達不能だった。復活は「到達しない安全境界」を
    増やすだけで実効性が無く、保守コストと誤解を生むため機械的に禁止する。
    """
    import hve.runner as runner_module

    assert not hasattr(runner_module, "_build_asdw_data_deploy_permission_handler")
    assert not hasattr(runner_module, "_asdw_data_deploy_allowed_write_roots")
    assert not hasattr(StepRunner, "_verify_asdw_data_deploy_session_mcp_servers")
    assert not hasattr(StepRunner, "_run_asdw_data_deploy_terminal_static_failure_gate")

    handler_source = inspect.getsource(StepRunner._build_step_permission_handler)
    assert "_is_asdw_data_deploy_step" not in handler_source
    assert "PermissionDecisionReject" not in handler_source

    sub_session_source = inspect.getsource(StepRunner._build_sub_session_opts)
    # 削除前は `opts["enable_config_discovery"] = False` が `if is_asdw_data_deploy:` の
    # 内側にあったため、当該キーの有無が死パス検出の代理になっていた。FR-CLI-76 (v2.41) が
    # 事前 QA サブセッションで同キーを正当に使うようになったので、DataDeploy 由来の
    # シンボルそのものを禁止する（代理より広く、かつ本来の意図に一致する）。
    assert "asdw_data_deploy" not in sub_session_source


def test_general_sub_session_mcp_routing_is_unchanged() -> None:
    """一般 Step の sub-session MCP routing は DataDeploy 削除の影響を受けない。"""
    runner = StepRunner(
        config=SDKConfig(
            mcp_servers={
                "azure": {"command": "az-mcp"},
                "microsoft-learn": {
                    "type": "http",
                    "url": "https://learn.microsoft.com/api/mcp",
                },
            },
        ),
        console=Console(verbose=False, quiet=True),
    )
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            StepRunner,
            "_build_step_permission_handler",
            lambda *_args, **_kwargs: "permission-handler",
        )
        options = runner._build_sub_session_opts(
            runner.config.model,
            step_id="2.3",
            suffix="pre-qa",
            custom_agent="Dev-Microservice-Azure-AgentCoding",
        )

    assert set(options["mcp_servers"]) == {"azure", "microsoft-learn"}
    assert "enable_config_discovery" not in options


def test_data_deploy_requires_repository_pinned_microsoft_learn_before_session_is_kept() -> None:
    """Learn MCP の repository-pinned 検査は一般 Foundry 経路と共有され続ける。"""
    assert callable(_require_trusted_asdw_data_deploy_mcp_servers)


@pytest.mark.parametrize(
    "mcp_payload",
    (
        None,
        "{not-json",
        '{"mcpServers":{"microsoft-learn":{"type":"http",'
        '"url":"https://learn.microsoft.com/api/mcp"}}}',
        '{"mcpServers":{"microsoft-learn":{"type":"http",'
        '"url":"https://evil.example/mcp"}}}',
    ),
)
def test_data_deploy_requires_repository_pinned_microsoft_learn_before_session(
    mcp_payload: str | None,
    tmp_path,
    monkeypatch,
) -> None:
    config = tmp_path / ".github" / ".mcp.json"
    if mcp_payload is not None:
        config.parent.mkdir(parents=True)
        config.write_text(mcp_payload, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="repository-pinned Microsoft Learn"):
        _require_trusted_asdw_data_deploy_mcp_servers(tmp_path)


def test_discovery_false_is_not_stripped_for_old_sdk() -> None:
    calls: list[dict] = []

    class _Client:
        async def create_session(self, **options):
            calls.append(options)
            raise TypeError(
                "create_session() got an unexpected keyword argument "
                "'enable_config_discovery'"
            )

    with pytest.raises(TypeError, match="enable_config_discovery"):
        asyncio.run(
            _create_session_with_auto_reasoning_fallback(
                _Client(),
                {
                    "enable_config_discovery": False,
                    "streaming": True,
                },
            )
        )

    assert len(calls) == 1
    assert calls[0]["enable_config_discovery"] is False


def test_console_exposes_permission_reject_event_method() -> None:
    """本番 Console は origin event 発行メソッドを実装する。

    MagicMock は任意の属性を自動生成するため、呼び出し側だけの検証では
    本番で属性が存在せず握り潰される偽 GREEN を検出できない。実 Console が
    callable な ``permission_reject_event`` を公開することを固定する。
    """
    assert callable(getattr(Console, "permission_reject_event", None))


# ---------------------------------------------------------------------------
# run_step の実行境界（native pipeline）
# ---------------------------------------------------------------------------


def test_data_deploy_run_step_stops_before_workdir_on_cross_run_root(
    tmp_path,
    monkeypatch,
) -> None:
    other_run = tmp_path / "work" / "run" / "other-run"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    monkeypatch.setenv("HVE_WORK_ROOT", str(other_run))
    runner = StepRunner(
        config=SDKConfig(run_id="run-1"),
        console=Console(verbose=False, quiet=True),
    )

    result = asyncio.run(
        runner.run_step(
            "1.3",
            "Data deploy",
            "must stop before SDK",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
        )
    )

    assert result is False
    assert not other_run.exists()


def test_data_deploy_runs_pre_verify_gate_then_native_pipeline_without_split_fork(
    monkeypatch,
) -> None:
    """Step 1.3 は pre-verify gate 後に native pipeline へ入り、SDK 経路を使わない。

    旧契約（pre-gate → main → post-main producer gate → final gate）は、
    Step 1.3 の HVE-owned native pipeline 化により置き換えられた。
    """
    calls: list[str] = []
    sdk_calls: list[str] = []
    split_fork_called = False
    deploy_gate_called = False

    run_id = f"pytest-registration-gate-{uuid.uuid4().hex}"
    runner = _data_deploy_runner(run_id)
    monkeypatch.setenv("HVE_RUN_ID", run_id)
    monkeypatch.setenv(
        "HVE_WORK_ROOT", str((Path.cwd() / "work" / "run" / run_id).resolve())
    )

    async def split_fork_must_not_run(**_kwargs):
        nonlocal split_fork_called
        split_fork_called = True
        return False

    def fake_gate(_step_id, _agent, *, include_registration=True):
        calls.append(f"gate:{include_registration}")
        return ["stale registration must remain producer-gate owned"] if include_registration else []

    def fake_producer_gate(_step_id, _agent, *, session_start=None):
        calls.append(f"producer:{session_start is not None}")
        return ["registration contract failed"]

    def deploy_gate_must_not_run(*_args, **_kwargs):
        nonlocal deploy_gate_called
        deploy_gate_called = True
        return []

    _forbid_sdk_client(monkeypatch, sdk_calls)
    monkeypatch.setattr(runner, "_maybe_run_split_fork", split_fork_must_not_run)
    monkeypatch.setattr(runner, "_run_asdw_data_verify_contract_gate", fake_gate)
    monkeypatch.setattr(
        runner,
        "_run_asdw_data_producer_contract_gate",
        fake_producer_gate,
    )
    monkeypatch.setattr(runner, "_run_deploy_ac_gate", deploy_gate_must_not_run)
    _patch_native_pipeline(monkeypatch, pipeline_results=(), calls=calls)

    run_root = Path("work") / "run" / run_id
    try:
        result = asyncio.run(
            runner.run_step(
                "1.3",
                "Data deploy",
                "generate registration script",
                custom_agent=_DATA_DEPLOY_AGENT,
                workflow_id="asdw-web",
            )
        )
    finally:
        shutil.rmtree(run_root, ignore_errors=True)

    assert result is False
    # pre-verify gate → native pipeline の順。SDK main session / post-main producer gate は無い。
    assert calls == ["gate:False", "native"]
    assert sdk_calls == []
    assert split_fork_called is False
    assert deploy_gate_called is False


def test_data_deploy_preflight_failure_stops_before_native_pipeline(
    monkeypatch,
) -> None:
    """runtime context 検査に失敗した Step 1.3 は native pipeline を起動しない。"""
    calls: list[str] = []
    sdk_calls: list[str] = []

    run_id = f"pytest-preflight-fatal-{uuid.uuid4().hex}"
    runner = _data_deploy_runner(run_id)
    monkeypatch.setenv("HVE_RUN_ID", run_id)

    def fake_gate(_step_id, _agent, *, include_registration=True):
        calls.append(f"gate:{include_registration}")
        return []

    _forbid_sdk_client(monkeypatch, sdk_calls)
    monkeypatch.setattr(runner, "_run_asdw_data_verify_contract_gate", fake_gate)
    _patch_native_pipeline(monkeypatch, pipeline_results=(), calls=calls)

    run_root = Path("work") / "run" / run_id
    try:
        result = asyncio.run(
            runner.run_step(
                "1.3",
                "Data deploy",
                "generate registration script",
                custom_agent=_DATA_DEPLOY_AGENT,
                workflow_id="asdw-web",
            )
        )
    finally:
        shutil.rmtree(run_root, ignore_errors=True)

    assert result is False
    assert "native" not in calls
    assert sdk_calls == []


def test_data_deploy_success_path_runs_pre_verify_gate_then_native_pipeline_only(
    monkeypatch,
) -> None:
    """成功した Step 1.3 は pre-verify gate 後に native pipeline だけを実行する。"""
    calls: list[str] = []
    sdk_calls: list[str] = []
    producer_session_starts: list[float | None] = []

    run_id = f"pytest-registration-success-{uuid.uuid4().hex}"
    runner = _data_deploy_runner(run_id)
    monkeypatch.setenv("HVE_RUN_ID", run_id)
    monkeypatch.setenv(
        "HVE_WORK_ROOT", str((Path.cwd() / "work" / "run" / run_id).resolve())
    )

    async def fake_split_fork(**_kwargs):
        calls.append("split")
        return True

    def fake_gate(_step_id, _agent, *, include_registration=True):
        calls.append(f"gate:{include_registration}")
        return ["stale registration must remain producer-gate owned"] if include_registration else []

    def fake_producer_gate(_step_id, _agent, *, session_start=None):
        calls.append("producer")
        producer_session_starts.append(session_start)
        return []

    _forbid_sdk_client(monkeypatch, sdk_calls)
    monkeypatch.setattr(runner, "_maybe_run_split_fork", fake_split_fork)
    monkeypatch.setattr(runner, "_run_asdw_data_verify_contract_gate", fake_gate)
    monkeypatch.setattr(
        runner,
        "_run_asdw_data_producer_contract_gate",
        fake_producer_gate,
    )
    monkeypatch.setattr(runner, "_run_tdd_report_gate", lambda *_args: [])
    monkeypatch.setattr(
        runner, "_run_asdw_ui_red_unresolved_contract_gate", lambda *_args: []
    )
    monkeypatch.setattr(runner, "_run_deploy_ac_gate", lambda *_args: [])
    monkeypatch.setattr("hve.runner._check_output_paths_gate", lambda *_args: [])
    _patch_native_pipeline(
        monkeypatch,
        pipeline_results=_successful_native_pipeline_results(),
        calls=calls,
    )
    monkeypatch.setattr(
        "hve.runner._write_asdw_data_deploy_evidence", lambda *_args, **_kwargs: []
    )

    run_root = Path("work") / "run" / run_id
    try:
        result = asyncio.run(
            runner.run_step(
                "1.3",
                "Data deploy",
                "generate registration script",
                custom_agent=_DATA_DEPLOY_AGENT,
                workflow_id="asdw-web",
            )
        )
    finally:
        shutil.rmtree(run_root, ignore_errors=True)

    assert result is True
    # 成功パスでも SDK main session / split-fork / post-main producer gate は走らない。
    assert calls == ["gate:False", "native"]
    assert sdk_calls == []
    assert producer_session_starts == []


def test_data_deploy_failed_stage_fails_step_before_evidence_gates(
    monkeypatch,
) -> None:
    """非 0 exit の stage が 1 つでもあれば Step は失敗し、成果物 gate へ進まない。"""
    from hve.asdw_data_script_launcher import StageResult

    calls: list[str] = []
    sdk_calls: list[str] = []
    tdd_gate_called = False

    run_id = f"pytest-native-stage-failure-{uuid.uuid4().hex}"
    runner = _data_deploy_runner(run_id)
    monkeypatch.setenv("HVE_RUN_ID", run_id)
    monkeypatch.setenv(
        "HVE_WORK_ROOT", str((Path.cwd() / "work" / "run" / run_id).resolve())
    )

    def tdd_gate_must_not_run(*_args, **_kwargs):
        nonlocal tdd_gate_called
        tdd_gate_called = True
        return []

    _forbid_sdk_client(monkeypatch, sdk_calls)
    monkeypatch.setattr(
        runner,
        "_run_asdw_data_verify_contract_gate",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(runner, "_run_tdd_report_gate", tdd_gate_must_not_run)
    _patch_native_pipeline(
        monkeypatch,
        pipeline_results=(
            StageResult(
                stage="registration",
                attempt=1,
                exit_code=23,
                reached=True,
                evidence="process-exit=23",
            ),
        ),
        calls=calls,
    )
    monkeypatch.setattr(
        "hve.runner._write_asdw_data_deploy_evidence", lambda *_args, **_kwargs: []
    )

    run_root = Path("work") / "run" / run_id
    try:
        result = asyncio.run(
            runner.run_step(
                "1.3",
                "Data deploy",
                "failing native stage",
                custom_agent=_DATA_DEPLOY_AGENT,
                workflow_id="asdw-web",
            )
        )
    finally:
        shutil.rmtree(run_root, ignore_errors=True)

    assert result is False
    assert calls == ["native"]
    assert sdk_calls == []
    assert tdd_gate_called is False
