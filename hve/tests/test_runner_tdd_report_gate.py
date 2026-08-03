"""StepRunner TDD report gate tests."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import types

import pytest

from hve.config import SDKConfig
from hve.console import Console
from hve.runner import StepRunner


def _runner() -> StepRunner:
    return StepRunner(config=SDKConfig(), console=Console(verbose=False, quiet=True))


_STEP12_ALL_PASS_MACHINE_LOG = (
    "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: PASS\n"
    "HVE-STEP12-LIVE-RED-STATUS: NOT_RUN\n"
    "HVE-STEP12-FOCUSED-REGRESSION-STATUS: PASS\n"
)


@pytest.fixture(autouse=True)
def _patch_step12_local_verification(monkeypatch):
    """Keep the Step 1.2 gate's HVE verifier offline in unit tests.

    The real verifier spawns bash and pytest; every gate test injects a canned
    all-PASS machine log instead, and individual tests re-patch it when they
    exercise the three-state mismatch path.
    """
    import hve.asdw_step12_verification as verification

    monkeypatch.setattr(
        verification,
        "run_asdw_step12_local_verification",
        lambda *_args, **_kwargs: _STEP12_ALL_PASS_MACHINE_LOG,
    )
    return monkeypatch


def _write_report(
    base: Path,
    *,
    workflow_id: str = "asdw-web",
    step_dir: str = "step-3-2",
    target: str = "SVC-13",
    phase: str = "RED",
    judgement: str = "PASS",
    step: str = "3.2",
    agent: str = "Dev-Microservice-Azure-ServiceTestCoding",
    raw_log_path: str = "N/A",
) -> Path:
    report = base / "tests" / "run" / "run-1" / workflow_id / step_dir / target / phase / "tdd-test-report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        f"""# TDD Test Report

<!-- validation-confirmed -->

- Schema-Version: 1
- Workflow: {workflow_id}
- Step: {step}
- Agent: {agent}
- Target-Key: {target}
- Phase: {phase}
- Test-Code-Path: src/test/api/SVC-13.Tests/
- Timestamp-UTC: 2026-07-06T00:00:00Z
- Evidence-Status: EXECUTED
- TDD-Judgement: {judgement}

## Command

- CWD: {base.as_posix()}
- Command: `dotnet test`
- Exit-Code: 1

## Expected Outcome

- Expected: RED expected failure
- Reason: production code is not implemented yet

## Actual Result

- Total: 3
- Passed: 0
- Failed: 3
- Skipped: 0
- Summary: 3 failed

## Evidence

- Log-Excerpt: sanitized excerpt
- Raw-Log-Path: {raw_log_path}
- Secret-Redaction: confirmed

## Failure Analysis

- Root-Cause: expected RED
- Next-Action: implement GREEN step

## Test Protection

- Test-Files-Changed: N/A
- Allowed-Test-Changes: N/A
""",
        encoding="utf-8",
    )
    return report


def _write_asdw_data_report(base: Path, *, raw_log_path: str | None = None) -> Path:
    expected_raw_log = (
        "tests/run/run-1/asdw-web/step-1-2/APP-009/RED/"
        "static-verification.log"
    )
    report = _write_report(
        base,
        step_dir="step-1-2",
        target="APP-009",
        step="1.2",
        agent="Dev-Microservice-Azure-DataTestCoding",
        raw_log_path=raw_log_path or expected_raw_log,
    )
    # Step 1.2 also carries the three-state evidence labels checked against the
    # HVE-owned machine log; the default values match the canned all-PASS log.
    with report.open("a", encoding="utf-8") as stream:
        stream.write(
            "\n- Artifact-Contract-Status: PASS\n"
            "- Live-RED-Status: NOT_RUN\n"
            "- Focused-Regression-Status: PASS\n"
        )
    return report


def _write_static_verification_log(report: Path) -> Path:
    raw_log = report.with_name("static-verification.log")
    raw_log.write_text(
        "Azure CLI / REST / live command: NOT RUN\n",
        encoding="utf-8",
    )
    return raw_log


def test_tdd_report_gate_skips_non_tdd_step(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    assert _runner()._run_tdd_report_gate("5.1", "QA-AzureArchitectureReview", "asdw-web") == []


def test_tdd_report_instruction_suffix_uses_exact_asdw_fanout_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")

    suffix = _runner()._build_tdd_report_instruction_suffix(
        "4.1/APP-009-S005",
        "Dev-Microservice-Azure-UITestCoding",
        "asdw-web",
    )

    assert "tests/run/run-1/asdw-web/step-4-1/APP-009-S005/RED/tdd-test-report.md" in suffix
    assert "- Workflow: asdw-web" in suffix
    assert "- Target-Key: APP-009-S005" in suffix
    assert "- Phase: RED" in suffix
    assert "Dev-Microservice-Azure-UITestCoding` は Agent 名" in suffix


def test_tdd_report_instruction_suffix_skips_non_tdd_step(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")

    suffix = _runner()._build_tdd_report_instruction_suffix(
        "5.1/APP-009-S005",
        "QA-AzureArchitectureReview",
        "asdw-web",
    )

    assert suffix == ""


def test_tdd_report_instruction_suffix_skips_tdd_step_without_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")

    suffix = _runner()._build_tdd_report_instruction_suffix(
        "3.2",
        "Dev-Microservice-Azure-ServiceTestCoding",
        "asdw-web",
    )

    assert suffix == ""


def test_tdd_report_gate_passes_when_report_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    _write_report(tmp_path)
    assert _runner()._run_tdd_report_gate("3.2", "Dev-Microservice-Azure-ServiceTestCoding", "asdw-web") == []


def test_asdw_data_tdd_report_gate_requires_existing_raw_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    _write_asdw_data_report(tmp_path)

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("static-verification.log not found" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_machine_log_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A report status that contradicts the HVE-owned machine log is rejected."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)  # report claims Focused-Regression PASS
    _write_static_verification_log(report)
    import hve.asdw_step12_verification as verification

    monkeypatch.setattr(
        verification,
        "run_asdw_step12_local_verification",
        lambda *_args, **_kwargs: (
            "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: PASS\n"
            "HVE-STEP12-LIVE-RED-STATUS: NOT_RUN\n"
            "HVE-STEP12-FOCUSED-REGRESSION-STATUS: FAIL\n"
        ),
    )

    errors = _runner()._run_tdd_report_gate(
        "1.2",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("Focused-Regression-Status" in error for error in errors)


def test_asdw_data_tdd_report_gate_requires_three_state_labels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A Step 1.2 report missing the three-state labels is rejected."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    # Bypass the helper's label appender to omit the three-state labels.
    report = _write_report(
        tmp_path,
        step_dir="step-1-2",
        target="APP-009",
        step="1.2",
        agent="Dev-Microservice-Azure-DataTestCoding",
        raw_log_path=(
            "tests/run/run-1/asdw-web/step-1-2/APP-009/RED/"
            "static-verification.log"
        ),
    )
    _write_static_verification_log(report)

    errors = _runner()._run_tdd_report_gate(
        "1.2",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("Artifact-Contract-Status" in error for error in errors)


def test_asdw_data_tdd_report_gate_writes_machine_verification_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The HVE-owned machine log is written beside the report for audit."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)

    _runner()._run_tdd_report_gate(
        "1.2",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    machine_log = report.with_name("machine-verification.log")
    assert machine_log.is_file()
    assert (
        "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: PASS"
        in machine_log.read_text(encoding="utf-8")
    )


def test_asdw_data_tdd_report_gate_accepts_exact_non_empty_raw_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)

    assert _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    ) == []


def test_asdw_data_tdd_report_gate_accepts_inline_code_raw_log_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    expected_raw_log = (
        "tests/run/run-1/asdw-web/step-1-2/APP-009/RED/"
        "static-verification.log"
    )
    report = _write_asdw_data_report(
        tmp_path,
        raw_log_path=f"`{expected_raw_log}`",
    )
    _write_static_verification_log(report)

    assert _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    ) == []


@pytest.mark.parametrize("inline_code", (False, True))
def test_asdw_data_tdd_report_gate_accepts_windows_raw_log_path(
    tmp_path: Path,
    monkeypatch,
    inline_code: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    expected_raw_log = (
        "tests/run/run-1/asdw-web/step-1-2/APP-009/RED/"
        "static-verification.log"
    )
    windows_raw_log = (
        "tests\\run\\run-1\\asdw-web\\step-1-2\\APP-009\\RED\\"
        "static-verification.log"
    )
    assert windows_raw_log.count("\\") == expected_raw_log.count("/")
    assert "/" not in windows_raw_log
    report = _write_asdw_data_report(
        tmp_path,
        raw_log_path=(
            f"`{windows_raw_log}`" if inline_code else windows_raw_log
        ),
    )
    _write_static_verification_log(report)

    assert _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    ) == []


@pytest.mark.parametrize(
    "raw_log_path",
    (
        "tests\\run/run-1/asdw-web/step-1-2/APP-009/RED/static-verification.log",
        "`tests\\run\\run-1\\asdw-web\\step-1-2\\APP-009\\RED\\other.log`",
        "tests\\run\\other-run\\asdw-web\\step-1-2\\APP-009\\RED\\static-verification.log",
        "tests\\run\\run-1\\asdw-web\\step-1-2\\APP-010\\RED\\static-verification.log",
        "tests\\run\\run-1\\asdw-web\\step-1-2\\APP-009\\GREEN\\static-verification.log",
        "C:\\repo\\tests\\run\\run-1\\asdw-web\\step-1-2\\APP-009\\RED\\static-verification.log",
        "\\\\server\\share\\tests\\run\\run-1\\asdw-web\\step-1-2\\APP-009\\RED\\static-verification.log",
        "tests\\run\\run-1\\asdw-web\\step-1-2\\APP-009\\RED\\child\\..\\static-verification.log",
        "tests\\\\run\\run-1\\asdw-web\\step-1-2\\APP-009\\RED\\static-verification.log",
    ),
)
def test_asdw_data_tdd_report_gate_rejects_noncanonical_windows_raw_log_path(
    tmp_path: Path,
    monkeypatch,
    raw_log_path: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path, raw_log_path=raw_log_path)
    _write_static_verification_log(report)

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("Raw-Log-Path must exactly match" in error for error in errors)


@pytest.mark.parametrize(
    "raw_log_path",
    (
        "`{expected_raw_log}",
        "{expected_raw_log}`",
        "``{expected_raw_log}``",
        "`{mismatched_raw_log}`",
    ),
)
def test_asdw_data_tdd_report_gate_rejects_invalid_inline_code_raw_log_path(
    tmp_path: Path,
    monkeypatch,
    raw_log_path: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    expected_raw_log = (
        "tests/run/run-1/asdw-web/step-1-2/APP-009/RED/"
        "static-verification.log"
    )
    mismatched_raw_log = expected_raw_log.replace(
        "static-verification.log",
        "other.log",
    )
    report = _write_asdw_data_report(
        tmp_path,
        raw_log_path=raw_log_path.format(
            expected_raw_log=expected_raw_log,
            mismatched_raw_log=mismatched_raw_log,
        ),
    )
    _write_static_verification_log(report)

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("Raw-Log-Path must exactly match" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_mismatched_raw_log_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path, raw_log_path="N/A")
    _write_static_verification_log(report)

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("Raw-Log-Path must exactly match" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_empty_raw_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    report.with_name("static-verification.log").write_text("", encoding="utf-8")

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("must not be empty" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_duplicate_visible_raw_log_labels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)
    text = report.read_text(encoding="utf-8")
    raw_log_label = next(
        line for line in text.splitlines() if "Raw-Log-Path:" in line
    )
    report.write_text(
        text.replace(raw_log_label, f"{raw_log_label}\n{raw_log_label}"),
        encoding="utf-8",
    )

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("exactly one visible" in error for error in errors)


def test_asdw_data_tdd_report_gate_ignores_comment_and_fence_labels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)
    text = report.read_text(encoding="utf-8")
    hidden_labels = (
        "<!-- - Raw-Log-Path: hidden-comment.log\n"
        "- <div hidden>\n"
        "-->\n"
        "```text\n"
        "- Raw-Log-Path: hidden-fence.log\n"
        ">  <details>\n"
        "```\n"
    )
    report.write_text(
        text.replace("## Evidence\n", f"## Evidence\n\n{hidden_labels}"),
        encoding="utf-8",
    )

    assert _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    ) == []


def test_asdw_data_tdd_report_gate_rejects_multiline_raw_log_label(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)
    text = report.read_text(encoding="utf-8")
    expected = (
        "tests/run/run-1/asdw-web/step-1-2/APP-009/RED/"
        "static-verification.log"
    )
    report.write_text(
        text.replace(
            f"- Raw-Log-Path: {expected}",
            f"- Raw-Log-Path:\n  {expected}",
        ),
        encoding="utf-8",
    )

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert errors
    assert any("Raw-Log-Path" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_raw_html_visibility_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)
    text = report.read_text(encoding="utf-8")
    report.write_text(
        text.replace(
            "## Evidence\n",
            "## Evidence\n\n<div hidden>\n- Raw-Log-Path: hidden.log\n</div>\n",
        ),
        encoding="utf-8",
    )

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("visibility boundary is invalid" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_direct_html_declaration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)
    text = report.read_text(encoding="utf-8")
    report.write_text(
        text.replace(
            "## Evidence\n",
            "## Evidence\n\n<!ENTITY hidden SYSTEM 'value'>\n",
        ),
        encoding="utf-8",
    )

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("visibility boundary is invalid" in error for error in errors)


@pytest.mark.parametrize(
    "hidden_opener",
    (
        "- ```text",
        "> ```text",
        ">  ```text",
        "- <div hidden>",
        "> <details>",
        "- <!ENTITY hidden SYSTEM 'value'>",
        "- >  <!ENTITY hidden SYSTEM 'value'>",
    ),
)
def test_asdw_data_tdd_report_gate_rejects_containerized_hidden_blocks(
    tmp_path: Path,
    monkeypatch,
    hidden_opener: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)
    text = report.read_text(encoding="utf-8")
    report.write_text(
        text.replace(
            "## Evidence\n",
            f"## Evidence\n\n{hidden_opener}\n"
            "  - Raw-Log-Path: hidden.log\n",
        ),
        encoding="utf-8",
    )

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("list/blockquote container" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_invalid_utf8_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)
    report.write_bytes(report.read_bytes() + b"\xff")

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("report is unreadable" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_invalid_utf8_raw_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    report.with_name("static-verification.log").write_bytes(b"\xff")

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("static-verification.log is unreadable" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_non_regular_raw_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    report.with_name("static-verification.log").mkdir()

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("not a regular file" in error or "unreadable" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_leaf_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    target = tmp_path / "outside.log"
    target.write_text("outside\n", encoding="utf-8")
    try:
        report.with_name("static-verification.log").symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("symlink" in error or "unreadable" in error for error in errors)


def test_asdw_data_tdd_report_gate_rejects_report_leaf_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    report_text = report.read_text(encoding="utf-8")
    report.unlink()
    target = tmp_path / "outside-report.md"
    target.write_text(report_text, encoding="utf-8")
    try:
        report.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("RED report" in error and ("symlink" in error or "unreadable" in error) for error in errors)


def test_asdw_data_tdd_report_gate_rejects_parent_symlink_escape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    parent = (
        tmp_path
        / "tests"
        / "run"
        / "run-1"
        / "asdw-web"
        / "step-1-2"
        / "APP-009"
    )
    parent.mkdir(parents=True)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-red"
    outside.mkdir()
    canonical_report = _write_asdw_data_report(tmp_path)
    report = outside / "tdd-test-report.md"
    report.write_text(canonical_report.read_text(encoding="utf-8"), encoding="utf-8")
    canonical_report.unlink()
    _write_static_verification_log(report)
    canonical_report.parent.rmdir()
    try:
        canonical_report.parent.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"directory symlink unavailable: {exc}")
        completed = subprocess.run(
            [
                "cmd",
                "/d",
                "/c",
                "mklink",
                "/J",
                str(canonical_report.parent),
                str(outside),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.fail(
                "directory junction could not be created for escape test: "
                + completed.stderr
            )

    errors = _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    )

    assert any("outside" in error or "junction" in error for error in errors)


def test_asdw_data_static_log_rejects_open_path_identity_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)
    replacement = tmp_path / "replacement.log"
    replacement.write_text("replacement\n", encoding="utf-8")
    real_lstat = os.lstat

    def mismatched_lstat(path):
        if Path(path).name == "static-verification.log":
            return os.stat(replacement)
        return real_lstat(path)

    monkeypatch.setattr(os, "lstat", mismatched_lstat)

    errors = StepRunner._validate_asdw_data_static_verification_log(
        report,
        tmp_path,
        report.read_text(encoding="utf-8"),
    )

    assert any("changed while it was opened" in error for error in errors)


def test_asdw_data_stable_reader_rejects_windows_reparse_attribute(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _write_asdw_data_report(tmp_path)
    raw_log = _write_static_verification_log(report)
    real_lstat = os.lstat

    def reparse_lstat(path):
        result = real_lstat(path)
        if Path(path) == raw_log:
            values = {
                name: getattr(result, name)
                for name in dir(result)
                if name.startswith("st_")
            }
            values["st_file_attributes"] = 0x0400
            return types.SimpleNamespace(**values)
        return result

    monkeypatch.setattr(os, "lstat", reparse_lstat)

    _text, errors = StepRunner._read_asdw_stable_repo_file(
        raw_log,
        tmp_path,
        "ASDW data static-verification.log",
    )

    assert any("reparse point" in error for error in errors)


def test_asdw_data_stable_reader_rechecks_parent_resolution_after_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _write_asdw_data_report(tmp_path)
    raw_log = _write_static_verification_log(report)
    outside = tmp_path.parent / f"{tmp_path.name}-post-read.log"
    outside.write_text("outside\n", encoding="utf-8")
    real_resolve = Path.resolve
    target_resolve_calls = 0

    def drifting_resolve(path: Path, *args, **kwargs):
        nonlocal target_resolve_calls
        if path == raw_log:
            target_resolve_calls += 1
            if target_resolve_calls == 2:
                return outside
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", drifting_resolve)

    _text, errors = StepRunner._read_asdw_stable_repo_file(
        raw_log,
        tmp_path,
        "ASDW data static-verification.log",
    )

    assert target_resolve_calls == 2
    assert any("after it was read" in error for error in errors)


def test_asdw_data_stable_reader_detects_size_change_during_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _write_asdw_data_report(tmp_path)
    raw_log = _write_static_verification_log(report)
    real_fstat = os.fstat
    fstat_calls = 0

    def changing_fstat(descriptor: int):
        nonlocal fstat_calls
        result = real_fstat(descriptor)
        fstat_calls += 1
        if fstat_calls == 2:
            return types.SimpleNamespace(
                st_mode=result.st_mode,
                st_dev=result.st_dev,
                st_ino=result.st_ino,
                st_size=result.st_size + 1,
                st_mtime_ns=result.st_mtime_ns,
            )
        return result

    monkeypatch.setattr(os, "fstat", changing_fstat)

    _text, errors = StepRunner._read_asdw_stable_repo_file(
        raw_log,
        tmp_path,
        "ASDW data static-verification.log",
    )

    assert any("changed while it was read" in error for error in errors)


def test_asdw_data_stable_reader_closes_descriptor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report = _write_asdw_data_report(tmp_path)
    raw_log = _write_static_verification_log(report)
    real_close = os.close
    closed_descriptors: list[int] = []

    def tracked_close(descriptor: int) -> None:
        closed_descriptors.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(os, "close", tracked_close)

    text, errors = StepRunner._read_asdw_stable_repo_file(
        raw_log,
        tmp_path,
        "ASDW data static-verification.log",
    )

    assert errors == []
    assert text is not None
    assert len(closed_descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(closed_descriptors[0])


def test_asdw_data_gate_validates_one_report_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    report = _write_asdw_data_report(tmp_path)
    _write_static_verification_log(report)
    real_reader = StepRunner._read_asdw_stable_repo_file
    report_reads = 0

    def mutate_after_report_read(
        path: Path,
        repo_root: Path,
        artifact_name: str,
    ):
        nonlocal report_reads
        text, errors = real_reader(path, repo_root, artifact_name)
        if artifact_name == "ASDW data RED report":
            report_reads += 1
            path.write_text("# changed after stable snapshot\n", encoding="utf-8")
        return text, errors

    monkeypatch.setattr(
        StepRunner,
        "_read_asdw_stable_repo_file",
        staticmethod(mutate_after_report_read),
    )

    assert _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Dev-Microservice-Azure-DataTestCoding",
        "asdw-web",
    ) == []
    assert report_reads == 1


def test_asdw_data_raw_log_gate_does_not_apply_to_other_agent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")

    assert _runner()._run_tdd_report_gate(
        "1.2/APP-009",
        "Other-Agent",
        "asdw-web",
    ) == []


@pytest.mark.parametrize(
    ("step_id", "agent", "workflow_id"),
    (
        ("1.1/APP-009", "Dev-Microservice-Azure-DataTestCoding", "asdw-web"),
        ("1.2/APP-009", "Dev-Microservice-Azure-DataTestCoding", "aad-web"),
        ("1.2/APP-009", "Other-Agent", "asdw-web"),
    ),
)
def test_asdw_data_raw_log_gate_scope_is_exact(
    tmp_path: Path,
    monkeypatch,
    step_id: str,
    agent: str,
    workflow_id: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")

    assert _runner()._run_tdd_report_gate(step_id, agent, workflow_id) == []


def test_tdd_report_gate_fails_when_report_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    errors = _runner()._run_tdd_report_gate("3.2", "Dev-Microservice-Azure-ServiceTestCoding", "asdw-web")
    assert errors
    assert "tdd-test-report.md not found" in errors[0]
    assert "tests/run/run-1/asdw-web/step-3-2" in errors[0].replace("\\", "/")


def test_tdd_report_gate_missing_report_includes_actionable_hint(tmp_path: Path, monkeypatch) -> None:
    """not-found 診断に、無出力ターン終了を疑う actionable hint を含める。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    errors = _runner()._run_tdd_report_gate("3.2", "Dev-Microservice-Azure-ServiceTestCoding", "asdw-web")
    assert errors
    assert "ターンを終えた可能性が高い" in errors[0]
    assert "console-log を確認" in errors[0]


def test_tdd_report_gate_validates_green_judgement(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    _write_report(tmp_path, step_dir="step-3-3", phase="GREEN", judgement="FAIL")
    errors = _runner()._run_tdd_report_gate("3.3", "Dev-Microservice-Azure-ServiceCoding-AzureFunctions", "asdw-web")
    assert any("TDD-Judgement" in e for e in errors)


def test_tdd_report_gate_accepts_green_blocked_judgement(tmp_path: Path, monkeypatch) -> None:
    # BLOCKED is an honest GREEN terminal for a confirmed test-side / shared-config
    # blocker; the gate must not fail the step (only PASS/BLOCKED are accepted, FAIL errors).
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    _write_report(tmp_path, step_dir="step-4-2", target="APP-009-S013", phase="GREEN", judgement="BLOCKED")
    assert _runner()._run_tdd_report_gate("4.2/APP-009-S013", "Dev-Microservice-Azure-UICoding", "asdw-web") == []


def test_tdd_report_gate_scopes_fanout_child_to_current_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    _write_report(tmp_path, step_dir="step-4-2", target="APP-009-S013", phase="GREEN")

    sibling = tmp_path / "tests" / "run" / "run-1" / "asdw-web" / "step-4-2" / "APP-009-S005" / "GREEN" / "tdd-test-report.md"
    sibling.parent.mkdir(parents=True, exist_ok=True)
    sibling.write_text("# malformed sibling report\n", encoding="utf-8")

    assert _runner()._run_tdd_report_gate("4.2/APP-009-S013", "Dev-Microservice-Azure-UICoding", "asdw-web") == []


def test_tdd_report_gate_fails_when_current_fanout_target_report_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    _write_report(tmp_path, step_dir="step-4-2", target="APP-009-S005", phase="GREEN")

    errors = _runner()._run_tdd_report_gate("4.2/APP-009-S013", "Dev-Microservice-Azure-UICoding", "asdw-web")

    assert errors
    assert "APP-009-S013" in errors[0]
    assert "tdd-test-report.md not found" in errors[0]


def test_tdd_report_gate_does_not_accept_report_under_agent_name_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_RUN_ID", "run-1")
    _write_report(
        tmp_path,
        workflow_id="Dev-Microservice-Azure-UITestCoding",
        step_dir="step-4-1",
        target="APP-009-S005",
        phase="RED",
    )

    errors = _runner()._run_tdd_report_gate("4.1/APP-009-S005", "Dev-Microservice-Azure-UITestCoding", "asdw-web")

    assert errors
    assert "tests/run/run-1/asdw-web/step-4-1/APP-009-S005/RED/tdd-test-report.md" in errors[0].replace("\\", "/")
    assert "tdd-test-report.md not found" in errors[0]


def test_asdw_ui_red_unresolved_contract_gate_scopes_to_current_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    current = tmp_path / "src" / "test" / "ui" / "APP-009-S005" / "APP-009-S005.red.test.js"
    current.parent.mkdir(parents=True)
    current.write_text("const endpoint = 'TBD（要確認）';\n", encoding="utf-8")
    sibling = tmp_path / "src" / "test" / "ui" / "APP-009-S006" / "APP-009-S006.red.test.js"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("const endpoint = 'TBD（要確認）';\n", encoding="utf-8")

    guard = getattr(_runner(), "_run_asdw_ui_red_unresolved_contract_gate")
    errors = guard(
        "4.1/APP-009-S005",
        "Dev-Microservice-Azure-UITestCoding",
        "asdw-web",
    )

    assert errors
    assert "APP-009-S005.red.test.js" in errors[0]
    assert "APP-009-S006" not in errors[0]


def test_asdw_ui_red_unresolved_contract_gate_skips_non_ui_red_step(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    test_file = tmp_path / "src" / "test" / "ui" / "APP-009-S005" / "APP-009-S005.red.test.js"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("const endpoint = 'TBD（要確認）';\n", encoding="utf-8")

    guard = getattr(_runner(), "_run_asdw_ui_red_unresolved_contract_gate")
    errors = guard(
        "4.2/APP-009-S005",
        "Dev-Microservice-Azure-UICoding",
        "asdw-web",
    )

    assert errors == []
