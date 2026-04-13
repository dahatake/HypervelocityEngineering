#!/usr/bin/env python3
"""Validate .agent.md frontmatter in .github/agents/"""

import re
import sys
from pathlib import Path

AGENTS_DIR = Path(".github/agents")
SKILLS_BASE = Path(".github/skills")
errors = 0

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
    m = re.search(r'^description:\s*[>|]\s*\n((?:[ \t]+.+\n)+)', fm_text, re.MULTILINE)
    if m:
        desc = re.sub(r'^[ \t]+', '', m.group(1), flags=re.MULTILINE).strip()
        return len(desc)
    m2 = re.search(r'^description:\s*(.+)', fm_text, re.MULTILINE)
    if m2:
        return len(m2.group(1).strip(' "\''))
    return 0

# Build set of known skill names
known_skills = {p.parent.name for p in SKILLS_BASE.rglob("SKILL.md")}

for agent_file in sorted(AGENTS_DIR.glob("*.agent.md")):
    content = agent_file.read_text(encoding="utf-8")
    file_errors = 0

    fm = extract_frontmatter(content)
    if fm is None:
        print(f"❌ Missing or malformed frontmatter: {agent_file}")
        errors += 1
        continue

    # Check for name field
    if not re.search(r'^name:', fm, re.MULTILINE):
        print(f"❌ Missing 'name' in frontmatter: {agent_file}")
        errors += 1
        file_errors += 1

    # Check for description field
    if not re.search(r'^description:', fm, re.MULTILINE):
        print(f"❌ Missing 'description' in frontmatter: {agent_file}")
        errors += 1
        file_errors += 1

    # Check description length (1024 chars max) - warn only
    desc_len = get_description_length(fm)
    if desc_len > 1024:
        print(f"⚠️  Description exceeds 1024 chars ({desc_len}): {agent_file}")

    if file_errors == 0:
        print(f"✅ {agent_file}")

if errors > 0:
    print(f"\n::error::Found {errors} validation errors in .agent.md files")
    sys.exit(1)

print(f"\nAll .agent.md files validated successfully")
