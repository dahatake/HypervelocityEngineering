"""test_console.py — Console の verbose/quiet 切り替えテスト"""

from __future__ import annotations

import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from console import Console


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
        self.assertIn("10.0", cap.stdout)

    def test_error_always_shown(self) -> None:
        c = self._make()
        with _CaptureOutput() as cap:
            c.error("致命的エラー")
        self.assertIn("致命的エラー", cap.stderr)


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


if __name__ == "__main__":
    unittest.main()
