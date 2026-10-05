"""FR-LOCAL-SURFACE-04: Windows 11 x64 bootstrap launcher contract。"""
from __future__ import annotations

import re
import json
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_CMD = _ROOT / "hve" / "bootstrap" / "Start-HVE.cmd.in"
_PS1 = _ROOT / "hve" / "bootstrap" / "Start-HVE.ps1"
_RUNTIME_CHECK = _ROOT / "hve" / "bootstrap" / "windows-pwsh-runtime-check.ps1"
_WINGET_INSPECT = _ROOT / "hve" / "bootstrap" / "winget-module-inspect.ps1"
_SOURCES = _ROOT / "hve" / "bootstrap" / "bootstrap-sources.json"

_POWERSHELL_VERSION = "7.6.5"
_POWERSHELL_SHA256 = "32eb8f6cdce08f86e987d625a2733e54ac3e289ae7e1621b14c0b5bcec2434ea"
_WINGET_CLIENT_VERSION = "1.29.280"
_WINGET_CLIENT_SHA256 = "726602001e6137efff66aa73c197c6ab6396ae2f9634d0adaada17ec5068ee46"
_PWSH = shutil.which("pwsh.exe") or shutil.which("pwsh")
_pwsh_required = pytest.mark.skipif(_PWSH is None, reason="PowerShell 7+ is required")
_windows_required = pytest.mark.skipif(os.name != "nt", reason="Windows native contract")


def _read(path: Path) -> str:
    assert path.is_file(), f"required Windows bootstrap source is missing: {path}"
    return path.read_text(encoding="utf-8")


def _position(text: str, literal: str) -> int:
    index = text.find(literal)
    assert index >= 0, f"missing contract literal: {literal}"
    return index


def _pwsh_json(tmp_path: Path, body: str, *, args: list[str] | None = None) -> dict[str, Any]:
    harness = tmp_path / "contract.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)\n"
        f". '{str(_PS1).replace("'", "''")}'\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [str(_PWSH), "-NoLogo", "-NoProfile", "-File", str(harness), *(args or [])],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout)
    assert isinstance(data, dict)
    return data


def _render_cmd(tmp_path: Path, *, critical_list: bytes, critical_hash: str | None = None) -> Path:
    sources = json.loads(_read(_SOURCES))
    rendered = _read(_CMD)
    values = {
        "{{POWERSHELL_VERSION}}": sources["powershell"]["version"],
        "{{POWERSHELL_WINDOWS_X64_URL}}": sources["powershell"]["windows_x64_url"],
        "{{POWERSHELL_WINDOWS_X64_SHA256}}": sources["powershell"]["windows_x64_sha256"],
        "{{CRITICAL_LIST_SHA256}}": critical_hash or hashlib.sha256(critical_list).hexdigest(),
    }
    for token, value in values.items():
        assert token in rendered
        rendered = rendered.replace(token, value)
    assert "{{" not in rendered and "}}" not in rendered
    root = tmp_path / "distribution"
    root.mkdir(exist_ok=True)
    # A failed guard in a native test must never reach the host network.
    rendered = rendered.replace("%SYSTEM_NATIVE%\\curl.exe", "%ROOT%\\network-denied.exe")
    launcher = root / "Start-HVE.cmd"
    launcher.write_text(rendered, encoding="utf-8", newline="\r\n")
    (root / "hve-bootstrap-critical.sha256").write_bytes(critical_list)
    return launcher


def _run_cmd(path: Path, *, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    native = Path(os.environ["SystemRoot"]) / "System32"
    env["PATH"] = str(native)
    env["HVE_TEST_LAUNCHER"] = str(path)
    env.update(env_overrides or {})
    return subprocess.run(
        f'"{native / "cmd.exe"}" /d /v:off /s /c ""%HVE_TEST_LAUNCHER%""',
        cwd=str(path.parent),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )


def test_windows_bootstrap_sources_exist_with_safe_text_formats() -> None:
    cmd = _CMD.read_bytes()
    ps1 = _PS1.read_bytes()
    runtime = _RUNTIME_CHECK.read_bytes()
    inspect = _WINGET_INSPECT.read_bytes()
    sources = _SOURCES.read_bytes()

    assert cmd and ps1 and runtime and inspect and sources
    assert not any(
        value.startswith(b"\xef\xbb\xbf")
        for value in (cmd, ps1, runtime, inspect, sources)
    )
    assert b"\r\n" in cmd
    assert b"\n" not in cmd.replace(b"\r\n", b"")
    # Design 9 requires interpreter-appropriate newlines; PowerShell accepts
    # both LF and CRLF. Unlike macOS scripts, it has no normative LF-only rule.
    # bootstrap-sources.json is input metadata, not the generated
    # hve-bootstrap-manifest.json whose LF contract design section 8 fixes.
    for script in (ps1, runtime, inspect, sources):
        script.decode("utf-8", errors="strict")
        assert b"\r" not in script.replace(b"\r\n", b"")
        if b"\r\n" in script:
            assert b"\n" not in script.replace(b"\r\n", b"")


def test_bootstrap_source_manifest_is_closed_and_matches_spike_candidates() -> None:
    data = json.loads(_read(_SOURCES))
    assert set(data) == {"schema_version", "powershell", "winget_client", "homebrew"}
    assert data["schema_version"] == 1
    assert data["powershell"] == {
        "version": _POWERSHELL_VERSION,
        "windows_x64_url": (
            "https://github.com/PowerShell/PowerShell/releases/download/v7.6.5/"
            "PowerShell-7.6.5-win-x64.zip"
        ),
        "windows_x64_sha256": _POWERSHELL_SHA256,
        "redirect_hosts": ["github.com", "release-assets.githubusercontent.com"],
    }
    assert data["winget_client"] == {
        "candidate_version": _WINGET_CLIENT_VERSION,
        "package_url": (
            "https://www.powershellgallery.com/api/v2/package/"
            "Microsoft.WinGet.Client/1.29.280"
        ),
        "package_sha256": _WINGET_CLIENT_SHA256,
        "redirect_hosts": ["www.powershellgallery.com", "cdn.powershellgallery.com"],
        "repair_argv_candidate": ["Repair-WinGetPackageManager", "-Force", "-Latest"],
        "repair_live_verified": False,
    }


def test_cmd_uses_only_native_tools_until_verified_pwsh() -> None:
    text = _read(_CMD)
    lowered = text.lower()

    assert "setlocal enableextensions disabledelayedexpansion" in lowered
    assert "powershell.exe" not in lowered
    assert re.search(r"(?im)^\s*powershell(?:\s|$)", text) is None
    for command in ("curl.exe", "tar.exe", "certutil.exe", "findstr.exe", "where.exe"):
        assert f'%SYSTEM_NATIVE%\\{command}' in text
    assert '"%PROBE_DIR%\\pwsh.exe" -NoLogo -NoProfile -File' in text
    assert "-Command" not in text
    assert "windows-pwsh-runtime-check.ps1" in text


def test_cmd_pins_powershell_download_and_redirect_policy() -> None:
    text = _read(_CMD)

    assert "{{POWERSHELL_WINDOWS_X64_URL}}" in text
    assert "{{POWERSHELL_WINDOWS_X64_SHA256}}" in text
    assert "{{POWERSHELL_VERSION}}" in text
    assert '--proto "=https"' in text
    assert '--proto-redir "=https"' in text
    assert 'https://github.com/' in text
    assert 'https://release-assets.githubusercontent.com/' in text
    assert "url_effective" in text
    assert "redirect-host" in text


def test_cmd_checks_platform_and_critical_payload_before_any_install() -> None:
    text = _read(_CMD)

    platform = _position(text, "PROCESSOR_ARCHITECTURE")
    critical = _position(text, "hve-bootstrap-critical.sha256")
    winget = _position(text, "winget.exe")
    download = _position(text, "PowerShell-7.6.5-win-x64.zip")
    setup = _position(text, "Start-HVE.ps1")

    assert platform < critical < winget < download < setup
    assert "Windows 11" in text
    assert "EXPECTED_CRITICAL_LIST_SHA256={{CRITICAL_LIST_SHA256}}" in text
    assert "critical-list-hash" in text
    assert "critical-file-hash" in text


def test_cmd_passes_paths_as_arguments_and_cleans_before_success() -> None:
    text = _read(_CMD)

    assert "EnableDelayedExpansion" not in text
    assert "-ExpectedExecutable" in text
    assert "-File \"%RUNTIME_CHECK%\"" in text
    assert "PROBE_DIR%\\pwsh.exe')" not in text
    assert "call :cleanup_files" in text
    assert _position(text, ":cleanup_files") < _position(text, "BOOTSTRAP_READY")
    assert "cleanup=true" in text
    assert "if exist \"%PROBE_DIR%\"" in text


@_windows_required
@pytest.mark.parametrize("directory_name", ["distribution", "space 日本語 quote' bang!"])
def test_generated_cmd_rejects_wrong_architecture_before_network(
    tmp_path: Path, directory_name: str
) -> None:
    scoped = tmp_path / directory_name
    scoped.mkdir()
    launcher = _render_cmd(scoped, critical_list=b"")
    completed = _run_cmd(
        launcher,
        env_overrides={"PROCESSOR_ARCHITECTURE": "ARM64", "PROCESSOR_ARCHITEW6432": ""},
    )
    assert completed.returncode == 2
    assert "stage=platform reason=not-x64" in completed.stdout
    assert not (launcher.parent / "PowerShell-7.6.5-win-x64.zip").exists()


@_windows_required
def test_generated_cmd_rejects_critical_list_hash_before_network(tmp_path: Path) -> None:
    launcher = _render_cmd(
        tmp_path, critical_list=b"payload", critical_hash="0" * 64
    )
    completed = _run_cmd(launcher)
    assert completed.returncode != 0
    assert "stage=integrity reason=critical-list-hash" in completed.stdout
    assert not (launcher.parent / "PowerShell-7.6.5-win-x64.zip").exists()


@_windows_required
@pytest.mark.parametrize(
    ("owner", "reason", "lock_remains"),
    [
        (f"PID={os.getpid()}\r\nSTARTED_UTC=2026-09-06T00:00:00Z\r\n", "lock-owner-live", True),
        ("PID=not-an-int\r\nSTARTED_UTC=bad\r\n", "lock-owner-unverifiable", True),
        ("PID=999999\r\nSTARTED_UTC=2026-09-06T00:00:00Z\r\n", "critical-file-hash", False),
    ],
)
def test_generated_cmd_lock_outcomes_are_fail_closed(
    tmp_path: Path, owner: str, reason: str, lock_remains: bool
) -> None:
    # Design section 7 fixes the critical-list delimiter at two spaces.
    critical = ("0" * 64 + "  missing-file\r\n").encode("ascii")
    launcher = _render_cmd(tmp_path, critical_list=critical)
    lock = launcher.parent / ".hve-bootstrap" / "bootstrap.lock"
    lock.mkdir(parents=True)
    (lock / "owner.txt").write_text(owner, encoding="ascii", newline="")

    completed = _run_cmd(launcher)

    assert completed.returncode != 0
    assert f"reason={reason}" in completed.stdout
    assert lock.exists() is lock_remains
    assert not (launcher.parent / "PowerShell-7.6.5-win-x64.zip").exists()


@pytest.mark.parametrize(
    ("state", "exit_code", "expected_action"),
    [
        ("ready", 0, "launch_gui"),
        ("needs_setup", 10, "run_setup"),
        ("needs_version_decision", 11, "launch_version_entrypoint"),
        ("blocked", 12, "stop"),
        ("blocked", 2, "stop"),
    ],
)
@_pwsh_required
def test_powershell_state_plan_is_executable_and_fail_closed(
    tmp_path: Path, state: str, exit_code: int, expected_action: str
) -> None:
    data = _pwsh_json(
        tmp_path,
        "$value = Resolve-HveBootstrapAction "
        f"-State '{state}' -VerifierExit {exit_code}\n"
        "$value | ConvertTo-Json -Compress",
    )
    assert data == {"state": state, "verifier_exit": exit_code, "action": expected_action}


@_pwsh_required
def test_powershell_state_plan_rejects_state_exit_mismatch(tmp_path: Path) -> None:
    harness = tmp_path / "contract.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f". '{str(_PS1).replace("'", "''")}'\n"
        "try { Resolve-HveBootstrapAction -State 'ready' -VerifierExit 10; exit 0 } "
        "catch { if ($_.Exception.Message -eq 'state-exit-mismatch') { exit 23 }; exit 24 }\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [str(_PWSH), "-NoLogo", "-NoProfile", "-File", str(harness)],
        cwd=str(_ROOT),
        check=False,
    )
    assert completed.returncode == 23


@_pwsh_required
def test_powershell_argv_helpers_round_trip_special_root(tmp_path: Path) -> None:
    root = tmp_path / "space 日本語 quote' bang!"
    root.mkdir()
    data = _pwsh_json(
        tmp_path,
        "$root = $args[0]\n"
        "$value = [ordered]@{ "
        "setup = @(Get-HveSetupArgList -Root $root); "
        "verifier = @(Get-HveVerifierArgList -Root $root); "
        "gui = @(Get-HveGuiArgList) }\n"
        "$value | ConvertTo-Json -Compress",
        args=[str(root)],
    )
    assert data["setup"] == [
        "-NoLogo",
        "-NoProfile",
        "-File",
        str(root / "hve" / "setup-hve.ps1"),
        "-Yes",
        "-NoGlobalCleanup",
    ]
    assert data["verifier"] == [
        "-I",
        "-m",
        "hve.bootstrap_verify",
        "--root",
        str(root),
        "--json",
    ]
    assert data["gui"] == ["gui"]
    assert "-Force" not in data["setup"]


@_pwsh_required
@_windows_required
def test_sequence_uses_helpers_and_records_exact_event_counts(tmp_path: Path) -> None:
    data = _pwsh_json(
        tmp_path,
        "$events = [Collections.Generic.List[object]]::new()\n"
        "$runner = { param($stage, $exe, $argv) "
        "$events.Add([ordered]@{stage=$stage;exe=$exe;argv=@($argv)}) | Out-Null; "
        "if ($stage -eq 'verifier') { return [ordered]@{exit_code=0;state='ready'} }; "
        "return [ordered]@{exit_code=0} }\n"
        "$rc = Invoke-HveBootstrapSequence -Root 'C:\\Dist' "
        "-InitialState 'needs_setup' -InitialExit 10 -ProcessRunner $runner\n"
        "[ordered]@{rc=$rc;events=@($events)} | ConvertTo-Json -Compress -Depth 6",
    )
    assert data["rc"] == 0
    # Design 5.1/5.2: setup runs the final verifier itself, not the launcher.
    assert [item["stage"] for item in data["events"]] == ["setup", "gui"]
    assert data["events"][0]["argv"][-2:] == ["-Yes", "-NoGlobalCleanup"]
    assert "-Force" not in data["events"][0]["argv"]
    assert data["events"][1]["argv"] == ["gui"]


@_pwsh_required
@_windows_required
@pytest.mark.parametrize(
    ("failed_stage", "child_exit", "expected_stages"),
    [
        ("setup", 31, ["setup"]),
        ("setup", 12, ["setup"]),  # setup propagates its own failed verifier
        ("gui", 41, ["setup", "gui"]),
    ],
)
def test_sequence_stops_at_each_failed_child_and_propagates_exit(
    tmp_path: Path,
    failed_stage: str,
    child_exit: int,
    expected_stages: list[str],
) -> None:
    data = _pwsh_json(
        tmp_path,
        "$events = [Collections.Generic.List[string]]::new()\n"
        "$failedStage = $args[0]\n"
        "$failedExit = [int]$args[1]\n"
        "$runner = { param($stage, $exe, $argv) $events.Add($stage) | Out-Null; "
        "if ($stage -eq $failedStage) { "
        "if ($stage -eq 'verifier') { return [ordered]@{exit_code=$failedExit;state='blocked'} }; "
        "return [ordered]@{exit_code=$failedExit} }; "
        "if ($stage -eq 'verifier') { return [ordered]@{exit_code=0;state='ready'} }; "
        "return [ordered]@{exit_code=0} }\n"
        "$rc = Invoke-HveBootstrapSequence -Root 'C:\\Dist' "
        "-InitialState 'needs_setup' -InitialExit 10 -ProcessRunner $runner\n"
        "[ordered]@{rc=$rc;events=@($events)} | ConvertTo-Json -Compress",
        args=[failed_stage, str(child_exit)],
    )
    assert data["events"] == expected_stages
    assert data["rc"] == child_exit


@_pwsh_required
@pytest.mark.parametrize(
    ("initial_state", "expected_stages"),
    [
        pytest.param("ready", ["gui"], marks=_windows_required),
        pytest.param("needs_version_decision", ["version-entrypoint"], marks=_windows_required),
        ("blocked", []),
    ],
)
def test_sequence_fast_version_and_blocked_paths(
    tmp_path: Path, initial_state: str, expected_stages: list[str]
) -> None:
    initial_exit = {"ready": 0, "needs_version_decision": 11, "blocked": 12}[initial_state]
    data = _pwsh_json(
        tmp_path,
        "$events = [Collections.Generic.List[string]]::new()\n"
        "$runner = { param($stage, $exe, $argv) $events.Add($stage) | Out-Null; "
        "return [ordered]@{exit_code=0;state='ready'} }\n"
        f"$rc = Invoke-HveBootstrapSequence -Root 'C:\\Dist' -InitialState '{initial_state}' "
        f"-InitialExit {initial_exit} -ProcessRunner $runner\n"
        "[ordered]@{rc=$rc;events=@($events)} | ConvertTo-Json -Compress",
    )
    assert data["events"] == expected_stages
    assert data["rc"] == (12 if initial_state == "blocked" else 0)


@_pwsh_required
def test_unverified_winget_repair_candidate_is_not_executed(tmp_path: Path) -> None:
    data = _pwsh_json(
        tmp_path,
        "$source = Get-Content -Raw -LiteralPath $args[0] | ConvertFrom-Json\n"
        "$value = Get-HveWinGetRepairPlan -Source $source.winget_client\n"
        "$value | ConvertTo-Json -Compress",
        args=[str(_SOURCES)],
    )
    assert data == {
        "allowed": False,
        "reason_code": "winget-repair-not-live-verified",
        "argv": [],
    }


def test_cmd_uses_atomic_lock_and_rejects_live_or_unverifiable_owner() -> None:
    text = _read(_CMD)

    assert "bootstrap.lock" in text
    # A complete owner directory is atomically renamed; no pending shared lock.
    assert 'mkdir "%LOCK_STAGE%"' in text
    assert 'ren "%LOCK_STAGE%" bootstrap.lock' in text
    assert "PID=pending" not in text
    assert "tasklist.exe" in text
    assert "lock-owner-live" in text
    assert "lock-owner-unverifiable" in text
    assert "lock-owner-stale" in text
    assert "PID" in text
    assert "STARTED_UTC" in text
    assert "COMMAND_LINE" not in text
    assert "TOKEN" not in text


def test_powershell_stage_pins_winget_module_and_validates_ownership() -> None:
    text = _read(_PS1)
    inspect = _read(_WINGET_INSPECT)

    assert "$PSVersionTable.PSEdition -ne 'Core'" in text
    assert "$PSVersionTable.PSVersion.Major -lt 7" in text
    assert "bootstrap-sources.json" in text
    assert "candidate_version" in text
    assert "package_sha256" in text
    assert "www.powershellgallery.com" in text
    assert "cdn.powershellgallery.com" in text
    assert "Repair-WinGetPackageManager" in text
    assert "'-Force'" in text and "'-Latest'" in text
    assert "Import-Module" in inspect
    assert "-PassThru" in inspect
    assert "ModuleBase" in inspect
    assert "Get-Command Repair-WinGetPackageManager -Module" in inspect
    assert "command_module_base_match" in inspect


def test_setup_verifier_and_gui_argv_are_exact_and_ordered() -> None:
    text = _read(_PS1)
    setup = _read(_ROOT / "hve" / "setup-hve.ps1")

    for helper in (
        "Get-HveSetupArgList",
        "Get-HveGuiArgList",
        "Resolve-HveBootstrapAction",
        "Resolve-HveChildExit",
        "Invoke-HveBootstrapSequence",
        "Get-HveWinGetRepairPlan",
    ):
        assert text.count(helper) >= 2, f"{helper} must be defined and consumed"
    assert (text + setup).count("Get-HveVerifierArgList") >= 2
    assert (text + setup).count("Validate-BootstrapPayload") >= 2
    main_body = text.split("function Invoke-HveWindowsBootstrap", 1)[1]
    assert "Invoke-HveBootstrapSequence" in main_body


def test_windows_state_machine_does_not_launch_gui_on_failure_or_version_decision() -> None:
    text = _read(_PS1)

    assert "Validate-BootstrapPayload" in text
    assert "state-exit-mismatch" in text
    assert "needs_version_decision" in text
    assert "needs_setup" in text
    assert "blocked" in text
    assert "exit 10" in text
    assert "exit 11" in text
    assert "exit 12" in text
    sequence = text.split("function Invoke-HveBootstrapSequence", 1)[1].split(
        "function ", 1
    )[0]
    assert "Resolve-HveBootstrapAction" in sequence
    assert "Resolve-HveChildExit" in sequence
    assert "& $ProcessRunner 'gui'" in sequence
    assert "& $ProcessRunner 'verifier'" not in sequence


@pytest.mark.parametrize("child_exit", [1, 2, 3, 10, 11, 12, 255])
@_pwsh_required
def test_child_failures_are_never_rounded_to_success(
    tmp_path: Path, child_exit: int
) -> None:
    data = _pwsh_json(
        tmp_path,
        "$value = Resolve-HveChildExit "
        f"-Stage 'setup' -ChildExit {child_exit}\n"
        "$value | ConvertTo-Json -Compress",
    )
    assert data == {"stage": "setup", "exit_code": child_exit, "launch_gui": False}


def test_windows_bootstrap_has_no_auth_cloud_workflow_or_azure_side_effects() -> None:
    combined = "\n".join(
        line
        for path in (_CMD, _PS1, _RUNTIME_CHECK, _WINGET_INSPECT)
        for line in _read(path).lower().splitlines()
        if not line.lstrip().startswith(("#", "rem ", "::"))
    )
    for forbidden in (
        "gh auth login",
        "copilot login",
        "az login",
        "run_workflow",
        "hve orchestrate",
        "git init",
        "git pull",
        "git fetch",
        "gh issue",
        "gh pr",
        "gh release",
        "set-executionpolicy",
        "unblock-file",
    ):
        assert forbidden not in combined
