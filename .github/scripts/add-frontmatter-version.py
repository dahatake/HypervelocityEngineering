#!/usr/bin/env python3
"""Add metadata.version to agent/skill frontmatter if missing."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Optional, Tuple

DEFAULT_VERSION = "1.0.0"
REPO_ROOT = Path(".")
TARGET_GLOBS = (
    ".github/agents/*.agent.md",
    ".github/skills/**/SKILL.md",
)


def extract_frontmatter(content: str) -> Optional[Tuple[str, int, int]]:
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end < 0:
        return None
    return content[4:end], 4, end


def has_metadata_version(frontmatter: str) -> bool:
    metadata_match = re.search(r"^metadata:\s*\n((?:[ \t]+.*\n?)*)", frontmatter, re.MULTILINE)
    if not metadata_match:
        return False
    metadata_body = metadata_match.group(1)
    return re.search(r'^[ \t]+version:\s*["\']?[^"\n\']+["\']?\s*$', metadata_body, re.MULTILINE) is not None


def add_metadata_version(frontmatter: str) -> str:
    if has_metadata_version(frontmatter):
        return frontmatter

    metadata_match = re.search(r"^metadata:\s*\n((?:[ \t]+.*\n?)*)", frontmatter, re.MULTILINE)
    if metadata_match:
        metadata_body = metadata_match.group(1)
        indent_match = re.search(r"^([ \t]+)", metadata_body, re.MULTILINE)
        indent = indent_match.group(1) if indent_match else "  "
        updated_body = f"{metadata_body}{indent}version: \"{DEFAULT_VERSION}\"\n"
        return frontmatter[: metadata_match.start(1)] + updated_body + frontmatter[metadata_match.end(1) :]

    suffix = "" if frontmatter.endswith("\n") else "\n"
    return f'{frontmatter}{suffix}metadata:\n  version: "{DEFAULT_VERSION}"\n'


def process_file(path: Path) -> bool:
    content = path.read_text(encoding="utf-8")
    extracted = extract_frontmatter(content)
    if extracted is None:
        return False
    frontmatter, start, end = extracted
    updated_frontmatter = add_metadata_version(frontmatter)
    if updated_frontmatter == frontmatter:
        return False
    updated_content = content[:start] + updated_frontmatter + content[end:]
    path.write_text(updated_content, encoding="utf-8")
    return True


def iter_target_files() -> list[Path]:
    files: list[Path] = []
    for pattern in TARGET_GLOBS:
        files.extend(sorted(REPO_ROOT.glob(pattern)))
    return files


def main() -> int:
    changed = 0
    total = 0
    for path in iter_target_files():
        total += 1
        if process_file(path):
            changed += 1
            print(f"UPDATED: {path}")
    print(f"Processed {total} files, updated {changed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
