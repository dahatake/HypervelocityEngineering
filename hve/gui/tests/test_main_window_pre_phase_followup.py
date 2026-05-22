"""R6: `_prompt_autopilot_downstream_continuation` の単体テスト。

MainWindow 全体の構築は重いため、Qt は offscreen でセットアップし、
`QMessageBox.question` / `build_plan` / `AutopilotController` を monkeypatch して
分岐ごとの挙動を確認する。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from hve.gui.main_window import MainWindow  # noqa: E402
from hve.autopilot.plan_model import AppChain, AutopilotPlan, AutopilotSelection  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_main_window(tmp_path: Path) -> MainWindow:
    win = MainWindow()
    win._repo_root = str(tmp_path)
    return win


def test_returns_completed_when_no_state(qapp, tmp_path: Path) -> None:
    """pre_phase_selection 等が未設定なら即座に '完了' status で抜ける。"""
    win = _make_main_window(tmp_path)
    # 状態未設定（fresh instance）
    win._prompt_autopilot_downstream_continuation()
    assert "完了" in win._status_label.text()


def test_returns_skip_when_user_says_no(qapp, tmp_path: Path) -> None:
    """ユーザーが No を選んだら 'downstream スキップ' status で抜ける。"""
    win = _make_main_window(tmp_path)
    catalog = tmp_path / "catalog.md"
    catalog.write_text("data", encoding="utf-8")
    win._autopilot_pre_phase_selection = AutopilotSelection(
        run_ard=True, run_aas=True, run_aad_web=True, run_asdw_web=True,
    )
    win._autopilot_pre_phase_catalog_path = catalog
    win._autopilot_pre_phase_max_parallel = 4

    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
        win._prompt_autopilot_downstream_continuation()
    assert "スキップ" in win._status_label.text()


def test_warning_when_catalog_never_ready(qapp, tmp_path: Path) -> None:
    """ユーザー Yes → catalog 未生成 → 警告 Dialog → 中止。"""
    win = _make_main_window(tmp_path)
    catalog = tmp_path / "never.md"  # 作らない
    win._autopilot_pre_phase_selection = AutopilotSelection(
        run_ard=True, run_aas=True, run_aad_web=True, run_asdw_web=True,
    )
    win._autopilot_pre_phase_catalog_path = catalog
    win._autopilot_pre_phase_max_parallel = 4

    warn_calls: list = []
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
         patch.object(QMessageBox, "warning", side_effect=lambda *a, **k: warn_calls.append(a)):
        # リトライ短縮のため _wait_catalog_ready をスタブ
        with patch.object(MainWindow, "_wait_catalog_ready", return_value=False):
            win._prompt_autopilot_downstream_continuation()
    assert warn_calls, "catalog 未生成警告が表示されるべき"


def test_warning_when_plan_empty_after_catalog_ready(qapp, tmp_path: Path) -> None:
    """catalog 準備 OK → build_plan が空 → 警告 → 中止。"""
    win = _make_main_window(tmp_path)
    catalog = tmp_path / "catalog.md"
    catalog.write_text("data", encoding="utf-8")
    win._autopilot_pre_phase_selection = AutopilotSelection(
        run_ard=True, run_aas=True, run_aad_web=True, run_asdw_web=True,
    )
    win._autopilot_pre_phase_catalog_path = catalog
    win._autopilot_pre_phase_max_parallel = 4

    empty_plan = AutopilotPlan(
        catalog_path=catalog,
        catalog_exists=True,
        requires_aas=False,
        app_chains=[],
    )
    warn_calls: list = []
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
         patch.object(QMessageBox, "warning", side_effect=lambda *a, **k: warn_calls.append(a)), \
         patch("hve.autopilot.planner.build_plan", return_value=empty_plan):
        win._prompt_autopilot_downstream_continuation()
    assert warn_calls, "空プラン警告が表示されるべき"


def test_starts_autopilot_controller_on_success(qapp, tmp_path: Path) -> None:
    """catalog 準備 OK + plan 非空 + Yes → AutopilotController が起動する。

    NOTE: 成功パスでは `_activate_autopilot_workbench()` / `_setup_autopilot_log_routing()`
    / `_update_title()` 等の UI 更新が走り、`MainWindow` のフルセット（AuthMonitor /
    CopilotChatPanel / PTY 依存）と組み合わせて Qt イベントループ起因のハングを引き起こす
    観測あり（既知の問題、本テスト固有）。Controller 起動の確認に絞るため UI 更新側は
    patch でスタブ化する。
    """
    win = _make_main_window(tmp_path)
    catalog = tmp_path / "catalog.md"
    catalog.write_text("data", encoding="utf-8")
    win._autopilot_pre_phase_selection = AutopilotSelection(
        run_ard=True, run_aas=True, run_aad_web=True, run_asdw_web=True,
    )
    win._autopilot_pre_phase_catalog_path = catalog
    win._autopilot_pre_phase_max_parallel = 4

    plan = AutopilotPlan(
        catalog_path=catalog,
        catalog_exists=True,
        requires_aas=False,
        app_chains=[AppChain(app_id="APP-001", architecture="web", workflows=["aad-web"])],
        max_parallel=4,
    )
    controller_mock = MagicMock()
    # AutopilotController(...) コンストラクタを差し替える。
    ctor_mock = MagicMock(return_value=controller_mock)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
         patch("hve.autopilot.planner.build_plan", return_value=plan), \
         patch("hve.gui.autopilot.child_launcher.AutopilotController", ctor_mock), \
         patch.object(MainWindow, "_activate_autopilot_workbench"), \
         patch.object(MainWindow, "_setup_autopilot_log_routing"), \
         patch.object(MainWindow, "_refresh_navigation"), \
         patch.object(MainWindow, "_update_title"):
        win._prompt_autopilot_downstream_continuation()
    ctor_mock.assert_called_once()
    controller_mock.start.assert_called_once()
    assert "downstream" in win._status_label.text() or "実行中" in win._status_label.text()
