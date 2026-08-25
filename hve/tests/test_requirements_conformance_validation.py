"""要件適合実測レポートの成果物ゲート契約（FR-WF-CONF-02 / 03 / 05）。

レポートは「測定した」と自己申告するだけでは意味がない。
未測定を PASS へ畳み込む、目標が無いことを測定済みと偽る、といった
偽 GREEN の経路を validator が塞ぐことを固定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.artifact_validation import validate_requirements_conformance_report

_VALID = """# 要件適合実測レポート

- Schema-Version: 1
- Workflow: asdw-web
- Step: 5.3
- Agent: QA-RequirementsConformanceEval
- Measured-At: 2026-08-17T04:05:06Z
- Target-Environment: https://app009-swa.example.net
- Measurement-Tool: playwright 1.48.0
- Secret-Redaction: confirmed

| Req ID | Kind | Target | Threshold | Measured | Judgement | Headroom | Evidence |
|---|---|---|---|---|---|---|---|
| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |
| NFR-02 | NFR | エラー率 | < 1.0 % | 0.2 % | PASS | 5.0x | perf-p95.log |
| FR-01 | FR | 会員照会が成功する | 成功 | 成功 | PASS | n/a | e2e-run.log |

- Conclusion: 測定した 3 件はいずれも目標を満たした
- Rationale: 本番同等の SWA エンドポイントに対し Playwright で 100 リクエストを実行した
- Simplification-Candidate: none
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "requirements-conformance-report.md"
    path.write_text(text, encoding="utf-8")
    return path


def _validate(tmp_path: Path, text: str) -> list[str]:
    return validate_requirements_conformance_report(
        _write(tmp_path, text), workflow_id="asdw-web", step_id="5.3"
    )


class TestValidReport:
    def test_valid_report_has_no_errors(self, tmp_path: Path):
        assert _validate(tmp_path, _VALID) == []

    def test_missing_file_is_reported(self, tmp_path: Path):
        errors = validate_requirements_conformance_report(
            tmp_path / "absent.md", workflow_id="asdw-web", step_id="5.3"
        )
        assert errors


class TestRequiredLabels:
    @pytest.mark.parametrize(
        "label",
        [
            "Schema-Version",
            "Workflow",
            "Step",
            "Agent",
            "Measured-At",
            "Target-Environment",
            "Measurement-Tool",
            "Secret-Redaction",
        ],
    )
    def test_missing_label_is_rejected(self, tmp_path: Path, label: str):
        text = "\n".join(
            line for line in _VALID.splitlines() if not line.startswith(f"- {label}:")
        )
        errors = _validate(tmp_path, text)
        assert any(label in error for error in errors)

    def test_workflow_label_must_match_the_running_step(self, tmp_path: Path):
        text = _VALID.replace("- Workflow: asdw-web", "- Workflow: adfdv")
        assert _validate(tmp_path, text)

    def test_step_label_must_match_the_running_step(self, tmp_path: Path):
        text = _VALID.replace("- Step: 5.3", "- Step: 4.3")
        assert _validate(tmp_path, text)

    def test_secret_redaction_must_be_confirmed(self, tmp_path: Path):
        text = _VALID.replace(
            "- Secret-Redaction: confirmed", "- Secret-Redaction: pending"
        )
        assert _validate(tmp_path, text)


class TestMeasurementTable:
    def test_table_must_have_at_least_one_row(self, tmp_path: Path):
        text = "\n".join(
            line for line in _VALID.splitlines() if not line.startswith("| NFR-")
        )
        text = "\n".join(line for line in text.splitlines() if not line.startswith("| FR-"))
        assert _validate(tmp_path, text)

    def test_missing_table_header_is_rejected(self, tmp_path: Path):
        text = _VALID.replace(
            "| Req ID | Kind | Target | Threshold | Measured | Judgement | Headroom | Evidence |",
            "| Req ID | Measured | Judgement |",
        )
        assert _validate(tmp_path, text)

    def test_unknown_kind_is_rejected(self, tmp_path: Path):
        text = _VALID.replace("| NFR-01 | NFR |", "| NFR-01 | PERF |")
        assert _validate(tmp_path, text)


class TestJudgementVocabulary:
    @pytest.mark.parametrize(
        "judgement", ["PASS", "FAIL", "NOT_MEASURED", "NO_TARGET"]
    )
    def test_allowed_values_are_accepted(self, tmp_path: Path, judgement: str):
        row = {
            "PASS": "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |",
            "FAIL": "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 900 ms | FAIL | 0.6x | perf-p95.log |",
            "NOT_MEASURED": "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 未測定 | NOT_MEASURED | n/a | 負荷生成環境が未整備のため |",
            "NO_TARGET": "| NFR-01 | NFR | API 応答時間 p95 | 未定義 | 180 ms | NO_TARGET | n/a | perf-p95.log |",
        }[judgement]
        text = _VALID.replace(
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |",
            row,
        )
        assert _validate(tmp_path, text) == []

    def test_unknown_judgement_is_rejected(self, tmp_path: Path):
        text = _VALID.replace("| PASS | 2.7x |", "| OK | 2.7x |")
        assert _validate(tmp_path, text)

    def test_pass_without_measured_value_is_rejected(self, tmp_path: Path):
        """測っていない値を根拠に合格判定を出させない。"""
        text = _VALID.replace(
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |",
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms |  | PASS | 2.7x | perf-p95.log |",
        )
        assert _validate(tmp_path, text)

    def test_not_measured_without_reason_is_rejected(self, tmp_path: Path):
        text = _VALID.replace(
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |",
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 未測定 | NOT_MEASURED | n/a |  |",
        )
        assert _validate(tmp_path, text)

    def test_no_target_without_measured_value_is_rejected(self, tmp_path: Path):
        """目標が無くても実測値は残す（次サイクルで目標を決める材料になる）。"""
        text = _VALID.replace(
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |",
            "| NFR-01 | NFR | API 応答時間 p95 | 未定義 |  | NO_TARGET | n/a | perf-p95.log |",
        )
        assert _validate(tmp_path, text)


class TestPassFailEvidence:
    """合否は目標・閾値・余裕度・証跡が揃って初めて主張できる（FR-WF-CONF-05）。"""

    @pytest.mark.parametrize(
        "column,row",
        [
            ("Target", "| NFR-01 | NFR |  | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |"),
            ("Threshold", "| NFR-01 | NFR | API 応答時間 p95 |  | 180 ms | PASS | 2.7x | perf-p95.log |"),
            ("Headroom", "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS |  | perf-p95.log |"),
            ("Evidence", "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x |  |"),
        ],
    )
    def test_pass_without_required_column_is_rejected(
        self, tmp_path: Path, column: str, row: str
    ):
        text = _VALID.replace(
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |",
            row,
        )
        assert any(column in error for error in _validate(tmp_path, text))

    def test_fail_without_evidence_is_rejected(self, tmp_path: Path):
        text = _VALID.replace(
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |",
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 900 ms | FAIL | 0.6x |  |",
        )
        assert any("Evidence" in error for error in _validate(tmp_path, text))

    def test_not_measured_row_does_not_require_target(self, tmp_path: Path):
        """測れなかった行にまで目標充足を要求しない（過剰検証の禁止）。"""
        text = _VALID.replace(
            "| NFR-01 | NFR | API 応答時間 p95 | < 500 ms | 180 ms | PASS | 2.7x | perf-p95.log |",
            "| NFR-01 | NFR |  |  | 未測定 | NOT_MEASURED | n/a | 負荷生成環境が未整備 |",
        )
        assert _validate(tmp_path, text) == []


class TestRequirementCoverage:
    def test_duplicate_req_id_is_rejected(self, tmp_path: Path):
        """同じ要件を複数行に分け、都合のよい行だけ PASS にさせない。"""
        text = _VALID.replace(
            "| NFR-02 | NFR | エラー率 | < 1.0 % | 0.2 % | PASS | 5.0x | perf-p95.log |",
            "| NFR-01 | NFR | エラー率 | < 1.0 % | 0.2 % | PASS | 5.0x | perf-p95.log |",
        )
        assert any("duplicate" in error for error in _validate(tmp_path, text))


class TestConclusionSection:
    @pytest.mark.parametrize(
        "label", ["Conclusion", "Rationale", "Simplification-Candidate"]
    )
    def test_missing_conclusion_label_is_rejected(self, tmp_path: Path, label: str):
        text = "\n".join(
            line for line in _VALID.splitlines() if not line.startswith(f"- {label}:")
        )
        errors = _validate(tmp_path, text)
        assert any(label in error for error in errors)

    def test_empty_simplification_candidate_is_rejected(self, tmp_path: Path):
        """該当なしは none と書かせる。空欄は判断の放棄と区別できない。"""
        text = _VALID.replace(
            "- Simplification-Candidate: none", "- Simplification-Candidate:"
        )
        assert _validate(tmp_path, text)
