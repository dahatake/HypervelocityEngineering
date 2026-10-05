"""要求定義書自身の active 要件と履歴記述の整合性を検査する。"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / ".github" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from hve_requirement_mapping import (  # noqa: E402
    definition_ids_in_line,
    iter_requirement_definitions,
    requirement_status_for_line,
    visible_markdown_lines,
)


_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
import re
_EXTERNAL_LINK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _read_document() -> str:
    return _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig")


def _markdown_link_targets(line: str) -> list[str]:
    targets: list[str] = []
    cursor = 0
    while True:
        label_start = line.find("[", cursor)
        if label_start < 0:
            return targets
        label_end = line.find("](", label_start + 1)
        if label_end < 0:
            return targets
        depth = 1
        target_start = label_end + 2
        end = target_start
        while end < len(line) and depth:
            if line[end] == "(":
                depth += 1
            elif line[end] == ")":
                depth -= 1
            end += 1
        if depth:
            return targets
        raw = line[target_start : end - 1].strip()
        if raw.startswith("<") and ">" in raw:
            target = raw[1 : raw.index(">")]
        else:
            target = re.split(r"\s+(?=[\"'(])", raw, maxsplit=1)[0]
        targets.append(target)
        cursor = end


def _active_definition_locations() -> dict[str, list[int]]:
    locations: defaultdict[str, list[int]] = defaultdict(list)
    for line_number, _section, identifier, status, _line in iter_requirement_definitions(
        _read_document()
    ):
        if status == "active-or-described":
            locations[identifier].append(line_number)
    return dict(locations)


def _section(heading_prefix: str) -> str:
    lines = _read_document().splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(heading_prefix)]
    assert len(starts) == 1, f"{heading_prefix!r} の見出しが {len(starts)} 件見つかった"
    start = starts[0]
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    for end in range(start + 1, len(lines)):
        heading = re.match(r"^(#{1,6})\s+", lines[end])
        if heading and len(heading.group(1)) <= level:
            return "\n".join(lines[start:end])
    return "\n".join(lines[start:])


def _active_definition_line(requirement_id: str) -> str:
    locations = _active_definition_locations().get(requirement_id, [])
    assert len(locations) == 1, (
        f"active {requirement_id} の定義行が {len(locations)} 件見つかった: {locations}"
    )
    return _read_document().splitlines()[locations[0] - 1]


def _table_row(section: str, row_id: str) -> str:
    pattern = re.compile(rf"^\|\s*{re.escape(row_id)}\s*\|")
    rows = [line for line in section.splitlines() if pattern.match(line)]
    assert len(rows) == 1, f"{row_id} の表行が {len(rows)} 件見つかった"
    return rows[0]


def _repository_local_link(target: str) -> str | None:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if target.startswith("#") or target.startswith("//"):
        return None
    if _EXTERNAL_LINK_RE.match(target) and not _WINDOWS_ABSOLUTE_RE.match(target):
        return None
    return unquote(target.split("#", 1)[0])


def test_active_definition_ids_are_unique() -> None:
    duplicates = {
        requirement_id: lines
        for requirement_id, lines in _active_definition_locations().items()
        if len(lines) > 1
    }
    details = ", ".join(
        f"{requirement_id}={lines}"
        for requirement_id, lines in sorted(duplicates.items())
    )
    assert duplicates == {}, f"active requirement definition IDs are duplicated: {details}"


def test_active_definition_parser_accepts_section_suffixed_requirement_ids() -> None:
    fixture = "- **FR-TEST-01-§3.2**: fixture"
    assert definition_ids_in_line(fixture) == ["FR-TEST-01-§3.2"]


def test_hidden_or_indented_requirement_definitions_are_not_visible() -> None:
    fixture = """\
<!-- - **FR-HIDDEN-01**: hidden -->
```markdown
- **FR-HIDDEN-02**: hidden
```
    - **FR-HIDDEN-03**: hidden
- **FR-VISIBLE-01**: visible
"""
    found = [
        identifier
        for _line_number, line in visible_markdown_lines(fixture)
        for identifier in definition_ids_in_line(line)
    ]
    assert found == ["FR-VISIBLE-01"]


def test_requirement_status_uses_structural_removal_not_prose_words() -> None:
    active = "- **FR-TEST-01**: 未対応入力は拒否する。"
    removed = "- ~~**FR-TEST-02**: old~~ → **廃止（v1）**"
    assert requirement_status_for_line(active) == "active-or-described"
    assert requirement_status_for_line(removed) == "deprecated-or-removed"


def test_repository_local_markdown_links_resolve_from_the_repository_root() -> None:
    root = _REPO_ROOT.resolve()
    missing: list[str] = []
    for line_number, line in enumerate(_read_document().splitlines(), start=1):
        for raw_target in _markdown_link_targets(line):
            target = _repository_local_link(raw_target)
            if not target:
                if raw_target == "":
                    missing.append(f"line {line_number}: empty link target")
                continue
            candidate = (root / target.lstrip("/")).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                missing.append(f"line {line_number}: {target} (repository escape)")
                continue
            if not candidate.exists():
                missing.append(f"line {line_number}: {target}")
    assert missing == [], "repository-local Markdown links do not resolve:\n" + "\n".join(missing)


def test_link_parser_keeps_empty_alt_images_and_windows_absolute_paths_in_scope() -> None:
    assert _markdown_link_targets("![](images/example.svg)") == ["images/example.svg"]
    assert _markdown_link_targets('[doc](docs/a(b).md "title")') == ["docs/a(b).md"]
    assert _markdown_link_targets("[broken]()") == [""]
    assert _repository_local_link(r"C:\outside\file.md") == r"C:\outside\file.md"


def test_section_1_4_marks_date_and_sha_as_an_initial_reverse_extraction_baseline() -> None:
    section = _section("### 1.4 ")

    assert "確認日" in section
    assert "commit SHA" in section
    assert "確認日: 2026-05-12" in section
    assert "commit SHA: `48326f3ea5fa55b65c262a4eb6e0cccea261bd6f`" in section
    assert "初期逆抽出ベースライン" in section
    assert "現在のスナップショットを示すものではない" in section


def test_resolved_tbd_06_does_not_contradict_the_active_ard_surface_contract() -> None:
    active_requirement = _active_definition_line("FR-WF-ARD-01")
    tbd_row = _table_row(_section("## 12. "), "TBD-06")

    assert "CLI / GUI / Cloud Orchestrator の 3 面" in active_requirement
    stale_claims = [
        phrase
        for phrase in ("CLI / GUI 専用", "CLI / GUI Orchestrator 専用")
        if phrase in tbd_row
    ]
    assert stale_claims == [], f"TBD-06 が旧 2 面契約を主張している: {stale_claims}"
    canonical = "ARD は CLI / GUI / Cloud Orchestrator の 3 面対応として確定"
    assert canonical in tbd_row


def test_fr_cloud_22_does_not_contradict_resolved_tbd_07() -> None:
    active_requirement = _active_definition_line("FR-CLOUD-22")
    tbd_row = _table_row(_section("## 12. "), "TBD-07")

    assert "解消" in tbd_row
    assert "主要 reusable workflow" in tbd_row and "存在する" in tbd_row
    stale_claims = [phrase for phrase in ("要確認", "未確認") if phrase in active_requirement]
    assert stale_claims == [], f"FR-CLOUD-22 が確認済み事項を未確認としている: {stale_claims}"
    canonical = "主要 reusable workflow の同等チェックも確認済み"
    assert canonical in active_requirement


def test_nfr_perf_03_remains_explicitly_undefined_until_tbd_09_is_resolved() -> None:
    performance_row = _table_row(_section("## 7. "), "NFR-PERF-03")
    tbd_row = _table_row(_section("## 12. "), "TBD-09")

    assert "未定義" in performance_row
    assert "KPI" in performance_row and "SLA" in performance_row
    assert "保留" in tbd_row
    assert "運用データ蓄積後" in tbd_row
