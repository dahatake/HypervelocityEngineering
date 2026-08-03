"""RED contracts for the HVE requirement-traceability PR gate.

The tests cover only behavior required by FR-MAINT-04.  Validator arguments,
diagnostic text, and GitHub Actions step layout intentionally remain free.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPO_ROOT / ".github/scripts/validate-hve-requirement-traceability.py"
WORKFLOW = REPO_ROOT / ".github/workflows/validate-hve-requirement-traceability.yml"
TRUSTED_WORKFLOW = REPO_ROOT / ".github/workflows/validate-hve-requirement-traceability-trusted.yml"
PR_TEMPLATE = REPO_ROOT / ".github/pull_request_template.md"
BRANCH_PROTECTION = REPO_ROOT / ".github/branch-protection-main.json"

REQUIREMENT_DEFINITION = "hve-dev/requirement-definition.md"
REQUIREMENT_MAPPING = "hve-dev/requirement-test-mapping.md"
FEATURE_INVENTORY = "hve-dev/hve-feature-inventory.csv"
TEST_INVENTORY = "hve-dev/hve-test-inventory.csv"
TEST_PATH = "hve/tests/test_feature_contract.py"
REQUIREMENT_ID = "FR-TEST-01"

SCHEMA_KEYS = (
    "Change-Type",
    "Change-Type-Reason",
    "Requirement-IDs",
    "Requirement-N/A-Reason",
    "Test-Paths",
    "Test-N/A-Reason",
    "TDD-Evidence",
    "Manual-Review-Required",
)

IN_SCOPE_PATHS = (
    "hve/runner.py",
    "mdq/cli.py",
    "cq/store.py",
    "cq/tests/test_store.py",
    "cq.toml",
    "hve-dev/requirement-definition.md",
    "template/agent.md",
    "tools/skills/markdown_query/SKILL.md",
    "tools/runner/task.py",
    "tools/check_catalog.py",
    "users-guide/hve-cli-guide.md",
    ".github/copilot-instructions.md",
    ".github/instructions/hve-maintenance.instructions.md",
    ".github/skills/example/SKILL.md",
    ".github/prompts/example.prompt.md",
    ".github/io-contracts/example.yaml",
    ".github/scripts/example.py",
    ".github/ISSUE_TEMPLATE/example.yml",
    ".github/workflows/validate-example.yml",
    ".github/workflows/validate-example.yaml",
    "hve/tests/test_runner.py",
    "hve/gui/tests/test_window.py",
    "mdq/tests/test_cli.py",
    ".github/scripts/tests/test_contract.py",
    ".github/scripts/python/tests/test_contract.py",
    ".github/scripts/powershell/tests/test_contract.py",
    "mdq/gui/tests/test_gui.py",
    "tests/bats/hve.bats",
    "pyproject.toml",
    "mdq.toml",
    "hve.cmd",
    "hve.sh",
    ".vscode/tasks.json",
)
OUT_OF_SCOPE_PATHS = (
    "src/app/main.py",
    "docs/spec.md",
    "docs-generated/index.md",
    "knowledge/D01.md",
    "qa/report.md",
    "original-docs/source.md",
    "sample/input.json",
    "work/run/result.md",
    "tests/run/result.log",
    "hve.egg-info/PKG-INFO",
    "tools/hve-app-cash/main.py",
    "tools/gen_app04_test_specs.py",
    ".github/workflows/deploy-api.yml",
    ".github/workflows/azure-static-web-apps-site.yml",
    ".github/workflows/app009-deploy.yml",
    "package.json",
    "jest.config.js",
    "babel.config.js",
    "playwright.config.js",
    "unmatched/file.txt",
)
ALLOWED_TEST_PATHS = (
    "hve/tests/test_contract.py",
    "hve/gui/tests/test_contract.py",
    "mdq/tests/test_contract.py",
    "cq/tests/test_contract.py",
    ".github/scripts/tests/test_contract.py",
    ".github/scripts/python/tests/test_contract.py",
    ".github/scripts/powershell/tests/test_contract.py",
    "mdq/gui/tests/test_contract.py",
    "tests/bats/test_contract.bats",
)

VALIDATOR_REQUIRED = pytest.mark.skipif(
    not VALIDATOR.is_file(),
    reason="RED: validate-hve-requirement-traceability.py is not implemented",
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _seed_repository(
    root: Path,
    *,
    inventory: Sequence[tuple[str, str, str]] | None = None,
    definition_ids: Iterable[str] | None = None,
    mappings: Mapping[str, Sequence[str]] | None = None,
    test_paths: Iterable[str] | None = None,
) -> None:
    rows = list(
        inventory
        if inventory is not None
        else [(REQUIREMENT_ID, "active-or-described", REQUIREMENT_DEFINITION)]
    )
    ids = list(definition_ids if definition_ids is not None else [row[0] for row in rows])
    mapped = dict(mappings if mappings is not None else {REQUIREMENT_ID: (TEST_PATH,)})
    paths = set(test_paths or ())
    for mapped_paths in mapped.values():
        paths.update(mapped_paths)

    _write(
        root / REQUIREMENT_DEFINITION,
        "# Fixture requirements\n\n"
        + "\n".join(f"- **{requirement_id}**: fixture requirement." for requirement_id in ids)
        + "\n",
    )
    mapping_sections = []
    for requirement_id, mapped_paths in mapped.items():
        links = "\n".join(f"  - [{path}]({path})" for path in mapped_paths)
        mapping_sections.append(f"#### {requirement_id} — fixture\n- 対応テスト:\n{links}\n")
    _write(root / REQUIREMENT_MAPPING, "# Fixture mapping\n\n" + "\n".join(mapping_sections))

    inventory_path = root / FEATURE_INVENTORY
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    with inventory_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "feature_kind", "feature_id", "active_status", "section",
                "title_or_summary", "source", "line", "details",
            ),
        )
        writer.writeheader()
        for line, (requirement_id, status, source) in enumerate(rows, start=1):
            kind = "NFR" if requirement_id.startswith("NFR-") else "GATE" if requirement_id.startswith("G-") else "FR"
            writer.writerow(
                {
                    "feature_kind": kind,
                    "feature_id": requirement_id,
                    "active_status": status,
                    "section": "fixture",
                    "title_or_summary": "fixture",
                    "source": source,
                    "line": str(line),
                    "details": f"- **{requirement_id}**: fixture requirement.",
                }
            )

    _write(root / TEST_INVENTORY, "file\n" + "\n".join(sorted(paths)) + "\n")

    for path in paths:
        _write(root / path, "def test_fixture_contract():\n    assert True\n")


def _block(
    *,
    change_type: str = "bugfix",
    requirement_ids: str = REQUIREMENT_ID,
    requirement_na_reason: str = "N/A",
    test_paths: str = TEST_PATH,
    test_na_reason: str = "N/A",
    evidence: str | None = None,
    manual_review: str = "no",
) -> str:
    if evidence is None:
        evidence = f"RED={TEST_PATH} failed before the fix; GREEN={TEST_PATH} passed after the fix"
    values = (
        change_type,
        "Fixture change reason.",
        requirement_ids,
        requirement_na_reason,
        test_paths,
        test_na_reason,
        evidence,
        manual_review,
    )
    lines = "\n".join(f"- {key}: {value}" for key, value in zip(SCHEMA_KEYS, values, strict=True))
    return "<!-- hve-traceability:start -->\n" + lines + "\n<!-- hve-traceability:end -->\n"


def _feature_block(**kwargs: str) -> str:
    defaults = {
        "change_type": "feature",
        "requirement_ids": REQUIREMENT_ID,
        "test_paths": TEST_PATH,
        "evidence": f"RED={TEST_PATH} failed before implementation; GREEN={TEST_PATH} passed after implementation",
    }
    defaults.update(kwargs)
    return _block(**defaults)


def _feature_changes(*, include: Iterable[str] = ()) -> str:
    return "".join(
        f"M\t{path}\n"
        for path in (
            "hve/feature.py", REQUIREMENT_DEFINITION, REQUIREMENT_MAPPING,
            FEATURE_INVENTORY, TEST_INVENTORY, TEST_PATH, *include,
        )
    )


def _run_validator(root: Path, *, body: str, changes: str, seed: bool = True) -> subprocess.CompletedProcess[str]:
    if seed:
        _seed_repository(root)
    inputs = root / ".traceability-inputs"
    body_path = inputs / "pr-body.md"
    changes_path = inputs / "changed-files.txt"
    _write(body_path, body)
    _write(changes_path, changes)
    return subprocess.run(
        [
            sys.executable, str(VALIDATOR), "--root", str(root),
            "--pr-body-file", str(body_path),
            "--changed-files-file", str(changes_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def _accepts(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def _rejects(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode != 0, result.stdout + result.stderr


def _replace_field(body: str, key: str, value: str) -> str:
    prefix = f"- {key}: "
    lines = body.splitlines()
    index = next(index for index, line in enumerate(lines) if line.startswith(prefix))
    lines[index] = prefix + value
    return "\n".join(lines) + "\n"


def _scalar_values(node: object) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _scalar_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _scalar_values(value)
    elif node is not None:
        yield str(node)


def _workflow_jobs() -> tuple[dict[str, object], str]:
    text = WORKFLOW.read_text(encoding="utf-8-sig")
    data = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(data, dict)
    assert set(data.get("on", {})) == {"pull_request"}
    assert "pull_request_target" not in text
    jobs = data.get("jobs")
    assert isinstance(jobs, dict) and jobs
    return jobs, text


def test_required_traceability_artifacts_exist() -> None:
    for artifact in (VALIDATOR, WORKFLOW, TRUSTED_WORKFLOW, PR_TEMPLATE, BRANCH_PROTECTION):
        assert artifact.is_file(), f"missing required artifact: {artifact}"


def test_pr_template_contains_one_traceability_block_with_all_fields() -> None:
    text = PR_TEMPLATE.read_text(encoding="utf-8-sig")
    assert text.count("<!-- hve-traceability:start -->") == 1
    assert text.count("<!-- hve-traceability:end -->") == 1
    for key in SCHEMA_KEYS:
        assert text.count(f"- {key}:") == 1


@VALIDATOR_REQUIRED
@pytest.mark.parametrize(
    ("changes", "accepted"),
    (
        *((f"M\t{path}\n", False) for path in IN_SCOPE_PATHS),
        *((f"M\t{path}\n", True) for path in OUT_OF_SCOPE_PATHS),
        ("M\tCHANGELOG.md\n", True),
        ("M\tCHANGELOG.md\nM\thve/runner.py\n", False),
        ("A\thve/new.py\n", False),
        ("D\thve/old.py\n", False),
        ("R087\tdocs/old.md\thve/new.py\n", False),
        ("R087\thve/old.py\tdocs/new.md\n", False),
        ("R100\tdocs/old.md\tsrc/new.py\n", True),
    ),
)
def test_hve_scope_matches_fr_maint_04_boundary_table(
    tmp_path: Path, changes: str, accepted: bool
) -> None:
    result = _run_validator(
        tmp_path,
        body="",
        changes=changes,
        seed=False,
    )
    (_accepts if accepted else _rejects)(result)


@VALIDATOR_REQUIRED
@pytest.mark.parametrize(
    "changes",
    (
        "", "M\t/hve/runner.py\n", "M\t./hve/runner.py\n",
        "M\thve//runner.py\n", "M\thve/../docs/spec.md\n",
        "M\t../hve/runner.py\n", "R100\thve/old.py\n",
    ),
)
def test_malformed_changed_path_input_fails_closed(tmp_path: Path, changes: str) -> None:
    _rejects(_run_validator(tmp_path, body="", changes=changes, seed=False))


@VALIDATOR_REQUIRED
def test_schema_requires_exact_markers_and_eight_keys(tmp_path: Path) -> None:
    _accepts(_run_validator(tmp_path, body=_block(), changes="M\thve/runner.py\n"))
    malformed = [
        "# no block\n",
        _block() + _block(),
        _block().replace("<!-- hve-traceability:end -->", ""),
        _replace_field(_block(), "Change-Type", "Feature"),
        _replace_field(_block(), "Requirement-IDs", f"{REQUIREMENT_ID},FR-TEST-02"),
        _block().replace("<!-- hve-traceability:end -->", "- Unknown-Key: value\n<!-- hve-traceability:end -->"),
        _block().replace("<!-- hve-traceability:end -->", "- Change-Type: bugfix\n<!-- hve-traceability:end -->"),
        _block().replace(
            "- Change-Type: bugfix\n- Change-Type-Reason: Fixture change reason.\n",
            "- Change-Type-Reason: Fixture change reason.\n- Change-Type: bugfix\n",
        ),
    ]
    for key in SCHEMA_KEYS:
        malformed.append(_replace_field(_block(), key, "REPLACE_ME"))
        malformed.append(
            _block().replace(
                "<!-- hve-traceability:end -->",
                f"- {key}: duplicate\n<!-- hve-traceability:end -->",
            )
        )
        malformed.append(_replace_field(_block(), key, "line one\n  line two"))
        malformed.append(
            "\n".join(line for line in _block().splitlines() if not line.startswith(f"- {key}: ")) + "\n"
        )
    malformed.append(_replace_field(_block(), "Test-Paths", f"{TEST_PATH},mdq/tests/test_second.py"))
    second_requirement = "FR-TEST-02"
    for index, body in enumerate(malformed):
        _rejects(_run_validator(tmp_path / str(index), body=body, changes="M\thve/runner.py\n"))
    second_path = "mdq/tests/test_second.py"
    root = tmp_path / "multiple-paths"
    _seed_repository(
        root,
        inventory=[
            (REQUIREMENT_ID, "active-or-described", REQUIREMENT_DEFINITION),
            (second_requirement, "active-or-described", REQUIREMENT_DEFINITION),
        ],
        mappings={
            REQUIREMENT_ID: (TEST_PATH,),
            second_requirement: (second_path,),
        },
    )
    _accepts(_run_validator(
        root,
        body=_block(
            requirement_ids=f"{REQUIREMENT_ID}, {second_requirement}",
            test_paths=f"{TEST_PATH}, {second_path}",
            evidence=(
                f"RED={TEST_PATH} failed and {second_path} failed; "
                f"GREEN={TEST_PATH} passed and {second_path} passed"
            ),
        ),
        changes="M\thve/runner.py\n",
        seed=False,
    ))
    bad_delimiter_root = tmp_path / "bad-delimiter"
    _seed_repository(
        bad_delimiter_root,
        inventory=[
            (REQUIREMENT_ID, "active-or-described", REQUIREMENT_DEFINITION),
            (second_requirement, "active-or-described", REQUIREMENT_DEFINITION),
        ],
        mappings={
            REQUIREMENT_ID: (TEST_PATH,),
            second_requirement: (second_path,),
        },
    )
    _rejects(_run_validator(
        bad_delimiter_root,
        body=_block(
            requirement_ids=f"{REQUIREMENT_ID},{second_requirement}",
            test_paths=f"{TEST_PATH}, {second_path}",
            evidence=(
                f"RED={TEST_PATH} failed and {second_path} failed; "
                f"GREEN={TEST_PATH} passed and {second_path} passed"
            ),
        ),
        changes="M\thve/runner.py\n",
        seed=False,
    ))
    _rejects(_run_validator(
        bad_delimiter_root,
        body=_block(
            requirement_ids=f"{REQUIREMENT_ID}, {second_requirement}",
            test_paths=f"{TEST_PATH},{second_path}",
            evidence=(
                f"RED={TEST_PATH} failed and {second_path} failed; "
                f"GREEN={TEST_PATH} passed and {second_path} passed"
            ),
        ),
        changes="M\thve/runner.py\n",
        seed=False,
    ))


@VALIDATOR_REQUIRED
def test_change_type_na_and_manual_review_boundaries(tmp_path: Path) -> None:
    rejected = (
        _feature_block(requirement_ids="N/A", requirement_na_reason="No requirement.", manual_review="yes"),
        _feature_block(test_paths="N/A", test_na_reason="No test.", manual_review="yes"),
        _block(requirement_ids="N/A", requirement_na_reason="N/A", manual_review="yes"),
        _block(change_type="maintenance", manual_review="no"),
    )
    for index, body in enumerate(rejected):
        _rejects(_run_validator(tmp_path / str(index), body=body, changes="M\thve/runner.py\n"))
    _accepts(_run_validator(
        tmp_path / "bugfix-na",
        body=_block(requirement_ids="N/A", requirement_na_reason="No active requirement covers this defect.", manual_review="yes"),
        changes="M\thve/runner.py\n",
    ))
    _accepts(_run_validator(
        tmp_path / "maintenance",
        body=_block(change_type="maintenance", manual_review="yes"),
        changes="M\thve-dev/internal.md\n",
    ))


@VALIDATOR_REQUIRED
def test_requirement_inventory_definition_and_mapping_must_agree(tmp_path: Path) -> None:
    cases = (
        ("deprecated", [(REQUIREMENT_ID, "deprecated-or-removed", REQUIREMENT_DEFINITION)], None, None),
        ("partial", [(REQUIREMENT_ID, "partial-or-not-supported", REQUIREMENT_DEFINITION)], None, None),
        ("wrong-source", [(REQUIREMENT_ID, "active-or-described", "hve/runner.py")], None, None),
        ("missing-mapping", None, None, {}),
        ("conflicting", [
            (REQUIREMENT_ID, "active-or-described", REQUIREMENT_DEFINITION),
            (REQUIREMENT_ID, "deprecated-or-removed", REQUIREMENT_DEFINITION),
        ], None, None),
    )
    for name, inventory, definition_ids, mappings in cases:
        root = tmp_path / name
        _seed_repository(root, inventory=inventory, definition_ids=definition_ids, mappings=mappings)
        _rejects(_run_validator(root, body=_block(), changes="M\thve/runner.py\n", seed=False))
    _seed_repository(tmp_path / "unknown")
    _rejects(_run_validator(tmp_path / "unknown", body=_block(requirement_ids="FR-UNKNOWN-01"), changes="M\thve/runner.py\n", seed=False))
    root = tmp_path / "invalid-header"
    _seed_repository(root)
    _write(root / FEATURE_INVENTORY, "feature_id,feature_id\nFR-TEST-01,FR-TEST-01\n")
    _rejects(_run_validator(root, body=_block(), changes="M\thve/runner.py\n", seed=False))
    root = tmp_path / "mismatched-mapping-link"
    _seed_repository(root)
    _write(
        root / REQUIREMENT_MAPPING,
        f"#### {REQUIREMENT_ID} — fixture\n- 対応テスト:\n  - [{TEST_PATH}](https://example.invalid/test.py)\n",
    )
    _rejects(_run_validator(root, body=_block(), changes="M\thve/runner.py\n", seed=False))


@VALIDATOR_REQUIRED
def test_normative_requirement_families_and_each_mapping_relationship(tmp_path: Path) -> None:
    for requirement_id in ("NFR-TEST-01", "G-TEST"):
        root = tmp_path / requirement_id
        _seed_repository(root, inventory=[(requirement_id, "active-or-described", REQUIREMENT_DEFINITION)], mappings={requirement_id: (TEST_PATH,)})
        _accepts(_run_validator(root, body=_block(requirement_ids=requirement_id), changes="M\thve/runner.py\n", seed=False))
    root = tmp_path / "wrong-mapping"
    _seed_repository(root, mappings={REQUIREMENT_ID: ("hve/tests/test_other.py",)})
    _rejects(_run_validator(root, body=_block(), changes="M\thve/runner.py\n", seed=False))


@VALIDATOR_REQUIRED
def test_test_paths_must_be_existing_allowed_and_non_escaping(tmp_path: Path) -> None:
    for path in ALLOWED_TEST_PATHS:
        root = tmp_path / path.replace("/", "_")
        _seed_repository(root, mappings={REQUIREMENT_ID: (path,)})
        body = _block(test_paths=path, evidence=f"RED={path} failed; GREEN={path} passed")
        _accepts(_run_validator(root, body=body, changes="M\thve/runner.py\n", seed=False))
    for path in ("hve/tests/missing.py", "tests/test_outside_allowlist.py", "hve/tests/../runner.py", "../hve/tests/test_contract.py", "/hve/tests/test_contract.py"):
        root = tmp_path / path.replace("/", "_").replace(".", "dot")
        _seed_repository(root, mappings={REQUIREMENT_ID: (path,)})
        if path == "hve/tests/missing.py":
            (root / path).unlink()
        body = _block(test_paths=path, evidence=f"RED={path} failed; GREEN={path} passed")
        _rejects(_run_validator(root, body=body, changes="M\thve/runner.py\n", seed=False))


@VALIDATOR_REQUIRED
def test_test_path_symlink_cannot_escape_repository(tmp_path: Path) -> None:
    path = "hve/tests/test_symlink_contract.py"
    _seed_repository(tmp_path, mappings={REQUIREMENT_ID: (path,)})
    link = tmp_path / path
    link.unlink()
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("def test_outside():\n    assert True\n", encoding="utf-8")
    try:
        os.symlink(outside, link)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    body = _block(test_paths=path, evidence=f"RED={path} failed; GREEN={path} passed")
    _rejects(_run_validator(tmp_path, body=body, changes="M\thve/runner.py\n", seed=False))


@VALIDATOR_REQUIRED
def test_test_path_symlink_cannot_target_an_internal_non_test_file(tmp_path: Path) -> None:
    path = "hve/tests/test_symlink_contract.py"
    _seed_repository(tmp_path, mappings={REQUIREMENT_ID: (path,)})
    link = tmp_path / path
    link.unlink()
    target = tmp_path / "hve/runner.py"
    _write(target, "def run():\n    return None\n")
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    body = _block(test_paths=path, evidence=f"RED={path} failed; GREEN={path} passed")
    _rejects(_run_validator(tmp_path, body=body, changes="M\thve/runner.py\n", seed=False))


@VALIDATOR_REQUIRED
def test_feature_requires_normative_files_changed_tests_and_matching_evidence(tmp_path: Path) -> None:
    _accepts(_run_validator(tmp_path / "valid", body=_feature_block(), changes=_feature_changes()))
    for omitted in (
        REQUIREMENT_DEFINITION,
        REQUIREMENT_MAPPING,
        FEATURE_INVENTORY,
        TEST_INVENTORY,
        TEST_PATH,
    ):
        changes = "".join(
            f"M\t{path}\n"
            for path in (
                "hve/feature.py",
                REQUIREMENT_DEFINITION,
                REQUIREMENT_MAPPING,
                FEATURE_INVENTORY,
                TEST_INVENTORY,
                TEST_PATH,
            )
            if path != omitted
        )
        _rejects(_run_validator(tmp_path / omitted.replace("/", "_"), body=_feature_block(), changes=changes))
    for evidence in (
        f"RED={TEST_PATH} failed",
        f"GREEN={TEST_PATH} passed",
        f"RED=hve/tests/test_other.py failed; GREEN=hve/tests/test_other.py passed",
    ):
        _rejects(_run_validator(tmp_path / evidence.replace("/", "_"), body=_feature_block(evidence=evidence), changes=_feature_changes()))


@VALIDATOR_REQUIRED
def test_bugfix_and_maintenance_evidence_rules(tmp_path: Path) -> None:
    for index, evidence in enumerate((
        f"RED={TEST_PATH} failed",
        f"GREEN={TEST_PATH} passed",
        f"RED={TEST_PATH} passed; GREEN={TEST_PATH} failed",
        f"RED={TEST_PATH} passed and hve/tests/test_other.py failed; GREEN={TEST_PATH} failed and hve/tests/test_other.py passed",
    )):
        _rejects(_run_validator(tmp_path / f"invalid-evidence-{index}", body=_block(evidence=evidence), changes="M\thve/runner.py\n"))
    _accepts(_run_validator(
        tmp_path / "maintenance-evidence",
        body=_block(
            change_type="maintenance",
            manual_review="yes",
            evidence=f"RED={TEST_PATH} failed; GREEN={TEST_PATH} passed",
        ),
        changes="M\thve-dev/internal.md\n",
    ))
    _accepts(_run_validator(
        tmp_path / "maintenance-na",
        body=_block(change_type="maintenance", manual_review="yes", test_paths="N/A", test_na_reason="No executable behavior changes.", evidence="N/A: no executable behavior changes."),
        changes="M\thve-dev/internal.md\n",
    ))


def _validator_job(workflow: dict[str, object]) -> dict[str, object]:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    validator_path = VALIDATOR.relative_to(REPO_ROOT).as_posix()
    validator_jobs = [job for job in jobs.values() if isinstance(job, dict) and any(validator_path in value for value in _scalar_values(job))]
    assert len(validator_jobs) == 1
    return validator_jobs[0]


def _job_context(workflow: dict[str, object]) -> str:
    workflow_name = str(workflow["name"])
    job_name = str(_validator_job(workflow).get("name"))
    assert job_name and job_name != "None"
    return f"{workflow_name} / {job_name}"


def test_workflow_uses_untrusted_pr_body_safely_and_requires_validator() -> None:
    text = WORKFLOW.read_text(encoding="utf-8-sig")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    assert set(workflow.get("on", {})) == {"pull_request"}
    assert set(workflow["on"]["pull_request"].get("types", [])) == {
        "opened", "synchronize", "reopened", "edited", "ready_for_review",
    }
    assert "pull_request_target:" not in text
    assert "github.event.pull_request.body" in text
    permissions = workflow.get("permissions")
    assert permissions == {"contents": "read"}
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    validator_job = _validator_job(workflow)
    assert "continue-on-error" not in validator_job
    assert validator_job.get("if") in (None, "")
    steps = validator_job.get("steps", [])
    assert isinstance(steps, list)
    validator_runs = [
        str(step.get("run", ""))
        for step in steps
        if isinstance(step, dict)
        and VALIDATOR.relative_to(REPO_ROOT).as_posix() in str(step.get("run", ""))
    ]
    assert len(validator_runs) == 1
    validator_run = validator_runs[0]
    validator_path = re.escape(VALIDATOR.relative_to(REPO_ROOT).as_posix())
    validator_command = re.search(rf"\bpython(?:3)?\s+['\"]?{validator_path}", validator_run)
    assert validator_command is not None
    assert re.search(r"\bset\s+-[^\n]*e", validator_run[:validator_command.start()])
    assert "set +e" not in validator_run
    assert "||" not in validator_run
    assert not re.search(rf"\b(?:if|while|until)\s+.*{validator_path}", validator_run)
    assert re.search(r"--root\s+\S+", validator_run)
    assert re.search(r"--pr-body-file\s+\S+", validator_run)
    assert re.search(r"--changed-files-file\s+\S+", validator_run)
    for step in steps:
        assert isinstance(step, dict)
        assert step.get("if") in (None, "")
        assert "continue-on-error" not in step
    assert not re.search(
        r"(?im)^\s*(?:if|while|until|for|case|function)\b|\b(?:eval|source)\b|`|\$\(|\(\)\s*\{",
        validator_run,
    )

    body_pattern = re.compile(r"^\$\{\{\s*github\.event\.pull_request\.body\s*\}\}$")
    body_environment_names: set[str] = set()
    for scope in (validator_job, *steps):
        if not isinstance(scope, dict):
            continue
        environment = scope.get("env")
        if not isinstance(environment, dict):
            continue
        for name, value in environment.items():
            if body_pattern.fullmatch(str(value)):
                body_environment_names.add(str(name))
    assert body_environment_names
    for name in body_environment_names:
        body_variable = rf"(?:\${name}\b|\$\{{{name}\}})"
        write_match = re.search(rf"{body_variable}.*>\s*([\"']?)(?P<path>\$[A-Za-z_][A-Za-z0-9_]*|\$\{{[A-Za-z_][A-Za-z0-9_]*\}})\1", "\n".join(str(step.get("run", "")) for step in steps))
        if write_match is None:
            continue
        assert re.search(rf"--pr-body-file\s+[\"']?{re.escape(write_match.group('path'))}", validator_run)
        break
    else:
        raise AssertionError("PR body must be written from a safe environment variable and passed to the validator")
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps", []):
            if isinstance(step, dict):
                assert not re.search(r"\$\{\{\s*github\.event\.pull_request\.body\s*\}\}", str(step.get("run", "")))


def test_trusted_workflow_executes_only_the_base_validator() -> None:
    text = TRUSTED_WORKFLOW.read_text(encoding="utf-8-sig")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    assert set(workflow.get("on", {})) == {"pull_request_target"}
    assert set(workflow["on"]["pull_request_target"].get("types", [])) == {
        "opened", "synchronize", "reopened", "edited", "ready_for_review",
    }
    assert workflow.get("permissions") == {"contents": "read", "pull-requests": "read"}
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    trusted_jobs = [job for job in jobs.values() if isinstance(job, dict) and job.get("name") == "HVE Requirement Traceability Trusted"]
    assert len(trusted_jobs) == 1
    trusted_job = trusted_jobs[0]
    assert trusted_job.get("if") in (None, "")
    assert "continue-on-error" not in trusted_job
    steps = trusted_job.get("steps", [])
    assert isinstance(steps, list)
    checkouts = [step for step in steps if isinstance(step, dict) and step.get("uses") == "actions/checkout@v4"]
    assert any(step.get("with") == {"ref": "${{ github.event.pull_request.base.sha }}", "path": "trusted", "fetch-depth": "1"} for step in checkouts)
    assert any(step.get("with") == {"ref": "${{ github.event.pull_request.head.sha }}", "path": "subject", "fetch-depth": "0"} for step in checkouts)
    runs = [str(step["run"]) for step in steps if isinstance(step, dict) and "run" in step]
    assert len(runs) == 1
    run = runs[0]
    assert "github.event.pull_request.body" not in run
    assert "set -e" in run
    assert 'git -C "$GITHUB_WORKSPACE/subject" diff --name-status "$BASE_SHA" "$HEAD_SHA"' in run
    assert 'python "$GITHUB_WORKSPACE/trusted/.github/scripts/validate-hve-requirement-traceability.py"' in run
    assert '--root "$GITHUB_WORKSPACE/subject"' in run
    assert "$GITHUB_WORKSPACE/subject/.github/scripts/validate-hve-requirement-traceability.py" not in run
    assert "allow-unsafe-pr-checkout" not in text
    for step in steps:
        assert isinstance(step, dict)
        assert step.get("if") in (None, "")
        assert "continue-on-error" not in step


def test_branch_protection_keeps_review_and_requires_validator_check() -> None:
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8-sig"), Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    data = json.loads(BRANCH_PROTECTION.read_text(encoding="utf-8-sig"))
    contexts = data["required_status_checks"]["contexts"]
    assert _job_context(workflow) in contexts
    trusted = yaml.load(TRUSTED_WORKFLOW.read_text(encoding="utf-8-sig"), Loader=yaml.BaseLoader)
    assert isinstance(trusted, dict)
    trusted_jobs = trusted["jobs"]
    assert isinstance(trusted_jobs, dict)
    trusted_job = next(job for job in trusted_jobs.values() if isinstance(job, dict) and job.get("name") == "HVE Requirement Traceability Trusted")
    assert f"{trusted['name']} / {trusted_job['name']}" in contexts
    assert data["required_pull_request_reviews"]["required_approving_review_count"] >= 1
