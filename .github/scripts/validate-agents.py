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
