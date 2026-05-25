"""DAG 直列連結経路: `MainWindow._start_autopilot` の分岐選択テスト。

`needs_chain_continuation()=True` の状況（pre_phases と app_chains が同時非空）で、
`_start_autopilot` が:

1. `_launch_autopilot_main_workflow_queue(["ard", "aas"])` を呼ぶこと
2. `AutopilotController` を**起動しない**こと（app_chains は pre_phases 完走後に起動）
3. `_autopilot_chain_continuation_pending = True` がセットされること

を検証する。本テストは Issue（GUI Workbench Workflow 複数選択時の DAG バグ）の
回帰防止用。MainWindow 完全構築コストを避けるため `__new__` で生成し、最小限の
attribute だけ mock で注入する。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from hve.autopilot.plan_model import AppChain, AutopilotPlan, AutopilotSelection
from hve.gui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_mock_main_window(repo_root: Path) -> MainWindow:
    """`__init__` をスキップして `_start_autopilot` 実行に必要な属性だけ注入する。"""
    mw = MainWindow.__new__(MainWindow)
    # _start_autopilot が参照する属性のみセット
    mw._repo_root = str(repo_root)
    mw._page_workflow = MagicMock()
    mw._page_workflow.autopilot_catalog_path.return_value = ""
    mw._page_workflow.selected_workflow_ids.return_value = [
        "ard", "aas", "aad-web", "asdw-web",
    ]
    mw._page_options = MagicMock()
    # 連結経路で参照されるメソッドを mock 化（実行検証用に呼び出し記録のみ）
    mw._activate_autopilot_workbench = MagicMock()
    mw._launch_autopilot_main_workflow_queue = MagicMock()
    return mw


def test_start_autopilot_takes_chain_continuation_branch_when_both_nonempty(
    qapp, tmp_path: Path
) -> None:
    """ARD+AAS+AAD-WEB+ASDW-WEB 選択 ＋ catalog 解決済み →
    `_start_autopilot` は pre_phases キュー起動かつ AutopilotController 未生成。"""
    repo_root = tmp_path
    mw = _make_mock_main_window(repo_root)

    # `build_plan` をスタブ化し pre_phases と app_chains 両方非空の plan を返す
    selection = AutopilotSelection(
        run_ard=True, run_aas=True,
        run_aad_web=True, run_asdw_web=True,
        run_abd=False, run_abdv=False,
    )
    fake_plan = AutopilotPlan(
        catalog_path=tmp_path / "catalog.md",
        catalog_exists=True,
        requires_aas=False,
        app_chains=[AppChain(app_id="APP-001", architecture="web-cloud",
                             workflows=["aad-web", "asdw-web"])],
        skipped=[],
        max_parallel=4,
        pre_phases=["ard", "aas"],
        main_workflows=[],
        ignored_workflows=[],
        pre_phase_only=False,
    )
    # 前提を確認: 新分岐の判定が True
    assert fake_plan.needs_chain_continuation() is True
    assert fake_plan.is_pre_phase_only() is False
    assert fake_plan.has_main_workflows() is False

    with patch("hve.gui.autopilot.build_plan", return_value=fake_plan), \
         patch("hve.gui.autopilot.child_launcher.AutopilotController") as mock_ctrl, \
         patch("hve.gui.settings_store.get_option", return_value=4):
        mw._start_autopilot()

    # 検証 1: pre_phases キューが ["ard", "aas"] の順で起動された
    mw._launch_autopilot_main_workflow_queue.assert_called_once()
    args, _ = mw._launch_autopilot_main_workflow_queue.call_args
    assert args[0] == ["ard", "aas"], (
        f"pre_phases キューが [ard, aas] で起動されるべき: actual={args[0]}"
    )

    # 検証 2: AutopilotController は起動されない（連結経路は pre_phases 完走後に起動）
    mock_ctrl.assert_not_called()

    # 検証 3: 連結経路フラグがセットされている
    assert mw._autopilot_chain_continuation_pending is True
    assert mw._autopilot_chain_continuation_selection == selection
    assert mw._autopilot_chain_continuation_max_parallel == 4


def test_start_autopilot_takes_app_chains_branch_when_no_pre_phases(
    qapp, tmp_path: Path
) -> None:
    """AAD-WEB のみ選択（ARD/AAS 未選択）→ 通常の app_chains 経路で AutopilotController 起動。"""
    repo_root = tmp_path
    mw = _make_mock_main_window(repo_root)
    mw._page_workflow.selected_workflow_ids.return_value = ["aad-web", "asdw-web"]
    # _start_autopilot 末尾で参照される追加属性
    mw._stack = MagicMock()
    mw._refresh_navigation = MagicMock()
    mw._update_title = MagicMock()
    mw._status_label = MagicMock()
    mw._setup_autopilot_log_routing = MagicMock()

    fake_plan = AutopilotPlan(
        catalog_path=tmp_path / "catalog.md",
        catalog_exists=True,
        requires_aas=False,
        app_chains=[AppChain(app_id="APP-001", architecture="web-cloud",
                             workflows=["aad-web", "asdw-web"])],
        skipped=[],
        max_parallel=4,
        pre_phases=[],
        main_workflows=[],
        ignored_workflows=[],
        pre_phase_only=False,
    )
    assert fake_plan.needs_chain_continuation() is False

    with patch("hve.gui.autopilot.build_plan", return_value=fake_plan), \
         patch("hve.gui.autopilot.child_launcher.AutopilotController") as mock_ctrl, \
         patch("hve.gui.settings_store.get_option", return_value=4):
        mw._start_autopilot()

    # 検証: AutopilotController が起動され、pre_phases キューは起動されない
    mock_ctrl.assert_called_once()
    mw._launch_autopilot_main_workflow_queue.assert_not_called()
    # 連結経路フラグは未セット（未参照の getattr で False 扱い）
    assert getattr(mw, "_autopilot_chain_continuation_pending", False) is False
