"""test_console.py — Console の verbose/quiet 切り替えテスト"""

from __future__ import annotations

import io
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from console import Console, _ACTION_DISPLAY, _format_elapsed_ja


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

    def test_header_lines_always_timestamp_prefixed(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.header("テストヘッダー")
        non_empty_lines = [line for line in cap.stdout.splitlines() if line.strip()]
        self.assertTrue(non_empty_lines)
        self.assertTrue(all(line.startswith("[") for line in non_empty_lines))

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


class TestConsoleReasoningStream(unittest.TestCase):
    """reasoning_* 系メソッドの表示とバッファ動作を検証する。"""

    def test_reasoning_token_flushes_on_newline(self) -> None:
        c = Console(verbosity=1, show_reasoning=True)
        with unittest.mock.patch.object(c, "thinking") as mock_thinking:
            c.reasoning_token("1.1", "line1\nline2")
        mock_thinking.assert_called_once_with("1.1", "line1")
        self.assertEqual(c._reasoning_buffer.get("1.1"), "line2")

    def test_reasoning_token_suppressed_when_show_reasoning_false(self) -> None:
        c = Console(verbosity=1, show_reasoning=False)
        with unittest.mock.patch.object(c, "thinking") as mock_thinking:
            c.reasoning_token("1.1", "hidden\n")
        mock_thinking.assert_not_called()
        self.assertEqual(c._reasoning_buffer.get("1.1", ""), "")

    def test_reasoning_flush_outputs_remaining_text(self) -> None:
        c = Console(verbosity=1, show_reasoning=True)
        with unittest.mock.patch.object(c, "thinking") as mock_thinking:
            c.reasoning_token("1.1", "tail")
            c.reasoning_flush("1.1")
        mock_thinking.assert_called_once_with("1.1", "tail")
        self.assertEqual(c._reasoning_buffer.get("1.1", ""), "")

    def test_reasoning_complete_flushes_and_emits_summary_at_verbosity3(self) -> None:
        c = Console(verbosity=3, show_reasoning=True)
        with unittest.mock.patch.object(c, "thinking") as mock_thinking, \
             unittest.mock.patch.object(c, "event") as mock_event:
            c.reasoning_token("1.1", "line")
            c.reasoning_complete("1.1", "line")
        mock_thinking.assert_called_once_with("1.1", "line")
        mock_event.assert_called_once_with("💭 [1.1] 推論完了 (4 chars)")

    def test_reasoning_token_multiline_japanese(self) -> None:
        c = Console(verbosity=1, show_reasoning=True)
        with unittest.mock.patch.object(c, "thinking") as mock_thinking:
            c.reasoning_token("1.1", "大きなファイルを読む\n要点を整理する\n")
        self.assertEqual(
            mock_thinking.call_args_list,
            [
                unittest.mock.call("1.1", "大きなファイルを読む"),
                unittest.mock.call("1.1", "要点を整理する"),
            ],
        )
        self.assertEqual(c._reasoning_buffer.get("1.1", ""), "")

    def test_reasoning_token_keeps_blank_lines(self) -> None:
        c = Console(verbosity=1, show_reasoning=True)
        with unittest.mock.patch.object(c, "thinking") as mock_thinking:
            c.reasoning_token("1.1", "line1\n\nline3\n")
        self.assertEqual(
            mock_thinking.call_args_list,
            [
                unittest.mock.call("1.1", "line1"),
                unittest.mock.call("1.1", ""),
                unittest.mock.call("1.1", "line3"),
            ],
        )

    def test_reasoning_complete_suppresses_summary_when_show_reasoning_false(self) -> None:
        c = Console(verbosity=3, show_reasoning=False)
        with unittest.mock.patch.object(c, "thinking") as mock_thinking, \
             unittest.mock.patch.object(c, "event") as mock_event:
            c.reasoning_token("1.1", "line")
            c.reasoning_complete("1.1", "line")
        mock_thinking.assert_not_called()
        mock_event.assert_not_called()
        self.assertEqual(c._reasoning_buffer.get("1.1", ""), "")


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
    _BANNER_WIDTH = 58
    _LEFT_SPACE_OFFSET = 1

    def _visible_col(self, console: Console, line: str, marker: str) -> int:
        marker_index = line.rfind(marker)
        self.assertNotEqual(marker_index, -1)
        normalized = (
            line[: marker_index + 1]
            .replace("│", "|")
            .replace("╮", "|")
            .replace("╯", "|")
            .replace("╭", "+")
            .replace("╰", "+")
            .replace("─", "-")
        )
        # 文字数（1-based）を右端の0-based列位置へ変換する。
        return console._visible_len(normalized) - 1

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

    def test_banner_right_border_aligned(self) -> None:
        with unittest.mock.patch("sys.stdout", new=io.StringIO()) as stdout:
            c = Console(verbosity=3)
            with unittest.mock.patch.object(c, "_is_tty", False):
                c.banner("実行計画", "サブタイトル")

        lines = [line for line in stdout.getvalue().splitlines() if line]
        content_lines = [line for line in lines if "│" in line]
        visible_widths = [c._visible_len(line) for line in content_lines]
        self.assertTrue(all(w == visible_widths[0] for w in visible_widths))

        top = next((line for line in lines if "╮" in line), None)
        bottom = next((line for line in lines if "╯" in line), None)
        if top is None or bottom is None:
            self.fail("バナーの上下罫線が出力されていません")

        right_border_col = self._visible_col(c, top, "╮")
        self.assertEqual(self._visible_col(c, bottom, "╯"), right_border_col)
        self.assertTrue(all(self._visible_col(c, line, "│") == right_border_col for line in content_lines))

    def test_banner_padding_uses_single_left_space_offset(self) -> None:
        title = "Execution Plan"
        with unittest.mock.patch("sys.stdout", new=io.StringIO()) as stdout:
            c = Console(verbosity=3)
            with unittest.mock.patch.object(c, "_is_tty", False):
                c.banner(title, "subtitle")

        lines = [line for line in stdout.getvalue().splitlines() if line]
        title_line = next((line for line in lines if title in line), None)
        self.assertIsNotNone(title_line)
        assert title_line is not None
        left = "  │ "
        self.assertTrue(title_line.startswith(left + title))
        right_border_index = title_line.rfind("│")
        padding = title_line[len(left + title):right_border_index]
        self.assertEqual(
            len(padding),
            self._BANNER_WIDTH - self._LEFT_SPACE_OFFSET - len(title),
        )

    def test_banner_right_border_aligned_with_ambiguous_char_on_windows(self) -> None:
        title = "HVE — GitHub Copilot SDK Workflow Orchestrator"
        subtitle = "ワークフローをインタラクティブに実行します"

        with unittest.mock.patch.object(sys, "platform", "win32"):
            with unittest.mock.patch("sys.stdout", new=io.StringIO()) as stdout:
                c = Console(verbosity=3)
                with unittest.mock.patch.object(c, "_is_tty", False):
                    c.banner(title, subtitle)

            lines = [line for line in stdout.getvalue().splitlines() if line]
            content_lines = [line for line in lines if "│" in line]
            self.assertGreaterEqual(len(content_lines), 2)

            top = next((line for line in lines if "╮" in line), None)
            self.assertIsNotNone(top)
            right_border_col = self._visible_col(c, top, "╮")
            self.assertTrue(
                all(self._visible_col(c, line, "│") == right_border_col for line in content_lines),
                msg=f"Expected all right borders at column {right_border_col}",
            )


class TestConsoleCharWidth(unittest.TestCase):
    """_char_width() の表示幅判定テスト。"""

    def test_ambiguous_is_1_on_windows(self) -> None:
        with unittest.mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(Console._char_width("—"), 1)
            self.assertEqual(Console._char_width("…"), 1)

    def test_ambiguous_is_2_on_non_windows(self) -> None:
        with unittest.mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(Console._char_width("—"), 2)
            self.assertEqual(Console._char_width("…"), 2)


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

    def test_panel_cjk_and_ansi_right_border_aligned(self) -> None:
        c = Console(verbose=True, quiet=False)
        lines = ["Wave 1: Step.1 original-docs 質問票生成", "\033[1m合計: 1 ステップ / 1 Wave\033[0m"]
        with _CaptureOutput() as cap:
            c.panel("実行計画 (DAG)", lines)

        output_lines = [line for line in cap.stdout.splitlines() if line]
        content_lines = [line for line in output_lines if "│" in line]
        visible_widths = [c._visible_len(line) for line in content_lines]
        self.assertTrue(all(w == visible_widths[0] for w in visible_widths))


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

    def test_empty_returns_default_index(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value=""):
            idx = c.menu_select("選択", ["A", "B", "C"], allow_empty=True, default_index=1)
        self.assertEqual(idx, 1)

    def test_empty_allow_empty_without_default_returns_minus_one(self) -> None:
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput(), unittest.mock.patch("builtins.input", return_value=""):
            idx = c.menu_select("選択", ["A", "B"], allow_empty=True)
        self.assertEqual(idx, -1)


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


class TestCopilotStyleOutput(unittest.TestCase):
    """Copilot CLI 風の thinking/action 表示テスト。"""

    def test_action_display_mapping_contains_search(self) -> None:
        self.assertEqual(_ACTION_DISPLAY["grep"], "Search (grep)")

    def test_thinking_verbosity_2_emits_no_timestamp(self) -> None:
        c = Console(verbosity=2)
        with unittest.mock.patch.object(c, "_emit") as mock_emit:
            c.thinking("1", "I'm looking into this.")
        mock_emit.assert_called_once()
        self.assertIn("ts", mock_emit.call_args.kwargs)
        self.assertFalse(mock_emit.call_args.kwargs["ts"])

    def test_thinking_verbosity_1_emits_no_timestamp(self) -> None:
        c = Console(verbosity=1)
        with unittest.mock.patch.object(c, "_emit") as mock_emit:
            c.thinking("1", "I'm looking into this.")
        mock_emit.assert_called_once()
        self.assertIn("ts", mock_emit.call_args.kwargs)
        self.assertFalse(mock_emit.call_args.kwargs["ts"])

    def test_action_start_verbosity_2_prints_tree(self) -> None:
        c = Console(verbosity=2)
        with unittest.mock.patch.object(c, "_emit") as mock_emit:
            c.action_start("1", "Search (grep)", '"pattern" (hve)')
        self.assertEqual(mock_emit.call_count, 2)
        first_msg = mock_emit.call_args_list[0].args[0]
        second_msg = mock_emit.call_args_list[1].args[0]
        self.assertIn("[1]", first_msg)
        self.assertIn("Search (grep)", first_msg)
        self.assertIn("│", second_msg)

    def test_action_result_verbosity_2_prints_tree_leaf(self) -> None:
        c = Console(verbosity=2)
        with unittest.mock.patch.object(c, "_emit") as mock_emit:
            c.action_result("1", "12 files found")
        mock_emit.assert_called_once()
        self.assertIn("[1]", mock_emit.call_args.args[0])
        self.assertIn("└", mock_emit.call_args.args[0])


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

    def test_step_elapsed_shown_when_normal_verbosity(self) -> None:
        c = Console(verbose=False, quiet=False, verbosity=2)
        c._step_start_times["3"] = c._start_time - 60
        with _CaptureOutput() as cap:
            c.step_elapsed("3")
        self.assertIn("Step.3", cap.stdout)
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


class TestStepIOSummary(unittest.TestCase):
    """step_io_summary と track_file のテスト。"""

    def test_track_file_read_write(self) -> None:
        """read + write を蓄積し、step_io_summary で表示される。"""
        c = Console(verbose=True, quiet=False)
        c.track_file("1", "docs/input.md", "read")
        c.track_file("1", "docs/input2.md", "read")
        c.track_file("1", "docs/output.md", "write")
        with _CaptureOutput() as cap:
            c.step_io_summary("1")
        self.assertIn("2 read", cap.stdout)
        self.assertIn("1 written", cap.stdout)
        self.assertIn("docs/input.md", cap.stdout)
        self.assertIn("docs/output.md", cap.stdout)

    def test_track_file_empty(self) -> None:
        """ファイルなしの場合、何も出力されない。"""
        c = Console(verbose=True, quiet=False)
        with _CaptureOutput() as cap:
            c.step_io_summary("1")
        self.assertEqual(cap.stdout.strip(), "")

    def test_track_file_no_tracked_files(self) -> None:
        """step_id は存在するがファイルが空の場合も出力なし。"""
        c = Console(verbose=True, quiet=False)
        c._step_files["1"] = {"read": [], "write": []}
        with _CaptureOutput() as cap:
            c.step_io_summary("1")
        self.assertEqual(cap.stdout.strip(), "")

    def test_quiet_no_output(self) -> None:
        """quiet=True で非表示。"""
        c = Console(verbose=False, quiet=True)
        c.track_file("1", "docs/file.md", "read")
        with _CaptureOutput() as cap:
            c.step_io_summary("1")
        self.assertEqual(cap.stdout.strip(), "")

    def test_verbosity_1_write_shows_summary_only(self) -> None:
        """verbosity=1 で write がある場合は件数サマリーのみ確定行表示する。"""
        c = Console(verbosity=1)
        c.track_file("1", "docs/file.md", "write")
        with _CaptureOutput() as cap:
            c.step_io_summary("1")
        self.assertIn("Files:", cap.stdout)
        self.assertNotIn("docs/file.md", cap.stdout)

    def test_verbosity_1_read_only_updates_spinner(self) -> None:
        """verbosity=1 で write がない場合はスピナー更新のみ。"""
        c = Console(verbosity=1)
        c.track_file("1", "docs/input.md", "read")
        with unittest.mock.patch.object(c, "_print") as mock_print, \
                unittest.mock.patch.object(c, "_update_spinner_msg") as mock_spinner:
            c.step_io_summary("1")
        mock_print.assert_not_called()
        mock_spinner.assert_called_once()

    def test_verbosity_2_write_shown(self) -> None:
        """verbosity=2 で write ファイルが確定行表示される。"""
        c = Console(verbosity=2)
        c.track_file("1", "docs/input.md", "read")
        c.track_file("1", "docs/output.md", "write")
        with _CaptureOutput() as cap:
            c.step_io_summary("1")
        self.assertIn("1 read", cap.stdout)
        self.assertIn("1 written", cap.stdout)
        self.assertIn("docs/output.md", cap.stdout)
        self.assertNotIn("docs/input.md", cap.stdout)

    def test_verbosity_3_all_shown(self) -> None:
        """verbosity=3 で read + write 全ファイルが表示される。"""
        c = Console(verbosity=3)
        c.track_file("1", "docs/input.md", "read")
        c.track_file("1", "docs/output.md", "write")
        with _CaptureOutput() as cap:
            c.step_io_summary("1")
        self.assertIn("docs/input.md", cap.stdout)
        self.assertIn("docs/output.md", cap.stdout)

    def test_max_display_truncation(self) -> None:
        """max_display を超えるファイルは省略される。"""
        c = Console(verbose=True, quiet=False)
        for i in range(20):
            c.track_file("1", f"docs/file-{i:02d}.md", "write")
        with _CaptureOutput() as cap:
            c.step_io_summary("1", max_display=5)
        self.assertIn("20 written", cap.stdout)
        self.assertIn("docs/file-00.md", cap.stdout)
        self.assertIn("docs/file-04.md", cap.stdout)
        self.assertNotIn("docs/file-05.md", cap.stdout)

    def test_track_file_dedup(self) -> None:
        """同一パスを2回追加しても1件のみ蓄積される。"""
        c = Console(verbose=True, quiet=False)
        c.track_file("1", "docs/file.md", "read")
        c.track_file("1", "docs/file.md", "read")
        self.assertEqual(len(c._step_files["1"]["read"]), 1)

    def test_track_file_normalized_dedup(self) -> None:
        """正規化後に同一パスなら1件のみ蓄積される。"""
        c = Console(verbose=True, quiet=False)
        c.track_file("1", "./docs/file.md", "read")
        c.track_file("1", "docs/file.md", "read")
        self.assertEqual(len(c._step_files["1"]["read"]), 1)

    def test_step_end_cleans_files(self) -> None:
        """step_end 呼び出し後に _step_files からエントリが削除される。"""
        c = Console(verbose=True, quiet=False)
        c.track_file("1", "docs/file.md", "read")
        self.assertIn("1", c._step_files)
        with _CaptureOutput():
            c.step_end("1", "success", elapsed=1.0)
        self.assertNotIn("1", c._step_files)


class TestFileIO(unittest.TestCase):
    """file_io の表示制御テスト。"""

    def test_verbosity_0_no_output(self) -> None:
        c = Console(verbosity=0)
        with _CaptureOutput() as cap:
            c.file_io("1", "docs/file.md", "read")
        self.assertEqual(cap.stdout.strip(), "")

    def test_verbosity_1_updates_spinner(self) -> None:
        c = Console(verbosity=1)
        with unittest.mock.patch.object(c, "_print") as mock_print, \
                unittest.mock.patch.object(c, "_update_spinner_msg") as mock_spinner:
            c.file_io("1", "docs/file.md", "write")
        mock_print.assert_not_called()
        mock_spinner.assert_called_once()

    def test_verbosity_2_prints_fixed_line(self) -> None:
        c = Console(verbosity=2)
        with _CaptureOutput() as cap:
            c.file_io("1", "docs/file.md", "read")
        self.assertIn("← [1] docs/file.md", cap.stdout)


if __name__ == "__main__":
    unittest.main()
