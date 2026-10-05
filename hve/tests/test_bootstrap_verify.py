"""FR-LOCAL-SURFACE-04: private source ZIP の共通 readiness verifier。"""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import webbrowser
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hve import bootstrap_verify as bv


_REQUIRED_CHECK_IDS = (
    "platform",
    "manifest",
    "python",
    "hve-version",
    "source-imports",
    "pip-check",
    "gui-imports",
    "gh",
    "pty",
    "pwsh",
    "sdk-runtime",
    "external-copilot-cli",
)

_EXPECTED_CHECK_FUNCTIONS = (
    ("platform", "check_platform"),
    ("manifest", "check_manifest"),
    ("python", "check_current_python"),
    ("hve-version", "check_current_hve_version"),
    ("source-imports", "check_current_import_locations"),
    ("pip-check", "check_pip_consistency"),
    ("gui-imports", "check_gui_imports"),
    ("gh", "check_gh"),
    ("pty", "check_pty"),
    ("pwsh", "check_pwsh"),
    ("sdk-runtime", "check_current_sdk_runtime"),
    ("external-copilot-cli", "check_external_copilot_cli"),
)

_REQUIRED_SOURCE_FILES_BY_TARGET = {
    "windows-x64": (
        "hve.cmd",
        "hve/setup-hve.ps1",
        "hve/__init__.py",
        "hve/bootstrap_verify.py",
        "hve/startup_version.py",
        "hve/auth.py",
        "hve/gui/copilot_cli_bridge.py",
        "hve/gui/pty_backend.py",
        "hve/bootstrap/bootstrap-sources.json",
        "hve/bootstrap/windows-pwsh-runtime-check.ps1",
        "hve/bootstrap/winget-module-inspect.ps1",
        "mdq/__init__.py",
        "cq/__init__.py",
        "pyproject.toml",
    ),
    "macos-arm64": (
        "hve.sh",
        "hve/setup-hve.sh",
        "hve/__init__.py",
        "hve/bootstrap_verify.py",
        "hve/startup_version.py",
        "hve/auth.py",
        "hve/gui/copilot_cli_bridge.py",
        "hve/gui/pty_backend.py",
        "hve/bootstrap/bootstrap-sources.json",
        "mdq/__init__.py",
        "cq/__init__.py",
        "pyproject.toml",
    ),
}


def _write_manifest(root: Path, *, target_platform: str) -> Path:
    files: dict[str, str] = {}
    for relative in _REQUIRED_SOURCE_FILES_BY_TARGET[target_platform]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(
                b'[project]\nname="hve"\nversion="1.2.3"\n'
                if relative == "pyproject.toml"
                else b"source\n"
            )
        files[relative] = bv.sha256_file(path)
    manifest = {
        "schema_version": 1,
        "distribution_kind": "hve-private-source",
        "hve_version": "1.2.3",
        "source_commit": "a" * 40,
        "source_dirty": False,
        "target_platform": target_platform,
        "launcher": (
            "Start-HVE.cmd" if target_platform == "windows-x64" else "Start-HVE.command"
        ),
        "files": files,
    }
    path = root / "hve-bootstrap-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    (root / "hve-bootstrap-critical.sha256").write_text(
        "0" * 64 + "  pyproject.toml\n", encoding="ascii"
    )
    launcher = root / manifest["launcher"]
    launcher.write_bytes(b"launcher\n")
    if target_platform == "windows-x64":
        (root / "Start-HVE.ps1").write_bytes(b"launcher-stage\n")
    return path


def _test_probes(root: Path) -> SimpleNamespace:
    executable = root / ".venv" / "Scripts" / "python.exe"
    sdk_runtime = root / ".sdk" / "copilot.exe"
    module_files = {name: root / name / "__init__.py" for name in ("hve", "mdq", "cq")}
    for path in (executable, sdk_runtime, *module_files.values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return SimpleNamespace(
        platform_name="win32",
        os_product_version="11.0.26100",
        machine="AMD64",
        executable=executable,
        prefix=root / ".venv",
        version_info=(3, 11, 0),
        isolated=True,
        installed_version="1.2.3",
        module_files=module_files,
        command_runner=lambda _argv: SimpleNamespace(
            returncode=0, stdout="1.0.79\n", stderr=""
        ),
        which={"gh": "C:/bin/gh.exe", "copilot": "C:/bin/copilot.cmd"},
        pty_available=True,
        pwsh_available=True,
        sdk_runtime=sdk_runtime,
        sdk_cli_version="1.0.79",
        gui_importable=True,
    )


def _check(
    check_id: str,
    *,
    passed: bool = True,
    reason_code: str = "ok",
    failure_state: bv.BootstrapState | None = None,
) -> bv.CheckResult:
    return bv.CheckResult(
        check_id=check_id,
        passed=passed,
        reason_code=reason_code,
        failure_state=failure_state,
    )


def test_result_schema_order_and_exit_codes_are_fixed() -> None:
    checks = tuple(_check(check_id) for check_id in _REQUIRED_CHECK_IDS)
    result = bv.VerificationResult(bv.BootstrapState.READY, checks)

    assert result.schema_version == 1
    assert result.exit_code == 0
    assert set(result.to_dict()) == {"schema_version", "state", "checks"}
    assert [item["check_id"] for item in result.to_dict()["checks"]] == list(
        _REQUIRED_CHECK_IDS
    )
    assert bv.VerificationResult(bv.BootstrapState.NEEDS_SETUP, ()).exit_code == 10
    assert (
        bv.VerificationResult(bv.BootstrapState.NEEDS_VERSION_DECISION, ()).exit_code
        == 11
    )
    assert bv.VerificationResult(bv.BootstrapState.BLOCKED, ()).exit_code == 12


def test_state_priority_is_blocked_then_version_then_setup_then_ready() -> None:
    setup = _check(
        "gh",
        passed=False,
        reason_code="not-found",
        failure_state=bv.BootstrapState.NEEDS_SETUP,
    )
    version = _check(
        "hve-version",
        passed=False,
        reason_code="version-mismatch",
        failure_state=bv.BootstrapState.NEEDS_VERSION_DECISION,
    )
    blocked = _check(
        "manifest",
        passed=False,
        reason_code="hash-mismatch",
        failure_state=bv.BootstrapState.BLOCKED,
    )

    assert bv.classify_state(()) is bv.BootstrapState.READY
    assert bv.classify_state((setup,)) is bv.BootstrapState.NEEDS_SETUP
    assert bv.classify_state((setup, version)) is bv.BootstrapState.NEEDS_VERSION_DECISION
    assert bv.classify_state((setup, version, blocked)) is bv.BootstrapState.BLOCKED


def test_payload_validation_rejects_unknown_shape_and_state_exit_mismatch() -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "state": "ready",
        "checks": [
            {"check_id": item, "passed": True, "reason_code": "ok"}
            for item in _REQUIRED_CHECK_IDS
        ],
    }
    assert bv.validate_payload(payload, reported_exit=0) == ()

    assert "state-exit-mismatch" in bv.validate_payload(payload, reported_exit=10)
    assert "unknown-top-level-key" in bv.validate_payload(
        {**payload, "detail": "must not be accepted"}, reported_exit=0
    )
    assert "invalid-check-order" in bv.validate_payload(
        {**payload, "checks": list(reversed(payload["checks"]))}, reported_exit=0
    )
    assert "invalid-schema-version" in bv.validate_payload(
        {**payload, "schema_version": True}, reported_exit=0
    )
    contradictory = {
        **payload,
        "checks": [
            {
                **item,
                "passed": False,
                "reason_code": "gh-not-found",
            }
            if item["check_id"] == "gh"
            else item
            for item in payload["checks"]
        ],
    }
    assert "state-check-mismatch" in bv.validate_payload(
        contradictory, reported_exit=0
    )


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda value: value.pop("state"), "missing-top-level-key"),
        (lambda value: value.__setitem__("state", "unknown"), "invalid-state"),
        (lambda value: value.__setitem__("checks", value["checks"][:-1]), "invalid-check-order"),
        (
            lambda value: value["checks"].append(dict(value["checks"][0])),
            "invalid-check-order",
        ),
        (
            lambda value: value["checks"][0].__setitem__("passed", 1),
            "invalid-check-passed",
        ),
        (
            lambda value: value["checks"][0].__setitem__("reason_code", ""),
            "invalid-check-reason-code",
        ),
        (
            lambda value: value["checks"][0].__setitem__("extra", "value"),
            "unknown-check-key",
        ),
        (lambda value: value.__setitem__("checks", "not-a-list"), "invalid-checks"),
        (
            lambda value: value.__setitem__("checks", ["not-an-object"]),
            "invalid-check",
        ),
        (
            lambda value: value["checks"][0].pop("check_id"),
            "missing-check-key",
        ),
        (
            lambda value: value["checks"][0].__setitem__(
                "reason_code", "invented-reason"
            ),
            "invalid-check-reason-code",
        ),
    ],
)
def test_payload_validation_rejects_missing_duplicate_and_typed_fields(
    mutator: object, expected: str
) -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "state": "ready",
        "checks": [
            {"check_id": item, "passed": True, "reason_code": "ok"}
            for item in _REQUIRED_CHECK_IDS
        ],
    }
    mutator(payload)  # type: ignore[operator]
    assert expected in bv.validate_payload(payload, reported_exit=0)


@pytest.mark.parametrize("payload", [None, [], "text", 1, True])
def test_payload_validation_rejects_non_object_roots(payload: object) -> None:
    assert bv.validate_payload(payload, reported_exit=2) == ("invalid-payload",)


def test_schema_version_and_exit_require_integers() -> None:
    payload = bv.VerificationResult(
        bv.BootstrapState.READY, tuple(_check(name) for name in _REQUIRED_CHECK_IDS)
    ).to_dict()
    assert "invalid-schema-version" in bv.validate_payload(
        {**payload, "schema_version": 1.0}, reported_exit=0
    )
    assert "invalid-exit-code" in bv.validate_payload(payload, reported_exit=False)


def test_python_check_requires_311_and_distribution_venv(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    windows_venv = root / ".venv" / "Scripts" / "python.exe"
    posix_venv = root / ".venv" / "bin" / "python"
    windows_venv.parent.mkdir(parents=True)
    posix_venv.parent.mkdir(parents=True)
    windows_venv.write_bytes(b"python")
    posix_venv.write_bytes(b"python")

    too_old = bv.check_python(
        root,
        executable=windows_venv,
        prefix=root / ".venv",
        version_info=(3, 10, 14),
        platform_name="win32",
        isolated=True,
    )
    outside = bv.check_python(
        root,
        executable=tmp_path / "Python" / "python.exe",
        prefix=root / ".venv",
        version_info=(3, 11, 0),
        platform_name="win32",
        isolated=True,
    )
    windows_ok = bv.check_python(
        root,
        executable=windows_venv,
        prefix=root / ".venv",
        version_info=(3, 11, 0),
        platform_name="win32",
        isolated=True,
    )
    posix_ok = bv.check_python(
        root,
        executable=posix_venv,
        prefix=root / ".venv",
        version_info=(3, 12, 0),
        platform_name="darwin",
        isolated=True,
    )
    non_isolated = bv.check_python(
        root,
        executable=windows_venv,
        prefix=root / ".venv",
        version_info=(3, 11, 0),
        platform_name="win32",
        isolated=False,
    )

    assert not too_old.passed and too_old.reason_code == "python-too-old"
    assert not outside.passed and outside.reason_code == "python-outside-distribution-venv"
    assert windows_ok.passed
    assert posix_ok.passed
    assert not non_isolated.passed and non_isolated.reason_code == "python-not-isolated"


def test_posix_venv_python_symlink_to_base_interpreter_is_allowed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "distribution"
    base = tmp_path / "base" / "python3"
    venv_python = root / ".venv" / "bin" / "python"
    base.parent.mkdir(parents=True)
    venv_python.parent.mkdir(parents=True)
    base.write_bytes(b"python")
    try:
        venv_python.symlink_to(base)
    except OSError:
        pytest.skip("file symlink creation is not available")

    result = bv.check_python(
        root,
        executable=venv_python,
        prefix=root / ".venv",
        version_info=(3, 11, 0),
        platform_name="darwin",
        isolated=True,
    )
    assert result.passed


def test_path_containment_rejects_prefix_drive_unc_and_symlink_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "App"
    root.mkdir()
    assert bv.is_path_within(root, root / ".venv" / "python", platform_name="darwin")
    assert not bv.is_path_within(
        root, tmp_path / "App-evil" / ".venv" / "python", platform_name="darwin"
    )
    assert bv.is_path_within(
        Path("C:/App"), Path("c:/APP/.venv/Scripts/python.exe"), platform_name="win32"
    )
    assert not bv.is_path_within(
        Path("C:/App"), Path("D:/App/.venv/Scripts/python.exe"), platform_name="win32"
    )
    assert not bv.is_path_within(
        Path("C:/App"), Path("//server/share/App/python.exe"), platform_name="win32"
    )

    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is not available")
    assert not bv.is_path_within(root, link / "module.py", platform_name=os.name)


def test_hve_version_uses_zip_root_without_git_or_network(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "hve"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    match = bv.check_hve_version(root, installed_version=lambda: "1.2.3")
    mismatch = bv.check_hve_version(root, installed_version=lambda: "1.2.2")

    assert match.passed and match.reason_code == "ok"
    assert not mismatch.passed
    assert mismatch.reason_code == "version-mismatch"
    assert mismatch.failure_state is bv.BootstrapState.NEEDS_VERSION_DECISION
    assert not (root / ".git").exists()


@pytest.mark.parametrize(
    ("platform_name", "product_version", "machine", "target", "passed"),
    [
        ("win32", "11.0.26100", "AMD64", "windows-x64", True),
        ("win32", "10.0.19045", "AMD64", "windows-x64", False),
        ("win32", "11.0.26100", "ARM64", "windows-x64", False),
        ("darwin", "15.7.1", "arm64", "macos-arm64", True),
        ("darwin", "26.0", "arm64", "macos-arm64", True),
        ("darwin", "14.7", "arm64", "macos-arm64", False),
        ("darwin", "15.7.1", "x86_64", "macos-arm64", False),
    ],
)
def test_platform_check_uses_os_product_version_not_kernel_release(
    tmp_path: Path,
    platform_name: str,
    product_version: str,
    machine: str,
    target: str,
    passed: bool,
) -> None:
    probes = SimpleNamespace(
        platform_name=platform_name,
        os_product_version=product_version,
        machine=machine,
        target_platform=target,
    )
    assert bv.check_platform(tmp_path, probes).passed is passed


def test_import_locations_must_resolve_inside_distribution_root(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    inside = root / "hve" / "__init__.py"
    outside = tmp_path / "other" / "mdq" / "__init__.py"
    inside.parent.mkdir(parents=True)
    outside.parent.mkdir(parents=True)
    inside.write_text("", encoding="utf-8")
    outside.write_text("", encoding="utf-8")

    failed = bv.check_import_locations(
        root,
        module_files={"hve": inside, "mdq": outside, "cq": root / "cq" / "__init__.py"},
    )
    assert not failed.passed
    assert failed.reason_code == "source-import-outside-package-root"

    site_packages = root / ".venv" / "Lib" / "site-packages" / "hve" / "__init__.py"
    site_packages.parent.mkdir(parents=True)
    site_packages.write_text("", encoding="utf-8")
    wrong_root = bv.check_import_locations(
        root,
        module_files={
            "hve": site_packages,
            "mdq": root / "mdq" / "__init__.py",
            "cq": root / "cq" / "__init__.py",
        },
    )
    assert not wrong_root.passed
    assert wrong_root.reason_code == "source-import-outside-package-root"


def test_manifest_validates_schema_target_paths_and_actual_hashes(tmp_path: Path) -> None:
    root = tmp_path / "distribution"
    root.mkdir()
    path = _write_manifest(root, target_platform="windows-x64")

    assert bv.check_manifest(root, expected_target="windows-x64").passed
    (root / "hve" / "bootstrap_verify.py").write_bytes(b"changed")
    mismatch = bv.check_manifest(root, expected_target="windows-x64")
    assert not mismatch.passed and mismatch.reason_code == "manifest-hash-mismatch"

    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"] = {"../escape": "0" * 64}
    path.write_text(json.dumps(manifest), encoding="utf-8")
    unsafe = bv.check_manifest(root, expected_target="windows-x64")
    assert not unsafe.passed and unsafe.reason_code == "manifest-unsafe-path"

    _write_manifest(root, target_platform="windows-x64")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"].pop("hve/setup-hve.ps1")
    path.write_text(json.dumps(manifest), encoding="utf-8")
    missing = bv.check_manifest(root, expected_target="windows-x64")
    assert not missing.passed and missing.reason_code == "manifest-required-file-missing"

    _write_manifest(root, target_platform="windows-x64")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["hve_version"] = "1.2.4"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    version_mismatch = bv.check_manifest(root, expected_target="windows-x64")
    assert not version_mismatch.passed
    assert version_mismatch.reason_code == "manifest-version-mismatch"


def test_sdk_runtime_and_external_cli_are_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPILOT_CLI_PATH", "C:/sdk-cache/copilot.exe")
    monkeypatch.setattr(bv.shutil, "which", lambda _name: None)
    assert bv.resolve_external_copilot_cli() is None

    monkeypatch.setattr(bv, "find_copilot_binary", lambda: "C:/sdk-cache/copilot.exe")
    assert bv.resolve_sdk_copilot_runtime() == Path("C:/sdk-cache/copilot.exe")
    assert not bv.check_external_copilot_cli().passed
    assert bv.check_sdk_runtime(
        version_runner=lambda _path: "1.0.79",
        expected_version="1.0.79",
    ).passed
    mismatch = bv.check_sdk_runtime(
        version_runner=lambda _path: "1.0.80",
        expected_version="1.0.79",
    )
    assert not mismatch.passed
    assert mismatch.reason_code == "sdk-runtime-version-mismatch"


def test_check_runner_never_emits_exception_text_or_credentials(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "github_pat_must_not_leak"

    def raises() -> bv.CheckResult:
        raise RuntimeError(f"failure with {secret} and https://user:token@example.invalid")

    with caplog.at_level(logging.DEBUG):
        result = bv.run_check("manifest", raises, bv.BootstrapState.BLOCKED)
    captured = capsys.readouterr()
    rendered = "\n".join(
        (
            json.dumps(result.to_dict(), ensure_ascii=False),
            captured.out,
            captured.err,
            caplog.text,
        )
    )

    assert not result.passed
    assert result.reason_code == "internal-error"
    assert secret not in rendered
    assert "example.invalid" not in rendered


def test_verification_runs_exact_checks_once_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[str] = []

    assert bv.CHECK_FUNCTIONS == _EXPECTED_CHECK_FUNCTIONS
    for check_id, function_name in _EXPECTED_CHECK_FUNCTIONS:
        def make_checker(expected_id: str):
            def checker(*_args: object, **_kwargs: object) -> bv.CheckResult:
                seen.append(expected_id)
                return _check(expected_id)

            return checker

        monkeypatch.setattr(bv, function_name, make_checker(check_id))
    result = bv.verify_distribution(tmp_path, probes=SimpleNamespace())

    assert seen == list(_REQUIRED_CHECK_IDS)
    assert result.state is bv.BootstrapState.READY
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("failed_id", "failure_state"),
    [
        ("platform", bv.BootstrapState.BLOCKED),
        ("manifest", bv.BootstrapState.BLOCKED),
        ("python", bv.BootstrapState.NEEDS_SETUP),
        ("hve-version", bv.BootstrapState.NEEDS_VERSION_DECISION),
        ("source-imports", bv.BootstrapState.NEEDS_SETUP),
        ("pip-check", bv.BootstrapState.NEEDS_SETUP),
        ("gui-imports", bv.BootstrapState.NEEDS_SETUP),
        ("gh", bv.BootstrapState.NEEDS_SETUP),
        ("pty", bv.BootstrapState.NEEDS_SETUP),
        ("pwsh", bv.BootstrapState.NEEDS_SETUP),
        ("sdk-runtime", bv.BootstrapState.NEEDS_SETUP),
        ("external-copilot-cli", bv.BootstrapState.NEEDS_SETUP),
    ],
)
def test_each_checker_failure_is_preserved_and_classified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failed_id: str,
    failure_state: bv.BootstrapState,
) -> None:
    calls: dict[str, int] = {check_id: 0 for check_id in _REQUIRED_CHECK_IDS}
    failure_reasons = {
        "platform": "unsupported-target", "manifest": "manifest-hash-mismatch",
        "python": "python-not-isolated", "hve-version": "version-mismatch",
        "source-imports": "source-import-missing", "pip-check": "pip-check-failed",
        "gui-imports": "gui-import-failed", "gh": "gh-not-found",
        "pty": "pty-unavailable", "pwsh": "pwsh7-unavailable",
        "sdk-runtime": "sdk-runtime-not-found",
        "external-copilot-cli": "external-copilot-cli-not-found",
    }
    for check_id, function_name in _EXPECTED_CHECK_FUNCTIONS:
        def make_checker(expected_id: str):
            def checker(*_args: object, **_kwargs: object) -> bv.CheckResult:
                calls[expected_id] += 1
                if expected_id == failed_id:
                    return _check(
                        expected_id,
                        passed=False,
                        reason_code=failure_reasons[expected_id],
                        failure_state=failure_state,
                    )
                return _check(expected_id)

            return checker

        monkeypatch.setattr(bv, function_name, make_checker(check_id))

    result = bv.verify_distribution(tmp_path, probes=SimpleNamespace())

    assert calls == {check_id: 1 for check_id in _REQUIRED_CHECK_IDS}
    assert result.state is failure_state
    failed = [item for item in result.checks if not item.passed]
    assert [(item.check_id, item.reason_code) for item in failed] == [
        (failed_id, failure_reasons[failed_id])
    ]
    assert bv.validate_payload(result.to_dict(), reported_exit=result.exit_code) == ()


def test_main_json_output_matches_exit_and_has_no_extra_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    result = bv.VerificationResult(
        bv.BootstrapState.NEEDS_SETUP,
        tuple(
            _check(
                check_id,
                passed=check_id != "gh",
                reason_code="gh-not-found" if check_id == "gh" else "ok",
                failure_state=(
                    bv.BootstrapState.NEEDS_SETUP if check_id == "gh" else None
                ),
            )
            for check_id in _REQUIRED_CHECK_IDS
        ),
    )
    monkeypatch.setattr(bv, "verify_distribution", lambda _root: result)

    exit_code = bv.main(["--root", str(tmp_path), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 10
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload == result.to_dict()
    assert bv.validate_payload(payload, reported_exit=exit_code) == ()


def test_main_returns_2_for_argument_and_manifest_schema_errors(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes = _test_probes(tmp_path)
    monkeypatch.setattr(bv, "_default_probes", lambda root: probes)
    assert bv.main(["--unknown"]) == 2
    capsys.readouterr()
    assert bv.main(["--root", str(tmp_path), "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["state"] == "blocked"
    assert any(item["reason_code"] == "manifest-missing" for item in payload["checks"])
    assert bv.validate_payload(payload, reported_exit=2) == ()


def test_verifier_has_no_auth_workflow_azure_or_remote_side_effect_surface(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    invoked: list[tuple[str, ...]] = []

    def command_runner(argv: list[str]) -> SimpleNamespace:
        invoked.append(tuple(argv))
        return SimpleNamespace(returncode=0, stdout="1.0.79\n", stderr="")

    probes = _test_probes(tmp_path)
    probes.command_runner = command_runner
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="hve"\nversion="1.2.3"\n', encoding="utf-8"
    )
    _write_manifest(tmp_path, target_platform="windows-x64")

    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("network"))
    monkeypatch.setattr(webbrowser, "open", lambda *_a, **_k: pytest.fail("browser"))
    monkeypatch.setattr(os, "system", lambda *_a, **_k: pytest.fail("os.system"))
    monkeypatch.setattr(
        subprocess, "run", lambda *_a, **_k: pytest.fail("ambient subprocess")
    )
    result = bv.verify_distribution(tmp_path, probes=probes)

    assert result.state is bv.BootstrapState.READY
    assert invoked
    assert all(
        ("-m", "pip", "check") == call[1:4]
        or call[-2:] == ("--no-auto-update", "--version")
        for call in invoked
    )

    source = Path(bv.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "gh auth login",
        "copilot login",
        "webbrowser",
        "azure login",
        "az login",
        "run_workflow",
        "git pull",
        "git fetch",
        "create_issue",
        "create_pull_request",
    ):
        assert forbidden not in source.lower()
    for forbidden_import in (
        "import requests",
        "import httpx",
        "import socket",
        "import webbrowser",
        "import urllib.request",
    ):
        assert forbidden_import not in source


def test_manifest_content_failure_uses_blocked_exit_not_schema_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    probes = _test_probes(tmp_path)
    _write_manifest(tmp_path, target_platform="windows-x64")
    (tmp_path / "hve" / "bootstrap_verify.py").write_bytes(b"tampered")
    monkeypatch.setattr(bv, "_default_probes", lambda root: probes)
    assert bv.main(["--root", str(tmp_path), "--json"]) == 12
    assert bv.validate_payload(json.loads(capsys.readouterr().out), reported_exit=12) == ()


@pytest.mark.parametrize("raw", ["hve//a.py", "./hve/a.py", "C:/escape", "hve/a:stream", "hve/a\n.py"])
def test_manifest_paths_are_canonical_on_every_platform(tmp_path: Path, raw: str) -> None:
    assert bv._safe_manifest_path(tmp_path, raw) is None


def test_current_python_passes_prefix_to_the_shared_predicate(tmp_path: Path) -> None:
    probes = _test_probes(tmp_path)
    assert bv.check_current_python(tmp_path, probes).passed
    probes.prefix = tmp_path / "other-venv"
    assert bv.check_current_python(tmp_path, probes).reason_code == "python-prefix-mismatch"


def test_checker_cannot_emit_unknown_reason_or_conflicting_state() -> None:
    bad = bv.run_check(
        "gh", lambda: _check("gh", reason_code="unknown"), bv.BootstrapState.NEEDS_SETUP
    )
    assert bad.reason_code == "internal-error"
    assert bad.failure_state is bv.BootstrapState.NEEDS_SETUP
    corrected = bv.run_check(
        "hve-version",
        lambda: _check("hve-version", passed=False, reason_code="source-version-unavailable",
                       failure_state=bv.BootstrapState.NEEDS_SETUP),
        bv.BootstrapState.NEEDS_SETUP,
    )
    assert corrected.failure_state is bv.BootstrapState.BLOCKED
