"""Sub-015 part 2b: the HVE-owned Step 1.2 local verification orchestration.

Every subprocess boundary is injected, so these tests exercise the fixed-order
composition (bash -n, optional ShellCheck, artifact validator, LF/BOM) into the
three-state machine log without spawning bash. Per FR-CLI-72 a product run must
not launch this repository's own test suite, which is also fixed here.
"""
from __future__ import annotations

import inspect
import subprocess
from pathlib import Path
from typing import Any

import pytest

import hve.asdw_step12_verification as verification
from hve.artifact_validation import validate_asdw_step12_evidence_report
from hve.asdw_step12_verification import run_asdw_step12_local_verification


def _write_script(
    root: Path,
    payload: bytes = b"#!/usr/bin/env bash\nset -euo pipefail\n",
) -> Path:
    path = root / "src/infra/azure/verify-data-resources.sh"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _run(root: Path, **overrides: Any) -> str:
    kwargs: dict[str, Any] = dict(
        artifact_validator=lambda _script: [],
        bash_syntax_runner=lambda _script: 0,
        shellcheck_runner=lambda _script: 0,
    )
    kwargs.update(overrides)
    return run_asdw_step12_local_verification(root, **kwargs)


def test_all_checks_pass_yields_canonical_statuses(tmp_path: Path) -> None:
    _write_script(tmp_path)
    log = _run(tmp_path)
    assert "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: PASS" in log
    assert "HVE-STEP12-LIVE-RED-STATUS: NOT_RUN" in log
    assert "HVE-STEP12-FOCUSED-REGRESSION-STATUS: PASS" in log


def test_output_round_trips_with_the_validator(tmp_path: Path) -> None:
    _write_script(tmp_path)
    log = _run(tmp_path)
    report = (
        "- Artifact-Contract-Status: PASS\n"
        "- Live-RED-Status: NOT_RUN\n"
        "- Focused-Regression-Status: PASS\n"
    )
    assert validate_asdw_step12_evidence_report(report, log) == []


def test_bash_syntax_failure_yields_artifact_fail(tmp_path: Path) -> None:
    _write_script(tmp_path)
    log = _run(tmp_path, bash_syntax_runner=lambda _script: 1)
    assert "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: FAIL" in log


def test_shellcheck_failure_yields_artifact_fail(tmp_path: Path) -> None:
    _write_script(tmp_path)
    log = _run(tmp_path, shellcheck_runner=lambda _script: 1)
    assert "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: FAIL" in log


def test_unavailable_shellcheck_is_not_a_failure(tmp_path: Path) -> None:
    _write_script(tmp_path)
    log = _run(tmp_path, shellcheck_runner=lambda _script: None)
    assert "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: PASS" in log


def test_artifact_validator_errors_yield_artifact_fail(tmp_path: Path) -> None:
    _write_script(tmp_path)
    log = _run(tmp_path, artifact_validator=lambda _script: ["boom"])
    assert "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: FAIL" in log


@pytest.mark.parametrize(
    "payload",
    (
        b"\xef\xbb\xbf#!/usr/bin/env bash\n",  # UTF-8 BOM
        b"#!/usr/bin/env bash\r\nset -e\r\n",  # CRLF
    ),
)
def test_bom_or_crlf_script_yields_artifact_fail(
    tmp_path: Path, payload: bytes
) -> None:
    _write_script(tmp_path, payload)
    log = _run(tmp_path)
    assert "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: FAIL" in log


def test_checks_run_in_the_fixed_order(tmp_path: Path) -> None:
    _write_script(tmp_path)
    order: list[str] = []

    def _record(name: str, result: Any) -> Any:
        def _runner(_script: Path) -> Any:
            order.append(name)
            return result

        return _runner

    _run(
        tmp_path,
        bash_syntax_runner=_record("bash", 0),
        shellcheck_runner=_record("shellcheck", 0),
        artifact_validator=_record("artifact", []),
    )
    assert order == ["bash", "shellcheck", "artifact"]


def test_missing_script_fails_artifact_without_running_local_tools(
    tmp_path: Path,
) -> None:
    invoked: list[str] = []

    def _record(name: str, result: Any) -> Any:
        def _runner(_script: Path) -> Any:
            invoked.append(name)
            return result

        return _runner

    log = _run(
        tmp_path,  # no verify script written
        bash_syntax_runner=_record("bash", 0),
        shellcheck_runner=_record("shellcheck", 0),
        artifact_validator=_record("artifact", []),
    )
    assert "HVE-STEP12-ARTIFACT-CONTRACT-STATUS: FAIL" in log
    assert invoked == []  # a missing artifact short-circuits every local tool


def test_live_red_status_passes_through(tmp_path: Path) -> None:
    _write_script(tmp_path)
    log = _run(tmp_path, live_red_status="BLOCKED")
    assert "HVE-STEP12-LIVE-RED-STATUS: BLOCKED" in log


def test_local_verification_never_spawns_a_pytest_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-CLI-72: a product run must not launch the repository's own suite.

    Only the injectable bash/ShellCheck boundaries may reach a subprocess, and
    those are stubbed here, so any surviving command is a regression.
    """
    _write_script(tmp_path)
    spawned: list[tuple[str, ...]] = []

    def _record(cmd: Any, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        spawned.append(tuple(str(part) for part in cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", _record)

    run_asdw_step12_local_verification(
        tmp_path,
        artifact_validator=lambda _script: [],
        bash_syntax_runner=lambda _script: 0,
        shellcheck_runner=lambda _script: 0,
    )

    assert spawned == []


def test_module_exposes_no_focused_pytest_surface() -> None:
    """FR-CLI-72: the focused regression is a CI/dev concern, not runtime."""
    for removed in (
        "_FOCUSED_PYTEST_TARGETS",
        "_default_pytest_runner",
        "PytestRunner",
    ):
        assert not hasattr(verification, removed), removed

    parameters = inspect.signature(run_asdw_step12_local_verification).parameters
    assert [name for name in parameters if "pytest" in name] == []
