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
    # _start_autopilot は app_chains 経路で _session_workdir.env_overrides() を参照する。
    mw._session_workdir = MagicMock()
    # _set_status (gui-status-banner) は _status_banner.set_status を呼ぶ。
    mw._status_banner = MagicMock()
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


# ---------------------------------------------------------------------------
# FR-GUI-13: workflow instance ごとの実行ジョブ対話チャネル配線
# ---------------------------------------------------------------------------


def _prepare_channel_capable_window(mw, tmp_path: Path) -> None:
    """`_start_autopilot` の app_chains 経路を実 argv で走らせるための最小注入。"""
    from hve.gui.orchestrate_args import OrchestrateArgs

    mw._page_workbench = MagicMock()
    mw._page_options.build_args_for_workflow.side_effect = (
        lambda workflow_id, repo_root=None: OrchestrateArgs(workflow=workflow_id)
    )
    mw._resolve_steps_for_workflow = MagicMock(return_value=(None, set()))
    mw._apply_cloud_step_overrides = MagicMock()
    mw._prepopulate_workbench_with_seeds = MagicMock()
    mw._build_autopilot_workflow_seeds = MagicMock(return_value=[])
    mw._setup_autopilot_log_routing = MagicMock()
    mw._stack = MagicMock()
    mw._refresh_navigation = MagicMock()
    mw._update_title = MagicMock()
    mw._status_label = MagicMock()


def _app_chains_plan(tmp_path: Path) -> AutopilotPlan:
    return AutopilotPlan(
        catalog_path=tmp_path / "catalog.md",
        catalog_exists=True,
        requires_aas=False,
        app_chains=[
            AppChain(app_id="APP-001", architecture="web-cloud", workflows=["aad-web"]),
            AppChain(app_id="APP-002", architecture="web-cloud", workflows=["aad-web"]),
        ],
        skipped=[],
        max_parallel=4,
        pre_phases=[],
        main_workflows=[],
        ignored_workflows=[],
        pre_phase_only=False,
    )


def test_app_chains_argv_factory_allocates_a_distinct_channel_per_lane(
    qapp, tmp_path: Path
) -> None:
    """FR-GUI-13: 並列 lane が同一 IPC ディレクトリを共有しない。"""
    mw = _make_mock_main_window(tmp_path)
    mw._page_workflow.selected_workflow_ids.return_value = ["aad-web"]
    _prepare_channel_capable_window(mw, tmp_path)

    with patch("hve.gui.autopilot.build_plan", return_value=_app_chains_plan(tmp_path)), \
         patch("hve.gui.autopilot.child_launcher.AutopilotController") as mock_ctrl, \
         patch("hve.gui.settings_store.get_option", return_value=4):
        mw._start_autopilot()

    argv_factory = mock_ctrl.call_args.kwargs["argv_factory"]
    argv_1 = argv_factory("APP-001", "aad-web")
    argv_2 = argv_factory("APP-002", "aad-web")

    assert "--steering-ipc-dir" in argv_1
    assert "--steering-ipc-dir" in argv_2
    dir_1 = argv_1[argv_1.index("--steering-ipc-dir") + 1]
    dir_2 = argv_2[argv_2.index("--steering-ipc-dir") + 1]
    assert dir_1 != dir_2
    assert Path(dir_1).is_dir() and Path(dir_2).is_dir()

    registered = {
        call.args[0]: call.args[1]
        for call in mw._page_workbench.register_job_channel.call_args_list
    }
    assert registered["aad-web#APP-001"] == dir_1
    assert registered["aad-web#APP-002"] == dir_2


def test_app_chains_relaunch_updates_the_channel_for_the_same_lane(
    qapp, tmp_path: Path
) -> None:
    """同一 lane の次の stage 起動ではチャネルを新規発行して登録し直す。"""
    mw = _make_mock_main_window(tmp_path)
    mw._page_workflow.selected_workflow_ids.return_value = ["aad-web"]
    _prepare_channel_capable_window(mw, tmp_path)

    with patch("hve.gui.autopilot.build_plan", return_value=_app_chains_plan(tmp_path)), \
         patch("hve.gui.autopilot.child_launcher.AutopilotController") as mock_ctrl, \
         patch("hve.gui.settings_store.get_option", return_value=4):
        mw._start_autopilot()

    argv_factory = mock_ctrl.call_args.kwargs["argv_factory"]
    first = argv_factory("APP-001", "aad-web")
    second = argv_factory("APP-001", "aad-web")
    dir_1 = first[first.index("--steering-ipc-dir") + 1]
    dir_2 = second[second.index("--steering-ipc-dir") + 1]
    assert dir_1 != dir_2
    last = mw._page_workbench.register_job_channel.call_args_list[-1]
    assert last.args == ("aad-web#APP-001", dir_2)


def test_prephase_window_allocates_a_channel_for_the_workflow(qapp, tmp_path: Path) -> None:
    """FR-GUI-13: prephase / main_workflow 経路もチャネルを登録する。"""
    mw = _make_mock_main_window(tmp_path)
    mw._page_workbench = MagicMock()
    mw._session_index = 1
    mw._resolve_steps_for_workflow = MagicMock(return_value=(None, set()))
    mw._merged_cloud_step_overrides_json = MagicMock(return_value=None)

    captured: dict = {}

    def _fake_launch(argv, *, env_overrides=None):
        captured["argv"] = list(argv)
        return MagicMock()

    with patch("hve.gui.state_bridge.launch_orchestrator", side_effect=_fake_launch), \
         patch("hve.gui.state_bridge.SubprocessReader") as mock_reader:
        mock_reader.return_value = MagicMock()
        mw._create_autopilot_phase_window(
            "ard",
            title_template="{wf} #{idx}",
            status_running_template="{wf} running",
            on_finished=lambda *a, **k: None,
        )

    argv = captured["argv"]
    assert "--steering-ipc-dir" in argv
    channel = argv[argv.index("--steering-ipc-dir") + 1]
    assert Path(channel).is_dir()
    mw._page_workbench.register_job_channel.assert_called_once_with("ard", channel)
