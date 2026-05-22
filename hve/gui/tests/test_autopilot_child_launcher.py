"""hve.gui.autopilot.child_launcher の AutopilotController テスト。

`subprocess.Popen` をモック化し、APP 単位の並列レーン + チェーン内直列 の挙動を検証する。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.autopilot.child_launcher import (  # noqa: E402
    AutopilotController,
    _detached_popen_kwargs,
)
from hve.gui.autopilot.plan_model import AppChain, AutopilotPlan  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeProc:
    """`subprocess.Popen` の極小モック。"""

    _pid_counter = 1000

    def __init__(self, exit_code: int = 0, finish_immediately: bool = True) -> None:
        _FakeProc._pid_counter += 1
        self.pid = _FakeProc._pid_counter
        self._exit_code = exit_code
        self._finished = finish_immediately
        self.terminate_called = False

    def poll(self):
        return self._exit_code if self._finished else None

    def terminate(self) -> None:
        self.terminate_called = True
        self._finished = True


def _plan(app_ids: List[str], *, max_parallel: int = 4) -> AutopilotPlan:
    chains = [
        AppChain(app_id=aid, architecture="Webフロントエンド + クラウド",
                 workflows=["aad-web", "asdw-web"])
        for aid in app_ids
    ]
    return AutopilotPlan(
        catalog_path=Path("docs/catalog/app-arch-catalog.md"),
        catalog_exists=True,
        requires_aas=False,
        app_chains=chains,
        skipped=[],
        max_parallel=max_parallel,
    )


def test_detached_popen_kwargs_per_os() -> None:
    kw = _detached_popen_kwargs()
    if sys.platform == "win32":
        assert "creationflags" in kw
    else:
        assert kw.get("start_new_session") is True


def test_argv_factory_used_when_provided(qapp) -> None:
    captured: List[List[str]] = []

    def argv_factory(app_id: str, workflow_id: str) -> List[str]:
        return ["orchestrate", "--workflow", workflow_id, "--app-id", app_id, "--MARK"]

    def popen_factory(argv):
        captured.append(argv)
        return _FakeProc(finish_immediately=False)

    controller = AutopilotController(
        _plan(["APP-01"]),
        argv_factory=argv_factory,
        popen_factory=popen_factory,
    )
    controller.start()
    assert len(captured) == 1
    assert "--MARK" in captured[0]
    assert "APP-01" in captured[0]


def test_default_argv_contains_orchestrate_app_ids(qapp) -> None:
    captured: List[List[str]] = []

    def popen_factory(argv):
        captured.append(argv)
        return _FakeProc(finish_immediately=False)

    controller = AutopilotController(
        _plan(["APP-42"]),
        popen_factory=popen_factory,
    )
    controller.start()
    assert captured
    argv = captured[0]
    assert "orchestrate" in argv
    assert "--workflow" in argv
    assert "--app-ids" in argv
    assert "APP-42" in argv
    assert "--workbench" in argv


def test_controller_respects_max_parallel(qapp) -> None:
    spawned: List[List[str]] = []

    def popen_factory(argv):
        spawned.append(argv)
        return _FakeProc(finish_immediately=False)

    controller = AutopilotController(
        _plan(["APP-01", "APP-02", "APP-03", "APP-04", "APP-05"], max_parallel=2),
        popen_factory=popen_factory,
    )
    controller.start()
    assert len(spawned) == 2
    assert len(controller._running) == 2
    assert len(controller._pending) == 3


def test_chain_advances_within_same_app_lane(qapp) -> None:
    """1 APP のチェーン (aad-web → asdw-web) が直列に再起動される。"""
    spawned_argvs: List[List[str]] = []
    procs: List[_FakeProc] = []

    def popen_factory(argv):
        spawned_argvs.append(argv)
        finish = len(procs) == 0
        p = _FakeProc(exit_code=0, finish_immediately=finish)
        procs.append(p)
        return p

    controller = AutopilotController(
        _plan(["APP-01"], max_parallel=1),
        popen_factory=popen_factory,
    )
    controller.start()
    assert len(spawned_argvs) == 1
    assert "aad-web" in spawned_argvs[0]
    controller._poll()
    assert len(spawned_argvs) == 2
    assert "asdw-web" in spawned_argvs[1]


def test_one_app_failure_does_not_affect_others(qapp) -> None:
    """1 APP のチェーン途中失敗が他 APP のチェーン継続に影響しないこと。"""
    procs: List[_FakeProc] = []

    def popen_factory(argv):
        if len(procs) == 0:
            p = _FakeProc(exit_code=2, finish_immediately=True)
        else:
            p = _FakeProc(exit_code=0, finish_immediately=False)
        procs.append(p)
        return p

    controller = AutopilotController(
        _plan(["APP-01", "APP-02", "APP-03"], max_parallel=2),
        popen_factory=popen_factory,
    )
    controller.start()
    controller._poll()
    assert len(controller._running) == 2  # APP-02, APP-03
    assert controller._done == 1  # APP-01 (ABORTED)
    assert not procs[1].terminate_called


def test_cancel_all_terminates_running(qapp) -> None:
    procs: List[_FakeProc] = []

    def popen_factory(argv):
        p = _FakeProc(finish_immediately=False)
        procs.append(p)
        return p

    controller = AutopilotController(
        _plan(["APP-01", "APP-02", "APP-03"], max_parallel=2),
        popen_factory=popen_factory,
    )
    controller.start()
    assert len(controller._running) == 2
    controller.cancel_all()
    assert len(controller._pending) == 0
    assert all(p.terminate_called for p in procs[:2])


def test_empty_plan_emits_finished_without_spawn(qapp) -> None:
    spawned: List[List[str]] = []

    def popen_factory(argv):
        spawned.append(argv)
        return _FakeProc()

    plan = AutopilotPlan(
        catalog_path=Path("x.md"),
        catalog_exists=True,
        requires_aas=False,
        app_chains=[],
        skipped=[],
        max_parallel=4,
    )
    finished_seen = []
    c = AutopilotController(plan, popen_factory=popen_factory)
    c.finished.connect(lambda: finished_seen.append(True))
    c.start()
    assert spawned == []
    assert finished_seen == [True]
