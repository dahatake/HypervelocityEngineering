"""FR-LOCAL-SURFACE-04: macOS 15/26 arm64 bootstrap launcher contract。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_COMMAND = _ROOT / "hve" / "bootstrap" / "Start-HVE.command.in"
_SOURCES = _ROOT / "hve" / "bootstrap" / "bootstrap-sources.json"
_GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
_BASH = str(_GIT_BASH) if os.name == "nt" and _GIT_BASH.is_file() else shutil.which("bash")
_bash_required = pytest.mark.skipif(_BASH is None, reason="bash is required")

_HOMEBREW_COMMIT = "7a133dcc74051ee4efc79467ed215dfedf45aea2"
_HOMEBREW_SHA256 = "12479a24be3f5307eecac7cde670fad7118640f031229e964f544b1367b52a41"


def _read(path: Path) -> str:
    assert path.is_file(), f"required macOS bootstrap source is missing: {path}"
    return path.read_text(encoding="utf-8")


def _posix(path: Path) -> str:
    """Translate fixtures, not product argv, to Git Bash's POSIX namespace."""
    value = path.resolve().as_posix()
    return f"/{value[0].lower()}{value[2:]}" if os.name == "nt" else value


def _bash_run(
    tmp_path: Path, body: str, *, args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    harness = tmp_path / "contract.sh"
    # JSON is a test transport, not a Python dependency of the native launcher.
    test_helpers = (
        f"hve_json_string_lines() {{ {shlex_quote(_posix(Path(sys.executable)))} -I -c "
        + shlex_quote("import json,sys; print(','.join(json.dumps(x.rstrip('\\n'), ensure_ascii=False) for x in sys.stdin))")
        + "; }\n"
    )
    if sys.platform != "darwin":
        # Linux/Git Bash have GNU stat, not macOS stat. Only the external OS
        # command seam is replaced; ownership control flow stays real.
        test_helpers += 'hve_lock_identity() { /usr/bin/stat -c "%d:%i" -- "$1"; }\n'
    if os.name == "nt":
        # Git Bash has sha256sum, not macOS shasum.
        test_helpers += (
            '/usr/bin/shasum() { [[ "$1" == -a && "$2" == 256 ]] || return 98; '
            'shift 2; command sha256sum "$@"; }\n'
        )
    harness.write_text(
        "#!/usr/bin/env bash\nset -eu\n"
        f"source {shlex_quote(_posix(_COMMAND))}\n"
        "printf 'HVE_SOURCE_OK\\n' >/dev/null\n"
        + test_helpers
        + body
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return subprocess.run(
        [str(_BASH), "--noprofile", "--norc", "-p", _posix(harness), *(args or [])],
        cwd=str(_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
        timeout=30,
    )


def _bash_json(tmp_path: Path, body: str, *, args: list[str] | None = None) -> dict[str, Any]:
    completed = _bash_run(tmp_path, body, args=args)
    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout)
    assert isinstance(data, dict)
    return data


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _render_command(tmp_path: Path, *, critical_list: bytes, critical_hash: str | None = None) -> Path:
    sources = json.loads(_read(_SOURCES))
    rendered = _read(_COMMAND)
    values = {
        "{{HOMEBREW_INSTALL_URL}}": sources["homebrew"]["install_url"],
        "{{HOMEBREW_INSTALL_SHA256}}": sources["homebrew"]["install_sha256"],
        "{{CRITICAL_LIST_SHA256}}": critical_hash or hashlib.sha256(critical_list).hexdigest(),
    }
    for token, value in values.items():
        assert token in rendered
        rendered = rendered.replace(token, value)
    assert "{{" not in rendered and "}}" not in rendered
    root = tmp_path / "distribution"
    root.mkdir()
    command = root / "Start-HVE.command"
    command.write_text(rendered, encoding="utf-8", newline="\n")
    command.chmod(0o755)
    (root / "hve-bootstrap-critical.sha256").write_bytes(critical_list)
    return command


def test_macos_bootstrap_source_is_lf_no_bom_and_nonempty() -> None:
    command = _COMMAND.read_bytes()
    assert command
    assert not command.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in command
    # -p ignores inherited BASH_ENV / shell functions before the first guard.
    assert command.startswith(b"#!/bin/bash -p\n")


def test_homebrew_source_manifest_is_immutable_and_hash_pinned() -> None:
    data = json.loads(_read(_SOURCES))["homebrew"]
    assert data == {
        "commit": _HOMEBREW_COMMIT,
        "install_url": (
            "https://raw.githubusercontent.com/Homebrew/install/"
            f"{_HOMEBREW_COMMIT}/install.sh"
        ),
        "install_sha256": _HOMEBREW_SHA256,
        "redirect_hosts": ["raw.githubusercontent.com"],
    }


def test_command_resolves_its_own_physical_directory_not_finder_cwd() -> None:
    text = _read(_COMMAND)
    assert 'BASH_SOURCE[0]' in text
    assert "pwd -P" in text
    assert "distribution_root" in text.lower()
    assert "$PWD" not in text
    assert "cd ~" not in text
    assert "source ~/." not in text


def test_command_checks_darwin_arm64_and_os_major_before_install() -> None:
    text = _read(_COMMAND)
    positions = [
        text.find(literal)
        for literal in (
            "/usr/bin/uname -s",
            "/usr/bin/uname -m",
            "/usr/bin/sw_vers -productVersion",
            "hve-bootstrap-critical.sha256",
            "xcode-select --install",
            "install.sh",
            "setup-hve.sh",
        )
    ]
    assert all(value >= 0 for value in positions)
    assert positions == sorted(positions)
    assert "15|26" in text
    assert "not-darwin" in text
    assert "not-arm64" in text
    assert "unsupported-macos-major" in text


def test_command_validates_critical_payload_before_clt_or_homebrew() -> None:
    text = _read(_COMMAND)
    assert 'EXPECTED_CRITICAL_LIST_SHA256="{{CRITICAL_LIST_SHA256}}"' in text
    assert "/usr/bin/shasum -a 256" in text
    assert "critical-list-hash" in text
    assert "critical-file-hash" in text
    assert text.find("critical-list-hash") < text.find("xcode-select --install")
    assert text.find("critical-file-hash") < text.find("install.sh")


def test_command_uses_absolute_homebrew_then_current_process_shellenv() -> None:
    text = _read(_COMMAND)
    assert "/opt/homebrew/bin/brew" in text
    assert 'shellenv="$(hve_exec /opt/homebrew/bin/brew shellenv)"' in text
    assert 'eval "$shellenv"' in text
    assert text.find("/opt/homebrew/bin/brew") < text.find("sudo -v")
    assert "~/.zprofile" not in text
    assert "~/.bash_profile" not in text
    assert "HOMEBREW_PREFIX" not in text


def test_command_pins_homebrew_download_without_a_circular_live_gate() -> None:
    text = _read(_COMMAND)
    assert 'HOMEBREW_INSTALL_URL="{{HOMEBREW_INSTALL_URL}}"' in text
    assert 'HOMEBREW_INSTALL_SHA256="{{HOMEBREW_INSTALL_SHA256}}"' in text
    assert "/usr/bin/curl" in text
    assert '--proto "=https"' in text
    assert '--proto-redir "=https"' in text
    assert "raw.githubusercontent.com" in text
    assert "NONINTERACTIVE=1 /bin/bash" in text
    assert "homebrew-installer-not-clean-os-verified" not in text


def test_clt_wait_is_bounded_and_refusal_is_failure() -> None:
    text = _read(_COMMAND)
    assert "/usr/bin/xcode-select -p" in text
    assert "/usr/bin/xcode-select --install" in text
    assert "CLT_TIMEOUT_SECONDS=900" in text
    assert "clt-timeout" in text
    assert "clt-refused" in text
    assert "sleep 5" in text


@_bash_required
@pytest.mark.parametrize(
    ("os_name", "machine", "major", "critical", "clt", "expected"),
    [
        ("Linux", "arm64", "15", "pass", "present", {"stage": "platform", "reason_code": "not-darwin", "action": "stop"}),
        ("Darwin", "x86_64", "15", "pass", "present", {"stage": "platform", "reason_code": "not-arm64", "action": "stop"}),
        ("Darwin", "arm64", "14", "pass", "present", {"stage": "platform", "reason_code": "unsupported-macos-major", "action": "stop"}),
        ("Darwin", "arm64", "15", "fail", "present", {"stage": "integrity", "reason_code": "critical-file-hash", "action": "stop"}),
        ("Darwin", "arm64", "15", "pass", "refused", {"stage": "clt", "reason_code": "clt-refused", "action": "stop"}),
        ("Darwin", "arm64", "26", "pass", "timeout", {"stage": "clt", "reason_code": "clt-timeout", "action": "stop"}),
        ("Darwin", "arm64", "26", "pass", "present", {"stage": "ready", "reason_code": "ok", "action": "continue"}),
    ],
)
def test_prerequisite_plan_is_fail_closed_before_install(
    tmp_path: Path,
    os_name: str,
    machine: str,
    major: str,
    critical: str,
    clt: str,
    expected: dict[str, str],
) -> None:
    data = _bash_json(
        tmp_path,
        "hve_prerequisite_plan \"$1\" \"$2\" \"$3\" \"$4\" \"$5\"",
        args=[os_name, machine, major, critical, clt],
    )
    assert data == expected


@_bash_required
def test_clt_polling_uses_injected_clock_and_is_bounded(tmp_path: Path) -> None:
    data = _bash_json(
        tmp_path,
        "polls=0\nsleeps=0\n"
        "hve_clt_present() { polls=$((polls + 1)); return 1; }\n"
        "hve_sleep() { sleeps=$((sleeps + 1)); }\n"
        "hve_now() { printf '%s\\n' $((sleeps * 5)); }\n"
        "rc=0\nhve_wait_for_clt 10 || rc=$?\n"
        "printf '{\"rc\":%s,\"polls\":%s,\"sleeps\":%s}\\n' \"$rc\" \"$polls\" \"$sleeps\"",
    )
    assert data == {"rc": 3, "polls": 3, "sleeps": 2}


@_bash_required
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
def test_shell_state_plan_is_executable_and_fail_closed(
    tmp_path: Path, state: str, exit_code: int, expected_action: str
) -> None:
    data = _bash_json(
        tmp_path,
        f"hve_resolve_action {shlex_quote(state)} {exit_code}",
    )
    assert data == {"state": state, "verifier_exit": exit_code, "action": expected_action}


@_bash_required
def test_shell_state_plan_rejects_mismatch(tmp_path: Path) -> None:
    completed = _bash_run(
        tmp_path,
        "printf 'HVE_SOURCE_OK\\n' >&2\n"
        "hve_resolve_action ready 10\n",
    )
    assert completed.returncode != 0
    assert "HVE_SOURCE_OK" in completed.stderr
    assert "state-exit-mismatch" in completed.stderr


@_bash_required
def test_shell_argv_round_trip_uses_actual_special_root_argument(tmp_path: Path) -> None:
    root = tmp_path / "space 日本語 quote' bang!"
    root.mkdir()
    data = _bash_json(
        tmp_path,
        "root=$1\n"
        "printf '{\"setup\":['\n"
        "hve_setup_argv \"$root\" | hve_json_string_lines\n"
        "printf '],\"verifier\":['\n"
        "hve_verifier_argv \"$root\" | hve_json_string_lines\n"
        "printf '],\"gui\":['\n"
        "hve_gui_argv \"$root\" | hve_json_string_lines\n"
        "printf ']}\\n'",
        args=[_posix(root)],
    )
    assert data["setup"] == [_posix(root / "hve" / "setup-hve.sh"), "--yes", "--no-global-cleanup"]
    assert data["verifier"] == [
        _posix(root / ".venv" / "bin" / "python"),
        "-I",
        "-m",
        "hve.bootstrap_verify",
        "--root",
        _posix(root),
        "--json",
    ]
    assert data["gui"] == [_posix(root / "hve.sh"), "gui"]
    assert "--force" not in data["setup"]


@_bash_required
def test_rendered_launcher_resolves_special_physical_root_from_unrelated_cwd(
    tmp_path: Path,
) -> None:
    scoped = tmp_path / "space 日本語 quote' bang!"
    scoped.mkdir()
    command = _render_command(scoped, critical_list=b"")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    completed = subprocess.run(
        [
            str(_BASH),
            "--noprofile", "--norc", "-p",
            "-c",
            'source "$1"; hve_distribution_root "$1"',
            "bash",
            _posix(command),
        ],
        cwd=str(unrelated),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == _posix(command.parent)


@_bash_required
def test_main_rejects_non_darwin_before_integrity_clt_homebrew_or_setup(
    tmp_path: Path,
) -> None:
    data = _bash_json(
        tmp_path,
        "event_file=$1\nevents=()\n"
        "hve_platform_facts() { printf 'platform\\n' >> \"$event_file\"; printf 'Linux\\narm64\\n15\\n'; }\n"
        "hve_verify_critical_payload() { events+=(integrity); return 0; }\n"
        "hve_prepare_clt() { events+=(clt); return 0; }\n"
        "hve_prepare_homebrew() { events+=(homebrew); return 0; }\n"
        "hve_initial_verification() { events+=(verifier); HVE_INITIAL_STATE=ready; HVE_INITIAL_EXIT=0; }\n"
        "hve_bootstrap_sequence() { events+=(sequence); return 0; }\n"
        "rc=0\nhve_main /Dist || rc=$?\n"
        "while IFS= read -r event; do events+=(\"$event\"); done < \"$event_file\"\n"
        "printf '{\"rc\":%s,\"stage\":\"%s\",\"reason\":\"%s\",\"events\":[\"%s\"]}\\n' "
        '"$rc" "$HVE_FAILURE_STAGE" "$HVE_FAILURE_REASON" "$(IFS='"'"','"'"'; echo "${events[*]}")"',
        args=[_posix(tmp_path / "events.log")],
    )
    assert data == {
        "rc": 2,
        "stage": "platform",
        "reason": "not-darwin",
        "events": ["platform"],
    }


@_bash_required
def test_shell_sequence_records_setup_verifier_gui_once(tmp_path: Path) -> None:
    data = _bash_json(
        tmp_path,
        "events=()\n"
        "hve_run_process() { local stage=$1; shift; events+=(\"$stage\"); return 0; }\n"
        "rc=0\n"
        "hve_bootstrap_sequence /Dist needs_setup 10 || rc=$?\n"
        "printf '{\"rc\":%s,\"events\":[' \"$rc\"\n"
        "printf '%s\\n' \"${events[@]}\" | hve_json_string_lines\n"
        "printf ']}\\n'",
    )
    assert data == {"rc": 0, "events": ["setup", "gui"]}


@_bash_required
@pytest.mark.parametrize(
    ("failed_stage", "child_exit", "expected_events"),
    [
        ("setup", 31, ["setup"]),
        ("gui", 41, ["setup", "gui"]),
    ],
)
def test_shell_sequence_stops_and_propagates_child_exit(
    tmp_path: Path,
    failed_stage: str,
    child_exit: int,
    expected_events: list[str],
) -> None:
    data = _bash_json(
        tmp_path,
        "failed_stage=$1\nfailed_exit=$2\nevents=()\n"
        "hve_run_process() { local stage=$1; shift; events+=(\"$stage\"); "
        "if [ \"$stage\" = \"$failed_stage\" ]; then return \"$failed_exit\"; fi; "
        "return 0; }\n"
        "rc=0\nhve_bootstrap_sequence /Dist needs_setup 10 || rc=$?\n"
        "printf '{\"rc\":%s,\"stage\":\"%s\",\"reason\":\"%s\",\"events\":[' "
        '"$rc" "$HVE_FAILURE_STAGE" "$HVE_FAILURE_REASON"\n'
        "printf '%s\\n' \"${events[@]}\" | hve_json_string_lines\n"
        "printf ']}\\n'",
        args=[failed_stage, str(child_exit)],
    )
    assert data == {
        "rc": child_exit,
        "stage": failed_stage,
        "reason": f"child-exit-{child_exit}",
        "events": expected_events,
    }


@_bash_required
def test_shell_fast_version_and_blocked_paths(tmp_path: Path) -> None:
    data = _bash_json(
        tmp_path,
        "hve_run_process() { events+=(\"$1\"); HVE_PROCESS_STATE=ready; return 0; }\n"
        "events=(); ready_rc=0; hve_bootstrap_sequence /Dist ready 0 || ready_rc=$?; "
        "ready_event=${events[0]-}\n"
        "events=(); version_rc=0; hve_bootstrap_sequence /Dist needs_version_decision 11 || version_rc=$?; "
        "version_event=${events[0]-}\n"
        "events=(); blocked_rc=0; hve_bootstrap_sequence /Dist blocked 12 || blocked_rc=$?; "
        "blocked_count=${#events[@]}\n"
        "printf '{\"ready\":{\"rc\":%s,\"event\":\"%s\"},"
        "\"needs_version_decision\":{\"rc\":%s,\"event\":\"%s\"},"
        "\"blocked\":{\"rc\":%s,\"event_count\":%s}}\\n' "
        '"$ready_rc" "$ready_event" "$version_rc" "$version_event" "$blocked_rc" "$blocked_count"',
    )
    assert data == {
        "ready": {"rc": 0, "event": "gui"},
        "needs_version_decision": {"rc": 0, "event": "version-entrypoint"},
        "blocked": {"rc": 12, "event_count": 0},
    }


def test_command_lock_is_atomic_and_stale_owner_is_rechecked() -> None:
    text = _read(_COMMAND)
    assert "bootstrap.lock" in text
    assert "mkdir \"$LOCK_DIR\"" in text
    assert "kill -0" in text
    assert "lock-owner-live" in text
    assert "lock-owner-unverifiable" in text
    assert "lock-owner-stale" in text
    assert "LOCK_OWNER_SNAPSHOT" in text
    assert "lock-owner-changed" in text
    assert "COMMAND_LINE" not in text
    assert "TOKEN" not in text


@_bash_required
@pytest.mark.parametrize(
    ("pid_state", "replace_owner", "expected_reason", "lock_remains"),
    [
        ("live", "no", "lock-owner-live", True),
        ("unverifiable", "no", "lock-owner-unverifiable", True),
        ("dead", "yes", "lock-owner-changed", True),
        ("dead", "no", "ok", False),
    ],
)
def test_lock_live_unverifiable_and_stale_race(
    tmp_path: Path,
    pid_state: str,
    replace_owner: str,
    expected_reason: str,
    lock_remains: bool,
) -> None:
    lock_root = tmp_path / "distribution"
    lock_root.mkdir()
    lock_dir = lock_root / ".hve-bootstrap" / "bootstrap.lock"
    lock_dir.mkdir(parents=True)
    owner = "PID=999999\nSTARTED_UTC=2026-09-06T00:00:00Z\n"
    (lock_dir / "owner.txt").write_text(owner, encoding="ascii", newline="\n")
    data = _bash_json(
        tmp_path,
        "root=$1\nstate=$2\nreplace=$3\n"
        "hve_pid_state() { printf '%s\\n' \"$state\"; }\n"
        "hve_before_stale_remove() { if [ \"$replace\" = yes ]; then "
        "printf 'PID=1\\nSTARTED_UTC=changed\\n' > \"$root/.hve-bootstrap/bootstrap.lock/owner.txt\"; fi; }\n"
        "rc=0\nreason=ok\nhve_acquire_lock \"$root\" || { rc=$?; reason=$HVE_LOCK_REASON; }\n"
        "if [ \"$rc\" -eq 0 ]; then hve_release_lock \"$root\"; fi\n"
        "remaining=false\n[ -d \"$root/.hve-bootstrap/bootstrap.lock\" ] && remaining=true\n"
        "printf '{\"rc\":%s,\"reason\":\"%s\",\"lock_remains\":%s}\\n' \"$rc\" \"$reason\" \"$remaining\"",
        args=[_posix(lock_root), pid_state, replace_owner],
    )
    assert data["reason"] == expected_reason
    assert data["lock_remains"] is lock_remains
    if expected_reason == "ok":
        assert data["rc"] == 0
    else:
        assert data["rc"] != 0


def test_setup_verifier_gui_helpers_are_defined_and_consumed() -> None:
    text = _read(_COMMAND)
    main = text.split("hve_main()", 1)[1]
    for helper in (
        "hve_platform_facts",
        "hve_prerequisite_plan",
        "hve_acquire_lock",
        "hve_verify_critical_payload",
        "hve_initial_verification",
        "hve_bootstrap_sequence",
    ):
        assert helper in main


def test_command_has_no_auth_cloud_azure_or_protection_bypass() -> None:
    executable = "\n".join(
        line for line in _read(_COMMAND).lower().splitlines() if not line.lstrip().startswith("#")
    )
    for forbidden in (
        "gh auth login",
        "copilot login",
        "az login",
        "hve orchestrate",
        "git init",
        "git pull",
        "git fetch",
        "gh issue",
        "gh pr",
        "gh release",
        "xattr -d",
        "xattr -c",
        "spctl --master-disable",
        "tccutil reset",
        "defaults write com.apple.launchservices",
    ):
        assert forbidden not in executable
