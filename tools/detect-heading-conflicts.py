#!/usr/bin/env python3
"""dry-run の rename 適用後に、同一ファイル内で重複 H2 が発生するファイルを検出する.

S4 の auto/manual 分類のための補助スクリプト。
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# normalize-agent-headings.py は dash 含むので importlib で読む
import importlib.util

spec = importlib.util.spec_from_file_location(
    "normalize_module",
    Path(__file__).resolve().parent / "normalize-agent-headings.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore[union-attr]

agents_dir = Path(__file__).resolve().parent.parent / ".github" / "agents"
conflicts: list[tuple[str, list[tuple[str, int]]]] = []
for f in sorted(agents_dir.glob("*.agent.md")):
    content = f.read_text(encoding="utf-8")
    if mod.should_skip(f, content):
        continue
    new_content, changes = mod.normalize_content(content)
    if not changes:
        continue
    h2s = [
        line.rstrip() for line in new_content.splitlines() if line.startswith("## ")
    ]
    counter = Counter(h2s)
    dups = [(h, c) for h, c in counter.items() if c > 1]
    if dups:
        conflicts.append((f.name, dups))

print(f"Conflict files: {len(conflicts)}")
for name, dups in conflicts:
    print(f"\n[CONFLICT] {name}")
    for h, c in dups:
        print(f"  {c}x  {h}")
