#!/usr/bin/env python3
"""Validate the HVE requirement-traceability block for a pull request."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from hve_scope import ScopeError, is_in_scope, normalise_relative


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
START_MARKER = "<!-- hve-traceability:start -->"
END_MARKER = "<!-- hve-traceability:end -->"
REQUIREMENT_DEFINITION = "hve-dev/requirement-definition.md"
REQUIREMENT_MAPPING = "hve-dev/requirement-test-mapping.md"
FEATURE_INVENTORY = "hve-dev/hve-feature-inventory.csv"
TEST_INVENTORY = "hve-dev/hve-test-inventory.csv"

ALLOWED_TEST_PREFIXES = (
    "hve/tests/", "hve/gui/tests/", "mdq/tests/", "cq/tests/", ".github/scripts/tests/",
    ".github/scripts/python/tests/", ".github/scripts/powershell/tests/",
    "mdq/gui/tests/", "tests/bats/",
)


class ValidationError(ValueError):
    """Raised when a traceability contract is invalid."""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read {path}") from exc


def _normalise_relative(value: str) -> str:
    try:
        return normalise_relative(value)
    except ScopeError as exc:
        raise ValidationError(str(exc)) from exc


def _changed_paths(path: Path) -> tuple[str, ...]:
    lines = _read_text(path).splitlines()
    if not lines:
        raise ValidationError("changed-files input is empty")
    changed: list[str] = []
    for line in lines:
        columns = line.split("\t")
        status = columns[0] if columns else ""
        if status in {"A", "M", "D"} and len(columns) == 2:
            changed.append(_normalise_relative(columns[1]))
        elif re.fullmatch(r"R\d+", status or "") and len(columns) == 3:
            changed.extend((_normalise_relative(columns[1]), _normalise_relative(columns[2])))
        else:
            raise ValidationError(f"invalid changed-files record: {line!r}")
    return tuple(changed)


def _parse_block(body: str) -> dict[str, str]:
    if body.count(START_MARKER) != 1 or body.count(END_MARKER) != 1:
        raise ValidationError("traceability markers must occur exactly once")
    start = body.index(START_MARKER) + len(START_MARKER)
    end = body.index(END_MARKER)
    if end < start or body[end + len(END_MARKER):].count(START_MARKER):
        raise ValidationError("invalid traceability marker order")
    lines = [line for line in body[start:end].splitlines() if line]
    expected = [f"- {key}: " for key in SCHEMA_KEYS]
    if len(lines) != len(expected) or any(not line.startswith(prefix) for line, prefix in zip(lines, expected, strict=True)):
        raise ValidationError("traceability keys must appear once and in the canonical order")
    fields = {key: line[len(prefix):] for key, line, prefix in zip(SCHEMA_KEYS, lines, expected, strict=True)}
    if any(not value or "REPLACE_ME" in value for value in fields.values()):
        raise ValidationError("traceability values must be populated")
    return fields


def _split_values(value: str, label: str) -> tuple[str, ...] | None:
    if value == "N/A":
        return None
    if "," in value and ", " not in value:
        raise ValidationError(f"{label} values must use ', ' as delimiter")
    values = tuple(value.split(", "))
    if not values or any(not item or "," in item for item in values):
        raise ValidationError(f"invalid {label} values")
    return values


def _read_inventory(root: Path) -> dict[str, list[dict[str, str]]]:
    path = root / FEATURE_INVENTORY
    expected_headers = (
        "feature_kind", "feature_id", "active_status", "section",
        "title_or_summary", "source", "line", "details",
    )
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader, None)
            if header != list(expected_headers) or len(header) != len(set(header)):
                raise ValidationError("feature inventory has an invalid header")
            rows = [dict(zip(expected_headers, row, strict=True)) for row in reader]
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        raise ValidationError("cannot read feature inventory") from exc
    inventory: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        feature_id = row.get("feature_id", "")
        if feature_id:
            inventory.setdefault(feature_id, []).append(row)
    return inventory


def _mapping_paths(mapping_text: str, requirement_id: str) -> set[str]:
    # 要求テストマッピングは節を `###` と `####` の両方で書いている。
    heading = re.search(rf"^#{{3,4}}\s+{re.escape(requirement_id)}(?:\s|—|-|$)(.*?)(?=^#{{1,4}}\s|\Z)", mapping_text, re.MULTILINE | re.DOTALL)
    if heading is None:
        return set()
    paths: set[str] = set()
    for display, target in re.findall(r"\[([^\]]+)\]\(([^)]*)\)", heading.group(1)):
        if display != target:
            raise ValidationError(f"mapping label and target differ for {requirement_id}")
        paths.add(_normalise_relative(target))
    return paths


def _validate_requirement_ids(root: Path, requirement_ids: tuple[str, ...], test_paths: tuple[str, ...]) -> None:
    inventory = _read_inventory(root)
    definition = _read_text(root / REQUIREMENT_DEFINITION)
    mapping = _read_text(root / REQUIREMENT_MAPPING)
    for requirement_id in requirement_ids:
        rows = inventory.get(requirement_id, [])
        if len(rows) != 1:
            raise ValidationError(f"requirement inventory is missing or conflicting: {requirement_id}")
        row = rows[0]
        if row.get("active_status") != "active-or-described" or row.get("source") != REQUIREMENT_DEFINITION:
            raise ValidationError(f"requirement is not active: {requirement_id}")
        if not re.search(rf"(?<![A-Za-z0-9-]){re.escape(requirement_id)}(?![A-Za-z0-9-])", definition):
            raise ValidationError(f"requirement is absent from definition: {requirement_id}")
        if not _mapping_paths(mapping, requirement_id).intersection(test_paths):
            raise ValidationError(f"requirement mapping does not contain a declared test path: {requirement_id}")


def _validate_test_paths(root: Path, test_paths: tuple[str, ...]) -> None:
    root_resolved = root.resolve()
    for value in test_paths:
        path = _normalise_relative(value)
        if not path.startswith(ALLOWED_TEST_PREFIXES):
            raise ValidationError(f"test path is outside the allowlist: {path}")
        candidate = root / path
        if candidate.is_symlink():
            raise ValidationError(f"test path must not be a symlink: {path}")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root_resolved)
        except (OSError, ValueError) as exc:
            raise ValidationError(f"test path is missing or escapes repository: {path}") from exc
        if not resolved.is_file():
            raise ValidationError(f"test path is not a file: {path}")


def _require_evidence(evidence: str, test_paths: tuple[str, ...]) -> None:
    red, separator, green = evidence.partition("; GREEN=")
    if not red.startswith("RED=") or not separator:
        raise ValidationError("RED/GREEN evidence is malformed")
    for path in test_paths:
        if not re.search(rf"(?:^|\band\s+){re.escape(path)}\s+failed\b", red[4:]):
            raise ValidationError(f"RED/GREEN evidence is missing for {path}")
        if not re.search(rf"(?:^|\band\s+){re.escape(path)}\s+passed\b", green):
            raise ValidationError(f"RED/GREEN evidence is missing for {path}")


def _validate_fields(root: Path, fields: dict[str, str], changed: tuple[str, ...]) -> None:
    change_type = fields["Change-Type"]
    if change_type not in {"feature", "bugfix", "maintenance"}:
        raise ValidationError("invalid change type")
    if fields["Manual-Review-Required"] not in {"yes", "no"}:
        raise ValidationError("invalid manual-review value")
    requirement_ids = _split_values(fields["Requirement-IDs"], "requirement ID")
    test_paths = _split_values(fields["Test-Paths"], "test path")
    manual_review = fields["Manual-Review-Required"]

    if requirement_ids is None:
        if change_type not in {"bugfix", "maintenance"} or fields["Requirement-N/A-Reason"] == "N/A" or manual_review != "yes":
            raise ValidationError("requirements may be N/A only for reviewed bugfix or maintenance")
    elif fields["Requirement-N/A-Reason"] != "N/A":
        raise ValidationError("requirement N/A reason must be N/A when IDs are declared")

    if test_paths is None:
        if change_type not in {"bugfix", "maintenance"} or fields["Test-N/A-Reason"] == "N/A" or manual_review != "yes":
            raise ValidationError("tests may be N/A only for reviewed bugfix or maintenance")
    elif fields["Test-N/A-Reason"] != "N/A":
        raise ValidationError("test N/A reason must be N/A when paths are declared")

    if change_type == "maintenance" and manual_review != "yes":
        raise ValidationError("maintenance requires human review")
    if requirement_ids is not None and test_paths is not None:
        _validate_test_paths(root, test_paths)
        _validate_requirement_ids(root, requirement_ids, test_paths)

    if change_type == "feature":
        if requirement_ids is None or test_paths is None:
            raise ValidationError("feature requires requirement IDs and test paths")
        required_paths = {
            REQUIREMENT_DEFINITION,
            REQUIREMENT_MAPPING,
            FEATURE_INVENTORY,
            TEST_INVENTORY,
            *test_paths,
        }
        if not required_paths.issubset(set(changed)):
            raise ValidationError("feature must update requirements, mapping, inventory, and tests")
        _require_evidence(fields["TDD-Evidence"], test_paths)
    elif change_type == "bugfix":
        if test_paths is not None:
            _require_evidence(fields["TDD-Evidence"], test_paths)
    elif test_paths is None:
        if not fields["TDD-Evidence"].startswith("N/A:"):
            raise ValidationError("maintenance without tests requires N/A evidence")
    else:
        _require_evidence(fields["TDD-Evidence"], test_paths)


def validate(root: Path, pr_body_file: Path, changed_files_file: Path) -> None:
    root = root.resolve()
    if not root.is_dir():
        raise ValidationError("repository root is not a directory")
    changed = _changed_paths(changed_files_file)
    if not any(is_in_scope(path) for path in changed):
        return
    fields = _parse_block(_read_text(pr_body_file))
    _validate_fields(root, fields, changed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--pr-body-file", required=True, type=Path)
    parser.add_argument("--changed-files-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        validate(args.root, args.pr_body_file, args.changed_files_file)
    except ValidationError as exc:
        print(f"HVE requirement traceability validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
