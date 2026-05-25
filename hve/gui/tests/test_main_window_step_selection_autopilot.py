"""T7: Autopilot 経路への Step 1 ステップ選択反映テスト (Q5=B)。

検証内容:
  1. ``WizardResult.steps`` が設定されると ``to_orchestrate_argv()`` に
     ``--steps <CSV>`` が含まれる (T4 実装)。空/None なら付与されない (後方互換)。
  2. ``MainWindow._resolve_steps_for_workflow`` の戻り値が
     Autopilot 経路 (prephase / Plan モード両方) でも同じ契約で利用できることを、
     非 ARD / ARD で再確認 (Q5=B により全 Autopilot 経路で同ヘルパーを共用)。

注: ``_create_autopilot_phase_window`` や ``_argv_factory`` の統合テストは
``launch_orchestrator`` / ``AutopilotController`` のモック整備に大量の前提が必要で
コスト高かつ脆弱なため、本テストではヘルパーと WizardResult の単位契約に絞る。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.main_window import MainWindow  # noqa: E402
from hve.gui.wizard import WizardResult  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# WizardResult.steps → argv 反映 (T4)
# ---------------------------------------------------------------------------


def test_wizard_result_steps_added_to_argv() -> None:
    """WizardResult.steps が non-empty なら argv に --steps <CSV> が含まれる。"""
    result = WizardResult(workflow="aas", steps="1,3")
    argv = result.to_orchestrate_argv()
    assert "--steps" in argv
    idx = argv.index("--steps")
    assert argv[idx + 1] == "1,3"


def test_wizard_result_steps_none_skips_flag() -> None:
    """WizardResult.steps が None / 空文字列なら --steps は付与されない (後方互換)。"""
    result_none = WizardResult(workflow="aas", steps=None)
    assert "--steps" not in result_none.to_orchestrate_argv()

    result_empty = WizardResult(workflow="aas", steps="")
    assert "--steps" not in result_empty.to_orchestrate_argv()


def test_wizard_result_default_steps_is_none() -> None:
    """既定値 (フィールド未指定) では --steps は付与されない。"""
    result = WizardResult(workflow="aas")
    assert result.steps is None
    assert "--steps" not in result.to_orchestrate_argv()


# ---------------------------------------------------------------------------
# Autopilot prephase 経路で使う呼び出し方 (text=None) でのヘルパー契約再確認
# ---------------------------------------------------------------------------


def test_autopilot_prephase_path_non_ard() -> None:
    """Autopilot prephase 経路: ``_resolve_steps_for_workflow(wf_id, None)`` で
    Step 1 選択が CSV 化されることを確認。
    """
    _ensure_app()
    fake = MagicMock()
    fake._page_workflow.all_enabled_steps.return_value = {"aas": ["1", "2"]}

    csv, _ = MainWindow._resolve_steps_for_workflow(fake, "aas", None)
    assert csv == "1,2"


def test_autopilot_prephase_path_ard_group_ids() -> None:
    """Autopilot prephase 経路 ARD: グループ ID がそのまま CSV に。"""
    _ensure_app()
    fake = MagicMock()
    fake._page_workflow.all_enabled_steps.return_value = {"ard": ["2", "4"]}

    csv, display = MainWindow._resolve_steps_for_workflow(fake, "ard", None)
    assert csv == "2,4"
    # display は実 Step ID 展開済 (Q4=A)
    assert "4.1" in display
    assert "1" not in display


def test_autopilot_argv_factory_path_text_intersect() -> None:
    """Autopilot Plan モード経路: テキスト欄ありの AND 動作を再確認 (Q2-1=A)。"""
    _ensure_app()
    fake = MagicMock()
    fake._page_workflow.all_enabled_steps.return_value = {"aas": ["1", "2", "3"]}

    # _argv_factory 内では args.steps が既に build_args_for_workflow で
    # テキスト欄値 (例 "2,4") に設定された状態で _resolve_steps_for_workflow が
    # 呼ばれる想定。
    csv, _ = MainWindow._resolve_steps_for_workflow(fake, "aas", "2,4")
    assert csv == "2"


# ---------------------------------------------------------------------------
# 後方互換: all_enabled_steps() が {} を返す既存 mock との互換
# ---------------------------------------------------------------------------


def test_autopilot_prephase_compat_empty_step_selection() -> None:
    """``{}`` のとき全 ON 扱い → CSV は全 step 列挙 (Q3=B)。

    Autopilot prephase 経路では既に Step 1 を経由した後の wf_id が渡るが、
    テストモック等で ``all_enabled_steps()`` が ``{}`` を返すケースの後方互換確認。
    """
    _ensure_app()
    fake = MagicMock()
    fake._page_workflow.all_enabled_steps.return_value = {}

    from hve.workflow_registry import get_workflow

    wf = get_workflow("aas")
    assert wf is not None
    all_ids = {s.id for s in wf.steps if not s.is_container}

    csv, _ = MainWindow._resolve_steps_for_workflow(fake, "aas", None)
    assert csv is not None
    assert set(csv.split(",")) == all_ids
