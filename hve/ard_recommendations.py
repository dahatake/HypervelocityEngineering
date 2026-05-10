"""ard_recommendations.py — `docs/company-business-requirement.md` の Strategic Recommendations 抽出・ID 付与。

ARD ワークフローの Step 1（Untargeted 事業分析）の出力ファイルから「## 6. Strategic
Recommendations（戦略提言）」セクション配下の推奨戦略を抽出し、`SR-1`, `SR-2`, ... の
ID を付与する。

後続の Step 2 では、このうち 1 件の SR-ID を選択し、その内容に基づいて
`target_business` パラメータの説明文を生成する（PR#6・PR#7 で実装）。

PR#4 のスコープ:
- parse_recommendations: 抽出のみ（読み取り専用）
- annotate_with_ids: ID をファイルに書き戻す（冪等）

抽出ロジックは以下の順で試行する:
1. `### 6.1 推奨戦略` 表内の行
2. セクション内の `### ` 第3レベル見出し
3. セクション内の `**(N) タイトル**` 太字番号付きパターン
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_SECTION_HEADING_RE = re.compile(r"^(#{1,2})\s*6\.\s*(?P<title>.+?)\s*$")
_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+.+$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?$")
_PARAGRAPH_RE = re.compile(r"(?P<prefix>\*\*\((?P<num>\d+)\)\s*)(?P<title>.+?)(?P<suffix>\*\*)")
_ID_PREFIX_RE = re.compile(r"^\[?(SR-\d+)\]?\s*", re.IGNORECASE)
_NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)+\s+")
_GENERIC_HEADING_TITLES = {"推奨戦略と根拠"}


@dataclass(frozen=True)
class Recommendation:
    """推奨戦略 1 件の情報。"""

    id: str
    title: str
    rationale: str
    source_line: int


@dataclass(frozen=True)
class _RawRecommendation:
    title: str
    rationale: str
    source_line: int
    existing_id: Optional[str]
    kind: str
    line_index: int
    heading_marks: str = ""
    title_column_index: int = -1


def _is_target_section_title(title: str) -> bool:
    normalized = title.casefold()
    return any(
        token in normalized
        for token in ("strategic recommendations", "戦略提言", "推奨戦略")
    )


def _strip_existing_id(title: str) -> tuple[Optional[str], str]:
    stripped = title.strip()
    match = _ID_PREFIX_RE.match(stripped)
    if not match:
        return None, stripped
    return match.group(1).upper(), stripped[match.end():].strip()


def _find_target_section(lines: list[str]) -> tuple[int, int] | None:
    for index, line in enumerate(lines):
        match = _SECTION_HEADING_RE.match(line.strip())
        if not match or not _is_target_section_title(match.group("title")):
            continue
        level = len(match.group(1))
        end_index = len(lines)
        for candidate in range(index + 1, len(lines)):
            next_line = lines[candidate].strip()
            next_match = _ANY_HEADING_RE.match(next_line)
            if next_match and len(next_match.group(1)) <= level:
                end_index = candidate
                break
        return index + 1, end_index
    return None


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _find_table_recommendations(lines: list[str], start: int, end: int) -> list[_RawRecommendation]:
    for index in range(start, end):
        line = lines[index].strip()
        if not line.startswith("|"):
            continue
        columns = _split_table_row(line)
        title_index = next((i for i, cell in enumerate(columns) if "推奨戦略" in cell), -1)
        no_index = next((i for i, cell in enumerate(columns) if cell in {"No.", "No"}), -1)
        rationale_index = next((i for i, cell in enumerate(columns) if "根拠" in cell), -1)
        if title_index < 0 or no_index < 0:
            continue

        recommendations: list[_RawRecommendation] = []
        for row_index in range(index + 1, end):
            row = lines[row_index].strip()
            if not row.startswith("|"):
                if recommendations:
                    return recommendations
                break
            if _TABLE_SEPARATOR_RE.match(row):
                continue
            cells = _split_table_row(row)
            if len(cells) <= max(title_index, no_index):
                continue
            if not cells[no_index].strip():
                continue
            title = cells[title_index].strip()
            if not title:
                continue
            existing_id, clean_title = _strip_existing_id(title)
            rationale = ""
            if rationale_index >= 0 and len(cells) > rationale_index:
                rationale = cells[rationale_index].strip()
            recommendations.append(
                _RawRecommendation(
                    title=clean_title,
                    rationale=rationale,
                    source_line=row_index + 1,
                    existing_id=existing_id,
                    kind="table",
                    line_index=row_index,
                    title_column_index=title_index,
                )
            )
        if recommendations:
            return recommendations
    return []


def _is_generic_heading_title(title: str) -> bool:
    normalized = title.strip()
    return normalized in _GENERIC_HEADING_TITLES or normalized.startswith("実行ステップ")


def _find_heading_recommendations(lines: list[str], start: int, end: int) -> list[_RawRecommendation]:
    recommendations: list[_RawRecommendation] = []
    for index in range(start, end):
        line = lines[index].rstrip()
        if not line.startswith("### "):
            continue
        title = line[4:].strip()
        if _NUMBERED_HEADING_RE.match(title) or _is_generic_heading_title(title):
            continue
        existing_id, clean_title = _strip_existing_id(title)
        if not clean_title:
            continue
        recommendations.append(
            _RawRecommendation(
                title=clean_title,
                rationale="",
                source_line=index + 1,
                existing_id=existing_id,
                kind="heading",
                line_index=index,
                heading_marks="###",
            )
        )
    return recommendations


def _find_paragraph_recommendations(lines: list[str], start: int, end: int) -> list[_RawRecommendation]:
    recommendations: list[_RawRecommendation] = []
    for index in range(start, end):
        match = _PARAGRAPH_RE.search(lines[index])
        if not match:
            continue
        existing_id, clean_title = _strip_existing_id(match.group("title"))
        if not clean_title:
            continue
        recommendations.append(
            _RawRecommendation(
                title=clean_title,
                rationale="",
                source_line=index + 1,
                existing_id=existing_id,
                kind="paragraph",
                line_index=index,
            )
        )
    return recommendations


def _extract_raw_recommendations(lines: list[str]) -> list[_RawRecommendation]:
    section = _find_target_section(lines)
    if section is None:
        return []
    start, end = section
    for extractor in (
        _find_table_recommendations,
        _find_heading_recommendations,
        _find_paragraph_recommendations,
    ):
        recommendations = extractor(lines, start, end)
        if recommendations:
            return recommendations
    return []


def _assign_ids(raw_recommendations: list[_RawRecommendation]) -> list[tuple[_RawRecommendation, Recommendation]]:
    assigned: list[tuple[_RawRecommendation, Recommendation]] = []
    used_numbers = {
        int(raw.existing_id.split("-", 1)[1])
        for raw in raw_recommendations
        if raw.existing_id
    }
    next_number = 1
    for raw in raw_recommendations:
        if raw.existing_id:
            recommendation_id = raw.existing_id
        else:
            while next_number in used_numbers:
                next_number += 1
            recommendation_id = f"SR-{next_number}"
            used_numbers.add(next_number)
            next_number += 1
        assigned.append(
            (
                raw,
                Recommendation(
                    id=recommendation_id,
                    title=raw.title,
                    rationale=raw.rationale,
                    source_line=raw.source_line,
                ),
            )
        )
    return assigned


def parse_recommendations(md_path: Path | str) -> list[Recommendation]:
    """Markdown ファイルから Strategic Recommendations を抽出して返す。

    ファイルが存在しない場合や該当セクションがない場合は空リストを返す（例外なし）。
    既存の SR-N ID は再利用し、ID 未付与の項目には新規 ID を採番する。
    """

    path = Path(md_path)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [recommendation for _, recommendation in _assign_ids(_extract_raw_recommendations(lines))]


def annotate_with_ids(md_path: Path | str) -> list[Recommendation]:
    """parse_recommendations の結果をファイルに書き戻す（ID を Markdown に追記）。

    - 表形式の場合: 「推奨戦略」列の値の先頭に `[SR-N] ` を付与（既に付いていれば変更しない）
    - 見出し形式の場合: 見出しテキスト先頭に `[SR-N] ` を付与
    - 段落形式の場合: `**(N) タイトル**` を `**(N) [SR-N] タイトル**` に置換
    - 副作用: ファイルを上書き保存（同一内容なら書き込みスキップ）

    Returns: 付与された Recommendation のリスト
    """

    path = Path(md_path)
    if not path.exists():
        return []
    try:
        original = path.read_text(encoding="utf-8")
    except OSError:
        return []

    lines = original.splitlines()
    assigned = _assign_ids(_extract_raw_recommendations(lines))
    if not assigned:
        return []

    updated_lines = list(lines)
    for raw, recommendation in assigned:
        line = updated_lines[raw.line_index]
        if raw.kind == "table":
            columns = _split_table_row(line)
            if len(columns) <= raw.title_column_index:
                continue
            existing_id, clean_title = _strip_existing_id(columns[raw.title_column_index])
            if existing_id:
                continue
            columns[raw.title_column_index] = f"[{recommendation.id}] {clean_title}"
            updated_lines[raw.line_index] = "| " + " | ".join(columns) + " |"
        elif raw.kind == "heading":
            current_title = line[4:].strip()
            existing_id, clean_title = _strip_existing_id(current_title)
            if existing_id:
                continue
            updated_lines[raw.line_index] = f"{raw.heading_marks} [{recommendation.id}] {clean_title}"
        elif raw.kind == "paragraph":
            match = _PARAGRAPH_RE.search(line)
            if not match:
                continue
            existing_id, clean_title = _strip_existing_id(match.group("title"))
            if existing_id:
                continue
            replacement = f"{match.group('prefix')}[{recommendation.id}] {clean_title}{match.group('suffix')}"
            updated_lines[raw.line_index] = _PARAGRAPH_RE.sub(replacement, line, count=1)

    updated_content = "\n".join(updated_lines)
    if original.endswith("\n"):
        updated_content += "\n"
    if updated_content != original:
        path.write_text(updated_content, encoding="utf-8")
    return parse_recommendations(path)
