"""§13 の Workflow Step 表と `hve/workflow_registry.py` の Step 集合の parity を横断検査する。

同種の drift は過去に 2 度発生し、そのつど当該 Workflow だけの個別テストで塞いできた。

- §13.5（ADFDV）: 旧称 ABDV / 実在しない fan-out parser / 旧パスが残存
  → `hve/tests/test_requirement_definition_adfdv_section.py`
- §13.12（ARD）: 旧 7-Step 表記のまま `2.1` / `3.x` を欠落
  → `hve/tests/test_ard_requirement_parity.py`

横断検査が無かったため、同じ drift が §13.2（AAD-WEB）と §13.3（ASDW-WEB）に残存していた。
本テストは registry へ登録された全 Workflow を対象とし、新規 Workflow が
`_SECTION_MODES` にも `_NO_SECTION_ALLOWLIST` にも載っていない場合に失敗する。

要件: hve-dev/requirement-definition.md §3.7 FR-MAINT-09
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from hve.workflow_registry import get_workflow, list_workflows

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"

_STRICT = "strict"
_SUBSET = "subset"

# Workflow ID -> (§13 の節番号, 検査モード)
#   strict: 表の Step ID 集合が registry の全 Step ID 集合と一致すること。
#   subset: 表が要約であることを本文で明示している節。記載 ID が registry に実在すればよい。
_SECTION_MODES: dict[str, tuple[str, str]] = {
    "aas": ("13.1", _STRICT),
    "aad-web": ("13.2", _STRICT),
    # §13.3 はコンテナ Step 5 件を FR-WF-OUT-04（成果物を持たない Sub-Issue 束ね）を根拠に表から省く。
    "asdw-web": ("13.3", _SUBSET),
    "adfd": ("13.4", _STRICT),
    "adfdv": ("13.5", _STRICT),
    "aag": ("13.6", _STRICT),
    "aagd": ("13.7", _STRICT),
    "akm": ("13.8", _STRICT),
    "adi": ("13.10", _STRICT),
    # §13.11 は `2.1〜2.5` の範囲表記でファイルサマリー 5 系統をまとめ、コンテナ Step を載せない。
    "adoc": ("13.11", _SUBSET),
    "ard": ("13.12", _STRICT),
}

# §13 に Step 表を持たない Workflow。除外には理由の記載を必須とする（FR-WF-OUT-09 と同じ方式）。
_NO_SECTION_ALLOWLIST: dict[str, str] = {
    "aar": "§13 に専用節が無い。Step 7 のみ §13.14 FR-WF-CONF-01 の表に記載がある。節の新設は別スコープ。",
    "ada": "§13 に専用節が無い。§13.1.1 が Step 4.1 の Data Model 共有契約だけを規定する。節の新設は別スコープ。",
}

_STEP_ID_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
_DELIMITER_RE = re.compile(r"^:?-+:?$")
# 範囲表記（`2.1〜2.5`）は要約表でだけ許容する。
_RANGE_CHARS = "〜～~"
# 連体助詞「の」は「アプリケーションリスト作成」と「アプリケーションリストの作成」のような
# 同一 Step の表記揺れを生むだけなので、別 Step の識別には使わない。
_TITLE_NOISE_RE = re.compile(r"[\s`*（）()\[\]【】「」・/／,、。．.\-–—:：]|の")


def _read_document() -> list[str]:
    return _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines()


def _section_lines(section: str) -> list[str]:
    lines = _read_document()
    heading = f"### {section} "
    starts = [i for i, line in enumerate(lines) if line.startswith(heading)]
    assert len(starts) == 1, f"§{section} の見出しが {len(starts)} 件見つかった"
    start = starts[0]
    for offset, line in enumerate(lines[start + 1 :], start + 1):
        if line.startswith("### "):
            return lines[start:offset]
    return lines[start:]


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _step_table_rows(section: str) -> list[list[str]]:
    """節内の `| Step | ... |` 表の本文行を返す。"""
    lines = _section_lines(section)
    headers = [
        i
        for i, line in enumerate(lines)
        if line.startswith("|") and _split_row(line)[:1] == ["Step"]
    ]
    assert len(headers) == 1, f"§{section} の Step 表が {len(headers)} 件見つかった"
    start = headers[0]
    assert all(_DELIMITER_RE.fullmatch(cell) for cell in _split_row(lines[start + 1]))
    rows: list[list[str]] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(_split_row(line))
    assert rows, f"§{section} の Step 表に本文行が無い"
    return rows


def _cell_tokens(cell: str) -> list[str]:
    return [token.strip().strip("`*").strip() for token in cell.split("/") if token.strip()]


def _documented_steps(section: str) -> tuple[dict[str, str], list[str]]:
    """(`Step ID -> 表のタイトル`, ID として解釈できなかったトークン) を返す。"""
    documented: dict[str, str] = {}
    unparsed: list[str] = []
    for row in _step_table_rows(section):
        title = row[1] if len(row) > 1 else ""
        for token in _cell_tokens(row[0]):
            if _STEP_ID_RE.fullmatch(token):
                documented[token] = title
            else:
                unparsed.append(token)
    return documented, unparsed


def _normalize_title(text: str) -> str:
    return _TITLE_NOISE_RE.sub("", unicodedata.normalize("NFKC", text)).casefold()


def _title_mismatches(section: str, workflow_id: str) -> list[str]:
    """表のタイトルが registry の別 Step を指している行を列挙する。

    表記の揺れ（`（TDD RED）` と `(TDD RED)`、修飾語の有無）で壊れないよう、
    正規化後の双方向包含で判定する。
    """
    documented, _ = _documented_steps(section)
    workflow = get_workflow(workflow_id)
    assert workflow is not None
    registry_titles = {step.id: step.title for step in workflow.steps}
    mismatches: list[str] = []
    for step_id, documented_title in documented.items():
        if step_id not in registry_titles:
            continue
        left = _normalize_title(documented_title)
        right = _normalize_title(registry_titles[step_id])
        if not left or not right:
            continue
        if left not in right and right not in left:
            mismatches.append(
                f"Step {step_id}: 表='{documented_title}' / registry='{registry_titles[step_id]}'"
            )
    return mismatches


class TestSectionCoverage:
    def test_every_registered_workflow_is_classified(self) -> None:
        classified = set(_SECTION_MODES) | set(_NO_SECTION_ALLOWLIST)
        registered = {workflow.id for workflow in list_workflows()}
        assert registered - classified == set(), (
            "§13 の検査モードにも allowlist にも載っていない Workflow がある: "
            f"{sorted(registered - classified)}"
        )
        assert classified - registered == set(), (
            f"registry に存在しない Workflow が分類表に残っている: {sorted(classified - registered)}"
        )

    def test_mode_and_allowlist_do_not_overlap(self) -> None:
        assert set(_SECTION_MODES) & set(_NO_SECTION_ALLOWLIST) == set()

    def test_allowlist_entries_carry_a_reason(self) -> None:
        blank = [wid for wid, reason in _NO_SECTION_ALLOWLIST.items() if not reason.strip()]
        assert blank == [], f"allowlist に理由が無い項目がある: {blank}"

    def test_declared_sections_exist(self) -> None:
        lines = _read_document()
        missing = [
            f"{wid} (§{section})"
            for wid, (section, _mode) in _SECTION_MODES.items()
            if not any(line.startswith(f"### {section} ") for line in lines)
        ]
        assert missing == [], f"宣言した §13 節が存在しない: {missing}"


@pytest.mark.parametrize(
    "workflow_id", sorted(_SECTION_MODES), ids=lambda wid: wid
)
class TestSectionStepParity:
    def test_step_ids_match_the_registry(self, workflow_id: str) -> None:
        section, mode = _SECTION_MODES[workflow_id]
        documented, _ = _documented_steps(section)
        workflow = get_workflow(workflow_id)
        assert workflow is not None
        registered = {step.id for step in workflow.steps}

        undeclared_in_registry = sorted(set(documented) - registered)
        assert undeclared_in_registry == [], (
            f"§{section} が registry に存在しない Step を記載している: {undeclared_in_registry}"
        )
        if mode == _STRICT:
            missing_from_document = sorted(registered - set(documented))
            assert missing_from_document == [], (
                f"§{section} に未記載の Step がある: {missing_from_document}"
            )

    def test_unparsed_id_tokens_are_limited_to_summary_ranges(self, workflow_id: str) -> None:
        section, mode = _SECTION_MODES[workflow_id]
        _, unparsed = _documented_steps(section)
        if mode == _STRICT:
            assert unparsed == [], (
                f"§{section} の Step 列に ID として解釈できないトークンがある: {unparsed}"
            )
            return
        invalid = [
            token for token in unparsed if not any(char in token for char in _RANGE_CHARS)
        ]
        assert invalid == [], (
            f"§{section} の Step 列に範囲表記でない不正トークンがある: {invalid}"
        )

    def test_titles_point_at_the_same_step_as_the_registry(self, workflow_id: str) -> None:
        section, _mode = _SECTION_MODES[workflow_id]
        mismatches = _title_mismatches(section, workflow_id)
        assert mismatches == [], (
            f"§{section} の Step タイトルが registry の別 Step を指している:\n"
            + "\n".join(mismatches)
        )
