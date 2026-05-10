"""test_wizard_resume_prompt.py — Phase 4 Resume Wizard プロンプトのテスト。

Phase 4 (Resume) で `__main__.py` に追加された機能を検証する:

1. `_maybe_show_resume_prompt(con)` — resumable runs があれば最初に
   「再開／新規／管理」を選択させる。
2. `_resume_selected_run(con, state)` — 選択された RunState の panel 表示・
   確認・SDK バージョン警告・環境変数チェック・resume 実行。
3. `_session_management_menu(con)` — 実行/削除/戻るを選べるセッション管理メニュー。
4. `default_session_name(workflow_id, params, ...)` — セッション名自動生成。
5. `to_local_time_str(iso_utc, fmt=...)` — ISO 8601 UTC → ローカル文字列。

`_cmd_run_interactive` 全体のテストは `test_main.py` 側で実施されており、
本ファイルでは Phase 4 で追加された関数単体の振る舞いを重点的に検証する。
"""

from __future__ import annotations

import asyncio
import importlib.util as _ilu
import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from keybind import KEY_CTRL_R, KeybindMonitor  # type: ignore[import-not-found]
from run_state import (  # type: ignore[import-not-found]
    DEFAULT_RUNS_DIR,
    RunState,
    StepState,
    default_session_name,
    get_current_sdk_version,
    is_resumable,
    list_resumable_runs,
    to_local_time_str,
)

# __main__.py は Python の __main__ と名前が衝突するため importlib で直接ロードする
_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_phase4", os.path.abspath(_main_path))
_main_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)

_maybe_show_resume_prompt = _main_mod._maybe_show_resume_prompt
_resume_selected_run = _main_mod._resume_selected_run
_session_management_menu = _main_mod._session_management_menu
_delete_run_interactive = _main_mod._delete_run_interactive
_show_resume_menu = _main_mod._show_resume_menu
_show_resume_menu_on_demand = _main_mod._show_resume_menu_on_demand


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------


def _make_state(
    work_dir: Path,
    *,
    run_id: str = "20260507T120000-test01",
    workflow_id: str = "akm",
    status: str = "paused",
    selected: list = None,
    completed: list = None,
    session_name: str = "テストセッション",
) -> RunState:
    """work_dir に state.json を保存した RunState を返す。"""
    state = RunState.new(
        run_id=run_id,
        workflow_id=workflow_id,
        config=SDKConfig(),
        params={},
        selected_step_ids=selected or ["1", "2", "3"],
        session_name=session_name,
        work_dir=work_dir,
    )
    state.status = status
    if completed:
        for sid in completed:
            if sid in state.step_states:
                state.step_states[sid].status = "completed"
    state.save()
    return state


def _make_console_mock() -> mock.MagicMock:
    """Console のモックを生成する（Phase 4 関数が使う属性を埋める）。"""
    con = mock.MagicMock()
    con.s = mock.MagicMock(
        CYAN="", RESET="", DIM="", GREEN="", YELLOW="", RED="", BOLD="", GRAY="",
    )
    return con


def _patched_modules(*, run_workflow_side_effect=None, **overrides) -> tuple:
    """`__main__.py` の helper が依存する flat-import モジュールを sys.modules で差し替える。

    `hve/orchestrator.py` は `from hve.template_engine import (...)` を持ち、
    `hve/template_engine.py` 自身も `from .workflow_registry import ...` を持つため、
    flat な `import` 経路で実モジュールを安全にロードできない。そのため
    `template_engine` / `orchestrator` をスタブで差し替える。

    Returns:
        (patcher, mock_orch_mod) のタプル。patcher.start()/stop() で寿命管理する。
    """
    te_stub = mock.MagicMock()
    te_stub._WORKFLOW_DISPLAY_NAMES = {
        "akm": "AKM",
        "aad": "AAD",
        "aas": "AAS",
        "abd": "ABD",
        "asdw": "ASDW",
        "aag": "AAG",
        "aagd": "AAGD",
        "adoc": "ADOC",
        "aqod": "AQOD",
    }

    mock_orch_mod = mock.MagicMock()
    if run_workflow_side_effect is not None:
        mock_orch_mod.run_workflow = mock.MagicMock(side_effect=run_workflow_side_effect)
    else:
        async def _noop_run(*args, **kwargs):
            return {"completed": [], "failed": [], "skipped": []}
        mock_orch_mod.run_workflow = mock.MagicMock(side_effect=_noop_run)

    modules = {
        "template_engine": te_stub,
        "orchestrator": mock_orch_mod,
    }
    modules.update(overrides)
    return mock.patch.dict("sys.modules", modules), mock_orch_mod


# ---------------------------------------------------------------------------
# default_session_name
# ---------------------------------------------------------------------------


class TestDefaultSessionName(unittest.TestCase):
    """default_session_name() の生成ロジック。"""

    def test_minimal_workflow_id_only(self) -> None:
        now = datetime(2026, 5, 7, 15, 30)
        name = default_session_name("akm", now=now)
        self.assertEqual(name, "akm 05/07 15:30")

    def test_workflow_display_name_short_form(self) -> None:
        """display_name にスペースがあれば最初の語のみ使用。"""
        now = datetime(2026, 5, 7, 15, 30)
        name = default_session_name(
            "aad", workflow_display_name="AAD - App Architecture Design", now=now,
        )
        self.assertEqual(name, "AAD 05/07 15:30")

    def test_app_ids_list_appended(self) -> None:
        now = datetime(2026, 5, 7, 15, 30)
        name = default_session_name(
            "aad",
            params={"app_ids": ["APP-05", "APP-06"]},
            workflow_display_name="AAD",
            now=now,
        )
        self.assertEqual(name, "AAD [APP-05,APP-06] 05/07 15:30")

    def test_app_ids_more_than_two_truncated_with_count(self) -> None:
        now = datetime(2026, 5, 7, 15, 30)
        name = default_session_name(
            "aad",
            params={"app_ids": ["APP-01", "APP-02", "APP-03", "APP-04"]},
            workflow_display_name="AAD",
            now=now,
        )
        self.assertEqual(name, "AAD [APP-01,APP-02+2] 05/07 15:30")

    def test_app_ids_string_csv_form(self) -> None:
        now = datetime(2026, 5, 7, 15, 30)
        name = default_session_name(
            "aad",
            params={"app_ids": "APP-01, APP-02"},
            workflow_display_name="AAD",
            now=now,
        )
        self.assertEqual(name, "AAD [APP-01,APP-02] 05/07 15:30")

    def test_single_app_id_field(self) -> None:
        now = datetime(2026, 5, 7, 15, 30)
        name = default_session_name(
            "aad",
            params={"app_id": "APP-07"},
            workflow_display_name="AAD",
            now=now,
        )
        self.assertEqual(name, "AAD [APP-07] 05/07 15:30")

    def test_empty_workflow_id_falls_back(self) -> None:
        name = default_session_name("", now=datetime(2026, 5, 7, 15, 30))
        self.assertIn("workflow", name)

    def test_long_name_truncated_with_ellipsis(self) -> None:
        very_long_app_id = "APP-VERY-LONG-IDENTIFIER-" + "X" * 100
        name = default_session_name(
            "aad",
            params={"app_id": very_long_app_id},
            workflow_display_name="AAD",
            now=datetime(2026, 5, 7, 15, 30),
        )
        self.assertLessEqual(len(name), 60)
        self.assertTrue(name.endswith("…"))


# ---------------------------------------------------------------------------
# to_local_time_str
# ---------------------------------------------------------------------------


class TestToLocalTimeStr(unittest.TestCase):
    """to_local_time_str() の変換ロジック。"""

    def test_none_returns_unknown(self) -> None:
        self.assertEqual(to_local_time_str(None), "(不明)")

    def test_empty_string_returns_unknown(self) -> None:
        self.assertEqual(to_local_time_str(""), "(不明)")

    def test_invalid_format_returns_unknown(self) -> None:
        self.assertEqual(to_local_time_str("not-a-date"), "(不明)")

    def test_iso_utc_returns_local_format(self) -> None:
        # UTC + 0 を入力 → ローカルタイムへ変換され、何らかの "MM/DD HH:MM" 文字列が返る
        result = to_local_time_str("2026-05-07T15:30:00+00:00")
        # フォーマットの妥当性を確認（数字 + "/" + 数字 + " " + 数字 + ":" + 数字）
        import re
        self.assertRegex(result, r"^\d{2}/\d{2} \d{2}:\d{2}$")

    def test_z_suffix_normalized(self) -> None:
        result = to_local_time_str("2026-05-07T15:30:00Z")
        import re
        self.assertRegex(result, r"^\d{2}/\d{2} \d{2}:\d{2}$")

    def test_naive_datetime_treated_as_utc(self) -> None:
        # tz info なし → UTC とみなす
        result = to_local_time_str("2026-05-07T15:30:00")
        import re
        self.assertRegex(result, r"^\d{2}/\d{2} \d{2}:\d{2}$")

    def test_custom_fmt_respected(self) -> None:
        result = to_local_time_str("2026-05-07T15:30:00+00:00", fmt="%Y")
        self.assertEqual(result, "2026")


# ---------------------------------------------------------------------------
# _maybe_show_resume_prompt
# ---------------------------------------------------------------------------


class TestMaybeShowResumePrompt(unittest.TestCase):
    """_maybe_show_resume_prompt() の Wizard プロンプト分岐。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)
        # default の DEFAULT_RUNS_DIR を tmp 配下にリダイレクト
        self._patcher = mock.patch("run_state.DEFAULT_RUNS_DIR", self.work_dir)
        self._patcher.start()
        self._modules, self.mock_orch = _patched_modules()
        self._modules.start()

    def tearDown(self) -> None:
        self._modules.stop()
        self._patcher.stop()
        self._tmp.cleanup()

    def test_no_resumable_runs_returns_none(self) -> None:
        """work/runs/ が空なら None を返し、wizard の通常フローに進む。"""
        con = _make_console_mock()
        result = _maybe_show_resume_prompt(con)
        self.assertIsNone(result)
        con.menu_select.assert_not_called()

    def test_only_completed_runs_returns_none(self) -> None:
        """status=completed のみの場合は再開可能でないため None。"""
        _make_state(self.work_dir, status="completed")
        con = _make_console_mock()
        result = _maybe_show_resume_prompt(con)
        self.assertIsNone(result)
        con.menu_select.assert_not_called()

    def test_paused_run_displays_menu(self) -> None:
        """paused が 1 件あれば menu_select が呼ばれる。"""
        _make_state(self.work_dir, status="paused")
        con = _make_console_mock()
        # 「新規実行」を選んで通常フローへ
        con.menu_select.return_value = 1  # index 0=resume, 1=new run, 2=management
        result = _maybe_show_resume_prompt(con)
        self.assertIsNone(result)
        con.menu_select.assert_called_once()
        # 選択肢に「新規実行」「セッション管理」が含まれる
        options = con.menu_select.call_args.args[1]
        self.assertEqual(len(options), 3)  # 1 resumable + new + mgmt
        self.assertTrue(any("新規実行" in opt for opt in options))
        self.assertTrue(any("セッション管理" in opt for opt in options))

    def test_select_resume_calls_resume_selected_run(self) -> None:
        """index 0（最初の再開可能 Run）を選ぶと _resume_selected_run が呼ばれる。"""
        _make_state(self.work_dir, status="paused")
        con = _make_console_mock()
        con.menu_select.return_value = 0  # 最初の resumable
        # _resume_selected_run をモックして呼び出されたことを確認
        with mock.patch.object(_main_mod, "_resume_selected_run", return_value=42) as mock_resume:
            result = _maybe_show_resume_prompt(con)
        self.assertEqual(result, 42)
        mock_resume.assert_called_once()
        # 第 2 引数が RunState インスタンス
        called_state = mock_resume.call_args.args[1]
        self.assertIsInstance(called_state, RunState)
        self.assertEqual(called_state.status, "paused")

    def test_select_management_menu_calls_management_stub(self) -> None:
        """index 2（セッション管理）を選ぶと _session_management_menu が呼ばれる。"""
        _make_state(self.work_dir, status="paused")
        con = _make_console_mock()
        con.menu_select.return_value = 2  # セッション管理
        with mock.patch.object(_main_mod, "_session_management_menu", return_value=0) as mock_mgmt:
            result = _maybe_show_resume_prompt(con)
        self.assertEqual(result, 0)
        mock_mgmt.assert_called_once()

    def test_multiple_resumable_runs_sorted_by_last_updated(self) -> None:
        """複数の再開可能 Run があれば、最終更新降順で表示される。"""
        # 2 件作成（last_updated_at は state.save() 時点で UTC now。
        # 後に save された方が新しい → 上位に表示）
        s1 = _make_state(
            self.work_dir,
            run_id="20260507T100000-old001",
            status="paused",
            session_name="OLD-SESSION",
        )
        s2 = _make_state(
            self.work_dir,
            run_id="20260507T120000-new001",
            status="paused",
            session_name="NEW-SESSION",
        )
        con = _make_console_mock()
        con.menu_select.return_value = 1  # 新規実行
        _maybe_show_resume_prompt(con)
        options = con.menu_select.call_args.args[1]
        self.assertEqual(len(options), 4)  # 2 resumable + new + mgmt
        # 新しい方が先に表示される（session_name で識別）
        self.assertIn("NEW-SESSION", options[0])
        self.assertIn("OLD-SESSION", options[1])


# ---------------------------------------------------------------------------
# Ctrl+R during wizard (Phase 8)
# ---------------------------------------------------------------------------


class TestCtrlRDuringWizard(unittest.TestCase):
    """Ctrl+R によるオンデマンド Resume 呼び出しのテスト。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)
        self._patcher = mock.patch("run_state.DEFAULT_RUNS_DIR", self.work_dir)
        self._patcher.start()
        self._modules, self.mock_orch = _patched_modules()
        self._modules.start()

    def tearDown(self) -> None:
        self._modules.stop()
        self._patcher.stop()
        self._tmp.cleanup()

    def test_show_resume_menu_on_demand_no_runs_returns_none(self) -> None:
        """保存済み Run が 0 件のとき、None を返し menu_select を呼ばない。"""
        con = _make_console_mock()
        result = _show_resume_menu_on_demand(con)
        self.assertIsNone(result)
        con.menu_select.assert_not_called()
        con._print.assert_called()
        self.assertIn("再開可能なセッションはありません", str(con._print.call_args.args[0]))

    def test_show_resume_menu_on_demand_with_runs_calls_resume(self) -> None:
        """1 件以上 paused があれば menu_select が呼ばれ、選択時 _resume_selected_run が起動する。"""
        _make_state(self.work_dir, status="paused")
        con = _make_console_mock()
        con.menu_select.return_value = 0
        with mock.patch.object(_main_mod, "_resume_selected_run", return_value=9) as mock_resume:
            result = _show_resume_menu_on_demand(con)
        self.assertEqual(result, 9)
        con.menu_select.assert_called_once()
        mock_resume.assert_called_once()

    def test_show_resume_menu_on_demand_handles_list_error(self) -> None:
        """一覧取得エラー時は warning を表示して None を返す。"""
        con = _make_console_mock()
        with mock.patch("run_state.list_resumable_runs", side_effect=OSError("boom")):
            result = _show_resume_menu_on_demand(con)
        self.assertIsNone(result)
        con.warning.assert_called_once()

    def test_cancel_returns_none_to_continue_wizard(self) -> None:
        """allow_cancel=True 時に「キャンセル」を選んだら None が返り、wizard を継続できる。"""
        state = _make_state(self.work_dir, status="paused")
        con = _make_console_mock()
        con.menu_select.return_value = 1  # index 1 = cancel（1 run + cancel）
        result = _show_resume_menu(con, [state], allow_cancel=True)
        self.assertIsNone(result)

    def test_keybind_monitor_disabled_in_pytest_so_no_thread(self) -> None:
        """pytest 配下では KeybindMonitor.enabled=False で thread が立たない。"""
        loop = asyncio.new_event_loop()
        try:
            monitor = KeybindMonitor(loop)
            self.assertFalse(monitor.enabled)
            monitor.start()
            self.assertIsNone(monitor._thread)
        finally:
            monitor.stop()
            loop.close()

    def test_dispatch_ctrl_r_triggers_on_demand_menu(self) -> None:
        """KeybindMonitor._dispatch(KEY_CTRL_R) で登録済み handler が呼ばれる。"""
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        invoked = threading.Event()
        try:
            monitor = KeybindMonitor(loop)

            async def _handler() -> None:
                invoked.set()

            monitor.register(KEY_CTRL_R, _handler)
            monitor._dispatch(KEY_CTRL_R)
            self.assertTrue(invoked.wait(timeout=2.0))
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2.0)
            loop.close()


# ---------------------------------------------------------------------------
# _resume_selected_run
# ---------------------------------------------------------------------------


class TestResumeSelectedRun(unittest.TestCase):
    """_resume_selected_run() の resume 実行フロー。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)
        # 環境変数のスナップショット
        self._env_backup = os.environ.copy()
        self._modules, self.mock_orch = _patched_modules()
        self._modules.start()

    def tearDown(self) -> None:
        self._modules.stop()
        os.environ.clear()
        os.environ.update(self._env_backup)
        self._tmp.cleanup()

    def test_user_declines_returns_zero_without_running(self) -> None:
        """確認プロンプトで N を返すと 0 を返し run_workflow を呼ばない。"""
        state = _make_state(self.work_dir, status="paused")
        con = _make_console_mock()
        con.prompt_yes_no.return_value = False
        # run_workflow をモックして呼ばれないことを確認
        with mock.patch.object(_main_mod, "asyncio") as mock_asyncio:
            result = _resume_selected_run(con, state)
        self.assertEqual(result, 0)
        mock_asyncio.run.assert_not_called()
        con.panel.assert_called_once()

    def test_calls_run_workflow_with_resume_state(self) -> None:
        """確認プロンプトで Y を返すと run_workflow が resume_state 付きで呼ばれる。"""
        state = _make_state(self.work_dir, status="paused", workflow_id="akm")
        con = _make_console_mock()
        con.prompt_yes_no.return_value = True

        captured = {}

        async def _fake_run_workflow(workflow_id=None, params=None, config=None, **kwargs):
            captured["workflow_id"] = workflow_id
            captured["params"] = params
            captured["resume_state"] = kwargs.get("resume_state")
            return {"completed": [], "failed": [], "skipped": []}

        # mock_orch.run_workflow を fake に差し替え
        self.mock_orch.run_workflow = mock.MagicMock(side_effect=_fake_run_workflow)

        # asyncio.run をスタブ化（実際にコルーチンを drive する）
        def _drive(coro):
            try:
                coro.send(None)
            except StopIteration as si:
                return si.value
            return None

        with mock.patch.object(_main_mod, "asyncio") as mock_asyncio:
            mock_asyncio.run.side_effect = _drive
            result = _resume_selected_run(con, state)

        self.assertEqual(result, 0)
        # asyncio.run が呼ばれた = run_workflow がスケジュールされた
        mock_asyncio.run.assert_called_once()
        # captured kwargs を確認
        self.assertEqual(captured.get("workflow_id"), "akm")
        self.assertIs(captured.get("resume_state"), state)

    def test_missing_repo_env_returns_error_when_create_pr(self) -> None:
        """state.config_snapshot.create_pr=True かつ REPO 環境変数が無い場合はエラー。"""
        state = _make_state(self.work_dir, status="paused")
        # snapshot を直接書き換え
        state.config_snapshot["create_pr"] = True
        state.save()
        os.environ.pop("REPO", None)
        con = _make_console_mock()
        con.prompt_yes_no.return_value = True
        result = _resume_selected_run(con, state)
        self.assertEqual(result, 1)
        con.error.assert_called()

    def test_missing_token_env_returns_error_when_create_issues(self) -> None:
        """create_issues=True かつ GH_TOKEN/GITHUB_TOKEN がいずれも無いとエラー。"""
        state = _make_state(self.work_dir, status="paused")
        state.config_snapshot["create_issues"] = True
        state.save()
        os.environ["REPO"] = "owner/repo"
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)
        con = _make_console_mock()
        con.prompt_yes_no.return_value = True
        result = _resume_selected_run(con, state)
        self.assertEqual(result, 1)
        con.error.assert_called()

    def test_panel_displays_session_summary(self) -> None:
        """セッション名・ワークフロー・進捗等が panel に渡される。"""
        state = _make_state(
            self.work_dir,
            status="paused",
            session_name="テスト-AKM",
            workflow_id="akm",
            selected=["1", "2"],
            completed=["1"],
        )
        con = _make_console_mock()
        con.prompt_yes_no.return_value = False  # キャンセルで早期 return
        _resume_selected_run(con, state)
        con.panel.assert_called_once()
        title, lines = con.panel.call_args.args
        joined = "\n".join(lines)
        self.assertIn("テスト-AKM", joined)
        self.assertIn("akm", joined.lower())
        self.assertIn("1/2", joined)  # 進捗 1/2


# ---------------------------------------------------------------------------
# _session_management_menu
# ---------------------------------------------------------------------------


class TestSessionManagementMenu(unittest.TestCase):
    """_session_management_menu() の実行/削除メニュー。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)
        self._patcher = mock.patch("run_state.DEFAULT_RUNS_DIR", self.work_dir)
        self._patcher.start()
        self._modules, self.mock_orch = _patched_modules()
        self._modules.start()

    def tearDown(self) -> None:
        self._modules.stop()
        self._patcher.stop()
        self._tmp.cleanup()

    def test_empty_dir_returns_zero(self) -> None:
        """セッションなしの場合は 0 を返す。"""
        con = _make_console_mock()
        result = _session_management_menu(con)
        self.assertEqual(result, 0)

    def test_completed_only_excluded(self) -> None:
        """completed のみの場合は管理対象が空となり 0 を返す。"""
        _make_state(self.work_dir, run_id="20260507T100000-aaa001", status="completed")
        con = _make_console_mock()
        result = _session_management_menu(con)
        self.assertEqual(result, 0)
        # menu_select は呼ばれない
        con.menu_select.assert_not_called()

    def test_back_returns_zero(self) -> None:
        """『戻る』を選択すると 0 を返す。"""
        _make_state(self.work_dir, run_id="20260507T110000-bbb002", status="paused")
        con = _make_console_mock()
        # 1 件 + 戻る → back_idx=1
        con.menu_select.return_value = 1
        result = _session_management_menu(con)
        self.assertEqual(result, 0)

    def test_select_resume_then_back(self) -> None:
        """セッション選択→実行→メニューに戻り、次ループで『戻る』。"""
        _make_state(self.work_dir, run_id="20260507T110000-bbb002", status="paused")
        con = _make_console_mock()
        # ループ1: top=0 (run0), sub=0 (実行)
        # ループ2: top=1 (戻る)
        con.menu_select.side_effect = [0, 0, 1]
        with mock.patch.object(_main_mod, "_resume_selected_run", return_value=0) as mock_resume:
            result = _session_management_menu(con)
        self.assertEqual(result, 0)
        mock_resume.assert_called_once()
        called_state = mock_resume.call_args.args[1]
        self.assertEqual(called_state.run_id, "20260507T110000-bbb002")

    def test_select_delete_yes_no_hard(self) -> None:
        """削除を選び、確認 Yes、SDK セッションなしなら hard 確認はスキップ。"""
        _make_state(self.work_dir, run_id="20260507T110000-ccc003", status="paused")
        con = _make_console_mock()
        # ループ1: top=0 (run0), sub=1 (削除)
        # ループ2: 一覧空 → 即 0 を返す
        con.menu_select.side_effect = [0, 1]
        # 削除確認 Yes（SDK session_id 無いので hard 確認は呼ばれない）
        con.prompt_yes_no.return_value = True
        with mock.patch.object(_main_mod, "_resume_selected_run") as mock_resume:
            result = _session_management_menu(con)
        self.assertEqual(result, 0)
        mock_resume.assert_not_called()
        # ディレクトリ削除されたこと
        target = self.work_dir / "20260507T110000-ccc003"
        self.assertFalse(target.exists())

    def test_delete_cancel(self) -> None:
        """削除確認で No を返すと削除されず、ループ継続。"""
        _make_state(self.work_dir, run_id="20260507T110000-ddd004", status="paused")
        con = _make_console_mock()
        # ループ1: top=0, sub=1 (削除)
        # ループ2: top=1 (戻る)
        con.menu_select.side_effect = [0, 1, 1]
        con.prompt_yes_no.return_value = False  # 削除キャンセル
        result = _session_management_menu(con)
        self.assertEqual(result, 0)
        target = self.work_dir / "20260507T110000-ddd004"
        self.assertTrue(target.exists())  # 残っている

    def test_delete_hard_when_sdk_session_present(self) -> None:
        """SDK セッション ID があれば hard 確認が呼ばれ、Yes なら _hard_delete_sdk_sessions 実行。"""
        state = _make_state(self.work_dir, run_id="20260507T110000-eee005", status="paused")
        # state に SDK prefix の session_id を埋め込む
        first_step = next(iter(state.step_states.values()))
        first_step.session_id = "hve-test-session-001"
        state.save()
        con = _make_console_mock()
        con.menu_select.side_effect = [0, 1]  # 削除選択 → 次ループで一覧空で終了
        con.prompt_yes_no.side_effect = [True, True]  # 削除Yes、hard Yes

        async def _fake_hard(_state):
            return []

        with mock.patch("resume_cli._hard_delete_sdk_sessions", side_effect=_fake_hard) as mock_hard:
            result = _session_management_menu(con)
        self.assertEqual(result, 0)
        mock_hard.assert_called_once()
        target = self.work_dir / "20260507T110000-eee005"
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
