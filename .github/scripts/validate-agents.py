#!/usr/bin/env python3
"""Validate .agent.md frontmatter in .github/agents/

Exit codes:
  0 - No errors (warnings may be present)
  1 - One or more errors found

Usage:
  python3 validate-agents.py [--strict]

  --strict  Treat recommended-field warnings as errors
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import yaml as _yaml

    def _parse_yaml(text: str) -> dict:
        result = _yaml.safe_load(text)
        return result if isinstance(result, dict) else {}

except ImportError:  # pragma: no cover
    _yaml = None  # type: ignore[assignment]

    def _parse_yaml(text: str) -> dict:  # type: ignore[misc]
        return {}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENTS_DIR = Path(".github/agents")

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

DESC_MIN_LEN = 40
DESC_MAX_LEN = 1024

# Heuristic patterns indicating "when to invoke" guidance in description
WHEN_TO_INVOKE_PATTERNS = [
    r"\bwhen\b",
    r"\buse this\b",
    r"\btrigger\b",
    r"の場合",
    r"のとき",
    r"に使用",
    r"を使う",
]
_WHEN_PATTERN = re.compile("|".join(WHEN_TO_INVOKE_PATTERNS), re.IGNORECASE)

TOOLS_OVERSPEC_THRESHOLD = 10

# Body section heading whose content must not be empty.
# Empty Skills 依存 section means the Agent declared the dependency anchor but
# never listed which Skills are required. This is a documentation gap.
SKILLS_SECTION_HEADING = "## Agent 固有の Skills 依存"

# Files in AGENTS_DIR that are not real Agent definitions and must be skipped
# during validation.
# - Files starting with "_" are templates / utilities (e.g. _template.md).
AGENT_FILE_SKIP_PREFIXES = ("_",)

# ---------------------------------------------------------------------------
# Heading order check (R07)
# ---------------------------------------------------------------------------
# Standard H2 section order per docs/agent-heading-standard.md.
# Sections marked optional may be absent without warning.
STANDARD_HEADING_ORDER = [
    ("## 共通ルール", True),
    ("## 1) 目的と非目的", True),
    ("## 2) 入力（必ず参照）", True),
    ("## 3) 出力フォーマット（Markdown固定スキーマ）", True),
    ("## 4) 実行手順（順序固定）", True),
    ("## 5) 品質原則（必ず守る）", True),
    ("## 6) セルフチェック（出力前に必ず確認）", True),
    ("## 7) 完了条件", True),
    ("## Agent 固有の Skills 依存", True),
    # Optional sections (presence not required, but if present must appear after C8)
    ("## APP-ID スコープ → Skill `app-scope-resolution` を参照", False),
    ("## 禁止事項", False),
    ("## 関連 / 参考", False),
]

# Agents using XML-tag template (R07 / S7) are out of scope for heading-order check.
HEADING_CHECK_SKIP_FILES = {
    "Arch-ArchitectureCandidateAnalyzer.agent.md",
    "Arch-TDD-TestSpec.agent.md",
    "Dev-Microservice-Azure-ComputeDeploy-AzureFunctions.agent.md",
    "Dev-Microservice-Azure-DataDeploy.agent.md",
    "Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps.agent.md",
}

# Files using a non-standard first H2 (workflow dispatcher) are skipped.
HEADING_CHECK_SKIP_FIRST_H2 = "## 0) モードディスパッチ"


def _extract_h2_headings(content: str) -> List[str]:
    """Return list of H2 heading text (with `## ` prefix) in document order."""
    return [
        line.rstrip()
        for line in content.splitlines()
        if line.startswith("## ")
    ]


def check_heading_order(content: str, filename: str) -> List[str]:
    """Verify required H2 sections exist and appear in standard order.

    Returns a list of human-readable issue messages (empty if OK).
    Skips XML-tag-style files and workflow dispatchers.
    """
    if filename in HEADING_CHECK_SKIP_FILES:
        return []
    h2s = _extract_h2_headings(content)
    if not h2s:
        return ["No H2 headings found"]
    if h2s[0] == HEADING_CHECK_SKIP_FIRST_H2:
        return []  # workflow dispatcher: out of scope

    issues: List[str] = []
    standard_only = [(h, req) for h, req in STANDARD_HEADING_ORDER]
    # Find positions of each standard heading in the file's H2 sequence
    positions: Dict[str, int] = {}
    for idx, h2 in enumerate(h2s):
        for std, _req in standard_only:
            if h2 == std and std not in positions:
                positions[std] = idx
                break

    # Required sections must exist
    for std, required in standard_only:
        if required and std not in positions:
            issues.append(f"Missing required heading: '{std}'")

    # Existing sections must appear in standard order
    ordered_std = [std for std, _ in standard_only if std in positions]
    indices = [positions[s] for s in ordered_std]
    if indices != sorted(indices):
        issues.append(
            "Heading order violation: standard sections not in canonical order"
        )

    return issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def extract_frontmatter(content: str) -> Optional[str]:
    """Return YAML frontmatter text (without delimiters), or None if absent."""
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end < 0:
        return None
    return content[4:end]


def get_field_value(fm_text: str, field: str) -> Optional[str]:
    """Return single-line field value, or None if field is absent."""
    m = re.search(rf"^{field}:\s*(.+)", fm_text, re.MULTILINE)
    if m:
        return m.group(1).strip(" \"'")
    return None


def get_description(fm_text: str) -> str:
    """Return description value (handles multi-line > / | styles)."""
    m = re.search(
        r"^description:\s*[>|]\s*\n((?:[ \t]+.+\n)+)", fm_text, re.MULTILINE
    )
    if m:
        return re.sub(r"^[ \t]+", "", m.group(1), flags=re.MULTILINE).strip()
    m2 = re.search(r"^description:\s*(.+)", fm_text, re.MULTILINE)
    if m2:
        return m2.group(1).strip(" \"'")
    return ""


def parse_tools_list(fm_text: str) -> Optional[List[str]]:
    """Return list of tool names from tools field, or None if field absent.

    Handles all common YAML forms:
      - Inline JSON:   tools: ["read", "search"]
      - Inline flow:   tools: [read, search]
      - Block list:    tools:\\n  - read\\n  - search
    Falls back to regex extraction when PyYAML is unavailable.
    """
    if _yaml is not None:
        data = _parse_yaml(fm_text)
        if "tools" not in data:
            return None
        tools_val = data["tools"]
        if tools_val is None:
            return []
        if isinstance(tools_val, list):
            return [str(item) for item in tools_val]
        return [str(tools_val)]

    # Fallback: regex (inline bracket style only)
    m = re.search(r"^tools:\s*(.+)", fm_text, re.MULTILINE)
    if not m:
        # Check for block list form "tools:\n  - item"
        if re.search(r"^tools:\s*$", fm_text, re.MULTILINE):
            items = re.findall(r"^\s+-\s+(.+)", fm_text, re.MULTILINE)
            return items if items else []
        return None
    raw = m.group(1).strip()
    items = re.findall(r'["\']([^"\']+)["\']|[\[\s,]([A-Za-z_*][A-Za-z0-9_*]*)[\],\s]', raw)
    flat = [a or b for a, b in items]
    return flat if flat else []


def get_metadata_version(fm_text: str) -> Optional[str]:
    """Extract metadata.version from frontmatter text."""
    metadata_match = re.search(r"^metadata:\s*\n((?:[ \t]+.*\n?)*)", fm_text, re.MULTILINE)
    if not metadata_match:
        return None
    metadata_body = metadata_match.group(1)
    version_match = re.search(
        r"^[ \t]+version:\s*[\"']?([^\"'\n]+)[\"']?\s*$", metadata_body, re.MULTILINE
    )
    if not version_match:
        return None
    return version_match.group(1).strip()


def _is_skills_section_empty(content: str) -> Optional[bool]:
    """Return True if the Skills 依存 section exists but is empty.

    Returns:
        None  - Section heading not present (caller decides whether to warn).
        False - Section heading present and contains at least one non-blank line.
        True  - Section heading present but contains only blank lines.
    """
    idx = content.find(SKILLS_SECTION_HEADING)
    if idx < 0:
        return None
    rest = content[idx + len(SKILLS_SECTION_HEADING):]
    # Find next markdown heading (## or #) — that delimits the section.
    next_h2 = rest.find("\n## ")
    next_h1 = rest.find("\n# ")
    candidates = [p for p in (next_h2, next_h1) if p >= 0]
    section = rest[: min(candidates)] if candidates else rest
    # Drop the heading's trailing newline, keep only following content lines.
    body_lines = [line for line in section.split("\n")[1:] if line.strip()]
    return not body_lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat recommended-field warnings as errors",
    )
    args = parser.parse_args()

    total_errors = 0
    total_warnings = 0
    file_results: List[dict] = []

    agent_files = sorted(AGENTS_DIR.glob("*.agent.md"))
    # Also include legacy files without the .agent.md suffix (e.g. _template.md).
    # Skip files whose name starts with AGENT_FILE_SKIP_PREFIXES (templates).
    agent_files = [
        f for f in agent_files
        if not f.name.startswith(AGENT_FILE_SKIP_PREFIXES)
    ]
    if not agent_files:
        print(f"⚠️  No .agent.md files found in {AGENTS_DIR}")
        return 0

    # --- Pass 1: collect per-file results ---
    seen_names: Dict[str, Path] = {}

    for agent_file in agent_files:
        content = agent_file.read_text(encoding="utf-8")
        file_errors: List[str] = []
        file_warnings: List[str] = []

        fm = extract_frontmatter(content)
        if fm is None:
            file_errors.append("Missing or malformed frontmatter (--- delimiters)")
            file_results.append(
                {"path": agent_file, "errors": file_errors, "warnings": file_warnings}
            )
            continue

        # --- Required checks (always errors) ---

        if not re.search(r"^name:", fm, re.MULTILINE):
            file_errors.append("Missing required field: 'name'")
        else:
            name_val = get_field_value(fm, "name")
            if name_val:
                if name_val in seen_names:
                    file_errors.append(
                        f"Duplicate name '{name_val}' (first seen in {seen_names[name_val]})"
                    )
                else:
                    seen_names[name_val] = agent_file

        if not re.search(r"^description:", fm, re.MULTILINE):
            file_errors.append("Missing required field: 'description'")
        else:
            desc = get_description(fm)
            desc_len = len(desc)

            # Description quality: always warnings (never errors)
            if desc_len < DESC_MIN_LEN:
                file_warnings.append(
                    f"Description too short ({desc_len} chars, min {DESC_MIN_LEN}): '{desc[:60]}'"
                )
            if desc_len > DESC_MAX_LEN:
                file_warnings.append(
                    f"Description exceeds {DESC_MAX_LEN} chars ({desc_len})"
                )
            if not _WHEN_PATTERN.search(desc):
                file_warnings.append(
                    "Description lacks 'when to invoke' guidance "
                    "(keywords: when/use this/trigger/の場合/のとき/に使用/を使う)"
                )

        # metadata.version: required, must be valid SemVer
        version = get_metadata_version(fm)
        if version is None:
            file_errors.append("Missing required field: 'metadata.version' (SemVer MAJOR.MINOR.PATCH)")
        elif not SEMVER_RE.fullmatch(version):
            file_errors.append(
                f"Invalid 'metadata.version' (SemVer MAJOR.MINOR.PATCH required): '{version}'"
            )

        # --- Recommended checks (warning by default, error with --strict) ---

        if not re.search(r"^model:", fm, re.MULTILINE):
            msg = "Missing recommended field: 'model' (explicit model promotes reproducibility)"
            if args.strict:
                file_errors.append(msg)
            else:
                file_warnings.append(msg)

        tools = parse_tools_list(fm)
        if tools is None:
            msg = "Missing recommended field: 'tools' (explicit tool list promotes least-privilege)"
            if args.strict:
                file_errors.append(msg)
            else:
                file_warnings.append(msg)
        else:
            # Tools over-specification: always warnings
            if "*" in tools:
                file_warnings.append(
                    "tools contains wildcard '*' — consider specifying minimum required tools"
                )
            elif len(tools) >= TOOLS_OVERSPEC_THRESHOLD:
                file_warnings.append(
                    f"tools lists {len(tools)} items (>= {TOOLS_OVERSPEC_THRESHOLD}) — consider reducing to minimum required"
                )

        # --- Body-level checks (always warnings; promoted to error under --strict) ---

        empty_skills = _is_skills_section_empty(content)
        if empty_skills is True:
            msg = (
                f"Section '{SKILLS_SECTION_HEADING}' exists but is empty "
                "(list the Skills this Agent depends on, or remove the section)"
            )
            if args.strict:
                file_errors.append(msg)
            else:
                file_warnings.append(msg)
        elif empty_skills is None:
            msg = (
                f"Missing recommended section: '{SKILLS_SECTION_HEADING}' "
                "(declare Skills dependencies for traceability)"
            )
            file_warnings.append(msg)

        # --- Heading order check (R07) ---
        heading_issues = check_heading_order(content, agent_file.name)
        for issue in heading_issues:
            if args.strict:
                file_errors.append(f"Heading: {issue}")
            else:
                file_warnings.append(f"Heading: {issue}")

        file_results.append(
            {"path": agent_file, "errors": file_errors, "warnings": file_warnings}
        )

    # --- Pass 2: print results ---
    for result in file_results:
        path = result["path"]
        errs = result["errors"]
        warns = result["warnings"]

        if errs:
            for msg in errs:
                print(f"❌ {path}: {msg}")
            total_errors += len(errs)
        elif warns:
            for msg in warns:
                print(f"⚠️  {path}: {msg}")
        else:
            print(f"✅ {path}")

        # Print warnings even when there are errors
        if errs and warns:
            for msg in warns:
                print(f"⚠️  {path}: {msg}")

        total_warnings += len(warns)

    # --- Summary ---
    print()
    print("=" * 60)
    print(f"  Files checked : {len(file_results)}")
    print(f"  Errors        : {total_errors}")
    print(f"  Warnings      : {total_warnings}")
    if args.strict:
        print("  Mode          : strict (recommended violations = errors)")
    print("=" * 60)

    if total_errors > 0:
        print(f"\n::error::Found {total_errors} validation error(s) in .agent.md files")
        return 1

    if total_warnings > 0:
        print(f"\n⚠️  Found {total_warnings} warning(s) (non-blocking)")

    print("\nAll .agent.md files validated successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
