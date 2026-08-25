"""``MainWindow._run_step1_unified_precheck`` の統合 precheck テスト。

旧 ``_run_step1_artifact_precheck`` / ``_run_autopilot_full_precheck`` をマージし、
両モードで同一の Step 1 統合 precheck + プランレビューを実行する新メソッドの動作確認。

検証ポイント:
    - ギャップ 0 件かつ plan-review 表示 OFF のとき ``True`` を返し、
      ``Step1PlanReviewDialog`` を生成しないこと。

軽量モック方針: ``test_step2_to_3_auth_guard.py`` 等と同じく ``self`` を ``MagicMock`` に
置換し、Qt ウィンドウを生成せずに unbound メソッドとして呼び出す。

NOTE: 旧テストにあった ``implicit_required_paths`` / ``autopilot_required_artifacts``
引数の検証は、precheck v2 で当該引数が ``run_step1_precheck`` から撤去されたため
削除した。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from hve.autopilot.precheck_model import AutopilotPrecheckResult  # noqa: E402
from hve.gui.main_window import MainWindow  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


def _make_self(tmp_path: Path) -> MagicMock:
    """``_run_step1_unified_precheck`` 実行に必要な属性のみ持つ軽量 self を作る。"""
    fake = MagicMock()
    fake._repo_root = tmp_path
    fake.tr = lambda s: s
    fake._step1_plan_review_iterations = 0
    fake._page_workflow.all_enabled_steps.return_value = {}
    fake._page_workflow.selected_workflow_ids.return_value = ["aas"]
    fake._page_workflow.autopilot_catalog_path.return_value = ""
    fake._collect_ard_attachment_paths.return_value = []
    return fake


def _ok_result() -> AutopilotPrecheckResult:
    """precheck 結果: 不足なし。"""
    return AutopilotPrecheckResult(items=[])


def _empty_plan_review():
    """ギャップ 0 件のプランレビュー結果ダミー。"""
    rv = MagicMock()
    rv.gaps = []
    return rv


# ---------------------------------------------------------------------------
# autopilot_mode=False かつ ギャップ 0 件 → True、Dialog skip
# ---------------------------------------------------------------------------
def test_unified_precheck_off_skips_dialog_when_no_gaps(tmp_path: Path) -> None:
    _ensure_app()
    fake_self = _make_self(tmp_path)

    with patch(
        "hve.autopilot.precheck_runner.run_step1_precheck",
        return_value=_ok_result(),
    ), patch(
        "hve.autopilot.plan_review_runner.build_step1_plan_review",
        return_value=_empty_plan_review(),
    ), patch(
        "hve.gui.settings_store.get_option",
        return_value=False,
    ), patch(
        "hve.gui.autopilot.plan_review_dialog.Step1PlanReviewDialog"
    ) as mock_dlg_cls:
        result = MainWindow._run_step1_unified_precheck(
            fake_self, ["aas"], autopilot_mode=False
        )

    assert result is True
    mock_dlg_cls.assert_not_called()


def test_unified_precheck_reports_startup_args_error(tmp_path: Path) -> None:
    _ensure_app()
    fake_self = _make_self(tmp_path)
    fake_self._page_options.build_args_for_workflow.side_effect = ValueError(
        "invalid startup settings"
    )

    with patch(
        "hve.gui.main_window.QMessageBox.warning"
    ) as warning, patch(
        "hve.autopilot.precheck_runner.run_step1_precheck"
    ) as run_precheck:
        result = MainWindow._run_step1_unified_precheck(
            fake_self, ["aas"], autopilot_mode=False
        )

    assert result is False
    warning.assert_called_once()
    assert "invalid startup settings" in str(warning.call_args.args)
    run_precheck.assert_not_called()
