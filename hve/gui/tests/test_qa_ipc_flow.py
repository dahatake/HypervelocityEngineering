"""test_qa_ipc_flow.py — GUI ↔ CLI IPC ファイル授受ラウンドトリップの統合テスト。

CLI 側 _collect_qa_answers_via_ipc と GUI 側 QAIpcManager を同一プロセス内で
動かして相互通信を検証する。

実行: QT_QPA_PLATFORM=offscreen pytest hve/gui/tests/test_qa_ipc_flow.py -v
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PySide6.QtWidgets import QApplication

from hve.config import SDKConfig
from hve.console import Console
from hve.qa_merger import Choice, QADocument, QAQuestion
from hve.runner import _collect_qa_answers_via_ipc
from hve.gui.qa_ipc_manager import QAIpcManager


_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _process_events_for(ms: int) -> None:
    app = _get_app()
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.05)


def _make_doc() -> QADocument:
    return QADocument(
        questions=[
            QAQuestion(
                no=1,
                question="Q1?",
                choices=[Choice(label="A", text="OK"), Choice(label="B", text="NG")],
                default_answer="A) OK",
            ),
        ]
    )


class TestQAIpcFlow(unittest.TestCase):
    """CLI 側と GUI 側の IPC フローを統合テストする。"""

    def setUp(self) -> None:
        _get_app()
        self._tmp = tempfile.mkdtemp(prefix="hve-qa-ipc-flow-")
        self.ipc_dir = Path(self._tmp)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_full_round_trip(self) -> None:
        """CLI が request 書く → GUI が answers 書く → CLI が回答取得。"""
        cfg = SDKConfig()
        cfg.qa_answer_mode = "gui-file"
        cfg.qa_ipc_dir = str(self.ipc_dir)
        cfg.qa_gui_input_timeout_seconds = 10.0

        doc = _make_doc()
        result = {}

        # CLI 側を別スレッドで実行
        def _cli_worker():
            raw, skip = asyncio.run(
                _collect_qa_answers_via_ipc(
                    Console(verbose=False, quiet=True), doc, "2.1", cfg
                )
            )
            result["raw"] = raw
            result["skip"] = skip

        t = threading.Thread(target=_cli_worker, daemon=True)
        t.start()

        # GUI 側 (本テストスレッド) で QAIpcManager 起動して回答を返す
        mgr = QAIpcManager(self.ipc_dir)
        triggered = []
        mgr.questionnaire_ready.connect(
            lambda s, p, i: triggered.append((s, p, i))
        )
        # ポーリング待機
        end = time.monotonic() + 5.0
        while time.monotonic() < end and not triggered:
            _process_events_for(200)
        self.assertTrue(triggered, "questionnaire_ready が発火していない")
        step_id, q_path, _ = triggered[0]
        self.assertEqual(step_id, "2.1")
        # 質問票ファイル本体が書き出されている
        self.assertTrue(Path(q_path).exists())

        # GUI が回答を書き出す
        mgr.write_answers("2.1", "1: A\n")
        # CLI スレッドが完了するまで待機
        t.join(timeout=5.0)
        self.assertFalse(t.is_alive(), "CLI スレッドが時間内に完了しなかった")
        mgr.stop_and_cleanup()

        self.assertIn("raw", result)
        self.assertFalse(result["skip"])
        self.assertIn("1: A", result["raw"])

    def test_cancel_round_trip(self) -> None:
        """GUI が cancel を書く → CLI が RuntimeError。"""
        cfg = SDKConfig()
        cfg.qa_answer_mode = "gui-file"
        cfg.qa_ipc_dir = str(self.ipc_dir)
        cfg.qa_gui_input_timeout_seconds = 10.0
        doc = _make_doc()
        err_holder = {}

        def _cli_worker():
            try:
                asyncio.run(
                    _collect_qa_answers_via_ipc(
                        Console(verbose=False, quiet=True), doc, "2.1", cfg
                    )
                )
            except RuntimeError as e:
                err_holder["err"] = e

        t = threading.Thread(target=_cli_worker, daemon=True)
        t.start()
        mgr = QAIpcManager(self.ipc_dir)
        triggered = []
        mgr.questionnaire_ready.connect(lambda s, p, i: triggered.append(s))
        end = time.monotonic() + 5.0
        while time.monotonic() < end and not triggered:
            _process_events_for(200)
        self.assertTrue(triggered)
        mgr.write_cancel("2.1")
        t.join(timeout=5.0)
        mgr.stop_and_cleanup()
        self.assertIn("err", err_holder, "RuntimeError が発生していない")


if __name__ == "__main__":
    unittest.main()
