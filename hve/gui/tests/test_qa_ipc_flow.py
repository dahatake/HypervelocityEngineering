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
from hve.qa_merger import Choice, QADocument, QAMerger, QAQuestion
from hve.runner import (
    _collect_qa_answers_via_ipc,
    _persist_answered_qa_and_dispatch,
)
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
                choices=[
                    Choice(label="A", text="OK"),
                    Choice(label="B", text="NG"),
                    Choice(label="C", text="その他"),
                ],
                default_answer="A) OK",
            ),
        ]
    )


class TestQAIpcFlow(unittest.TestCase):
    """CLI 側と GUI 側の IPC フローを統合テストする。"""

    def setUp(self) -> None:
        _get_app()
        self._tmp = tempfile.mkdtemp(prefix="hve-qa-ipc-flow-")
        self.repo_root = Path(self._tmp)
        self.ipc_dir = self.repo_root / ".hve" / "qa-ipc"

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

        dispatched: list[Path] = []
        output = self.repo_root / "qa" / "gui-answered.md"
        merged = _persist_answered_qa_and_dispatch(
            doc=doc,
            user_answers_raw=result["raw"],
            use_defaults=result["skip"],
            output_path=output,
            workflow_id="aas",
            dispatcher=dispatched.append,
        )
        reparsed = QAMerger.parse_qa_file(output)
        self.assertIn("A) OK", merged)
        self.assertEqual(reparsed.questions[0].user_answer, "A) OK")
        self.assertEqual(dispatched, [output])

    def test_other_freetext_round_trip(self) -> None:
        """「その他」の自由記述が IPC を経由して変更されずに返る。"""
        cfg = SDKConfig()
        cfg.qa_answer_mode = "gui-file"
        cfg.qa_ipc_dir = str(self.ipc_dir)
        cfg.qa_gui_input_timeout_seconds = 10.0

        doc = _make_doc()
        result = {}

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
        mgr = QAIpcManager(self.ipc_dir)
        triggered = []
        mgr.questionnaire_ready.connect(
            lambda s, p, i: triggered.append((s, p, i))
        )
        end = time.monotonic() + 5.0
        while time.monotonic() < end and not triggered:
            _process_events_for(200)
        self.assertTrue(triggered, "questionnaire_ready が発火していない")
        request_doc = QAMerger.parse_qa_file(Path(triggered[0][1]))
        self.assertEqual(
            [(choice.label, choice.text) for choice in request_doc.questions[0].choices],
            [("A", "OK"), ("B", "NG"), ("C", "その他")],
        )

        mgr.write_answers("2.1", "1:: その他: GUI 固有の回答\n")
        t.join(timeout=5.0)
        self.assertFalse(t.is_alive(), "CLI スレッドが時間内に完了しなかった")
        mgr.stop_and_cleanup()

        self.assertFalse(result["skip"])
        self.assertEqual(result["raw"], "1:: その他: GUI 固有の回答\n")
        self.assertEqual(
            QAMerger.parse_answers(result["raw"]),
            {1: "その他: GUI 固有の回答"},
        )

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
