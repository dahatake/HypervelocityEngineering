"""Tool Search 方針（`auto` / `yes` / `no`）別の TB-CAP validator テスト。

FR-WF-AAG-01 / FR-WF-AAG-02。
`test_toolbox_contract_validation.py` が `auto` の閾値挙動を扱うのに対し、
本ファイルは方針別の必須／N/A の切り替えと Tool 集合の完全一致を扱う。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.artifact_validation import validate_ai_agent_design_artifact

from hve.tests.test_toolbox_contract_validation import (
    _ROUTE_TOOL_ID,
    _crud_matrix,
    _design,
    _search_rows,
    _tb_cap_01,
    _tb_cap_02,
    _tb_cap_03,
    _tb_cap_04,
    _tb_cap_05,
    _tb_errors,
)


def _validate(text: str, **kwargs) -> list:
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "agent-detail-AG-01.md"
        path.write_text(text, encoding="utf-8")
        return validate_ai_agent_design_artifact(path, **kwargs)


def _ids(read_tools: int) -> list:
    return [f"order-read-{i:02d}" for i in range(read_tools)] + [_ROUTE_TOOL_ID]


def _full_blocks(read_tools: int, *, tool_search: str = "enabled") -> str:
    ids = _ids(read_tools)
    return (
        _tb_cap_01(total=len(ids), rest=read_tools, routes=1) + "\n"
        + _tb_cap_02(tool_search=tool_search) + "\n"
        + _tb_cap_03(pinned=ids[0]) + "\n"
        + _tb_cap_04(_search_rows(ids, pinned={ids[0]})) + "\n"
        + _tb_cap_05()
    )


_NA_TAIL = (
    "- Reason: The tool catalog stays small and every tool is used in almost every turn.\n"
    "- Decision source: docs/agent/tool-search-policy.md#no\n"
    "- Recheck condition: Revisit when the tool count exceeds 15.\n"
)


def _na_blocks(read_tools: int) -> str:
    """`no` 方針で許される形（TB-CAP-01/02 + 理由付き N/A の 03〜05）。"""
    blocks = (
        _tb_cap_01(total=read_tools + 1, rest=read_tools, routes=1) + "\n"
        + _tb_cap_02(
            tool_search="disabled",
            reason="The operator disabled tool search for this Agent.",
        ) + "\n"
    )
    for heading in (
        "7.5.3 Pinning Policy（TB-CAP-03）",
        "7.5.4 Search Metadata（TB-CAP-04）",
        "7.5.5 Discovery Budget（TB-CAP-05）",
    ):
        blocks += f"#### {heading}\n- Status: N/A\n{_NA_TAIL}\n"
    return blocks


class TestPolicyAuto(unittest.TestCase):
    """`auto` は Tool 総数だけで判定する（既定・後方互換）。"""

    def test_boundary_15_does_not_require_tb_cap(self) -> None:
        errors = _validate(_design(crud=_crud_matrix(14), tb_blocks=""), tool_search_policy="auto")
        self.assertEqual(_tb_errors(errors), [])

    def test_boundary_16_requires_tb_cap(self) -> None:
        errors = _validate(_design(crud=_crud_matrix(15), tb_blocks=""), tool_search_policy="auto")
        self.assertTrue(_tb_errors(errors))

    def test_omitted_policy_behaves_as_auto(self) -> None:
        """既存呼出し（policy 未指定）が挙動を変えない。"""
        without = _tb_errors(_validate(_design(crud=_crud_matrix(15), tb_blocks="")))
        with_auto = _tb_errors(
            _validate(_design(crud=_crud_matrix(15), tb_blocks=""), tool_search_policy="auto")
        )
        self.assertEqual(without, with_auto)


class TestPolicyYes(unittest.TestCase):
    """`yes` は Tool 総数に関係なく TB-CAP-01〜05 を要求する。"""

    def test_small_catalog_still_requires_tb_cap(self) -> None:
        errors = _tb_errors(
            _validate(_design(crud=_crud_matrix(3), tb_blocks=""), tool_search_policy="yes")
        )
        self.assertTrue(errors, "yes 指定なのに TB-CAP を要求していない")

    def test_small_catalog_with_tb_cap_passes(self) -> None:
        errors = _tb_errors(
            _validate(
                _design(crud=_crud_matrix(3), tb_blocks=_full_blocks(3)),
                tool_search_policy="yes",
            )
        )
        self.assertEqual(errors, [], errors)

    def test_disabled_tool_search_conflicts_with_yes(self) -> None:
        errors = _tb_errors(
            _validate(
                _design(crud=_crud_matrix(3), tb_blocks=_full_blocks(3, tool_search="disabled")),
                tool_search_policy="yes",
            )
        )
        self.assertTrue(any("enabled" in e for e in errors), errors)


class TestPolicyNo(unittest.TestCase):
    """`no` は Toolbox を採用せず、TB-CAP-03〜05 を理由付き N/A にする。"""

    def test_large_catalog_accepts_reasoned_na(self) -> None:
        errors = _tb_errors(
            _validate(
                _design(crud=_crud_matrix(20), tb_blocks=_na_blocks(20)),
                tool_search_policy="no",
            )
        )
        self.assertEqual(errors, [], errors)

    def test_small_catalog_still_requires_decision_record(self) -> None:
        """`no` でも判断を記録させる（空欄で消させない）。"""
        errors = _tb_errors(
            _validate(_design(crud=_crud_matrix(3), tb_blocks=""), tool_search_policy="no")
        )
        self.assertTrue(errors, "no 指定時に TB-CAP-01/02 を要求していない")

    def test_enabled_tool_search_conflicts_with_no(self) -> None:
        errors = _tb_errors(
            _validate(
                _design(crud=_crud_matrix(20), tb_blocks=_full_blocks(20)),
                tool_search_policy="no",
            )
        )
        self.assertTrue(any("disabled" in e for e in errors), errors)

    def test_bare_na_without_reason_fails(self) -> None:
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n"
            + _tb_cap_02(tool_search="disabled", reason="Operator disabled tool search.") + "\n"
            + "#### 7.5.3 Pinning Policy（TB-CAP-03）\n- Status: N/A\n\n"
            + "#### 7.5.4 Search Metadata（TB-CAP-04）\n- Status: N/A\n\n"
            + "#### 7.5.5 Discovery Budget（TB-CAP-05）\n- Status: N/A\n"
        )
        errors = _tb_errors(
            _validate(_design(crud=_crud_matrix(20), tb_blocks=blocks), tool_search_policy="no")
        )
        self.assertTrue(any("Reason" in e for e in errors), errors)


class TestUnknownPolicy(unittest.TestCase):
    def test_unknown_policy_fails_closed(self) -> None:
        errors = _tb_errors(
            _validate(
                _design(crud=_crud_matrix(20), tb_blocks=_full_blocks(20)),
                tool_search_policy="ON",
            )
        )
        self.assertTrue(any("policy" in e for e in errors), errors)


class TestSearchMetadataCompleteness(unittest.TestCase):
    """TB-CAP-04 は全 Tool を過不足なく 1 行 1 件で持つ。"""

    def _blocks(self, rows: str) -> str:
        ids = _ids(20)
        return (
            _tb_cap_01(total=len(ids), rest=20, routes=1) + "\n"
            + _tb_cap_02() + "\n"
            + _tb_cap_03(pinned=ids[0]) + "\n"
            + _tb_cap_04(rows) + "\n"
            + _tb_cap_05()
        )

    def test_missing_tool_fails(self) -> None:
        ids = _ids(20)
        rows = _search_rows(ids[:-1], pinned={ids[0]})
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=self._blocks(rows))))
        self.assertTrue(any("missing" in e.lower() for e in errors), errors)

    def test_extra_tool_fails(self) -> None:
        ids = _ids(20)
        rows = _search_rows(ids + ["order-read-99"], pinned={ids[0]})
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=self._blocks(rows))))
        self.assertTrue(any("unknown" in e.lower() for e in errors), errors)

    def test_duplicate_tool_fails(self) -> None:
        ids = _ids(20)
        rows = _search_rows(ids, pinned={ids[0]}) + _search_rows([ids[1]])
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=self._blocks(rows))))
        self.assertTrue(any("duplicate" in e.lower() for e in errors), errors)

    def test_pinned_column_must_match_tb_cap_03(self) -> None:
        ids = _ids(20)
        rows = _search_rows(ids, pinned={ids[1]})
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=self._blocks(rows))))
        self.assertTrue(any("pinned" in e.lower() for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
