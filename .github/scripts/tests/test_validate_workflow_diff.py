"""G-DIFF の決定的 validator entrypoint 契約。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPO_ROOT / ".github" / "scripts" / "validate-workflow-diff.py"
_AAS_ALLOWED_PATH = "docs/catalog/app-arch-catalog.md"


def _write_json(path: Path, value: object, *, bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False)
    encoding = "utf-8-sig" if bom else "utf-8"
    path.write_text(text + "\n", encoding=encoding, newline="\n")


def _seed_root(root: Path) -> None:
    (root / "docs" / "catalog").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "catalog" / "app-catalog.md").write_text(
        "# App Catalog\n\n| APP-ID | Name |\n|---|---|\n| APP-009 | Demo |\n",
        encoding="utf-8",
        newline="\n",
    )


def _run(
    tmp_path: Path,
    *,
    files: object,
    workflow_id: str | None = "aas",
    metadata: object | None = None,
    output_format: str = "json",
    bom: bool = False,
    root: Path | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    subject = root or (tmp_path / "subject")
    if not subject.exists():
        _seed_root(subject)
    files_path = tmp_path / "inputs" / "files.json"
    _write_json(files_path, files, bom=bom)
    command = [
        sys.executable,
        str(VALIDATOR),
        "--root",
        str(subject),
        "--changed-files-file",
        str(files_path),
        "--format",
        output_format,
    ]
    if workflow_id is not None:
        command.extend(("--workflow-id", workflow_id))
    else:
        metadata_path = tmp_path / "inputs" / "metadata.json"
        _write_json(metadata_path, metadata, bom=bom)
        command.extend(("--pr-metadata-file", str(metadata_path)))
    return subprocess.run(
        command,
        cwd=cwd or REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=env,
    )


def _payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.stdout.strip(), result.stderr
    value = json.loads(result.stdout)
    assert isinstance(value, dict)
    return value


def test_json_pass_for_declared_path(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        files=[{"filename": _AAS_ALLOWED_PATH, "status": "modified"}],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = _payload(result)
    assert payload["status"] == "PASS"
    assert payload["workflow_id"] == "aas"
    assert payload["violations"] == []


def test_json_blocked_for_undeclared_path(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        files=[{"filename": "README.md", "status": "modified"}],
    )
    assert result.returncode != 0
    payload = _payload(result)
    assert payload["status"] == "BLOCKED"
    assert payload["violations"] == ["README.md"]


def test_metadata_can_resolve_managed_and_unmanaged_prs(tmp_path: Path) -> None:
    managed = _run(
        tmp_path / "managed",
        workflow_id=None,
        metadata={
            "title": "[AAS] generated",
            "body": "<!-- hve-workflow-id: aas -->",
            "issue_titles": [],
            "issue_labels": [],
            "changed_files": 1,
        },
        files=[{"filename": _AAS_ALLOWED_PATH, "status": "modified"}],
    )
    assert managed.returncode == 0
    assert _payload(managed)["status"] == "PASS"

    unmanaged = _run(
        tmp_path / "unmanaged",
        workflow_id=None,
        metadata={
            "title": "Ordinary maintenance",
            "body": "",
            "issue_titles": [],
            "issue_labels": [],
            "changed_files": 1,
        },
        files=[{"filename": "hve/runner.py", "status": "modified"}],
    )
    assert unmanaged.returncode == 0
    payload = _payload(unmanaged)
    assert payload["status"] == "N/A"
    assert payload["reason"] == "unmanaged pull request"


def test_metadata_count_mismatch_is_blocked(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        workflow_id=None,
        metadata={
            "title": "[AAS] generated",
            "body": "<!-- hve-workflow-id: aas -->",
            "issue_titles": [],
            "issue_labels": [],
            "changed_files": 2,
        },
        files=[{"filename": _AAS_ALLOWED_PATH, "status": "modified"}],
    )
    assert result.returncode != 0
    assert _payload(result)["status"] == "BLOCKED"


def test_more_than_github_api_file_limit_is_blocked(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        files=[
            {"filename": f"docs/generated-{index}.md", "status": "modified"}
            for index in range(3001)
        ],
    )
    assert result.returncode != 0
    payload = _payload(result)
    assert payload["status"] == "BLOCKED"
    assert "3,000-file limit" in str(payload["errors"])


def test_utf8_bom_inputs_are_accepted(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        workflow_id=None,
        metadata={
            "title": "[AAS] 日本語",
            "body": "<!-- hve-workflow-id: aas -->",
            "issue_titles": [],
            "issue_labels": [],
            "changed_files": 1,
        },
        files=[{"filename": _AAS_ALLOWED_PATH, "status": "modified"}],
        bom=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _payload(result)["status"] == "PASS"


def test_malformed_json_is_blocked_with_json_output(tmp_path: Path) -> None:
    subject = tmp_path / "subject"
    _seed_root(subject)
    files_path = tmp_path / "files.json"
    files_path.write_text("{not-json", encoding="utf-8", newline="\n")
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--root",
            str(subject),
            "--workflow-id",
            "aas",
            "--changed-files-file",
            str(files_path),
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert _payload(result)["status"] == "BLOCKED"


def test_text_output_is_deterministic_and_safe(tmp_path: Path) -> None:
    secret = "ghp_DO_NOT_PRINT_THIS_TOKEN"
    metadata = {
        "title": "[AAS] generated",
        "body": f"<!-- hve-workflow-id: unknown-{secret} -->\n{secret}",
        "issue_titles": [],
        "issue_labels": [],
        "changed_files": 1,
    }
    first = _run(
        tmp_path / "first",
        workflow_id=None,
        metadata=metadata,
        files=[{"filename": "README.md", "status": "modified", "patch": secret}],
        output_format="text",
    )
    second = _run(
        tmp_path / "second",
        workflow_id=None,
        metadata=metadata,
        files=[{"filename": "README.md", "status": "modified", "patch": secret}],
        output_format="text",
    )
    assert first.returncode != 0 and second.returncode != 0
    assert first.stdout == second.stdout
    assert secret not in first.stdout + first.stderr
    assert "BLOCKED" in first.stdout


def test_subject_python_is_never_imported(tmp_path: Path) -> None:
    subject = tmp_path / "subject"
    _seed_root(subject)
    marker = tmp_path / "subject-imported.txt"
    package = subject / "hve"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "workflow_diff_gate.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\nraise RuntimeError('subject imported')\n",
        encoding="utf-8",
        newline="\n",
    )
    result = _run(
        tmp_path,
        root=subject,
        cwd=subject,
        files=[{"filename": _AAS_ALLOWED_PATH, "status": "modified"}],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()


def test_subject_python_is_not_imported_when_trusted_root_is_later_on_pythonpath(
    tmp_path: Path,
) -> None:
    subject = tmp_path / "subject"
    _seed_root(subject)
    marker = tmp_path / "subject-imported-from-pythonpath.txt"
    package = subject / "hve"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n",
        encoding="utf-8",
        newline="\n",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(subject), str(REPO_ROOT)))

    result = _run(
        tmp_path,
        root=subject,
        cwd=subject,
        env=env,
        files=[{"filename": _AAS_ALLOWED_PATH, "status": "modified"}],
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()


def test_root_symlink_is_rejected(tmp_path: Path) -> None:
    real_root = tmp_path / "real-subject"
    _seed_root(real_root)
    link = tmp_path / "subject-link"
    try:
        os.symlink(real_root, link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    result = _run(
        tmp_path,
        root=link,
        files=[{"filename": _AAS_ALLOWED_PATH, "status": "modified"}],
    )
    assert result.returncode != 0
    assert _payload(result)["status"] == "BLOCKED"


def test_catalog_symlink_escape_is_rejected(tmp_path: Path) -> None:
    subject = tmp_path / "subject"
    _seed_root(subject)
    catalog = subject / "docs" / "catalog" / "app-catalog.md"
    catalog.unlink()
    outside = tmp_path / "outside-catalog.md"
    outside.write_text("| APP-ID | Name |\n|---|---|\n| APP-009 | Outside |\n", encoding="utf-8")
    try:
        os.symlink(outside, catalog)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    result = _run(
        tmp_path,
        root=subject,
        files=[{"filename": _AAS_ALLOWED_PATH, "status": "modified"}],
    )
    assert result.returncode != 0
    assert _payload(result)["status"] == "BLOCKED"


def test_malformed_changed_file_entry_is_blocked(tmp_path: Path) -> None:
    result = _run(tmp_path, files=[{"status": "modified"}])
    assert result.returncode != 0
    assert _payload(result)["status"] == "BLOCKED"
