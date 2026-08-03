"""hve.gui.workbench_logger.process_log_line の汎用 ⚠️ WARNING fallback テスト。

`_LOG_PATTERN` にマッチしない `⚠️` 始まりの任意の警告行が、
`state.add_user_action(level="WARN")` 経由で「実行中の課題」へ反映されることを
保証する（従来の `Session error` 限定を撤廃した一般化挙動）。本テストは GUI
パーサ単体の挙動検証であり、特定の発生源コードの出力有無には依存しない。対象例:

  - catalog 見出し WARNING (hve/app_arch_filter.py, タイムスタンプ無し)
  - dry-run 警告              (hve/app_arch_filter.py)
  - タイムスタンプ付き ⚠️ 行 （タイムスタンプ抽出の検証用サンプル）

いずれもタスクは継続する（ステップ状態を変更しない）ことを併せて検証する。
"""

from __future__ import annotations

from hve.gui.workbench_logger import process_log_line
from hve.gui.workbench_state import WorkbenchState


def _state() -> WorkbenchState:
    return WorkbenchState(workflow_id="wf", run_id="r", model="m")


class TestGeneralWarningFallback:
    def test_catalog_heading_warning_without_timestamp(self) -> None:
        s = _state()
        line = (
            "\u26A0\uFE0F WARNING: catalog の見出しが canonical "
            "(`## A) サマリ表（全APP横断）`) と異なります: "
            "`## 2. Architecture Selection Summary` を受理しました。"
            "出力契約に合わせて見出しを揃えることを推奨します: "
            "docs/catalog/app-arch-catalog.md"
        )
        process_log_line(s, line)
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "WARN"
        # 汎用 WARN はカテゴリ無し（"指摘" / "ツール失敗" のような分類は付けない）
        assert a.category is None
        assert a.message.startswith("WARNING: catalog の見出し")
        # タイムスタンプ無し行はフォールバック現在時刻 (HH:MM:SS) を使う
        assert len(a.timestamp) == 8

    def test_split_fork_disabled_warning(self) -> None:
        """タイムスタンプ付き ⚠️ 行が WARN 記録され、タイムスタンプが抽出されることを検証。

        sample payload は ⚠️ 形式の一例であり、GUI パーサは発生源コードに依存しない
        （パーサ検証用のサンプルで、特定コードの実出力であることは前提としない）。
        """
        s = _state()
        line = (
            "[15:51:29] \u26A0\uFE0F    \u23ED [1/APP-009] legacy split-fork は"
            "無効です (split_fork_enabled=False)。"
        )
        process_log_line(s, line)
        assert len(s.user_actions) == 1
        a = s.user_actions[0]
        assert a.level == "WARN"
        assert a.timestamp == "15:51:29"
        assert "legacy split-fork" in a.message

    def test_dry_run_warning_recorded(self) -> None:
        s = _state()
        line = (
            "\u26A0\uFE0F WARNING: catalog 不在"
            "（dry-run モード: フィルタをスキップして続行します）"
        )
        process_log_line(s, line)
        assert len(s.user_actions) == 1
        assert s.user_actions[0].level == "WARN"

    def test_warning_line_does_not_change_step_status(self) -> None:
        """⚠️ 行は WARN 記録されるが、ステップ状態を一切変更しない（タスク継続の保証）。

        payload は ⚠️ 形式のサンプルであり、検証対象はパーサのステップ状態不変性。
        """
        s = _state()
        assert s.running_step_ids == set()
        assert s.current_running_step_id is None

        process_log_line(
            s,
            "[15:51:29] \u26A0\uFE0F  legacy split-fork は無効です",
        )

        assert len(s.user_actions) == 1
        assert s.user_actions[0].level == "WARN"
        assert s.user_actions[0].step_id is None
        # ステップ状態は不変
        assert s.running_step_ids == set()
        assert s.current_running_step_id is None
