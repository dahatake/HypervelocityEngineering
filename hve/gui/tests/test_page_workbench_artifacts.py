"""WorkbenchPage の session_artifacts 収集機構のテスト。

Step 1 ⇔ Step 2 を往復するセッションで、orchestrator が書き込みしたファイル
パスを累積して Step 1 に提示するための基盤 API を検証する。
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.page_workbench import WorkbenchPage  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    return app


def _stats_line(kind: str, **fields: object) -> str:
    payload = {"kind": kind, **fields}
    return "[hve:stats] " + json.dumps(payload, ensure_ascii=False, sort_keys=True)


class TestSessionArtifacts(unittest.TestCase):
    def setUp(self) -> None:
        _ensure_app()
        self.page = WorkbenchPage()

    def test_initial_state_is_empty(self) -> None:
        self.assertEqual(self.page.session_artifacts(), [])

    def test_write_event_is_recorded(self) -> None:
        self.page._on_line_received(
            _stats_line("file_io", step="s1", path="docs/foo.md", mode="write")
        )
        artifacts = self.page.session_artifacts()
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].name, "foo.md")

    def test_read_event_is_ignored(self) -> None:
        self.page._on_line_received(
            _stats_line("file_io", step="s1", path="docs/bar.md", mode="read")
        )
        self.assertEqual(self.page.session_artifacts(), [])

    def test_duplicate_paths_are_deduplicated(self) -> None:
        for _ in range(3):
            self.page._on_line_received(
                _stats_line("file_io", step="s1", path="docs/dup.md", mode="write")
            )
        self.assertEqual(len(self.page.session_artifacts()), 1)

    def test_order_is_preserved(self) -> None:
        for name in ("a.md", "b.md", "c.md"):
            self.page._on_line_received(
                _stats_line("file_io", step="s1", path=f"docs/{name}", mode="write")
            )
        artifacts = self.page.session_artifacts()
        self.assertEqual([p.name for p in artifacts], ["a.md", "b.md", "c.md"])

    def test_clear_session_artifacts(self) -> None:
        self.page._on_line_received(
            _stats_line("file_io", step="s1", path="docs/x.md", mode="write")
        )
        self.assertEqual(len(self.page.session_artifacts()), 1)
        self.page.clear_session_artifacts()
        self.assertEqual(self.page.session_artifacts(), [])

    def test_non_file_io_events_ignored(self) -> None:
        self.page._on_line_received(
            _stats_line("tool_invoked", step="s1", tool_name="bash", action_name="ls")
        )
        self.assertEqual(self.page.session_artifacts(), [])

    def test_invalid_payload_does_not_crash(self) -> None:
        # path missing
        self.page._on_line_received(_stats_line("file_io", step="s1", mode="write"))
        # mode missing
        self.page._on_line_received(
            _stats_line("file_io", step="s1", path="x.md")
        )
        self.assertEqual(self.page.session_artifacts(), [])

    def test_session_artifacts_returns_copy(self) -> None:
        """返り値は内部リストのコピーで、外部変更が内部状態に波及しないこと。"""
        self.page._on_line_received(
            _stats_line("file_io", step="s1", path="docs/y.md", mode="write")
        )
        snapshot = self.page.session_artifacts()
        snapshot.clear()
        self.assertEqual(len(self.page.session_artifacts()), 1)


if __name__ == "__main__":
    unittest.main()
