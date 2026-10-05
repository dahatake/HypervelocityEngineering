"""FR-LOCAL-SURFACE-04: macOS bootstrap 検証 workflow の契約。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

import yaml  # type: ignore[import-untyped]


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "test-hve-bootstrap.yml"
_PROBE = _REPO_ROOT / ".github" / "scripts" / "bash" / "probe-hve-bootstrap-macos.sh"
_CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
_UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"
_PROBE_SHA256 = "b0f6907861f49b835afc037dfd753e45fccd3b88840918850e25bef67da8a64b"


def _load_workflow() -> dict[object, object]:
    assert _WORKFLOW.is_file(), f"required workflow is missing: {_WORKFLOW}"
    loaded = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _on_section(workflow: dict[object, object]) -> dict[str, object]:
    section = workflow.get(True, workflow.get("on"))
    assert isinstance(section, dict)
    return cast(dict[str, object], section)


def _jobs(workflow: dict[object, object]) -> dict[str, dict[str, object]]:
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    assert all(isinstance(value, dict) for value in jobs.values())
    return cast(dict[str, dict[str, object]], jobs)


def _run_text(job: dict[str, object]) -> str:
    steps = job.get("steps")
    assert isinstance(steps, list)
    return "\n".join(
        str(step.get("run", "")) for step in steps if isinstance(step, dict)
    )


def test_workflow_is_manual_only_with_bounded_inputs() -> None:
    workflow = _load_workflow()
    on_section = _on_section(workflow)
    assert set(on_section) == {"workflow_dispatch"}
    dispatch = on_section["workflow_dispatch"]
    assert isinstance(dispatch, dict)
    inputs = dispatch.get("inputs")
    assert isinstance(inputs, dict)
    assert set(inputs) == {
        "test_scope",
        "runner_label",
        "source_ref",
        "estimated_cost_usd",
        "cost_approved",
    }
    scope = inputs["test_scope"]
    assert isinstance(scope, dict)
    assert scope.get("type") == "choice"
    assert scope.get("required") is True
    assert scope.get("default") == "prerequisites"
    assert scope.get("options") == ["prerequisites", "distribution"]
    runner = inputs["runner_label"]
    assert isinstance(runner, dict)
    assert runner.get("type") == "choice"
    assert runner.get("required") is True
    assert runner.get("options") == ["macos-15", "macos-26"]
    source_ref = inputs["source_ref"]
    assert isinstance(source_ref, dict)
    assert source_ref.get("required") is True
    assert source_ref.get("type") == "string"
    estimate = inputs["estimated_cost_usd"]
    assert isinstance(estimate, dict)
    assert estimate.get("required") is True
    assert estimate.get("type") == "string"
    approval = inputs["cost_approved"]
    assert isinstance(approval, dict)
    assert approval.get("required") is True
    assert approval.get("type") == "boolean"
    assert approval.get("default") is False


def test_prerequisite_job_is_paid_gate_read_only_and_not_rerunnable() -> None:
    workflow = _load_workflow()
    assert workflow.get("permissions") == {"contents": "read"}
    jobs = _jobs(workflow)
    assert set(jobs) == {"gate", "prerequisites", "distribution"}
    gate = jobs["gate"]
    assert gate.get("runs-on") == "ubuntu-slim"
    assert gate.get("timeout-minutes") == 1
    gate_steps = gate.get("steps")
    assert isinstance(gate_steps, list)
    assert len(gate_steps) == 1
    gate_step = gate_steps[0]
    assert isinstance(gate_step, dict)
    assert gate_step.get("name") == "Validate dispatch approval"
    assert gate_step.get("shell") == "bash"
    assert gate_step.get("env") == {
        "TEST_SCOPE": "${{ inputs.test_scope }}",
        "RUNNER_LABEL": "${{ inputs.runner_label }}",
        "SOURCE_REF": "${{ inputs.source_ref }}",
        "ESTIMATED_COST_USD": "${{ inputs.estimated_cost_usd }}",
        "COST_APPROVED": "${{ inputs.cost_approved }}",
        "RUN_ATTEMPT": "${{ github.run_attempt }}",
    }
    assert str(gate_step.get("run", "")) == (
        'set -eu\n'
        'case "$TEST_SCOPE" in prerequisites|distribution) ;; *) exit 2 ;; esac\n'
        'case "$RUNNER_LABEL" in macos-15|macos-26) ;; *) exit 2 ;; esac\n'
        'test -n "$SOURCE_REF"\n'
        "printf '%s' \"$SOURCE_REF\" | grep -Eq '^[0-9a-f]{40}$'\n"
        'test -n "$ESTIMATED_COST_USD"\n'
        'test "$COST_APPROVED" = "true"\n'
        'test "$RUN_ATTEMPT" = "1"\n'
    )
    job = jobs["prerequisites"]
    assert job.get("needs") == "gate"
    assert job.get("runs-on") == "${{ inputs.runner_label }}"
    assert job.get("timeout-minutes") == 60
    assert job.get("continue-on-error") is not True
    condition = str(job.get("if", ""))
    assert " ".join(condition.split()) == (
        "inputs.test_scope == 'prerequisites' && "
        "inputs.cost_approved && "
        "inputs.estimated_cost_usd != '' && "
        "inputs.source_ref != '' && "
        "github.run_attempt == 1"
    )


def test_distribution_job_builds_and_validates_private_archive_without_live_dispatch() -> None:
    job = _jobs(_load_workflow())["distribution"]
    assert job.get("needs") == "gate"
    assert job.get("runs-on") == "${{ inputs.runner_label }}"
    assert job.get("timeout-minutes") == 60
    condition = " ".join(str(job.get("if", "")).split())
    assert "inputs.test_scope == 'distribution'" in condition
    assert "inputs.cost_approved" in condition
    assert "github.run_attempt == 1" in condition
    run_text = _run_text(job)
    assert "build-hve-bootstrap.py" in run_text
    assert "--target macos-arm64" in run_text
    assert "hashlib.sha256" in run_text
    assert "Start-HVE.command" in run_text
    steps = job.get("steps")
    assert isinstance(steps, list)
    checkout = next(
        step for step in steps
        if isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout.get("uses") == f"actions/checkout@{_CHECKOUT_SHA}"
    assert checkout.get("with") == {
        "ref": "${{ inputs.source_ref }}",
        "persist-credentials": False,
    }
    upload = next(
        step for step in steps
        if isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/upload-artifact@")
    )
    assert upload.get("uses") == f"actions/upload-artifact@{_UPLOAD_ARTIFACT_SHA}"
    assert upload.get("if") == "${{ always() }}"
    assert upload.get("with", {}).get("retention-days") == 7
    assert upload.get("with", {}).get("if-no-files-found") == "error"


def test_checkout_is_pinned_to_the_approved_source_ref() -> None:
    workflow = _load_workflow()
    for job_name in ("prerequisites", "distribution"):
        steps = _jobs(workflow)[job_name].get("steps")
        assert isinstance(steps, list)
        checkout = next(
            step
            for step in steps
            if isinstance(step, dict) and str(step.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout.get("uses") == f"actions/checkout@{_CHECKOUT_SHA}"
        assert checkout.get("with") == {
            "ref": "${{ inputs.source_ref }}",
            "persist-credentials": False,
        }


def test_probe_is_fixed_read_only_and_records_runner_facts() -> None:
    job = _jobs(_load_workflow())["prerequisites"]
    steps = job.get("steps")
    assert isinstance(steps, list)
    assert len(steps) == 3
    assert [
        set(step) if isinstance(step, dict) else set()
        for step in steps
    ] == [
        {"uses", "with"},
        {"name", "shell", "env", "run"},
        {"name", "if", "uses", "with"},
    ]
    assert sum(
        1
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/checkout@")
    ) == 1
    assert sum(
        1
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ) == 1
    probe = steps[1]
    assert isinstance(probe, dict)
    assert probe.get("name") == "Record approved source and runner facts"
    assert probe.get("shell") == "bash"
    assert probe.get("env") == {
        "HVE_RUNNER_LABEL": "${{ inputs.runner_label }}",
        "HVE_SOURCE_REF": "${{ inputs.source_ref }}",
    }
    assert probe.get("run") == (
        "bash .github/scripts/bash/probe-hve-bootstrap-macos.sh"
    )

    source = _PROBE.read_text(encoding="utf-8")
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == _PROBE_SHA256
    assert "$(uname -s)" in source
    assert '"Darwin"' in source
    assert '"$RUNNER_OS" = "macOS"' in source
    assert '"$(uname -m)" = "arm64"' in source
    assert "macos-15) EXPECTED_MAJOR=15" in source
    assert "macos-26) EXPECTED_MAJOR=26" in source
    assert 'SOURCE_COMMIT="$(git rev-parse HEAD)"' in source
    assert '[ "$SOURCE_COMMIT" = "$HVE_SOURCE_REF" ]' in source
    for required_fact in (
        "probe_status=facts-collected",
        "source_commit=%s",
        "runner_label=%s",
        "runner_os=%s",
        "image_os=%s",
        "image_version=%s",
        "os=%s",
        "architecture=arm64",
        "xcode_select=%s",
        "brew=%s",
        "%s_available=%s",
        "%s_path=%s",
    ):
        assert required_fact in source
    for forbidden in (
        "brew install",
        "pip install",
        "npm install",
        "sudo ",
        "gh auth",
        "az login",
    ):
        assert forbidden not in source


def test_artifact_is_small_private_and_short_lived() -> None:
    steps = _jobs(_load_workflow())["prerequisites"].get("steps")
    assert isinstance(steps, list)
    upload = next(
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/upload-artifact@")
    )
    assert upload.get("if") == "${{ always() }}"
    assert upload.get("uses") == (
        f"actions/upload-artifact@{_UPLOAD_ARTIFACT_SHA}"
    )
    with_values = upload.get("with")
    assert isinstance(with_values, dict)
    assert with_values.get("name") == "hve-bootstrap-prerequisites-${{ inputs.runner_label }}"
    assert with_values.get("path") == (
        "${{ runner.temp }}/hve-bootstrap-prerequisites/runner-facts.txt"
    )
    assert with_values.get("retention-days") == 7
    assert with_values.get("if-no-files-found") == "error"
    assert with_values.get("include-hidden-files") is not True
