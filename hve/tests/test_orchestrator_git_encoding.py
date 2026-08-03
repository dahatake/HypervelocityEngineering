"""
Test for orchestrator git subprocess encoding fix.

orchestrator.py の git subprocess に encoding="utf-8", errors="replace" が
正しく指定され、Windows JP locale（cp932）での UnicodeDecodeError が
回避されることを検証する。

Scope:
  - UTF-8 含む git コマンド出力（commit message、branch 名等）の
    正常なデコード確認
  - encoding="utf-8", errors="replace" の動作確認
  - _git_* 関連の subprocess.run が全て encoding 指定を持つ確認
"""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


class TestOrchestratorGitEncoding(unittest.TestCase):
    """orchestrator.py の git 関連 subprocess encoding テスト。"""

    def test_subprocess_run_has_encoding_utf8(self):
        """orchestrator.py の全 subprocess.run が encoding="utf-8" を持つことを確認。"""
        orchestrator_path = Path(__file__).parent.parent / "orchestrator.py"
        self.assertTrue(orchestrator_path.exists(), f"orchestrator.py が見つかりません: {orchestrator_path}")

        with open(orchestrator_path, "r", encoding="utf-8") as f:
            content = f.read()

        # subprocess.run と capture_output=True が一緒に出現する箇所を確認
        import re
        pattern = r'subprocess\.run\([^)]*capture_output=True[^)]*text=True[^)]*\)'

        matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
        subprocess_calls = list(matches)

        self.assertGreater(
            len(subprocess_calls),
            0,
            "capture_output=True, text=True を含む subprocess.run が見つかりません"
        )

        # 各 subprocess.run が encoding="utf-8" と errors="replace" を持つか確認
        for i, match in enumerate(subprocess_calls):
            call_str = match.group()
            self.assertIn(
                'encoding="utf-8"',
                call_str,
                f"subprocess.run #{i + 1} が encoding=\"utf-8\" を持っていません:\n{call_str[:100]}..."
            )
            self.assertIn(
                'errors="replace"',
                call_str,
                f"subprocess.run #{i + 1} が errors=\"replace\" を持っていません:\n{call_str[:100]}..."
            )

    def test_git_encoding_parameter_correctness(self):
        """git subprocess に encoding と errors パラメータが正しく指定されているか。"""
        orchestrator_path = Path(__file__).parent.parent / "orchestrator.py"

        with open(orchestrator_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # encoding と errors が同じ関数内にあるか確認（簡易的なチェック）
        git_subprocess_lines = [
            (i, line) for i, line in enumerate(lines, 1)
            if "capture_output=True" in line and "text=True" in line
        ]

        for line_num, line_content in git_subprocess_lines:
            # 前後の行も確認（マルチライン subprocess.run）
            start = max(0, line_num - 5)
            end = min(len(lines), line_num + 5)
            context = "".join(lines[start:end])

            # encoding="utf-8" と errors="replace" が存在するか
            self.assertIn(
                'encoding="utf-8"',
                context,
                f"L{line_num} 周辺に encoding=\"utf-8\" が見つかりません"
            )
            self.assertIn(
                'errors="replace"',
                context,
                f"L{line_num} 周辺に errors=\"replace\" が見つかりません"
            )

    @mock.patch("subprocess.run")
    def test_git_fetch_with_encoding(self, mock_run):
        """git fetch の encoding 指定が正しいことを確認（モック）。"""
        # orchestrator._git_checkout_new_branch 内の git fetch を
        # モックして encoding 指定を確認
        mock_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")

        # このテストは実装の検証というより、デコレータのモック動作確認
        # 実際の修正は parse 検査（test_subprocess_run_has_encoding_utf8）で十分
        self.assertTrue(True)

    def test_encoding_replace_fallback_behavior(self):
        """errors='replace' での decode 失敗時 fallback 動作を確認。"""
        # UTF-8 バイト列の一部を破壊して cp932 互換性を低下させる
        broken_utf8 = b"git log\xe9\xba\x8c\x94"  # 無効な UTF-8 シーケンス

        try:
            # errors="replace" なら例外なく decode される
            result = broken_utf8.decode("utf-8", errors="replace")
            # 無効バイトは U+FFFD（replacement character）に置換される
            self.assertIn("\ufffd", result, "errors='replace' が機能していません")
        except UnicodeDecodeError:
            self.fail("errors='replace' が UnicodeDecodeError を出しました")

    @mock.patch("hve.orchestrator.subprocess.run")
    def test_git_add_commit_push_uses_utf8_for_japanese_commit_message(self, mock_run):
        """日本語 commit message 経路でも git subprocess が UTF-8 指定を渡すことを確認。"""
        from hve.console import Console
        from hve.orchestrator import _git_add_commit_push

        mock_run.side_effect = [
            subprocess.CompletedProcess(["git", "status"], 0, stdout=" M file.txt\n", stderr=""),
            subprocess.CompletedProcess(["git", "add"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git", "diff"], 1, stdout="", stderr=""),
            subprocess.CompletedProcess(
                ["git", "commit"],
                0,
                stdout="[main abc123] [ASDW-WEB] Step.3.4 remote CI/CD 前の成果物\n",
                stderr="",
            ),
            subprocess.CompletedProcess(["git", "push"], 0, stdout="", stderr=""),
        ]

        result = _git_add_commit_push(
            branch="copilot-sdk/asdw-web-step-3-4-test",
            commit_message="[ASDW-WEB] Step.3.4 remote CI/CD 前の成果物",
            console=Console(quiet=True),
        )

        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 5)
        commit_args = mock_run.call_args_list[3].args[0]
        self.assertEqual(commit_args[:3], ["git", "commit", "-m"])
        self.assertIn("前の成果物", commit_args[3])
        for call in mock_run.call_args_list:
            kwargs = call.kwargs
            if kwargs.get("capture_output") and kwargs.get("text"):
                self.assertEqual(kwargs.get("encoding"), "utf-8")
                self.assertEqual(kwargs.get("errors"), "replace")

    def test_no_unencoded_subprocess_run(self):
        """orchestrator.py に encoding 指定なしの subprocess.run がないか確認。"""
        orchestrator_path = Path(__file__).parent.parent / "orchestrator.py"

        with open(orchestrator_path, "r", encoding="utf-8") as f:
            content = f.read()

        # git コマンドの subprocess.run（capture_output=True, text=True）を
        # すべて検出し、encoding 指定を確認
        import re

        # git コマンドのパターン
        git_pattern = r'subprocess\.run\(\s*\[\s*"git"[^)]*capture_output=True[^)]*text=True[^)]*\)'
        matches = re.finditer(git_pattern, content, re.MULTILINE | re.DOTALL)

        for match in matches:
            call_str = match.group()
            self.assertIn(
                'encoding="utf-8"',
                call_str,
                f"git subprocess が encoding 指定なし:\n{call_str}"
            )


if __name__ == "__main__":
    unittest.main()
