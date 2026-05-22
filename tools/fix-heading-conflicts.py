#!/usr/bin/env python3
"""S5d 手動修正スクリプト: 11 conflict ファイルの個別対応.

3 パターンを処理:
- A: `## N) 禁止事項（このタスク固有）` → `## N) タスク固有の禁止事項` (6 Batch + 1 ARD)
- B: `## N) 成果物保存` → `### N.1) 成果物保存` (demote to H3)
- C: `## N) 出力ルール` → `### N) 出力ルール` (demote to H3, 3 ARD files)
- D: Arch-ARD-BusinessAnalysis-Untargeted の本文中 `## 禁止事項` (pre-existing dup) は L412 を `### 禁止事項（プロンプト本文内）` に降格
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS = REPO_ROOT / ".github" / "agents"

# Pattern A
PATTERN_A: dict[str, list[tuple[str, str]]] = {
    "Arch-Dataflow-TDD-TestSpec.agent.md": [
        ("## 7) 禁止事項（このタスク固有）", "## 7) タスク固有の禁止事項"),
    ],
    "Dev-Dataflow-DataDeploy.agent.md": [
        ("## 8) 禁止事項（このタスク固有）", "## 8) タスク固有の禁止事項"),
    ],
    "Dev-Dataflow-DataServiceSelect.agent.md": [
        ("## 8) 禁止事項（このタスク固有）", "## 8) タスク固有の禁止事項"),
    ],
    "Dev-Dataflow-FunctionsDeploy.agent.md": [
        ("## 8) 禁止事項（このタスク固有）", "## 8) タスク固有の禁止事項"),
    ],
    "Dev-Dataflow-ServiceCoding.agent.md": [
        ("## 7) 禁止事項（このタスク固有）", "## 7) タスク固有の禁止事項"),
    ],
    "Dev-Dataflow-TestCoding.agent.md": [
        ("## 7) 禁止事項（このタスク固有）", "## 7) タスク固有の禁止事項"),
    ],
}

# Pattern B: demote 成果物保存
PATTERN_B = {
    "Arch-ImprovementPlanner.agent.md": [
        ("## 4) 成果物保存", "### 4.1) 成果物保存"),
    ],
    "QA-CodeQualityScan.agent.md": [
        ("## 4) 成果物保存", "### 4.1) 成果物保存"),
    ],
}

# Pattern C: demote 出力ルール (3 ARD files)
PATTERN_C = {
    "Arch-ARD-BusinessAnalysis-Targeted.agent.md": [
        ("## 5) 出力ルール", "### 5) 出力ルール"),
    ],
    "Arch-ARD-BusinessAnalysis-Untargeted.agent.md": [
        ("## 5) 出力ルール", "### 5) 出力ルール"),
        # Pattern D: 本文中の `## 禁止事項` (L412) を降格。
        # L13 の標準 `## 禁止事項` は残し、L412 の Prompt 本文内のものを降格。
        # ファイル内に `## 禁止事項` が 2 個ある場合のうち 2 個目のみを置換。
    ],
    "Arch-ARD-UseCaseCatalog.agent.md": [
        ("## 5) 出力ルール", "### 5) 出力ルール"),
    ],
}


def apply_replacements(path: Path, replacements: list[tuple[str, str]]) -> int:
    text = path.read_text(encoding="utf-8")
    count = 0
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new, 1)  # 最初の 1 件のみ
            count += 1
    path.write_text(text, encoding="utf-8")
    return count


def handle_untargeted_dup(path: Path) -> bool:
    """Arch-ARD-BusinessAnalysis-Untargeted の本文中 `## 禁止事項` (2 個目) を降格."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    seen = 0
    for i, line in enumerate(lines):
        if line.rstrip() == "## 禁止事項":
            seen += 1
            if seen == 2:
                # 2 個目を `### 禁止事項（プロンプト本文内テンプレート）` に降格
                lines[i] = "### 禁止事項（プロンプト本文内テンプレート）\n"
                path.write_text("".join(lines), encoding="utf-8")
                return True
    return False


def main() -> None:
    total = 0
    for fname, reps in {**PATTERN_A, **PATTERN_B, **PATTERN_C}.items():
        path = AGENTS / fname
        if not path.exists():
            print(f"[MISSING] {fname}")
            continue
        c = apply_replacements(path, reps)
        print(f"[FIXED] {fname}: {c} replacement(s)")
        total += c
    # Pattern D
    p = AGENTS / "Arch-ARD-BusinessAnalysis-Untargeted.agent.md"
    if handle_untargeted_dup(p):
        print(f"[FIXED-D] {p.name}: demoted 2nd `## 禁止事項`")
        total += 1
    print(f"\nTotal replacements: {total}")


if __name__ == "__main__":
    main()
