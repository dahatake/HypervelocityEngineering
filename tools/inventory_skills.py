#!/usr/bin/env python3
"""SKILL.md の frontmatter / 本文インベントリを生成する。"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
WHITESPACE_RE = re.compile(r"\s+")
PREAMBLE_REFERENCE_RE = re.compile(
    r"agent-common-preamble(?:/SKILL\.md)?",
    re.IGNORECASE,
)
DEFAULT_COMMON_PREAMBLE = (
    ".github/skills/agent-common-preamble/SKILL.md"
)


@dataclass(frozen=True)
class SkillFile:
    path: Path
    frontmatter_text: str
    body_text: str
    frontmatter: Dict[str, Any]


def _read_skill(path: Path) -> SkillFile:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if match is None:
        raise ValueError(f"YAML frontmatter が見つかりません: {path}")

    frontmatter_text = match.group(1)
    body_text = text[match.end() :]
    frontmatter = _parse_frontmatter(frontmatter_text)
    if not isinstance(frontmatter, dict):
        raise ValueError(f"frontmatter が辞書ではありません: {path}")

    return SkillFile(
        path=path,
        frontmatter_text=frontmatter_text,
        body_text=body_text,
        frontmatter=frontmatter,
    )


def _normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_frontmatter(frontmatter_text: str) -> Dict[str, Any]:
    lines = frontmatter_text.splitlines()
    parsed: Dict[str, Any] = {}
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith((" ", "\t")):
            raise ValueError(f"top-level 以外の行から開始しました: {line!r}")

        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if match is None:
            raise ValueError(f"frontmatter を解釈できません: {line!r}")

        key = match.group(1)
        raw_value = (match.group(2) or "").strip()

        if raw_value in {">", "|", ">-", "|-"}:
            index += 1
            block_lines: List[str] = []
            while index < len(lines):
                next_line = lines[index]
                if next_line.startswith((" ", "\t")):
                    block_lines.append(next_line.lstrip())
                    index += 1
                    continue
                if not next_line.strip():
                    block_lines.append("")
                    index += 1
                    continue
                break
            parsed[key] = _normalize_text("\n".join(block_lines))
            continue

        if raw_value == "":
            index += 1
            nested_lines: List[str] = []
            while index < len(lines):
                next_line = lines[index]
                if next_line.startswith((" ", "\t")) or not next_line.strip():
                    nested_lines.append(next_line)
                    index += 1
                    continue
                break

            list_items = [
                _strip_quotes(item_match.group(1).strip())
                for nested_line in nested_lines
                if (item_match := re.match(r"^\s*-\s+(.*)$", nested_line))
            ]
            parsed[key] = list_items if list_items else {}
            continue

        parsed[key] = _strip_quotes(raw_value)
        index += 1

    return parsed


def _body_lines_for_similarity(body_text: str) -> List[str]:
    lines = [line.strip() for line in body_text.splitlines()]
    return [line for line in lines if line]


def _similarity_against_common_preamble(
    body_text: str,
    common_body_text: str,
) -> Tuple[bool, float, int]:
    body_lines = _body_lines_for_similarity(body_text)
    common_lines = _body_lines_for_similarity(common_body_text)
    if not body_lines or not common_lines:
        return False, 0.0, 0

    max_lines = min(len(body_lines), len(common_lines), 80)
    best_ratio = 0.0
    best_line_count = 0
    for line_count in range(1, max_lines + 1):
        candidate = _normalize_text("\n".join(body_lines[:line_count]))
        target = _normalize_text("\n".join(common_lines[:line_count]))
        if not candidate or not target:
            continue
        ratio = SequenceMatcher(None, candidate, target).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_line_count = line_count

    return best_ratio >= 0.80, best_ratio, best_line_count


def _count_tools(frontmatter: Dict[str, Any]) -> int:
    tools = frontmatter.get("tools")
    if isinstance(tools, list):
        return len(tools)
    return 0


def _description_chars(frontmatter: Dict[str, Any]) -> int:
    description = frontmatter.get("description")
    if isinstance(description, str):
        return len(description)
    return 0


def build_inventory(
    repo_root: Path,
    common_preamble_path: Path,
) -> List[Dict[str, Any]]:
    skill_paths = sorted((repo_root / ".github" / "skills").rglob("SKILL.md"))
    common_skill = _read_skill(common_preamble_path)
    common_body_text = common_skill.body_text
    rows: List[Dict[str, Any]] = []

    for skill_path in skill_paths:
        skill = _read_skill(skill_path)
        relative_path = skill_path.relative_to(repo_root).as_posix()
        has_reference = bool(PREAMBLE_REFERENCE_RE.search(skill.body_text))
        has_similarity, ratio, line_count = _similarity_against_common_preamble(
            skill.body_text,
            common_body_text,
        )
        rows.append(
            {
                "path": relative_path,
                "bytes": skill_path.stat().st_size,
                "frontmatter_bytes": len(skill.frontmatter_text.encode("utf-8")),
                "body_bytes": len(skill.body_text.encode("utf-8")),
                "description_chars": _description_chars(skill.frontmatter),
                "tools_count": _count_tools(skill.frontmatter),
                "has_common_preamble": "yes" if (has_reference or has_similarity) else "no",
                "common_preamble_similarity": f"{ratio:.4f}",
                "common_preamble_similarity_lines": line_count,
            }
        )

    return rows


def _write_csv(rows: Iterable[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "path",
        "bytes",
        "frontmatter_bytes",
        "body_bytes",
        "description_chars",
        "tools_count",
        "has_common_preamble",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})


def _write_markdown(rows: Iterable[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Skill common preamble audit",
        "",
        "| path | has_common_preamble | similarity | compared_lines |",
        "|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['path']}` | {row['has_common_preamble']} | {row['common_preamble_similarity']} | {row['common_preamble_similarity_lines']} |"
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory .github/skills/**/SKILL.md")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="repository root path",
    )
    parser.add_argument(
        "--output",
        default="measurements/skills-inventory-before.csv",
        help="inventory CSV output path",
    )
    parser.add_argument(
        "--common-preamble",
        default=DEFAULT_COMMON_PREAMBLE,
        help="agent-common-preamble skill path",
    )
    parser.add_argument(
        "--audit-output",
        default=None,
        help="optional markdown output path for similarity audit",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(args.repo_root).resolve()
    common_preamble_path = (repo_root / args.common_preamble).resolve()
    rows = build_inventory(repo_root, common_preamble_path)

    _write_csv(rows, (repo_root / args.output).resolve())
    if args.audit_output:
        _write_markdown(rows, (repo_root / args.audit_output).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
