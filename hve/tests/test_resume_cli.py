"""test_resume_cli.py — Phase 5 (Resume): セッション管理 CLI のテスト。

Phase 5 で `hve/resume_cli.py` に追加された機能を検証する:

1. cmd_list      — list 表示 / 未完了フィルタ / --json 出力
2. cmd_show      — 1 セッション詳細 / --json 出力 / 存在しない run_id
3. cmd_rename    — 名前変更 / 永続化
4. cmd_delete    — soft / --hard / --yes / 安全性ガード
5. cmd_continue  — run_workflow 呼び出し / SDK バージョン差異 / 環境変数チェック
6. dispatch      — サブコマンド分岐
7. add_resume_parser — argparse 統合

テストは Fake SDK を `sys.modules` に注入する `test_resume_phase3.py` パターンに
従う（実 SDK 不在でも実行可能にする）。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config import SDKConfig  # type: ignore[import-not-found]
from run_state import (  # type: ignore[import-not-found]
    DEFAULT_SESSION_ID_PREFIX,
    RunState,
    StepState,
)

import resume_cli  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------


def _make_state(
    work_dir: Path,
    *,
    run_id: str = "20260507T120000-cli001",
    workflow_id: str = "akm",
    status: str = "paused",
    selected: list = None,
    completed: list = None,
    session_name: str = "テストセッション",
    sdk_version: str = "0.2.2",
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
                state.step_states[sid].session_id = (
                    f"{DEFAULT_SESSION_ID_PREFIX}-{run_id}-step-{sid}"
                )
                state.step_states[sid].elapsed_seconds = 12.34
    state.host.copilot_sdk_version = sdk_version
    state.save()
    return state


def _ns(**kwargs) -> argparse.Namespace:
    """`argparse.Namespace` を簡潔に生成する。"""
    return argparse.Namespace(**kwargs)


# ---------------------------------------------------------------------------
# cmd_list
# ---------------------------------------------------------------------------


class TestCmdList(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_dir_returns_zero(self) -> None:
        args = _ns(work_dir=str(self.work_dir), all=False, json=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = resume_cli.cmd_list(args)
        self.assertEqual(rc, 0)
        self.assertIn("セッションはありません", buf.getvalue())

    def test_all_completed_shows_unfinished_empty_message(self) -> None:
        _make_state(self.work_dir, run_id="20260507T100000-aaa001", status="completed")
        args = _ns(work_dir=str(self.work_dir), all=False, json=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = resume_cli.cmd_list(args)
        self.assertEqual(rc, 0)
        self.assertIn("未完了のセッションはありません", buf.getvalue())

    def test_unfinished_filter_excludes_completed_by_default(self) -> None:
        _make_state(self.work_dir, run_id="20260507T100000-aaa001", status="completed")
        _make_state(self.work_dir, run_id="20260507T110000-bbb002", status="paused")
        args = _ns(work_dir=str(self.work_dir), all=False, json=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = resume_cli.cmd_list(args)
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertNotIn("aaa001", out)
        self.assertIn("bbb002", out)

    def test_json_output_is_valid_json(self) -> None:
        _make_state(
            self.work_dir,
            run_id="20260507T120000-jjj001",
            status="paused",
            session_name="JSON-TEST",
            completed=["1"],
        )
        args = _ns(work_dir=str(self.work_dir), all=False, json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = resume_cli.cmd_list(args)
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 1)
        first = payload[0]
        self.assertEqual(first["run_id"], "20260507T120000-jjj001")
        self.assertEqual(first["session_name"], "JSON-TEST")
        self.assertEqual(first["status"], "paused")
        self.assertEqual(first["progress"]["completed"], 1)
        self.assertEqual(first["progress"]["total"], 3)


# ---------------------------------------------------------------------------
# cmd_show
# ---------------------------------------------------------------------------


class TestCmdShow(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_unknown_run_id_returns_one(self) -> None:
        args = _ns(work_dir=str(self.work_dir), run_id="does-not-exist", json=False)
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = resume_cli.cmd_show(args)
        self.assertEqual(rc, 1)
        self.assertIn("ERROR", err_buf.getvalue())

    def test_show_displays_human_readable_summary(self) -> None:
        _make_state(
            self.work_dir,
            run_id="20260507T120000-show001",
            session_name="表示テスト",
            workflow_id="akm",
            selected=["1", "2"],
            completed=["1"],
        )
        args = _ns(work_dir=str(self.work_dir), run_id="20260507T120000-show001", json=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = resume_cli.cmd_show(args)
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("20260507T120000-show001", out)
        self.assertIn("表示テスト", out)
        self.assertIn("akm", out)
        self.assertIn("1/2", out)
        # ステップテーブルが表示される
        self.assertIn("STEP_ID", out)
        self.assertIn("completed", out)

    def test_show_json_output_contains_step_states(self) -> None:
        _make_state(
            self.work_dir,
            run_id="20260507T120000-show002",
            selected=["1"],
            completed=["1"],
        )
        args = _ns(work_dir=str(self.work_dir), run_id="20260507T120000-show002", json=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = resume_cli.cmd_show(args)
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["run_id"], "20260507T120000-show002")
        self.assertIn("step_states", data)
        self.assertEqual(data["step_states"]["1"]["status"], "completed")


# ---------------------------------------------------------------------------
# cmd_rename
# ---------------------------------------------------------------------------


class TestCmdRename(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_rename_persists_change(self) -> None:
        _make_state(self.work_dir, run_id="20260507T120000-ren001", session_name="OLD")
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-ren001",
            new_name="NEW-NAME",
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = resume_cli.cmd_rename(args)
        self.assertEqual(rc, 0)
        # 再ロードして名前が変わっていることを確認
        reloaded = RunState.load("20260507T120000-ren001", work_dir=self.work_dir)
        self.assertEqual(reloaded.session_name, "NEW-NAME")
        self.assertIn("NEW-NAME", buf.getvalue())

    def test_unknown_run_id_returns_one(self) -> None:
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="missing",
            new_name="anything",
        )
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = resume_cli.cmd_rename(args)
        self.assertEqual(rc, 1)

    def test_empty_new_name_returns_one(self) -> None:
        _make_state(self.work_dir, run_id="20260507T120000-ren002")
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-ren002",
            new_name="   ",
        )
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = resume_cli.cmd_rename(args)
        self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# cmd_delete
# ---------------------------------------------------------------------------


class TestCmdDelete(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_soft_delete_removes_work_dir_only(self) -> None:
        state = _make_state(
            self.work_dir,
            run_id="20260507T120000-del001",
            completed=["1"],
        )
        target = self.work_dir / "20260507T120000-del001"
        self.assertTrue(target.exists())

        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-del001",
            hard=False,
            yes=True,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = resume_cli.cmd_delete(args)
        self.assertEqual(rc, 0)
        self.assertFalse(target.exists())

    def test_user_decline_keeps_dir(self) -> None:
        _make_state(self.work_dir, run_id="20260507T120000-del002")
        target = self.work_dir / "20260507T120000-del002"
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-del002",
            hard=False,
            yes=False,
        )
        # `_confirm` は input() を呼ぶ → "n" を返す
        with mock.patch("builtins.input", return_value="n"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = resume_cli.cmd_delete(args)
        self.assertEqual(rc, 0)
        self.assertTrue(target.exists())  # まだ存在
        self.assertIn("キャンセル", buf.getvalue())

    def test_hard_delete_calls_sdk_delete_session(self) -> None:
        """--hard で SDK 側 delete_session が hve prefix の ID 全てに対し呼ばれる。"""
        state = _make_state(
            self.work_dir,
            run_id="20260507T120000-del003",
            selected=["1", "2"],
            completed=["1", "2"],  # 両ステップに hve prefix の session_id が付く
        )

        # Fake SDK モジュールを sys.modules に注入
        deleted_ids: list[str] = []

        class _FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

            async def delete_session(self, sid: str) -> None:
                deleted_ids.append(sid)

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()  # type: ignore[attr-defined]
        fake_copilot.SubprocessConfig = lambda **kwargs: object()  # type: ignore[attr-defined]

        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-del003",
            hard=True,
            yes=True,
        )
        with mock.patch.dict(sys.modules, {"copilot": fake_copilot}):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = resume_cli.cmd_delete(args)
        self.assertEqual(rc, 0)
        # 2 件の hve-prefixed セッション ID が削除された
        self.assertEqual(len(deleted_ids), 2)
        for sid in deleted_ids:
            self.assertTrue(sid.startswith(DEFAULT_SESSION_ID_PREFIX))

    def test_hard_delete_skips_non_hve_prefix_session_id(self) -> None:
        """安全性ガード: hve prefix で始まらない session_id は削除しない。"""
        state = _make_state(self.work_dir, run_id="20260507T120000-del004")
        # 不正な session_id を直接設定
        state.step_states["1"].session_id = "external-other-tool-session-xyz"
        state.save()

        deleted_ids: list[str] = []

        class _FakeClient:
            async def start(self):
                return None

            async def stop(self):
                return None

            async def delete_session(self, sid: str) -> None:  # pragma: no cover - 呼ばれてはいけない
                deleted_ids.append(sid)

        fake_copilot = types.ModuleType("copilot")
        fake_copilot.CopilotClient = lambda config=None: _FakeClient()  # type: ignore[attr-defined]
        fake_copilot.SubprocessConfig = lambda **kwargs: object()  # type: ignore[attr-defined]

        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-del004",
            hard=True,
            yes=True,
        )
        with mock.patch.dict(sys.modules, {"copilot": fake_copilot}):
            err_buf = io.StringIO()
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(err_buf):
                rc = resume_cli.cmd_delete(args)
        self.assertEqual(rc, 0)
        # delete_session は一切呼ばれない
        self.assertEqual(deleted_ids, [])
        self.assertIn("prefix", err_buf.getvalue())

    def test_unknown_run_id_returns_one(self) -> None:
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="missing-id",
            hard=False,
            yes=True,
        )
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = resume_cli.cmd_delete(args)
        self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# _safe_remove_run_dir 安全性ガード
# ---------------------------------------------------------------------------


class TestSafeRemoveRunDir(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_refuses_dir_without_state_json(self) -> None:
        """state.json が無いディレクトリは削除を拒否する。"""
        state = _make_state(self.work_dir, run_id="20260507T120000-safe001")
        # state.json を消す → hve 管理外と判定されるはず
        (self.work_dir / "20260507T120000-safe001" / "state.json").unlink()
        with self.assertRaises(RuntimeError):
            resume_cli._safe_remove_run_dir(state, self.work_dir)
        # ディレクトリは残る
        self.assertTrue((self.work_dir / "20260507T120000-safe001").exists())

    def test_no_op_for_nonexistent_dir(self) -> None:
        """存在しないディレクトリは静かに no-op。"""
        state = RunState.new(
            run_id="20260507T120000-safe002",
            workflow_id="akm",
            config=SDKConfig(),
            work_dir=self.work_dir,
        )
        # save() を呼んでいないので work_dir 内にディレクトリ無し
        # 例外を投げないことを確認
        resume_cli._safe_remove_run_dir(state, self.work_dir)


# ---------------------------------------------------------------------------
# cmd_continue
# ---------------------------------------------------------------------------


class TestCmdContinue(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work_dir = Path(self._tmp.name)
        self._env_backup = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        self._tmp.cleanup()

    def _patch_orchestrator(
        self,
        *,
        result: dict = None,
    ) -> tuple[mock._patch_dict, mock.MagicMock]:
        """orchestrator.run_workflow を fake で差し替え、(patch, mock_run) を返す。"""
        if result is None:
            result = {"completed": [], "failed": [], "skipped": []}
        captured: dict = {}

        async def _fake_run_workflow(workflow_id=None, params=None, config=None, **kwargs):
            captured["workflow_id"] = workflow_id
            captured["params"] = params
            captured["resume_state"] = kwargs.get("resume_state")
            return result

        mock_orch_mod = types.ModuleType("orchestrator")
        mock_orch_mod.run_workflow = mock.MagicMock(side_effect=_fake_run_workflow)  # type: ignore[attr-defined]
        mock_orch_mod._captured = captured  # type: ignore[attr-defined]

        return mock.patch.dict(sys.modules, {"orchestrator": mock_orch_mod}), mock_orch_mod

    def test_unknown_run_id_returns_one(self) -> None:
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="missing-id",
            abort_on_sdk_mismatch=False,
        )
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = resume_cli.cmd_continue(args)
        self.assertEqual(rc, 1)

    def test_calls_run_workflow_with_resume_state(self) -> None:
        state = _make_state(
            self.work_dir,
            run_id="20260507T120000-cont001",
            workflow_id="akm",
        )
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-cont001",
            abort_on_sdk_mismatch=False,
        )
        patcher, mock_orch = self._patch_orchestrator()
        with patcher:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = resume_cli.cmd_continue(args)
        self.assertEqual(rc, 0)
        mock_orch.run_workflow.assert_called_once()
        captured = mock_orch._captured  # type: ignore[attr-defined]
        self.assertEqual(captured["workflow_id"], "akm")
        # resume_state は読み込まれた RunState インスタンス
        self.assertIsInstance(captured["resume_state"], RunState)
        self.assertEqual(captured["resume_state"].run_id, "20260507T120000-cont001")
        self.assertIn("Resume 完了", buf.getvalue())

    def test_failed_result_returns_one(self) -> None:
        state = _make_state(
            self.work_dir,
            run_id="20260507T120000-cont002",
            workflow_id="akm",
        )
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-cont002",
            abort_on_sdk_mismatch=False,
        )
        patcher, _ = self._patch_orchestrator(
            result={"completed": ["1"], "failed": ["2"], "skipped": []}
        )
        with patcher:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = resume_cli.cmd_continue(args)
        self.assertEqual(rc, 1)

    def test_missing_repo_env_when_create_pr_returns_one(self) -> None:
        state = _make_state(self.work_dir, run_id="20260507T120000-cont003")
        state.config_snapshot["create_pr"] = True
        state.save()
        os.environ.pop("REPO", None)
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-cont003",
            abort_on_sdk_mismatch=False,
        )
        # orchestrator は呼ばれない想定だが念のためモック
        patcher, mock_orch = self._patch_orchestrator()
        with patcher:
            err_buf = io.StringIO()
            with redirect_stderr(err_buf):
                rc = resume_cli.cmd_continue(args)
        self.assertEqual(rc, 1)
        mock_orch.run_workflow.assert_not_called()
        self.assertIn("REPO", err_buf.getvalue())

    def test_sdk_mismatch_warning_continues_by_default(self) -> None:
        state = _make_state(
            self.work_dir,
            run_id="20260507T120000-cont004",
            sdk_version="0.1.0",  # 古い保存
        )
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-cont004",
            abort_on_sdk_mismatch=False,
        )
        patcher, mock_orch = self._patch_orchestrator()
        with mock.patch(
            "run_state.get_current_sdk_version", return_value="0.3.0"
        ), patcher:
            err_buf = io.StringIO()
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(err_buf):
                rc = resume_cli.cmd_continue(args)
        self.assertEqual(rc, 0)
        mock_orch.run_workflow.assert_called_once()
        self.assertIn("SDK バージョン差異", err_buf.getvalue())

    def test_sdk_mismatch_with_abort_flag_returns_one(self) -> None:
        state = _make_state(
            self.work_dir,
            run_id="20260507T120000-cont005",
            sdk_version="0.1.0",
        )
        args = _ns(
            work_dir=str(self.work_dir),
            run_id="20260507T120000-cont005",
            abort_on_sdk_mismatch=True,
        )
        patcher, mock_orch = self._patch_orchestrator()
        with mock.patch(
            "run_state.get_current_sdk_version", return_value="0.3.0"
        ), patcher:
            err_buf = io.StringIO()
            with redirect_stderr(err_buf):
                rc = resume_cli.cmd_continue(args)
        self.assertEqual(rc, 1)
        mock_orch.run_workflow.assert_not_called()


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


class TestDispatch(unittest.TestCase):
    def test_unknown_subcommand_returns_one_with_help(self) -> None:
        args = _ns(resume_command=None)
        err_buf = io.StringIO()
        with redirect_stderr(err_buf):
            rc = resume_cli.dispatch(args)
        self.assertEqual(rc, 1)
        self.assertIn("使い方", err_buf.getvalue())

    def test_dispatches_to_each_subcommand(self) -> None:
        """dispatch が各 cmd_* を呼ぶことを mock で検証。"""
        for sub_name, fn_name in [
            ("list", "cmd_list"),
            ("show", "cmd_show"),
            ("rename", "cmd_rename"),
            ("delete", "cmd_delete"),
            ("continue", "cmd_continue"),
        ]:
            with self.subTest(sub_name=sub_name):
                args = _ns(resume_command=sub_name)
                with mock.patch.object(resume_cli, fn_name, return_value=0) as m:
                    rc = resume_cli.dispatch(args)
                self.assertEqual(rc, 0)
                m.assert_called_once_with(args)


# ---------------------------------------------------------------------------
# add_resume_parser (argparse 統合)
# ---------------------------------------------------------------------------


class TestAddResumeParser(unittest.TestCase):
    def _build_parser(self) -> argparse.ArgumentParser:
        """テスト用のミニマルパーサーに resume サブコマンドを登録する。"""
        parser = argparse.ArgumentParser(prog="hve-test")
        sub = parser.add_subparsers(dest="command")
        resume_cli.add_resume_parser(sub)
        return parser

    def test_list_subcommand_parses(self) -> None:
        p = self._build_parser()
        args = p.parse_args(["resume", "list", "--json"])
        self.assertEqual(args.command, "resume")
        self.assertEqual(args.resume_command, "list")
        self.assertTrue(args.json)

    def test_list_rejects_all_flag(self) -> None:
        p = self._build_parser()
        with self.assertRaises(SystemExit):
            p.parse_args(["resume", "list", "--all"])

    def test_show_requires_run_id(self) -> None:
        p = self._build_parser()
        args = p.parse_args(["resume", "show", "20260507T-abc"])
        self.assertEqual(args.run_id, "20260507T-abc")
        self.assertFalse(args.json)

    def test_rename_takes_two_positionals(self) -> None:
        p = self._build_parser()
        args = p.parse_args(["resume", "rename", "rid", "新名前"])
        self.assertEqual(args.run_id, "rid")
        self.assertEqual(args.new_name, "新名前")

    def test_delete_flags_parse(self) -> None:
        p = self._build_parser()
        args = p.parse_args(["resume", "delete", "rid", "--hard", "--yes"])
        self.assertEqual(args.run_id, "rid")
        self.assertTrue(args.hard)
        self.assertTrue(args.yes)

    def test_continue_with_abort_flag(self) -> None:
        p = self._build_parser()
        args = p.parse_args(["resume", "continue", "rid", "--abort-on-sdk-mismatch"])
        self.assertEqual(args.run_id, "rid")
        self.assertTrue(args.abort_on_sdk_mismatch)

    def test_work_dir_option(self) -> None:
        p = self._build_parser()
        args = p.parse_args(["resume", "--work-dir", "/tmp/runs", "list"])
        self.assertEqual(args.work_dir, "/tmp/runs")


if __name__ == "__main__":
    unittest.main()
