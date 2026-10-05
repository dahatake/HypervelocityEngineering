"""N-14: Step 1.3 の失敗 stage の stderr 要約を、秘密を除いて証跡へ残す契約。"""
from __future__ import annotations

import subprocess

import hve.runner as runner_module
from hve import asdw_data_script_launcher as launcher
from hve.asdw_data_script_launcher import StageResult, summarize_stage_failure


def test_summary_keeps_the_azure_error_text() -> None:
    summary = summarize_stage_failure(
        b"ERROR: (UserException) AadBasedSecurityPrincipals cannot be null or empty\n"
    )
    assert "AadBasedSecurityPrincipals cannot be null or empty" in summary


def test_summary_masks_secret_shaped_values() -> None:
    guid = "12345678-1234-1234-1234-123456789abc"
    stderr = "\n".join(
        [
            f"subscription {guid} denied",
            "fetch https://example.invalid/path?sig=abc123 failed",
            "password=hunter2 rejected",
            "user alice@example.invalid not allowed",
            r"file C:\Users\alice\secret.txt missing",
            "open /home/alice/.azure/token failed",
            "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9abcdefghijklmnop",
            "blob " + "A" * 40,
        ]
    )
    summary = summarize_stage_failure(stderr)
    for leaked in (
        guid,
        "example.invalid",
        "sig=abc123",
        "hunter2",
        "alice",
        "eyJhbGci",
        "A" * 40,
    ):
        assert leaked not in summary, leaked
    assert "<redacted>" in summary


def test_summary_is_bounded_and_fence_safe() -> None:
    stderr = "\n".join(f"line {index} ```" for index in range(100))
    summary = summarize_stage_failure(stderr)
    assert len(summary.splitlines()) <= 20
    assert len(summary) <= 2003
    assert "```" not in summary
    assert "line 99" in summary
    assert "line 0 " not in summary


def test_summary_of_missing_stderr_is_empty() -> None:
    assert summarize_stage_failure(None) == ""
    assert summarize_stage_failure(b"") == ""


def test_stage_runner_tees_stderr_and_keeps_a_tail(capfd) -> None:
    script = b"echo visible-error >&2\nexit 7\n"
    bash = launcher._trusted_bash_path()
    result = launcher._run_stage_process(
        [bash, "--noprofile", "--norc", "-s"],
        cwd=".",
        env={"PATH": ""},
        input=script,
    )
    assert result.returncode == 7
    assert b"visible-error" in result.stderr
    assert "visible-error" in capfd.readouterr().err


def test_failed_stage_summary_is_recorded_in_work_status(tmp_path) -> None:
    evidence = (
        "process-exit=1\n"
        "ERROR: no such host\n"
        "token=abcdef failed"
    )
    results = (
        StageResult(
            stage="prep", attempt=1, exit_code=1, reached=True, evidence=evidence
        ),
    )
    assert runner_module._write_asdw_data_deploy_evidence(
        tmp_path, "failure-summary", results
    ) == []
    work_status, _ac, _tdd = runner_module._asdw_data_deploy_evidence_paths(
        tmp_path, "failure-summary"
    )
    text = work_status.read_text(encoding="utf-8")
    assert "status: BLOCKED" in text
    assert "## Failure summary: prep (attempt 1)" in text
    assert "no such host" in text
    assert "abcdef" not in text


def test_successful_stage_records_no_failure_summary(tmp_path) -> None:
    results = tuple(
        StageResult(stage=s, attempt=a, exit_code=0, reached=True, evidence="process-exit=0")
        for s, a in runner_module._ASDW_DATA_DEPLOY_PIPELINE_SEQUENCE
    )
    assert runner_module._write_asdw_data_deploy_evidence(
        tmp_path, "no-failure", results
    ) == []
    work_status, _ac, _tdd = runner_module._asdw_data_deploy_evidence_paths(
        tmp_path, "no-failure"
    )
    assert "Failure summary" not in work_status.read_text(encoding="utf-8")


def test_execute_stage_hands_the_failure_summary_to_the_sink(
    tmp_path, monkeypatch
) -> None:
    from hve.tests.test_asdw_data_script_launcher import _write_stage_inputs

    _write_stage_inputs(tmp_path)
    monkeypatch.setattr(launcher, "_validate_stage", lambda *_args: [])
    monkeypatch.setattr(launcher, "_trusted_bash_path", lambda: "trusted-bash")

    def failing_run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 3, stdout=None, stderr=b"boom happened\n")

    sink: list[str] = []
    code = launcher.execute_stage(
        "prep",
        repo_root=tmp_path,
        process_runner=failing_run,
        _failure_summary_sink=sink,
    )
    assert code == 3
    assert sink == ["boom happened"]