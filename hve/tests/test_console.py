"""test_console.py — Console の verbose/quiet 切り替えテスト"""

from __future__ import annotations

import io
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from console import Console, _format_elapsed_ja


class _CaptureOutput:
    """stdout / stderr を一時的にキャプチャするコンテキストマネージャー。"""

    def __enter__(self):
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        return self

    def __exit__(self, *_):
        self.stdout = sys.stdout.getvalue()
        self.stderr = sys.stderr.getvalue()
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr


class TestConsoleVerbose(unittest.TestCase):
    """verbose=True (デフォルト) の動作を検証する。"""

    def _make(self) -> Console:
        return Console(verbose=True, quiet=False)

    def test_header_shown(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.header("テストヘッダー")
        self.assertIn("テストヘッダー", cap.stdout)

    def test_step_start_shown(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.step_start("1.1", "ドメイン分析", agent="Arch-Agent")
        self.assertIn("Step.1.1", cap.stdout)
        self.assertIn("ドメイン分析", cap.stdout)
        self.assertIn("Arch-Agent", cap.stdout)

    def test_step_end_shown(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.step_end("1.1", "success", elapsed=3.5)
        self.assertIn("Step.1.1", cap.stdout)
        self.assertIn("success", cap.stdout)

    def test_event_shown_when_verbose(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.event("イベント詳細")
        self.assertIn("イベント詳細", cap.stdout)

    def test_tool_shown_when_verbose(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.tool("grep", step_id="1.1")
        self.assertIn("grep", cap.stdout)

    def test_dag_batch_shown_when_verbose(self) -> None:
        c = self._make()

        class _Step:
            def __init__(self, id_: str):
                self.id = id_

        with _CaptureOutput() as cap:
            c.dag_batch([_Step("7.1"), _Step("7.2")])
        self.assertIn("Step.7.1", cap.stdout)
        self.assertIn("Step.7.2", cap.stdout)

    def test_summary_shown(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.summary({"success": 3, "failed": 1, "skipped": 0, "total_elapsed": 10.0})
        self.assertIn("3", cap.stdout)
        self.assertIn("10秒", cap.stdout)

    def test_error_always_shown(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.error("致命的エラー")
        self.assertIn("致命的エラー", cap.stderr)


class TestFormatElapsedJa(unittest.TestCase):
    """_format_elapsed_ja のテスト。"""

    def test_minutes_seconds(self) -> None:
        self.assertEqual(_format_elapsed_ja(2784.0), "46分24秒")

    def test_hours_minutes_seconds(self) -> None:
        self.assertEqual(_format_elapsed_ja(3661.5), "1時間1分1秒")

    def test_seconds_only(self) -> None:
        self.assertEqual(_format_elapsed_ja(45.0), "45秒")


class TestConsoleNonVerbose(unittest.TestCase):
    """verbose=False の動作を検証する。"""

    def _make(self) -> Console:
        return Console(verbose=False, quiet=False)

    def test_header_shown(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.header("ヘッダー")
        self.assertIn("ヘッダー", cap.stdout)

    def test_step_start_shown(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.step_start("2.1", "サービス設計")
        self.assertIn("Step.2.1", cap.stdout)

    def test_event_hidden_when_not_verbose(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.event("非表示のイベント")
        self.assertEqual(cap.stdout, "")

    def test_tool_hidden_when_not_verbose(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.tool("bash")
        self.assertEqual(cap.stdout, "")

    def test_dag_batch_hidden_when_not_verbose(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.dag_batch(["Step.1", "Step.2"])
        self.assertEqual(cap.stdout, "")


class TestConsoleQuiet(unittest.TestCase):
    """quiet=True の動作を検証する（error 以外全抑制）。"""

    def _make(self) -> Console:
        return Console(verbose=True, quiet=True)

    def test_header_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.header("ヘッダー")
        self.assertEqual(cap.stdout, "")

    def test_step_start_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.step_start("1.1", "テスト")
        self.assertEqual(cap.stdout, "")

    def test_step_end_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.step_end("1.1", "success")
        self.assertEqual(cap.stdout, "")

    def test_event_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.event("イベント")
        self.assertEqual(cap.stdout, "")

    def test_tool_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.tool("grep")
        self.assertEqual(cap.stdout, "")

    def test_summary_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.summary({"success": 1, "failed": 0, "skipped": 0})
        self.assertEqual(cap.stdout, "")

    def test_error_shown_even_when_quiet(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.error("必須エラー")
        self.assertIn("必須エラー", cap.stderr)

    def test_warning_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.warning("警告メッセージ")
        self.assertEqual(cap.stdout, "")

    def test_progress_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.progress(1, 5, "進行中")
        self.assertEqual(cap.stdout, "")


# -----------------------------------------------------------------------
# ストリーム出力テスト
# -----------------------------------------------------------------------


class TestConsoleStreamEnabled(unittest.TestCase):
    """show_stream=True の動作を検証する。"""

    def _make(self) -> Console:
        return Console(verbose=True, quiet=False, show_stream=True)

    def test_stream_token_outputs_to_stdout(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_token("1.1", "Hello")
        self.assertEqual(cap.stdout, "Hello")

    def test_stream_token_no_newline(self) -> None:
        """stream_token は改行を付加しない。"""
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_token("1.1", "A")
            c.stream_token("1.1", "B")
        self.assertEqual(cap.stdout, "AB")

    def test_stream_start_marker(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_start("2.1")
        self.assertIn("Step.2.1", cap.stdout)
        self.assertIn("ストリーム開始", cap.stdout)

    def test_stream_end_marker(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_end("2.1")
        self.assertIn("Step.2.1", cap.stdout)
        self.assertIn("ストリーム終了", cap.stdout)


class TestConsoleStreamDisabled(unittest.TestCase):
    """show_stream=False の場合、ストリーム出力は全て抑制される。"""

    def _make(self) -> Console:
        return Console(verbose=True, quiet=False, show_stream=False)

    def test_stream_token_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_token("1.1", "Hello")
        self.assertEqual(cap.stdout, "")

    def test_stream_start_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_start("1.1")
        self.assertEqual(cap.stdout, "")

    def test_stream_end_suppressed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_end("1.1")
        self.assertEqual(cap.stdout, "")


class TestConsoleStreamQuiet(unittest.TestCase):
    """quiet=True のとき show_stream=True でもストリーム出力は抑制される。"""

    def _make(self) -> Console:
        return Console(verbose=True, quiet=True, show_stream=True)

    def test_stream_token_suppressed_when_quiet(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_token("1.1", "Hello")
        self.assertEqual(cap.stdout, "")

    def test_stream_start_suppressed_when_quiet(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_start("1.1")
        self.assertEqual(cap.stdout, "")

    def test_stream_end_suppressed_when_quiet(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.stream_end("1.1")
        self.assertEqual(cap.stdout, "")


# -----------------------------------------------------------------------
# ANSI スタイルテスト
# -----------------------------------------------------------------------


class TestStyleTTY(unittest.TestCase):
    """_Style — TTY 接続時は ANSI エスケープコードを返す。"""

    def test_codes_nonempty_when_tty(self) -> None:
        from console import _Style

        s = _Style(is_tty=True)
        self.assertTrue(s.BOLD.startswith("\033["))
        self.assertTrue(s.CYAN.startswith("\033["))
        self.assertTrue(s.RESET.startswith("\033["))

    def test_codes_empty_when_not_tty(self) -> None:
        from console import _Style

        s = _Style(is_tty=False)
        self.assertEqual(s.BOLD, "")
        self.assertEqual(s.CYAN, "")
        self.assertEqual(s.RESET, "")


# -----------------------------------------------------------------------
# バナー / パネルテスト
# -----------------------------------------------------------------------


class TestConsoleBanner(unittest.TestCase):
    """banner() の表示テスト。"""

    def test_banner_shows_title(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput() as cap:
            c.banner("テストタイトル", "サブタイトル")
        self.assertIn("テストタイトル", cap.stdout)
        self.assertIn("サブタイトル", cap.stdout)

    def test_banner_suppressed_when_quiet(self) -> None:
        c = Console(verbose=True, quiet=True)
        with _CaptureOutput() as cap:
            c.banner("タイトル")
        self.assertEqual(cap.stdout, "")


class TestConsolePanel(unittest.TestCase):
    """panel() の表示テスト。"""

    def test_panel_shows_title_and_lines(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput() as cap:
            c.panel("設定確認", ["モデル: claude-opus-4.7", "並列: 15"])
        self.assertIn("設定確認", cap.stdout)
        self.assertIn("claude-opus-4.7", cap.stdout)

    def test_panel_suppressed_when_quiet(self) -> None:
        c = Console(verbose=True, quiet=True)
        with _CaptureOutput() as cap:
            c.panel("タイトル", ["行1"])
        self.assertEqual(cap.stdout, "")


# -----------------------------------------------------------------------
# インタラクティブ入力テスト
# -----------------------------------------------------------------------


class TestConsoleMenuSelect(unittest.TestCase):
    """menu_select() のテスト。"""

    def test_valid_selection(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value="2"):
            idx = c.menu_select("選択", ["Option A", "Option B", "Option C"])
        self.assertEqual(idx, 1)

    def test_eof_returns_zero(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", side_effect=EOFError):
            idx = c.menu_select("選択", ["A", "B"])
        self.assertEqual(idx, 0)

    def test_keyboard_interrupt_returns_zero(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", side_effect=KeyboardInterrupt):
            idx = c.menu_select("選択", ["A", "B"])
        self.assertEqual(idx, 0)


class TestConsolePromptInput(unittest.TestCase):
    """prompt_input() のテスト。"""

    def test_returns_user_input(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value="hello"):
            val = c.prompt_input("テスト")
        self.assertEqual(val, "hello")

    def test_returns_default_on_empty(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value=""):
            val = c.prompt_input("テスト", default="default_val")
        self.assertEqual(val, "default_val")

    def test_required_rejects_empty(self) -> None:
        """required=True で空入力→リトライ→有効値を返す。"""
        c = Console(verbose=True, quiet=False)
        inputs = iter(["", "valid"])
        with _CaptureOutput(), unittest.mock.patch("builtins.input", side_effect=inputs):
            val = c.prompt_input("テスト", required=True)
        self.assertEqual(val, "valid")


class TestConsolePromptYesNo(unittest.TestCase):
    """prompt_yes_no() のテスト。"""

    def test_yes_input(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value="y"):
            val = c.prompt_yes_no("確認")
        self.assertTrue(val)

    def test_no_input(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value="n"):
            val = c.prompt_yes_no("確認")
        self.assertFalse(val)

    def test_empty_returns_default_true(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value=""):
            val = c.prompt_yes_no("確認", default=True)
        self.assertTrue(val)

    def test_empty_returns_default_false(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value=""):
            val = c.prompt_yes_no("確認", default=False)
        self.assertFalse(val)


class TestConsoleMultiSelect(unittest.TestCase):
    """prompt_multi_select() のテスト。"""

    def test_empty_returns_empty(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value=""):
            val = c.prompt_multi_select("選択", ["A", "B", "C"])
        self.assertEqual(val, [])

    def test_single_selection(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value="2"):
            val = c.prompt_multi_select("選択", ["A", "B", "C"])
        self.assertEqual(val, [1])

    def test_comma_separated(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value="1,3"):
            val = c.prompt_multi_select("選択", ["A", "B", "C"])
        self.assertEqual(val, [0, 2])


# -----------------------------------------------------------------------
# スピナーテスト
# -----------------------------------------------------------------------


class TestConsoleSpinner(unittest.TestCase):
    """spinner_start/stop のテスト。"""

    def test_spinner_start_stop_no_crash(self) -> None:
        """非 TTY 環境ではスピナーは no-op で、例外は発生しない。"""
        c = Console(verbose=True, quiet=False)
        c._is_tty = False
        c.spinner_start("テスト中...")
        c.spinner_stop("完了")

    def test_spinner_suppressed_when_quiet(self) -> None:
        c = Console(verbose=True, quiet=True)
        c.spinner_start("テスト中...")
        self.assertIsNone(c._spinner_thread)


# -----------------------------------------------------------------------
# ワークフローフェーズ / DAG 進捗 / ステップ内フェーズテスト
# -----------------------------------------------------------------------


class TestPhaseOutput(unittest.TestCase):
    """phase_start / phase_end のテスト。"""

    def test_phase_start_shown(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput() as cap:
            c.phase_start(2, 7, "パラメータ収集")
        self.assertIn("Phase 2/7", cap.stdout)
        self.assertIn("パラメータ収集", cap.stdout)

    def test_phase_end_shown(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput() as cap:
            c.phase_end(3, 7, "ステップフィルタリング", 0.5)
        self.assertIn("Phase 3/7", cap.stdout)
        self.assertIn("✓", cap.stdout)
        self.assertIn("0.5s", cap.stdout)

    def test_phase_suppressed_when_quiet(self) -> None:
        c = Console(verbose=True, quiet=True)
        with _CaptureOutput() as cap:
            c.phase_start(1, 5, "テスト")
            c.phase_end(1, 5, "テスト", 1.0)
        self.assertEqual(cap.stdout, "")


class TestDagWaveOutput(unittest.TestCase):
    """dag_wave_start / dag_progress のテスト。"""

    class _Step:
        def __init__(self, id_: str):
            self.id = id_

    def test_dag_wave_start_shown(self) -> None:
        c = Console(verbose=True, quiet=False)
        steps = [self._Step("2a"), self._Step("2b")]
        with _CaptureOutput() as cap:
            c.dag_wave_start(2, 4, steps)
        self.assertIn("Wave 2/4", cap.stdout)
        self.assertIn("Step.2a", cap.stdout)
        self.assertIn("Step.2b", cap.stdout)

    def test_dag_wave_suppressed_when_quiet(self) -> None:
        c = Console(verbose=True, quiet=True)
        with _CaptureOutput() as cap:
            c.dag_wave_start(1, 3, [self._Step("1")])
        self.assertEqual(cap.stdout, "")

    def test_dag_progress_shown(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput() as cap:
            c.dag_progress(3, 2, 8)
        self.assertIn("3/8", cap.stdout)
        self.assertIn("完了", cap.stdout)
        self.assertIn("実行中 2", cap.stdout)
        self.assertIn("残り 3", cap.stdout)

    def test_dag_progress_suppressed_when_quiet(self) -> None:
        c = Console(verbose=True, quiet=True)
        with _CaptureOutput() as cap:
            c.dag_progress(1, 1, 5)
        self.assertEqual(cap.stdout, "")


class TestStepPhaseOutput(unittest.TestCase):
    """step_phase_start / step_phase_end のテスト。"""

    def test_step_phase_start_shown(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput() as cap:
            c.step_phase_start("3", 1, 3, "メインタスク")
        self.assertIn("Phase 1/3", cap.stdout)
        self.assertIn("メインタスク", cap.stdout)

    def test_step_phase_end_with_result(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput() as cap:
            c.step_phase_end("3", 2, 3, "QA レビュー", 30.5, result="PASS")
        self.assertIn("Phase 2/3", cap.stdout)
        self.assertIn("30.5s", cap.stdout)
        self.assertIn("PASS", cap.stdout)

    def test_step_phase_suppressed_when_quiet(self) -> None:
        c = Console(verbose=True, quiet=True)
        with _CaptureOutput() as cap:
            c.step_phase_start("1", 1, 2, "テスト")
            c.step_phase_end("1", 1, 2, "テスト", 5.0)
        self.assertEqual(cap.stdout, "")


class TestExecutionPlanOutput(unittest.TestCase):
    """execution_plan のテスト。"""

    class _Step:
        def __init__(self, id_: str, title: str = ""):
            self.id = id_
            self.title = title

    def test_execution_plan_shown(self) -> None:
        c = Console(verbose=True, quiet=False)
        waves = [
            [self._Step("1", "ドメイン分析")],
            [self._Step("2a", "データモデル"), self._Step("2b", "サービスカタログ")],
        ]
        with _CaptureOutput() as cap:
            c.execution_plan(waves, 3, 15)
        self.assertIn("実行計画", cap.stdout)
        self.assertIn("Wave 1", cap.stdout)
        self.assertIn("Wave 2", cap.stdout)
        self.assertIn("ドメイン分析", cap.stdout)

    def test_execution_plan_suppressed_when_quiet(self) -> None:
        c = Console(verbose=True, quiet=True)
        with _CaptureOutput() as cap:
            c.execution_plan([[self._Step("1")]], 1, 15)
        self.assertEqual(cap.stdout, "")


class TestStepElapsedOutput(unittest.TestCase):
    """step_elapsed のテスト。"""

    def test_step_elapsed_shown_when_verbose(self) -> None:
        c = Console(verbose=True, quiet=False)
        c._step_start_times["3"] = c._start_time - 125  # 2m 5s ago
        with _CaptureOutput() as cap:
            c.step_elapsed("3")
        self.assertIn("Step.3", cap.stdout)
        self.assertIn("m", cap.stdout)
        self.assertIn("経過", cap.stdout)

    def test_step_elapsed_hidden_when_not_verbose(self) -> None:
        c = Console(verbose=False, quiet=False)
        c._step_start_times["3"] = c._start_time - 60
        with _CaptureOutput() as cap:
            c.step_elapsed("3")
        self.assertEqual(cap.stdout, "")

    def test_step_elapsed_no_crash_for_unknown_step(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput() as cap:
            c.step_elapsed("unknown")
        self.assertEqual(cap.stdout, "")


class TestConsoleCliLog(unittest.TestCase):
    """Console.cli_log() の verbosity 別表示制御テスト。"""

    def test_quiet_suppresses_all(self) -> None:
        """verbosity=0 では全ての CLI ログが抑制される。"""
        con = Console(verbosity=0)
        with unittest.mock.patch.object(con, '_emit') as mock_emit:
            con.cli_log("1", "● Environment loaded: 10 agents")
            con.cli_log("1", "○ List directory qa")
            mock_emit.assert_not_called()

    def test_compact_shows_env_loaded_as_fixed(self) -> None:
        """verbosity=1 で ● Environment loaded は確定行として出力される。"""
        con = Console(verbosity=1)
        with unittest.mock.patch.object(con, '_emit') as mock_emit:
            con.cli_log("1", "● Environment loaded: 22 custom instructions")
            mock_emit.assert_called_once()

    def test_compact_ignores_activity_lines(self) -> None:
        """verbosity=1 で ○ 行は _emit されない。"""
        con = Console(verbosity=1)
        with unittest.mock.patch.object(con, '_emit') as mock_emit:
            con.cli_log("1", "○ List directory qa")
            mock_emit.assert_not_called()

    def test_verbose_shows_all_as_fixed(self) -> None:
        """verbosity=3 で全行が確定行として出力される。"""
        con = Console(verbosity=3)
        with unittest.mock.patch.object(con, '_emit') as mock_emit:
            con.cli_log("1", "○ Search (glob)")
            mock_emit.assert_called_once()

    def test_normal_shows_important_as_fixed(self) -> None:
        """verbosity=2 で ● 行は確定行として出力される。"""
        con = Console(verbosity=2)
        with unittest.mock.patch.object(con, '_emit') as mock_emit:
            con.cli_log("1", "● Read-only remote session")
            mock_emit.assert_called_once()

    def test_tree_lines_in_verbose(self) -> None:
        """verbosity=3 で └ ツリー行が確定行として出力される。"""
        con = Console(verbosity=3)
        with unittest.mock.patch.object(con, '_emit') as mock_emit:
            con.cli_log("1", '  └ ".github/agents/KnowledgeManager*"')
            mock_emit.assert_called_once()

    def test_step_id_prefix_always_present(self) -> None:
        """step_id が出力に含まれることを確認。"""
        con = Console(verbosity=3)
        with unittest.mock.patch.object(con, '_emit') as mock_emit:
            con.cli_log("2.1", "● Environment loaded: 5 agents")
            call_args = mock_emit.call_args[0][0]
            self.assertIn("[2.1]", call_args)

    def test_normal_activity_updates_spinner_not_emit(self) -> None:
        """verbosity=2 で ○ 行は _emit ではなくスピナー更新のみ。"""
        con = Console(verbosity=2)
        with unittest.mock.patch.object(con, '_emit') as mock_emit, \
                unittest.mock.patch.object(con, '_update_spinner_msg') as mock_spinner:
            con.cli_log("1", "○ List directory qa")
            mock_emit.assert_not_called()
            mock_spinner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
