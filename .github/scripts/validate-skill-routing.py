#!/usr/bin/env python3
"""Validate routing consistency between _routing/SKILL.md and skill files."""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROUTING = Path(".github/skills/_routing/SKILL.md")
SKILLS_ROOT = Path(".github/skills")
SKILL_FILE_NAME = "SKILL.md"

# Intentionally minimal: keep only true exceptions that are expected to be unreferenced.
UNREFERENCED_ALLOWLIST: set[str] = {
    ".github/skills/karpathy-guidelines/SKILL.md",
}

PATH_PATTERN = re.compile(r"(?P<path>(?:\.\.?/|\.github/)[A-Za-z0-9_./-]+/SKILL\.md)")


@dataclass(frozen=True)
class Violation:
    """Represents a validation finding."""

    level: str  # ERROR or WARN
    code: str
    message: str


@dataclass(frozen=True)
class Frontmatter:
    """Minimal frontmatter fields needed by this validator."""

    has_frontmatter: bool
    name: str | None
    description: str | None
    metadata_version: str | None


def parse_args() -> argparse.Namespace:
    """Parse CLI options."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate skill routing consistency: missing references, unreferenced skills, "
            "duplicate skill names, and required frontmatter keys."
        )
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat WARN findings as errors for exit code calculation.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root path. Defaults to repository root resolved from this script.",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        help="Glob pattern for relative paths to ignore. Can be specified multiple times.",
    )
    return parser.parse_args()


def resolve_repo_root(root: Path | None) -> Path:
    """Resolve repository root."""
    if root is not None:
        return root.resolve()
    return Path(__file__).resolve().parents[2]


def to_rel_path(path: Path, root: Path) -> str:
    """Convert path to root-relative POSIX path string."""
    return path.resolve().relative_to(root).as_posix()


def should_ignore(rel_path: str, ignore_patterns: list[str]) -> bool:
    """Return True if path matches any ignore pattern."""
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in ignore_patterns)


def extract_frontmatter_block(content: str) -> str | None:
    """Extract YAML frontmatter block from markdown."""
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end < 0:
        return None
    return content[4:end]


def parse_frontmatter(content: str) -> Frontmatter:
    """Parse required frontmatter fields with a lightweight parser."""
    fm_text = extract_frontmatter_block(content)
    if fm_text is None:
        return Frontmatter(False, None, None, None)

    name_match = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
    description_match = re.search(r"^description:\s*(.+)$", fm_text, re.MULTILINE)

    metadata_block = re.search(r"^metadata:\s*\n((?:[ \t]+.*\n?)*)", fm_text, re.MULTILINE)
    version = None
    if metadata_block:
        version_match = re.search(
            r"^[ \t]+version:\s*[\"']?([^\"\n']+)[\"']?\s*$",
            metadata_block.group(1),
            re.MULTILINE,
        )
        if version_match:
            version = version_match.group(1).strip()

    name = name_match.group(1).strip().strip("\"'") if name_match else None
    description = description_match.group(1).strip() if description_match else None

    return Frontmatter(True, name, description, version)


def resolve_reference_path(candidate: str, routing_file: Path, root: Path) -> Path:
    """Resolve candidate reference path to absolute path."""
    if candidate.startswith(".github/"):
        return (root / candidate).resolve()
    return (routing_file.parent / candidate).resolve()


def extract_routing_references(routing_file: Path, root: Path) -> tuple[set[str], list[str]]:
    """Extract referenced SKILL.md paths from routing markdown."""
    content = routing_file.read_text(encoding="utf-8")
    references: set[str] = set()
    escaped_references: list[str] = []

    for match in PATH_PATTERN.finditer(content):
        candidate = match.group("path")
        resolved = resolve_reference_path(candidate, routing_file, root)
        try:
            rel = to_rel_path(resolved, root)
        except ValueError:
            escaped_references.append(candidate)
            continue

        if rel.startswith(f"{SKILLS_ROOT.as_posix()}/") and rel.endswith("/SKILL.md"):
            references.add(rel)

    return references, escaped_references


def list_skill_files(root: Path, ignore_patterns: list[str]) -> list[Path]:
    """List target skill files for validation."""
    base = root / SKILLS_ROOT
    all_skills = sorted(base.rglob(SKILL_FILE_NAME))
    target_files: list[Path] = []

    for skill_file in all_skills:
        rel = to_rel_path(skill_file, root)
        if rel == DEFAULT_ROUTING.as_posix():
            continue
        if "/_evals/" in rel:
            continue
        if should_ignore(rel, ignore_patterns):
            continue
        target_files.append(skill_file)

    return target_files


def check_missing_references(
    references: set[str], escaped_references: list[str], root: Path, ignore_patterns: list[str]
) -> list[Violation]:
    """Detect references in routing that do not exist."""
    violations: list[Violation] = []
    for raw_reference in sorted(set(escaped_references)):
        violations.append(
            Violation(
                "ERROR",
                "MISSING_REFERENCE",
                f"_routing -> {raw_reference}（リポジトリ外を参照）",
            )
        )

    for rel in sorted(references):
        if should_ignore(rel, ignore_patterns):
            continue
        if not (root / rel).is_file():
            violations.append(
                Violation(
                    "ERROR",
                    "MISSING_REFERENCE",
                    f"_routing -> {rel}（存在しない）",
                )
            )
    return violations


def check_unreferenced_skills(
    references: set[str], skill_files: list[Path], root: Path
) -> list[Violation]:
    """Detect skill files not referenced from routing."""
    violations: list[Violation] = []
    for skill_file in skill_files:
        rel = to_rel_path(skill_file, root)
        if rel in references or rel in UNREFERENCED_ALLOWLIST:
            continue
        violations.append(Violation("WARN", "UNREFERENCED_SKILL", rel))
    return violations


def check_duplicate_skill_names(skill_files: list[Path], root: Path) -> list[Violation]:
    """Detect duplicate skill names by frontmatter name or folder fallback."""
    by_name: dict[str, list[str]] = {}

    for skill_file in skill_files:
        rel = to_rel_path(skill_file, root)
        content = skill_file.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content)
        skill_name = frontmatter.name or skill_file.parent.name
        by_name.setdefault(skill_name, []).append(rel)

    violations: list[Violation] = []
    for skill_name, paths in sorted(by_name.items()):
        if len(paths) < 2:
            continue
        location_labels = ", ".join(path.rsplit("/", 1)[0] + "/" for path in sorted(paths))
        violations.append(
            Violation(
                "ERROR",
                "DUPLICATE_SKILL_NAME",
                f"{skill_name}: {location_labels}",
            )
        )
    return violations


def check_required_frontmatter(skill_files: list[Path], root: Path) -> list[Violation]:
    """Detect missing required frontmatter fields."""
    violations: list[Violation] = []

    for skill_file in skill_files:
        rel = to_rel_path(skill_file, root)
        content = skill_file.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content)

        missing: list[str] = []
        if not frontmatter.has_frontmatter:
            missing.extend(["name", "description", "metadata.version"])
        else:
            if not frontmatter.name:
                missing.append("name")
            if not frontmatter.description:
                missing.append("description")
            if not frontmatter.metadata_version:
                missing.append("metadata.version")

        if missing:
            violations.append(
                Violation(
                    "ERROR",
                    "MISSING_FRONTMATTER",
                    f"{rel}: {', '.join(missing)}",
                )
            )

    return violations


def build_violations(root: Path, ignore_patterns: list[str]) -> list[Violation]:
    """Run all validations and return findings."""
    routing_file = root / DEFAULT_ROUTING
    if not routing_file.is_file():
        return [
            Violation(
                "ERROR",
                "MISSING_ROUTING_FILE",
                f"{DEFAULT_ROUTING.as_posix()} が見つかりません",
            )
        ]

    references, escaped_references = extract_routing_references(routing_file, root)
    skill_files = list_skill_files(root, ignore_patterns)

    violations: list[Violation] = []
    violations.extend(
        check_missing_references(references, escaped_references, root, ignore_patterns)
    )
    violations.extend(check_unreferenced_skills(references, skill_files, root))
    violations.extend(check_duplicate_skill_names(skill_files, root))
    violations.extend(check_required_frontmatter(skill_files, root))

    return violations


def print_violations(violations: list[Violation]) -> None:
    """Print findings in a stable format."""
    for violation in violations:
        print(
            f"[{violation.level}]   {violation.code:<22} {violation.message}",
            file=sys.stderr,
        )


def compute_exit_code(violations: list[Violation], strict: bool) -> int:
    """Compute process exit code from findings and strict mode."""
    has_error = any(v.level == "ERROR" for v in violations)
    has_warning = any(v.level == "WARN" for v in violations)

    if has_error:
        return 1
    if strict and has_warning:
        return 1
    return 0


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    root = resolve_repo_root(args.root)
    violations = build_violations(root, args.ignore)

    print_violations(violations)
    return compute_exit_code(violations, args.strict)


if __name__ == "__main__":
    sys.exit(main())
