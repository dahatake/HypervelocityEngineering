from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parents[1]
SCRIPT = TOOL_DIR / "copy_hve.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_copy_hve", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


copy_hve = _load_module()


def _write(root: Path, relative: str, content: str = "content\n") -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def _file_hashes(root: Path, *, exclude_git: bool = False) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if exclude_git and relative.parts[0].casefold() == ".git":
            continue
        hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _file_paths(root: Path, *, exclude_git: bool = False) -> set[str]:
    paths: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if exclude_git and relative.parts[0].casefold() == ".git":
            continue
        paths.add(relative.as_posix())
    return paths


def _fake_source(tmp_path: Path, *, complete: bool = True) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)

    scope = '''\
def is_out_of_scope(path):
    return (
        path.startswith(("src/", "docs/", "work/"))
        or path.startswith(".github/workflows/deploy-")
    )


def is_in_scope(path):
    return (
        path.startswith(("hve/", "mdq/", "cq/", "template/", "tools/", ".github/scripts/"))
        or path in {
            ".github/copilot-instructions.md",
            "pyproject.toml",
            "hve.cmd",
            "hve.sh",
        }
    )
'''
    _write(root, ".github/scripts/hve_scope.py", scope)

    required = {
        ".github/copilot-instructions.md": "instructions\n",
        ".gitattributes": "* text=auto\n",
        ".gitignore": ".venv/\n",
        "CHANGELOG.md": "# Changelog\n",
        "LICENSE": "test license\n",
        "README.md": "# HVE\n",
        "cq/__init__.py": "",
        "hve.cmd": "@echo off\n",
        "hve.sh": "#!/usr/bin/env bash\n",
        "hve/__init__.py": "__version__ = '1.0.0'\n",
        "hve/setup-hve.ps1": "# setup\n",
        "hve/setup-hve.sh": "#!/usr/bin/env bash\n",
        "mdq/__init__.py": "",
        "pyproject.toml": "[project]\nname = 'hve'\nversion = '1.0.0'\n",
    }
    if not complete:
        required.pop("hve.sh")
    for relative, content in required.items():
        _write(root, relative, content)

    included = {
        ".github/.mcp.json": "{}\n",
        ".github/io-contract-exceptions.yaml": "exceptions: []\n",
        ".github/prompts/example.prompt.md": "# Prompt\n",
        ".github/workflows/hve-ci.yml": "name: hve\n",
        ".vscode/settings.json": "{}\n",
        "hve/module.py": "VALUE = 1\n",
        "template/sample.md": "# Template\n",
        "tests/[gui]SystemTest - Full.txt": "# GUI system test\n",
        "tests/prompt-version/01-request-contract.md": "# Request contract\n",
        "tools/for-other-repo/README.md": "# Kits\n",
        "tools/skills/_kit/kit_sync.py": "VALUE = 1\n",
        "users-guide/hve-cli-getting-started.md": "# Guide\n",
    }
    for relative, content in included.items():
        _write(root, relative, content)

    excluded = {
        ".github/workflows/deploy-generated.yml": "name: generated\n",
        "docs/business-requirement.md": "# Generated app document\n",
        "local-llm-dev/app.py": "VALUE = 1\n",
        "src/app.py": "VALUE = 1\n",
        "tests/run/generated-report.md": "# Generated app test run\n",
        "tools/copy-hve-other-repo/private.txt": "do not copy the copier\n",
        "work/run/log.txt": "generated\n",
    }
    for relative, content in excluded.items():
        _write(root, relative, content)
    return root


def test_repository_selection_uses_hve_boundary_and_support_files() -> None:
    paths = {
        path.as_posix() for path in copy_hve.collect_source_files(REPO_ROOT)
    }

    required = {
        ".github/.mcp.json",
        ".github/copilot-instructions.md",
        ".github/scripts/hve_scope.py",
        ".gitattributes",
        ".gitignore",
        "CHANGELOG.md",
        "LICENSE",
        "README.md",
        "cq/__init__.py",
        "hve.cmd",
        "hve.sh",
        "hve/__init__.py",
        "hve/setup-hve.ps1",
        "hve/setup-hve.sh",
        "mdq/__init__.py",
        "pyproject.toml",
        "users-guide/hve-cli-getting-started.md",
    }
    assert required <= paths
    assert any(path.startswith(".github/prompts/") for path in paths)
    assert any(path.startswith("template/") for path in paths)
    assert not any(
        path == prefix or path.startswith(f"{prefix}/")
        for path in paths
        for prefix in (
            ".git",
            "docs",
            "docs-generated",
            "knowledge",
            "local-llm-dev",
            "qa",
            "sample",
            "src",
            "tools/copy-hve-other-repo",
            "work",
        )
    )
    assert not any(
        path.startswith(".github/workflows/deploy-") for path in paths
    )


def test_repository_selection_includes_fixtures_required_by_copied_tests() -> None:
    """コピー済み `hve/tests/**` が実在を assert する `tests/` 資産も同時に運ぶ。"""
    paths = {path.as_posix() for path in copy_hve.collect_source_files(REPO_ROOT)}

    referenced = {
        # hve/tests/test_systemtest_screenshot_prompt_contract.py
        "tests/[cli]SystemTest - Full.txt",
        "tests/[gui]SystemTest - Full.txt",
        "tests/prompt-version/09-full-system-test.md",
        # hve/tests/test_prompt_edition_docs_contract.py
        "tests/prompt-version/README.md",
        "tests/prompt-version/02-plan-and-approval-gate.md",
        "tests/prompt-version/06-agent-skill-behavior.md",
        "tests/prompt-version/08-e2e-smoke.md",
        # hve/tests/test_prompt_request_integration_contract.py
        "tests/prompt-version/01-request-contract.md",
    }
    assert referenced <= paths

    documents = {
        document.relative_to(REPO_ROOT).as_posix()
        for document in (REPO_ROOT / "tests" / "prompt-version").rglob("*.md")
    }
    assert documents
    assert documents <= paths

    assert not any(path.startswith("tests/run/") for path in paths)


def test_repository_selection_includes_documentation_for_copied_tools() -> None:
    """`tools/*.py` を運ぶなら、その手順書 `tools/io-contracts-README.md` も運ぶ。"""
    paths = {path.as_posix() for path in copy_hve.collect_source_files(REPO_ROOT)}

    documented_scripts = {
        "tools/enrich_upstream_inputs.py",
        "tools/normalize_producers.py",
        "tools/remove_work_outputs.py",
        "tools/split_io_contracts.py",
    }
    assert documented_scripts <= paths
    assert "tools/io-contracts-README.md" in paths


def test_real_repository_copy_is_complete_and_runnable(tmp_path: Path) -> None:
    destination = tmp_path / "destination"
    destination.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=destination, check=True)
    _write(destination, ".hidden-old", "remove\n")
    _write(destination, "old/deep/file.txt", "remove\n")
    git_before = _file_hashes(destination / ".git")

    selected = copy_hve.collect_source_files(REPO_ROOT)
    expected = {relative.as_posix() for relative in selected}

    result = copy_hve.copy_hve_application(REPO_ROOT, destination)

    assert result.copied_files == len(expected)
    assert result.removed_entries == 2
    assert _file_paths(destination, exclude_git=True) == expected
    assert _file_hashes(destination / ".git") == git_before
    assert not (destination / ".hidden-old").exists()
    assert not (destination / "old").exists()
    for relative in (
        ".github/copilot-instructions.md",
        "hve/__init__.py",
        "mdq/__init__.py",
        "cq/__init__.py",
        "users-guide/hve-cli-getting-started.md",
    ):
        assert hashlib.sha256((destination / relative).read_bytes()).digest() == hashlib.sha256(
            (REPO_ROOT / relative).read_bytes()
        ).digest()

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(destination)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["HVE_STARTUP_VERSION_CHECKED"] = "1"
    completed = subprocess.run(
        [sys.executable, "-m", "hve", "--help"],
        cwd=destination,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "orchestrate" in completed.stdout


def test_copy_preserves_git_directory_and_replaces_everything_else(
    tmp_path: Path,
) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path / "destination"
    git_dir = destination / ".git"
    git_dir.mkdir(parents=True)
    git_marker = b"git metadata must survive\x00\xff"
    (git_dir / "config").write_bytes(git_marker)
    _write(destination, ".gitignore", "old ignore\n")
    _write(destination, ".hidden", "old hidden file\n")
    _write(destination, "old/deep/read-only.txt", "old\n")
    read_only = destination / "old/deep/read-only.txt"
    read_only.chmod(stat.S_IREAD)
    read_only.parent.chmod(stat.S_IREAD)
    selected = copy_hve.collect_source_files(source)
    expected = {
        relative.as_posix(): hashlib.sha256((source / relative).read_bytes()).hexdigest()
        for relative in selected
    }

    result = copy_hve.copy_hve_application(source, destination)

    assert result.copied_files > 0
    assert result.removed_entries == 3
    assert (git_dir / "config").read_bytes() == git_marker
    assert (destination / ".gitignore").read_text(encoding="utf-8") == ".venv/\n"
    assert not (destination / ".hidden").exists()
    assert not (destination / "old").exists()
    assert (destination / "hve/module.py").is_file()
    assert (destination / "users-guide/hve-cli-getting-started.md").is_file()
    assert (destination / "tests/prompt-version/01-request-contract.md").is_file()
    assert (destination / "tests/[gui]SystemTest - Full.txt").is_file()
    assert not (destination / "tests/run").exists()
    assert not (destination / "src").exists()
    assert not (destination / "docs").exists()
    assert not (destination / "local-llm-dev").exists()
    assert not (destination / "tools/copy-hve-other-repo").exists()
    assert not (destination / ".github/workflows/deploy-generated.yml").exists()
    assert _file_hashes(destination, exclude_git=True) == expected


def test_copy_preserves_worktree_git_file(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path / "destination"
    destination.mkdir()
    marker = "gitdir: ../main/.git/worktrees/target\n"
    _write(destination, ".git", marker)
    _write(destination, "remove-me.txt", "old\n")

    copy_hve.copy_hve_application(source, destination)

    assert (destination / ".git").read_text(encoding="utf-8") == marker
    assert not (destination / "remove-me.txt").exists()
    assert (destination / "hve/__init__.py").is_file()


def test_copy_removes_non_git_hardlink_to_worktree_git_file(
    tmp_path: Path,
) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path / "destination"
    destination.mkdir()
    marker = "gitdir: ../main/.git/worktrees/target\n"
    _write(destination, ".git", marker)
    alias = destination / "metadata-alias"
    try:
        alias.hardlink_to(destination / ".git")
    except OSError as exc:
        pytest.skip(f"hardlinks are unavailable: {exc}")

    copy_hve.copy_hve_application(source, destination)

    assert (destination / ".git").read_text(encoding="utf-8") == marker
    assert not alias.exists()
    assert (destination / "hve/__init__.py").is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows case folding contract")
def test_copy_preserves_case_variant_git_directory_on_windows(
    tmp_path: Path,
) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path / "destination"
    _write(destination, ".GIT/config", "keep case variant\n")
    _write(destination, "remove-me.txt", "old\n")

    copy_hve.copy_hve_application(source, destination)

    assert (destination / ".GIT/config").read_text(encoding="utf-8") == "keep case variant\n"
    assert not (destination / "remove-me.txt").exists()
    assert (destination / "hve/__init__.py").is_file()


def test_missing_source_contract_fails_before_destination_cleanup(
    tmp_path: Path,
) -> None:
    source = _fake_source(tmp_path, complete=False)
    destination = tmp_path / "destination"
    _write(destination, ".git/config", "keep\n")
    _write(destination, "old.txt", "must remain\n")

    with pytest.raises(copy_hve.CopyError, match="required HVE source files"):
        copy_hve.copy_hve_application(source, destination)

    assert (destination / ".git/config").read_text(encoding="utf-8") == "keep\n"
    assert (destination / "old.txt").read_text(encoding="utf-8") == "must remain\n"


@pytest.mark.parametrize("relation", ["same", "inside-source", "source-inside"])
def test_overlapping_source_and_destination_are_rejected_before_deletion(
    tmp_path: Path, relation: str
) -> None:
    source = _fake_source(tmp_path)
    if relation == "same":
        destination = source
    elif relation == "inside-source":
        destination = source / "nested-destination"
        _write(destination, "old.txt", "keep\n")
    else:
        destination = tmp_path

    with pytest.raises(copy_hve.CopyError, match="overlap"):
        copy_hve.copy_hve_application(source, destination)

    assert (source / "hve/__init__.py").is_file()
    if relation == "inside-source":
        assert (destination / "old.txt").is_file()


def test_filesystem_root_is_rejected(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    filesystem_root = Path(source.anchor)

    with pytest.raises(copy_hve.CopyError, match="filesystem root"):
        copy_hve.validate_paths(source, filesystem_root)


@pytest.mark.parametrize("suffix", [(".git",), ("repository", ".git", "objects")])
def test_git_metadata_path_is_rejected_before_deletion(
    tmp_path: Path, suffix: tuple[str, ...]
) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path.joinpath(*suffix)
    _write(destination, "marker.txt", "must remain\n")

    with pytest.raises(copy_hve.CopyError, match="Git metadata"):
        copy_hve.copy_hve_application(source, destination)

    assert (destination / "marker.txt").read_text(encoding="utf-8") == "must remain\n"


def test_symlinked_git_metadata_destination_is_rejected_before_deletion(
    tmp_path: Path,
) -> None:
    source = _fake_source(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    metadata = tmp_path / "external-metadata"
    _write(metadata, "marker.txt", "must remain\n")
    try:
        (repository / ".git").symlink_to(metadata, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(copy_hve.CopyError, match="Git metadata"):
        copy_hve.copy_hve_application(source, repository / ".git")

    assert (metadata / "marker.txt").read_text(encoding="utf-8") == "must remain\n"


def test_lexical_git_metadata_is_rejected_before_symlink_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path / "repository" / ".git"
    resolved_metadata = tmp_path / "external-metadata"
    _write(resolved_metadata, "marker.txt", "must remain\n")
    original_resolved = copy_hve._resolved

    def simulate_symlink_resolution(path: Path) -> Path:
        if Path(path) == destination:
            return resolved_metadata
        return original_resolved(path)

    monkeypatch.setattr(copy_hve, "_resolved", simulate_symlink_resolution)

    with pytest.raises(copy_hve.CopyError, match="Git metadata"):
        copy_hve.validate_paths(source, destination)

    assert (resolved_metadata / "marker.txt").read_text(encoding="utf-8") == "must remain\n"


def test_dry_run_does_not_create_or_modify_destination(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path / "destination"
    _write(destination, ".git/config", "keep\n")
    _write(destination, "old.txt", "keep old\n")

    result = copy_hve.copy_hve_application(source, destination, dry_run=True)

    assert result.copied_files > 0
    assert result.removed_entries == 1
    assert (destination / ".git/config").read_text(encoding="utf-8") == "keep\n"
    assert (destination / "old.txt").read_text(encoding="utf-8") == "keep old\n"


def test_cleanup_failure_does_not_start_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path / "destination"
    _write(destination, ".git/config", "keep\n")
    _write(destination, "old.txt", "cannot remove\n")

    def fail_delete(path: Path) -> None:
        raise copy_hve.CopyError(f"forced cleanup failure: {path}")

    monkeypatch.setattr(copy_hve, "_remove_path", fail_delete)

    with pytest.raises(copy_hve.CopyError, match="forced cleanup failure"):
        copy_hve.copy_hve_application(source, destination)

    assert (destination / ".git/config").read_text(encoding="utf-8") == "keep\n"
    assert (destination / "old.txt").read_text(encoding="utf-8") == "cannot remove\n"
    assert not (destination / "hve").exists()


def test_os_launchers_delegate_without_owning_delete_logic() -> None:
    powershell = (TOOL_DIR / "copy-hve.ps1").read_text(encoding="utf-8")
    shell = (TOOL_DIR / "copy-hve.sh").read_text(encoding="utf-8")

    assert "copy_hve.py" in powershell
    assert "copy_hve.py" in shell
    assert "Remove-Item" not in powershell
    assert "rm -rf" not in shell
    assert not (TOOL_DIR / "copy-hve.sh").read_bytes().startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in (TOOL_DIR / "copy-hve.sh").read_bytes()


def test_cli_refuses_noninteractive_delete_without_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path / "destination"
    _write(destination, ".git/config", "keep\n")
    _write(destination, "old.txt", "keep old\n")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    result = copy_hve.main([str(destination)], source_root=source)

    assert result == 2
    assert (destination / "old.txt").is_file()


def test_cli_yes_performs_the_copy(tmp_path: Path) -> None:
    source = _fake_source(tmp_path)
    destination = tmp_path / "destination"
    _write(destination, ".git/config", "keep\n")
    _write(destination, "old.txt", "remove\n")

    result = copy_hve.main([str(destination), "--yes"], source_root=source)

    assert result == 0
    assert (destination / ".git/config").is_file()
    assert not (destination / "old.txt").exists()
    assert (destination / "hve/__init__.py").is_file()