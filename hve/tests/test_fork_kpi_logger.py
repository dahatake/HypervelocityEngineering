"""test_fork_kpi_logger.py — Fork-integration T4.3.

`hve/fork_kpi_logger.py` の JSONL 出力を検証する。

DoD (T4.3):
- enabled=False は no-op（ファイル作成しない）
- 1 レコード = 1 行
- 機微情報（プロンプト等）が混入しない
- I/O 失敗時に例外を投げず stderr に warn を出す
- スキーマ（必須フィールド）を満たす
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fork_kpi_logger import ForkKPILogger  # type: ignore[import-not-found]


class TestForkKPILoggerDisabled(unittest.TestCase):
    """enabled=False の no-op 動作。"""

    def test_disabled_does_not_create_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            kpi_dir = Path(td) / "kpi"
            logger = ForkKPILogger(enabled=False, run_id="run-1", kpi_dir=kpi_dir)
            logger.log_step(
                step_id="2.3",
                session_id="hve-run-1-step-2.3",
                forked_session_id=None,
                success=True,
                retry_count=0,
                elapsed_seconds=1.0,
            )
            self.assertFalse(logger.log_path.exists())
            self.assertFalse(kpi_dir.exists())


class TestForkKPILoggerEnabled(unittest.TestCase):
    """enabled=True の通常書き込み。"""

    def test_writes_jsonl_line(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            kpi_dir = Path(td) / "kpi"
            logger = ForkKPILogger(enabled=True, run_id="run-A", kpi_dir=kpi_dir)
            logger.log_step(
                step_id="2.3",
                session_id="hve-run-A-step-2.3",
                forked_session_id=None,
                success=True,
                retry_count=0,
                elapsed_seconds=12.3,
                tokens=0,
                fork_on_retry_enabled=True,
            )
            self.assertTrue(logger.log_path.exists())
            content = logger.log_path.read_text(encoding="utf-8")
            lines = [ln for ln in content.splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            # 必須フィールド
            for key in ("timestamp", "run_id", "step_id", "success",
                        "retry_count", "elapsed_seconds", "tokens",
                        "fork_on_retry_enabled"):
                self.assertIn(key, record)
            self.assertEqual(record["step_id"], "2.3")
            self.assertEqual(record["retry_count"], 0)
            self.assertTrue(record["fork_on_retry_enabled"])

    def test_appends_multiple_lines(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            kpi_dir = Path(td) / "kpi"
            logger = ForkKPILogger(enabled=True, run_id="run-B", kpi_dir=kpi_dir)
            for sid in ("1", "2", "3"):
                logger.log_step(
                    step_id=sid,
                    session_id=f"hve-run-B-step-{sid}",
                    forked_session_id=None,
                    success=True,
                    retry_count=0,
                    elapsed_seconds=0.1,
                )
            content = logger.log_path.read_text(encoding="utf-8")
            lines = [ln for ln in content.splitlines() if ln.strip()]
            self.assertEqual(len(lines), 3)
            for line in lines:
                json.loads(line)  # 各行が JSON として valid

    def test_fork_record_includes_forked_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            kpi_dir = Path(td) / "kpi"
            logger = ForkKPILogger(enabled=True, run_id="run-C", kpi_dir=kpi_dir)
            logger.log_step(
                step_id="2.3",
                session_id="hve-run-C-step-2.3",
                forked_session_id="hve-run-C-step-2.3-fork1",
                success=True,
                retry_count=1,
                elapsed_seconds=20.0,
            )
            line = logger.log_path.read_text(encoding="utf-8").strip()
            record = json.loads(line)
            self.assertEqual(record["forked_session_id"], "hve-run-C-step-2.3-fork1")
            self.assertEqual(record["retry_count"], 1)


class TestForkKPILoggerSanitization(unittest.TestCase):
    """機微情報・パストラバーサル防止。"""

    def test_unsafe_run_id_sanitized(self) -> None:
        logger = ForkKPILogger(
            enabled=True,
            run_id="../../etc/passwd",
            kpi_dir=Path("/tmp/does-not-matter"),
        )
        # `_sanitize_run_id` でパストラバーサル文字が除去されている
        self.assertNotIn("..", str(logger.log_path))
        self.assertNotIn("/", logger.log_path.name)

    def test_no_prompt_field_in_record(self) -> None:
        """ロガーは prompt / token 値などの機微情報を受け取らないため、レコードに含まれないこと。"""
        with tempfile.TemporaryDirectory() as td:
            kpi_dir = Path(td) / "kpi"
            logger = ForkKPILogger(enabled=True, run_id="run-D", kpi_dir=kpi_dir)
            logger.log_step(
                step_id="X",
                session_id="hve-run-D-step-X",
                forked_session_id=None,
                success=True,
                retry_count=0,
                elapsed_seconds=0.0,
            )
            record = json.loads(logger.log_path.read_text(encoding="utf-8").strip())
            for forbidden in ("prompt", "github_token", "api_key", "secret"):
                self.assertNotIn(forbidden, record)


class TestForkKPILoggerIOFailure(unittest.TestCase):
    """I/O 失敗時に例外を投げないこと（M11 対応: 実 mock で確実に OSError を発生させる）。"""

    def test_oserror_does_not_propagate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            kpi_dir = Path(td) / "kpi"
            logger = ForkKPILogger(enabled=True, run_id="run-E", kpi_dir=kpi_dir)

            buf = io.StringIO()
            # Path.mkdir を強制的に OSError 化して I/O 失敗を確実に再現
            with redirect_stderr(buf), patch.object(
                Path, "mkdir", side_effect=PermissionError("denied")
            ):
                # 例外が伝播しないこと
                logger.log_step(
                    step_id="Z",
                    session_id=None,
                    forked_session_id=None,
                    success=False,
                    retry_count=0,
                    elapsed_seconds=0.0,
                )

            # stderr に warn メッセージが出ていること
            self.assertIn("fork_kpi_logger", buf.getvalue())
            self.assertIn("WARN", buf.getvalue())
            # ファイルは作成されない
            self.assertFalse(logger.log_path.exists())


if __name__ == "__main__":
    unittest.main()
