"""One production-path chain for ASDW-WEB Step 1.3.

Step 1.3 は HVE native pipeline へ移行済みで、Agent セッションおよびその
permission 境界は production から到達しない。したがってこのテストは Agent の
権限チェーンではなく、**production が実際に通る境界**だけを検証する:

    old public (stale) producers on disk
      -> HVE pre-session generator regenerates the fixed set
      -> the create/registration validators accept the generated set (0 errors)
      -> run_step drives the native pipeline (execute_pipeline) and never
         constructs a Copilot SDK client or session
      -> StageResult -> HVE-owned evidence (work-status / ac-verification /
         tdd-test-report) -> run_step returns True
      -> a second generator pass reuses the set (identical bytes and mtimes)

The valid producer bytes are never hand-authored here; they only exist because
the production generator promoted them from stale inputs. The canonical design
and sample inputs are reused from the generator contract test so this chain
does not fork a second source of truth for them. No live Azure call is made:
``execute_pipeline`` is the seam, and the harness asserts that no child process
is spawned.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import hve.runner as runner_module
from hve.artifact_validation import (
    validate_asdw_data_create_scripts,
    validate_asdw_data_registration_script,
    validate_deploy_ac_verification,
    validate_tdd_test_report,
)
from hve.asdw_data_script_generator import ensure_asdw_data_producers
from hve.asdw_data_script_launcher import StageResult
from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner
from hve.tests.test_asdw_data_script_generator import (
    _prepare_promotion_repo,
    _producer_mtimes,
    _producer_snapshot,
)


_DATA_DEPLOY_AGENT = "Dev-Microservice-Azure-DataDeploy"
_PREP_PATH = "src/infra/azure/create-azure-data-resources-prep.sh"
_CREATE_PATH = "src/infra/azure/create-azure-data-resources.sh"
_REGISTRATION_PATH = "src/data/azure/data-registration-script.sh"
_DESIGN_PATH = "docs/azure/azure-services-data.md"
_SAMPLE_PATH = "src/data/sample-data.json"

# Stale, public, marker-less producers — the exact class of artifact the loop
# used to leave behind. They are intentionally invalid so the generator must
# regenerate rather than reuse them.
_STALE_PRODUCERS: dict[str, bytes] = {
    _PREP_PATH: (
        b"#!/usr/bin/env bash\n"
        b"set -euo pipefail\n"
        b"# stale public prep without HVE markers\n"
        b'az group create --name rg --location eastus --output none\n'
    ),
    _CREATE_PATH: (
        b"#!/usr/bin/env bash\n"
        b"set -euo pipefail\n"
        b"# stale public create without HVE markers\n"
        b'az sql server create --name sql --enable-public-network true --output none\n'
        b'az sql server firewall-rule create --name AllowAzureServices '
        b'--start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 --output none\n'
    ),
    _REGISTRATION_PATH: (
        b"#!/usr/bin/env bash\n"
        b"set -euo pipefail\n"
        b"# stale registration without HVE markers\n"
    ),
}

# The runner resolves this from `az account show`; tests must never shell out.
_SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000001"
_WORKFLOW_PARAMS = {
    "resource_group": "test-resource-group",
    "app_ids": ["APP-009"],
    "app_id": "APP-009",
    "data_location": "japaneast",
    "data_resource_suffix": "app009",
    "data_vnet_cidr": "10.40.0.0/16",
    "data_private_endpoint_subnet_cidr": "10.40.1.0/24",
    "data_aci_subnet_cidr": "10.40.2.0/24",
}


def _successful_stage_results() -> tuple[StageResult, ...]:
    return tuple(
        StageResult(
            stage=stage,
            attempt=attempt,
            exit_code=0,
            reached=True,
            evidence="process-exit=0",
        )
        for stage, attempt in runner_module._ASDW_DATA_DEPLOY_PIPELINE_SEQUENCE
    )


def _pin_production_boundary(monkeypatch, spawned: list[str], sdk: list[str]) -> None:
    """Pin the seams that must never be crossed on the native production path."""

    def unexpected_process(*_args, **_kwargs):
        spawned.append("subprocess")
        raise AssertionError("the native production path must not spawn a process")

    monkeypatch.setattr(runner_module.subprocess, "run", unexpected_process)
    monkeypatch.setattr(runner_module.subprocess, "Popen", unexpected_process)
    monkeypatch.setattr(os, "system", unexpected_process)
    monkeypatch.setattr(os, "popen", unexpected_process)

    def unexpected_client(**_kwargs):
        sdk.append("client")
        raise AssertionError("Step 1.3 must not construct a Copilot SDK client")

    monkeypatch.setattr(
        "hve.copilot_client_factory.create_copilot_client",
        unexpected_client,
    )
    # `az account show` はここでは呼ばない（live Azure を unit test に混ぜない）。
    monkeypatch.setattr(
        runner_module,
        "_resolve_asdw_data_deploy_subscription_id",
        lambda: _SUBSCRIPTION_ID,
    )
    # Step 1.2 が producer である verifier 契約と runtime context の検査は
    # それぞれ専用テストが担保する。ここでは Step 1.3 の実行境界だけを見る。
    monkeypatch.setattr(
        runner_module,
        "_validate_asdw_data_deploy_runtime_context",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        runner_module.StepRunner,
        "_run_asdw_data_verify_contract_gate",
        lambda *_args, **_kwargs: [],
    )


def _data_deploy_runner(run_id: str) -> StepRunner:
    return StepRunner(
        config=SDKConfig(
            run_id=run_id,
            auto_qa=False,
            auto_contents_review=False,
            auto_self_improve=False,
        ),
        console=Console(verbose=False, quiet=True),
        workflow_params=dict(_WORKFLOW_PARAMS),
    )


def test_stale_producers_regenerate_then_native_pipeline_writes_hve_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _prepare_promotion_repo(repo_root, dict(_STALE_PRODUCERS))
    monkeypatch.chdir(repo_root)

    # 1. The seeded fixture is genuinely stale/public: the current validator
    #    rejects it, proving the chain does not start from a valid set.
    stale_errors = validate_asdw_data_create_scripts(
        repo_root / _PREP_PATH,
        repo_root / _CREATE_PATH,
        design_doc_path=repo_root / _DESIGN_PATH,
        sample_data_path=repo_root / _SAMPLE_PATH,
    )
    assert stale_errors

    # 2. HVE regenerates the fixed producer set from the stale inputs.
    first = ensure_asdw_data_producers(repo_root=repo_root)
    assert first.status == "regenerated"
    assert first.audit_mode == "sql-ledger-digest"

    # 3. The create and registration validators accept the generated set.
    assert (
        validate_asdw_data_create_scripts(
            repo_root / _PREP_PATH,
            repo_root / _CREATE_PATH,
            design_doc_path=repo_root / _DESIGN_PATH,
            sample_data_path=repo_root / _SAMPLE_PATH,
        )
        == []
    )
    assert (
        validate_asdw_data_registration_script(
            repo_root / _REGISTRATION_PATH,
            design_doc_path=repo_root / _DESIGN_PATH,
        )
        == []
    )

    # 4. run_step drives the native pipeline. `execute_pipeline` is the single
    #    production seam; no SDK client/session and no child process may appear.
    run_id = "asdw-production-path-native"
    monkeypatch.setenv("HVE_RUN_ID", run_id)
    monkeypatch.setenv("HVE_WORK_ROOT", str(repo_root / "work" / "run" / run_id))
    spawned: list[str] = []
    sdk: list[str] = []
    _pin_production_boundary(monkeypatch, spawned, sdk)

    pipeline_calls: list[dict[str, Any]] = []

    def fake_execute_pipeline(**kwargs):
        pipeline_calls.append(dict(kwargs))
        return _successful_stage_results()

    monkeypatch.setattr(runner_module, "execute_pipeline", fake_execute_pipeline)

    runner = _data_deploy_runner(run_id)
    result = asyncio.run(
        runner.run_step(
            "1.3",
            "Azure data deploy",
            "production path probe",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
        )
    )

    assert result is True
    assert spawned == []
    assert sdk == []
    assert runner._sub_sessions_created == 0
    assert len(pipeline_calls) == 1
    assert pipeline_calls[0]["repo_root"] == repo_root.resolve()
    environment = pipeline_calls[0]["environment"]
    assert environment["RESOURCE_GROUP"] == "test-resource-group"
    assert environment["HVE_RUN_ID"] == run_id

    # 5. StageResult は HVE-owned evidence へ写され、Step の成果物 gate を通る。
    work_status, ac_report, tdd_report = (
        runner_module._asdw_data_deploy_evidence_paths(repo_root, run_id)
    )
    assert "status: PASS" in work_status.read_text(encoding="utf-8")
    assert (
        validate_deploy_ac_verification(
            ac_report,
            _DATA_DEPLOY_AGENT,
            required_acs=["AC-1", "AC-2", "AC-3"],
        )
        == []
    )
    assert (
        validate_tdd_test_report(
            tdd_report,
            expected_phase="GREEN",
            expected_workflow="asdw-web",
            expected_target_key="APP-009",
        )
        == []
    )

    # 6. A second generator pass reuses the promoted set unchanged.
    promoted_bytes = _producer_snapshot(repo_root)
    promoted_mtimes = _producer_mtimes(repo_root)
    second = ensure_asdw_data_producers(repo_root=repo_root)
    assert second.status == "reused"
    assert second.audit_mode == "sql-ledger-digest"
    assert _producer_snapshot(repo_root) == promoted_bytes
    assert _producer_mtimes(repo_root) == promoted_mtimes


def test_failed_native_stage_fails_the_step_and_leaves_blocked_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A failing StageResult must fail the Step and record BLOCKED evidence."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _prepare_promotion_repo(repo_root, dict(_STALE_PRODUCERS))
    monkeypatch.chdir(repo_root)
    assert ensure_asdw_data_producers(repo_root=repo_root).status == "regenerated"

    run_id = "asdw-production-path-native-blocked"
    monkeypatch.setenv("HVE_RUN_ID", run_id)
    monkeypatch.setenv("HVE_WORK_ROOT", str(repo_root / "work" / "run" / run_id))
    spawned: list[str] = []
    sdk: list[str] = []
    _pin_production_boundary(monkeypatch, spawned, sdk)
    monkeypatch.setattr(
        runner_module,
        "execute_pipeline",
        lambda **_kwargs: (
            StageResult(
                stage="registration",
                attempt=1,
                exit_code=23,
                reached=True,
                evidence="process-exit=23",
            ),
        ),
    )

    runner = _data_deploy_runner(run_id)
    result = asyncio.run(
        runner.run_step(
            "1.3",
            "Azure data deploy",
            "production path failure probe",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
        )
    )

    assert result is False
    assert spawned == []
    assert sdk == []
    work_status, ac_report, _tdd_report = (
        runner_module._asdw_data_deploy_evidence_paths(repo_root, run_id)
    )
    assert "status: BLOCKED" in work_status.read_text(encoding="utf-8")
    assert "| AC-1 | native pipeline completed | ❌ |" in ac_report.read_text(
        encoding="utf-8"
    )
