"""Build deterministic private HVE source distributions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tomllib
import unicodedata
import zipfile
from typing import NamedTuple

ROOT_FILES = (
    "LICENSE", "README.md", "CHANGELOG.md", "pyproject.toml", "hve.cmd",
    "hve.sh", "mdq.toml", "cq.toml", ".gitattributes", ".gitignore",
)
INCLUDE_PREFIXES = (
    "hve/", "mdq/", "cq/", "tools/", "template/", "users-guide/",
    ".github/instructions/", ".github/prompts/", ".github/skills/",
    ".github/io-contracts/", ".github/scripts/",
)
INCLUDE_EXACT = (
    ".github/copilot-instructions.md", ".github/io-contract-exceptions.yaml",
    ".github/pull_request_template.md", ".github/labels.json",
    "hve-dev/requirement-definition.md", "hve-dev/requirement-definition-history.md",
    "hve-dev/requirement-test-mapping.md",
    "hve-dev/hve-feature-inventory.csv", "hve-dev/hve-test-inventory.csv",
    "hve-dev/hve-surface-inventory.csv", "hve-dev/hve-app-tools.md",
    "hve-dev/hve-tdd-change-policy.md",
)
EXCLUDE_PREFIXES = (
    ".git/", ".venv/", "work/", "gui-logs/", ".mdq/", ".cq/", ".toolsearch/",
    "docs/", "docs-generated/", "docs-original/", "knowledge/", "qa/", "src/",
    "sample/", "tests/", "hve/tests/", "hve/gui/tests/", "mdq/tests/", "cq/tests/",
    "hve.egg-info/", "node_modules/", "__pycache__/", ".vscode/",
    ".github/workflows/", ".github/ISSUE_TEMPLATE/",
)
EXCLUDE_EXACT = ("hve/.settings.txt", "hve/.settings.txt.tmp")
EXCLUDE_BASENAMES = (".env", "credentials.json", "secrets.json", ".npmrc", ".pypirc", "conftest.py")
EXCLUDE_BASENAME_PREFIXES = ("test_",)
EXCLUDE_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".jks", ".keystore", ".pyc")
GENERATED_EXACT_BY_TARGET = {
    "windows-x64": ("Start-HVE.cmd", "Start-HVE.ps1", "hve-bootstrap-critical.sha256", "hve-bootstrap-manifest.json"),
    "macos-arm64": ("Start-HVE.command", "hve-bootstrap-critical.sha256", "hve-bootstrap-manifest.json"),
}
_LAUNCHER_BY_TARGET = {
    "windows-x64": "Start-HVE.cmd",
    "macos-arm64": "Start-HVE.command",
}
CRITICAL_PATHS_BY_TARGET = {
    "windows-x64": (
        "hve-bootstrap-manifest.json", "pyproject.toml", "hve/__init__.py", "hve/bootstrap_verify.py",
        "hve/startup_version.py", "hve/auth.py", "hve/gui/copilot_cli_bridge.py", "hve/gui/pty_backend.py",
        "hve/bootstrap/bootstrap-sources.json", "hve/setup-hve.ps1", "Start-HVE.ps1",
        "hve/bootstrap/windows-pwsh-runtime-check.ps1", "hve/bootstrap/winget-module-inspect.ps1",
    ),
    "macos-arm64": (
        "hve-bootstrap-manifest.json", "pyproject.toml", "hve/__init__.py", "hve/bootstrap_verify.py",
        "hve/startup_version.py", "hve/auth.py", "hve/gui/copilot_cli_bridge.py", "hve/gui/pty_backend.py",
        "hve/bootstrap/bootstrap-sources.json", "hve/setup-hve.sh",
    ),
}
ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
_SHA = re.compile(r"^[0-9a-f]{64}$")


class DistributionError(RuntimeError):
    pass


class IndexEntry(NamedTuple):
    mode: int
    oid: str
    stage: int
    path: str


class SourceEntry(NamedTuple):
    path: str
    mode: int
    oid: str
    data: bytes


class SourceSnapshot(NamedTuple):
    entries: tuple[SourceEntry, ...]
    source_dirty: bool


class BuildResult(NamedTuple):
    zip_path: Path
    digest_path: Path
    archive_sha256: str


def _run_git(root: Path, args: list[str], *, input_data: bytes | None = None) -> bytes:
    if not args or args[0] not in {"ls-files", "cat-file", "rev-parse", "diff"}:
        raise DistributionError("unsupported-git-subcommand")
    result = subprocess.run(
        ["git", *args], cwd=str(root), input=input_data, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, shell=False,
    )
    if result.returncode:
        raise DistributionError(f"git-{args[0]}-failed")
    return result.stdout


def _normal(path: str) -> str:
    if not path or "\\" in path or path.startswith("/") or "//" in path:
        raise DistributionError("unsafe-path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise DistributionError("unsafe-path")
    return str(pure)


def is_allowed(path: str) -> bool:
    try:
        path = _normal(path)
    except DistributionError:
        return False
    nested_excluded = (
        "/tests/" in path or "/results/" in path or "/__pycache__/" in path
    ) and (path.startswith("tools/") or path.startswith(".github/scripts/"))
    if path in EXCLUDE_EXACT or nested_excluded or any(path.startswith(p) for p in EXCLUDE_PREFIXES):
        return False
    name = path.rsplit("/", 1)[-1]
    if name in EXCLUDE_BASENAMES or any(name.startswith(p) for p in EXCLUDE_BASENAME_PREFIXES):
        if name.startswith("test_") and not name.endswith(".json"):
            return False
        if name in EXCLUDE_BASENAMES:
            return False
    if any(path.endswith(s) for s in EXCLUDE_SUFFIXES):
        return False
    return path in ROOT_FILES or path in INCLUDE_EXACT or any(path.startswith(p) for p in INCLUDE_PREFIXES)


def _scan_index(root: Path) -> tuple[IndexEntry, ...]:
    raw = _run_git(root, ["ls-files", "-s", "-z", "--cached"])
    entries: list[IndexEntry] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        head, path_bytes = record.split(b"\t", 1)
        mode_text, oid, stage_text = head.decode("ascii").split()
        entries.append(IndexEntry(int(mode_text, 8), oid, int(stage_text), _normal(path_bytes.decode("utf-8"))))
    return tuple(sorted(entries, key=lambda x: x.path))


def scan_index(root: Path) -> tuple[IndexEntry, ...]:
    return _scan_index(root)


def _working_dirty(root: Path) -> bool:
    for args in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        result = subprocess.run(["git", *args], cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, shell=False)
        if result.returncode not in (0, 1):
            raise DistributionError("git-diff-failed")
        if result.returncode == 1:
            return True
    return False


def _validate_bytes(entries: tuple[SourceEntry, ...]) -> None:
    normalized: dict[str, tuple[str, str]] = {}
    for entry in entries:
        if entry.mode not in (0o100644, 0o100755):
            raise DistributionError("unsupported-index-mode")
        if entry.path != _normal(entry.path):
            raise DistributionError("unsafe-path")
        nfc_value = unicodedata.normalize("NFC", entry.path)
        nfc = nfc_value.casefold()
        if nfc in normalized:
            previous, previous_nfc = normalized[nfc]
            raise DistributionError(
                "unicode-collision" if previous != previous_nfc or entry.path != nfc_value else "case-collision"
            )
        normalized[nfc] = (entry.path, nfc_value)
        if entry.data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise DistributionError("git-lfs-pointer")
        if not entry.data and not entry.path.endswith("/__init__.py"):
            raise DistributionError("unexpected-empty-file")
        text = entry.data.decode("utf-8", errors="ignore")
        if re.search(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----", text):
            raise DistributionError(f"secret-signature:private-key:{entry.path}")
        if re.search(r"(?:ghp_|github_pat_)[A-Za-z0-9_]+", text):
            raise DistributionError(f"secret-signature:github-token:{entry.path}")
        if ("DefaultEndpointsProtocol=" in text and "AccountKey=" in text):
            raise DistributionError(f"secret-signature:azure-storage-connection-string:{entry.path}")


def validate_source_entries(entries: list[SourceEntry] | tuple[SourceEntry, ...]) -> None:
    """Validate an already materialized index snapshot (public test seam)."""
    _validate_bytes(tuple(entries))


def collect_source_snapshot(root: Path) -> SourceSnapshot:
    entries = _scan_index(root)
    untracked = _run_git(root, ["ls-files", "-z", "--others", "--exclude-standard"]).split(b"\0")
    if any(item and is_allowed(item.decode("utf-8")) for item in untracked):
        raise DistributionError("untracked-allowed-file")
    source: list[SourceEntry] = []
    for item in entries:
        if not is_allowed(item.path):
            continue
        if item.stage != 0:
            raise DistributionError("unsupported-index-stage")
        if item.mode not in (0o100644, 0o100755):
            raise DistributionError("unsupported-index-mode")
        data = _run_git(root, ["cat-file", "blob", item.oid])
        source.append(SourceEntry(item.path, item.mode, item.oid, data))
    result = SourceSnapshot(tuple(source), _working_dirty(root))
    _validate_bytes(result.entries)
    return result


def _version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    value = data["project"]["version"]
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise DistributionError("invalid-version")
    return value


def _render(template: bytes, target: str, critical: bytes) -> bytes:
    values = json.loads((Path(__file__).resolve().parents[2] / "hve/bootstrap/bootstrap-sources.json").read_text(encoding="utf-8"))
    if target == "windows-x64":
        replacements = {
            "{{CRITICAL_LIST_SHA256}}": hashlib.sha256(critical).hexdigest(),
            "{{POWERSHELL_VERSION}}": values["powershell"]["version"],
            "{{POWERSHELL_WINDOWS_X64_URL}}": values["powershell"]["windows_x64_url"],
            "{{POWERSHELL_WINDOWS_X64_SHA256}}": values["powershell"]["windows_x64_sha256"],
        }
    else:
        replacements = {
            "{{CRITICAL_LIST_SHA256}}": hashlib.sha256(critical).hexdigest(),
            "{{HOMEBREW_INSTALL_URL}}": values["homebrew"]["install_url"],
            "{{HOMEBREW_INSTALL_SHA256}}": values["homebrew"]["install_sha256"],
        }
    text = template.decode("utf-8")
    for token, value in replacements.items():
        text = text.replace(token, value)
    if "{{" in text or "}}" in text:
        raise DistributionError("unresolved-template")
    return text.encode("utf-8")


def _critical(source: dict[str, bytes], target: str) -> bytes:
    lines = []
    for path in CRITICAL_PATHS_BY_TARGET[target]:
        if path not in source:
            raise DistributionError(f"critical-missing:{path}")
        lines.append(f"{hashlib.sha256(source[path]).hexdigest()}  {path}\n")
    return "".join(lines).encode("ascii")


def _zip_bytes(files: dict[str, tuple[bytes, int]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            data, mode = files[name]
            info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IMODE(mode) << 16)
            archive.writestr(info, data)


def build_distribution(repo_root: Path, target: str, output_dir: Path, *, formal: bool = True) -> BuildResult:
    if target not in GENERATED_EXACT_BY_TARGET:
        raise DistributionError("unsupported-target")
    repo_root = Path(repo_root).resolve()
    initial_index = scan_index(repo_root)
    snapshot = collect_source_snapshot(repo_root)
    if scan_index(repo_root) != initial_index:
        raise DistributionError("index-changed")
    if formal and snapshot.source_dirty:
        raise DistributionError("dirty-source")
    source = {e.path: (e.data, e.mode) for e in snapshot.entries}
    for executable in ("hve.sh", "hve/setup-hve.sh"):
        if executable in source:
            source[executable] = (source[executable][0], 0o100755)
    source_names = set(source)
    manifest_files = {name: hashlib.sha256(data).hexdigest() for name, (data, _) in sorted(source.items())}
    commit = _run_git(repo_root, ["rev-parse", "HEAD"]).decode().strip()
    manifest = {
        "schema_version": 1, "distribution_kind": "hve-private-source", "hve_version": _version(Path(repo_root)),
        "source_commit": commit, "source_dirty": snapshot.source_dirty, "target_platform": target,
        "launcher": _LAUNCHER_BY_TARGET[target], "files": manifest_files,
    }
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    source["hve-bootstrap-manifest.json"] = (manifest_data, 0o100644)
    critical_source = {k: v[0] for k, v in source.items()}
    if target == "windows-x64":
        critical_source["Start-HVE.ps1"] = (
            (repo_root / "hve/bootstrap/Start-HVE.ps1")
            .read_text(encoding="utf-8")
            .replace("\r\n", "\n")
            .encode("utf-8")
        )
    critical = _critical(critical_source, target)
    source["hve-bootstrap-critical.sha256"] = (critical, 0o100644)
    if target == "windows-x64":
        source["Start-HVE.cmd"] = (_render((Path(repo_root) / "hve/bootstrap/Start-HVE.cmd.in").read_bytes(), target, critical), 0o100644)
        source["Start-HVE.ps1"] = (
            ((repo_root / "hve/bootstrap/Start-HVE.ps1").read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")),
            0o100644,
        )
    else:
        source["Start-HVE.command"] = (_render((Path(repo_root) / "hve/bootstrap/Start-HVE.command.in").read_bytes(), target, critical), 0o755)
    expected = set(source_names) | set(GENERATED_EXACT_BY_TARGET[target])
    if set(source) != expected:
        raise DistributionError("generated-set-mismatch")
    zip_path = Path(output_dir) / f"hve-{target}-{manifest['hve_version']}.zip"
    _zip_bytes(source, zip_path)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    digest_path = zip_path.with_suffix(zip_path.suffix + ".sha256")
    digest_path.write_text(digest + "\n", encoding="ascii", newline="\n")
    return BuildResult(zip_path, digest_path, digest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--target", choices=tuple(GENERATED_EXACT_BY_TARGET), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_distribution(args.repo_root, args.target, args.output_dir, formal=not args.local)
    except (DistributionError, OSError, ValueError) as exc:
        print(f"BUILD_FAIL reason={type(exc).__name__}", file=__import__("sys").stderr)
        return 1
    print(json.dumps({"zip": str(result.zip_path), "sha256": result.archive_sha256}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
