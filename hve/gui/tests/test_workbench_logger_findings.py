"""test_workbench_logger_findings.py — NFR-OBS-06 指摘検知の構造化テスト。

検証項目:
  1. `hve/prompts.py` の重大度テーブル行だけを指摘として検知すること
  2. Agent の自由記述（`work-status.md` / `fail-closed` 等）を誤検知しないこと
  3. テンプレート行・区切り行を検知しないこと
  4. `[hve:ctx:<step_id>]` マーカー付き行を正規化して step_id を復元すること

実データ根拠: work/run/20260726T210312-2e97d7/console-log.txt の 5 件は
すべて偽陽性であった（部分文字列 `status` が `work-status.md` に、
`FAIL` が `fail-closed` に一致していた）。

根拠: hve-dev/requirement-definition.md §7 NFR-OBS-06
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hve.gui.workbench_logger import process_log_line
from hve.gui.workbench_state import WorkbenchState


# 2026-07-26 のランで誤検知された実ログ行（Agent の地の文）。
FALSE_POSITIVE_LINES = (
    "[hve:ctx:fleet-w2] [21:26:26]   - `step-2-1-add-service` (Step.2.1 / "
    "追加 Azure サービス選定 — `docs/azure/azure-services-compute.md` 欠損の "
    "fail-closed 判定を含む)",
    "[hve:ctx:General Purpose Agent] [00:01:07]   **ブロッカー・要確認事項**: なし。"
    "API契約(SVC-09等)はTBDのまま README/work-status.md に契約確定待ちとして記録し、",
    "[hve:ctx:General Purpose Agent] [00:04:49]   - `error-handling.test.js`（AC-05）と "
    "`auth-authorization.test.js`（AC-06）で解釈が異なる（work-status.mdに申し送り記録済み、"
    "GREEN実装時要確認）",
    "[hve:ctx:General Purpose Agent] [00:07:44]   ### ブロッカー・要確認事項"
    "（契約確定待ち、work-status.mdに記録済み）",
    "[hve:ctx:General Purpose Agent] [00:29:02] ● 2回目も同一 FAIL です。"
    "Storage のプロパティ記述子を確認し、own 判定ではなく prototype/instance 両面へ切り替えます。",
)


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="asdw-web", run_id="r1", model="test")


def _findings(lines) -> list:
    state = _state()
    for line in lines:
        process_log_line(state, line)
    return [a for a in state.user_actions if a.category == "指摘"]


class TestStructuredFindingDetection(unittest.TestCase):
    """NFR-OBS-06: 重大度テーブル行だけを指摘として扱う。"""

    def test_critical_row_is_detected_as_error(self) -> None:
        findings = _findings([
            "| 1 | 技術的正確性 | Critical | hve/runner.py:100 | 値が未検証 | 検証を追加 |",
        ])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "ERROR")
        self.assertIn("Critical", findings[0].message)

    def test_major_row_is_detected_as_warn(self) -> None:
        findings = _findings([
            "| 2 | 整合性 | Major | docs/a.md | 記述が矛盾 | 統一する |",
        ])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "WARN")

    def test_minor_row_is_not_reported(self) -> None:
        findings = _findings([
            "| 3 | 表記 | Minor | docs/a.md | 表記ゆれ | 統一する |",
        ])
        self.assertEqual(findings, [])

    def test_template_row_is_not_reported(self) -> None:
        findings = _findings([
            "| 1 | [軸名] | [Critical/Major/Minor] | [箇所] | [問題] | [修正案] |",
        ])
        self.assertEqual(findings, [])

    def test_separator_row_is_not_reported(self) -> None:
        findings = _findings([
            "|-----|-----|--------|---------|-----------|--------|",
        ])
        self.assertEqual(findings, [])

    def test_header_row_is_not_reported(self) -> None:
        findings = _findings([
            "| No. | 軸 | 重大度 | 指摘箇所 | 問題の説明 | 修正案 |",
        ])
        self.assertEqual(findings, [])

    def test_severity_is_case_insensitive(self) -> None:
        findings = _findings([
            "| 1 | 技術 | CRITICAL | a.py | x | y |",
        ])
        self.assertEqual(len(findings), 1)

    def test_ctx_marker_is_normalized_and_step_id_recovered(self) -> None:
        findings = _findings([
            "[hve:ctx:1.3] [00:10:00] | 1 | 技術 | Critical | a.py | x | y |",
        ])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].step_id, "1.3")
        self.assertNotIn("hve:ctx", findings[0].message)


class TestNoFalsePositivesOnAgentProse(unittest.TestCase):
    """NFR-OBS-06: Agent の自由記述を指摘として拾わない。"""

    def test_incident_log_lines_produce_no_findings(self) -> None:
        self.assertEqual(_findings(FALSE_POSITIVE_LINES), [])

    def test_work_status_filename_alone_is_not_a_finding(self) -> None:
        self.assertEqual(
            _findings(["work-status.md に要確認事項を記録しました"]), []
        )

    def test_fail_closed_vocabulary_is_not_a_finding(self) -> None:
        self.assertEqual(
            _findings(["入力不備は fail-closed 判定で停止します"]), []
        )

    def test_negation_sentence_is_not_a_finding(self) -> None:
        self.assertEqual(
            _findings(["**ブロッカー・要確認事項**: なし。レビュー結果は問題なし。"]), []
        )

    def test_tdd_red_narration_is_not_a_finding(self) -> None:
        self.assertEqual(
            _findings(["2回目も同一 FAIL です。own 判定を見直します。"]), []
        )


if __name__ == "__main__":
    unittest.main()
