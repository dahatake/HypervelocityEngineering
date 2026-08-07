"""Tool Search 評価レポート（AAGD Step.4）の artifact gate テスト。

FR-WF-AAGD-03。
Step.4 が空・自己申告だけで完了しないよう、レポートの測定構造を検証する。
数値の正しさは判定しない（証跡と未測定理由の存在だけを見る）。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hve.artifact_validation import validate_tool_search_eval_report

from hve.tests.test_ai_agent_capability_validation import _design_text
from hve.tests.test_toolbox_implementation_validation import (
    _disabled_blocks,
    _tb_blocks,
)

_QUERY_HEADER = """## 評価クエリ

| Query ID | Query | Expected tools | Multi tool |
|---|---|---|---|
"""


def _queries(total: int = 10, multi: int = 3) -> str:
    rows = ""
    for index in range(total):
        is_multi = "yes" if index < multi else "no"
        expected = "order-read, order-update" if index < multi else "order-read"
        rows += f"| Q{index:02d} | 注文 {index} の状況を調べたい | {expected} | {is_multi} |\n"
    return _QUERY_HEADER + rows


_METRICS = """## 指標一覧

| Metric | Measured off | Measured on | Evidence |
|---|---|---|---|
| 初期 tools/list トークン数 | 4210 | 980 | client trace 2026-08-05 |
| 1 ターン総入力トークン | 5300 | 2100 | client trace 2026-08-05 |
| Tool 選択正解率 | 0.92 | 0.90 | expected tool set 突合 |
| tool_search 呼び出し回数 | 0 | 12 | client trace 2026-08-05 |
| 追加レイテンシ p50 / p95 | 未測定（負荷試験環境が未払い出しのため） | 未測定（同左） | — |
| 過剰呼び出し率 | 0.05 | 0.04 | 該当 Tool なしタスク 3 件 |
"""

_CONDITIONS = """## 測定条件

- Toolbox name: orders-toolbox
- Toolbox version: 2026-08-05-01
- Total tools: 4
- Pinned tools: order-read
- limit: 5
- Measured at: 2026-08-05T09:00:00Z
- SDK / API version: azure-ai-projects 1.2.3 / 2026-05-01-preview
"""

_CONCLUSION = """## TB-CAP-02 Conclusion

- Conclusion: 妥当
- Rationale: 初期 tools/list トークンが 4210 から 980 へ減り、正解率の低下は 2 ポイントに留まった。
"""


def _report(
    *,
    queries: str = "",
    metrics: str = _METRICS,
    conditions: str = _CONDITIONS,
    conclusion: str = _CONCLUSION,
) -> str:
    return (
        "# Tool Search 評価レポート: AG-01\n\n"
        + conditions
        + "\n"
        + (queries or _queries())
        + "\n"
        + metrics
        + "\n"
        + conclusion
    )


_NA_REPORT = """# Tool Search 評価レポート: AG-01

## 測定対象なし（理由付き N/A）

- Status: N/A
- Reason: 設計に TB-CAP-01〜05 が無く、Toolbox を作成していないため測定対象が存在しない。
- Decision source: docs/agent/agent-detail-AG-01.md#7.5
- Recheck condition: Tool 総数が 15 を超えて TB-CAP が追加されたとき。
"""


def _validate(
    *,
    report: "str | None",
    tb_blocks: "str | None" = None,
    policy: str = "yes",
) -> list:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        detail = root / "docs" / "agent" / "agent-detail-AG-01.md"
        detail.parent.mkdir(parents=True, exist_ok=True)
        blocks = _tb_blocks() if tb_blocks is None else tb_blocks
        detail.write_text(_design_text() + "\n" + blocks, encoding="utf-8")
        path = root / "docs" / "agent" / "tool-search-eval" / "AG-01-eval-report.md"
        if report is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report, encoding="utf-8")
        return validate_tool_search_eval_report(detail, path, policy)


def _tb_errors(errors: list) -> list:
    return [error for error in errors if "TB-CAP" in error]


class TestEnabledReport(unittest.TestCase):
    def test_complete_report_passes(self) -> None:
        errors = _tb_errors(_validate(report=_report()))
        self.assertEqual(errors, [], errors)

    def test_missing_report_fails(self) -> None:
        errors = _tb_errors(_validate(report=None))
        self.assertTrue(any("not found" in e.lower() for e in errors), errors)

    def test_empty_report_fails(self) -> None:
        errors = _tb_errors(_validate(report="# 空\n"))
        self.assertTrue(errors, "空レポートを通している")

    def test_fewer_than_ten_queries_fails(self) -> None:
        errors = _tb_errors(_validate(report=_report(queries=_queries(total=9, multi=3))))
        self.assertTrue(any("10" in e for e in errors), errors)

    def test_fewer_than_three_multi_tool_queries_fails(self) -> None:
        errors = _tb_errors(_validate(report=_report(queries=_queries(total=10, multi=2))))
        self.assertTrue(any("multi" in e.lower() for e in errors), errors)

    def test_missing_expected_tool_set_fails(self) -> None:
        broken = _queries().replace("| order-read |", "|  |")
        errors = _tb_errors(_validate(report=_report(queries=broken)))
        self.assertTrue(any("expected tool" in e.lower() for e in errors), errors)

    def test_missing_metrics_table_fails(self) -> None:
        errors = _tb_errors(_validate(report=_report(metrics="## 指標一覧\n\nあとで測る。\n")))
        self.assertTrue(any("metrics" in e.lower() for e in errors), errors)

    def test_missing_on_off_comparison_fails(self) -> None:
        one_sided = _METRICS.replace("| Measured off ", "").replace(
            "|---|---|---|---|", "|---|---|---|"
        )
        errors = _tb_errors(_validate(report=_report(metrics=one_sided)))
        self.assertTrue(any("on" in e.lower() and "off" in e.lower() for e in errors), errors)

    def test_blank_metric_without_reason_fails(self) -> None:
        blank = _METRICS.replace(
            "| 未測定（負荷試験環境が未払い出しのため） | 未測定（同左） | — |", "|  |  | — |"
        )
        errors = _tb_errors(_validate(report=_report(metrics=blank)))
        self.assertTrue(any("未測定" in e or "unmeasured" in e.lower() for e in errors), errors)

    def test_missing_conclusion_fails(self) -> None:
        errors = _tb_errors(_validate(report=_report(conclusion="## まとめ\n\n特になし。\n")))
        self.assertTrue(any("TB-CAP-02" in e for e in errors), errors)
    def test_missing_measurement_conditions_fails(self) -> None:
        errors = _tb_errors(_validate(report=_report(conditions="## 測定条件\n\n省略。\n")))
        self.assertTrue(any("condition" in e.lower() for e in errors), errors)


class TestBenchmarkSubstitution(unittest.TestCase):
    """公開ベンチマーク値で実測欄を埋めさせない。"""

    def test_benchmark_only_metrics_fail(self) -> None:
        borrowed = _METRICS.replace("client trace 2026-08-05", "ToolRet ベンチマーク公表値")
        errors = _tb_errors(_validate(report=_report(metrics=borrowed)))
        self.assertTrue(any("benchmark" in e.lower() for e in errors), errors)

    def test_benchmark_cited_as_background_passes(self) -> None:
        """背景としての引用まで禁止すると Prompt の説明が書けない。"""
        with_note = _report() + "\n> 参考: 公開ベンチマーク (ToolRet) では 60% 超と報告されている。\n"
        errors = _tb_errors(_validate(report=with_note))
        self.assertEqual(errors, [], errors)


class TestReasonedNaReport(unittest.TestCase):
    """TB-CAP なしでも「成果物なし」にせず理由付き N/A を残す。"""

    def test_na_report_passes(self) -> None:
        errors = _tb_errors(_validate(report=_NA_REPORT, tb_blocks="", policy="auto"))
        self.assertEqual(errors, [], errors)

    def test_missing_report_fails_even_without_tb_cap(self) -> None:
        errors = _tb_errors(_validate(report=None, tb_blocks="", policy="auto"))
        self.assertTrue(any("not found" in e.lower() for e in errors), errors)

    def test_bare_na_without_reason_fails(self) -> None:
        bare = "# Tool Search 評価レポート: AG-01\n\n## 測定対象なし\n\n- Status: N/A\n"
        errors = _tb_errors(_validate(report=bare, tb_blocks="", policy="auto"))
        self.assertTrue(errors, "理由なし N/A を通している")

    def test_na_is_rejected_when_tool_search_is_enabled(self) -> None:
        errors = _tb_errors(_validate(report=_NA_REPORT))
        self.assertTrue(errors, "enabled 設計で N/A レポートを通している")


class TestDisabledDesign(unittest.TestCase):
    def test_disabled_design_accepts_na_report(self) -> None:
        errors = _tb_errors(
            _validate(report=_NA_REPORT, tb_blocks=_disabled_blocks(), policy="no")
        )
        self.assertEqual(errors, [], errors)


if __name__ == "__main__":
    unittest.main()
