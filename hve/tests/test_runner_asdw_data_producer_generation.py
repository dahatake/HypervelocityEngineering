"""ASDW-WEB Step 1.3 producer generation must precede Agent startup."""

from __future__ import annotations

import ast
import asyncio
import builtins
import os
from pathlib import Path
import sys
import types
from typing import Mapping, cast

import pytest

from hve.asdw_data_script_generator import (
    AsdwDataScriptGenerationError,
    AsdwDataScriptGenerationResult,
)
from hve.asdw_data_script_launcher import StageResult
from hve.config import SDKConfig
from hve.console import Console
import hve.runner as runner_module
from hve.runner import StepRunner


_ORIGINAL_EXECUTE_PIPELINE = runner_module.execute_pipeline


_DATA_DEPLOY_AGENT = "Dev-Microservice-Azure-DataDeploy"
_DATA_TEST_CODING_AGENT = "Dev-Microservice-Azure-DataTestCoding"
_DEFAULT_GENERATION_RESULT = object()
_AUDIT_MODE = "sql-ledger-digest"
_COMPLETE_RUNTIME_ENVIRONMENT = {
    key: f"value-{key.casefold().replace('_', '-')}"
    for key in runner_module._ASDW_DATA_DEPLOY_COMMON_ENVIRONMENT_KEYS
    if key != "RESOURCE_GROUP"
}
_COMPLETE_RUNTIME_ENVIRONMENT.update(
    {
        "DATA_NETWORK_MODE": "private",
        "SQL_DB_SVC12": "value-sql-db-svc12",
        "SQL_AUDIT_TABLE": "value-sql-audit-table",
    }
)
_BOOTSTRAP_WORKFLOW_PARAMS = {
    "data_location": "japaneast",
    "data_resource_suffix": "app009",
    "data_vnet_cidr": "10.40.0.0/16",
    "data_private_endpoint_subnet_cidr": "10.40.1.0/24",
    "data_aci_subnet_cidr": "10.40.2.0/24",
}
# The runner resolves this from `az account show`; tests must never shell out.
_SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _restore_step_identity_environment():
    """run_step writes these process globals without using monkeypatch."""
    names = ("HVE_STEP_ID", "HVE_AGENT_ID")
    missing = object()
    original = {name: os.environ.get(name, missing) for name in names}
    yield
    for name, value in original.items():
        if value is missing:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def _install_fake_copilot_modules(monkeypatch, events: list[str]) -> None:
    """Provide only the SDK types touched before the fake main session starts."""
    copilot = types.ModuleType("copilot")
    copilot.__path__ = []

    class ObservedSessionModule(types.ModuleType):
        def __getattribute__(self, name: str):
            if name == "PermissionHandler" and "sdk-import" not in events:
                events.append("sdk-import")
            return super().__getattribute__(name)

    session = ObservedSessionModule("copilot.session")
    generated = types.ModuleType("copilot.generated")
    generated.__path__ = []
    rpc = types.ModuleType("copilot.generated.rpc")

    class PermissionHandler:
        @staticmethod
        async def approve_all(*_args, **_kwargs):
            return True

    class PermissionDecisionApproveOnce:
        pass

    class PermissionDecisionReject:
        def __init__(self, *, feedback: str = "") -> None:
            self.feedback = feedback

    setattr(session, "PermissionHandler", PermissionHandler)
    setattr(rpc, "PermissionDecisionApproveOnce", PermissionDecisionApproveOnce)
    setattr(rpc, "PermissionDecisionReject", PermissionDecisionReject)
    monkeypatch.setitem(sys.modules, "copilot", copilot)
    monkeypatch.setitem(sys.modules, "copilot.session", session)
    monkeypatch.setitem(sys.modules, "copilot.generated", generated)
    monkeypatch.setitem(sys.modules, "copilot.generated.rpc", rpc)


def _run_step_with_generation_probe(
    tmp_path: Path,
    monkeypatch,
    *,
    step_id: str,
    custom_agent: str,
    workflow_id: str,
    generation_status: str = "reused",
    audit_mode: str = _AUDIT_MODE,
    generation_result: object = _DEFAULT_GENERATION_RESULT,
    generation_error: bool = False,
    generation_exception: BaseException | None = None,
    runtime_errors: list[str] | None = None,
    input_errors: list[str] | None = None,
    dry_run: bool = False,
    captured_errors: list[str] | None = None,
    captured_client_kwargs: list[dict[str, object]] | None = None,
    captured_pipeline_kwargs: list[dict[str, object]] | None = None,
    native_evidence_gates: bool = False,
    workflow_params: Mapping[str, object] | None = None,
) -> tuple[bool, list[str], list[Path], list[str]]:
    """Run through the main turn with all unrelated post-session gates neutralized."""
    run_id = "run-asdw-producer-generation"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", run_id)
    monkeypatch.setenv(
        "HVE_WORK_ROOT",
        str(tmp_path / "work" / "run" / run_id),
    )
    for name, value in _COMPLETE_RUNTIME_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    events: list[str] = []
    generator_roots: list[Path] = []
    subprocess_calls: list[str] = []

    def fake_generator(repo_root: Path) -> object:
        events.append("generator")
        generator_roots.append(Path(repo_root).resolve())
        if generation_exception is not None:
            raise generation_exception
        if generation_error:
            raise AsdwDataScriptGenerationError(
                "sanitized injected generation failure"
            )
        if generation_result is not _DEFAULT_GENERATION_RESULT:
            return cast(AsdwDataScriptGenerationResult, generation_result)
        return AsdwDataScriptGenerationResult(
            status=generation_status,
            summary="producer scripts test result",
            audit_mode=audit_mode,
        )

    # Sub-007 will import this exact symbol into hve.runner. raising=False keeps
    # Sub-006 RED focused on the missing invocation rather than collection/setup.
    monkeypatch.setattr(
        runner_module,
        "ensure_asdw_data_producers",
        fake_generator,
        raising=False,
    )

    monkeypatch.setattr(
        runner_module,
        "_resolve_asdw_data_deploy_subscription_id",
        lambda: _SUBSCRIPTION_ID,
    )

    def unexpected_subprocess(*_args, **_kwargs):
        subprocess_calls.append("subprocess")
        raise AssertionError("producer generation failure must precede subprocess")

    monkeypatch.setattr(runner_module.subprocess, "run", unexpected_subprocess)
    monkeypatch.setattr(runner_module.subprocess, "Popen", unexpected_subprocess)
    monkeypatch.setattr(os, "system", unexpected_subprocess)
    monkeypatch.setattr(os, "popen", unexpected_subprocess)

    async def unexpected_async_subprocess(*_args, **_kwargs):
        subprocess_calls.append("async-subprocess")
        raise AssertionError("producer generation failure must precede subprocess")

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        unexpected_async_subprocess,
    )
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_shell",
        unexpected_async_subprocess,
    )
    _install_fake_copilot_modules(monkeypatch, events)

    class FakeSession:
        def on(self, _callback) -> None:
            return None

        async def disconnect(self) -> None:
            return None

    class FakeClient:
        async def stop(self) -> None:
            return None

    def fake_client_factory(**_kwargs):
        events.append("client-factory")
        if captured_client_kwargs is not None:
            captured_client_kwargs.append(dict(_kwargs))
        return FakeClient()

    async def fake_start_client(_client, *, console) -> None:
        events.append("client-start")

    async def fake_session(_self, **_kwargs):
        events.append("session-created")
        return FakeSession()

    async def fake_main_turn(
        _self,
        _session,
        _prompt,
        *,
        timeout,
        step_id,
    ):
        events.append("main-turn")
        return object()

    async def fake_split_fork(**_kwargs) -> bool:
        events.append("split-fork")
        return True

    runner = StepRunner(
        config=SDKConfig(
            run_id=run_id,
            dry_run=dry_run,
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
        ),
        console=Console(verbose=False, quiet=True),
        workflow_params=workflow_params
        if workflow_params is not None
        else {
            "resource_group": "test-resource-group",
            "app_ids": ["APP-009"],
            "app_id": "APP-009",
            **_BOOTSTRAP_WORKFLOW_PARAMS,
        },
    )
    original_console_event = runner.console.event

    def record_console_event(message, *args, **kwargs):
        if "ASDW data producers:" in str(message):
            events.append("generation-console")
        return original_console_event(message, *args, **kwargs)

    monkeypatch.setattr(runner.console, "event", record_console_event)
    if captured_errors is not None:
        monkeypatch.setattr(runner.console, "error", captured_errors.append)
    original_ensure_step_work_dir = runner_module._ensure_step_work_dir

    def observed_ensure_step_work_dir(*args, **kwargs):
        events.append("work-dir")
        return original_ensure_step_work_dir(*args, **kwargs)

    monkeypatch.setattr(
        runner_module,
        "_ensure_step_work_dir",
        observed_ensure_step_work_dir,
    )
    monkeypatch.setattr(runner_module, "_start_client_with_retry", fake_start_client)
    monkeypatch.setattr(
        "hve.copilot_client_factory.create_copilot_client",
        fake_client_factory,
    )
    monkeypatch.setattr("hve.prompt_loader.load_prompt", lambda _agent: "")
    monkeypatch.setattr(runner_module, "_extract_text", lambda _response: "")

    def fake_runtime_gate(*_args, **_kwargs):
        events.append("runtime-gate")
        return list(runtime_errors or [])

    monkeypatch.setattr(
        runner_module,
        "_validate_asdw_data_deploy_runtime_context",
        fake_runtime_gate,
    )
    monkeypatch.setattr(
        runner_module,
        "_require_trusted_asdw_data_deploy_mcp_servers",
        lambda *_args, **_kwargs: {"microsoft-learn": {}},
    )
    monkeypatch.setattr(
        runner,
        "_create_main_session",
        types.MethodType(fake_session, runner),
    )
    monkeypatch.setattr(
        runner,
        "_send_and_wait_with_model_call_failure_guard",
        types.MethodType(fake_main_turn, runner),
    )
    monkeypatch.setattr(runner, "_maybe_run_split_fork", fake_split_fork)

    def fake_input_gate(*_args, **_kwargs):
        is_pre_session_call = "main-turn" not in events
        if is_pre_session_call:
            assert _kwargs.get("include_registration") is False
            events.append("input-gate")
            return list(input_errors or [])
        return []

    monkeypatch.setattr(
        runner,
        "_run_asdw_data_verify_contract_gate",
        fake_input_gate,
    )
    monkeypatch.setattr(
        runner,
        "_run_asdw_data_producer_contract_gate",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        runner,
        "_run_asdw_data_deploy_preflight_failure_gate",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        runner,
        "_run_ai_agent_capability_gate",
        lambda *_args, **_kwargs: [],
    )
    if not native_evidence_gates:
        monkeypatch.setattr(
            runner,
            "_run_tdd_report_gate",
            lambda *_args, **_kwargs: [],
        )
    monkeypatch.setattr(
        runner,
        "_run_asdw_ui_red_unresolved_contract_gate",
        lambda *_args, **_kwargs: [],
    )
    if not native_evidence_gates:
        monkeypatch.setattr(
            runner,
            "_run_deploy_ac_gate",
            lambda *_args, **_kwargs: [],
        )
    monkeypatch.setattr(
        runner_module,
        "_check_output_paths_gate",
        lambda *_args, **_kwargs: [],
    )
    if runner_module.execute_pipeline is _ORIGINAL_EXECUTE_PIPELINE:
        def fake_native_pipeline(**_kwargs):
            events.append("native-pipeline")
            if captured_pipeline_kwargs is not None:
                captured_pipeline_kwargs.append(dict(_kwargs))
            return (
                StageResult(
                    stage="verify",
                    attempt=2,
                    exit_code=0,
                    reached=True,
                    evidence="process-exit=0",
                ),
            )

        monkeypatch.setattr(
            runner_module,
            "execute_pipeline",
            fake_native_pipeline,
        )

    result = asyncio.run(
        runner.run_step(
            step_id,
            "Data producer generation probe",
            "main task",
            custom_agent=custom_agent,
            workflow_id=workflow_id,
        )
    )
    return result, events, generator_roots, subprocess_calls


@pytest.mark.parametrize("generation_status", ("reused", "regenerated"))
def test_asdw_web_data_deploy_generates_once_before_client_session_and_main_turn(
    generation_status: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            generation_status=generation_status,
        )
    )

    assert result is True
    assert generator_roots == [tmp_path.resolve()]
    assert events == [
        "runtime-gate",
        "input-gate",
        "work-dir",
        "generator",
        "generation-console",
        "native-pipeline",
    ]
    assert subprocess_calls == []


def test_data_deploy_environment_snapshot_uses_formal_param_and_strips_hve_owned_values() -> None:
    process_environment = {
        **_COMPLETE_RUNTIME_ENVIRONMENT,
        "RESOURCE_GROUP": "stale-ambient-resource-group",
        "DATA_CREATE_RUN_ID": "a" * 32,
        "DATA_REGISTER_RUN_ID": "b" * 32,
        "DATA_VERIFY_RUN_ID": "c" * 32,
        "AUDIT_RECORD_JSON": "stale-audit-payload",
        "DATA_DEPLOY_ENV": "stale-data-deploy.env",
        "UNRELATED_RUNTIME_INPUT": "preserved",
    }

    snapshot = runner_module._build_asdw_data_deploy_environment_snapshot(
        {"resource_group": "formal-resource-group"},
        process_environment,
        _AUDIT_MODE,
    )

    assert snapshot["RESOURCE_GROUP"] == "formal-resource-group"
    assert snapshot["UNRELATED_RUNTIME_INPUT"] == "preserved"
    for key in (
        "DATA_CREATE_RUN_ID",
        "DATA_REGISTER_RUN_ID",
        "DATA_VERIFY_RUN_ID",
        "AUDIT_RECORD_JSON",
        "DATA_DEPLOY_ENV",
    ):
        assert key not in snapshot
    with pytest.raises(TypeError):
        snapshot["RESOURCE_GROUP"] = "mutated"  # type: ignore[index]


@pytest.mark.parametrize(
    "missing_key",
    tuple(
        key
        for key in runner_module._ASDW_DATA_DEPLOY_COMMON_ENVIRONMENT_KEYS
        if key
        not in ("RESOURCE_GROUP", runner_module._ASDW_DATA_DEPLOY_READ_BACK_KEY)
    )
    + ("SQL_DB_SVC12", "SQL_AUDIT_TABLE"),
)
def test_data_deploy_environment_snapshot_rejects_each_missing_input(
    missing_key: str,
) -> None:
    process_environment = dict(_COMPLETE_RUNTIME_ENVIRONMENT)
    process_environment.pop(missing_key)

    with pytest.raises(ValueError, match=missing_key):
        runner_module._build_asdw_data_deploy_environment_snapshot(
            {"resource_group": "formal-resource-group"},
            process_environment,
            _AUDIT_MODE,
        )


def test_acl_environment_snapshot_requires_only_the_acl_audit_value() -> None:
    process_environment = dict(_COMPLETE_RUNTIME_ENVIRONMENT)
    process_environment.pop("SQL_DB_SVC12")
    process_environment.pop("SQL_AUDIT_TABLE")
    process_environment["CONFIDENTIAL_LEDGER_COLLECTION"] = "audit-collection"

    snapshot = runner_module._build_asdw_data_deploy_environment_snapshot(
        {"resource_group": "formal-resource-group"},
        process_environment,
        "acl-direct",
    )

    assert snapshot["CONFIDENTIAL_LEDGER_COLLECTION"] == "audit-collection"
    assert "SQL_DB_SVC12" not in snapshot
    assert "SQL_AUDIT_TABLE" not in snapshot


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("RESOURCE_GROUP", ""),
        ("RESOURCE_GROUP", " whitespace "),
        ("LOCATION", "eastus\nINJECTED=value"),
        ("DATA_NETWORK_MODE", "public"),
    ),
)
def test_data_deploy_environment_snapshot_rejects_invalid_values(
    key: str,
    value: str,
) -> None:
    process_environment = dict(_COMPLETE_RUNTIME_ENVIRONMENT)
    workflow_params = {"resource_group": "formal-resource-group"}
    if key == "RESOURCE_GROUP":
        workflow_params["resource_group"] = value
    else:
        process_environment[key] = value

    with pytest.raises(ValueError):
        runner_module._build_asdw_data_deploy_environment_snapshot(
            workflow_params,
            process_environment,
            _AUDIT_MODE,
        )


def test_data_deploy_passes_one_frozen_environment_to_local_copilot_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline_kwargs: list[dict[str, object]] = []

    result, events, _roots, _subprocess_calls = _run_step_with_generation_probe(
        tmp_path,
        monkeypatch,
        step_id="1.3",
        custom_agent=_DATA_DEPLOY_AGENT,
        workflow_id="asdw-web",
        captured_pipeline_kwargs=pipeline_kwargs,
    )

    assert result is True
    assert events.index("generator") < events.index("native-pipeline")
    assert len(pipeline_kwargs) == 1
    runtime_environment = cast(
        Mapping[str, str],
        pipeline_kwargs[0]["environment"],
    )
    assert runtime_environment["RESOURCE_GROUP"] == "test-resource-group"
    assert runtime_environment["DATA_NETWORK_MODE"] == "private"
    assert "DATA_VERIFY_RUN_ID" not in runtime_environment


def test_data_deploy_bootstrap_context_overrides_ambient_runtime_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pipeline_kwargs: list[dict[str, object]] = []
    monkeypatch.setenv("LOCATION", "ambient-location")
    monkeypatch.setenv("DATA_VERIFY_ACI_IMAGE", "ambient.example/verify:stale")
    monkeypatch.setenv("DATA_VNET_CIDR", "192.0.2.0/24")

    result, _events, _roots, _subprocess_calls = _run_step_with_generation_probe(
        tmp_path,
        monkeypatch,
        step_id="1.3",
        custom_agent=_DATA_DEPLOY_AGENT,
        workflow_id="asdw-web",
        captured_pipeline_kwargs=pipeline_kwargs,
    )

    assert result is True
    runtime_environment = cast(
        Mapping[str, str],
        pipeline_kwargs[0]["environment"],
    )
    assert runtime_environment["LOCATION"] == "japaneast"
    assert runtime_environment["DATA_VERIFY_ACI_IMAGE"].endswith(
        ".azurecr.io/hve-asdw-data-verify:app009"
    )
    assert runtime_environment["DATA_VNET_CIDR"] == "10.40.0.0/16"


def test_data_deploy_rejects_bootstrap_resource_group_conflict():
    with pytest.raises(ValueError, match="does not match"):
        runner_module._build_asdw_data_deploy_environment_snapshot(
            {"resource_group": "rg-workflow"},
            _COMPLETE_RUNTIME_ENVIRONMENT,
            _AUDIT_MODE,
            {
                "RESOURCE_GROUP": "rg-bootstrap",
                "LOCATION": "japaneast",
                "RESOURCE_SUFFIX": "app009",
                "DATA_VNET_CIDR": "10.40.0.0/16",
                "DATA_PRIVATE_ENDPOINT_SUBNET_CIDR": "10.40.1.0/24",
                "DATA_ACI_SUBNET_CIDR": "10.40.2.0/24",
                "DATA_VERIFY_ACR_NAME": "hveasdwapp009deadbeef",
                "DATA_VERIFY_ACI_IMAGE": (
                    "hveasdwapp009deadbeef.azurecr.io/hve-asdw-data-verify:app009"
                ),
            },
        )


def test_data_deploy_clean_run_needs_no_undeclared_ambient_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for key in runner_module._ASDW_DATA_DEPLOY_HVE_OWNED_ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)

    result, events, _roots, subprocess_calls = _run_step_with_generation_probe(
        tmp_path,
        monkeypatch,
        step_id="1.3",
        custom_agent=_DATA_DEPLOY_AGENT,
        workflow_id="asdw-web",
    )

    assert result is True
    assert "native-pipeline" in events
    assert subprocess_calls == []


def test_asdw_web_fanout_data_deploy_generates_before_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3/APP-009",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
        )
    )

    assert result is True
    assert generator_roots == [tmp_path.resolve()]
    assert events.index("generator") < events.index("native-pipeline")
    assert events.count("generation-console") == 1
    assert subprocess_calls == []


def test_asdw_web_data_deploy_generation_error_stops_before_client_or_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    errors: list[str] = []
    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            generation_error=True,
            captured_errors=errors,
        )
    )

    assert result is False
    assert generator_roots == [tmp_path.resolve()]
    assert events == ["runtime-gate", "input-gate", "work-dir", "generator"]
    assert subprocess_calls == []
    assert errors
    assert all("sanitized injected generation failure" not in error for error in errors)


def test_asdw_web_data_deploy_missing_bootstrap_stops_before_generation_or_sdk(
    tmp_path: Path,
    monkeypatch,
) -> None:
    errors: list[str] = []
    workflow_params = {
        "resource_group": "test-resource-group",
        "app_ids": ["APP-009"],
        "app_id": "APP-009",
        **_BOOTSTRAP_WORKFLOW_PARAMS,
    }
    workflow_params.pop("data_aci_subnet_cidr")

    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            workflow_params=workflow_params,
            captured_errors=errors,
        )
    )

    assert result is False
    assert events == []
    assert generator_roots == []
    assert subprocess_calls == []
    assert errors and "DATA_ACI_SUBNET_CIDR" in errors[0]


@pytest.mark.parametrize(
    "workflow_params",
    (
        {"resource_group": "test-resource-group"},
        {
            "resource_group": "test-resource-group",
            "app_id": "APP-009",
        },
        {"resource_group": "test-resource-group", "app_ids": ["APP-010"]},
        {
            "resource_group": "test-resource-group",
            "app_ids": ["APP-009", "APP-010"],
        },
        {
            "resource_group": "test-resource-group",
            "app_ids": ["APP-009"],
            "app_id": "APP-010",
        },
        {},
    ),
)
def test_asdw_web_data_deploy_rejects_unsupported_or_ambiguous_app_scope_before_generation(
    workflow_params: Mapping[str, object],
    tmp_path: Path,
    monkeypatch,
) -> None:
    errors: list[str] = []

    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            workflow_params=workflow_params,
            captured_errors=errors,
        )
    )

    assert result is False
    assert events == []
    assert generator_roots == []
    assert subprocess_calls == []
    assert errors == [
        "  ❌ [1.3] ASDW Step 1.3 supports exactly one selected APP-009 "
        "before producer generation"
    ]


@pytest.mark.parametrize(
    ("step_id", "workflow_params"),
    (
        (
            "1.3/APP-010",
            {
                "resource_group": "test-resource-group",
                "app_ids": ["APP-009"],
                "app_id": "APP-009",
            },
        ),
        (
            "1.3/",
            {
                "resource_group": "test-resource-group",
                "app_ids": ["APP-009"],
                "app_id": "APP-009",
            },
        ),
        (
            "1.3/APP-009/extra",
            {
                "resource_group": "test-resource-group",
                "app_ids": ["APP-009"],
                "app_id": "APP-009",
            },
        ),
    ),
)
def test_asdw_web_data_deploy_rejects_mismatched_fanout_app_scope_before_generation(
    step_id: str,
    workflow_params: Mapping[str, object],
    tmp_path: Path,
    monkeypatch,
) -> None:
    errors: list[str] = []

    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id=step_id,
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            workflow_params=workflow_params,
            captured_errors=errors,
        )
    )

    assert result is False
    assert events == []
    assert generator_roots == []
    assert subprocess_calls == []
    assert errors == [
        f"  ❌ [{step_id}] ASDW Step 1.3 supports exactly one selected APP-009 "
        "before producer generation"
    ]


def test_asdw_web_data_deploy_rejects_builtin_type_spoofs_before_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class SpoofedAppId(str):
        def __eq__(self, _other: object) -> bool:
            return True

        def __ne__(self, _other: object) -> bool:
            return False

    class SpoofedAppIds(list):
        pass

    errors: list[str] = []
    workflow_params = {
        "resource_group": "test-resource-group",
        "app_ids": SpoofedAppIds([SpoofedAppId("APP-010")]),
        "app_id": SpoofedAppId("APP-010"),
    }

    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            workflow_params=workflow_params,
            captured_errors=errors,
        )
    )

    assert result is False
    assert events == []
    assert generator_roots == []
    assert subprocess_calls == []
    assert errors == [
        "  ❌ [1.3] ASDW Step 1.3 supports exactly one selected APP-009 "
        "before producer generation"
    ]


def test_asdw_web_data_deploy_rejects_app_id_string_subclass_before_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class SpoofedAppId(str):
        pass

    errors: list[str] = []
    workflow_params = {
        "resource_group": "test-resource-group",
        "app_ids": ["APP-009"],
        "app_id": SpoofedAppId("APP-009"),
    }

    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            workflow_params=workflow_params,
            captured_errors=errors,
        )
    )

    assert result is False
    assert events == []
    assert generator_roots == []
    assert subprocess_calls == []
    assert errors == [
        "  ❌ [1.3] ASDW Step 1.3 supports exactly one selected APP-009 "
        "before producer generation"
    ]


@pytest.mark.parametrize("generation_status", ("", "unexpected", "SECRET\nSTATUS"))
def test_invalid_generation_status_fails_closed_without_logging_value(
    generation_status: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    errors: list[str] = []
    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            generation_status=generation_status,
            captured_errors=errors,
        )
    )

    assert result is False
    assert events == ["runtime-gate", "input-gate", "work-dir", "generator"]
    assert generator_roots == [tmp_path.resolve()]
    assert all(generation_status not in error for error in errors if generation_status)
    assert subprocess_calls == []


@pytest.mark.parametrize(
    "generation_result",
    (None, object(), types.SimpleNamespace(status=[])),
    ids=("none", "missing-status", "unhashable-status"),
)
def test_invalid_generation_result_object_fails_closed(
    generation_result: object | None,
    tmp_path: Path,
    monkeypatch,
) -> None:
    errors: list[str] = []
    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            generation_result=generation_result,
            captured_errors=errors,
        )
    )

    assert result is False
    assert events == ["runtime-gate", "input-gate", "work-dir", "generator"]
    assert generator_roots == [tmp_path.resolve()]
    assert errors
    assert subprocess_calls == []


def test_str_subclass_generation_status_is_rejected_without_protocol_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class SpoofedStatus(str):
        def __eq__(self, _other: object) -> bool:
            raise AssertionError("status subclass equality must not run")

        def __hash__(self) -> int:
            raise AssertionError("status subclass hash must not run")

        def __format__(self, _format_spec: str) -> str:
            raise AssertionError("status subclass formatting must not run")

    errors: list[str] = []
    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            generation_status=SpoofedStatus("reused"),
            captured_errors=errors,
        )
    )

    assert result is False
    assert events == ["runtime-gate", "input-gate", "work-dir", "generator"]
    assert generator_roots == [tmp_path.resolve()]
    assert errors
    assert subprocess_calls == []


@pytest.mark.parametrize(
    ("step_id", "custom_agent", "workflow_id"),
    (
        ("1.2", _DATA_TEST_CODING_AGENT, "asdw-web"),
        ("1.3", _DATA_DEPLOY_AGENT, "aagd"),
        ("1.3", _DATA_TEST_CODING_AGENT, "asdw-web"),
        ("1.30", _DATA_DEPLOY_AGENT, "asdw-web"),
        ("1.3-copy", _DATA_DEPLOY_AGENT, "asdw-web"),
    ),
)
def test_data_producer_generation_is_not_called_outside_asdw_web_step_1_3(
    step_id: str,
    custom_agent: str,
    workflow_id: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id=step_id,
            custom_agent=custom_agent,
            workflow_id=workflow_id,
        )
    )

    assert result is True
    assert generator_roots == []
    expected_prefix = []
    is_data_deploy = (
        custom_agent == _DATA_DEPLOY_AGENT
        and step_id.split("/", 1)[0] == "1.3"
    )
    if is_data_deploy:
        expected_prefix.append("runtime-gate")
    if is_data_deploy:
        expected_prefix.append("input-gate")
    assert events == expected_prefix + [
        "work-dir",
        "sdk-import",
        "client-factory",
        "client-start",
        "session-created",
        "main-turn",
        "split-fork",
    ]
    assert subprocess_calls == []


def test_asdw_web_data_deploy_dry_run_skips_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            dry_run=True,
        )
    )

    assert result is True
    assert events == ["runtime-gate"]
    assert generator_roots == []
    assert subprocess_calls == []


@pytest.mark.parametrize(
    "generation_exception",
    (
        RuntimeError("unexpected runtime failure"),
        asyncio.CancelledError(),
        SystemExit(2),
    ),
)
def test_non_generation_exceptions_are_not_converted_to_step_failure(
    generation_exception: BaseException,
    tmp_path: Path,
    monkeypatch,
) -> None:
    with pytest.raises(type(generation_exception)) as exc_info:
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            generation_exception=generation_exception,
        )
    assert exc_info.value is generation_exception


@pytest.mark.parametrize(
    ("runtime_errors", "input_errors", "expected_events"),
    (
        (["invalid runtime context"], None, ["runtime-gate"]),
        (None, ["invalid producer input"], ["runtime-gate", "input-gate"]),
    ),
)
def test_asdw_web_data_deploy_gate_failure_stops_before_generation(
    runtime_errors: list[str] | None,
    input_errors: list[str] | None,
    expected_events: list[str],
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, events, generator_roots, subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            runtime_errors=runtime_errors,
            input_errors=input_errors,
        )
    )

    assert result is False
    assert events == expected_events
    assert generator_roots == []
    assert subprocess_calls == []


def test_runner_imports_the_production_generator_symbol() -> None:
    from hve.asdw_data_script_generator import ensure_asdw_data_producers

    assert (
        vars(runner_module).get("ensure_asdw_data_producers")
        is ensure_asdw_data_producers
    )


def test_package_generator_import_does_not_fallback_after_internal_import_error(
    monkeypatch,
) -> None:
    source_path = Path(runner_module.__file__)
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    import_branch = next(
        node
        for node in module.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "__package__"
        and "ensure_asdw_data_producers" in ast.unparse(node)
    )
    import_calls: list[tuple[str, int]] = []
    original_import = builtins.__import__

    def injected_import(
        name,
        globals=None,
        locals=None,
        fromlist=(),
        level=0,
    ):
        if name == "asdw_data_script_generator":
            import_calls.append((name, level))
            if level == 1:
                raise ImportError("injected internal generator import failure")
            raise AssertionError("top-level generator fallback must not run")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", injected_import)
    isolated_branch = ast.fix_missing_locations(
        ast.Module(body=[import_branch], type_ignores=[])
    )
    with pytest.raises(
        ImportError,
        match="injected internal generator import failure",
    ):
        exec(
            compile(isolated_branch, str(source_path), "exec"),
            {"__package__": "hve"},
        )
    assert import_calls == [("asdw_data_script_generator", 1)]