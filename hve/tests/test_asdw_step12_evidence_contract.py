"""Sub-014 RED contract: ASDW-WEB Step 1.2 three-state machine evidence.

These tests define the contract for a not-yet-implemented validator,
``hve.artifact_validation.validate_asdw_step12_evidence_report``. On this
branch the symbol is absent, so every behavioural test fails at the lazy import
(this is the intended RED: the module/gate absence is the only reason to fail).
Sub-015 implements the validator (and the HVE-owned local verifier that writes
the authoritative machine log) to turn these GREEN.

The three states are recorded and machine-checked separately so a static
contract PASS can never be presented as a live RED execution, and a nonzero
focused pytest can never be folded into a single PASS:

- ``Artifact-Contract-Status``: bash -n / static validator / ShellCheck / LF-BOM
- ``Live-RED-Status``: expected-fail live Azure run, or NOT_RUN, or BLOCKED
- ``Focused-Regression-Status``: required focused pytest exit code

The Agent-visible report labels must match the HVE-owned machine log line for
each state (the machine log, produced by the Runner from tool events, is the
source of truth).
"""
from __future__ import annotations

from typing import Callable, List

import pytest


_REPORT_LABELS = (
    "Artifact-Contract-Status",
    "Live-RED-Status",
    "Focused-Regression-Status",
)

# Canonical honest Step 1.2 RED evidence: the deliverable passes its static
# contract, the live Azure verifier was not executed (static-only step), and
# the required focused pytest exited zero.
_CANONICAL_REPORT = (
    "# TDD Test Report - verify-data-resources RED\n\n"
    "<!-- validation-confirmed -->\n\n"
    "- Artifact-Contract-Status: PASS\n"
    "- Live-RED-Status: NOT_RUN\n"
    "- Focused-Regression-Status: PASS\n"
)
_CANONICAL_LOG = (
    "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: PASS\n"
    "HVE-STEP12-LIVE-RED-STATUS: NOT_RUN\n"
    "HVE-STEP12-FOCUSED-REGRESSION-STATUS: PASS\n"
)


def _validator() -> Callable[..., List[str]]:
    """Import lazily so the RED failure is a per-test missing-symbol error."""
    from hve.artifact_validation import validate_asdw_step12_evidence_report

    return validate_asdw_step12_evidence_report


def _report_with(**overrides: str) -> str:
    values = {
        "Artifact-Contract-Status": "PASS",
        "Live-RED-Status": "NOT_RUN",
        "Focused-Regression-Status": "PASS",
    }
    values.update(overrides)
    return (
        "# TDD Test Report - verify-data-resources RED\n\n"
        "<!-- validation-confirmed -->\n\n"
        + "".join(f"- {label}: {values[label]}\n" for label in _REPORT_LABELS)
    )


def _log_with(**overrides: str) -> str:
    values = {
        "ARTIFACT-CONTRACT": "PASS",
        "LIVE-RED": "NOT_RUN",
        "FOCUSED-REGRESSION": "PASS",
    }
    values.update(overrides)
    return (
        f"HVE-STEP12-ARTIFACT-CONTRACT-STATUS: {values['ARTIFACT-CONTRACT']}\n"
        f"HVE-STEP12-LIVE-RED-STATUS: {values['LIVE-RED']}\n"
        f"HVE-STEP12-FOCUSED-REGRESSION-STATUS: {values['FOCUSED-REGRESSION']}\n"
    )


def test_module_exposes_the_step12_evidence_validator() -> None:
    import hve.artifact_validation as artifact_validation

    assert hasattr(artifact_validation, "validate_asdw_step12_evidence_report")


def test_accepts_a_consistent_three_state_report() -> None:
    assert _validator()(_CANONICAL_REPORT, _CANONICAL_LOG) == []


@pytest.mark.parametrize("live_value", ("NOT_RUN", "BLOCKED", "EXPECTED_FAIL"))
def test_accepts_each_valid_live_red_state_backed_by_the_machine_log(
    live_value: str,
) -> None:
    """Every allowed Live-RED state is accepted when the machine log agrees."""
    report = _report_with(**{"Live-RED-Status": live_value})
    log = _log_with(**{"LIVE-RED": live_value})
    assert _validator()(report, log) == []


@pytest.mark.parametrize("missing_label", _REPORT_LABELS)
def test_requires_each_three_state_label(missing_label: str) -> None:
    report = "".join(
        line
        for line in _CANONICAL_REPORT.splitlines(keepends=True)
        if not line.startswith(f"- {missing_label}:")
    )
    errors = _validator()(report, _CANONICAL_LOG)
    assert any(missing_label in error for error in errors)


@pytest.mark.parametrize("label", _REPORT_LABELS)
def test_rejects_a_duplicated_three_state_label(label: str) -> None:
    report = _CANONICAL_REPORT + f"- {label}: PASS\n"
    errors = _validator()(report, _CANONICAL_LOG)
    assert any(label in error for error in errors)


@pytest.mark.parametrize(
    ("label", "bad_value"),
    (
        ("Artifact-Contract-Status", "MAYBE"),
        ("Live-RED-Status", "PASS"),
        ("Focused-Regression-Status", "SKIPPED"),
    ),
)
def test_rejects_status_values_outside_the_fixed_allowlist(
    label: str, bad_value: str
) -> None:
    errors = _validator()(_report_with(**{label: bad_value}), _CANONICAL_LOG)
    assert any(label in error for error in errors)


def test_static_pass_cannot_claim_live_expected_fail_without_machine_evidence() -> None:
    """A static-only PASS must not be reported as an executed live RED."""
    report = _report_with(**{"Live-RED-Status": "EXPECTED_FAIL"})
    errors = _validator()(report, _CANONICAL_LOG)  # machine log says NOT_RUN
    assert any("Live-RED-Status" in error for error in errors)


def test_focused_regression_pass_contradicting_nonzero_pytest_is_rejected() -> None:
    """A nonzero focused pytest recorded by HVE cannot be folded into PASS."""
    report = _report_with(**{"Focused-Regression-Status": "PASS"})
    errors = _validator()(report, _log_with(**{"FOCUSED-REGRESSION": "FAIL"}))
    assert any("Focused-Regression-Status" in error for error in errors)


def test_artifact_contract_pass_contradicting_log_failure_is_rejected() -> None:
    report = _report_with(**{"Artifact-Contract-Status": "PASS"})
    errors = _validator()(report, _log_with(**{"ARTIFACT-CONTRACT": "FAIL"}))
    assert any("Artifact-Contract-Status" in error for error in errors)


@pytest.mark.parametrize(
    "log_key",
    ("ARTIFACT-CONTRACT", "LIVE-RED", "FOCUSED-REGRESSION"),
)
def test_requires_each_authoritative_machine_log_line(log_key: str) -> None:
    log = "".join(
        line
        for line in _CANONICAL_LOG.splitlines(keepends=True)
        if log_key not in line
    )
    errors = _validator()(_CANONICAL_REPORT, log)
    assert errors


def test_a_label_hidden_in_a_comment_does_not_satisfy_the_contract() -> None:
    """The Agent-authored report is parsed by visible lines only."""
    report = _CANONICAL_REPORT.replace(
        "- Live-RED-Status: NOT_RUN\n",
        "<!-- - Live-RED-Status: NOT_RUN -->\n",
    )
    errors = _validator()(report, _CANONICAL_LOG)
    assert any("Live-RED-Status" in error for error in errors)


def _builder() -> Callable[..., str]:
    from hve.artifact_validation import build_asdw_step12_machine_log

    return build_asdw_step12_machine_log


_ALL_PASS_INPUTS = dict(
    bash_syntax_ok=True,
    shellcheck_ok=True,
    artifact_validator_errors=[],
    lf_bom_ok=True,
    focused_pytest_exit_code=0,
)


def test_builder_all_checks_pass_renders_canonical_statuses() -> None:
    log = _builder()(**_ALL_PASS_INPUTS)
    assert "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: PASS" in log
    assert "HVE-STEP12-LIVE-RED-STATUS: NOT_RUN" in log
    assert "HVE-STEP12-FOCUSED-REGRESSION-STATUS: PASS" in log


def test_builder_output_is_accepted_by_the_validator_round_trip() -> None:
    log = _builder()(**_ALL_PASS_INPUTS)
    assert _validator()(_CANONICAL_REPORT, log) == []


@pytest.mark.parametrize(
    "override",
    (
        {"bash_syntax_ok": False},
        {"shellcheck_ok": False},
        {"artifact_validator_errors": ["boom"]},
        {"lf_bom_ok": False},
    ),
)
def test_builder_any_artifact_check_failure_yields_fail(override: dict) -> None:
    log = _builder()(**{**_ALL_PASS_INPUTS, **override})
    assert "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: FAIL" in log


def test_builder_nonzero_focused_pytest_is_never_folded_into_pass() -> None:
    log = _builder()(**{**_ALL_PASS_INPUTS, "focused_pytest_exit_code": 1})
    assert "HVE-STEP12-FOCUSED-REGRESSION-STATUS: FAIL" in log


@pytest.mark.parametrize("live", ("NOT_RUN", "BLOCKED", "EXPECTED_FAIL"))
def test_builder_passes_through_valid_live_red_status(live: str) -> None:
    log = _builder()(**{**_ALL_PASS_INPUTS, "live_red_status": live})
    assert f"HVE-STEP12-LIVE-RED-STATUS: {live}" in log


def test_builder_rejects_an_invalid_live_red_status() -> None:
    with pytest.raises(ValueError):
        _builder()(**{**_ALL_PASS_INPUTS, "live_red_status": "PASS"})


