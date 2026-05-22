"""test_qa_gui_file_mode.py — GUI 連携 QA 回答モード（autopilot / gui-file）の単体テスト。

検証対象:
    - runner._collect_qa_answers() の qa_answer_mode == "autopilot" 分岐
    - runner._collect_qa_answers_via_ipc() の正常系・キャンセル・タイムアウト・IPC dir 不正

前提:
    - 既存 _collect_qa_answers の非 TTY フォールバック / qa_auto_defaults 分岐は
      test_questionnaire_ui.py で検証済み。本ファイルは追加分のみ検証する。
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig
from console import Console
from qa_merger import Choice, QADocument, QAQuestion
from runner import _collect_qa_answers, _collect_qa_answers_via_ipc


def _make_console() -> Console:
    return Console(verbose=False, quiet=True)


def _make_doc() -> QADocument:
    return QADocument(
        questions=[
            QAQuestion(
                no=1,
                question="Q1?",
                choices=[Choice(label="A", text="はい"), Choice(label="B", text="いいえ")],
                default_answer="A) はい",
            ),
            QAQuestion(
                no=2,
                question="Q2?",
                choices=[Choice(label="A", text="OK"), Choice(label="B", text="NG")],
                default_answer="B) NG",
            ),
        ]
    )


class TestAutopilotMode(unittest.TestCase):
    """qa_answer_mode='autopilot' の挙動。"""

    def test_autopilot_returns_skip_input_true(self) -> None:
        cfg = SDKConfig()
        cfg.qa_answer_mode = "autopilot"
        doc = _make_doc()
        raw, skip = asyncio.run(_collect_qa_answers(_make_console(), doc, "1.1", cfg))
        self.assertEqual(raw, "")
        self.assertTrue(skip)


class TestGuiFileMode(unittest.TestCase):
    """qa_answer_mode='gui-file' の挙動。"""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="hve-qa-ipc-test-")
        self.ipc_dir = Path(self._tmp)
        self.cfg = SDKConfig()
        self.cfg.qa_answer_mode = "gui-file"
        self.cfg.qa_ipc_dir = str(self.ipc_dir)
        self.cfg.qa_gui_input_timeout_seconds = 5.0  # テスト用に短く
        self.doc = _make_doc()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _run_with_simulator(self, simulator) -> tuple[str, bool]:
        """simulator スレッドを起動して _collect_qa_answers_via_ipc を呼ぶ。"""
        result = {}
        loop_done = threading.Event()

        def _worker():
            simulator(self.ipc_dir, "1.1")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        try:
            raw, skip = asyncio.run(
                _collect_qa_answers_via_ipc(_make_console(), self.doc, "1.1", self.cfg)
            )
            result["raw"] = raw
            result["skip"] = skip
        finally:
            loop_done.set()
            t.join(timeout=5.0)
        return result["raw"], result["skip"]

    def test_answers_file_returns_user_answers(self) -> None:
        """GUI が answers.md を書き出すと回答が返る。"""
        def sim(ipc: Path, step_id: str) -> None:
            time.sleep(0.5)
            # request JSON が CLI 側で書かれているはず
            req = ipc / f"{step_id}.request.json"
            for _ in range(30):
                if req.exists():
                    break
                time.sleep(0.1)
            (ipc / f"{step_id}.answers.md").write_text("1: A\n2: B\n", encoding="utf-8")

        raw, skip = self._run_with_simulator(sim)
        self.assertFalse(skip)
        self.assertIn("1: A", raw)
        self.assertIn("2: B", raw)

    def test_cancel_file_raises(self) -> None:
        """cancel ファイル検出時は RuntimeError。"""
        def sim(ipc: Path, step_id: str) -> None:
            time.sleep(0.5)
            (ipc / f"{step_id}.cancel").write_text("", encoding="utf-8")

        with self.assertRaises(RuntimeError) as ctx:
            self._run_with_simulator(sim)
        self.assertIn("キャンセル", str(ctx.exception))

    def test_timeout_falls_back_to_defaults(self) -> None:
        """タイムアウト時は既定値採用 (skip_input=True)。"""
        self.cfg.qa_gui_input_timeout_seconds = 2.0

        def sim(ipc: Path, step_id: str) -> None:
            pass  # 何もしない → タイムアウト

        raw, skip = self._run_with_simulator(sim)
        self.assertEqual(raw, "")
        self.assertTrue(skip)

    def test_empty_answers_treated_as_defaults(self) -> None:
        """空の answers.md は既定値採用扱い。"""
        def sim(ipc: Path, step_id: str) -> None:
            time.sleep(0.3)
            (ipc / f"{step_id}.answers.md").write_text("", encoding="utf-8")

        raw, skip = self._run_with_simulator(sim)
        self.assertEqual(raw, "")
        self.assertTrue(skip)

    def test_missing_ipc_dir_falls_back(self) -> None:
        """qa_ipc_dir=None の場合は既定値採用。"""
        self.cfg.qa_ipc_dir = None
        raw, skip = asyncio.run(
            _collect_qa_answers_via_ipc(_make_console(), self.doc, "1.1", self.cfg)
        )
        self.assertEqual(raw, "")
        self.assertTrue(skip)

    def test_request_json_schema(self) -> None:
        """CLI が書き出す request JSON が schema を満たす。"""
        captured = {}

        def sim(ipc: Path, step_id: str) -> None:
            time.sleep(0.5)
            req = ipc / f"{step_id}.request.json"
            for _ in range(30):
                if req.exists():
                    captured["data"] = json.loads(req.read_text(encoding="utf-8"))
                    break
                time.sleep(0.1)
            (ipc / f"{step_id}.answers.md").write_text("1: A\n", encoding="utf-8")

        self._run_with_simulator(sim)
        data = captured.get("data", {})
        self.assertEqual(data.get("schema_version"), 1)
        self.assertEqual(data.get("step_id"), "1.1")
        self.assertIsInstance(data.get("pid"), int)
        self.assertIn("created_at", data)
        self.assertIn("questionnaire_path", data)
        # questionnaire ファイル本体が IPC dir に書かれていたこと（クリーンアップ後でも path 文字列は確認可）
        self.assertTrue(str(data["questionnaire_path"]).endswith("1.1.questionnaire.md"))


if __name__ == "__main__":
    unittest.main()
