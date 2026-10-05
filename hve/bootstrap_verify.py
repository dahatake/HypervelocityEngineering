"""Private source distribution readiness checks for FR-LOCAL-SURFACE-04."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import hashlib
import importlib
import importlib.metadata as metadata
import json
import ntpath
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
from types import SimpleNamespace
from typing import Any, Callable, Mapping, NoReturn, Sequence, cast

from .auth import find_copilot_binary
from .startup_version import _parse_version, _read_source_version


_SCHEMA_VERSION = 1
_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_SOURCE_FILES_BY_TARGET: dict[str, tuple[str, ...]] = {
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
_GENERATED_REQUIRED_BY_TARGET: dict[str, tuple[str, ...]] = {
    "windows-x64": (
        "Start-HVE.cmd",
        "Start-HVE.ps1",
        "hve-bootstrap-critical.sha256",
        "hve-bootstrap-manifest.json",
    ),
    "macos-arm64": (
        "Start-HVE.command",
        "hve-bootstrap-critical.sha256",
        "hve-bootstrap-manifest.json",
    ),
}
_LAUNCHER_BY_TARGET = {
    "windows-x64": "Start-HVE.cmd",
    "macos-arm64": "Start-HVE.command",
}
_MANIFEST_KEYS = {
    "schema_version",
    "distribution_kind",
    "hve_version",
    "source_commit",
    "source_dirty",
    "target_platform",
    "launcher",
    "files",
}
_CHECK_KEYS = {"check_id", "passed", "reason_code"}
_MANIFEST_SCHEMA_ERROR_REASONS = {
    "manifest-missing",
    "manifest-invalid-json",
    "manifest-invalid-schema",
    "manifest-invalid-kind",
    "manifest-invalid-version",
    "manifest-invalid-commit",
    "manifest-invalid-dirty-state",
    "manifest-invalid-files",
    "manifest-invalid-hash",
}
_REASON_CODES_BY_CHECK: dict[str, frozenset[str]] = {
    "platform": frozenset(
        {
            "ok",
            "unsupported-windows-platform",
            "unsupported-windows-version",
            "unsupported-macos-platform",
            "unsupported-macos-version",
            "unsupported-target",
            "internal-error",
        }
    ),
    "manifest": frozenset(
        {
            "ok",
            *_MANIFEST_SCHEMA_ERROR_REASONS,
            "manifest-target-mismatch",
            "manifest-launcher-mismatch",
            "manifest-required-file-missing",
            "manifest-unsafe-path",
            "manifest-file-missing",
            "manifest-hash-mismatch",
            "manifest-generated-file-missing",
            "manifest-version-mismatch",
            "internal-error",
        }
    ),
    "python": frozenset(
        {
            "ok",
            "python-too-old",
            "python-not-isolated",
            "python-prefix-mismatch",
            "python-outside-distribution-venv",
            "internal-error",
        }
    ),
    "hve-version": frozenset(
        {
            "ok",
            "source-version-unavailable",
            "installed-version-unavailable",
            "version-mismatch",
            "internal-error",
        }
    ),
    "source-imports": frozenset(
        {
            "ok",
            "source-import-missing",
            "source-import-outside-package-root",
            "internal-error",
        }
    ),
    "pip-check": frozenset(
        {"ok", "pip-check-error", "pip-check-failed", "internal-error"}
    ),
    "gui-imports": frozenset({"ok", "gui-import-failed", "internal-error"}),
    "gh": frozenset({"ok", "gh-not-found", "internal-error"}),
    "pty": frozenset({"ok", "pty-unavailable", "internal-error"}),
    "pwsh": frozenset({"ok", "pwsh7-unavailable", "internal-error"}),
    "sdk-runtime": frozenset(
        {
            "ok",
            "sdk-runtime-not-found",
            "sdk-pin-unavailable",
            "sdk-runtime-invalid-version",
            "sdk-runtime-version-mismatch",
            "internal-error",
        }
    ),
    "external-copilot-cli": frozenset(
        {"ok", "external-copilot-cli-not-found", "internal-error"}
    ),
}


class BootstrapState(str, Enum):
    READY = "ready"
    NEEDS_SETUP = "needs_setup"
    NEEDS_VERSION_DECISION = "needs_version_decision"
    BLOCKED = "blocked"


EXIT_BY_STATE: dict[BootstrapState, int] = {
    BootstrapState.READY: 0,
    BootstrapState.NEEDS_SETUP: 10,
    BootstrapState.NEEDS_VERSION_DECISION: 11,
    BootstrapState.BLOCKED: 12,
}


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    passed: bool
    reason_code: str
    failure_state: BootstrapState | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class VerificationResult:
    state: BootstrapState
    checks: tuple[CheckResult, ...]

    @property
    def schema_version(self) -> int:
        return _SCHEMA_VERSION

    @property
    def exit_code(self) -> int:
        return EXIT_BY_STATE[self.state]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "checks": [check.to_dict() for check in self.checks],
        }


CHECK_FUNCTIONS: tuple[tuple[str, str], ...] = (
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
_CHECK_IDS = tuple(check_id for check_id, _function_name in CHECK_FUNCTIONS)


def _ok(check_id: str) -> CheckResult:
    return CheckResult(check_id, True, "ok")


def _failed(
    check_id: str,
    reason_code: str,
    state: BootstrapState,
) -> CheckResult:
    return CheckResult(check_id, False, reason_code, state)


def classify_state(checks: Sequence[CheckResult]) -> BootstrapState:
    failed_states = {
        check.failure_state or BootstrapState.BLOCKED
        for check in checks
        if not check.passed
    }
    for state in (
        BootstrapState.BLOCKED,
        BootstrapState.NEEDS_VERSION_DECISION,
        BootstrapState.NEEDS_SETUP,
    ):
        if state in failed_states:
            return state
    return BootstrapState.READY


def _payload_failure_state(check_id: str, reason_code: str) -> BootstrapState:
    if check_id in {"platform", "manifest"}:
        return BootstrapState.BLOCKED
    if check_id == "hve-version":
        if reason_code == "version-mismatch":
            return BootstrapState.NEEDS_VERSION_DECISION
        if reason_code == "source-version-unavailable":
            return BootstrapState.BLOCKED
    return BootstrapState.NEEDS_SETUP


def validate_payload(payload: object, *, reported_exit: int) -> tuple[str, ...]:
    if not isinstance(payload, dict):
        return ("invalid-payload",)

    errors: list[str] = []
    keys = set(payload)
    required_keys = {"schema_version", "state", "checks"}
    if keys - required_keys:
        errors.append("unknown-top-level-key")
    if required_keys - keys:
        errors.append("missing-top-level-key")

    schema_version = payload.get("schema_version")
    if type(schema_version) is not int or schema_version != _SCHEMA_VERSION:
        errors.append("invalid-schema-version")
    if type(reported_exit) is not int:
        errors.append("invalid-exit-code")

    state_value = payload.get("state")
    try:
        state = BootstrapState(state_value) if isinstance(state_value, str) else None
    except ValueError:
        state = None
    if state is None:
        errors.append("invalid-state")

    checks_value = payload.get("checks")
    parsed_ids: list[str] = []
    manifest_schema_failure = False
    parsed_checks: list[CheckResult] = []
    if not isinstance(checks_value, list):
        errors.append("invalid-checks")
    else:
        for item in checks_value:
            if not isinstance(item, dict):
                errors.append("invalid-check")
                continue
            item_keys = set(item)
            if item_keys - _CHECK_KEYS:
                errors.append("unknown-check-key")
            if _CHECK_KEYS - item_keys:
                errors.append("missing-check-key")
            check_id = item.get("check_id")
            if isinstance(check_id, str):
                parsed_ids.append(check_id)
            if not isinstance(item.get("passed"), bool):
                errors.append("invalid-check-passed")
            reason_code = item.get("reason_code")
            if not isinstance(reason_code, str) or not reason_code:
                errors.append("invalid-check-reason-code")
            elif (
                isinstance(check_id, str)
                and reason_code not in _REASON_CODES_BY_CHECK.get(check_id, frozenset())
            ):
                errors.append("invalid-check-reason-code")
            if isinstance(check_id, str) and isinstance(item.get("passed"), bool) and isinstance(reason_code, str):
                passed = bool(item["passed"])
                if (passed and reason_code != "ok") or (not passed and reason_code == "ok"):
                    errors.append("invalid-check-reason-code")
                elif check_id in _REASON_CODES_BY_CHECK:
                    parsed_checks.append(
                        CheckResult(
                            check_id,
                            passed,
                            reason_code,
                            None if passed else _payload_failure_state(check_id, reason_code),
                        )
                    )
            if (
                check_id == "manifest"
                and item.get("passed") is False
                and isinstance(reason_code, str)
                and reason_code in _MANIFEST_SCHEMA_ERROR_REASONS
            ):
                manifest_schema_failure = True
        if tuple(parsed_ids) != _CHECK_IDS:
            errors.append("invalid-check-order")

    if state is not None:
        if tuple(parsed_ids) == _CHECK_IDS and len(parsed_checks) == len(_CHECK_IDS):
            if classify_state(parsed_checks) is not state:
                errors.append("state-check-mismatch")
        expected_exit = EXIT_BY_STATE[state]
        schema_error_exit = (
            reported_exit == 2
            and state is BootstrapState.BLOCKED
            and manifest_schema_failure
        )
        if reported_exit != expected_exit and not schema_error_exit:
            errors.append("state-exit-mismatch")

    return tuple(dict.fromkeys(errors))


def _is_windows_name(value: str) -> bool:
    return value.lower() in {"nt", "win", "win32", "windows"} or value.lower().startswith(
        "win"
    )


def is_path_within(root: Path, candidate: Path, *, platform_name: str) -> bool:
    try:
        root_resolved = root.resolve(strict=False)
        candidate_resolved = candidate.resolve(strict=False)
    except OSError:
        return False

    if _is_windows_name(platform_name):
        root_text = ntpath.normcase(str(root_resolved))
        candidate_text = ntpath.normcase(str(candidate_resolved))
        try:
            common = ntpath.commonpath((root_text, candidate_text))
        except ValueError:
            return False
        return common == root_text

    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError:
        return False
    return True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_manifest_path(root: Path, raw: object) -> Path | None:
    if (
        not isinstance(raw, str)
        or not raw
        or "\\" in raw
        or ":" in raw
        or any(ord(char) < 32 for char in raw)
        or any(part in {"", ".", ".."} for part in raw.split("/"))
    ):
        return None
    pure = Path(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    resolved = root / pure
    for part in (resolved, *resolved.parents):
        if part == root:
            break
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            return None
    if not is_path_within(root, resolved, platform_name=os.name):
        return None
    return resolved


def _read_manifest(root: Path) -> dict[str, object] | None:
    try:
        value = json.loads((root / "hve-bootstrap-manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _target_from_probes(root: Path, probes: object | None) -> str:
    explicit_target = getattr(probes, "target_platform", None)
    if isinstance(explicit_target, str):
        return explicit_target
    manifest = _read_manifest(root)
    if manifest is not None and isinstance(manifest.get("target_platform"), str):
        return str(manifest["target_platform"])
    platform_name = str(getattr(probes, "platform_name", sys.platform))
    return "windows-x64" if _is_windows_name(platform_name) else "macos-arm64"


def check_manifest(
    root: Path,
    probes: object | None = None,
    *,
    expected_target: str | None = None,
) -> CheckResult:
    check_id = "manifest"
    path = root / "hve-bootstrap-manifest.json"
    if not path.is_file():
        return _failed(check_id, "manifest-missing", BootstrapState.BLOCKED)
    try:
        raw = path.read_text(encoding="utf-8")
        manifest = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _failed(check_id, "manifest-invalid-json", BootstrapState.BLOCKED)
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_KEYS:
        return _failed(check_id, "manifest-invalid-schema", BootstrapState.BLOCKED)
    if type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        return _failed(check_id, "manifest-invalid-schema", BootstrapState.BLOCKED)
    if manifest.get("distribution_kind") != "hve-private-source":
        return _failed(check_id, "manifest-invalid-kind", BootstrapState.BLOCKED)
    version = manifest.get("hve_version")
    if not isinstance(version, str) or _VERSION_RE.fullmatch(version) is None:
        return _failed(check_id, "manifest-invalid-version", BootstrapState.BLOCKED)
    source_version = _read_source_version(root)
    if source_version is None or source_version != version:
        return _failed(check_id, "manifest-version-mismatch", BootstrapState.BLOCKED)
    commit = manifest.get("source_commit")
    if not isinstance(commit, str) or _COMMIT_RE.fullmatch(commit) is None:
        return _failed(check_id, "manifest-invalid-commit", BootstrapState.BLOCKED)
    if not isinstance(manifest.get("source_dirty"), bool):
        return _failed(check_id, "manifest-invalid-dirty-state", BootstrapState.BLOCKED)

    target = manifest.get("target_platform")
    expected = expected_target or _target_from_probes(root, probes)
    if not isinstance(target, str) or target not in _REQUIRED_SOURCE_FILES_BY_TARGET or target != expected:
        return _failed(check_id, "manifest-target-mismatch", BootstrapState.BLOCKED)
    if manifest.get("launcher") != _LAUNCHER_BY_TARGET[target]:
        return _failed(check_id, "manifest-launcher-mismatch", BootstrapState.BLOCKED)

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return _failed(check_id, "manifest-invalid-files", BootstrapState.BLOCKED)
    resolved_entries: list[tuple[Path, str]] = []
    for relative, expected_hash in files.items():
        resolved = _safe_manifest_path(root, relative)
        if resolved is None:
            return _failed(check_id, "manifest-unsafe-path", BootstrapState.BLOCKED)
        if not isinstance(expected_hash, str) or _SHA256_RE.fullmatch(expected_hash) is None:
            return _failed(check_id, "manifest-invalid-hash", BootstrapState.BLOCKED)
        resolved_entries.append((resolved, expected_hash))

    required = set(_REQUIRED_SOURCE_FILES_BY_TARGET[target])
    if not required.issubset(files):
        return _failed(check_id, "manifest-required-file-missing", BootstrapState.BLOCKED)

    for resolved, expected_hash in resolved_entries:
        if not resolved.is_file():
            return _failed(check_id, "manifest-file-missing", BootstrapState.BLOCKED)
        if sha256_file(resolved) != expected_hash:
            return _failed(check_id, "manifest-hash-mismatch", BootstrapState.BLOCKED)

    for relative in _GENERATED_REQUIRED_BY_TARGET[target]:
        generated = _safe_manifest_path(root, relative)
        if generated is None or not generated.is_file():
            return _failed(check_id, "manifest-generated-file-missing", BootstrapState.BLOCKED)
    return _ok(check_id)


def check_python(
    root: Path,
    *,
    executable: Path,
    prefix: Path,
    version_info: Sequence[int],
    platform_name: str,
    isolated: bool,
) -> CheckResult:
    check_id = "python"
    if tuple(version_info[:2]) < (3, 11):
        return _failed(check_id, "python-too-old", BootstrapState.NEEDS_SETUP)
    if not isolated:
        return _failed(check_id, "python-not-isolated", BootstrapState.NEEDS_SETUP)
    expected_prefix = root / ".venv"
    try:
        prefix_matches = os.path.samefile(prefix, expected_prefix)
    except OSError:
        prefix_matches = (
            ntpath.normcase(os.path.abspath(str(prefix)))
            == ntpath.normcase(os.path.abspath(str(expected_prefix)))
            if _is_windows_name(platform_name)
            else os.path.abspath(str(prefix)) == os.path.abspath(str(expected_prefix))
        )
    if not prefix_matches:
        return _failed(check_id, "python-prefix-mismatch", BootstrapState.NEEDS_SETUP)
    expected = (
        root / ".venv" / "Scripts" / "python.exe"
        if _is_windows_name(platform_name)
        else root / ".venv" / "bin" / "python"
    )
    executable_text = os.path.abspath(str(executable))
    expected_text = os.path.abspath(str(expected))
    same = (
        ntpath.normcase(executable_text) == ntpath.normcase(expected_text)
        if _is_windows_name(platform_name)
        else executable_text == expected_text
    )
    if not same:
        return _failed(
            check_id,
            "python-outside-distribution-venv",
            BootstrapState.NEEDS_SETUP,
        )
    return _ok(check_id)


def check_hve_version(
    root: Path,
    *,
    installed_version: Callable[[], str | None],
) -> CheckResult:
    check_id = "hve-version"
    source = _read_source_version(root)
    if source is None or _parse_version(source) is None:
        return _failed(check_id, "source-version-unavailable", BootstrapState.BLOCKED)
    try:
        installed = installed_version()
    except Exception:
        installed = None
    if installed is None or _parse_version(installed) is None:
        return _failed(check_id, "installed-version-unavailable", BootstrapState.NEEDS_SETUP)
    if installed != source:
        return _failed(
            check_id,
            "version-mismatch",
            BootstrapState.NEEDS_VERSION_DECISION,
        )
    return _ok(check_id)


def check_import_locations(
    root: Path,
    *,
    module_files: Mapping[str, Path],
) -> CheckResult:
    check_id = "source-imports"
    for name in ("hve", "mdq", "cq"):
        path = module_files.get(name)
        expected = root / name / "__init__.py"
        if path is None or not Path(path).is_file():
            return _failed(check_id, "source-import-missing", BootstrapState.NEEDS_SETUP)
        try:
            same = os.path.samefile(path, expected)
        except OSError:
            same = (
                ntpath.normcase(os.path.abspath(str(path)))
                == ntpath.normcase(os.path.abspath(str(expected)))
                if os.name == "nt"
                else os.path.abspath(str(path)) == os.path.abspath(str(expected))
            )
        if not same:
            return _failed(
                check_id,
                "source-import-outside-package-root",
                BootstrapState.NEEDS_SETUP,
            )
    return _ok(check_id)


def resolve_sdk_copilot_runtime() -> Path | None:
    try:
        value = find_copilot_binary()
    except Exception:
        return None
    return Path(value) if value else None


def resolve_external_copilot_cli() -> Path | None:
    value = shutil.which("copilot")
    return Path(value) if value else None


def _run_version(path: Path) -> str | None:
    try:
        completed = subprocess.run(
            [str(path), "--no-auto-update", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    line = (completed.stdout or "").splitlines()
    return line[0].strip() if line else None


def check_sdk_runtime(
    *,
    version_runner: Callable[[Path], str | None] = _run_version,
    runtime_path: Path | None = None,
    expected_version: str | None = None,
) -> CheckResult:
    check_id = "sdk-runtime"
    path = runtime_path or resolve_sdk_copilot_runtime()
    if path is None:
        return _failed(check_id, "sdk-runtime-not-found", BootstrapState.NEEDS_SETUP)
    expected = expected_version if expected_version is not None else _sdk_cli_version()
    if not isinstance(expected, str) or re.fullmatch(r"\d+\.\d+\.\d+(?:-\d+)?", expected) is None:
        return _failed(check_id, "sdk-pin-unavailable", BootstrapState.NEEDS_SETUP)
    version = version_runner(path)
    match = re.search(r"(?<![\w.])(\d+\.\d+\.\d+(?:-\d+)?)(?![\w.-])", version) if isinstance(version, str) else None
    if match is None:
        return _failed(check_id, "sdk-runtime-invalid-version", BootstrapState.NEEDS_SETUP)
    if match.group(1) != expected:
        return _failed(check_id, "sdk-runtime-version-mismatch", BootstrapState.NEEDS_SETUP)
    return _ok(check_id)


def _default_command_runner(argv: list[str]) -> SimpleNamespace:
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        shell=False,
    )
    return SimpleNamespace(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _installed_version() -> str | None:
    try:
        value = metadata.version("hve")
    except (metadata.PackageNotFoundError, OSError, UnicodeError):
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _module_files() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for name in ("hve", "mdq", "cq"):
        try:
            module = importlib.import_module(name)
            raw = getattr(module, "__file__", None)
        except Exception:
            raw = None
        if isinstance(raw, str):
            result[name] = Path(raw)
    return result


def _gui_importable() -> bool:
    try:
        importlib.import_module("PySide6.QtWidgets")
        importlib.import_module("PySide6.QtWebEngineWidgets")
    except Exception:
        return False
    return True


def _pty_available() -> bool:
    try:
        from .gui.pty_backend import is_pty_available

        return bool(is_pty_available())
    except Exception:
        return False


def _pwsh_available() -> bool:
    if not sys.platform.startswith("win"):
        return True
    try:
        from .copilot_client_factory import _require_pwsh7_on_windows

        return bool(_require_pwsh7_on_windows())
    except Exception:
        return False


def _sdk_cli_version() -> str | None:
    try:
        return importlib.import_module("copilot._cli_version").CLI_VERSION
    except (ImportError, AttributeError):
        return None


def _os_product_version() -> str:
    if sys.platform == "darwin":
        return platform.mac_ver()[0]
    if sys.platform == "win32":
        version = sys.getwindowsversion()
        major = 11 if version.build >= 22000 and version.product_type == 1 else version.major
        return f"{major}.{version.minor}.{version.build}"
    return platform.release()


def _default_probes(root: Path) -> SimpleNamespace:
    del root
    return SimpleNamespace(
        platform_name=sys.platform,
        os_product_version=_os_product_version(),
        machine=platform.machine(),
        executable=Path(sys.executable),
        prefix=Path(sys.prefix),
        version_info=tuple(sys.version_info[:3]),
        isolated=bool(sys.flags.isolated),
        installed_version=_installed_version(),
        module_files=_module_files(),
        command_runner=_default_command_runner,
        which={"gh": shutil.which("gh"), "copilot": shutil.which("copilot")},
        pty_available=_pty_available(),
        pwsh_available=_pwsh_available(),
        sdk_runtime=resolve_sdk_copilot_runtime(),
        sdk_cli_version=_sdk_cli_version(),
        gui_importable=_gui_importable(),
    )


def check_platform(root: Path, probes: object | None = None) -> CheckResult:
    check_id = "platform"
    probes = _default_probes(root) if probes is None else probes
    target = _target_from_probes(root, probes)
    system = str(getattr(probes, "platform_name", ""))
    machine = str(getattr(probes, "machine", "")).lower()
    release = str(getattr(probes, "os_product_version", ""))
    if target == "windows-x64":
        if not _is_windows_name(system) or machine not in {"amd64", "x86_64"}:
            return _failed(check_id, "unsupported-windows-platform", BootstrapState.BLOCKED)
        if release not in {"11", "windows 11"} and not release.startswith("11."):
            return _failed(check_id, "unsupported-windows-version", BootstrapState.BLOCKED)
    elif target == "macos-arm64":
        if system.lower() not in {"darwin", "macos"} or machine not in {"arm64", "aarch64"}:
            return _failed(check_id, "unsupported-macos-platform", BootstrapState.BLOCKED)
        major = release.split(".", 1)[0]
        if major not in {"15", "26"}:
            return _failed(check_id, "unsupported-macos-version", BootstrapState.BLOCKED)
    else:
        return _failed(check_id, "unsupported-target", BootstrapState.BLOCKED)
    return _ok(check_id)


def check_current_python(root: Path, probes: object | None = None) -> CheckResult:
    probes = _default_probes(root) if probes is None else probes
    return check_python(
        root,
        executable=Path(getattr(probes, "executable")),
        prefix=Path(getattr(probes, "prefix")),
        version_info=tuple(getattr(probes, "version_info")),
        platform_name=str(getattr(probes, "platform_name")),
        isolated=bool(getattr(probes, "isolated")),
    )


def check_current_hve_version(root: Path, probes: object | None = None) -> CheckResult:
    probes = _default_probes(root) if probes is None else probes
    installed = getattr(probes, "installed_version", None)
    return check_hve_version(root, installed_version=lambda: installed)


def check_current_import_locations(root: Path, probes: object | None = None) -> CheckResult:
    probes = _default_probes(root) if probes is None else probes
    return check_import_locations(root, module_files=dict(getattr(probes, "module_files", {})))


def check_pip_consistency(root: Path, probes: object | None = None) -> CheckResult:
    check_id = "pip-check"
    probes = _default_probes(root) if probes is None else probes
    argv = [str(getattr(probes, "executable")), "-m", "pip", "check"]
    try:
        completed = getattr(probes, "command_runner")(argv)
    except Exception:
        return _failed(check_id, "pip-check-error", BootstrapState.NEEDS_SETUP)
    if getattr(completed, "returncode", None) != 0:
        return _failed(check_id, "pip-check-failed", BootstrapState.NEEDS_SETUP)
    return _ok(check_id)


def check_gui_imports(root: Path, probes: object | None = None) -> CheckResult:
    check_id = "gui-imports"
    probes = _default_probes(root) if probes is None else probes
    return (
        _ok(check_id)
        if bool(getattr(probes, "gui_importable", False))
        else _failed(check_id, "gui-import-failed", BootstrapState.NEEDS_SETUP)
    )


def check_gh(root: Path, probes: object | None = None) -> CheckResult:
    check_id = "gh"
    probes = _default_probes(root) if probes is None else probes
    value = dict(getattr(probes, "which", {})).get("gh")
    return (
        _ok(check_id)
        if value
        else _failed(check_id, "gh-not-found", BootstrapState.NEEDS_SETUP)
    )


def check_pty(root: Path, probes: object | None = None) -> CheckResult:
    check_id = "pty"
    probes = _default_probes(root) if probes is None else probes
    return (
        _ok(check_id)
        if bool(getattr(probes, "pty_available", False))
        else _failed(check_id, "pty-unavailable", BootstrapState.NEEDS_SETUP)
    )


def check_pwsh(root: Path, probes: object | None = None) -> CheckResult:
    check_id = "pwsh"
    probes = _default_probes(root) if probes is None else probes
    platform_name = str(getattr(probes, "platform_name", ""))
    if not _is_windows_name(platform_name):
        return _ok(check_id)
    return (
        _ok(check_id)
        if bool(getattr(probes, "pwsh_available", False))
        else _failed(check_id, "pwsh7-unavailable", BootstrapState.NEEDS_SETUP)
    )


def check_current_sdk_runtime(root: Path, probes: object | None = None) -> CheckResult:
    probes = _default_probes(root) if probes is None else probes
    runtime = getattr(probes, "sdk_runtime", None)
    if runtime is None:
        return _failed("sdk-runtime", "sdk-runtime-not-found", BootstrapState.NEEDS_SETUP)
    runner = getattr(probes, "command_runner")

    def version_runner(path: Path) -> str | None:
        try:
            completed = runner([str(path), "--no-auto-update", "--version"])
        except Exception:
            return None
        if getattr(completed, "returncode", None) != 0:
            return None
        lines = str(getattr(completed, "stdout", "")).splitlines()
        return lines[0].strip() if lines else None

    return check_sdk_runtime(
        version_runner=version_runner,
        runtime_path=Path(runtime),
        expected_version=getattr(probes, "sdk_cli_version", ""),
    )


def check_external_copilot_cli(
    root: Path | None = None,
    probes: object | None = None,
) -> CheckResult:
    check_id = "external-copilot-cli"
    if probes is None:
        path = resolve_external_copilot_cli()
    else:
        path = dict(getattr(probes, "which", {})).get("copilot")
    return (
        _ok(check_id)
        if path
        else _failed(check_id, "external-copilot-cli-not-found", BootstrapState.NEEDS_SETUP)
    )


def run_check(
    check_id: str,
    check: Callable[[], CheckResult],
    failure_state: BootstrapState,
) -> CheckResult:
    try:
        result = check()
    except Exception:
        return _failed(check_id, "internal-error", failure_state)
    if (
        not isinstance(result, CheckResult)
        or result.check_id != check_id
        or type(result.passed) is not bool
        or result.reason_code not in _REASON_CODES_BY_CHECK.get(check_id, frozenset())
        or result.passed != (result.reason_code == "ok")
    ):
        return _failed(check_id, "internal-error", failure_state)
    return CheckResult(
        check_id,
        result.passed,
        result.reason_code,
        None if result.passed else _payload_failure_state(check_id, result.reason_code),
    )


def verify_distribution(root: Path, *, probes: object | None = None) -> VerificationResult:
    root = Path(root).resolve(strict=False)
    probes = _default_probes(root) if probes is None else probes
    default_failure_states = {
        "platform": BootstrapState.BLOCKED,
        "manifest": BootstrapState.BLOCKED,
        "python": BootstrapState.NEEDS_SETUP,
        "hve-version": BootstrapState.NEEDS_SETUP,
        "source-imports": BootstrapState.NEEDS_SETUP,
        "pip-check": BootstrapState.NEEDS_SETUP,
        "gui-imports": BootstrapState.NEEDS_SETUP,
        "gh": BootstrapState.NEEDS_SETUP,
        "pty": BootstrapState.NEEDS_SETUP,
        "pwsh": BootstrapState.NEEDS_SETUP,
        "sdk-runtime": BootstrapState.NEEDS_SETUP,
        "external-copilot-cli": BootstrapState.NEEDS_SETUP,
    }
    checks: list[CheckResult] = []
    for check_id, function_name in CHECK_FUNCTIONS:
        function = cast(
            Callable[[Path, object], CheckResult],
            globals()[function_name],
        )

        # The editor's checker cannot infer a nested closure over the loop-local
        # callable, although the explicit cast above fixes the runtime contract.
        # type: ignore[reportUnknownLambdaType]
        def invoke(
            function: Callable[[Path, object], CheckResult] = function,
        ) -> CheckResult:
            return function(root, probes)

        checks.append(
            run_check(
                check_id,
                invoke,
                default_failure_states[check_id],
            )
        )
    frozen_checks = tuple(checks)
    return VerificationResult(classify_state(frozen_checks), frozen_checks)


class _Parser(argparse.ArgumentParser):
    # Pylance versions disagree on argparse.ArgumentParser.error's Never return.
    # The implementation always raises and therefore never returns at runtime.
    def error(self, message: str) -> NoReturn:  # type: ignore[override]
        del message
        raise ValueError("invalid-arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(add_help=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def _human_summary(result: VerificationResult) -> str:
    failures = [
        f"{check.check_id}:{check.reason_code}"
        for check in result.checks
        if not check.passed
    ]
    suffix = ", ".join(failures) if failures else "all checks passed"
    return f"HVE bootstrap verification: {result.state.value} ({suffix})"


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(list(argv) if argv is not None else None)
    except (ValueError, SystemExit):
        return 2

    root = Path(args.root)
    result = verify_distribution(root)
    manifest_failure = next(
        (
            check
            for check in result.checks
            if check.check_id == "manifest"
            and not check.passed
            and check.reason_code in _MANIFEST_SCHEMA_ERROR_REASONS
        ),
        None,
    )
    exit_code = 2 if manifest_failure is not None else result.exit_code
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, separators=(",", ":")))
    else:
        print(_human_summary(result))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
