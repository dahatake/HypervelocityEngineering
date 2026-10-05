"""FR-LOCAL-SURFACE-04: executable macOS launcher boundaries, without installers."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from hve.tests import test_bootstrap_macos as mac


pytestmark = mac._bash_required


@pytest.mark.parametrize(
    ("state", "code", "events"),
    [
        ("ready", 0, ["integrity", "verifier", "gui"]),
        ("needs_setup", 10, ["integrity", "verifier", "homebrew", "setup", "gui"]),
        ("needs_version_decision", 11, ["integrity", "verifier", "version-entrypoint"]),
        ("blocked", 12, ["integrity", "verifier"]),
    ],
)
def test_main_routes_once_and_preserves_user_files(
    tmp_path: Path, state: str, code: int, events: list[str],
) -> None:
    root = tmp_path / "space 日本語 quote' bang!"
    root.mkdir()
    for name in ("hve/.settings.txt", "docs/user.md", "knowledge/user.md", "qa/user.md", "src/user.py"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"user-owned sentinel\n")
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    run = mac._bash_run(
        tmp_path,
        "root=$1; state=$2; code=$3; events=()\n"
        "hve_platform_facts() { printf 'Darwin\\narm64\\n26.0\\n'; }\n"
        "hve_verify_critical_payload() { events+=(integrity); }\n"
        "hve_initial_verification() { events+=(verifier); HVE_INITIAL_STATE=$state; HVE_INITIAL_EXIT=$code; }\n"
        "hve_prepare_homebrew() { events+=(homebrew); }\n"
        "hve_run_process() { events+=(\"$1\"); }\n"
        "rc=0; hve_main \"$root\" || rc=$?\n"
        "printf '%s\\n' \"rc=$rc\" \"${events[@]}\"",
        args=[mac._posix(root), state, str(code)],
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.splitlines() == [f"rc={code if state == 'blocked' else 0}", *events]
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert after == before
    assert not (root / ".hve-bootstrap/bootstrap.lock").exists()


def test_native_integrity_failure_precedes_lock_and_python(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    root.mkdir()
    run = mac._bash_run(
        tmp_path,
        "hve_platform_facts() { printf 'Darwin\\narm64\\n15.6\\n'; }\n"
        "hve_verify_critical_payload() { hve_fail integrity critical-file-hash 3; }\n"
        "hve_initial_verification() { printf 'UNSAFE\\n'; }\n"
        "rc=0; hve_main \"$1\" || rc=$?; printf '%s\\n' \"$rc\"",
        args=[mac._posix(root)],
    )
    assert run.returncode == 0
    assert run.stdout.strip() == "3"
    assert not (root / ".hve-bootstrap").exists()


@pytest.mark.parametrize("tamper", ["none", "list", "file", "traversal", "empty"])
def test_native_hash_checks_real_bytes_before_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str,
) -> None:
    contents = b"printf 'must not execute'\n"
    name = "../outside" if tamper == "traversal" else "hve/setup-hve.sh"
    critical = b"" if tamper == "empty" else f"{hashlib.sha256(contents).hexdigest()}  {name}\n".encode()
    command = mac._render_command(tmp_path, critical_list=critical)
    root = command.parent
    file = root / "hve/setup-hve.sh"
    file.parent.mkdir()
    file.write_bytes(contents + (b"changed" if tamper == "file" else b""))
    if tamper == "list":
        (root / "hve-bootstrap-critical.sha256").write_bytes(critical + b"\n")
    monkeypatch.setattr(mac, "_COMMAND", command)
    run = mac._bash_run(
        tmp_path,
        'rc=0; hve_verify_critical_payload "$1" || rc=$?; printf "%s\\n" "$rc"',
        args=[mac._posix(root)],
    )
    assert run.returncode == 0, run.stderr
    assert (run.stdout.strip() == "0") is (tamper == "none")
    if tamper == "list":
        assert "critical-list-hash" in run.stderr
    elif tamper != "none":
        assert "critical-file-hash" in run.stderr


@pytest.mark.parametrize("bad_owner", ["", "garbage\n", "PID=0\nSTARTED_UTC=2026-09-06T00:00:00Z\n", "PID=99\nSTARTED_UTC=invalid\n"])
def test_lock_invalid_owner_is_not_removed(tmp_path: Path, bad_owner: str) -> None:
    root = tmp_path / "distribution"
    lock = root / ".hve-bootstrap/bootstrap.lock"
    lock.mkdir(parents=True)
    owner = lock / "owner.txt"
    owner.write_text(bad_owner, encoding="ascii")
    run = mac._bash_run(
        tmp_path,
        'hve_pid_state() { printf "dead\\n"; }; rc=0; hve_acquire_lock "$1" || rc=$?; '
        'printf "%s:%s\\n" "$rc" "$HVE_LOCK_REASON"',
        args=[mac._posix(root)],
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip().endswith(":lock-owner-unverifiable")
    assert not run.stdout.startswith("0:")
    assert owner.read_text(encoding="ascii") == bad_owner


def test_release_never_deletes_replacement_owner(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    root.mkdir()
    run = mac._bash_run(
        tmp_path,
        'root=$1; hve_acquire_lock "$root"; '
        'printf "PID=1\\nSTARTED_UTC=2026-09-06T00:00:00Z\\n" > "$root/.hve-bootstrap/bootstrap.lock/owner.txt"\n'
        'rc=0; hve_release_lock "$root" || rc=$?; printf "%s\\n" "$rc"',
        args=[mac._posix(root)],
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() != "0"
    assert (root / ".hve-bootstrap/bootstrap.lock/owner.txt").read_text().startswith("PID=1\n")


def test_existing_live_owner_blocks_second_invocation(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    root.mkdir()
    run = mac._bash_run(
        tmp_path,
        'root=$1; hve_acquire_lock "$root"\n'
        '( rc=0; hve_acquire_lock "$root" || rc=$?; printf "%s:%s\\n" "$rc" "$HVE_LOCK_REASON" )\n'
        'hve_release_lock "$root"',
        args=[mac._posix(root)],
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip().endswith(":lock-owner-live")
    assert not run.stdout.startswith("0:")
    assert not (root / ".hve-bootstrap/bootstrap.lock").exists()


def test_lock_does_not_follow_symlink_parent(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / ".hve-bootstrap").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host does not permit directory symlinks")
    run = mac._bash_run(tmp_path, 'hve_acquire_lock "$1"', args=[mac._posix(root)])
    assert run.returncode != 0
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("present,install_exit,wait_exit,expected", [(True, 0, 0, "0:0:0"), (False, 0, 0, "0:1:1"), (False, 1, 0, "3:1:0"), (False, 0, 3, "3:1:1")])
def test_clt_request_is_single_and_wait_is_not_hidden(
    tmp_path: Path, present: bool, install_exit: int, wait_exit: int, expected: str,
) -> None:
    run = mac._bash_run(
        tmp_path,
        f"installs=0; waits=0\nhve_clt_present() {{ return {0 if present else 1}; }}\n"
        f"/usr/bin/xcode-select() {{ [[ \"$1\" == --install ]] || return 98; installs=$((installs+1)); return {install_exit}; }}\n"
        f"hve_wait_for_clt() {{ waits=$((waits+1)); return {wait_exit}; }}\n"
        'rc=0; hve_prepare_clt || rc=$?; printf "%s:%s:%s\\n" "$rc" "$installs" "$waits"',
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == expected


def test_clock_rollback_still_has_a_finite_poll_budget(tmp_path: Path) -> None:
    data = mac._bash_json(
        tmp_path,
        "sleeps=0; hve_clt_present() { return 1; }; hve_now() { printf '0\\n'; }; "
        "hve_sleep() { sleeps=$((sleeps+1)); }; rc=0; hve_wait_for_clt 10 || rc=$?; "
        "printf '{\"rc\":%s,\"sleeps\":%s}\\n' \"$rc\" \"$sleeps\"",
    )
    assert data == {"rc": 3, "sleeps": 2}


def test_initial_missing_python_never_runs_a_process(tmp_path: Path) -> None:
    data = mac._bash_json(
        tmp_path,
        'hve_initial_verification "$1"; '
        "printf '{\"state\":\"%s\",\"exit\":%s}\\n' \"$HVE_INITIAL_STATE\" \"$HVE_INITIAL_EXIT\"",
        args=[mac._posix(tmp_path)],
    )
    assert data == {"state": "needs_setup", "exit": 10}


def test_process_environment_is_sanitized_without_persisting(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update({"PYTHONPATH": "hostile", "PYTHONHOME": "hostile", "PERL5OPT": "hostile", "NODE_OPTIONS": "hostile", "PIP_TARGET": "hostile", "BASH_ENV": "hostile"})
    run = mac._bash_run(
        tmp_path,
        'hve_sanitize_environment; printf "%s:%s:%s:%s:%s:%s:%s\\n" '
        '"${PYTHONPATH-unset}" "${PYTHONHOME-unset}" "${PERL5OPT-unset}" '
        '"${NODE_OPTIONS-unset}" "${PIP_TARGET-unset}" "${BASH_ENV-unset}" "$PYTHONNOUSERSITE"',
        env=env,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "unset:unset:unset:unset:unset:unset:1"


def test_command_extension_attributes_are_lf() -> None:
    text = (mac._ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.command text eol=lf" in text
    assert "*.command.in text eol=lf" in text


@pytest.mark.parametrize(
    "kind,expected_exit,expected_events",
    [
        ("ok", 0, ["clt", "sudo", "download", "installer", "shellenv"]),
        ("existing", 0, ["shellenv", "clt"]),
        ("sudo-refused", 3, ["clt", "sudo"]),
        ("download-failed", 3, ["clt", "sudo", "download"]),
        ("wrong-host", 3, ["clt", "sudo", "download"]),
        ("http", 3, ["clt", "sudo", "download"]),
        ("empty", 3, ["clt", "sudo", "download"]),
        ("wrong-hash", 3, ["clt", "sudo", "download"]),
        ("installer-failed", 37, ["clt", "sudo", "download", "installer"]),
        ("still-missing", 3, ["clt", "sudo", "download", "installer"]),
    ],
)
def test_homebrew_pinned_download_and_cleanup_use_real_control_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    kind: str, expected_exit: int, expected_events: list[str],
) -> None:
    command = mac._render_command(tmp_path, critical_list=b"")
    text = command.read_text(encoding="utf-8").replace(
        mac._HOMEBREW_SHA256, hashlib.sha256(b"fake-installer\n").hexdigest(),
    )
    command.write_text(text, encoding="utf-8", newline="\n")
    monkeypatch.setattr(mac, "_COMMAND", command)
    events = tmp_path / "events.log"
    curl_args = tmp_path / "curl-args.log"
    run = mac._bash_run(
        tmp_path,
        'root=$1; fake_kind=$2; event_file=$3; curl_args=$4; fake_brew_ready=false\n'
        'hve_exec() { if [[ "$1" == NONINTERACTIVE=1 ]]; then shift; NONINTERACTIVE=1 "$@"; else "$@"; fi; }\n'
        '[[ "$fake_kind" != existing ]] || fake_brew_ready=true\n'
        'hve_homebrew_present() { [[ "$fake_brew_ready" == true ]]; }\n'
        'hve_prepare_clt() { printf "clt\\n" >> "$event_file"; }\n'
        'hve_apply_homebrew_shellenv() { printf "shellenv\\n" >> "$event_file"; }\n'
        '/usr/bin/sudo() { [[ "$*" == -v ]] || return 98; printf "sudo\\n" >> "$event_file"; [[ "$fake_kind" != sudo-refused ]]; }\n'
        '/usr/bin/curl() {\n'
        '  printf "download\\n" >> "$event_file"; printf "%s\\n" "$@" > "$curl_args"\n'
        '  local out=""; while [[ $# -gt 0 ]]; do if [[ "$1" == --output ]]; then out=$2; shift 2; else shift; fi; done\n'
        '  [[ -n "$out" ]] || return 98\n'
        '  case "$fake_kind" in empty) : > "$out" ;; wrong-hash) printf "bad" > "$out" ;; *) printf "fake-installer\\n" > "$out" ;; esac\n'
        '  case "$fake_kind" in wrong-host) printf "https://not-approved.invalid/install.sh" ;; http) printf "http://raw.githubusercontent.com/install.sh" ;; *) printf "https://raw.githubusercontent.com/Homebrew/install/pinned/install.sh" ;; esac\n'
        '  [[ "$fake_kind" != download-failed ]]\n'
        '}\n'
        '/bin/bash() {\n'
        '  [[ "${NONINTERACTIVE:-}" == 1 && "$#" -eq 1 && -s "$1" ]] || return 98\n'
        '  printf "installer\\n" >> "$event_file"\n'
        '  [[ "$fake_kind" != installer-failed ]] || return 37\n'
        '  [[ "$fake_kind" == still-missing ]] || fake_brew_ready=true\n'
        '}\n'
        'hve_acquire_lock "$root"\n'
        'rc=0; hve_prepare_homebrew "$root" || rc=$?\n'
        'hve_cleanup; printf "%s\\n" "$rc"',
        args=[mac._posix(command.parent), kind, mac._posix(events), mac._posix(curl_args)],
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == str(expected_exit)
    assert events.read_text(encoding="utf-8").splitlines() == expected_events
    if curl_args.exists():
        argv = curl_args.read_text(encoding="utf-8").splitlines()
        assert argv[0] == "-q"
        assert argv[argv.index("--proto") + 1] == "=https"
        assert argv[argv.index("--proto-redir") + 1] == "=https"
        assert "--max-time" in argv and "--max-redirs" in argv
        assert argv[-1] == json.loads(mac._read(mac._SOURCES))["homebrew"]["install_url"]
    assert list((command.parent / ".hve-bootstrap").iterdir()) == []


@pytest.mark.parametrize("shellenv_exit", [0, 19])
def test_absolute_brew_shellenv_is_process_only_and_failure_is_checked(
    tmp_path: Path, shellenv_exit: int,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    profile = home / ".zprofile"
    profile.write_bytes(b"user profile sentinel\n")
    run = mac._bash_run(
        tmp_path,
        'hve_exec() { "$@"; }\n'
        '/opt/homebrew/bin/brew() { [[ "$*" == shellenv ]] || return 98; '
        f"printf 'export T15_SHELLENV_APPLIED=yes\\n'; return {shellenv_exit}; }}\n"
        'command() { if [[ "$*" == "-v brew" ]]; then printf "/opt/homebrew/bin/brew\\n"; else builtin command "$@"; fi; }\n'
        'rc=0; hve_apply_homebrew_shellenv || rc=$?; printf "%s:%s\\n" "$rc" "${T15_SHELLENV_APPLIED-unset}"',
        env={**os.environ, "HOME": mac._posix(home)},
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == ("0:yes" if shellenv_exit == 0 else "3:unset")
    assert profile.read_bytes() == b"user profile sentinel\n"
    assert list(home.iterdir()) == [profile]


def test_cleanup_never_trusts_inherited_ownership(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    outside = tmp_path / "not-owned"
    root.mkdir()
    outside.mkdir()
    installer = outside / "install.sh"
    installer.write_bytes(b"user-owned\n")
    run = mac._bash_run(
        tmp_path,
        'HVE_DOWNLOAD_ID=$(hve_lock_identity "$HVE_DOWNLOAD_DIR")\n'
        "hve_platform_facts() { printf 'Darwin\\narm64\\n15.6\\n'; }\n"
        "hve_verify_critical_payload() { :; }; hve_initial_verification() { HVE_INITIAL_STATE=ready; HVE_INITIAL_EXIT=0; }; hve_run_process() { :; }\n"
        'hve_main "$1"',
        args=[mac._posix(root)],
        env={**os.environ, "HVE_DOWNLOAD_DIR": mac._posix(outside), "HVE_LOCK_HELD": "true", "HVE_LOCK_ROOT": mac._posix(outside)},
    )
    assert run.returncode == 0, run.stderr
    assert installer.read_bytes() == b"user-owned\n"


def test_signal_releases_owned_lock(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    root.mkdir()
    run = mac._bash_run(
        tmp_path,
        "hve_platform_facts() { printf 'Darwin\\narm64\\n15.6\\n'; }\n"
        "hve_verify_critical_payload() { :; }; hve_initial_verification() { HVE_INITIAL_STATE=ready; HVE_INITIAL_EXIT=0; }\n"
        'hve_run_process() { kill -TERM "$$"; }; hve_main "$1"',
        args=[mac._posix(root)],
    )
    assert run.returncode == 143, run.stderr
    assert not (root / ".hve-bootstrap/bootstrap.lock").exists()


def test_stale_owner_changed_during_final_pid_probe_is_preserved(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    lock = root / ".hve-bootstrap/bootstrap.lock"
    lock.mkdir(parents=True)
    owner = lock / "owner.txt"
    owner.write_text("PID=999999\nSTARTED_UTC=2026-09-06T00:00:00Z\n", encoding="ascii", newline="\n")
    count = tmp_path / "probes"
    count.write_text("0\n", encoding="ascii", newline="\n")
    run = mac._bash_run(
        tmp_path,
        'root=$1; counter=$2\n'
        'hve_pid_state() { local n; read -r n < "$counter"; n=$((n+1)); printf "%s\\n" "$n" > "$counter"; '
        'if [[ "$n" -eq 2 ]]; then printf "PID=1\\nSTARTED_UTC=2026-09-06T00:00:00Z\\n" > "$root/.hve-bootstrap/bootstrap.lock/owner.txt"; fi; printf "dead\\n"; }\n'
        'rc=0; hve_acquire_lock "$root" || rc=$?; printf "%s:%s\\n" "$rc" "$HVE_LOCK_REASON"',
        args=[mac._posix(root), mac._posix(count)],
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "1:lock-owner-changed"
    assert owner.read_text().startswith("PID=1\n")


@pytest.mark.parametrize(
    "case,reported_exit,expected_state",
    [
        ("ready", 0, "ready"),
        ("needs_setup", 10, "needs_setup"),
        ("needs_version_decision", 11, "needs_version_decision"),
        ("blocked", 12, "blocked"),
        ("schema_error", 2, "blocked"),
        ("ready", 10, None),
        ("unknown_key", 0, None),
        ("unknown_reason", 0, None),
        ("duplicate_key", 0, None),
        ("missing_check", 0, None),
        ("fake_ready", 0, None),
        ("non_json", 0, None),
        ("old_python", 0, None),
        ("other_python", 0, None),
        ("other_prefix", 0, None),
        ("other_source", 0, None),
    ],
)
def test_actual_embedded_json_validator_reuses_t13_closed_schema(
    tmp_path: Path, case: str, reported_exit: int, expected_state: str | None,
) -> None:
    from hve import bootstrap_verify

    payload = {
        "schema_version": 1,
        "state": "ready",
        "checks": [{"check_id": check_id, "passed": True, "reason_code": "ok"} for check_id, _ in bootstrap_verify.CHECK_FUNCTIONS],
    }
    changes = {
        "needs_setup": ("pip-check", "pip-check-failed", "needs_setup"),
        "needs_version_decision": ("hve-version", "version-mismatch", "needs_version_decision"),
        "blocked": ("manifest", "manifest-hash-mismatch", "blocked"),
        "schema_error": ("manifest", "manifest-invalid-schema", "blocked"),
        "fake_ready": ("pip-check", "pip-check-failed", "ready"),
    }
    if case in changes:
        check_id, reason, state = changes[case]
        payload["state"] = state
        for check in payload["checks"]:
            if check["check_id"] == check_id:
                check.update(passed=False, reason_code=reason)
    if case == "unknown_key":
        payload["extra"] = True
    if case == "unknown_reason":
        payload["checks"][0]["reason_code"] = "untrusted reason"
    if case == "missing_check":
        payload["checks"].pop()
    raw = json.dumps(payload)
    if case == "duplicate_key":
        raw = raw.replace('"state": "ready"', '"state": "blocked", "state": "ready"')
    if case == "non_json":
        raw = "not json"
    root = tmp_path / "space 日本語 quote' bang!"
    (root / "hve").mkdir(parents=True)
    (root / ".venv").mkdir()
    (root / "hve/bootstrap_verify.py").write_bytes(b"fixture origin\n")
    driver = tmp_path / "validator-driver.py"
    driver.write_text(
        "import pathlib,re,sys\n"
        "from hve import bootstrap_verify as verifier\n"
        "template,root,code,case = sys.argv[1:]\n"
        "source=pathlib.Path(template).read_text(encoding='utf-8')\n"
        "snippet=re.search(r\"-I -c '\\n(.*?)\\n' \\\"\\$1\\\" \\\"\\$2\\\"\", source, re.S).group(1)\n"
        "root=pathlib.Path(root)\n"
        "if case != 'other_source': verifier.__file__=str(root/'hve/bootstrap_verify.py')\n"
        "sys.executable=str(root/('.venv/bin/other' if case=='other_python' else '.venv/bin/python'))\n"
        "sys.prefix=str(root/('other' if case=='other_prefix' else '.venv'))\n"
        "sys.platform='darwin'\n"
        "if case=='old_python': sys.version_info=(3,10,0)\n"
        "sys.argv=['-c',str(root),code]\n"
        "exec(compile(snippet,'<launcher-json-validator>','exec'))\n",
        encoding="utf-8", newline="\n",
    )
    completed = subprocess.run(
        [sys.executable, "-I", str(driver), str(mac._COMMAND), str(root), str(reported_exit), case],
        input=raw, capture_output=True, text=True, encoding="utf-8", check=False, timeout=20,
    )
    assert completed.returncode == (0 if expected_state else 2), completed.stderr
    assert completed.stdout.strip() == (expected_state or "")


@pytest.mark.parametrize("state,code,wants_setup", [("ready", 0, False), ("needs_setup", 10, True), ("needs_version_decision", 11, False)])
def test_real_shell_process_argv_preserves_special_root(
    tmp_path: Path, state: str, code: int, wants_setup: bool,
) -> None:
    root = tmp_path / "space 日本語 quote' bang!"
    (root / "hve").mkdir(parents=True)
    setup = root / "hve/setup-hve.sh"
    gui = root / "hve.sh"
    setup_args = tmp_path / "setup-args"
    gui_args = tmp_path / "gui-args"
    setup.write_text('#!/bin/bash\nprintf "%s\\0" "$@" > ' + mac.shlex_quote(mac._posix(setup_args)) + '\n', encoding="utf-8", newline="\n")
    gui.write_text('#!/bin/bash\nprintf "%s\\0" "$@" > ' + mac.shlex_quote(mac._posix(gui_args)) + '\n', encoding="utf-8", newline="\n")
    run = mac._bash_run(
        tmp_path,
        '/bin/chmod +x "$1/hve/setup-hve.sh" "$1/hve.sh"\n'
        'hve_bootstrap_sequence "$1" "$2" "$3"',
        args=[mac._posix(root), state, str(code)],
    )
    assert run.returncode == 0, run.stderr
    assert setup_args.exists() is wants_setup
    if wants_setup:
        assert setup_args.read_bytes() == b"--yes\0--no-global-cleanup\0"
    assert gui_args.read_bytes() == b"gui\0"


@pytest.mark.parametrize("state,code", [("ready", 0), ("needs_setup", 10), ("needs_version_decision", 11), ("blocked", 12)])
def test_initial_verifier_executes_exact_isolated_argv_once(
    tmp_path: Path, state: str, code: int,
) -> None:
    root = tmp_path / "space 日本語 quote' bang!"
    python = root / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    args_file = tmp_path / "verifier-args"
    python.write_text(
        '#!/bin/bash\nprintf "%s\\0" "$@" >> ' + mac.shlex_quote(mac._posix(args_file)) + '\n'
        'printf "%s\\n" ' + mac.shlex_quote(json.dumps({"state": state})) + f'\nexit {code}\n',
        encoding="utf-8", newline="\n",
    )
    run = mac._bash_run(
        tmp_path,
        '/bin/chmod +x "$1/.venv/bin/python"\n'
        # The actual shared parser is covered above; this seam proves process
        # argv, once-only execution, stdout delivery and reported exit separately.
        'hve_validate_verifier_result() { [[ "$1" == "$HVE_TEST_ROOT" && "$2" == "$HVE_TEST_EXIT" ]] || return 98; '
        'local data; IFS= read -r data; [[ "$data" == "$HVE_TEST_PAYLOAD" ]] || return 98; printf "%s\\n" "$HVE_TEST_STATE"; }\n'
        'hve_initial_verification "$1"; printf "%s:%s\\n" "$HVE_INITIAL_STATE" "$HVE_INITIAL_EXIT"',
        args=[mac._posix(root)],
        env={**os.environ, "HVE_TEST_VERIFIER_ARGS": mac._posix(args_file), "HVE_TEST_EXIT": str(code), "HVE_TEST_STATE": state, "HVE_TEST_ROOT": mac._posix(root), "HVE_TEST_PAYLOAD": json.dumps({"state": state})},
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == f"{state}:{code}"
    assert args_file.read_bytes().decode("utf-8").split("\0") == ["-I", "-m", "hve.bootstrap_verify", "--root", mac._posix(root), "--json", ""]


def test_inherited_shell_function_cannot_reach_child_process(tmp_path: Path) -> None:
    run = mac._bash_run(
        tmp_path,
        'hve_sanitize_environment\n'
        "hve_run_process probe /bin/bash --noprofile --norc -c 'if declare -F hve_test_injected >/dev/null; then printf inherited; else printf absent; fi'",
        env={**os.environ, "BASH_FUNC_hve_test_injected%%": "() { printf injected; }"},
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout == "absent"