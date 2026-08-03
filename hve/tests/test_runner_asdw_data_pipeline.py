"""RED contracts for the HVE-owned ASDW-WEB Step 1.3 native pipeline."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import hve.runner as runner_module
from hve.artifact_validation import (
    validate_deploy_ac_verification,
    validate_tdd_test_report,
)
from hve.asdw_data_script_launcher import StageResult
from hve.tests.test_runner_asdw_data_producer_generation import (
    _DATA_DEPLOY_AGENT,
    _run_step_with_generation_probe,
)


def _successful_pipeline_result() -> tuple[StageResult, ...]:
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


def test_app009_data_deploy_uses_native_pipeline_without_creating_sdk_session(
    tmp_path,
    monkeypatch,
) -> None:
    pipeline_calls: list[dict[str, Any]] = []

    def run_pipeline(**kwargs):
        pipeline_calls.append(kwargs)
        return _successful_pipeline_result()

    monkeypatch.setattr(
        runner_module,
        "execute_pipeline",
        run_pipeline,
        # P07 is RED-only: Runner imports this symbol in P08, so its absence
        # must fail through assertions rather than fixture setup.
        raising=False,
    )

    result, events, generator_roots, _subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
        )
    )

    assert result is True
    assert generator_roots == [tmp_path.resolve()]
    assert len(pipeline_calls) == 1
    assert pipeline_calls[0]["repo_root"] == tmp_path.resolve()
    assert pipeline_calls[0]["environment"]["RESOURCE_GROUP"] == "test-resource-group"
    assert "client-factory" not in events
    assert "session-created" not in events
    assert "main-turn" not in events


def test_native_pipeline_failure_fails_step_without_creating_sdk_session(
    tmp_path,
    monkeypatch,
) -> None:
    pipeline_calls: list[dict[str, Any]] = []

    def fail_pipeline(**kwargs):
        pipeline_calls.append(kwargs)
        return (
            StageResult(
                stage="registration",
                attempt=1,
                exit_code=23,
                reached=True,
                evidence="process-exit=23",
            ),
        )

    monkeypatch.setattr(
        runner_module,
        "execute_pipeline",
        fail_pipeline,
        raising=False,
    )

    result, events, generator_roots, _subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
        )
    )

    assert result is False
    assert generator_roots == [tmp_path.resolve()]
    assert len(pipeline_calls) == 1
    assert "client-factory" not in events
    assert "session-created" not in events
    assert "main-turn" not in events


def test_native_pipeline_exception_fails_step_without_creating_sdk_session(
    tmp_path,
    monkeypatch,
) -> None:
    pipeline_calls: list[dict[str, Any]] = []

    def raise_pipeline(**kwargs):
        pipeline_calls.append(kwargs)
        raise RuntimeError("injected native pipeline failure")

    monkeypatch.setattr(
        runner_module,
        "execute_pipeline",
        raise_pipeline,
        raising=False,
    )

    result, events, generator_roots, _subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
        )
    )

    assert result is False
    assert generator_roots == [tmp_path.resolve()]
    assert len(pipeline_calls) == 1
    assert "client-factory" not in events
    assert "session-created" not in events
    assert "main-turn" not in events


def test_stage_results_generate_hve_owned_green_evidence_that_passes_gates(
    tmp_path,
) -> None:
    run_id = "pipeline-evidence-green"

    assert runner_module._write_asdw_data_deploy_evidence(
        tmp_path,
        run_id,
        _successful_pipeline_result(),
    ) == []
    work_status, ac_report, tdd_report = (
        runner_module._asdw_data_deploy_evidence_paths(tmp_path, run_id)
    )

    assert "status: PASS" in work_status.read_text(encoding="utf-8")
    assert validate_deploy_ac_verification(
        ac_report,
        _DATA_DEPLOY_AGENT,
        required_acs=["AC-1", "AC-2", "AC-3"],
    ) == []
    assert validate_tdd_test_report(
        tdd_report,
        expected_phase="GREEN",
        expected_workflow="asdw-web",
        expected_target_key="APP-009",
    ) == []


def test_hve_evidence_paths_conform_to_the_app009_runtime_contract(tmp_path) -> None:
    run_id = "pipeline-evidence-paths"
    work_status, ac_report, tdd_report = (
        runner_module._asdw_data_deploy_evidence_paths(tmp_path, run_id)
    )

    assert work_status.relative_to(tmp_path).as_posix() == (
        f"work/run/{run_id}/Dev-Microservice-Azure-DataDeploy/"
        "Issue-step-1-3/work-status.md"
    )
    assert ac_report.relative_to(tmp_path).as_posix() == (
        f"work/run/{run_id}/Dev-Microservice-Azure-DataDeploy/"
        "Issue-step-1-3/ac-verification.md"
    )
    assert tdd_report.relative_to(tmp_path).as_posix() == (
        f"tests/run/{run_id}/asdw-web/step-1-3/APP-009/GREEN/"
        "tdd-test-report.md"
    )


def test_failed_stage_results_leave_hve_owned_blocked_evidence(
    tmp_path,
) -> None:
    run_id = "pipeline-evidence-failed"
    failed_results = (
        StageResult(
            stage="registration",
            attempt=1,
            exit_code=23,
            reached=True,
            evidence="process-exit=23",
        ),
    )

    assert runner_module._write_asdw_data_deploy_evidence(
        tmp_path,
        run_id,
        failed_results,
    ) == []
    work_status, ac_report, tdd_report = (
        runner_module._asdw_data_deploy_evidence_paths(tmp_path, run_id)
    )

    assert "status: BLOCKED" in work_status.read_text(encoding="utf-8")
    assert "| AC-1 | native pipeline completed | ❌ |" in ac_report.read_text(
        encoding="utf-8"
    )
    assert "- TDD-Judgement: BLOCKED" in tdd_report.read_text(encoding="utf-8")


def test_stage_results_preserve_individual_ac_outcomes(tmp_path) -> None:
    run_id = "pipeline-evidence-ac-granularity"
    failed_verify = tuple(
        StageResult(
            stage=stage,
            attempt=attempt,
            exit_code=13 if (stage, attempt) == ("verify", 2) else 0,
            reached=True,
            evidence="process-exit=13" if (stage, attempt) == ("verify", 2) else "process-exit=0",
        )
        for stage, attempt in runner_module._ASDW_DATA_DEPLOY_PIPELINE_SEQUENCE
    )

    assert runner_module._write_asdw_data_deploy_evidence(
        tmp_path,
        run_id,
        failed_verify,
    ) == []
    _work_status, ac_report, _tdd_report = (
        runner_module._asdw_data_deploy_evidence_paths(tmp_path, run_id)
    )
    report = ac_report.read_text(encoding="utf-8")
    assert "| AC-1 | native pipeline completed | ❌ |" in report
    assert "| AC-2 | create and registration second pass | ✅ |" in report
    assert "| AC-3 | verify completed for both passes | ❌ |" in report


def test_evidence_write_failure_restores_preexisting_reports(
    tmp_path,
    monkeypatch,
) -> None:
    run_id = "pipeline-evidence-rollback"
    paths = runner_module._asdw_data_deploy_evidence_paths(tmp_path, run_id)
    originals = {
        path: f"original-{index}\n".encode("utf-8")
        for index, path in enumerate(paths)
    }
    for path, original in originals.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)
    real_replace = runner_module.os.replace
    failed = False

    def fail_second_evidence_commit(source, destination):
        nonlocal failed
        if not failed and Path(destination) == paths[1]:
            failed = True
            raise OSError("injected evidence commit failure")
        real_replace(source, destination)

    monkeypatch.setattr(runner_module.os, "replace", fail_second_evidence_commit)

    assert runner_module._write_asdw_data_deploy_evidence(
        tmp_path,
        run_id,
        _successful_pipeline_result(),
    ) == ["ASDW native data pipeline evidence could not be written."]
    assert failed is True
    assert {path: path.read_bytes() for path in paths} == originals
    assert not list(tmp_path.rglob("*.tmp"))


def test_native_pipeline_success_runs_hve_tdd_and_deploy_evidence_gates(
    tmp_path,
    monkeypatch,
) -> None:
    gate_calls: list[str] = []

    def run_pipeline(**_kwargs):
        return _successful_pipeline_result()

    monkeypatch.setattr(runner_module, "execute_pipeline", run_pipeline)
    original_tdd_gate = runner_module.StepRunner._run_tdd_report_gate
    original_deploy_gate = runner_module.StepRunner._run_deploy_ac_gate

    def record_tdd_gate(self, *args, **kwargs):
        gate_calls.append("tdd")
        return original_tdd_gate(self, *args, **kwargs)

    def record_deploy_gate(self, *args, **kwargs):
        gate_calls.append("deploy")
        return original_deploy_gate(self, *args, **kwargs)

    monkeypatch.setattr(
        runner_module.StepRunner,
        "_run_tdd_report_gate",
        record_tdd_gate,
    )
    monkeypatch.setattr(
        runner_module.StepRunner,
        "_run_deploy_ac_gate",
        record_deploy_gate,
    )

    result, events, _generator_roots, _subprocess_calls = (
        _run_step_with_generation_probe(
            tmp_path,
            monkeypatch,
            step_id="1.3",
            custom_agent=_DATA_DEPLOY_AGENT,
            workflow_id="asdw-web",
            native_evidence_gates=True,
        )
    )

    assert result is True
    assert gate_calls == ["tdd", "deploy"]
    assert "client-factory" not in events


def test_pipeline_modules_import_under_top_level_runner_compatibility_path() -> None:
    """`hve/` を sys.path へ置く top-level runner 互換経路でも import できること。

    `hve/runner.py` は `__package__` が無い場合に top-level 名で
    `asdw_data_script_launcher` を import する。launcher 側が無条件の相対 import を
    持つと、この経路が ImportError で壊れる。
    """
    hve_dir = str(Path(runner_module.__file__).resolve().parent)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {hve_dir!r})\n"
        "import asdw_data_script_launcher as launcher\n"
        "import runner\n"
        "assert callable(launcher.execute_pipeline)\n"
        "assert runner.execute_pipeline is not None\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
