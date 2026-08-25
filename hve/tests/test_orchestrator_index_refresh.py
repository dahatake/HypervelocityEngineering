"""FR-CLI-77: watcher 起動の直列化と、起動時差分更新を開始するサブコマンドの限定。

RED 先行。`orchestrator._start_index_watchers` /
`orchestrator._start_index_watchers_when_idle` と `hve/__main__.py` の結線は
本テストの後に追加する。
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SDKConfig  # noqa: E402
from orchestrator import run_workflow  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class TestWatcherStartIsDeferred(unittest.TestCase):
    def test_refresh_completes_before_any_watcher_is_constructed(self) -> None:
        import orchestrator

        order: list[str] = []

        def _wait(*_a, **_k) -> bool:
            order.append("wait")
            return True

        class _FakeWatcher:
            def __init__(self, *_a, **_k) -> None:
                order.append("watcher")

            def start(self) -> bool:
                return False

        cfg = SDKConfig(dry_run=False, quiet=True, mdq_watch=True, cq_watch=True)

        # `orchestrator` は相対 / 絶対 import の双方で読み込まれうるため、
        # モジュール名ではなく orchestrator が実際に保持する参照へパッチする。
        with patch.object(orchestrator.index_refresh, "wait_until_idle", new=_wait), \
             patch("mdq.watcher.MdqWatcher", new=_FakeWatcher), \
             patch("cq.watcher.CqWatcher", new=_FakeWatcher):
            orchestrator._start_index_watchers(cfg)

        self.assertTrue(order, "watcher 起動経路が実行されていない")
        self.assertEqual(order[0], "wait")

    def test_dry_run_starts_no_watcher_thread(self) -> None:
        import orchestrator

        cfg = SDKConfig(dry_run=True, quiet=True, mdq_watch=True, cq_watch=True)

        self.assertIsNone(orchestrator._start_index_watchers_when_idle(cfg))

    def test_disabled_watch_flags_start_no_thread(self) -> None:
        import orchestrator

        cfg = SDKConfig(dry_run=False, quiet=True, mdq_watch=False, cq_watch=False)

        self.assertIsNone(orchestrator._start_index_watchers_when_idle(cfg))

    def test_run_workflow_uses_the_deferred_starter(self) -> None:
        with patch("orchestrator._start_index_watchers_when_idle") as spy:
            _run(run_workflow(
                workflow_id="aas",
                params={"branch": "main", "selected_steps": []},
                config=SDKConfig(dry_run=True, quiet=True),
            ))

        spy.assert_called_once()


class TestEntryCommands(unittest.TestCase):
    def test_orchestrator_entry_commands_are_declared(self) -> None:
        from hve.__main__ import INDEX_REFRESH_COMMANDS

        self.assertEqual(INDEX_REFRESH_COMMANDS, frozenset({"run", "cli", "orchestrate"}))

    def test_orchestrate_starts_the_refresh(self) -> None:
        import hve.__main__ as entry

        with patch("hve.index_refresh.start_background") as spy, \
             patch.object(entry, "_ensure_run_workdir_env"), \
             patch.object(entry, "_cmd_orchestrate", return_value=0):
            entry.main(["orchestrate", "--workflow", "aas"])

        spy.assert_called_once()

    def test_login_does_not_start_the_refresh(self) -> None:
        import hve.__main__ as entry

        with patch("hve.index_refresh.start_background") as spy, \
             patch.object(entry, "_cmd_login", return_value=0):
            entry.main(["login", "--status"])

        spy.assert_not_called()

    def test_index_unrelated_commands_are_excluded(self) -> None:
        from hve.__main__ import INDEX_REFRESH_COMMANDS

        for command in ("gui", "login", "pricing", "toolsearch",
                        "qa-merge", "workiq-doctor", "emit-prompt", "ingest-docs"):
            self.assertNotIn(command, INDEX_REFRESH_COMMANDS)

    def test_default_gui_launch_is_left_to_the_gui(self) -> None:
        """引数なしは GUI 既定起動のため CLI 側では開始しない（FR-GUI-22 が担う）。"""
        from hve.__main__ import INDEX_REFRESH_COMMANDS

        self.assertNotIn(None, INDEX_REFRESH_COMMANDS)


if __name__ == "__main__":
    unittest.main()
