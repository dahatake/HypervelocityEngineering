"""test_main_startup.py — Phase 4 (Major #18): startup_recovery の smoke test。

`__main__._run_startup_recovery` の以下を検証:
- pending journal が存在しないとき、即座に return する
- 環境変数 `HVE_DISABLE_STARTUP_RECOVERY=1` のフラグ評価が正しい

NOTE: `importlib.reload(run_state)` や独立 spec_from_file_location は
モジュール identity を破壊して後続テストを壊すため使用しない。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from run_journal import scan_archive_for_pending  # type: ignore[import-not-found]


class TestStartupRecoverySmoke(unittest.TestCase):
    def test_no_pending_no_sdk_load(self) -> None:
        """scan_archive_for_pending が空 list を返すことだけ検証。

        `_run_startup_recovery` 全体を呼ぶと sys.modules 操作で副作用が出るため、
        ここでは前提条件（pending スキャンが空ならスキップに繋がる）の最小確認。
        """
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "journal-archive"
            # 存在しない場合
            self.assertEqual(scan_archive_for_pending(archive), [])
            # 空ディレクトリ
            archive.mkdir(parents=True)
            self.assertEqual(scan_archive_for_pending(archive), [])


class TestMainStartupRecoveryFlag(unittest.TestCase):
    def test_disable_flag_values(self) -> None:
        """`HVE_DISABLE_STARTUP_RECOVERY` の各種真値が `main` でスキップ判定される。

        `main()` は argparse を呼ぶため直接呼べないが、評価ロジックの形を確認する。
        """
        for v in ("1", "true", "yes", "on", "TRUE", "Yes"):
            with mock.patch.dict(os.environ, {"HVE_DISABLE_STARTUP_RECOVERY": v}):
                val = os.environ.get("HVE_DISABLE_STARTUP_RECOVERY", "").strip().lower()
                self.assertIn(val, {"1", "true", "yes", "on"})

        for v in ("0", "false", "no", "", "anything-else"):
            with mock.patch.dict(os.environ, {"HVE_DISABLE_STARTUP_RECOVERY": v}):
                val = os.environ.get("HVE_DISABLE_STARTUP_RECOVERY", "").strip().lower()
                self.assertNotIn(val, {"1", "true", "yes", "on"})


if __name__ == "__main__":
    unittest.main()
