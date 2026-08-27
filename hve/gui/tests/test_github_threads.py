"""hve.gui.tests.test_github_threads

FR-GUI-26 / FR-GUI-27: GitHub API 呼び出しを GUI スレッド外で実行するワーカーの単体テスト。
"""

from __future__ import annotations

import os
import threading
from typing import Any, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QThread, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.github_service import GitHubServiceError  # noqa: E402
from hve.gui.github_threads import GitHubWorker  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _run_worker(task):
    """ワーカーを実行し (succeeded_payloads, failed_messages, worker_thread_ids) を返す。"""
    worker = GitHubWorker(task)
    ok: List[Any] = []
    ng: List[str] = []
    tids: List[int] = []
    worker.succeeded.connect(
        lambda payload: (ok.append(payload), tids.append(threading.get_ident())),
        Qt.ConnectionType.DirectConnection,
    )
    worker.failed.connect(
        lambda message: (ng.append(message), tids.append(threading.get_ident())),
        Qt.ConnectionType.DirectConnection,
    )
    worker.start()
    assert worker.wait(10_000), "worker did not finish within 10s"
    return ok, ng, tids


class TestWorkerSignals:
    def test_success_emits_payload(self, qapp) -> None:
        ok, ng, _ = _run_worker(lambda: [{"number": 1}])
        assert ok == [[{"number": 1}]]
        assert ng == []

    def test_none_result_is_still_emitted(self, qapp) -> None:
        ok, ng, _ = _run_worker(lambda: None)
        assert ok == [None]
        assert ng == []

    def test_service_error_emits_its_message(self, qapp) -> None:
        def _task():
            raise GitHubServiceError("対象が見つかりません。")

        ok, ng, _ = _run_worker(_task)
        assert ok == []
        assert ng == ["対象が見つかりません。"]

    def test_title_generation_error_emits_safe_domain_message(self, qapp) -> None:
        from hve.github_title_generator import GitHubTitleGenerationError

        def _task():
            raise GitHubTitleGenerationError("Copilot CLI がタイムアウトしました。")

        ok, ng, _ = _run_worker(_task)
        assert ok == []
        assert ng == ["Copilot CLI がタイムアウトしました。"]

    def test_unexpected_error_includes_type_name(self, qapp) -> None:
        def _task():
            raise ValueError("broken")

        ok, ng, _ = _run_worker(_task)
        assert ok == []
        assert len(ng) == 1
        assert "ValueError" in ng[0]
        assert "broken" not in ng[0]

    def test_task_runs_off_the_gui_thread(self, qapp) -> None:
        gui_thread_id = threading.get_ident()
        captured: List[int] = []

        ok, ng, _ = _run_worker(lambda: captured.append(threading.get_ident()))
        assert ng == []
        assert captured and captured[0] != gui_thread_id

    def test_emits_exactly_one_signal(self, qapp) -> None:
        ok, ng, _ = _run_worker(lambda: "value")
        assert len(ok) + len(ng) == 1


class TestActiveRegistry:
    """呼び出し側が GC されても実行中スレッドが解放されないこと。"""

    def test_running_worker_is_registered(self, qapp) -> None:
        from hve.gui import github_threads

        release = threading.Event()
        worker = GitHubWorker(lambda: release.wait(10))
        worker.start()
        try:
            assert worker in github_threads._ACTIVE
        finally:
            release.set()
            assert worker.wait(10_000)

    def test_finished_worker_is_unregistered(self, qapp) -> None:
        from hve.gui import github_threads

        worker = GitHubWorker(lambda: "done")
        worker.start()
        assert worker.wait(10_000)
        # finished の配送にイベントループが必要なため明示的に回す
        QApplication.processEvents()
        assert worker not in github_threads._ACTIVE

    def test_start_failure_does_not_leak_active_worker(
        self, qapp, monkeypatch
    ) -> None:
        from hve.gui import github_threads

        worker = GitHubWorker(lambda: "never runs")

        def _fail_start(_thread, *_args, **_kwargs):
            raise RuntimeError("thread unavailable")

        monkeypatch.setattr(QThread, "start", _fail_start)

        with pytest.raises(RuntimeError, match="thread unavailable"):
            worker.start()

        assert worker not in github_threads._ACTIVE
