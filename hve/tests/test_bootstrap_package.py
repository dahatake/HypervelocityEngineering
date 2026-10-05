"""FR-LOCAL-SURFACE-04: private source ZIP generator contract。"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
from pathlib import Path
import stat
import subprocess
import types
import unicodedata
import zipfile

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _ROOT / ".github" / "scripts" / "build-hve-bootstrap.py"
_SOURCE_FILES = (
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "hve.cmd",
    "hve.sh",
    "mdq.toml",
    "cq.toml",
    ".gitattributes",
    ".gitignore",
    "hve/__init__.py",
    "hve/bootstrap_verify.py",
    "hve/setup-hve.ps1",
    "hve/setup-hve.sh",
    "hve/bootstrap/Start-HVE.cmd.in",
    "hve/bootstrap/Start-HVE.ps1",
    "hve/bootstrap/Start-HVE.command.in",
    "hve/bootstrap/windows-pwsh-runtime-check.ps1",
    "hve/bootstrap/winget-module-inspect.ps1",
    "hve/bootstrap/bootstrap-sources.json",
    "hve/startup_version.py",
    "hve/auth.py",
    "hve/gui/copilot_cli_bridge.py",
    "hve/gui/pty_backend.py",
)
_FORBIDDEN_PREFIXES = (
    ".git/",
    ".venv/",
    "work/",
    "gui-logs/",
    ".mdq/",
    ".cq/",
    ".toolsearch/",
    "docs/",
    "docs-generated/",
    "docs-original/",
    "knowledge/",
    "qa/",
    "src/",
    "sample/",
    "tests/",
)
_EXPECTED_ROOT_FILES = {
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "hve.cmd",
    "hve.sh",
    "mdq.toml",
    "cq.toml",
    ".gitattributes",
    ".gitignore",
}
_EXPECTED_INCLUDE_PREFIXES = {
    "hve/",
    "mdq/",
    "cq/",
    "tools/",
    "template/",
    "users-guide/",
    ".github/instructions/",
    ".github/prompts/",
    ".github/skills/",
    ".github/io-contracts/",
    ".github/scripts/",
}
_EXPECTED_INCLUDE_EXACT = {
    ".github/copilot-instructions.md",
    ".github/io-contract-exceptions.yaml",
    ".github/pull_request_template.md",
    ".github/labels.json",
    "hve-dev/requirement-definition.md",
    "hve-dev/requirement-definition-history.md",
    "hve-dev/requirement-test-mapping.md",
    "hve-dev/hve-feature-inventory.csv",
    "hve-dev/hve-test-inventory.csv",
    "hve-dev/hve-surface-inventory.csv",
    "hve-dev/hve-app-tools.md",
    "hve-dev/hve-tdd-change-policy.md",
}
_EXPECTED_EXCLUDE_PREFIXES = set(_FORBIDDEN_PREFIXES) | {
    "hve/tests/",
    "hve/gui/tests/",
    "mdq/tests/",
    "cq/tests/",
    "hve.egg-info/",
    "node_modules/",
    "__pycache__/",
    ".vscode/",
    ".github/workflows/",
    ".github/ISSUE_TEMPLATE/",
}
_EXPECTED_EXCLUDE_EXACT = {"hve/.settings.txt", "hve/.settings.txt.tmp"}
_EXPECTED_EXCLUDE_BASENAMES = {
    ".env",
    "credentials.json",
    "secrets.json",
    ".npmrc",
    ".pypirc",
    "conftest.py",
}
_EXPECTED_EXCLUDE_SUFFIXES = {
    ".pem",
    ".key",
    ".pfx",
    ".p12",
    ".jks",
    ".keystore",
    ".pyc",
}
_SYNTHETIC_ALLOWED = {
    "mdq/allowed.py": b"allowed\n",
    "cq/allowed.py": b"allowed\n",
    "tools/allowed.py": b"allowed\n",
    "template/allowed.txt": b"allowed\n",
    "users-guide/allowed.md": b"allowed\n",
    ".github/instructions/allowed.md": b"allowed\n",
    ".github/prompts/allowed.md": b"allowed\n",
    ".github/skills/allowed.md": b"allowed\n",
    ".github/io-contracts/allowed.yaml": b"allowed: true\n",
    ".github/scripts/allowed.py": b"allowed\n",
    **{path: b"allowed\n" for path in _EXPECTED_INCLUDE_EXACT},
}
_SYNTHETIC_EXCLUDED = {
    "docs/private.md": b"excluded\n",
    "tests/test_root.py": b"excluded\n",
    "hve/tests/test_internal.py": b"excluded\n",
    "tools/example/test_helper.py": b"excluded\n",
    ".github/scripts/python/tests/test_helper.py": b"excluded\n",
    ".github/workflows/deploy-app.yml": b"excluded\n",
    ".github/ISSUE_TEMPLATE/app.yml": b"excluded\n",
    "hve/.settings.txt": b"excluded\n",
    "hve/credentials.json": b"excluded\n",
    "hve/private.key": b"excluded\n",
    "unknown-root.txt": b"unknown\n",
}
_EXPECTED_SNAPSHOT_PATHS = set(_SOURCE_FILES) | set(_SYNTHETIC_ALLOWED)
_EXPECTED_COMMON_CRITICAL = {
    "hve-bootstrap-manifest.json",
    "pyproject.toml",
    "hve/__init__.py",
    "hve/bootstrap_verify.py",
    "hve/startup_version.py",
    "hve/auth.py",
    "hve/gui/copilot_cli_bridge.py",
    "hve/gui/pty_backend.py",
    "hve/bootstrap/bootstrap-sources.json",
}
_EXPECTED_CRITICAL_BY_TARGET = {
    "windows-x64": _EXPECTED_COMMON_CRITICAL
    | {
        "hve/setup-hve.ps1",
        "Start-HVE.ps1",
        "hve/bootstrap/windows-pwsh-runtime-check.ps1",
        "hve/bootstrap/winget-module-inspect.ps1",
    },
    "macos-arm64": _EXPECTED_COMMON_CRITICAL | {"hve/setup-hve.sh"},
}


def _load_generator() -> types.ModuleType:
    assert _GENERATOR.is_file(), f"required generator is missing: {_GENERATOR}"
    spec = importlib.util.spec_from_file_location("build_hve_bootstrap", _GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=check,
    )


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "--object-format=sha1")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.autocrlf", "false")
    hooks = repo / ".empty-hooks"
    hooks.mkdir()
    _git(repo, "config", "core.hooksPath", str(hooks))
    for relative in _SOURCE_FILES:
        source = _ROOT / relative
        assert source.is_file(), f"required source fixture is missing: {relative}"
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    _git(repo, "add", "--", *_SOURCE_FILES)
    for relative, data in {**_SYNTHETIC_ALLOWED, **_SYNTHETIC_EXCLUDED}.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # The fixture intentionally stages ignored paths so the generator can verify
    # exclusion rules against the index; this must override the copied root
    # .gitignore rather than fail before the generator is exercised.
    _git(repo, "add", "-f", "--", *_SYNTHETIC_ALLOWED, *_SYNTHETIC_EXCLUDED)
    _git(repo, "commit", "-qm", "fixture")
    return repo


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_text(path: Path) -> str:
    assert path.is_file(), f"required source is missing: {path}"
    return path.read_text(encoding="utf-8")


def test_generator_policy_constants_match_the_design_boundary() -> None:
    module = _load_generator()
    assert set(module.ROOT_FILES) == _EXPECTED_ROOT_FILES
    assert set(module.INCLUDE_PREFIXES) == _EXPECTED_INCLUDE_PREFIXES
    assert set(module.INCLUDE_EXACT) == _EXPECTED_INCLUDE_EXACT
    assert set(module.EXCLUDE_PREFIXES) == _EXPECTED_EXCLUDE_PREFIXES
    assert set(module.EXCLUDE_EXACT) == _EXPECTED_EXCLUDE_EXACT
    assert set(module.EXCLUDE_BASENAMES) == _EXPECTED_EXCLUDE_BASENAMES
    assert tuple(module.EXCLUDE_BASENAME_PREFIXES) == ("test_",)
    assert set(module.EXCLUDE_SUFFIXES) == _EXPECTED_EXCLUDE_SUFFIXES
    assert module.GENERATED_EXACT_BY_TARGET == {
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
    assert {
        target: set(paths) for target, paths in module.CRITICAL_PATHS_BY_TARGET.items()
    } == _EXPECTED_CRITICAL_BY_TARGET


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        *((path, True) for path in sorted(_EXPECTED_ROOT_FILES)),
        *((path, True) for path in sorted(_EXPECTED_INCLUDE_EXACT)),
        *((prefix + "sample.txt", True) for prefix in sorted(_EXPECTED_INCLUDE_PREFIXES)),
        *((prefix + "sample.txt", False) for prefix in sorted(_EXPECTED_EXCLUDE_PREFIXES)),
        *((path, False) for path in sorted(_EXPECTED_EXCLUDE_EXACT)),
        *(("hve/" + name, False) for name in sorted(_EXPECTED_EXCLUDE_BASENAMES)),
        *(("hve/private" + suffix, False) for suffix in sorted(_EXPECTED_EXCLUDE_SUFFIXES)),
        ("tools/sample/test_helper.py", False),
        ("tools/sample/test_data.json", True),
        ("unknown-root.txt", False),
    ],
)
def test_is_allowed_applies_every_policy_rule(path: str, expected: bool) -> None:
    module = _load_generator()
    assert module.is_allowed(path) is expected


def test_collect_source_entries_uses_index_blob_not_working_tree(tmp_path: Path) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    staged = (repo / "README.md").read_bytes()
    (repo / "README.md").write_bytes(b"working tree changed\n")

    snapshot = module.collect_source_snapshot(repo)
    readme = next(item for item in snapshot.entries if item.path == "README.md")

    assert readme.data == staged
    assert readme.data != (repo / "README.md").read_bytes()
    assert readme.mode == 0o100644
    assert re_full_oid(readme.oid)
    assert snapshot.source_dirty is True
    assert {item.path for item in snapshot.entries} == _EXPECTED_SNAPSHOT_PATHS
    assert not any(item.path.startswith(_FORBIDDEN_PREFIXES) for item in snapshot.entries)
    assert not any(item.path == "unknown-root.txt" for item in snapshot.entries)


def re_full_oid(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def test_allowed_untracked_file_fails_closed(tmp_path: Path) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    path = repo / "hve" / "unreviewed.py"
    path.write_text("print('not reviewed')\n", encoding="utf-8")

    with pytest.raises(module.DistributionError, match="untracked-allowed-file"):
        module.collect_source_snapshot(repo)

    excluded = repo / "docs" / "untracked.md"
    excluded.parent.mkdir(exist_ok=True)
    excluded.write_text("excluded\n", encoding="utf-8")
    path.unlink()
    module.collect_source_snapshot(repo)


def test_actual_index_gitlink_is_rejected(tmp_path: Path) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    oid = _git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{oid},hve/submodule")
    with pytest.raises(module.DistributionError, match="unsupported-index-mode"):
        module.collect_source_snapshot(repo)


def test_actual_unmerged_index_stage_is_rejected(tmp_path: Path) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    oid = _git(repo, "rev-parse", "HEAD:README.md").stdout.decode().strip()
    index_info = (
        f"100644 {oid} 1\thve/conflict.py\n"
        f"100644 {oid} 2\thve/conflict.py\n"
    ).encode("ascii")
    subprocess.run(
        ["git", "update-index", "--index-info"],
        cwd=repo,
        input=index_info,
        check=True,
    )
    with pytest.raises(module.DistributionError, match="unsupported-index-stage"):
        module.collect_source_snapshot(repo)


def test_index_mode_symlink_lfs_secret_zero_and_collisions_are_rejected() -> None:
    module = _load_generator()
    entry = module.SourceEntry
    valid = entry("hve/app.py", 0o100644, "a" * 40, b"print('ok')\n")

    bad_cases = [
        ([entry("hve/link", 0o120000, "b" * 40, b"target")], "unsupported-index-mode"),
        ([entry("hve/model.bin", 0o100644, "b" * 40, b"version https://git-lfs.github.com/spec/v1\n")], "git-lfs-pointer"),
        ([entry("hve/secret.txt", 0o100644, "b" * 40, b"github_pat_example")], "secret-signature"),
        ([entry("hve/empty.py", 0o100644, "b" * 40, b"")], "unexpected-empty-file"),
        ([valid, entry("HVE/app.py", 0o100644, "b" * 40, b"other")], "case-collision"),
        (
            [
                entry("hve/café.py", 0o100644, "b" * 40, b"one"),
                entry(
                    unicodedata.normalize("NFD", "hve/café.py"),
                    0o100644,
                    "c" * 40,
                    b"two",
                ),
            ],
            "unicode-collision",
        ),
        ([valid, entry("hve/../escape.py", 0o100644, "b" * 40, b"bad")], "unsafe-path"),
    ]
    for entries, reason in bad_cases:
        with pytest.raises(module.DistributionError, match=reason):
            module.validate_source_entries(entries)

    marker = entry("hve/pkg/__init__.py", 0o100644, "c" * 40, b"")
    module.validate_source_entries([marker])


@pytest.mark.parametrize(
    ("payload", "signature_id", "not_secret"),
    [
        (b"ghp_supersecret", "github-token", b"ghx_not-a-token"),
        (b"github_pat_supersecret", "github-token", b"github_path_value"),
        (b"-----BEGIN PRIVATE KEY-----\nsuper-secret", "private-key", b"-----BEGIN PUBLIC KEY-----"),
        (b"-----BEGIN RSA PRIVATE KEY-----\nsuper-secret", "private-key", b"RSA PRIVATE VALUE"),
        (b"-----BEGIN EC PRIVATE KEY-----\nsuper-secret", "private-key", b"EC PUBLIC KEY"),
        (b"-----BEGIN OPENSSH PRIVATE KEY-----\nsuper-secret", "private-key", b"OPENSSH PUBLIC KEY"),
        (
            b"DefaultEndpointsProtocol=https;AccountKey=super-secret",
            "azure-storage-connection-string",
            b"DefaultEndpointsProtocol=https;AccountName=public",
        ),
        (
            b"AccountKey=super-secret;DefaultEndpointsProtocol=https",
            "azure-storage-connection-string",
            b"AccountKeyName=public",
        ),
    ],
)
def test_secret_signatures_are_complete_redacted_and_avoid_near_misses(
    payload: bytes, signature_id: str, not_secret: bytes
) -> None:
    module = _load_generator()
    entry = module.SourceEntry("hve/key.txt", 0o100644, "a" * 40, payload)
    with pytest.raises(module.DistributionError) as captured:
        module.validate_source_entries([entry])
    message = str(captured.value)
    assert "secret-signature" in message
    assert signature_id in message
    assert "hve/key.txt" in message
    assert "super-secret" not in message
    assert payload.decode("utf-8", errors="ignore") not in message

    safe = module.SourceEntry("hve/public.txt", 0o100644, "b" * 40, not_secret)
    module.validate_source_entries([safe])


@pytest.mark.parametrize(
    "payload",
    [
        b"DefaultEndpointsProtocol=https",
        b"AccountKey=not-enough-alone",
        b"github_path_not_token",
        b"-----BEGIN PUBLIC KEY-----",
    ],
)
def test_secret_near_misses_are_not_rejected(payload: bytes) -> None:
    module = _load_generator()
    module.validate_source_entries(
        [module.SourceEntry("hve/public.txt", 0o100644, "a" * 40, payload)]
    )


def test_invalid_entry_after_valid_entry_is_not_skipped() -> None:
    module = _load_generator()
    entries = [
        module.SourceEntry("hve/valid.py", 0o100644, "a" * 40, b"valid\n"),
        module.SourceEntry(
            "hve/later.bin",
            0o100644,
            "b" * 40,
            b"version https://git-lfs.github.com/spec/v1\n",
        ),
    ]
    with pytest.raises(module.DistributionError, match="git-lfs-pointer"):
        module.validate_source_entries(entries)


def test_build_is_deterministic_and_target_specific(tmp_path: Path) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    first = module.build_distribution(repo, "windows-x64", tmp_path / "out-a")
    second = module.build_distribution(repo, "windows-x64", tmp_path / "out-b")
    macos = module.build_distribution(repo, "macos-arm64", tmp_path / "out-c")

    assert _sha256(first.zip_path) == _sha256(second.zip_path)
    assert first.archive_sha256 == _sha256(first.zip_path)
    assert first.digest_path.read_text(encoding="ascii").strip() == first.archive_sha256

    with zipfile.ZipFile(first.zip_path) as archive:
        windows_names = archive.namelist()
    with zipfile.ZipFile(macos.zip_path) as archive:
        macos_names = archive.namelist()

    assert windows_names == sorted(windows_names)
    assert macos_names == sorted(macos_names)
    assert "Start-HVE.cmd" in windows_names and "Start-HVE.ps1" in windows_names
    assert "Start-HVE.command" not in windows_names
    assert "Start-HVE.command" in macos_names
    assert "Start-HVE.cmd" not in macos_names and "Start-HVE.ps1" not in macos_names


def test_formal_build_rejects_dirty_but_local_build_records_index_payload(
    tmp_path: Path,
) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    indexed = b"staged source bytes\n"
    (repo / "README.md").write_bytes(indexed)
    _git(repo, "add", "README.md")

    with pytest.raises(module.DistributionError, match="dirty-source"):
        module.build_distribution(repo, "windows-x64", tmp_path / "formal")

    result = module.build_distribution(
        repo, "windows-x64", tmp_path / "local", formal=False
    )
    with zipfile.ZipFile(result.zip_path) as archive:
        manifest = json.loads(archive.read("hve-bootstrap-manifest.json"))
        assert archive.read("README.md") == indexed
    assert manifest["source_dirty"] is True


def test_build_rejects_index_change_between_scans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    original = module.scan_index
    calls = 0

    def changing_scan(root: Path):
        nonlocal calls
        calls += 1
        result = list(original(root))
        if calls == 2:
            item = result[-1]
            result[-1] = module.IndexEntry(item.mode, "f" * 40, item.stage, item.path)
        return tuple(result)

    monkeypatch.setattr(module, "scan_index", changing_scan)
    with pytest.raises(module.DistributionError, match="index-changed"):
        module.build_distribution(repo, "windows-x64", tmp_path / "out")
    assert calls == 2


def test_archive_manifest_modes_and_exclusions_are_safe(tmp_path: Path) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    result = module.build_distribution(repo, "macos-arm64", tmp_path / "out")

    with zipfile.ZipFile(result.zip_path) as archive:
        info_list = archive.infolist()
        infos = {item.filename: item for item in info_list}
        names = set(infos)
        manifest = json.loads(archive.read("hve-bootstrap-manifest.json"))
        critical = archive.read("hve-bootstrap-critical.sha256")
        assert len(info_list) == len(infos)
        assert set(manifest["files"]) == _EXPECTED_SNAPSHOT_PATHS
        expected_names = _EXPECTED_SNAPSHOT_PATHS | set(
            module.GENERATED_EXACT_BY_TARGET["macos-arm64"]
        )
        assert names == expected_names
        assert not any(name.startswith(_FORBIDDEN_PREFIXES) for name in names)
        assert not any(name.startswith("/") or ".." in Path(name).parts for name in names)
        assert set(manifest) == {
            "schema_version",
            "distribution_kind",
            "hve_version",
            "source_commit",
            "source_dirty",
            "target_platform",
            "launcher",
            "files",
        }
        assert manifest["schema_version"] == 1
        assert manifest["distribution_kind"] == "hve-private-source"
        assert manifest["target_platform"] == "macos-arm64"
        assert manifest["launcher"] == "Start-HVE.command"
        assert manifest["source_commit"] == _git(repo, "rev-parse", "HEAD").stdout.decode().strip()
        assert manifest["source_dirty"] is False
        assert manifest["files"]
        assert "hve-bootstrap-manifest.json" not in manifest["files"]
        assert "Start-HVE.command" not in manifest["files"]

        critical_lines = critical.decode("ascii").splitlines()
        critical_entries = {
            name: digest
            for line in critical_lines
            for digest, name in [line.split("  ", 1)]
        }
        assert critical_entries
        assert set(critical_entries) == _EXPECTED_CRITICAL_BY_TARGET["macos-arm64"]
        for name, digest in critical_entries.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        assert "hve-bootstrap-critical.sha256" not in critical_entries
        assert "Start-HVE.command" not in critical_entries
        assert hashlib.sha256(critical).hexdigest().encode("ascii") in archive.read(
            "Start-HVE.command"
        )

        for name in ("Start-HVE.command", "hve.sh", "hve/setup-hve.sh"):
            mode = infos[name].external_attr >> 16
            assert stat.S_IMODE(mode) == 0o755
            data = archive.read(name)
            assert data and not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data

        for info in info_list:
            assert info.date_time == module.ZIP_TIMESTAMP
            assert info.compress_type == zipfile.ZIP_DEFLATED
            assert info.create_system == 3
            assert stat.S_IMODE(info.external_attr >> 16) in {0o644, 0o755}
        for name in ("hve-bootstrap-manifest.json", "hve-bootstrap-critical.sha256"):
            data = archive.read(name)
            assert data and not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data


def test_manifest_hashes_match_archive_source_payload(tmp_path: Path) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    result = module.build_distribution(repo, "windows-x64", tmp_path / "out")
    with zipfile.ZipFile(result.zip_path) as archive:
        manifest = json.loads(archive.read("hve-bootstrap-manifest.json"))
        for name, digest in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest


def test_windows_generated_text_formats_and_modes_are_fixed(tmp_path: Path) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    result = module.build_distribution(repo, "windows-x64", tmp_path / "out")
    with zipfile.ZipFile(result.zip_path) as archive:
        cmd = archive.read("Start-HVE.cmd")
        ps1 = archive.read("Start-HVE.ps1")
        manifest = archive.read("hve-bootstrap-manifest.json")
        critical = archive.read("hve-bootstrap-critical.sha256")
        infos = {item.filename: item for item in archive.infolist()}
    assert cmd and b"\r\n" in cmd and not cmd.startswith(b"\xef\xbb\xbf")
    assert ps1 and b"\r\n" not in ps1 and not ps1.startswith(b"\xef\xbb\xbf")
    assert manifest and b"\r\n" not in manifest and not manifest.startswith(b"\xef\xbb\xbf")
    assert critical and b"\r\n" not in critical and not critical.startswith(b"\xef\xbb\xbf")
    assert stat.S_IMODE(infos["Start-HVE.cmd"].external_attr >> 16) == 0o644
    assert stat.S_IMODE(infos["Start-HVE.ps1"].external_attr >> 16) == 0o644


def test_zip_changes_with_index_blob_and_returns_after_restore(tmp_path: Path) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    original = module.build_distribution(repo, "windows-x64", tmp_path / "a")
    original_sha = _sha256(original.zip_path)
    readme = repo / "README.md"
    original_bytes = readme.read_bytes()

    readme.write_bytes(b"new indexed bytes\n")
    _git(repo, "add", "README.md")
    with pytest.raises(module.DistributionError, match="dirty-source"):
        module.build_distribution(repo, "windows-x64", tmp_path / "formal-b")
    changed = module.build_distribution(
        repo, "windows-x64", tmp_path / "b", formal=False
    )
    assert _sha256(changed.zip_path) != original_sha

    readme.write_bytes(original_bytes)
    _git(repo, "add", "README.md")
    restored = module.build_distribution(repo, "windows-x64", tmp_path / "c")
    assert _sha256(restored.zip_path) == original_sha


def test_build_performs_only_local_git_subprocesses_and_no_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    module = _load_generator()
    repo = _make_repo(tmp_path)
    real_run = module.subprocess.run
    commands: list[tuple[str, ...]] = []

    def audited_run(argv: list[str], **kwargs: object):
        commands.append(tuple(argv))
        assert argv[0] == "git"
        assert len(argv) >= 2 and argv[1] in {"ls-files", "cat-file", "rev-parse", "diff"}
        assert kwargs.get("shell") is False
        assert Path(str(kwargs.get("cwd"))).resolve() == repo.resolve()
        assert not any("://" in token or token.startswith("git@") for token in argv)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", audited_run)
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("network"))

    result = module.build_distribution(repo, "windows-x64", tmp_path / "out")
    cli_exit = module.main(
        [
            "--repo-root",
            str(repo),
            "--target",
            "windows-x64",
            "--output-dir",
            str(tmp_path / "cli-out"),
        ]
    )

    assert result.zip_path.is_file()
    assert cli_exit == 0
    assert "https://" not in capsys.readouterr().out
    assert commands
