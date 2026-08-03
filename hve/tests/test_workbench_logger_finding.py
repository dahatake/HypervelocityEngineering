"""hve.gui.workbench_logger.process_log_line の「指摘」検知テスト（NFR-OBS-06 改訂版）。

## 改訂の経緯

旧実装は「ラベル語（status / 判定 / レビュー）と指摘語（要修正 / 要確認 / FAIL /
不整合）の両方を含む行」を部分文字列一致で指摘としていた。しかし本リポジトリでは
`work-status.md` が全 Agent の標準成果物であり、`fail-closed` が標準語彙であるため、
Agent の自由記述が両条件を満たしてしまう。2026-07-26 のランでは検知 5 件が
**全件偽陽性** だった（`work/run/20260726T210312-2e97d7/console-log.txt`）。

改訂後は `hve/prompts.py` が Agent に出力させる重大度テーブル行:

    | No. | 軸 | 重大度 | 指摘箇所 | 問題の説明 | 修正案 |

だけを指摘として扱う。重大度は Critical → ERROR、Major → WARN にマップし、
Minor（任意修正）は課題ペインへ流さない。

根拠: hve-dev/requirement-definition.md §7 NFR-OBS-06
"""

from __future__ import annotations

from hve.gui.workbench_logger import process_log_line
from hve.gui.workbench_state import WorkbenchState


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r", model="m")


class TestFindingDetection:
    """重大度テーブル行だけを指摘として検知する。"""

    def test_critical_row_with_timestamp(self) -> None:
        s = _state()
        process_log_line(
            s, "[16:18:00] | 1 | 技術的正確性 | Critical | a.py:10 | 未検証 | 検証追加 |"
        )
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "ERROR"
        assert a.category == "指摘"
        assert a.timestamp == "16:18:00"
        assert "Critical" in a.message

    def test_major_row_without_timestamp(self) -> None:
        s = _state()
        process_log_line(s, "| 2 | 整合性 | Major | docs/a.md | 矛盾 | 統一 |")
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "WARN"
        assert a.category == "指摘"
        # タイムスタンプ無し行はフォールバック現在時刻 (HH:MM:SS) を使う
        assert len(a.timestamp) == 8

    def test_minor_row_is_not_reported(self) -> None:
        s = _state()
        process_log_line(s, "| 3 | 表記 | Minor | docs/a.md | 揺れ | 統一 |")
        assert s.user_actions == []

    def test_message_excludes_duplicate_timestamp(self) -> None:
        s = _state()
        process_log_line(s, "[16:18:00] | 1 | 技術 | Critical | a.py | x | y |")
        assert not s.user_actions[0].message.startswith("[16:18:00]")


class TestRetiredHeuristicDoesNotFire:
    """旧ヒューリスティックで偽陽性となっていた行を検知しない。"""

    def test_status_label_prose_is_skipped(self) -> None:
        s = _state()
        process_log_line(s, "[16:18:00] - **status**: 成功（要修正判定）")
        assert s.user_actions == []

    def test_hantei_fail_prose_is_skipped(self) -> None:
        s = _state()
        process_log_line(s, "- **判定**: FAIL")
        assert s.user_actions == []

    def test_hantei_youkakunin_prose_is_skipped(self) -> None:
        s = _state()
        process_log_line(s, "- **判定**: 要確認")
        assert s.user_actions == []

    def test_review_summary_prose_is_skipped(self) -> None:
        s = _state()
        process_log_line(
            s,
            "- **summary**: 5 カタログを横断レビューし、**10 件の不整合**を検出。",
        )
        assert s.user_actions == []

    def test_work_status_filename_prose_is_skipped(self) -> None:
        """`work-status.md` の `status` に一致していた実ログ由来の偽陽性。"""
        s = _state()
        process_log_line(
            s, "**ブロッカー・要確認事項**: なし。work-status.md に記録済み"
        )
        assert s.user_actions == []

    def test_fail_closed_vocabulary_is_skipped(self) -> None:
        """`fail-closed` の `fail` に一致していた実ログ由来の偽陽性。"""
        s = _state()
        process_log_line(s, "- azure-services-compute.md 欠損の fail-closed 判定を含む")
        assert s.user_actions == []

    def test_count_zero_line_is_skipped(self) -> None:
        s = _state()
        process_log_line(s, "- Critical: 0件")
        assert s.user_actions == []

    def test_plain_heading_is_skipped(self) -> None:
        s = _state()
        process_log_line(s, "## 成果物サマリー")
        assert s.user_actions == []


class TestFindingDoesNotAffectStepState:
    """タスク継続の保証: 指摘行はステップ状態を変更しない。"""

    def test_finding_line_does_not_change_step_status(self) -> None:
        s = _state()
        assert s.running_step_ids == set()
        assert s.current_running_step_id is None

        process_log_line(s, "| 1 | 技術 | Critical | a.py | x | y |")

        assert len(s.user_actions) == 1
        assert s.user_actions[0].step_id is None
        assert s.running_step_ids == set()
        assert s.current_running_step_id is None

    def test_finding_line_with_ctx_marker_records_step_id(self) -> None:
        s = _state()
        process_log_line(s, "[hve:ctx:1.3] | 1 | 技術 | Critical | a.py | x | y |")
        assert s.user_actions[0].step_id == "1.3"
        assert s.running_step_ids == set()
