"""FR-STATE-04/05・NFR-REL-03・FR-CLI-90 の orchestrator RED 契約。

実ネットワーク、GitHub、Azure、Copilot SDK は使用しない。新しい durable API は
各 test 内で dynamic import し、未実装期間も collection error ではなく、どの契約が
未実装かを test case 単位で報告する。
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import importlib
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Awaitable, Callable, Optional
from unittest.mock import Mock

import pytest

from hve import (
    approval,
    dag_executor,
    error_severity,
    orchestrator,
    run_progress,
    workflow_registry,
)
from hve.config import SDKConfig
from hve.orchestrator_context import OrchestratorContext
from hve.workflow_registry import StepDef, WorkflowDef


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ORCHESTRATOR_PATH = _REPO_ROOT / "hve" / "orchestrator.py"


def _dynamic_import(module_name: str) -> ModuleType:
    """Import a future durable module without aborting test collection."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            pytest.fail(
                f"{module_name} が未実装です: {type(exc).__name__}: {exc}",
                pytrace=False,
            )
        raise


def _state_api() -> ModuleType:
    module = _dynamic_import("hve.run_state_store")
    for name in ("DurableStateError", "LeaseToken", "RunStateStore", "HeartbeatWorker"):
        assert hasattr(module, name), f"hve.run_state_store.{name} が未実装です"
    return module


def _resume_api() -> ModuleType:
    module = _dynamic_import("hve.resume_service")
    assert hasattr(module, "ResumeService"), "hve.resume_service.ResumeService が未実装です"
    return module


@dataclass
class _Trace:
    events: list[str] = field(default_factory=list)
    service_registrations: list[dict[str, Any]] = field(default_factory=list)
    store_registrations: list[dict[str, Any]] = field(default_factory=list)
    workflow_transitions: list[dict[str, Any]] = field(default_factory=list)
    step_transitions: list[dict[str, Any]] = field(default_factory=list)
    lease_acquires: list[dict[str, Any]] = field(default_factory=list)
    lease_releases: list[Any] = field(default_factory=list)
    heartbeat_starts: int = 0
    heartbeat_stops: int = 0
    heartbeat_initial_tokens: list[Any] = field(default_factory=list)
    heartbeat_stop_tokens: list[Any] = field(default_factory=list)
    heartbeat_error: Optional[BaseException] = None
    heartbeat_callback_errors: list[BaseException] = field(default_factory=list)
    executor_started: threading.Event = field(default_factory=threading.Event)
    executor_cancelled: bool = False
    executor_active_sets: list[set[str]] = field(default_factory=list)
    executor_kwargs: list[dict[str, Any]] = field(default_factory=list)
    runner_calls: list[dict[str, Any]] = field(default_factory=list)
    jsonl_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)
    external_calls: list[str] = field(default_factory=list)


class _Record(dict[str, Any]):
    """SQLite row と dataclass の双方に近い test record。"""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - diagnostic path
            raise AttributeError(name) from exc


class _FakeStore:
    def __init__(self, api: ModuleType, trace: _Trace, path: Path) -> None:
        self.api = api
        self.trace = trace
        self.path = path
        self.execution_id = "exec-test"
        self.instance_id = "instance-aas"
        self.workflow_id = "aas"
        self.state_version = 0
        self.execution = _Record(
            execution_id=self.execution_id,
            repo_key=api.compute_repo_key(path.parent),
            surface="orchestrate",
            launch_plan_hash="launch-plan-hash",
            plan_json="[]",
            checkpoint_head=None,
        )
        self.instance = _Record(
            execution_id=self.execution_id,
            instance_id=self.instance_id,
            workflow_id=self.workflow_id,
            ordinal=0,
            mode="standard",
            status="pending",
            state_version=self.state_version,
            run_id=None,
            checkpoint_head=None,
            argv_json="[]",
            missing_replay_keys_json="[]",
            lease_owner=None,
            lease_generation=0,
        )
        self.steps: list[_Record] = []

    def __enter__(self) -> "_FakeStore":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def close(self) -> None:
        self.trace.events.append("store.close")
        return None

    def quick_check(self) -> bool:
        return True

    def _token(self, owner: str = "test-owner") -> Any:
        return self.api.LeaseToken(
            execution_id=self.execution_id,
            instance_id=self.instance_id,
            owner=owner,
            generation=1,
            state_version=self.state_version,
        )

    def _bump(self, token: Any) -> Any:
        self.state_version += 1
        self.instance["state_version"] = self.state_version
        try:
            return dataclasses.replace(token, state_version=self.state_version)
        except (TypeError, ValueError):  # pragma: no cover - defensive fake compatibility
            return self._token(getattr(token, "owner", "test-owner"))

    def register_execution(
        self,
        execution_id: str,
        repo_key: str,
        surface: str,
        launch_plan_hash: str,
        plan_json: str,
        instances: Any,
        **kwargs: Any,
    ) -> None:
        self.trace.store_registrations.append(
            {
                "execution_id": execution_id,
                "repo_key": repo_key,
                "surface": surface,
                "launch_plan_hash": launch_plan_hash,
                "plan_json": plan_json,
                "instances": instances,
                **kwargs,
            }
        )
        self.trace.events.append("store.register")

    def get_execution(self, execution_id: str) -> Optional[_Record]:
        return self.execution if execution_id == self.execution_id else None

    def get_instance(self, execution_id: str, instance_id: str) -> Optional[_Record]:
        if execution_id == self.execution_id and instance_id == self.instance_id:
            return self.instance
        return None

    def list_instances(self, execution_id: str) -> list[_Record]:
        return [self.instance] if execution_id == self.execution_id else []

    def list_steps(self, execution_id: str, instance_id: str) -> list[_Record]:
        if execution_id == self.execution_id and instance_id == self.instance_id:
            return list(self.steps)
        return []

    def list_candidates(self, _repo_key: str) -> list[_Record]:
        return [self.execution]

    def acquire_lease(
        self,
        execution_id: str,
        instance_id: str,
        expected_state_version: int,
        owner: str,
        *,
        now: Any = None,
        allow_takeover: bool = False,
    ) -> Any:
        self.trace.lease_acquires.append(
            {
                "execution_id": execution_id,
                "instance_id": instance_id,
                "expected_state_version": expected_state_version,
                "owner": owner,
                "now": now,
                "allow_takeover": allow_takeover,
            }
        )
        self.execution_id = execution_id
        self.instance_id = instance_id
        self.state_version = expected_state_version
        self.instance.update(
            execution_id=execution_id,
            instance_id=instance_id,
            state_version=expected_state_version,
        )
        return self._token(owner)

    def transition_workflow(
        self,
        token: Any,
        status: str,
        *,
        run_id: Optional[str] = None,
        checkpoint_head: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        record = {
            "status": status,
            "run_id": run_id,
            "checkpoint_head": checkpoint_head,
            **kwargs,
        }
        self.trace.workflow_transitions.append(record)
        self.trace.events.append(f"workflow:{status}")
        self.instance["status"] = status
        if run_id is not None:
            self.instance["run_id"] = run_id
        return self._bump(token)

    def transition_step(
        self,
        token: Any,
        step_id: str,
        status: str,
        *,
        record_kind: str = "step",
        phase: Optional[str] = None,
        phase_state: Optional[str] = None,
        session_id: Optional[str] = None,
        last_error_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        record = {
            "step_id": step_id,
            "status": status,
            "record_kind": record_kind,
            "phase": phase,
            "phase_state": phase_state,
            "session_id": session_id,
            "last_error_type": last_error_type,
            **kwargs,
        }
        self.trace.step_transitions.append(record)
        self.trace.events.append(f"step:{step_id}:{status}")
        return self._bump(token)

    def heartbeat(self, token: Any, *, now: Any = None) -> Any:
        self.trace.events.append("heartbeat")
        return token

    def release_lease(self, token: Any) -> None:
        self.trace.lease_releases.append(token)
        self.trace.events.append("lease.release")


class _FakeResumeService:
    def __init__(
        self,
        store: _FakeStore,
        repo_root: Path,
        trace: _Trace,
        resume_api: ModuleType,
    ) -> None:
        self.store = store
        self.repo_root = repo_root
        self.trace = trace
        self.resume_api = resume_api

    def new_execution_id(self) -> str:
        return self.store.execution_id

    def sanitize_argv(self, argv: Any) -> tuple[tuple[Any, ...], tuple[str, ...]]:
        return tuple(argv or ()), ()

    def register_execution(
        self,
        surface: str,
        descriptors: Any,
        *,
        execution_id: Optional[str] = None,
        checkpoint_head: Optional[str] = None,
    ) -> str:
        descriptor_list = list(descriptors)
        execution_id = execution_id or self.store.execution_id
        if descriptor_list:
            descriptor = descriptor_list[0]
            self.store.instance_id = str(getattr(descriptor, "instance_id", self.store.instance_id))
            self.store.workflow_id = str(getattr(descriptor, "workflow_id", self.store.workflow_id))
            self.store.instance.update(
                execution_id=execution_id,
                instance_id=self.store.instance_id,
                workflow_id=self.store.workflow_id,
                status="pending",
                state_version=0,
            )
        self.store.execution_id = execution_id
        self.store.execution["execution_id"] = execution_id
        record = {
            "surface": surface,
            "descriptors": descriptor_list,
            "execution_id": execution_id,
            "checkpoint_head": checkpoint_head,
        }
        self.trace.service_registrations.append(record)
        self.trace.events.append("resume.register")
        return execution_id

    def list_candidates(self) -> list[_Record]:
        return [self.store.execution]

    def build_plan(
        self,
        execution_id: str,
        *,
        action: Optional[str] = None,
        replay_values: Any = None,
        current_head: Optional[str] = None,
    ) -> Any:
        del replay_values, current_head
        return SimpleNamespace(
            execution_id=execution_id,
            instance_id=self.store.instance_id,
            workflow_id=self.store.workflow_id,
            action=action or "restart-step",
            expected_state_version=self.store.state_version,
            risk_reasons=(),
            missing_replay_keys=(),
            argv=(),
            resume_plan_hash="resume-plan-hash",
        )

    def acquire(self, plan: Any, owner: str) -> Any:
        return self.store.acquire_lease(
            plan.execution_id,
            plan.instance_id,
            plan.expected_state_version,
            owner,
            allow_takeover=bool(getattr(plan, "action", None)),
        )


class _FakeHeartbeatWorker:
    def __init__(
        self,
        path: Path,
        token: Any,
        trace: _Trace,
        *,
        interval_seconds: float = 5.0,
        on_failure: Optional[Callable[[BaseException], None]] = None,
    ) -> None:
        self.path = path
        self.token = token
        self.trace = trace
        self.interval_seconds = interval_seconds
        self.on_failure = on_failure
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.trace.heartbeat_starts += 1
        self.trace.heartbeat_initial_tokens.append(self.token)
        self.trace.events.append("heartbeat.start")
        if self.trace.heartbeat_error is None:
            return

        def _notify() -> None:
            if not self.trace.executor_started.wait(timeout=0.75):
                return
            if self.on_failure is None:
                return
            try:
                self.on_failure(self.trace.heartbeat_error)  # type: ignore[arg-type]
            except BaseException as exc:  # pragma: no cover - retained for diagnostics
                self.trace.heartbeat_callback_errors.append(exc)

        self._thread = threading.Thread(
            target=_notify,
            name="fake-heartbeat-failure",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self.trace.heartbeat_stops += 1
        self.trace.heartbeat_stop_tokens.append(self.token)
        self.trace.events.append("heartbeat.stop")
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def raise_if_failed(self) -> None:
        if self.trace.heartbeat_error is not None:
            raise self.trace.heartbeat_error


class _FakeRunner:
    def __init__(self, trace: _Trace, **_kwargs: Any) -> None:
        self.trace = trace

    async def run_step(self, **kwargs: Any) -> bool:
        self.trace.runner_calls.append(dict(kwargs))
        self.trace.external_calls.append("Copilot SDK StepRunner.run_step")
        raise AssertionError("fake DAG から SDK runner を呼んではならない")

    def set_fork_index(self, *_args: Any) -> None:
        return None


ExecutorBehavior = Callable[["_FakeDAGExecutor"], Awaitable[dict[str, Any]]]


class _FakeDAGExecutor:
    def __init__(
        self,
        trace: _Trace,
        behavior: ExecutorBehavior,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        del args
        self.trace = trace
        self.behavior = behavior
        self.workflow = kwargs.get("workflow")
        self.active_step_ids = set(kwargs.get("active_step_ids") or ())
        self.completed: set[str] = set()
        self.failed: set[str] = set()
        self.skipped: set[str] = set()
        self.blocked: set[str] = set()
        self._results: dict[str, Any] = {}
        self._expanded_steps = list(getattr(self.workflow, "steps", ()) or ())
        self.on_step_start = kwargs.get("on_step_start")
        self.on_step_complete = kwargs.get("on_step_complete")
        self.on_wave_start = kwargs.get("on_wave_start")
        trace.executor_active_sets.append(set(self.active_step_ids))
        trace.executor_kwargs.append(dict(kwargs))
        trace.events.append("executor.init")

    def compute_waves(self) -> list[list[Any]]:
        return []

    def total_display_steps(self) -> int:
        return len(self.active_step_ids)

    async def execute(self) -> dict[str, Any]:
        self.trace.events.append("executor.execute")
        return await self.behavior(self)


def _patch_imported_aliases(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    original: Any,
    replacement: Any,
) -> None:
    for name, value in list(vars(module).items()):
        if value is original:
            monkeypatch.setattr(module, name, replacement)


def _install_durable_fakes(
    monkeypatch: pytest.MonkeyPatch,
    trace: _Trace,
    state_path: Path,
) -> _FakeStore:
    state_api = _state_api()
    resume_api = _resume_api()
    store = _FakeStore(state_api, trace, state_path)

    original_store = state_api.RunStateStore
    original_worker = state_api.HeartbeatWorker
    original_default_path = state_api.default_state_path
    original_service = resume_api.ResumeService

    def _store_factory(*_args: Any, **_kwargs: Any) -> _FakeStore:
        return store

    def _worker_factory(
        path: Path,
        token: Any,
        *,
        interval_seconds: float = 5.0,
        on_failure: Optional[Callable[[BaseException], None]] = None,
        **_kwargs: Any,
    ) -> _FakeHeartbeatWorker:
        return _FakeHeartbeatWorker(
            path,
            token,
            trace,
            interval_seconds=interval_seconds,
            on_failure=on_failure,
        )

    def _service_factory(store_arg: _FakeStore, repo_root: Path) -> _FakeResumeService:
        return _FakeResumeService(store_arg, repo_root, trace, resume_api)

    _patch_imported_aliases(monkeypatch, orchestrator, original_store, _store_factory)
    _patch_imported_aliases(monkeypatch, orchestrator, original_worker, _worker_factory)
    _patch_imported_aliases(monkeypatch, orchestrator, original_default_path, lambda: state_path)
    _patch_imported_aliases(monkeypatch, orchestrator, original_service, _service_factory)
    monkeypatch.setattr(state_api, "RunStateStore", _store_factory)
    monkeypatch.setattr(state_api, "HeartbeatWorker", _worker_factory)
    monkeypatch.setattr(state_api, "default_state_path", lambda: state_path)
    monkeypatch.setattr(resume_api, "ResumeService", _service_factory)
    return store


def _install_jsonl_spy(monkeypatch: pytest.MonkeyPatch, trace: _Trace) -> None:
    def _record(*args: Any, **kwargs: Any) -> None:
        trace.jsonl_calls.append((args, kwargs))

    monkeypatch.setattr(run_progress, "record_step", _record)


def _install_external_tripwires(
    monkeypatch: pytest.MonkeyPatch,
    trace: _Trace,
) -> None:
    original_socket_connect = socket.socket.connect

    def _blocked(label: str) -> Callable[..., Any]:
        def _call(*_args: Any, **_kwargs: Any) -> Any:
            trace.external_calls.append(label)
            raise AssertionError(f"実 external call を禁止しました: {label}")

        return _call

    def _guarded_socket_connect(sock: socket.socket, address: Any) -> Any:
        # Python 3.14 の Windows ProactorEventLoop は初期化時の wakeup 用
        # socketpair を loopback TCP で構築する。これは外部通信ではない。
        host = address[0] if isinstance(address, tuple) and address else None
        if host in {"127.0.0.1", "::1"}:
            return original_socket_connect(sock, address)
        return _blocked("network.socket.connect")(sock, address)

    for name in (
        "_create_copilot_client_from_config",
        "create_issue",
        "get_issue",
        "link_sub_issue",
        "post_comment",
        "create_pull_request",
        "get_pull_request",
        "list_issue_comments",
        "list_check_runs_for_ref",
        "add_labels",
        "api_call",
    ):
        if hasattr(orchestrator, name):
            monkeypatch.setattr(orchestrator, name, _blocked(name))
    monkeypatch.setattr(orchestrator.subprocess, "run", _blocked("subprocess"))
    monkeypatch.setattr(socket, "create_connection", _blocked("network.create_connection"))
    monkeypatch.setattr(socket.socket, "connect", _guarded_socket_connect)


def _install_run_harness(
    monkeypatch: pytest.MonkeyPatch,
    trace: _Trace,
    behavior: ExecutorBehavior,
    tmp_path: Path,
    *,
    workflow: Optional[WorkflowDef] = None,
) -> None:
    monkeypatch.chdir(tmp_path)
    _install_external_tripwires(monkeypatch, trace)
    monkeypatch.setattr(orchestrator, "_start_index_watchers_when_idle", lambda _config: None)
    monkeypatch.setattr(orchestrator, "_attach_runtime_observability", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "_attach_mcp_io_logging", lambda *a, **k: None)
    monkeypatch.setattr(
        orchestrator,
        "validate_startup_configuration",
        lambda **_kwargs: SimpleNamespace(is_ok=lambda: True),
    )
    monkeypatch.setattr(
        orchestrator,
        "_check_dirty_hve_sources",
        lambda **_kwargs: {"should_abort": False, "blocked_step_ids": [], "error": None},
    )
    monkeypatch.setattr(
        orchestrator,
        "_check_workflow_input_artifacts",
        lambda **_kwargs: {"should_abort": False, "blocked_step_ids": [], "error": None},
    )
    monkeypatch.setattr(
        orchestrator,
        "_check_required_skills_for_active_steps",
        lambda **_kwargs: {"should_abort": False, "blocked_step_ids": [], "error": None},
    )
    monkeypatch.setattr(orchestrator, "_detect_existing_artifacts", lambda *a, **k: {})
    monkeypatch.setattr(orchestrator, "_build_step_prompt", lambda **_kwargs: "test prompt")
    monkeypatch.setattr(orchestrator, "_create_issues_if_needed", lambda **_kwargs: (None, {}))
    monkeypatch.setattr(orchestrator, "_emit_github_target_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "_emit_context_injection_metrics", lambda **_kwargs: None)
    monkeypatch.setattr(orchestrator, "_emit_runtime_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        orchestrator,
        "_resolve_durable_checkpoint_head",
        lambda _repo_root: "head-at-registration",
        raising=False,
    )
    monkeypatch.setattr(orchestrator, "apply_cloud_session_auto_routing", lambda *a, **k: {})
    monkeypatch.setattr(workflow_registry, "get_meta_dependencies", lambda _workflow_id: [])
    monkeypatch.setattr(
        orchestrator,
        "_expand_workflow_for_dag",
        lambda wf, active, *_args, **_kwargs: (
            wf,
            set(active),
            SimpleNamespace(fanout_map={}, deferred_fanout_ids=[]),
        ),
    )
    monkeypatch.setattr(orchestrator.rework, "resolve_rework_targets", lambda *a, **k: [])
    monkeypatch.setattr(orchestrator.rework, "format_rework_suggestion", lambda *a, **k: None)
    monkeypatch.setattr(
        orchestrator,
        "StepRunner",
        lambda *args, **kwargs: _FakeRunner(trace, **kwargs),
    )
    monkeypatch.setattr(
        orchestrator,
        "DAGExecutor",
        lambda *args, **kwargs: _FakeDAGExecutor(trace, behavior, *args, **kwargs),
    )
    if workflow is not None:
        monkeypatch.setattr(orchestrator, "get_workflow", lambda _workflow_id: workflow)
        monkeypatch.setattr(
            orchestrator,
            "resolve_selected_steps",
            lambda _workflow, _selected: {step.id for step in workflow.steps},
        )


def _config(**overrides: Any) -> SDKConfig:
    values: dict[str, Any] = {
        "dry_run": False,
        "quiet": True,
        "no_workbench": True,
        "mdq_watch": False,
        "cq_watch": False,
        "auto_self_improve": False,
        "self_improve_skip": True,
        "create_issues": False,
        "create_pr": False,
        "repo": "",
        "run_id": "run-test",
    }
    values.update(overrides)
    return SDKConfig(**values)


def _params() -> dict[str, Any]:
    return {"branch": "main", "selected_steps": ["1"]}


def _context(**overrides: Any) -> OrchestratorContext:
    values: dict[str, Any] = {
        "execution_id": "",
        "instance_id": "",
        "expected_state_version": None,
        "recovery_action": None,
        "lease_owner": None,
        "lease_generation": None,
    }
    values.update(overrides)
    try:
        return OrchestratorContext(**values)
    except TypeError as exc:
        pytest.fail(f"OrchestratorContext durable identity fields が未実装です: {exc}")


def _mark_success(executor: _FakeDAGExecutor, step_ids: set[str]) -> dict[str, Any]:
    for step_id in sorted(step_ids):
        result = dag_executor.StepResult(step_id, success=True, elapsed=0.0)
        executor.completed.add(step_id)
        executor._results[step_id] = result
    return dict(executor._results)


async def _success_with_step_callbacks(executor: _FakeDAGExecutor) -> dict[str, Any]:
    assert executor.active_step_ids, "標準新規 run の active Step が空です"
    step_id = sorted(executor.active_step_ids)[0]
    assert executor.on_step_start is not None, "durable step-start callback が未配線です"
    assert executor.on_step_complete is not None, "durable step-complete callback が未配線です"
    executor.on_step_start(step_id)
    result = dag_executor.StepResult(step_id, success=True, elapsed=0.0)
    executor.completed.add(step_id)
    executor._results[step_id] = result
    executor.on_step_complete(result)
    return dict(executor._results)


async def _success_without_callbacks(executor: _FakeDAGExecutor) -> dict[str, Any]:
    return _mark_success(executor, executor.active_step_ids)


def _assert_no_external_calls(trace: _Trace) -> None:
    assert trace.runner_calls == []
    assert trace.external_calls == []


def _approval_records(trace: _Trace, wave_index: int) -> list[dict[str, Any]]:
    return [
        record
        for record in trace.step_transitions
        if record["step_id"] == f"approval:{wave_index}"
    ]


def _one_step_executor(
    *,
    on_step_start: Optional[Callable[[str], None]] = None,
    on_step_complete: Optional[Callable[[Any], None]] = None,
    on_wave_start: Optional[Callable[[list[Any], int], None]] = None,
    run_step_calls: Optional[list[str]] = None,
) -> dag_executor.DAGExecutor:
    step = StepDef(id="1", title="one", custom_agent=None)
    workflow = WorkflowDef(
        id="durable-test",
        name="durable-test",
        label_prefix="durable",
        state_labels={},
        params=[],
        steps=[step],
    )
    calls = run_step_calls if run_step_calls is not None else []

    async def _run_step(step_id: str, **_kwargs: Any) -> bool:
        calls.append(step_id)
        return True

    return dag_executor.DAGExecutor(
        workflow=workflow,
        run_step_fn=_run_step,
        active_step_ids={"1"},
        enable_fanout=False,
        on_step_start=on_step_start,
        on_step_complete=on_step_complete,
        on_wave_start=on_wave_start,
    )


class TestDurableWriteFailure:
    def test_durable_failure_cancels_same_wave_sibling_before_return(self) -> None:
        state_api = _state_api()
        error = state_api.DurableStateError("same-wave durable failure")
        steps = [
            StepDef(id="1", title="fails", custom_agent=None),
            StepDef(id="2", title="waits", custom_agent=None),
        ]
        workflow = WorkflowDef(
            id="durable-test",
            name="durable-test",
            label_prefix="durable",
            state_labels={},
            params=[],
            steps=steps,
        )

        async def _scenario() -> bool:
            sibling_started = asyncio.Event()
            sibling_cancelled = asyncio.Event()

            async def _run_step(step_id: str, **_kwargs: Any) -> bool:
                if step_id == "1":
                    await sibling_started.wait()
                    raise error
                sibling_started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    sibling_cancelled.set()
                    raise
                return True

            executor = dag_executor.DAGExecutor(
                workflow=workflow,
                run_step_fn=_run_step,
                active_step_ids={"1", "2"},
                enable_fanout=False,
            )
            try:
                await executor.execute()
            except state_api.DurableStateError:
                return sibling_cancelled.is_set()
            raise AssertionError("durable failure was not rethrown")

        assert asyncio.run(_scenario()) is True

    def test_runner_durable_error_is_not_converted_or_retried(self) -> None:
        state_api = _state_api()
        error = state_api.DurableStateError("runner checkpoint failed")
        run_step_calls: list[str] = []
        step = StepDef(id="1", title="one", custom_agent=None)
        workflow = WorkflowDef(
            id="durable-test",
            name="durable-test",
            label_prefix="durable",
            state_labels={},
            params=[],
            steps=[step],
        )

        async def _fail(step_id: str, **_kwargs: Any) -> bool:
            run_step_calls.append(step_id)
            raise error

        executor = dag_executor.DAGExecutor(
            workflow=workflow,
            run_step_fn=_fail,
            active_step_ids={"1"},
            enable_fanout=False,
            fork_on_retry=True,
        )

        with pytest.raises(
            state_api.DurableStateError,
            match="runner checkpoint failed",
        ):
            asyncio.run(executor.execute())
        assert run_step_calls == ["1"]

    def test_step_start_failure_is_rethrown_before_runner(self) -> None:
        state_api = _state_api()
        error = state_api.DurableStateError("start transition failed")
        run_step_calls: list[str] = []

        def _fail(_step_id: str) -> None:
            raise error

        executor = _one_step_executor(
            on_step_start=_fail,
            run_step_calls=run_step_calls,
        )
        with pytest.raises(state_api.DurableStateError, match="start transition failed"):
            asyncio.run(executor.execute())
        assert run_step_calls == []

    def test_step_complete_failure_is_rethrown(self) -> None:
        state_api = _state_api()
        error = state_api.DurableStateError("complete transition failed")
        run_step_calls: list[str] = []

        def _fail(_result: Any) -> None:
            raise error

        executor = _one_step_executor(
            on_step_complete=_fail,
            run_step_calls=run_step_calls,
        )
        with pytest.raises(state_api.DurableStateError, match="complete transition failed"):
            asyncio.run(executor.execute())
        assert run_step_calls == ["1"]

    def test_wave_start_failure_is_rethrown_before_runner(self) -> None:
        state_api = _state_api()
        error = state_api.DurableStateError("wave transition failed")
        run_step_calls: list[str] = []

        def _fail(_steps: list[Any], _wave_index: int) -> None:
            raise error

        executor = _one_step_executor(
            on_wave_start=_fail,
            run_step_calls=run_step_calls,
        )
        with pytest.raises(state_api.DurableStateError, match="wave transition failed"):
            asyncio.run(executor.execute())
        assert run_step_calls == []

    def test_run_workflow_does_not_enter_generic_fatal_downgrade(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        _resume_api()
        trace = _Trace()
        error = state_api.DurableStateError("sqlite commit failed")

        async def _raise(_executor: _FakeDAGExecutor) -> dict[str, Any]:
            raise error

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _raise, tmp_path)
        classifier = Mock(return_value="fatal")
        monkeypatch.setattr(error_severity, "classify_error", classifier)

        with pytest.raises(state_api.DurableStateError, match="sqlite commit failed"):
            asyncio.run(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                    orchestrator_ctx=_context(continue_on_error=True),
                )
            )

        classifier.assert_not_called()
        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1
        assert len(trace.lease_releases) == 1
        assert trace.events.index("heartbeat.stop") < trace.events.index("lease.release")
        assert trace.events.index("lease.release") < trace.events.index("store.close")
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)

    @pytest.mark.parametrize(
        "error_type",
        [asyncio.CancelledError, KeyboardInterrupt, SystemExit],
        ids=["cancelled", "keyboard-interrupt", "system-exit"],
    )
    def test_process_control_is_suspended_and_rethrown(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        error_type: type[BaseException],
    ) -> None:
        trace = _Trace()

        async def _raise(_executor: _FakeDAGExecutor) -> dict[str, Any]:
            raise error_type("operator stop")

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _raise, tmp_path)

        with pytest.raises(error_type, match="operator stop"):
            asyncio.run(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                    orchestrator_ctx=_context(continue_on_error=True),
                )
            )

        assert [item["status"] for item in trace.workflow_transitions] == [
            "running",
            "suspended",
        ]
        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1
        assert len(trace.lease_releases) == 1
        assert trace.events.index("heartbeat.stop") < trace.events.index("lease.release")
        assert trace.events.index("lease.release") < trace.events.index("store.close")
        assert trace.jsonl_calls == []


class TestDurableContext:
    def test_identity_fields_are_immutable_and_survive_depth_changes(self) -> None:
        context = _context(
            execution_id="exec-public",
            instance_id="instance-2",
            expected_state_version=7,
            recovery_action="restart-step",
            lease_owner="resume-owner",
            lease_generation=3,
            split_fork_depth=1,
        )
        assert context.execution_id == "exec-public"
        assert context.instance_id == "instance-2"
        assert context.expected_state_version == 7
        assert context.recovery_action == "restart-step"
        assert context.lease_owner == "resume-owner"
        assert context.lease_generation == 3
        with pytest.raises(dataclasses.FrozenInstanceError):
            context.execution_id = "mutated"  # type: ignore[misc]

        child = context.with_increased_depth()
        assert child.split_fork_depth == 2
        assert child.execution_id == context.execution_id
        assert child.instance_id == context.instance_id
        assert child.expected_state_version == context.expected_state_version
        assert child.recovery_action == context.recovery_action
        assert child.lease_owner == context.lease_owner
        assert child.lease_generation == context.lease_generation


class TestDurableTransitions:
    def test_standard_run_registers_before_execution_and_commits_canonical_states(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()
        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _success_with_step_callbacks, tmp_path)

        result = asyncio.run(
            orchestrator.run_workflow("aas", params=_params(), config=_config())
        )

        assert len(trace.service_registrations) == 1
        assert trace.events.index("resume.register") < trace.events.index("executor.execute")
        assert [item["status"] for item in trace.workflow_transitions][0] == "running"
        assert [item["status"] for item in trace.workflow_transitions][-1] == "succeeded"
        step_states = [
            item["status"]
            for item in trace.step_transitions
            if item["step_id"] == "1" and item["record_kind"] == "step"
        ]
        assert step_states == ["running", "succeeded"]
        assert result["completed"] == ["1"]
        assert trace.service_registrations[0]["checkpoint_head"] == (
            "head-at-registration"
        )
        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1
        assert trace.heartbeat_initial_tokens[0].state_version < (
            trace.heartbeat_stop_tokens[0].state_version
        )
        heartbeat_start_index = trace.events.index("heartbeat.start")
        assert heartbeat_start_index < trace.events.index("executor.init")
        assert trace.events.index("executor.init") < trace.events.index(
            "executor.execute"
        )
        assert len(trace.lease_releases) == 1
        assert trace.heartbeat_stop_tokens[0].state_version == (
            trace.lease_releases[0].state_version
        )
        assert trace.events.index("heartbeat.stop") < trace.events.index("lease.release")
        assert trace.events.index("lease.release") < trace.events.index("store.close")
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)

    def test_existing_identity_acquires_locally_without_reregistration(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()
        store = _install_durable_fakes(
            monkeypatch,
            trace,
            tmp_path / "state.sqlite3",
        )
        store.execution_id = "exec-existing"
        store.instance_id = "instance-existing"
        store.state_version = 7
        store.execution["execution_id"] = store.execution_id
        store.instance.update(
            execution_id=store.execution_id,
            instance_id=store.instance_id,
            state_version=store.state_version,
        )
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(
            monkeypatch,
            trace,
            _success_with_step_callbacks,
            tmp_path,
        )

        asyncio.run(
            orchestrator.run_workflow(
                "aas",
                params=_params(),
                config=_config(),
                orchestrator_ctx=_context(
                    execution_id=store.execution_id,
                    instance_id=store.instance_id,
                    expected_state_version=7,
                    recovery_action="restart-step",
                ),
            )
        )

        assert trace.service_registrations == []
        assert len(trace.lease_acquires) == 1
        assert trace.lease_acquires[0]["allow_takeover"] is True
        assert len(trace.lease_releases) == 1
        assert trace.lease_releases[0].state_version == store.state_version
        _assert_no_external_calls(trace)

    def test_recovery_requires_the_approved_expected_state_version(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        trace = _Trace()
        store = _install_durable_fakes(
            monkeypatch,
            trace,
            tmp_path / "state.sqlite3",
        )
        store.instance["status"] = "suspended"
        _install_run_harness(
            monkeypatch,
            trace,
            _success_without_callbacks,
            tmp_path,
        )

        with pytest.raises(
            state_api.DurableStateError,
            match="expected state version",
        ):
            asyncio.run(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                    orchestrator_ctx=_context(
                        execution_id=store.execution_id,
                        instance_id=store.instance_id,
                        expected_state_version=None,
                        recovery_action="restart-step",
                    ),
                )
            )

        assert trace.lease_acquires == []
        assert "executor.execute" not in trace.events

    def test_identity_only_context_rejects_a_non_pending_instance(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        trace = _Trace()
        store = _install_durable_fakes(
            monkeypatch,
            trace,
            tmp_path / "state.sqlite3",
        )
        store.instance["status"] = "failed"
        _install_run_harness(
            monkeypatch,
            trace,
            _success_without_callbacks,
            tmp_path,
        )

        with pytest.raises(
            state_api.DurableStateError,
            match="pending instance",
        ):
            asyncio.run(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                    orchestrator_ctx=_context(
                        execution_id=store.execution_id,
                        instance_id=store.instance_id,
                    ),
                )
            )

        assert trace.lease_acquires == []
        assert "executor.execute" not in trace.events

    def test_expected_version_without_action_rejects_a_failed_instance(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        trace = _Trace()
        store = _install_durable_fakes(
            monkeypatch,
            trace,
            tmp_path / "state.sqlite3",
        )
        store.instance.update(
            status="failed",
            lease_owner="parent-owner",
            lease_generation=4,
        )
        _install_run_harness(
            monkeypatch,
            trace,
            _success_without_callbacks,
            tmp_path,
        )

        with pytest.raises(
            state_api.DurableStateError,
            match="pending instance",
        ):
            asyncio.run(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                    orchestrator_ctx=_context(
                        execution_id=store.execution_id,
                        instance_id=store.instance_id,
                        expected_state_version=store.state_version,
                        lease_owner="parent-owner",
                        lease_generation=4,
                    ),
                )
            )

        assert trace.lease_acquires == []
        assert "executor.execute" not in trace.events

    def test_parent_owned_token_is_adopted_but_not_released(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()
        store = _install_durable_fakes(
            monkeypatch,
            trace,
            tmp_path / "state.sqlite3",
        )
        store.execution_id = "exec-parent"
        store.instance_id = "instance-parent"
        store.state_version = 9
        store.execution["execution_id"] = store.execution_id
        store.instance.update(
            execution_id=store.execution_id,
            instance_id=store.instance_id,
            state_version=store.state_version,
            lease_owner="parent-owner",
            lease_generation=4,
        )
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(
            monkeypatch,
            trace,
            _success_with_step_callbacks,
            tmp_path,
        )

        asyncio.run(
            orchestrator.run_workflow(
                "aas",
                params=_params(),
                config=_config(),
                orchestrator_ctx=_context(
                    execution_id=store.execution_id,
                    instance_id=store.instance_id,
                    expected_state_version=9,
                    recovery_action="restart-step",
                    lease_owner="parent-owner",
                    lease_generation=4,
                ),
            )
        )

        assert trace.service_registrations == []
        assert trace.lease_acquires == []
        assert trace.lease_releases == []
        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1
        assert trace.heartbeat_initial_tokens[0].owner == "parent-owner"
        assert trace.heartbeat_initial_tokens[0].generation == 4
        assert trace.heartbeat_stop_tokens[0].owner == "parent-owner"
        assert trace.heartbeat_stop_tokens[0].generation == 4
        assert trace.heartbeat_stop_tokens[0].state_version == store.state_version
        assert trace.events.index("heartbeat.stop") < trace.events.index("store.close")
        assert [item["status"] for item in trace.workflow_transitions] == [
            "running",
            "succeeded",
        ]
        _assert_no_external_calls(trace)

    def test_heartbeat_token_tracks_runner_checkpoint_and_stop_refresh(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        trace = _Trace()
        store = _FakeStore(state_api, trace, tmp_path / "state.sqlite3")
        token = store.acquire_lease(
            store.execution_id,
            store.instance_id,
            0,
            "local-owner",
        )
        workers: list[_FakeHeartbeatWorker] = []

        def _worker_factory(
            path: Path,
            worker_token: Any,
            *,
            interval_seconds: float = 5.0,
            on_failure: Optional[Callable[[BaseException], None]] = None,
        ) -> _FakeHeartbeatWorker:
            worker = _FakeHeartbeatWorker(
                path,
                worker_token,
                trace,
                interval_seconds=interval_seconds,
                on_failure=on_failure,
            )
            workers.append(worker)
            return worker

        monkeypatch.setattr(orchestrator, "HeartbeatWorker", _worker_factory)

        class _CheckpointRunner:
            def __init__(self) -> None:
                self._durable_token_lock = threading.RLock()
                self.token: Any = None

            def _durable_lease_token_from_context(self) -> Any:
                return self.token

            def _set_durable_lease_token(self, next_token: Any) -> None:
                self.token = next_token

            def _commit_durable_checkpoint(self) -> None:
                self.token = store.transition_step(
                    self.token,
                    "1",
                    "running",
                    phase="main",
                    phase_state="running",
                    session_id="session-1",
                )

        runner = _CheckpointRunner()
        lifecycle = orchestrator._DurableWorkflowLifecycle(
            store,
            token,
            locally_owned=True,
        )
        lifecycle.attach_runner(runner)
        lifecycle.transition_workflow("running", run_id="run-test")

        async def _exercise() -> tuple[Any, Any, Any]:
            lifecycle.start_heartbeat()
            initial = workers[0].token
            runner._commit_durable_checkpoint()
            after_checkpoint = workers[0].token
            runner.token = store.transition_step(
                runner.token,
                "1",
                "running",
                phase="review",
                phase_state="running",
                session_id="session-review",
            )
            before_stop = workers[0].token
            lifecycle.stop_heartbeat()
            return initial, after_checkpoint, before_stop

        initial, after_checkpoint, before_stop = asyncio.run(_exercise())
        lifecycle.release()
        lifecycle.close()

        assert initial.state_version == 1
        assert after_checkpoint.state_version == 2
        assert before_stop.state_version == 2
        assert trace.heartbeat_stop_tokens[0].state_version == 3
        assert trace.lease_releases[0].state_version == 3
        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1

    def test_release_uses_runner_newest_token_exactly_once(
        self,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        trace = _Trace()
        store = _FakeStore(state_api, trace, tmp_path / "state.sqlite3")
        token = store.acquire_lease(
            store.execution_id,
            store.instance_id,
            0,
            "local-owner",
        )

        class _TokenAwareRunner:
            def __init__(self) -> None:
                self._durable_token_lock = threading.RLock()
                self.token: Any = None

            def _durable_lease_token_from_context(self) -> Any:
                return self.token

            def _set_durable_lease_token(self, next_token: Any) -> None:
                self.token = next_token

        runner = _TokenAwareRunner()
        lifecycle = orchestrator._DurableWorkflowLifecycle(
            store,
            token,
            locally_owned=True,
        )
        lifecycle.attach_runner(runner)
        lifecycle.transition_workflow("running", run_id="run-test")
        checkpoint_token = store.transition_step(
            runner.token,
            "1",
            "running",
            phase="main",
            phase_state="running",
            session_id="session-1",
        )
        runner._set_durable_lease_token(checkpoint_token)
        lifecycle.transition_step("1", "succeeded")

        lifecycle.release()
        lifecycle.release()
        lifecycle.close()

        assert len(trace.lease_releases) == 1
        assert trace.lease_releases[0].state_version == store.state_version

    def test_supplied_identity_is_scoped_to_current_repository(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        trace = _Trace()
        store = _install_durable_fakes(
            monkeypatch,
            trace,
            tmp_path / "state.sqlite3",
        )
        store.execution["repo_key"] = state_api.compute_repo_key(tmp_path / "other")
        _install_run_harness(
            monkeypatch,
            trace,
            _success_without_callbacks,
            tmp_path,
        )

        with pytest.raises(
            state_api.DurableStateError,
            match="another repository",
        ):
            asyncio.run(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                    orchestrator_ctx=_context(
                        execution_id=store.execution_id,
                        instance_id=store.instance_id,
                    ),
                )
            )

        assert trace.lease_acquires == []
        assert trace.lease_releases == []
        assert "executor.execute" not in trace.events

    def test_open_cleanup_failure_does_not_mask_the_primary_state_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        trace = _Trace()
        store = _install_durable_fakes(
            monkeypatch,
            trace,
            tmp_path / "state.sqlite3",
        )
        store.execution["repo_key"] = state_api.compute_repo_key(tmp_path / "other")

        def _fail_close() -> None:
            raise RuntimeError("secondary close failure")

        store.close = _fail_close  # type: ignore[method-assign]
        _install_run_harness(
            monkeypatch,
            trace,
            _success_without_callbacks,
            tmp_path,
        )

        with pytest.raises(
            state_api.DurableStateError,
            match="another repository",
        ) as captured:
            asyncio.run(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                    orchestrator_ctx=_context(
                        execution_id=store.execution_id,
                        instance_id=store.instance_id,
                    ),
                )
            )

        assert any(
            "secondary close failure" in note
            for note in captured.value.__notes__
        )


class TestApprovalRecords:
    def test_approved_wave_uses_a_succeeded_approval_pseudo_row(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()

        async def _approve(executor: _FakeDAGExecutor) -> dict[str, Any]:
            assert executor.on_wave_start is not None, "durable wave callback が未配線です"
            step = SimpleNamespace(id="1", title="one", approval_gate=True)
            executor.on_wave_start([step], 4)
            return _mark_success(executor, executor.active_step_ids)

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _approve, tmp_path)
        monkeypatch.setattr(approval, "stdin_is_interactive", lambda: True)
        monkeypatch.setattr(approval, "request_wave_approval", lambda *a, **k: None)

        asyncio.run(
            orchestrator.run_workflow(
                "aas",
                params={**_params(), "approval_gates": True},
                config=_config(),
            )
        )

        records = _approval_records(trace, 4)
        assert len(records) == 1
        assert records[0]["record_kind"] == "approval"
        assert records[0]["status"] == "succeeded"
        assert not {
            "approver",
            "answer",
            "prompt",
            "response",
            "reason",
            "free_text",
        } & set(records[0])
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)

    def test_declined_wave_uses_a_failed_approval_pseudo_row_and_blocks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()

        async def _decline(executor: _FakeDAGExecutor) -> dict[str, Any]:
            assert executor.on_wave_start is not None, "durable wave callback が未配線です"
            step = SimpleNamespace(id="1", title="one", approval_gate=True)
            executor.on_wave_start([step], 5)
            raise AssertionError("approval decline は callback から伝播する必要があります")

        def _raise_decline(
            _steps: Any,
            wave_index: int,
            **_kwargs: Any,
        ) -> None:
            raise approval.ApprovalDeclined("declined", wave_index=wave_index)

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _decline, tmp_path)
        monkeypatch.setattr(approval, "stdin_is_interactive", lambda: True)
        monkeypatch.setattr(approval, "request_wave_approval", _raise_decline)

        result = asyncio.run(
            orchestrator.run_workflow(
                "aas",
                params={**_params(), "approval_gates": True},
                config=_config(),
            )
        )

        records = _approval_records(trace, 5)
        assert len(records) == 1
        assert records[0]["record_kind"] == "approval"
        assert records[0]["status"] == "failed"
        assert result["blocked"] == ["1"]
        assert result["error"] == "declined"
        assert [item["status"] for item in trace.workflow_transitions][-1] == "blocked"
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)


class TestHeartbeatFailure:
    def test_normal_failed_result_stops_worker_once_before_release(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()

        async def _fail(executor: _FakeDAGExecutor) -> dict[str, Any]:
            step_id = sorted(executor.active_step_ids)[0]
            assert executor.on_step_start is not None
            assert executor.on_step_complete is not None
            executor.on_step_start(step_id)
            result = dag_executor.StepResult(
                step_id,
                success=False,
                elapsed=0.0,
                error="injected normal failure",
            )
            executor.failed.add(step_id)
            executor._results[step_id] = result
            executor.on_step_complete(result)
            return dict(executor._results)

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _fail, tmp_path)

        result = asyncio.run(
            orchestrator.run_workflow(
                "aas",
                params=_params(),
                config=_config(),
            )
        )

        assert result["failed"] == ["1"]
        assert [item["status"] for item in trace.workflow_transitions] == [
            "running",
            "failed",
        ]
        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1
        assert len(trace.lease_releases) == 1
        assert trace.events.index("heartbeat.stop") < trace.events.index("lease.release")
        assert trace.events.index("lease.release") < trace.events.index("store.close")
        _assert_no_external_calls(trace)

    def test_failure_cancels_executor_commits_suspended_and_rethrows(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        _resume_api()
        trace = _Trace(heartbeat_error=state_api.DurableStateError("heartbeat fenced"))

        async def _block(executor: _FakeDAGExecutor) -> dict[str, Any]:
            executor.trace.executor_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                executor.trace.executor_cancelled = True
                executor.trace.events.append("executor.quiesced")
                raise

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _block, tmp_path)

        async def _invoke() -> dict[str, Any]:
            return await asyncio.wait_for(
                orchestrator.run_workflow("aas", params=_params(), config=_config()),
                timeout=1.0,
            )

        with pytest.raises(state_api.DurableStateError, match="heartbeat fenced"):
            asyncio.run(_invoke())

        assert trace.executor_cancelled is True
        workflow_states = [item["status"] for item in trace.workflow_transitions]
        assert "suspended" in workflow_states
        assert workflow_states[-1] == "suspended"
        assert trace.events.index("executor.quiesced") < trace.events.index(
            "workflow:suspended"
        )
        assert trace.events.index("workflow:suspended") < trace.events.index(
            "heartbeat.stop"
        )
        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1
        assert len(trace.lease_releases) == 1
        assert trace.events.index("heartbeat.stop") < trace.events.index("lease.release")
        assert trace.events.index("lease.release") < trace.events.index("store.close")
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)

    def test_failure_cancels_and_quiesces_all_owned_siblings(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        state_api = _state_api()
        trace = _Trace(
            heartbeat_error=state_api.DurableStateError("heartbeat fenced")
        )
        started: set[str] = set()
        cancelled: set[str] = set()
        workflow = WorkflowDef(
            id="aas",
            name="heartbeat siblings",
            label_prefix="aas",
            state_labels={},
            params=[],
            steps=[
                StepDef(
                    id="1",
                    title="first",
                    custom_agent=None,
                    consumed_artifacts=[],
                ),
                StepDef(
                    id="2",
                    title="second",
                    custom_agent=None,
                    consumed_artifacts=[],
                ),
            ],
        )

        async def _run_step(step_id: str, **_kwargs: Any) -> bool:
            started.add(step_id)
            if started == {"1", "2"}:
                trace.executor_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.add(step_id)
                raise

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(
            monkeypatch,
            trace,
            _success_without_callbacks,
            tmp_path,
            workflow=workflow,
        )

        def _real_executor(*args: Any, **kwargs: Any) -> dag_executor.DAGExecutor:
            kwargs["run_step_fn"] = _run_step
            return dag_executor.DAGExecutor(*args, **kwargs)

        monkeypatch.setattr(orchestrator, "DAGExecutor", _real_executor)

        async def _invoke() -> dict[str, Any]:
            return await asyncio.wait_for(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                ),
                timeout=1.0,
            )

        with pytest.raises(state_api.DurableStateError, match="heartbeat fenced"):
            asyncio.run(_invoke())

        assert started == {"1", "2"}
        assert cancelled == {"1", "2"}
        assert [item["status"] for item in trace.workflow_transitions] == [
            "running",
            "suspended",
        ]
        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1
        assert len(trace.lease_releases) == 1
        assert trace.events.index("heartbeat.stop") < trace.events.index("lease.release")
        assert trace.events.index("lease.release") < trace.events.index("store.close")
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)

    def test_running_state_starts_worker_before_pre_execution_planning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()
        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(
            monkeypatch,
            trace,
            _success_without_callbacks,
            tmp_path,
        )

        def _fail_plan(**_kwargs: Any) -> str:
            raise ValueError("injected prompt plan failure")

        monkeypatch.setattr(orchestrator, "_build_step_prompt", _fail_plan)

        with pytest.raises(ValueError, match="prompt plan failure"):
            asyncio.run(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                )
            )

        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1
        assert "executor.execute" not in trace.events
        assert [item["status"] for item in trace.workflow_transitions] == [
            "running",
            "failed",
        ]
        assert len(trace.lease_releases) == 1
        assert trace.events.index("workflow:running") < trace.events.index(
            "heartbeat.start"
        )
        assert trace.events.index("heartbeat.stop") < trace.events.index(
            "lease.release"
        )
        assert trace.events.index("lease.release") < trace.events.index("store.close")
        _assert_no_external_calls(trace)

    def test_gui_graceful_cancel_commits_and_stops_within_three_seconds(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()
        quiescence_barrier = threading.Barrier(2)

        async def _block(executor: _FakeDAGExecutor) -> dict[str, Any]:
            executor.trace.executor_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                executor.trace.executor_cancelled = True
                await asyncio.to_thread(quiescence_barrier.wait, 2.0)
                executor.trace.events.append("executor.quiesced")
                raise

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _block, tmp_path)

        async def _invoke_and_cancel() -> float:
            task = asyncio.create_task(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                )
            )
            started = await asyncio.wait_for(
                asyncio.to_thread(trace.executor_started.wait, 1.0),
                timeout=1.5,
            )
            assert started is True
            loop = asyncio.get_running_loop()
            cancel_started = loop.time()
            task.cancel()
            await asyncio.wait_for(
                asyncio.to_thread(quiescence_barrier.wait, 2.0),
                timeout=2.5,
            )
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=3.0)
            return loop.time() - cancel_started

        elapsed = asyncio.run(_invoke_and_cancel())

        assert elapsed < 3.0
        assert trace.executor_cancelled is True
        assert [item["status"] for item in trace.workflow_transitions] == [
            "running",
            "suspended",
        ]
        assert trace.events.index("executor.quiesced") < trace.events.index(
            "workflow:suspended"
        )
        assert trace.events.index("workflow:suspended") < trace.events.index(
            "heartbeat.stop"
        )
        assert trace.heartbeat_starts == 1
        assert trace.heartbeat_stops == 1
        assert len(trace.lease_releases) == 1
        assert trace.events.index("heartbeat.stop") < trace.events.index("lease.release")
        assert trace.events.index("lease.release") < trace.events.index("store.close")
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)

    def test_non_cooperative_executor_does_not_block_final_suspend_and_worker_stop(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()
        release_executor = threading.Event()
        executor_exited = threading.Event()

        async def _resist_cancel(executor: _FakeDAGExecutor) -> dict[str, Any]:
            executor.trace.executor_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                executor.trace.executor_cancelled = True
                await asyncio.to_thread(release_executor.wait, 5.0)
                executor_exited.set()
                return {}

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _resist_cancel, tmp_path)

        async def _scenario() -> float:
            task = asyncio.create_task(
                orchestrator.run_workflow(
                    "aas",
                    params=_params(),
                    config=_config(),
                )
            )
            started = await asyncio.wait_for(
                asyncio.to_thread(trace.executor_started.wait, 1.0),
                timeout=1.5,
            )
            assert started is True
            loop = asyncio.get_running_loop()
            cancel_started = loop.time()
            task.cancel()
            done, _pending = await asyncio.wait((task,), timeout=2.9)
            elapsed = loop.time() - cancel_started
            assert task in done
            with pytest.raises(asyncio.CancelledError):
                await task
            release_executor.set()
            exited = await asyncio.wait_for(
                asyncio.to_thread(executor_exited.wait, 1.0),
                timeout=1.5,
            )
            assert exited is True
            return elapsed

        elapsed = asyncio.run(_scenario())

        assert elapsed < 3.0
        assert trace.executor_cancelled is True
        assert [item["status"] for item in trace.workflow_transitions] == [
            "running",
            "suspended",
        ]
        assert trace.events.index("workflow:suspended") < trace.events.index(
            "heartbeat.stop"
        )
        assert trace.events.index("heartbeat.stop") < trace.events.index(
            "lease.release"
        )
        assert trace.events.index("lease.release") < trace.events.index("store.close")


class TestFanoutOutputInvalidation:
    def test_missing_child_output_reactivates_child_and_transitive_descendants_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()
        store = _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)

        steps = [
            StepDef(
                id="1/A",
                title="fan-out A",
                custom_agent=None,
                output_paths=["out/a.txt"],
            ),
            StepDef(
                id="1/B",
                title="fan-out B",
                custom_agent=None,
                output_paths=["out/b.txt"],
            ),
            StepDef(
                id="2",
                title="child descendant",
                custom_agent=None,
                depends_on=["1/A"],
                output_paths=["out/2.txt"],
            ),
            StepDef(
                id="3",
                title="transitive descendant",
                custom_agent=None,
                depends_on=["2"],
                output_paths=["out/3.txt"],
            ),
            StepDef(
                id="9",
                title="independent",
                custom_agent=None,
                output_paths=["out/9.txt"],
            ),
        ]
        workflow = WorkflowDef(
            id="aas",
            name="resume fan-out fixture",
            label_prefix="aas",
            state_labels={},
            params=[],
            steps=steps,
        )
        for relative in ("out/b.txt", "out/2.txt", "out/3.txt", "out/9.txt"):
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("present", encoding="utf-8")

        store.execution_id = "exec-existing"
        store.instance_id = "instance-existing"
        store.workflow_id = "aas"
        store.state_version = 7
        store.execution["execution_id"] = store.execution_id
        store.instance.update(
            execution_id=store.execution_id,
            instance_id=store.instance_id,
            workflow_id="aas",
            status="suspended",
            state_version=7,
        )
        store.steps = [
            _Record(
                execution_id=store.execution_id,
                instance_id=store.instance_id,
                step_id=step.id,
                record_kind="step",
                status="succeeded",
            )
            for step in steps
        ]

        _install_run_harness(
            monkeypatch,
            trace,
            _success_without_callbacks,
            tmp_path,
            workflow=workflow,
        )
        context = _context(
            execution_id=store.execution_id,
            instance_id=store.instance_id,
            expected_state_version=7,
            recovery_action="restart-step",
        )

        asyncio.run(
            orchestrator.run_workflow(
                "aas",
                params={"branch": "main", "selected_steps": [step.id for step in steps]},
                config=_config(run_id="run-resumed"),
                orchestrator_ctx=context,
            )
        )

        scheduled = trace.executor_active_sets[-1]
        assert {"1/A", "2", "3"} <= scheduled
        assert {"1/B", "9"}.isdisjoint(scheduled)
        assert trace.service_registrations == []
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)


class TestLegacyCutover:
    def test_orchestrator_contains_zero_legacy_jsonl_writes(self) -> None:
        tree = ast.parse(_ORCHESTRATOR_PATH.read_text(encoding="utf-8"))
        writes = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "record_step"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "run_progress"
        ]
        assert writes == [], (
            "orchestrator に legacy JSONL write が残っています; "
            f"expected=0 actual={len(writes)} lines={writes}"
        )

    def test_explicit_legacy_resume_reads_the_selected_workflow_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()
        calls: list[tuple[str, str]] = []
        workflow = WorkflowDef(
            id="aas",
            name="legacy workflow scope",
            label_prefix="aas",
            state_labels={},
            params=[],
            steps=[
                StepDef(id="1", title="already done", custom_agent=None),
                StepDef(id="2", title="still pending", custom_agent=None),
            ],
        )

        def _completed(run_id: str, workflow_id: str) -> frozenset[str]:
            calls.append((run_id, workflow_id))
            return frozenset({"1"})

        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(
            monkeypatch,
            trace,
            _success_without_callbacks,
            tmp_path,
            workflow=workflow,
        )
        monkeypatch.setattr(run_progress, "completed_steps", _completed)

        result = asyncio.run(
            orchestrator.run_workflow(
                "aas",
                params={
                    "branch": "main",
                    "selected_steps": ["1", "2"],
                    "resume_run": "legacy-run-1",
                },
                config=_config(),
            )
        )

        assert calls == [("legacy-run-1", "aas")]
        assert trace.executor_active_sets[-1] == {"2"}
        assert result["completed"] == ["2"]
        assert trace.jsonl_calls == []


class TestRegistrationBoundary:
    def test_direct_registration_uses_the_complete_resolved_replay_shape(
        self,
        tmp_path: Path,
    ) -> None:
        resume_api = _resume_api()
        service = resume_api.ResumeService(SimpleNamespace(), tmp_path)
        config = _config(
            additional_prompt="do-not-persist-this-prompt",
            mcp_servers={"configured": {"type": "local"}},
            unattended=True,
        )
        argv = orchestrator._build_direct_durable_argv(
            "aas",
            {
                **_params(),
                "app_id": "APP-009",
                "sources": "qa,original-docs",
                "approval_gates": True,
            },
            config,
        )

        safe_argv, missing = service.sanitize_argv(argv)

        assert "--sources" in safe_argv
        assert safe_argv[safe_argv.index("--sources") + 1] == "qa,original-docs"
        assert "--approval-gates" in safe_argv
        assert "--strict" in safe_argv
        assert "--unattended" in safe_argv
        assert safe_argv[safe_argv.index("--app-ids") + 1] == "APP-009"
        assert "additional_prompt" in missing
        assert "mcp_config" in missing
        assert "do-not-persist-this-prompt" not in safe_argv

    def test_direct_replay_uses_the_effective_continue_on_error_mode(
        self,
    ) -> None:
        argv = orchestrator._build_direct_durable_argv(
            "aas",
            _params(),
            _config(),
            continue_on_error=True,
        )

        assert "--strict" not in argv

    def test_code_review_error_is_a_failed_durable_terminal_state(self) -> None:
        assert orchestrator._durable_terminal_workflow_status(
            {
                "completed": ["1"],
                "failed": [],
                "code_review_error": "review failed",
            }
        ) == "failed"

    def test_dry_run_registers_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        trace = _Trace()
        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _success_without_callbacks, tmp_path)

        result = asyncio.run(
            orchestrator.run_workflow(
                "aas",
                params=_params(),
                config=_config(dry_run=True),
            )
        )

        assert result["dry_run"] is True
        assert trace.service_registrations == []
        assert trace.store_registrations == []
        assert trace.workflow_transitions == []
        assert trace.step_transitions == []
        assert trace.heartbeat_starts == 0
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)

    @pytest.mark.parametrize(
        "unsupported_flag",
        ["fleet_mode_enabled", "cloud_session_enabled"],
        ids=["fleet", "cloud-session"],
    )
    def test_initial_unsupported_modes_register_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        unsupported_flag: str,
    ) -> None:
        trace = _Trace()
        _install_durable_fakes(monkeypatch, trace, tmp_path / "state.sqlite3")
        _install_jsonl_spy(monkeypatch, trace)
        _install_run_harness(monkeypatch, trace, _success_without_callbacks, tmp_path)

        asyncio.run(
            orchestrator.run_workflow(
                "aas",
                params=_params(),
                config=_config(**{unsupported_flag: True}),
            )
        )

        assert trace.service_registrations == []
        assert trace.store_registrations == []
        assert trace.workflow_transitions == []
        assert trace.step_transitions == []
        assert trace.heartbeat_starts == 0
        assert trace.jsonl_calls == []
        _assert_no_external_calls(trace)