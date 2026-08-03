"""Unit tests for TDD test report validation."""

from __future__ import annotations

from pathlib import Path

from hve import artifact_validation as av


def _write_report(tmp_path: Path, content: str) -> Path:
    report = tmp_path / "tdd-test-report.md"
    report.write_text(content, encoding="utf-8")
    return report


def _valid_report(phase: str = "RED", judgement: str = "PASS") -> str:
    return f"""# TDD Test Report

<!-- validation-confirmed -->

- Schema-Version: 1
- Workflow: asdw-web
- Step: 3.2
- Agent: Dev-Microservice-Azure-ServiceTestCoding
- Target-Key: SVC-13
- Phase: {phase}
- Test-Code-Path: src/test/api/SVC-13.Tests/
- Timestamp-UTC: 2026-07-06T00:00:00Z
- Evidence-Status: EXECUTED
- TDD-Judgement: {judgement}

## Command

- CWD: c:/repo
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
- Raw-Log-Path: N/A
- Secret-Redaction: confirmed

## Failure Analysis

- Root-Cause: expected RED
- Next-Action: implement GREEN step

## Test Protection

- Test-Files-Changed: N/A
- Allowed-Test-Changes: N/A
"""


def test_valid_red_report_passes(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _valid_report("RED", "PASS"))
    assert av.validate_tdd_test_report(report, expected_phase="RED") == []


def test_preloaded_report_text_is_the_validated_snapshot(tmp_path: Path) -> None:
    report = _write_report(tmp_path, "# malformed on disk\n")

    assert av.validate_tdd_test_report(
        report,
        expected_phase="RED",
        report_text=_valid_report("RED", "PASS"),
    ) == []


def test_missing_report_fails(tmp_path: Path) -> None:
    missing = tmp_path / "missing.md"
    errors = av.validate_tdd_test_report(missing, expected_phase="RED")
    assert errors
    assert "not found" in errors[0]


def test_missing_validation_marker_fails(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _valid_report().replace("<!-- validation-confirmed -->\n\n", ""))
    errors = av.validate_tdd_test_report(report, expected_phase="RED")
    assert any("validation-confirmed" in e for e in errors)


def test_missing_required_label_fails(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _valid_report().replace("- TDD-Judgement: PASS\n", ""))
    errors = av.validate_tdd_test_report(report, expected_phase="RED")
    assert any("TDD-Judgement" in e for e in errors)


def test_plain_labels_without_markdown_list_marker_fail(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        _valid_report().replace("- Schema-Version: 1", "Schema-Version: 1"),
    )
    errors = av.validate_tdd_test_report(report, expected_phase="RED")
    assert any("Schema-Version" in e for e in errors)


def test_result_heading_alias_does_not_replace_actual_result(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _valid_report().replace("## Actual Result", "## Result"))
    errors = av.validate_tdd_test_report(report, expected_phase="RED")
    assert any("## Actual Result" in e for e in errors)


def test_changed_test_files_heading_does_not_replace_test_protection(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        _valid_report().replace("## Test Protection", "## Changed Test Files"),
    )
    errors = av.validate_tdd_test_report(report, expected_phase="RED")
    assert any("## Test Protection" in e for e in errors)


def test_wrong_phase_fails(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _valid_report("RED", "PASS"))
    errors = av.validate_tdd_test_report(report, expected_phase="GREEN")
    assert any("Phase" in e and "GREEN" in e for e in errors)


def test_workflow_mismatch_fails_when_expected_workflow_is_supplied(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        _valid_report().replace("- Workflow: asdw-web", "- Workflow: Dev-Microservice-Azure-UITestCoding"),
    )
    errors = av.validate_tdd_test_report(report, expected_phase="RED", expected_workflow="asdw-web")
    assert any("Workflow mismatch" in e and "asdw-web" in e for e in errors)


def test_target_key_mismatch_fails_when_expected_target_is_supplied(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _valid_report())
    errors = av.validate_tdd_test_report(report, expected_phase="RED", expected_target_key="APP-009-S005")
    assert any("Target-Key mismatch" in e and "APP-009-S005" in e for e in errors)


def test_green_report_requires_pass_judgement(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _valid_report("GREEN", "FAIL"))
    errors = av.validate_tdd_test_report(report, expected_phase="GREEN")
    assert any("TDD-Judgement" in e and "PASS" in e for e in errors)


def test_green_report_accepts_blocked_judgement(tmp_path: Path) -> None:
    # BLOCKED records an honest GREEN terminal for a confirmed test-side /
    # shared-config blocker. The gate must not error, same as PASS.
    report = _write_report(tmp_path, _valid_report("GREEN", "BLOCKED"))
    assert av.validate_tdd_test_report(report, expected_phase="GREEN") == []


def test_asdw_ui_red_tbd_guard_rejects_executable_unresolved_tbd(tmp_path: Path) -> None:
    test_file = tmp_path / "src" / "test" / "ui" / "APP-009-S009" / "APP-009-S009.red.test.js"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "test('contract', () => {\n"
        "  const contract = { endpoint: 'TBD（要確認）' };\n"
        "  expect(contract.endpoint !== 'TBD（要確認）').toBe(true);\n"
        "});\n",
        encoding="utf-8",
    )

    guard = getattr(av, "validate_asdw_ui_red_tests_no_unresolved_contracts")
    errors = guard(test_file.parent)

    assert errors
    assert "executable unresolved TBD" in errors[0]
    assert "APP-009-S009.red.test.js:2" in errors[0]


def test_asdw_ui_red_tbd_guard_ignores_comment_only_tbd(tmp_path: Path) -> None:
    test_file = tmp_path / "src" / "test" / "ui" / "APP-009-S009" / "APP-009-S009.red.test.js"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "// 契約確定待ち: TBD（要確認）\n"
        "test('ui red', () => {\n"
        "  expect(document.body).toBeDefined();\n"
        "});\n",
        encoding="utf-8",
    )

    guard = getattr(av, "validate_asdw_ui_red_tests_no_unresolved_contracts")
    assert guard(test_file.parent) == []


def test_asdw_ui_red_tbd_guard_scans_sibling_js_files_under_target_directory(tmp_path: Path) -> None:
    target_dir = tmp_path / "src" / "test" / "ui" / "APP-009-S009"
    target_dir.mkdir(parents=True)
    (target_dir / "APP-009-S009.red.test.js").write_text(
        "test('ui red', () => {\n"
        "  expect(document.body).toBeDefined();\n"
        "});\n",
        encoding="utf-8",
    )
    helper = target_dir / "apiMocks.js"
    helper.write_text(
        "export const endpoint = 'TBD（要確認）';\n",
        encoding="utf-8",
    )

    guard = getattr(av, "validate_asdw_ui_red_tests_no_unresolved_contracts")
    errors = guard(target_dir)

    assert errors
    assert "apiMocks.js:1" in errors[0]


def test_asdw_ui_red_tbd_guard_missing_path_is_noop(tmp_path: Path) -> None:
    guard = getattr(av, "validate_asdw_ui_red_tests_no_unresolved_contracts")

    assert guard(tmp_path / "missing" / "src" / "test" / "ui" / "APP-009-S009") == []
