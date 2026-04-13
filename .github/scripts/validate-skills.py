#!/usr/bin/env python3
"""Validate SKILL.md frontmatter in .github/skills/"""

import re
import sys
from pathlib import Path

SKILLS_BASE = Path(".github/skills")
errors = 0
warnings = 0

def extract_frontmatter(content):
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---\n"):
        return None
    end = content.find("\n---\n", 4)
    if end < 0:
        return None
    return content[4:end]

def get_description_length(fm_text):
    """Get the length of the description field value."""
    # Multi-line YAML > or | style
    m = re.search(r'^description:\s*[>|]\s*\n((?:[ \t]+.+\n)+)', fm_text, re.MULTILINE)
    if m:
        desc = re.sub(r'^[ \t]+', '', m.group(1), flags=re.MULTILINE).strip()
        return len(desc)
    # Single-line style  
    m2 = re.search(r'^description:\s*(.+)', fm_text, re.MULTILINE)
    if m2:
        return len(m2.group(1).strip(' "\''))
    return 0

for skill_file in sorted(SKILLS_BASE.rglob("SKILL.md")):
    folder_name = skill_file.parent.name
    content = skill_file.read_text(encoding="utf-8")
    file_errors = 0

    fm = extract_frontmatter(content)
    if fm is None:
        print(f"❌ Missing or malformed frontmatter: {skill_file}")
        errors += 1
        continue

    # Check for name field
    if not re.search(r'^name:', fm, re.MULTILINE):
        print(f"❌ Missing 'name' in frontmatter: {skill_file}")
        errors += 1
        file_errors += 1

    # Check for description field
    if not re.search(r'^description:', fm, re.MULTILINE):
        print(f"❌ Missing 'description' in frontmatter: {skill_file}")
        errors += 1
        file_errors += 1

    # Check name matches folder name
    m = re.search(r'^name:\s*(.+)', fm, re.MULTILINE)
    if m:
        skill_name = m.group(1).strip(' "\'')
        if skill_name != folder_name:
            print(f"❌ Name '{skill_name}' does not match folder '{folder_name}': {skill_file}")
            errors += 1
            file_errors += 1

    # Check description length (1024 chars max)
    desc_len = get_description_length(fm)
    if desc_len > 1024:
        print(f"❌ Description exceeds 1024 chars ({desc_len}): {skill_file}")
        errors += 1
        file_errors += 1

    # Check metadata.version exists (warning)
    if not re.search(r'^\s+version:', fm, re.MULTILINE):
        print(f"⚠️  Missing metadata.version: {skill_file}")
        warnings += 1

    # Check USE FOR exists (warning, skip Microsoft official Skills)
    if not re.search(r'author:\s*Microsoft', fm) and 'USE FOR:' not in content:
        print(f"⚠️  Recommend adding USE FOR: trigger: {skill_file}")
        warnings += 1

    if file_errors == 0:
        print(f"✅ {skill_file}")

if errors > 0:
    print(f"\n::error::Found {errors} validation errors in SKILL.md files")
    sys.exit(1)

if warnings > 0:
    print(f"\n⚠️  Found {warnings} warnings (non-blocking)")

print(f"\nAll SKILL.md files validated successfully")
