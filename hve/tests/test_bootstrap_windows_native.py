"""FR-LOCAL-SURFACE-04: offline native boundary tests, never clean-OS evidence."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from .test_bootstrap_windows import (
    _PS1, _PWSH, _ROOT, _RUNTIME_CHECK, _SOURCES, _WINGET_INSPECT,
    _pwsh_json, _read, _render_cmd, _run_cmd,
)

pytestmark = pytest.mark.skipif(os.name != "nt" or not _PWSH, reason="Windows with PowerShell 7+ required")

_CRITICAL = (
    "hve-bootstrap-manifest.json", "pyproject.toml", "hve/__init__.py",
    "hve/bootstrap_verify.py", "hve/startup_version.py", "hve/auth.py",
    "hve/gui/copilot_cli_bridge.py", "hve/gui/pty_backend.py",
    "hve/bootstrap/bootstrap-sources.json", "hve/setup-hve.ps1", "Start-HVE.ps1",
    "hve/bootstrap/windows-pwsh-runtime-check.ps1", "hve/bootstrap/winget-module-inspect.ps1",
)
_CHECK_IDS = (
    "platform", "manifest", "python", "hve-version", "source-imports", "pip-check",
    "gui-imports", "gh", "pty", "pwsh", "sdk-runtime", "external-copilot-cli",
)


def _payload(state: str) -> dict:
    checks = [{"check_id": name, "passed": True, "reason_code": "ok"} for name in _CHECK_IDS]
    failed = {
        "needs_setup": ("gui-imports", "gui-import-failed"),
        "needs_version_decision": ("hve-version", "version-mismatch"),
        "blocked": ("platform", "unsupported-windows-version"),
    }.get(state)
    if failed:
        check = next(item for item in checks if item["check_id"] == failed[0])
        check.update(passed=False, reason_code=failed[1])
    return {"schema_version": 1, "state": state, "checks": checks}


def _distribution(base: Path, payload: str, verifier_exit: int, entry_exit: int = 0) -> Path:
    """Install no packages: stub probes but use the real T13 payload validator."""
    base.mkdir(parents=True, exist_ok=True)
    root = base / "distribution"
    root.mkdir()
    for relative in _CRITICAL:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")
    (root / "hve/auth.py").write_text("def find_copilot_binary(): return None\n", encoding="utf-8")
    (root / "hve/startup_version.py").write_text(
        "def _parse_version(value): return None\ndef _read_source_version(root): return None\n",
        encoding="utf-8",
    )
    verifier = _read(_ROOT / "hve/bootstrap_verify.py")
    marker = 'if __name__ == "__main__":'
    assert verifier.count(marker) == 1
    # Override CLI probes only, not the schema validator consumed by the launcher.
    verifier = verifier.split(marker)[0] + '''
if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "fixture.json").read_text(encoding="utf-8"))
    with (root / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"stage": "verifier", "argv": sys.argv[1:], "isolated": sys.flags.isolated}) + "\\n")
    print(config["payload"])
    raise SystemExit(config["verifier_exit"])
'''
    (root / "hve/bootstrap_verify.py").write_text(verifier, encoding="utf-8")
    (root / "Start-HVE.ps1").write_bytes(_PS1.read_bytes())
    (root / "hve/bootstrap/bootstrap-sources.json").write_bytes(_SOURCES.read_bytes())
    for source in (_RUNTIME_CHECK, _WINGET_INSPECT):
        (root / "hve/bootstrap" / source.name).write_bytes(source.read_bytes())
    (root / "fixture.json").write_text(
        json.dumps({"payload": payload, "verifier_exit": verifier_exit, "entry_exit": entry_exit}), encoding="utf-8",
    )
    (root / "entry.py").write_text('''
import json, os, sys
from pathlib import Path
root = Path(__file__).resolve().parent
with (root / "events.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"stage": "entry", "argv": sys.argv[1:], "leaked": [name for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PIP_TARGET", "PIP_USER") if name in os.environ]}) + "\\n")
raise SystemExit(json.loads((root / "fixture.json").read_text(encoding="utf-8"))["entry_exit"])
''', encoding="utf-8")
    (root / "hve.cmd").write_bytes(
        b'@echo off\r\n"%~dp0.venv\\Scripts\\python.exe" -I "%~dp0entry.py" %*\r\nexit /b %ERRORLEVEL%\r\n'
    )
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(("PYTHON", "PIP_"))}
    create = subprocess.run(
        [sys.executable, "-I", "-B", "-m", "venv", "--without-pip", str(root / ".venv")],
        env=env, capture_output=True, text=True, check=False, timeout=30,
    )
    assert create.returncode == 0, create.stderr
    (root / ".venv/Lib/site-packages/distribution.pth").write_text(str(root) + "\n", encoding="utf-8")
    critical = "".join(
        f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}\r\n"
        for name in sorted(_CRITICAL)
    ).encode("ascii")
    return _render_cmd(base, critical_list=critical)


def _events(root: Path) -> list[dict]:
    path = root / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


@pytest.mark.parametrize("state,exit_code", [("ready", 0), ("needs_version_decision", 11)])
@pytest.mark.parametrize("name", ["plain", "space 日本語 quote' bang! percent%"])
def test_native_fast_and_version_paths(tmp_path: Path, state: str, exit_code: int, name: str) -> None:
    launcher = _distribution(tmp_path / name, json.dumps(_payload(state)), exit_code, entry_exit=41)
    root = launcher.parent
    sentinels = {}
    for relative in ("hve/.settings.txt", "docs/keep", "knowledge/keep", "qa/keep", "src/keep"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"user-owned sentinel\n")
        sentinels[path] = path.read_bytes()
    completed = _run_cmd(launcher, env_overrides={
        "PYTHONPATH": "fixture-leak", "PYTHONHOME": "fixture-leak", "PYTHONSTARTUP": "fixture-leak",
        "PIP_TARGET": "fixture-leak", "PIP_USER": "1",
    })
    assert completed.returncode == 41, (completed.stdout, completed.stderr)
    events = _events(root)
    assert [event["stage"] for event in events] == ["verifier", "entry"]
    assert events[0]["argv"] == ["--root", str(root), "--json"]
    assert events[0]["isolated"] == 1
    assert events[1]["argv"] == ["gui"]  # no Yes on the version path
    assert events[1]["leaked"] == []
    assert not (root / ".hve-bootstrap/bootstrap.lock").exists()
    assert {path: path.read_bytes() for path in sentinels} == sentinels


@pytest.mark.parametrize("payload,exit_code", [
    (json.dumps(_payload("blocked")), 12),
    (json.dumps(_payload("ready")), 10),
    ('{"state":"ready","state":"ready"}', 0),
    ("not-json", 0),
])
def test_native_payload_failures_never_launch(tmp_path: Path, payload: str, exit_code: int) -> None:
    launcher = _distribution(tmp_path, payload, exit_code)
    completed = _run_cmd(launcher)
    assert completed.returncode != 0
    assert [event["stage"] for event in _events(launcher.parent)] == ["verifier"]
    assert not (launcher.parent / ".hve-bootstrap/bootstrap.lock").exists()
    assert "BOOTSTRAP_READY" not in completed.stdout


@pytest.mark.parametrize("relative", ["hve-bootstrap-manifest.json", "pyproject.toml", "hve/bootstrap_verify.py", "Start-HVE.ps1", "hve/setup-hve.ps1", "hve/bootstrap/windows-pwsh-runtime-check.ps1"])
def test_native_hash_gate_precedes_every_interpreter(tmp_path: Path, relative: str) -> None:
    launcher = _distribution(tmp_path, json.dumps(_payload("ready")), 0)
    target = launcher.parent / relative
    target.write_bytes(target.read_bytes() + b"\nmodified\n")
    completed = _run_cmd(launcher)
    assert completed.returncode == 2, (completed.stdout, completed.stderr)
    assert "reason=critical-file-hash" in completed.stdout
    assert _events(launcher.parent) == []
    assert not (launcher.parent / ".hve-bootstrap/bootstrap.lock").exists()


@pytest.mark.parametrize("state,verifier_exit,expected", [
    ("ready", 0, 0), ("needs_setup", 10, 10), ("needs_version_decision", 11, 11),
    ("blocked", 12, 12), ("needs_setup", 0, 12),
    ("ready", 10, 12), ("ready", 11, 12), ("ready", 12, 12),
    ("malformed", 10, 12), ("malformed", 11, 12), ("malformed", 12, 12),
    ("duplicate", 10, 12), ("duplicate", 11, 12), ("duplicate", 12, 12),
])
def test_real_distribution_setup_block_owns_one_verifier(tmp_path: Path, state: str, verifier_exit: int, expected: int) -> None:
    payload = {"malformed": "not-json", "duplicate": '{"state":"ready","state":"blocked"}'}.get(state)
    launcher = _distribution(tmp_path, payload or json.dumps(_payload(state)), verifier_exit)
    setup = _read(_ROOT / "hve/setup-hve.ps1")
    block = setup.split("# ---------- 検証 ----------", 1)[1].split("# ---------- まとめ ----------", 1)[0]
    harness = tmp_path / "setup-final.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)\n"
        "$repoRoot=$args[0]; $venvPy=Join-Path $repoRoot '.venv\\Scripts\\python.exe'; $installGui=$true\n"
        "function Write-Step($Msg) {}; function Write-Ok($Msg) {}; function Write-ErrLine($Msg) { Write-Host $Msg }\n"
        "function Invoke-Probe { throw 'unexpected-legacy-audit' }\n" + block + "\nexit 0\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [str(_PWSH), "-NoLogo", "-NoProfile", "-File", str(harness), str(launcher.parent)],
        capture_output=True, text=True, encoding="utf-8", check=False, timeout=30,
    )
    assert completed.returncode == expected, (completed.stdout, completed.stderr)
    assert [event["stage"] for event in _events(launcher.parent)] == ["verifier"]


def test_process_adapter_preserves_argv_and_only_sanitizes_child(tmp_path: Path) -> None:
    child = tmp_path / "child.ps1"
    child.write_text(
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n"
        "[Console]::InputEncoding=[Text.UTF8Encoding]::new($false)\n"
        "@{argv=@($args);input=[Console]::In.ReadToEnd();python_path=$env:PYTHONPATH;pip_target=$env:PIP_TARGET} | ConvertTo-Json -Compress\n",
        encoding="utf-8",
    )
    argument = "space 日本語 quote' bang! % & (x)"
    data = _pwsh_json(tmp_path,
        "$env:PYTHONPATH='parent-only'; $env:PIP_TARGET='parent-only'\n"
        "$r=Invoke-HveBootstrapChild -Root $args[0] -Stage probe -Exe (Join-Path $PSHOME 'pwsh.exe') "
        "-ArgList @('-NoLogo','-NoProfile','-File',$args[1],$args[2]) -CaptureOutput -InputText $args[2] -TimeoutSeconds 15\n"
        "@{rc=$r.exit_code;child=($r.stdout | ConvertFrom-Json);parent=$env:PYTHONPATH} | ConvertTo-Json -Depth 5 -Compress",
        args=[str(tmp_path), str(child), argument],
    )
    assert data["rc"] == 0
    assert data["child"]["argv"] == [argument]
    assert data["child"]["input"] == argument
    assert not data["child"]["python_path"] and not data["child"]["pip_target"]
    assert data["parent"] == "parent-only"


def test_cmd_adapter_passes_special_root_without_code_interpolation(tmp_path: Path) -> None:
    root = tmp_path / "日本語 quote' bang! % & (x)"
    root.mkdir()
    entry = root / "hve.cmd"
    entry.write_bytes(b"@echo off\r\necho ARG=%~1\r\nexit /b 37\r\n")
    data = _pwsh_json(tmp_path,
        "$r=Invoke-HveBootstrapChild -Root $args[0] -Stage gui -Exe $args[1] -ArgList @('gui') -CaptureOutput\n"
        "$r | ConvertTo-Json -Compress", args=[str(root), str(entry)],
    )
    assert data["exit_code"] == 37
    assert data["stdout"].strip() == "ARG=gui"


@pytest.mark.parametrize("final_url,good_hash,reason", [
    ("https://release-assets.githubusercontent.com/file?sig=PRIVATE_FIXTURE", True, "ok"),
    ("https://github.com.evil.invalid/file?sig=PRIVATE_FIXTURE", True, "redirect-host"),
    ("http://github.com/file", True, "redirect-host"),
    ("https://github.com/file", False, "download-hash"),
])
def test_download_metadata_and_hash_are_checked_without_network(tmp_path: Path, final_url: str, good_hash: bool, reason: str) -> None:
    digest = hashlib.sha256(b"fixture").hexdigest() if good_hash else "0" * 64
    data = _pwsh_json(tmp_path,
        "$root=$args[0]; $final=$args[1]; $hash=$args[2]\n"
        "$runner={param($exe,$argv) $p=$argv[[Array]::IndexOf($argv,'--output')+1]; [IO.File]::WriteAllBytes($p,[Text.Encoding]::ASCII.GetBytes('fixture')); @{exit_code=0;stdout=$final}}\n"
        "try { Invoke-HvePinnedDownload -Root $root -Url 'https://github.com/fixed-release' -Sha256 $hash "
        "-AllowedHosts @('github.com','release-assets.githubusercontent.com') -Destination (Join-Path $root 'payload.zip') "
        "-ProcessRunner $runner; $reason='ok' } catch { $reason=$_.Exception.Message }\n"
        "@{reason=$reason} | ConvertTo-Json -Compress", args=[str(tmp_path), final_url, digest],
    )
    assert data == {"reason": reason}


def test_unverified_repair_blocks_before_download_or_child(tmp_path: Path) -> None:
    data = _pwsh_json(tmp_path,
        "function Invoke-HvePinnedDownload { throw 'unexpected-download' }\n"
        "function Invoke-HveBootstrapChild { throw 'unexpected-child' }\n"
        "$source=Get-Content -LiteralPath $args[1] -Raw | ConvertFrom-Json\n"
        "try { Repair-HveWinGet -Root $args[0] -Source $source.winget_client; $reason='unexpected-success' } "
        "catch { $reason=$_.Exception.Message }\n"
        "@{reason=$reason;created=(Test-Path -LiteralPath (Join-Path $args[0] '.hve-bootstrap'))} | ConvertTo-Json -Compress",
        args=[str(tmp_path), str(_SOURCES)],
    )
    assert data == {"reason": "winget-repair-not-live-verified", "created": False}


@pytest.mark.parametrize("version,with_latest,exit_code", [("1.29.280", True, 0), ("1.29.281", True, 3), ("1.29.280", False, 3)])
def test_companion_checks_actual_module_ownership_without_repair(tmp_path: Path, version: str, with_latest: bool, exit_code: int) -> None:
    module = tmp_path / "module 日本語 quote' bang!"
    module.mkdir()
    manifest = module / "Microsoft.WinGet.Client.psd1"
    manifest.write_text(
        "@{ RootModule='Microsoft.WinGet.Client.psm1'; ModuleVersion='1.29.280'; FunctionsToExport=@('Repair-WinGetPackageManager') }\n",
        encoding="utf-8",
    )
    parameters = "[switch]$Force, [switch]$Latest" if with_latest else "[switch]$Force"
    (module / "Microsoft.WinGet.Client.psm1").write_text(
        f"function Repair-WinGetPackageManager {{ param({parameters}) throw 'repair-must-not-run' }}\n"
        "Export-ModuleMember -Function Repair-WinGetPackageManager\n", encoding="utf-8",
    )
    completed = subprocess.run(
        [str(_PWSH), "-NoLogo", "-NoProfile", "-File", str(_WINGET_INSPECT),
         "-ManifestPath", str(manifest), "-ExpectedVersion", version, "-ExpectedModuleBase", str(module)],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
    )
    assert completed.returncode == exit_code, completed.stderr
    if exit_code == 0:
        data = json.loads(completed.stdout)
        assert data["status"] == "PASS" and data["module_version"] == "1.29.280"
        assert all(data[key] for key in ("module_base_match", "command_module_match", "command_version_match", "command_module_base_match"))
    else:
        assert not completed.stdout
        assert "reason=inspection-failed" in completed.stderr


@pytest.mark.parametrize("winget_state", ["missing", "broken"])
def test_windows_main_reports_unverified_repair_without_any_install(tmp_path: Path, winget_state: str) -> None:
    launcher = _distribution(tmp_path, json.dumps(_payload("ready")), 0)
    root = launcher.parent
    expected_hash = hashlib.sha256((root / "hve-bootstrap-critical.sha256").read_bytes()).hexdigest()
    env = os.environ.copy()
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    if winget_state == "broken":
        fake_bin = tmp_path / "broken-tool"
        fake_bin.mkdir()
        (fake_bin / "winget.exe").write_bytes(b"not an executable")
        env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
    completed = subprocess.run(
        [str(_PWSH), "-NoLogo", "-NoProfile", "-File", str(root / "Start-HVE.ps1"),
         "-Root", str(root), "-ExpectedCriticalListHash", expected_hash],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=30,
    )
    assert completed.returncode == 3, (completed.stdout, completed.stderr)
    assert "reason=winget-repair-not-live-verified" in completed.stderr
    assert _events(root) == []
    assert not (root / ".hve-bootstrap").exists()


@pytest.mark.parametrize("tamper", ["none", "child-junction", "parent-junction"])
def test_concurrent_launcher_and_cleanup_preserve_ownership(tmp_path: Path, tamper: str) -> None:
    launcher = _distribution(tmp_path, json.dumps(_payload("ready")), 0)
    root = launcher.parent
    entry = root / "entry.py"
    entry.write_text(
        entry.read_text(encoding="utf-8").replace(
            "raise SystemExit(", "print('ENTRY_READY', flush=True)\nsys.stdin.readline()\nraise SystemExit(", 1
        ), encoding="utf-8",
    )
    env = os.environ.copy()
    native = Path(os.environ["SystemRoot"]) / "System32"
    env["PATH"] = str(native)
    env["HVE_TEST_LAUNCHER"] = str(launcher)
    first = subprocess.Popen(
        f'"{native / "cmd.exe"}" /d /v:off /s /c ""%HVE_TEST_LAUNCHER%""',
        env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    outside = tmp_path / "user-owned"
    outside.mkdir()
    sentinel = outside / "keep"
    sentinel.write_bytes(b"do not delete")
    try:
        assert first.stdout is not None
        assert first.stdout.readline().strip() == "ENTRY_READY"
        lock = root / ".hve-bootstrap/bootstrap.lock"
        owner = (lock / "owner.txt").read_bytes()
        second = _run_cmd(launcher)
        assert second.returncode == 2
        assert "reason=lock-owner-live" in second.stdout
        assert (lock / "owner.txt").read_bytes() == owner
        assert [event["stage"] for event in _events(root)] == ["verifier", "entry"]
        if tamper == "child-junction":
            linked = subprocess.run(
                [str(native / "cmd.exe"), "/d", "/c", "mklink", "/J", str(lock / "junction"), str(outside)],
                capture_output=True, check=False, timeout=10,
            )
            assert linked.returncode == 0, linked.stderr
        elif tamper == "parent-junction":
            outside_lock = outside / "bootstrap.lock"
            outside_lock.mkdir()
            (outside_lock / "owner.txt").write_bytes(owner)
            os.rename(root / ".hve-bootstrap", root / "held-bootstrap")
            linked = subprocess.run(
                [str(native / "cmd.exe"), "/d", "/c", "mklink", "/J", str(root / ".hve-bootstrap"), str(outside)],
                capture_output=True, check=False, timeout=10,
            )
            assert linked.returncode == 0, linked.stderr
        stdout, stderr = first.communicate("continue\n", timeout=15)
        assert first.returncode == (0 if tamper == "none" else 3), (stdout, stderr)
        if tamper != "none":
            assert "reason=cleanup-failed" in stdout
            assert "BOOTSTRAP_READY" not in stdout
            if tamper == "child-junction":
                # Remove only the test junction, not its target, before pytest cleanup.
                os.rmdir(lock / "junction")
            else:
                assert (outside / "bootstrap.lock/owner.txt").read_bytes() == owner
                os.rmdir(root / ".hve-bootstrap")
                os.rename(root / "held-bootstrap", root / ".hve-bootstrap")
        else:
            assert "BOOTSTRAP_READY cleanup=true" in stdout
            assert not lock.exists()
        assert sentinel.read_bytes() == b"do not delete"
    finally:
        if first.poll() is None:
            first.communicate("continue\n", timeout=15)


@pytest.mark.parametrize("delimiter", [b" ", b"   ", b"\t", b"\r\n", b";comment\r\n"])
def test_native_critical_list_rejects_noncanonical_lines(tmp_path: Path, delimiter: bytes) -> None:
    launcher = _distribution(tmp_path, json.dumps(_payload("ready")), 0)
    data = (launcher.parent / "hve-bootstrap-critical.sha256").read_bytes()
    if delimiter.endswith(b"\r\n"):
        data = delimiter + data
    else:
        data = data.replace(b"  ", delimiter, 1)
    launcher = _render_cmd(tmp_path, critical_list=data)
    completed = _run_cmd(launcher)
    assert completed.returncode == 2, (completed.stdout, completed.stderr)
    assert "reason=critical-file-hash" in completed.stdout
    assert _events(launcher.parent) == []


def test_native_rejects_server_before_any_payload_or_network(tmp_path: Path) -> None:
    launcher = _render_cmd(tmp_path, critical_list=b"")
    source = launcher.read_text(encoding="utf-8")
    registry_line = next(line for line in source.splitlines() if "reg.exe query" in line)
    # Replace only the OS response boundary; keep the actual native OS gate.
    launcher.write_text(source.replace(registry_line, 'set "OS_INSTALLATION_TYPE=Server"'), encoding="utf-8", newline="\r\n")
    completed = _run_cmd(launcher)
    assert completed.returncode == 2
    assert "stage=platform" in completed.stdout
    assert not (launcher.parent / ".hve-bootstrap").exists()


def test_interruption_before_runtime_leaves_no_published_pending_lock(tmp_path: Path) -> None:
    launcher = _distribution(tmp_path, json.dumps(_payload("ready")), 0)
    root = launcher.parent
    critical = (root / "hve-bootstrap-critical.sha256").read_bytes()
    source = launcher.read_text(encoding="utf-8")
    assert source.count("\n:resolve_pwsh\n") == 1
    # Deterministic process interruption before any runtime/package-manager call.
    launcher.write_text(source.replace("\n:resolve_pwsh\n", "\n:resolve_pwsh\nexit /b 73\n"), encoding="utf-8", newline="\r\n")
    python = root / ".venv/Scripts/python.exe"
    original = python.read_bytes()
    python.unlink()
    stopped = _run_cmd(launcher)
    assert stopped.returncode == 73
    assert not (root / ".hve-bootstrap/bootstrap.lock").exists()
    abandoned = set((root / ".hve-bootstrap").iterdir())
    assert abandoned
    python.write_bytes(original)
    launcher = _render_cmd(tmp_path, critical_list=critical)
    restarted = _run_cmd(launcher)
    assert restarted.returncode == 0, (restarted.stdout, restarted.stderr)
    assert [event["stage"] for event in _events(root)] == ["verifier", "entry"]
    assert set((root / ".hve-bootstrap").iterdir()) == abandoned


def test_inherited_internal_cleanup_paths_cannot_delete_user_files(tmp_path: Path) -> None:
    launcher = _distribution(tmp_path, json.dumps(_payload("ready")), 0)
    outside = tmp_path / "keep-outside"
    outside.mkdir()
    sentinel = outside / "owner.txt"
    sentinel.write_bytes(b"user-owned file")
    completed = _run_cmd(launcher, env_overrides={
        "ZIP_PATH": str(sentinel), "PROBE_DIR": str(outside), "LOCK_STAGE": str(outside),
        "WORK_DIR": str(outside), "OWN_WORK": "1", "OWN_LOCK": "1",
        "INSTALL_STABLE_PWSH": "1", "WINGET_EXE": str(outside / "do-not-execute.exe"),
    })
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert sentinel.read_bytes() == b"user-owned file"
    assert [event["stage"] for event in _events(launcher.parent)] == ["verifier", "entry"]