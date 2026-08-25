"""FR-WF-ARD-03: ARD要求表とWorkflow registryのparity契約。

§13.12 の Step ID 集合が registry と一致することは、全 Workflow 横断の単一実装
（FR-MAINT-09 / `hve/tests/test_requirement_section13_parity.py`）が担う。
本ファイルは ARD 固有の契約（実 Step 件数・4 表示グループ対応・既定 tuple）だけを検査する（FR-MAINT-07）。
"""

from __future__ import annotations

import re
from pathlib import Path

# FR-WF-ARD-03がこのprivate mapをSSOTとして名指すための意図的な契約結合。
from hve.workflow_registry import _WORKFLOW_GROUP_MAPS

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_SECTION_START = "### 13.12 ARD — Auto Requirement Definition"
_SECTION_END = "### 13.13 ゲート条件（受入基準）"
_GROUP_HEADER = ("表示グループ", "利用者向け名称", "展開する実 Step")
_STEP_HEADER = ("Step", "タイトル", "依存", "Fan-out", "生成ファイル")
_DELIMITER_RE = re.compile(r"^:?-+:?$")
_DEFAULT_TUPLE_RE = re.compile(r"ARD_DEFAULT_GROUP_IDS\s*=\s*\(([^)]*)\)")


def _read_requirement_section() -> str:
    text = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig")
    assert text.count(_SECTION_START) == 1
    assert text.count(_SECTION_END) == 1
    start = text.index(_SECTION_START) + len(_SECTION_START)
    end = text.index(_SECTION_END, start)
    return text[start:end]


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table_rows(section: str, header: tuple[str, ...]) -> list[list[str]]:
    lines = section.splitlines()
    positions = [index for index, line in enumerate(lines) if line.startswith("|") and tuple(_split_row(line)) == header]
    assert len(positions) == 1, f"expected one table {header!r}, found {len(positions)}"
    start = positions[0]
    delimiter = _split_row(lines[start + 1])
    assert len(delimiter) == len(header)
    assert all(_DELIMITER_RE.fullmatch(cell) for cell in delimiter)
    rows: list[list[str]] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(_split_row(line))
    assert rows
    return rows


def _documented_group_map(section: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for group_cell, _title, steps_cell in _table_rows(section, _GROUP_HEADER):
        group_id = group_cell.strip("`")
        result[group_id] = re.findall(r"`([^`]+)`", steps_cell)
    return result


def _documented_step_ids(section: str) -> list[str]:
    return [row[0].strip("`") for row in _table_rows(section, _STEP_HEADER)]


def _documented_default_group_ids(section: str) -> tuple[str, ...]:
    lines = [line for line in section.splitlines() if line.startswith("- **FR-WF-ARD-03**:")]
    assert len(lines) == 1
    match = _DEFAULT_TUPLE_RE.search(lines[0])
    assert match is not None
    return tuple(re.findall(r'["\']([^"\']+)["\']', match.group(1)))


class TestArdRequirementParity:
    def test_requirement_declares_eight_unique_steps(self) -> None:
        """ARD 固有の件数不変（10 実 Step）と重複不在。registry との集合一致は横断テストが担う。"""
        section = _read_requirement_section()
        documented = _documented_step_ids(section)

        assert len(documented) == 10
        assert len(documented) == len(set(documented))

    def test_requirement_group_map_matches_registry(self) -> None:
        section = _read_requirement_section()
        documented = _documented_group_map(section)
        registered = _WORKFLOW_GROUP_MAPS["ard"]

        assert len(documented) == 5
        assert documented == registered
        flattened = [step_id for steps in documented.values() for step_id in steps]
        assert len(flattened) == len(set(flattened))
        assert set(flattened) == set(_documented_step_ids(section))

    def test_default_group_ids_symbol_matches_requirement(self) -> None:
        # C1まで未実装のシンボルだけを動的取得し、他のparity検査を道連れにしない。
        import hve.workflow_registry as registry

        ARD_DEFAULT_GROUP_IDS = getattr(registry, "ARD_DEFAULT_GROUP_IDS")

        expected = _documented_default_group_ids(_read_requirement_section())
        assert isinstance(ARD_DEFAULT_GROUP_IDS, tuple)
        assert ARD_DEFAULT_GROUP_IDS == expected
        assert set(ARD_DEFAULT_GROUP_IDS) <= set(_WORKFLOW_GROUP_MAPS["ard"])
