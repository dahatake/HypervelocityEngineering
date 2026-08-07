"""Toolbox / tool search 契約（TB-CAP-01〜05）validator テスト。

`foundry-toolbox-contract` Skill の整合ルール R1〜R10 を
`hve.artifact_validation` が決定的に検証することを確認する。

ゲーティング条件は「Tool 総数が閾値（15）を超えるか」であり、
AR-CAP（経路選択でゲート）とは異なる。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.artifact_validation import validate_ai_agent_design_artifact

from hve.tests.test_agentic_retrieval_contract_validation import (
    _HEAD,
    _MCP_NA,
    _SKILL_NOT_REQUIRED,
)

# AG-CAP-03: 同じ経路が複数行に現れるケース（R1 の二重計上を検出するため）
_ROUTING_TWO_ROWS_ONE_ROUTE = """#### 7.0 Knowledge & Structured Data Routing（AG-CAP-03）
| Request class | Data source | Required for Done | Preferred route | Design status | Checked at | Runtime probe | Fallback route | Blocked condition | Permission boundary | Citation requirement | Decision source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| operational-api-read | Order service | yes | orders-search | supported | 2026-08-04 | Verify service health and delegated scope | none: block rather than substitute another source | Stop and Handoff when the API is unavailable | delegated order-reader scope | correlation ID and observed timestamp | docs/catalog/service-catalog-matrix.md#Orders |
| enterprise-unstructured | Policy corpus | yes | orders-search | supported | 2026-08-04 | Verify service health and delegated scope | none: block rather than substitute another source | Stop and Handoff when the API is unavailable | delegated order-reader scope | correlation ID and observed timestamp | docs/catalog/service-catalog-matrix.md#Orders |
"""

# _ROUTING_TWO_ROWS_ONE_ROUTE の Preferred route。TB-CAP-01 の Tool 総数に含まれる。
_ROUTE_TOOL_ID = "orders-search"

_CRUD_HEADER = """#### 7.1 REST CRUD Matrix（AG-CAP-04）
| Tool ID | Operation | Required | REST method | REST path | Request schema | Response schema | Authentication | Authorization | Approval | Idempotency | Retry | Error class | Audit evidence | Contract source |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
"""


def _crud_row(tool_id: str, operation: str = "Read", method: str = "GET") -> str:
    approval = "not required for read" if operation == "Read" else "required with owner approval"
    return (
        f"| {tool_id} | {operation} | yes | {method} | /orders/{tool_id} "
        "| id required string | order body with status | managed identity "
        "| order-reader scope | " + approval + " "
        "| server generated key with replay window | 429 and 503 up to 2 with backoff "
        "| validation and dependency | actor operation target and correlation ID "
        "| docs/catalog/service-catalog-matrix.md#Orders |\n"
    )


def _crud_matrix(read_tools: int) -> str:
    """Read Tool を n 個持ち、C/U/D は理由付き Required: no とする表を作る。"""
    body = "".join(_crud_row(f"order-read-{i:02d}") for i in range(read_tools))
    for operation, method in (("Create", "POST"), ("Update", "PATCH"), ("Delete", "DELETE")):
        body += (
            f"| order-{operation.lower()} | {operation} | no | {method} | /orders/x "
            "| n/a: mutation intent is none | n/a: mutation intent is none | managed identity "
            "| order-reader scope | required with owner approval "
            "| server generated key with replay window | no retry for mutation "
            "| validation and dependency | actor operation target and correlation ID "
            "| docs/catalog/service-catalog-matrix.md#Orders |\n"
        )
    return _CRUD_HEADER + body


def _tb_cap_01(*, total: int, rest: int, mcp: int = 0, routes: int = 1) -> str:
    return f"""#### 7.5.1 Tool Inventory（TB-CAP-01）
- Status: selected
- Total tools: {total}
- REST tools: {rest}
- MCP allowlist tools: {mcp}
- Distinct search routes: {routes}
- Counting source: AG-CAP-03 / AG-CAP-04 / AG-CAP-05
- Checked at: 2026-08-04
"""


def _tb_cap_02(
    *,
    tool_search: str = "enabled",
    topology: str = "via-toolbox",
    reason: str = "",
) -> str:
    extra = f"- Reason: {reason}\n" if reason else ""
    return f"""#### 7.5.2 Toolbox Decision（TB-CAP-02）
- Status: selected
- Toolbox: adopted
- Tool search: {tool_search}
- Connection topology: {topology}
- Threshold basis: 16 tools exceeds the documented 10-15 range
{extra}- SDK package: azure-ai-projects (version confirmed at implementation time)
- Checked at: 2026-08-04
"""


def _tb_cap_03(*, pinned: str = "order-read-00", wildcard: str = "not used") -> str:
    return f"""#### 7.5.3 Pinning Policy（TB-CAP-03）
- Status: selected
- Pinned tools: {pinned}
- Pin rationale: Called first in every workflow, so a search round trip would add latency.
- Unpinned scope: Long tail tools used less than monthly.
- Wildcard pin: {wildcard}
- Checked at: 2026-08-04
"""


_TB_CAP_04_HEADER = """#### 7.5.4 Search Metadata（TB-CAP-04）
| Tool ID | Pinned | Additional search text | 想定ユーザー語彙 |
|---|---|---|---|
"""


def _tb_cap_04(rows: str) -> str:
    return _TB_CAP_04_HEADER + rows


def _tb_cap_05(*, limit: str = "5") -> str:
    return f"""#### 7.5.5 Discovery Budget（TB-CAP-05）
- Status: selected
- limit: {limit}
- Expected tool_search calls per turn: 1 to 2
- Overflow behavior: Report capability missing after 3 searches instead of guessing a nearby Tool.
- System prompt requirement: Always call tool_search before concluding a capability is missing.
- Checked at: 2026-08-04
"""


def _design(*, crud: str, tb_blocks: str, routing: str = _ROUTING_TWO_ROWS_ONE_ROUTE) -> str:
    return (
        _HEAD + "\n" + routing + "\n" + crud + "\n" + _MCP_NA + "\n"
        + _SKILL_NOT_REQUIRED + "\n" + tb_blocks
    )


def _validate(text: str) -> list:
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "agent-detail-AG-01.md"
        path.write_text(text, encoding="utf-8")
        return validate_ai_agent_design_artifact(path)


def _tb_errors(errors: list) -> list:
    return [e for e in errors if "TB-CAP" in e]


def _search_rows(tool_ids, *, pinned=(), text="notes orders lookup"):
    out = ""
    for tid in tool_ids:
        if tid in pinned:
            out += f"| {tid} | yes | （pin のため不要） | — |\n"
        else:
            out += f"| {tid} | no | {text} | 注文を調べたい |\n"
    return out


def _all_tb_blocks(read_tools: int, *, total: int) -> str:
    ids = [f"order-read-{i:02d}" for i in range(read_tools)] + [_ROUTE_TOOL_ID]
    return (
        _tb_cap_01(total=total, rest=read_tools, routes=1) + "\n"
        + _tb_cap_02() + "\n"
        + _tb_cap_03(pinned=ids[0]) + "\n"
        + _tb_cap_04(_search_rows(ids, pinned={ids[0]})) + "\n"
        + _tb_cap_05()
    )


class TestToolboxGating(unittest.TestCase):
    """TB-CAP は Tool 総数が閾値を超えたときだけ必須になる。"""

    def test_small_catalog_does_not_require_tb_cap(self) -> None:
        """Tool が少ない設計に TB-CAP を強制しない。"""
        errors = _validate(_design(crud=_crud_matrix(3), tb_blocks=""))
        self.assertEqual(_tb_errors(errors), [])

    def test_large_catalog_requires_tb_cap(self) -> None:
        """閾値超過なのに TB-CAP が無ければ FAIL（陰性対照）。"""
        errors = _validate(_design(crud=_crud_matrix(20), tb_blocks=""))
        self.assertTrue(_tb_errors(errors), "閾値超過時に TB-CAP を要求していない")

    def test_large_catalog_with_tb_cap_passes(self) -> None:
        errors = _validate(
            _design(crud=_crud_matrix(20), tb_blocks=_all_tb_blocks(20, total=21))
        )
        self.assertEqual(_tb_errors(errors), [], f"想定外の TB-CAP エラー: {_tb_errors(errors)}")


class TestToolboxConsistencyRules(unittest.TestCase):
    def test_r1_total_must_match_breakdown(self) -> None:
        """内訳の合計が総数と合わなければ FAIL。"""
        blocks = (
            _tb_cap_01(total=99, rest=20, routes=1) + "\n"
            + _tb_cap_02() + "\n" + _tb_cap_03(pinned="order-read-00") + "\n"
            + _tb_cap_04(_search_rows(["order-read-00"], pinned={"order-read-00"})) + "\n"
            + _tb_cap_05()
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertTrue(any("breakdown" in e for e in errors), errors)

    def test_r1_counts_distinct_routes_not_rows(self) -> None:
        """同じ経路が 2 行にあっても検索経路は 1 と数える。"""
        blocks = _all_tb_blocks(20, total=21)
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertEqual(errors, [], f"経路を二重計上している: {errors}")

    def test_r2_disabled_without_reason_fails(self) -> None:
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n"
            + _tb_cap_02(tool_search="disabled") + "\n"
            + _tb_cap_03(pinned="order-read-00") + "\n"
            + _tb_cap_04(_search_rows(["order-read-00"], pinned={"order-read-00"})) + "\n"
            + _tb_cap_05()
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertTrue(any("Reason" in e for e in errors), errors)

    def test_r2_disabled_with_reason_passes(self) -> None:
        ids = [f"order-read-{i:02d}" for i in range(20)] + [_ROUTE_TOOL_ID]
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n"
            + _tb_cap_02(
                tool_search="disabled",
                reason="All 20 tools are used in nearly every turn, so search adds latency without saving tokens.",
            ) + "\n"
            + _tb_cap_03(pinned=ids[0]) + "\n"
            + _tb_cap_04(_search_rows(ids, pinned={ids[0]})) + "\n"
            + _tb_cap_05()
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertEqual(errors, [], errors)

    def test_r3_limit_above_maximum_fails(self) -> None:
        ids = [f"order-read-{i:02d}" for i in range(20)]
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n" + _tb_cap_02() + "\n"
            + _tb_cap_03(pinned=ids[0]) + "\n"
            + _tb_cap_04(_search_rows(ids, pinned={ids[0]})) + "\n"
            + _tb_cap_05(limit="20")
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertTrue(any("limit" in e for e in errors), errors)

    def test_r5_unpinned_tool_without_search_text_fails(self) -> None:
        ids = [f"order-read-{i:02d}" for i in range(20)]
        rows = _search_rows(ids, pinned={ids[0]})
        rows += "| order-read-99 | no |  |  |\n"
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n" + _tb_cap_02() + "\n"
            + _tb_cap_03(pinned=ids[0]) + "\n" + _tb_cap_04(rows) + "\n" + _tb_cap_05()
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertTrue(any("additional search text" in e.lower() for e in errors), errors)

    def test_r5_deferred_is_accepted(self) -> None:
        """初回設計では deferred を許容する（公式の反復型指針に合わせる）。"""
        ids = [f"order-read-{i:02d}" for i in range(20)] + [_ROUTE_TOOL_ID]
        rows = _search_rows(ids, pinned={ids[0]}, text="deferred（実測後に追加）")
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n" + _tb_cap_02() + "\n"
            + _tb_cap_03(pinned=ids[0]) + "\n" + _tb_cap_04(rows) + "\n" + _tb_cap_05()
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertEqual(errors, [], errors)

    def test_r6_wildcard_pin_with_search_enabled_fails(self) -> None:
        ids = [f"order-read-{i:02d}" for i in range(20)]
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n" + _tb_cap_02() + "\n"
            + _tb_cap_03(pinned=ids[0], wildcard='"*" pins every tool') + "\n"
            + _tb_cap_04(_search_rows(ids, pinned={ids[0]})) + "\n" + _tb_cap_05()
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertTrue(any("wildcard" in e.lower() for e in errors), errors)

    def test_r7_unknown_topology_fails(self) -> None:
        ids = [f"order-read-{i:02d}" for i in range(20)]
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n"
            + _tb_cap_02(topology="whatever") + "\n"
            + _tb_cap_03(pinned=ids[0]) + "\n"
            + _tb_cap_04(_search_rows(ids, pinned={ids[0]})) + "\n" + _tb_cap_05()
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertTrue(any("topology" in e.lower() for e in errors), errors)

    def test_r8_empty_pinned_tools_fails(self) -> None:
        ids = [f"order-read-{i:02d}" for i in range(20)]
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n" + _tb_cap_02() + "\n"
            + _tb_cap_03(pinned="") + "\n"
            + _tb_cap_04(_search_rows(ids)) + "\n" + _tb_cap_05()
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertTrue(any("pinned" in e.lower() for e in errors), errors)

    def test_r8_reasoned_none_is_accepted(self) -> None:
        ids = [f"order-read-{i:02d}" for i in range(20)] + [_ROUTE_TOOL_ID]
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n" + _tb_cap_02() + "\n"
            + _tb_cap_03(
                pinned="none: every tool is used at most weekly so no tool needs immediate visibility",
            ) + "\n"
            + _tb_cap_04(_search_rows(ids)) + "\n" + _tb_cap_05()
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertEqual(errors, [], errors)


class TestMissingContract(unittest.TestCase):
    def test_missing_single_contract_is_detected(self) -> None:
        """5 契約のうち 1 つ欠けても検出する。"""
        ids = [f"order-read-{i:02d}" for i in range(20)]
        blocks = (
            _tb_cap_01(total=21, rest=20, routes=1) + "\n" + _tb_cap_02() + "\n"
            + _tb_cap_03(pinned=ids[0]) + "\n"
            + _tb_cap_04(_search_rows(ids, pinned={ids[0]}))
        )
        errors = _tb_errors(_validate(_design(crud=_crud_matrix(20), tb_blocks=blocks)))
        self.assertTrue(any("TB-CAP-05" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
