"""``MainWindow._run_step1_unified_precheck`` の autopilot_mode 分岐テスト。

旧 ``_run_step1_artifact_precheck`` / ``_run_autopilot_full_precheck`` をマージし、
両モードで同一の Step 1 統合 precheck + プランレビューを実行する新メソッドの動作確認。

検証ポイント:
    1. ``autopilot_mode=False`` → ``run_step1_precheck`` への呼び出しで
       ``implicit_required_paths is None`` かつ ``autopilot_required_artifacts is None``。
    2. ``autopilot_mode=True`` → 同呼び出しで ``implicit_required_paths`` に
       ``_AUTOPILOT_IMPLICIT_REQUIRED_PATHS`` が、``autopilot_required_artifacts`` に
       カタログ相対パスが渡される。

軽量モック方針: ``test_step2_to_3_auth_guard.py`` 等と同じく ``self`` を ``MagicMock`` に
置換し、Qt ウィンドウを生成せずに unbound メソッドとして呼び出す。
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
    # _refresh_auth_states_sync は (providers, settings, states) の 3 タプルを返す
    fake._refresh_auth_states_sync.return_value = ([], {}, {})
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
# Case 1: autopilot_mode=False
#   → implicit_required_paths is None, autopilot_required_artifacts is None
# ---------------------------------------------------------------------------
def test_unified_precheck_off_omits_autopilot_implicit_requirements(
    tmp_path: Path,
) -> None:
    _ensure_app()
    fake_self = _make_self(tmp_path)

    with patch(
        "hve.autopilot.precheck_runner.run_step1_precheck",
        return_value=_ok_result(),
    ) as mock_precheck, patch(
        "hve.autopilot.plan_review_runner.build_step1_plan_review",
        return_value=_empty_plan_review(),
    ), patch(
        "hve.gui.settings_store.get_option",
        return_value=False,  # step1_show_plan_review_always=False
    ):
        result = MainWindow._run_step1_unified_precheck(
            fake_self, ["aas"], autopilot_mode=False
        )

    assert result is True
    # run_step1_precheck が 1 回呼ばれている
    mock_precheck.assert_called_once()
    kwargs = mock_precheck.call_args.kwargs
    assert kwargs.get("implicit_required_paths") is None
    assert kwargs.get("autopilot_required_artifacts") is None


# ---------------------------------------------------------------------------
# Case 2: autopilot_mode=True
#   → implicit_required_paths が dict、autopilot_required_artifacts が catalog パスを含む
# ---------------------------------------------------------------------------
def test_unified_precheck_on_includes_autopilot_implicit_requirements(
    tmp_path: Path,
) -> None:
    _ensure_app()
    fake_self = _make_self(tmp_path)

    with patch(
        "hve.autopilot.precheck_runner.run_step1_precheck",
        return_value=_ok_result(),
    ) as mock_precheck, patch(
        "hve.autopilot.plan_review_runner.build_step1_plan_review",
        return_value=_empty_plan_review(),
    ), patch(
        "hve.gui.settings_store.get_option",
        return_value=False,
    ):
        result = MainWindow._run_step1_unified_precheck(
            fake_self, ["aad-web"], autopilot_mode=True
        )

    assert result is True
    mock_precheck.assert_called_once()
    kwargs = mock_precheck.call_args.kwargs
    implicit = kwargs.get("implicit_required_paths")
    assert isinstance(implicit, dict)
    # 既知の Autopilot 暗黙依存 dict が渡されていること
    assert "aad-web" in implicit
    required = kwargs.get("autopilot_required_artifacts")
    assert required is not None
    assert any("app-arch-catalog.md" in str(p) for p in required)


# ---------------------------------------------------------------------------
# Case 3: autopilot_mode=False かつ ギャップ 0 件 → True、Dialog skip
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
