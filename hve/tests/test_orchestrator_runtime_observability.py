"""FR-RTO-03 / FR-RTO-06: Orchestrator への観測記録の配線とライフサイクル。

RED 先行。`_attach_runtime_observability` は本テスト作成時点で未実装。
実 SDK セッションを起動しないよう、ヘルパー単体と静的配線検査だけで検証する。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from hve import orchestrator as orch
from hve import runtime_observability as rto
from hve.config import SDKConfig
from hve.console import Console


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("HVE_GUI_SESSION_ID", raising=False)
    monkeypatch.delenv("HVE_STATS_STREAM", raising=False)
    monkeypatch.delenv("HVE_WORK_ROOT", raising=False)


class TestAttachRuntimeObservability:
    def test_returns_none_without_work_root(self) -> None:
        console = Console(verbose=False)
        recorder = orch._attach_runtime_observability(console, SDKConfig(), "aad-web")
        assert recorder is None

    def test_returns_none_for_dry_run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path))
        console = Console(verbose=False)
        recorder = orch._attach_runtime_observability(console, SDKConfig(dry_run=True), "aad-web")
        assert recorder is None
        assert not (tmp_path / rto.OBSERVABILITY_DIRNAME).exists()

    def test_attaches_recorder_and_identity(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path))
        console = Console(verbose=False)
        config = SDKConfig()
        config.run_id = "run-42"
        console.set_run_id(config.run_id)

        recorder = orch._attach_runtime_observability(
            console, config, "asdw-web", app_ids=["APP-009"]
        )
        assert recorder is not None
        console.stats_event("step_status", step_id="1", status="running")
        recorder.close()

        events = rto.read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["workflow_id"] == "asdw-web"
        assert events[0]["instance_id"] == "asdw-web#APP-009"
        assert events[0]["run_id"] == "run-42"

    def test_instance_id_without_app_scope(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path))
        console = Console(verbose=False)
        recorder = orch._attach_runtime_observability(console, SDKConfig(), "aad-web")
        console.stats_event("step_status", step_id="1", status="running")
        recorder.close()

        assert rto.read_events(tmp_path)[0]["instance_id"] == "aad-web"

    def test_multiple_app_ids_do_not_pin_a_single_instance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HVE_WORK_ROOT", str(tmp_path))
        console = Console(verbose=False)
        recorder = orch._attach_runtime_observability(
            console, SDKConfig(), "aad-web", app_ids=["APP-001", "APP-002"]
        )
        console.stats_event("step_status", step_id="1", status="running")
        recorder.close()

        assert rto.read_events(tmp_path)[0]["instance_id"] == "aad-web"


class TestLifecycleWiring:
    """FR-RTO-06: run_workflow が記録器を生成し、終了時に閉じる。"""

    def test_run_workflow_attaches_and_closes_recorder(self) -> None:
        source = inspect.getsource(orch._run_workflow_body)
        assert "_attach_runtime_observability(" in source
        assert "_rt_recorder.close()" in source
