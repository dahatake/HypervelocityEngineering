"""FR-CLI-90 / FR-TS-13 — StepRunner durable SDK resume の offline 契約。

durable store と SDK runtime は fake に置換する。実 SDK の wire 検査も fake
transport だけを使用し、起動・ダウンロード・実通信は行わない。公開
``run_step()`` の観測可能な順序と fail-closed 動作を固定する。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import json
import socket
import sqlite3
import subprocess
import sys
import types
import unittest.mock
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Callable, Iterator, Optional
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from copilot import CopilotClient as _SDKClient, RuntimeConnection as _SDKConnection
from copilot.generated.rpc import (
    CurrentToolMetadata,
    MCPDisableRequest,
    MCPListToolsRequest,
    SessionUpdateOptionsParams,
    ToolsGetCurrentMetadataResult,
)
from copilot.generated.session_events import SessionEventType, SessionResumeData
from copilot.session import CopilotSession as _SDKSession
from copilot.tools import Tool

from hve.config import SDKConfig
from hve.console import Console
from hve.toolsearch.policy import ToolSearchPolicy
from hve.toolsearch.resource_inventory import ResourceItem, ResourceSnapshot
from hve.toolsearch.resource_routing import (
    ResourceRoute,
    build_routed_session_options,
    restrict_resource_route,
)


_RECOVERY_PROMPT_PATH = "runtime/runner/resume-recovery.prompt.md"
_RECOVERY_PROMPT_SENTINEL = "FIXED-RECOVERY-PROMPT-SENTINEL"
_MAIN_PROMPT = "ORIGINAL-MAIN-TASK-MUST-RESTART-FROM-BEGINNING"


class _Record(dict[str, Any]):
    """SQLite row と dataclass の双方に近い fake record。"""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - diagnostic path
            raise AttributeError(name) from exc


class _DurableStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class _LeaseToken:
    execution_id: str
    instance_id: str
    owner: str
    generation: int
    state_version: int


@dataclass
class _Trace:
    events: list[tuple[str, Any]] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    create_calls: list[dict[str, Any]] = field(default_factory=list)
    resume_calls: list[dict[str, Any]] = field(default_factory=list)
    resume_handler_present: list[bool] = field(default_factory=list)
    send_prompts: list[str] = field(default_factory=list)
    network_attempts: int = 0


class _FakeStore:
    def __init__(
        self,
        trace: _Trace,
        *,
        phase: Optional[str],
        phase_state: Optional[str],
        session_id: Optional[str],
    ) -> None:
        self.trace = trace
        self.execution_id = "execution-001"
        self.instance_id = "aas#1"
        self.step_id = "1"
        self.state_version = 7
        self.closed = False
        self.instance = _Record(
            execution_id=self.execution_id,
            instance_id=self.instance_id,
            workflow_id="aas",
            status="running",
            state_version=self.state_version,
            current_run_id="old-run",
            run_id="old-run",
        )
        self.step = _Record(
            execution_id=self.execution_id,
            instance_id=self.instance_id,
            step_id=self.step_id,
            record_kind="step",
            status="running",
            phase=phase,
            phase_state=phase_state,
            session_id=session_id,
            state_version=self.state_version,
        )
        self.token = _LeaseToken(
            execution_id=self.execution_id,
            instance_id=self.instance_id,
            owner="runner-test-owner",
            generation=3,
            state_version=self.state_version,
        )

    def __enter__(self) -> "_FakeStore":
        self.trace.events.append(("store.enter", None))
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def close(self) -> None:
        self.closed = True
        self.trace.events.append(("store.close", None))

    def quick_check(self) -> bool:
        return True

    def get_execution(self, execution_id: str) -> Optional[_Record]:
        if execution_id != self.execution_id:
            return None
        return _Record(execution_id=self.execution_id, repo_key="repo-key")

    def get_instance(
        self, execution_id: str, instance_id: str
    ) -> Optional[_Record]:
        if (execution_id, instance_id) != (self.execution_id, self.instance_id):
            return None
        return self.instance

    def list_instances(self, execution_id: str) -> list[_Record]:
        return [self.instance] if execution_id == self.execution_id else []

    def list_steps(self, execution_id: str, instance_id: str) -> list[_Record]:
        if (execution_id, instance_id) != (self.execution_id, self.instance_id):
            return []
        return [self.step]

    def get_step(
        self, execution_id: str, instance_id: str, step_id: str
    ) -> Optional[_Record]:
        if (
            execution_id,
            instance_id,
            step_id,
        ) != (self.execution_id, self.instance_id, self.step_id):
            return None
        return self.step

    def acquire_lease(
        self,
        execution_id: str,
        instance_id: str,
        expected_state_version: int,
        owner: str,
        *,
        now: Any = None,
        allow_takeover: bool = False,
    ) -> _LeaseToken:
        payload = {
            "execution_id": execution_id,
            "instance_id": instance_id,
            "expected_state_version": expected_state_version,
            "owner": owner,
            "now": now,
            "allow_takeover": allow_takeover,
        }
        self.trace.events.append(("store.acquire", payload))
        self.token = _LeaseToken(
            execution_id=execution_id,
            instance_id=instance_id,
            owner=owner,
            generation=self.token.generation + 1,
            state_version=expected_state_version,
        )
        return self.token

    def transition_step(
        self,
        token: _LeaseToken,
        step_id: str,
        status: str,
        *,
        record_kind: str = "step",
        phase: Optional[str] = None,
        phase_state: Optional[str] = None,
        session_id: Optional[str] = None,
        last_error_type: Optional[str] = None,
        **extra: Any,
    ) -> _LeaseToken:
        if token.state_version != self.state_version:
            raise _DurableStateError("durable step transition was fenced")
        payload = {
            "step_id": step_id,
            "status": status,
            "record_kind": record_kind,
            "phase": phase,
            "phase_state": phase_state,
            "session_id": session_id,
            "last_error_type": last_error_type,
            **extra,
        }
        self.trace.transitions.append(payload)
        self.trace.events.append(("durable.transition", payload))
        self.state_version += 1
        self.step.update(payload)
        self.step["state_version"] = self.state_version
        self.instance["state_version"] = self.state_version
        self.token = replace(token, state_version=self.state_version)
        return self.token

    def transition_workflow(
        self,
        token: _LeaseToken,
        status: str,
        **_kwargs: Any,
    ) -> _LeaseToken:
        self.state_version += 1
        self.instance.update(status=status, state_version=self.state_version)
        self.token = replace(token, state_version=self.state_version)
        return self.token

    def heartbeat(self, token: _LeaseToken, *, now: Any = None) -> _LeaseToken:
        del now
        return token

    def release_lease(self, token: _LeaseToken) -> None:
        self.trace.events.append(("store.release", token))


class _FakeSession:
    def __init__(self, trace: _Trace, label: str) -> None:
        self.trace = trace
        self.label = label
        self.handlers: list[Callable[[Any], None]] = []
        self.disconnect_calls = 0
        self.already_in_use = False
        self.session_was_active = False

    def on(self, callback: Callable[[Any], None]) -> Callable[[], None]:
        self.handlers.append(callback)
        self.trace.events.append((f"session.on.{self.label}", callback))
        return lambda: None

    async def send_and_wait(self, prompt: str, *, timeout: float) -> Any:
        self.trace.send_prompts.append(prompt)
        self.trace.events.append(
            ("sdk.send", {"label": self.label, "prompt": prompt, "timeout": timeout})
        )
        return SimpleNamespace(text="fake response")

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.trace.events.append((f"session.disconnect.{self.label}", None))


class _FakeClient:
    def __init__(
        self,
        trace: _Trace,
        *,
        resume_flags: tuple[bool, bool] = (False, False),
        resume_error: Optional[BaseException] = None,
        resume_event_delay: float = 0.0,
        omit_resume_event: bool = False,
    ) -> None:
        self.trace = trace
        self.resume_flags = resume_flags
        self.resume_error = resume_error
        self.resume_event_delay = resume_event_delay
        self.omit_resume_event = omit_resume_event
        self.resume_event_tasks: list[asyncio.Task[None]] = []
        self.created_session = _FakeSession(trace, "created")
        self.resumed_session = _FakeSession(trace, "resumed")
        self.start_calls = 0
        self.stop_calls = 0
        self.force_stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1
        self.trace.events.append(("sdk.client.start", None))

    async def create_session(self, *args: Any, **kwargs: Any) -> _FakeSession:
        if args:
            assert len(args) == 1 and isinstance(args[0], dict)
            kwargs = {**args[0], **kwargs}
        copied = dict(kwargs)
        self.trace.create_calls.append(copied)
        self.trace.events.append(("sdk.create", copied))
        return self.created_session

    async def resume_session(
        self,
        session_id: str,
        *,
        on_event: Optional[Callable[[Any], None]] = None,
        continue_pending_work: Optional[bool] = None,
        **kwargs: Any,
    ) -> _FakeSession:
        call = {
            "session_id": session_id,
            "on_event": on_event,
            "continue_pending_work": continue_pending_work,
            **kwargs,
        }
        self.trace.resume_calls.append(call)
        self.trace.resume_handler_present.append(callable(on_event))
        if callable(on_event) and not self.omit_resume_event:
            self.trace.events.append(("resume.handler.ready", on_event))
        self.trace.events.append(("sdk.resume", call))

        already_in_use, session_was_active = self.resume_flags
        if callable(on_event) and not self.omit_resume_event:
            event = SimpleNamespace(
                type=SessionEventType.SESSION_RESUME,
                data=SessionResumeData(
                    event_count=0,
                    resume_time=datetime.now(timezone.utc),
                    already_in_use=already_in_use,
                    session_was_active=session_was_active,
                ),
            )
            if self.resume_event_delay > 0:
                async def _emit_later() -> None:
                    await asyncio.sleep(self.resume_event_delay)
                    on_event(event)

                self.resume_event_tasks.append(asyncio.create_task(_emit_later()))
            else:
                on_event(event)
        if self.resume_error is not None:
            raise self.resume_error
        return self.resumed_session

    async def stop(self) -> None:
        if self.resume_event_tasks:
            await asyncio.gather(*self.resume_event_tasks, return_exceptions=True)
            self.resume_event_tasks.clear()
        self.stop_calls += 1
        self.trace.events.append(("sdk.client.stop", None))

    async def force_stop(self) -> None:
        self.force_stop_calls += 1
        self.trace.events.append(("sdk.client.force_stop", None))


class _FakeResumeService:
    def __init__(self, store: _FakeStore, repo_root: Path) -> None:
        self.store = store
        self.repo_root = Path(repo_root)

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
            workflow_id="aas",
            action=action,
            expected_state_version=self.store.state_version,
            risk_reasons=(),
            missing_replay_keys=(),
            argv=(),
            resume_plan_hash="fake-resume-plan-hash",
        )

    def acquire(self, plan: Any, owner: str) -> _LeaseToken:
        return self.store.acquire_lease(
            plan.execution_id,
            plan.instance_id,
            plan.expected_state_version,
            owner,
            allow_takeover=bool(plan.action),
        )


@dataclass(frozen=True)
class _Runtime:
    module: ModuleType
    trace: _Trace
    store: _FakeStore
    client: _FakeClient
    runner: Any
    network_guard: Callable[..., Any]

    def run(
        self,
        step_id: str = "1",
        *,
        workflow_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        async def _scenario() -> bool:
            # Windows の asyncio は event loop 作成・破棄時に内部 socketpair を
            # 使用する。loop 作成後から Runner 完了までだけ connect を禁止する。
            with (
                patch.object(socket.socket, "connect", self.network_guard),
                patch.object(socket.socket, "connect_ex", self.network_guard),
            ):
                execution = self.runner.run_step(
                    step_id,
                    "durable runner test",
                    _MAIN_PROMPT,
                    workflow_id=workflow_id,
                )
                if timeout is not None:
                    return await asyncio.wait_for(execution, timeout=timeout)
                return await execution

        return asyncio.run(
            _scenario()
        )


def _install_fake_state_modules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: _FakeStore,
) -> tuple[ModuleType, ModuleType]:
    state_module = types.ModuleType("hve.run_state_store")
    state_module.SCHEMA_VERSION = 1
    state_module.HEARTBEAT_INTERVAL_SECONDS = 5.0
    state_module.LEASE_TTL_SECONDS = 20.0
    state_module.BUSY_TIMEOUT_SECONDS = 1.0
    state_module.DurableStateError = _DurableStateError
    state_module.LeaseToken = _LeaseToken
    state_module.RunStateStore = lambda *_args, **_kwargs: store
    state_module.default_state_path = lambda: tmp_path / "fake-state.sqlite3"
    state_module.compute_repo_key = lambda root: hashlib.sha256(
        str(Path(root)).encode("utf-8")
    ).hexdigest()

    service_module = types.ModuleType("hve.resume_service")
    service_module.ResumeService = _FakeResumeService
    service_module.canonical_json = lambda value: json.dumps(
        value, sort_keys=True, default=str
    )
    service_module.compute_launch_plan_hash = lambda value: hashlib.sha256(
        repr(value).encode("utf-8")
    ).hexdigest()
    service_module.compute_resume_plan_hash = service_module.compute_launch_plan_hash

    monkeypatch.setitem(sys.modules, "hve.run_state_store", state_module)
    monkeypatch.setitem(sys.modules, "hve.resume_service", service_module)
    hve_package = importlib.import_module("hve")
    monkeypatch.setattr(hve_package, "run_state_store", state_module, raising=False)
    monkeypatch.setattr(hve_package, "resume_service", service_module, raising=False)
    return state_module, service_module


def _install_fake_copilot(monkeypatch: pytest.MonkeyPatch) -> None:
    class _PermissionHandler:
        approve_all = staticmethod(lambda *_args, **_kwargs: True)

    package = types.ModuleType("copilot")
    package.__path__ = []  # type: ignore[attr-defined]
    session_module = types.ModuleType("copilot.session")
    session_module.PermissionHandler = _PermissionHandler
    package.session = session_module
    monkeypatch.setitem(sys.modules, "copilot", package)
    monkeypatch.setitem(sys.modules, "copilot.session", session_module)


@pytest.fixture()
def runtime_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> "Iterator[Callable[..., _Runtime]]":
    runtimes: list[_Runtime] = []

    def make(
        *,
        action: Optional[str],
        phase: Optional[str] = "main",
        phase_state: Optional[str] = "running",
        session_id: Optional[str] = "saved-main-session",
        resume_flags: tuple[bool, bool] = (False, False),
        resume_error: Optional[BaseException] = None,
        resume_event_delay: float = 0.0,
        omit_resume_event: bool = False,
    ) -> _Runtime:
        trace = _Trace()
        store = _FakeStore(
            trace,
            phase=phase,
            phase_state=phase_state,
            session_id=session_id,
        )
        state_module, service_module = _install_fake_state_modules(
            monkeypatch, tmp_path, store
        )
        _install_fake_copilot(monkeypatch)

        runner_module = importlib.import_module("hve.runner")
        monkeypatch.setattr(
            runner_module, "RunStateStore", state_module.RunStateStore, raising=False
        )
        monkeypatch.setattr(
            runner_module, "default_state_path", state_module.default_state_path,
            raising=False,
        )
        monkeypatch.setattr(
            runner_module, "DurableStateError", _DurableStateError, raising=False
        )
        monkeypatch.setattr(
            runner_module, "LeaseToken", _LeaseToken, raising=False
        )
        monkeypatch.setattr(
            runner_module, "ResumeService", service_module.ResumeService, raising=False
        )
        monkeypatch.setattr(
            runner_module, "_ensure_step_work_dir", lambda *_args: tmp_path
        )
        monkeypatch.setattr(
            runner_module, "_extract_text", lambda response: getattr(response, "text", "")
        )

        async def _no_steering(_self: Any, _session: Any, _step_id: str) -> None:
            await asyncio.Future()

        monkeypatch.setattr(
            runner_module.StepRunner,
            "_poll_steering_ipc",
            _no_steering,
        )

        client = _FakeClient(
            trace,
            resume_flags=resume_flags,
            resume_error=resume_error,
            resume_event_delay=resume_event_delay,
            omit_resume_event=omit_resume_event,
        )
        client_factory = importlib.import_module("hve.copilot_client_factory")
        monkeypatch.setattr(
            client_factory,
            "create_copilot_client",
            lambda **_kwargs: client,
        )
        monkeypatch.setattr(
            runner_module,
            "create_copilot_client",
            lambda **_kwargs: client,
            raising=False,
        )

        def _deny_network(*_args: Any, **_kwargs: Any) -> Any:
            trace.network_attempts += 1
            raise AssertionError("runner resume RED tests must not use the network")

        monkeypatch.setattr(socket, "create_connection", _deny_network)

        config = SDKConfig(
            dry_run=False,
            model="gpt-5.4",
            run_id="new-attempt-run",
            auto_qa=False,
            auto_contents_review=False,
        )
        context = SimpleNamespace(
            execution_id=store.execution_id,
            instance_id=store.instance_id,
            expected_state_version=store.state_version,
            recovery_action=action,
            lease_owner=store.token.owner,
            lease_generation=store.token.generation,
            continue_on_error=False,
            # Runtime implementations may retain an already-acquired fenced token
            # in-process; these aliases remain fake-only and are never serialized.
            lease_token=store.token,
            durable_lease_token=store.token,
            run_state_store=store,
            durable_store=store,
        )
        step_runner = runner_module.StepRunner(
            config=config,
            console=Console(verbose=False, quiet=True),
            orchestrator_ctx=context,
            workflow_params={"selected_steps": [store.step_id]},
        )
        runtime = _Runtime(
            runner_module,
            trace,
            store,
            client,
            step_runner,
            _deny_network,
        )
        runtimes.append(runtime)
        return runtime

    yield make

    for runtime in runtimes:
        assert runtime.trace.network_attempts == 0, (
            "fake-only Runner tests attempted a real network connection"
        )


def _event_index(
    trace: _Trace,
    name: str,
    *,
    predicate: Optional[Callable[[Any], bool]] = None,
) -> int:
    for index, (event_name, payload) in enumerate(trace.events):
        if event_name == name and (predicate is None or predicate(payload)):
            return index
    pytest.fail(f"expected event {name!r}; actual={[item[0] for item in trace.events]}")


def _phase_session_commit_index(trace: _Trace, session_id: str) -> int:
    return _event_index(
        trace,
        "durable.transition",
        predicate=lambda payload: bool(payload.get("phase"))
        and payload.get("session_id") == session_id,
    )


class TestDurableCommitOrdering:
    def test_phase_and_session_id_are_committed_before_create_and_send(
        self,
        runtime_factory: Callable[..., _Runtime],
    ) -> None:
        runtime = runtime_factory(action=None, phase="main", session_id=None)

        assert runtime.run() is True
        assert len(runtime.trace.create_calls) == 1
        assert runtime.trace.resume_calls == []
        created_session_id = runtime.trace.create_calls[0].get("session_id")
        assert isinstance(created_session_id, str) and created_session_id

        commit_index = _phase_session_commit_index(runtime.trace, created_session_id)
        assert commit_index < _event_index(runtime.trace, "sdk.create")
        assert commit_index < _event_index(runtime.trace, "sdk.send")
        assert _MAIN_PROMPT not in repr(runtime.trace.transitions), (
            "durable phase records must not persist prompt/tool bodies"
        )

    def test_identity_only_normal_child_uses_existing_non_durable_session_path(
        self,
        runtime_factory: Callable[..., _Runtime],
    ) -> None:
        runtime = runtime_factory(action=None, phase=None, session_id=None)
        runtime.runner._orchestrator_ctx.expected_state_version = None
        runtime.runner._orchestrator_ctx.lease_owner = None
        runtime.runner._orchestrator_ctx.lease_generation = None

        assert runtime.run() is True
        assert len(runtime.trace.create_calls) == 1
        assert runtime.trace.transitions == []

    def test_main_checkpoint_is_preserved_across_repeated_steps(
        self,
        runtime_factory: Callable[..., _Runtime],
    ) -> None:
        runtime = runtime_factory(action=None, phase="main", session_id=None)

        assert runtime.run() is True
        first_version = runtime.store.state_version
        assert runtime.run() is True

        assert runtime.store.state_version > first_version
        assert len(runtime.trace.create_calls) == 2
        phases = [transition["phase"] for transition in runtime.trace.transitions]
        assert "split-fork" not in phases
        assert set(phases) == {"main"}

    def test_saved_session_is_recommitted_before_resume_and_recovery_send(
        self,
        runtime_factory: Callable[..., _Runtime],
    ) -> None:
        runtime = runtime_factory(action="reuse-session")

        assert runtime.run() is True
        assert runtime.trace.create_calls == []
        assert len(runtime.trace.resume_calls) == 1
        saved_session_id = runtime.trace.resume_calls[0]["session_id"]

        commit_index = _phase_session_commit_index(runtime.trace, saved_session_id)
        assert commit_index < _event_index(runtime.trace, "sdk.resume")
        assert commit_index < _event_index(runtime.trace, "sdk.send")


class TestMainSessionReuse:
    def test_reuse_disables_automatic_pending_work_continuation(
        self,
        runtime_factory: Callable[..., _Runtime],
    ) -> None:
        runtime = runtime_factory(action="reuse-session")

        assert runtime.run() is True
        assert len(runtime.trace.resume_calls) == 1
        assert (
            runtime.trace.resume_calls[0].get("continue_pending_work") is False
        )
        assert runtime.trace.create_calls == []

    def test_resume_event_handler_is_present_before_resume_rpc(
        self,
        runtime_factory: Callable[..., _Runtime],
    ) -> None:
        runtime = runtime_factory(action="reuse-session")

        assert runtime.run() is True
        assert runtime.trace.resume_handler_present == [True]
        assert _event_index(runtime.trace, "resume.handler.ready") < _event_index(
            runtime.trace, "sdk.resume"
        )

    def test_resume_reinstalls_the_step_permission_handler(
        self,
        runtime_factory: Callable[..., _Runtime],
    ) -> None:
        runtime = runtime_factory(action="reuse-session")

        assert runtime.run() is True
        assert callable(runtime.trace.resume_calls[0].get("on_permission_request"))

    def test_reuse_action_applies_only_to_the_selected_recovery_step(
        self,
        runtime_factory: Callable[..., _Runtime],
    ) -> None:
        runtime = runtime_factory(action="reuse-session")

        assert runtime.run("1") is True
        assert runtime.run("2") is True
        assert len(runtime.trace.resume_calls) == 1
        assert len(runtime.trace.create_calls) == 1


@pytest.mark.parametrize(
    "resume_flags",
    [(True, False), (False, True)],
    ids=["already-in-use", "session-was-active"],
)
def test_active_resume_event_disconnects_and_fails_closed(
    runtime_factory: Callable[..., _Runtime],
    resume_flags: tuple[bool, bool],
) -> None:
    runtime = runtime_factory(action="reuse-session", resume_flags=resume_flags)

    assert runtime.run() is False
    assert len(runtime.trace.resume_calls) == 1
    assert runtime.client.resumed_session.disconnect_calls >= 1
    assert runtime.client.stop_calls == 1
    assert runtime.trace.create_calls == []
    assert runtime.trace.send_prompts == []


def test_delayed_active_resume_event_blocks_recovery_send(
    runtime_factory: Callable[..., _Runtime],
) -> None:
    runtime = runtime_factory(
        action="reuse-session",
        resume_flags=(True, False),
        resume_event_delay=0.01,
    )

    assert runtime.run() is False
    assert runtime.client.resumed_session.disconnect_calls >= 1
    assert runtime.trace.send_prompts == []


def test_resume_rpc_hang_fails_within_the_control_deadline(
    runtime_factory: Callable[..., _Runtime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_factory(action="reuse-session")
    monkeypatch.setattr(runtime.module, "_RUNNER_RESUME_EVENT_TIMEOUT_SECONDS", 0.01)

    async def _hang_resume(*_args: Any, **_kwargs: Any) -> _FakeSession:
        await asyncio.Future()
        raise AssertionError("unreachable")

    runtime.client.resume_session = _hang_resume  # type: ignore[method-assign]

    assert runtime.run() is False
    assert runtime.trace.send_prompts == []
    assert runtime.client.stop_calls == 1


def test_missing_resume_event_fails_within_the_control_deadline(
    runtime_factory: Callable[..., _Runtime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_factory(action="reuse-session", omit_resume_event=True)
    monkeypatch.setattr(runtime.module, "_RUNNER_RESUME_EVENT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(runtime.module, "_RUNNER_CLEANUP_TIMEOUT_SECONDS", 0.01)

    assert runtime.run() is False
    assert runtime.trace.send_prompts == []
    assert runtime.client.resumed_session.disconnect_calls >= 1


def test_active_resume_disconnect_hang_does_not_block_failure(
    runtime_factory: Callable[..., _Runtime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_factory(action="reuse-session", resume_flags=(True, False))
    monkeypatch.setattr(runtime.module, "_RUNNER_CLEANUP_TIMEOUT_SECONDS", 0.01)

    async def _hang_disconnect() -> None:
        await asyncio.Future()

    runtime.client.resumed_session.disconnect = _hang_disconnect  # type: ignore[method-assign]

    assert runtime.run() is False
    assert runtime.trace.send_prompts == []
    assert runtime.client.stop_calls == 1


def test_client_stop_hang_uses_bounded_force_stop(
    runtime_factory: Callable[..., _Runtime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_factory(action="reuse-session")
    monkeypatch.setattr(runtime.module, "_RUNNER_CLEANUP_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(runtime.module, "_RUNNER_FORCE_STOP_TIMEOUT_SECONDS", 0.01)

    async def _hang_stop() -> None:
        await asyncio.Future()

    runtime.client.stop = _hang_stop  # type: ignore[method-assign]

    assert runtime.run() is True
    assert runtime.client.force_stop_calls == 1


def test_reuse_target_store_failure_remains_a_durable_state_error(
    runtime_factory: Callable[..., _Runtime],
) -> None:
    runtime = runtime_factory(action="reuse-session")

    def _fail_list_steps(execution_id: str, instance_id: str) -> list[_Record]:
        del execution_id, instance_id
        raise _DurableStateError("durable target read failed")

    runtime.store.list_steps = _fail_list_steps  # type: ignore[method-assign]

    with pytest.raises(_DurableStateError, match="durable target read failed"):
        runtime.run()
    assert runtime.trace.resume_calls == []
    assert runtime.trace.create_calls == []


def test_resume_failure_never_silently_falls_back_to_restart(
    runtime_factory: Callable[..., _Runtime],
) -> None:
    runtime = runtime_factory(
        action="reuse-session",
        resume_error=RuntimeError("simulated resume failure"),
    )

    assert runtime.run() is False
    assert len(runtime.trace.resume_calls) == 1
    assert runtime.trace.create_calls == []
    assert runtime.trace.send_prompts == []
    assert runtime.client.stop_calls == 1


@pytest.mark.parametrize(
    "phase",
    ["pre-qa", "review"],
    ids=["pre-qa", "review"],
)
def test_non_main_phase_rejects_reuse_before_any_sdk_session_action(
    runtime_factory: Callable[..., _Runtime],
    phase: str,
) -> None:
    runtime = runtime_factory(action="reuse-session", phase=phase)

    assert runtime.run() is False
    assert runtime.trace.resume_calls == []
    assert runtime.trace.create_calls == []
    assert runtime.trace.send_prompts == []


def test_restart_step_uses_a_fresh_session_and_original_main_task(
    runtime_factory: Callable[..., _Runtime],
) -> None:
    runtime = runtime_factory(action="restart-step", phase="review")

    assert runtime.run() is True
    assert runtime.trace.resume_calls == []
    assert len(runtime.trace.create_calls) == 1
    fresh_session_id = runtime.trace.create_calls[0].get("session_id")
    assert isinstance(fresh_session_id, str) and fresh_session_id
    assert fresh_session_id != "saved-main-session"
    assert len(runtime.trace.send_prompts) == 1
    assert _MAIN_PROMPT in runtime.trace.send_prompts[0]

    commit_index = _phase_session_commit_index(runtime.trace, fresh_session_id)
    assert commit_index < _event_index(runtime.trace, "sdk.create")
    assert commit_index < _event_index(runtime.trace, "sdk.send")


def test_reuse_sends_fixed_recovery_prompt_through_prompt_loader(
    runtime_factory: Callable[..., _Runtime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_factory(action="reuse-session")
    loader_calls: list[str] = []
    original_loader = runtime.module.load_prompt_file

    def _load(path: str) -> str:
        loader_calls.append(path)
        if path == _RECOVERY_PROMPT_PATH:
            return _RECOVERY_PROMPT_SENTINEL
        return original_loader(path)

    monkeypatch.setattr(runtime.module, "load_prompt_file", _load)

    assert runtime.run() is True
    assert _RECOVERY_PROMPT_PATH in loader_calls
    assert runtime.trace.send_prompts == [
        _RECOVERY_PROMPT_SENTINEL
        + runtime.module._build_runtime_guidance_suffix(
            unattended=False,
            step_timeout_seconds=runtime.runner.config.step_timeout_seconds,
        )
    ]
    assert _MAIN_PROMPT not in runtime.trace.send_prompts[0]
    assert _RECOVERY_PROMPT_SENTINEL not in repr(runtime.trace.transitions)
    assert runtime.trace.create_calls == []


def test_reuse_session_resolves_and_applies_resource_route_before_first_send(
    runtime_factory: Callable[..., _Runtime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_factory(action="reuse-session")
    snapshot = object()
    policy = object()
    route = ResourceRoute()

    monkeypatch.setattr(
        runtime.module,
        "discover_sdk_resources",
        lambda **_kwargs: snapshot,
        raising=False,
    )
    monkeypatch.setattr(
        runtime.module,
        "ToolSearchPolicy",
        SimpleNamespace(load=lambda **_kwargs: policy),
        raising=False,
    )

    def _resolve_resource_route(**kwargs: Any) -> Any:
        runtime.trace.events.append(("route.resolve", kwargs))
        assert kwargs["available_tools"] is None
        assert kwargs["excluded_tools"] is None
        return route

    async def _apply_resource_route(
        *, session: Any, route: Any, deadline: Optional[float] = None,
    ) -> Any:
        runtime.trace.events.append(
            ("route.apply", {"session": session, "route": route, "deadline": deadline})
        )
        return route

    monkeypatch.setattr(
        runtime.module,
        "resolve_resource_route",
        _resolve_resource_route,
        raising=False,
    )
    monkeypatch.setattr(
        runtime.module,
        "apply_resource_route",
        _apply_resource_route,
        raising=False,
    )
    monkeypatch.setattr(
        runtime.module,
        "_check_output_paths_gate",
        lambda *_args, **_kwargs: [],
        raising=False,
    )

    async def _scenario() -> bool:
        with unittest.mock.patch.object(
            socket.socket,
            "connect",
            runtime.network_guard,
        ):
            return await runtime.runner.run_step(
                "1",
                "durable runner test",
                _MAIN_PROMPT,
                workflow_id="ard",
            )

    assert asyncio.run(_scenario()) is True
    assert runtime.trace.create_calls == []
    assert len(runtime.trace.resume_calls) == 1
    assert _event_index(runtime.trace, "route.resolve") < _event_index(
        runtime.trace,
        "sdk.resume",
    )
    assert _event_index(runtime.trace, "sdk.resume") < _event_index(
        runtime.trace,
        "route.apply",
    )
    assert _event_index(runtime.trace, "route.apply") < _event_index(
        runtime.trace,
        "sdk.send",
    )


@pytest.fixture
def routed_resume(runtime_factory, monkeypatch):
    """Real ARD registry/route/apply; only external boundaries are replaced."""
    runtime = runtime_factory(action="reuse-session")
    module, runner = runtime.module, runtime.runner
    assert Path(module.__file__).resolve() == Path(__file__).resolve().parents[1] / "runner.py"
    assert runner.run_step.__func__.__globals__ is vars(module)
    workflow = importlib.import_module("hve.workflow_registry").get_workflow("ard")
    required = tuple(runner._get_required_skills_for_step("ard", "1", workflow))
    assert required == ("task-dag-planning", "knowledge-management")
    runtime.store.instance["workflow_id"] = "ard"
    for owner, name in (
        (socket, "getaddrinfo"), (sqlite3, "connect"),
        (subprocess, "Popen"), (subprocess, "run"),
        (asyncio, "create_subprocess_exec"), (asyncio, "create_subprocess_shell"),
    ):
        monkeypatch.setattr(owner, name, runtime.network_guard)
    monkeypatch.setattr(runner.config, "resolve_token", Mock(return_value=""))
    monkeypatch.setattr(runner.config, "tool_search_session_option", Mock(return_value=None))
    monkeypatch.setattr(module, "_check_output_paths_gate", Mock(return_value=[]))

    r = SimpleNamespace(
        runtime=runtime, module=module, runner=runner, client=runtime.client,
        trace=runtime.trace, required=required, options={}, base_options={},
        rpc_calls=[], deadlines=[],
    )
    r.snapshot = ResourceSnapshot(
        plugin_state="ready", mcp_state="ready", skill_state="ready",
        skill_ownership_state="ready", plugins=(),
        mcp_servers=tuple(ResourceItem("mcp_server", name, True, "user") for name in (
            "knowledge", "other-knowledge", "engineering", "unclassified",
        )),
        skills=tuple(ResourceItem("skill", name, True, "project") for name in (
            *required, "optional-knowledge", "engineering-skill", "unclassified-skill",
        )),
    )
    r.policy = ToolSearchPolicy(
        version=1, limit=5, max_limit=20, tau=0.0,
        field_weights={"name": 1, "additional_search_text": 1, "description": 1, "arg_terms": 1},
        pins={}, additional_search_text={},
        resource_classifications={
            "plugins": {},
            "mcp_servers": {
                "knowledge": "knowledge", "other-knowledge": "knowledge",
                "engineering": "software-engineering",
            },
            "skills": {
                **{name: "software-engineering" for name in required},
                "optional-knowledge": "knowledge", "engineering-skill": "software-engineering",
            },
        },
        knowledge_tool_allowlists={"knowledge": ("lookup",), "other-knowledge": ("lookup",)},
        software_engineering_tool_allowlists={"engineering": ("build",)},
        required_mcp_servers_by_skill={required[0]: ("knowledge",)},
    )
    add_directories = runner._add_required_external_skill_directories

    def add_options(options, skills):
        result = add_directories(options, skills)
        options.update(r.options)
        r.base_options = dict(options)
        return result

    monkeypatch.setattr(runner, "_add_required_external_skill_directories", add_options)
    r.discover = Mock(side_effect=lambda **_kwargs: r.snapshot)
    r.load_policy = Mock(side_effect=lambda **_kwargs: r.policy)
    monkeypatch.setattr(module, "discover_sdk_resources", r.discover)
    monkeypatch.setattr(module, "ToolSearchPolicy", SimpleNamespace(load=r.load_policy))
    r.resolve = Mock(wraps=module.resolve_resource_route)
    r.restrict = Mock(wraps=restrict_resource_route)
    r.build = Mock(wraps=build_routed_session_options)
    r.apply = AsyncMock(wraps=module.apply_resource_route)
    monkeypatch.setattr(module, "resolve_resource_route", r.resolve)
    monkeypatch.setattr(module, "restrict_resource_route", r.restrict, raising=False)
    monkeypatch.setattr(module, "build_routed_session_options", r.build, raising=False)
    monkeypatch.setattr(module, "apply_resource_route", r.apply)
    remaining = module._remaining_deadline_seconds

    def remaining_time(deadline):
        r.deadlines.append(deadline)
        return remaining(deadline)

    monkeypatch.setattr(module, "_remaining_deadline_seconds", remaining_time)
    r.handler = Mock(wraps=runner._handle_session_event_for_step)
    r.error = Mock(wraps=runner.console.error)
    monkeypatch.setattr(runner, "_handle_session_event_for_step", r.handler)
    monkeypatch.setattr(runner.console, "error", r.error)

    def rpc(name):
        async def reply(*args, timeout):
            r.rpc_calls.append((name, args, timeout))
            r.trace.events.append((name, args))
            if name == "rpc.skills":
                return SimpleNamespace(skills=[SimpleNamespace(name=n, enabled=True) for n in required])
            if name == "rpc.list":
                return SimpleNamespace(host=object(), servers=[
                    SimpleNamespace(name=n, status="connected") for n in ("knowledge", "other-knowledge")
                ])
            if name == "rpc.tools":
                return SimpleNamespace(tools=[SimpleNamespace(name=n) for n in ("lookup", "write")])
            if name == "rpc.options":
                return SimpleNamespace(success=True)
            if name == "rpc.metadata":
                servers = tuple(dict.fromkeys(
                    call_args[0].server_name
                    for call_name, call_args, _call_timeout in r.rpc_calls
                    if call_name == "rpc.tools"
                ))
                return ToolsGetCurrentMetadataResult(tools=[
                    CurrentToolMetadata(
                        description="offline MCP tool",
                        name=f"mcp__{server_name}__lookup",
                        mcp_server_name=server_name,
                        mcp_tool_name="lookup",
                        namespaced_name=f"mcp:{server_name}-lookup",
                    )
                    for server_name in servers
                ])
            return SimpleNamespace()

        return AsyncMock(side_effect=reply)

    r.rpc = SimpleNamespace(
        skills=SimpleNamespace(list=rpc("rpc.skills")),
        tools=SimpleNamespace(
            initialize_and_validate=rpc("rpc.init"),
            get_current_metadata=rpc("rpc.metadata"),
        ),
        mcp=SimpleNamespace(list=rpc("rpc.list"), list_tools=rpc("rpc.tools"), disable=rpc("rpc.disable")),
        options=SimpleNamespace(update=rpc("rpc.options")),
    )
    r.client.resumed_session.rpc = r.rpc
    r.run = lambda **kwargs: runtime.run(workflow_id="ard", **kwargs)
    return r


@pytest.mark.parametrize("tool_search", [None, {"enabled": False}, {"enabled": True, "defer_threshold": 8}], ids=["absent", "off", "on"])
def test_resume_pre_rpc_kwargs_and_apply_share_caller_restrictions(routed_resume, tool_search):
    r = routed_resume
    r.options.update(
        tools=[Tool(name="local-helper", description="offline tool")],
        disabled_mcp_servers=["other-knowledge", "absent-mcp", "other-knowledge"],
        disabled_skills=["optional-knowledge", "absent-skill", "optional-knowledge"],
        provider={"type": "openai"}, context_tier="long_context", reasoning_effort="high",
        infinite_sessions={"enabled": True}, cloud={"enabled": True}, unsupported_create_field=True,
    )
    if tool_search is not None:
        r.options["tool_search"] = tool_search
    original_options = {key: list(value) if isinstance(value, list) else value for key, value in r.options.items()}
    r.runner.config.available_tools = ["view", "local-helper", "mcp:knowledge-lookup", "mcp:other-knowledge-lookup"]
    r.runner.config.excluded_tools = ["write", "mcp:knowledge-write"]

    assert r.run() is True
    assert len(r.trace.resume_calls) == 1
    actual = r.trace.resume_calls[0]
    expected = {
        "session_id": "saved-main-session", "on_event": actual["on_event"],
        "on_permission_request": r.base_options["on_permission_request"],
        "continue_pending_work": False, "tools": r.options["tools"],
        "enable_config_discovery": True, "enable_skills": True,
        "skill_directories": r.base_options["skill_directories"],
        "disabled_mcp_servers": ["other-knowledge", "absent-mcp", "engineering", "unclassified", "github-mcp-server"],
        "disabled_skills": ["optional-knowledge", "absent-skill", "engineering-skill", "unclassified-skill"],
        "available_tools": ["view", "local-helper", "mcp:knowledge-lookup"],
        "excluded_tools": ["write", "mcp:knowledge-write"],
        "request_extensions": False,
    }
    if tool_search is not None:
        expected["tool_search"] = tool_search
    assert actual == expected, "resume must project only resource kwargs, before its RPC"
    inspect.signature(_SDKClient.resume_session).bind(None, **actual)
    r.discover.assert_called_once()
    r.load_policy.assert_called_once()
    r.resolve.assert_called_once()
    assert r.resolve.call_args.kwargs["workflow_id"] == "ard"
    assert tuple(r.resolve.call_args.kwargs["required_skills"]) == r.required
    r.restrict.assert_called_once()
    r.build.assert_called_once()
    route = r.apply.await_args.kwargs["route"]
    assert route == ResourceRoute(
        enabled_mcp_servers=("knowledge",), disabled_mcp_servers=tuple(expected["disabled_mcp_servers"]),
        enabled_skills=r.required, disabled_skills=tuple(expected["disabled_skills"]),
        mcp_tool_allowlists={"knowledge": ("lookup",), "other-knowledge": ("lookup",)},
        required_mcp_servers=("knowledge",), required_skills=r.required,
        available_tools=tuple(expected["available_tools"]), excluded_tools=tuple(expected["excluded_tools"]),
    )
    assert r.build.call_args.kwargs["route"] is route
    assert [entry.args[0].server_name for entry in r.rpc.mcp.list_tools.await_args_list] == ["knowledge"]
    assert [name for name, _args, _timeout in r.rpc_calls] == [
        "rpc.skills", "rpc.init", "rpc.list", "rpc.tools", "rpc.options", "rpc.metadata",
    ]
    r.rpc.options.update.assert_awaited_once()
    assert r.options == original_options
    assert r.runner.config.available_tools[-1] == "mcp:other-knowledge-lookup"
    assert r.trace.create_calls == []
    assert _phase_session_commit_index(r.trace, "saved-main-session") < _event_index(r.trace, "sdk.resume")
    assert _event_index(r.trace, "rpc.options") < _event_index(r.trace, "sdk.send")
    assert _event_index(r.trace, "rpc.metadata") < _event_index(r.trace, "sdk.send")
    assert all(row["phase"] == "main" and row["session_id"] == "saved-main-session" for row in r.trace.transitions)
    assert len(r.handler.call_args_list) == 1 and r.handler.call_args.args[1] == "1"


@pytest.mark.parametrize("kind", ["mcp", "skill"])
def test_resume_required_caller_disabled_collision_stops_before_rpc(routed_resume, kind):
    r = routed_resume
    key, name = ("disabled_mcp_servers", "knowledge") if kind == "mcp" else ("disabled_skills", r.required[0])
    r.options[key] = [name]

    assert r.run() is False
    assert "disabled by the caller" in str(r.error.call_args_list)
    assert r.trace.resume_calls == r.trace.create_calls == r.trace.send_prompts == []
    r.apply.assert_not_awaited()
    assert r.rpc_calls == []
    assert r.runtime.store.step["session_id"] == "saved-main-session"


@pytest.mark.parametrize("flags, delay, attribute", [
    ((True, False), 0, None), ((False, True), 0, None),
    ((True, False), 0.01, None), ((False, True), 0.01, None),
    ((False, False), 0, "already_in_use"), ((False, False), 0, "session_was_active"),
], ids=["in-use-event", "active-event", "delayed-in-use", "delayed-active", "in-use-resident", "active-resident"])
def test_routed_resume_active_guard_precedes_apply_and_send(routed_resume, flags, delay, attribute):
    r = routed_resume
    r.client.resume_flags = flags
    r.client.resume_event_delay = delay
    if attribute:
        setattr(r.client.resumed_session, attribute, True)

    assert r.run() is False
    assert len(r.trace.resume_calls) == 1 and r.trace.resume_handler_present == [True]
    r.apply.assert_not_awaited()
    assert r.rpc_calls == r.trace.create_calls == r.trace.send_prompts == []
    assert r.client.resumed_session.disconnect_calls == 1 and r.client.stop_calls == 1


def test_resume_apply_inherits_the_original_resume_deadline(routed_resume):
    r = routed_resume
    assert r.module._RUNNER_RESUME_EVENT_TIMEOUT_SECONDS == 60.0
    r.client.resume_event_delay = 0.01

    assert r.run() is True
    r.apply.assert_awaited_once()
    assert r.apply.await_args.kwargs.get("deadline") == r.deadlines[0]
    assert len(r.deadlines) >= 3 and len(set(r.deadlines)) == 1
    assert all(0 < timeout < 60.0 for _name, _args, timeout in r.rpc_calls)


def test_resume_deadline_starts_after_slow_resource_discovery(routed_resume, monkeypatch):
    r = routed_resume
    monkeypatch.setattr(r.module, "_RUNNER_RESUME_EVENT_TIMEOUT_SECONDS", 0.2)

    async def slow_discovery(**_kwargs):
        await asyncio.sleep(0.3)
        return r.snapshot

    r.discover.side_effect = slow_discovery
    r.client.resume_event_delay = 0.01

    assert r.run() is True
    assert r.client.resumed_session is not None
    assert r.trace.create_calls == []


def test_resume_expired_deadline_never_creates_an_unawaited_rpc_coroutine(
    routed_resume, monkeypatch, recwarn
):
    r = routed_resume
    monkeypatch.setattr(r.module, "_RUNNER_RESUME_EVENT_TIMEOUT_SECONDS", 0.0)

    assert r.run() is False
    assert not [w for w in recwarn.list if "was never awaited" in str(w.message)]
    assert r.trace.send_prompts == r.trace.create_calls == []

def test_resume_hung_routing_is_cancelled_within_remaining_budget(routed_resume, monkeypatch):
    r = routed_resume
    monkeypatch.setattr(r.module, "_RUNNER_RESUME_EVENT_TIMEOUT_SECONDS", 0.05)
    cancelled = []

    async def hang(*, timeout):
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.append(timeout)
            raise

    r.rpc.tools.initialize_and_validate.side_effect = hang
    # A test-only safety bound catches an unbounded product apply; it is not the product deadline.
    assert r.run(timeout=0.5) is False
    assert len(cancelled) == 1 and 0 < cancelled[0] <= 0.05
    r.rpc.mcp.disable.assert_not_awaited()
    r.rpc.options.update.assert_not_awaited()
    assert r.trace.send_prompts == r.trace.create_calls == []
    assert r.client.resumed_session.disconnect_calls >= 1 and r.client.stop_calls == 1


def test_resume_external_cancellation_propagates_after_shared_cleanup(routed_resume):
    r = routed_resume

    async def scenario():
        entered = asyncio.Event()

        async def hang(*, timeout):
            entered.set()
            await asyncio.Future()

        r.rpc.tools.initialize_and_validate.side_effect = hang
        with patch.object(socket.socket, "connect", r.runtime.network_guard), patch.object(socket.socket, "connect_ex", r.runtime.network_guard):
            task = asyncio.create_task(r.runner.run_step("1", "T13 cancel", _MAIN_PROMPT, workflow_id="ard"))
            try:
                await asyncio.wait_for(entered.wait(), timeout=1)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert r.client.resumed_session.disconnect_calls >= 1 and r.client.stop_calls == 1
    assert r.trace.send_prompts == r.trace.create_calls == []
    r.rpc.mcp.disable.assert_not_awaited()
    r.rpc.options.update.assert_not_awaited()


def test_unrouted_resume_preserves_explicit_false_and_empty_resource_options(routed_resume):
    r = routed_resume
    r.options.update(
        tools=[], enable_config_discovery=False, enable_skills=False, skill_directories=[],
        disabled_skills=[], disabled_mcp_servers=[], available_tools=[], excluded_tools=[],
        request_extensions=False,
    )

    assert r.runtime.run() is True
    actual = r.trace.resume_calls[0]
    assert actual == {
        "session_id": "saved-main-session", "on_event": actual["on_event"],
        "on_permission_request": r.base_options["on_permission_request"],
        "continue_pending_work": False, **r.options,
    }
    r.discover.assert_not_called()
    r.apply.assert_not_awaited()


# SDK 1.0.11 sends session.destroy on disconnect; 1.0.13 and later send session.detach.
_SDK_DISCONNECT_METHODS = ("session.destroy", "session.detach")


@pytest.fixture(params=["copilot-cli", "empty"])
def sdk_resume_wire(routed_resume, request, monkeypatch):
    """SDK 1.0.11 public resume/typed RPCs, without start or runtime resolution."""
    r = routed_resume
    r.snapshot = replace(r.snapshot, mcp_servers=(), skills=r.snapshot.skills[:len(r.required)])
    r.policy = replace(r.policy, required_mcp_servers_by_skill={})
    r.runner.config.available_tools = ["view"]  # Also required by SDK empty mode.
    r.options["excluded_tools"] = []
    r.wire_calls = []
    r.persisted_disabled = set()
    r.missing_skills = set()
    r.mode = request.param
    blocked = Mock(side_effect=r.runtime.network_guard)
    for name in ("start", "_resolve_runtime_entrypoint", "_start_cli_server", "_start_inprocess_ffi", "_connect_to_server"):
        monkeypatch.setattr(_SDKClient, name, blocked)
    with patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked):
        sdk = _SDKClient(connection=_SDKConnection.for_uri("localhost:54321"), mode=r.mode)

    async def rpc(method, params, **kwargs):
        r.wire_calls.append((method, dict(params), dict(kwargs)))
        r.trace.events.append((method, dict(params)))
        if method == "session.resume":
            r.resume_payload = dict(params)
            if "disabledSkills" in params:
                r.persisted_disabled = set(params["disabledSkills"])
            session = sdk._sessions[params["sessionId"]]
            assert len(session._event_handlers) == 1, "SDK must register the callback before RPC"
            session._dispatch_event(SimpleNamespace(
                type=SessionEventType.SESSION_RESUME,
                data=SessionResumeData(
                    event_count=0, resume_time=datetime.now(timezone.utc),
                    already_in_use=False, session_was_active=False,
                ),
            ))
            assert r.handler.call_count == 1, "resume event must be observed before RPC returns"
            monkeypatch.setattr(session, "send_and_wait", r.client.resumed_session.send_and_wait)
            return {"sessionId": params["sessionId"]}
        if method == "session.skills.list":
            assert params == {"sessionId": "saved-main-session"}
            assert set(kwargs) == {"timeout"} and 0 < kwargs["timeout"] <= 60.0
            return {"skills": [
                {
                    "name": name, "description": "offline required Skill", "source": "project",
                    "userInvocable": True,
                    "enabled": name not in r.persisted_disabled and r.resume_payload.get("enableSkills", r.mode != "empty"),
                }
                for name in r.required if name not in r.missing_skills
            ]}
        if method == "session.options.update":
            return {"success": True}
        if method in _SDK_DISCONNECT_METHODS:
            assert params == {"sessionId": "saved-main-session"}
            return {"success": True}
        raise AssertionError(f"unexpected offline SDK request: {method}")

    transport = SimpleNamespace(request=AsyncMock(side_effect=rpc))
    sdk._client = transport

    async def resume(session_id, **kwargs):
        inspect.signature(_SDKClient.resume_session).bind(sdk, session_id, **kwargs)
        r.trace.resume_calls.append({"session_id": session_id, **kwargs})
        return await sdk.resume_session(session_id, **kwargs)

    monkeypatch.setattr(r.client, "resume_session", resume)
    yield r
    blocked.assert_not_called()
    assert not any(method in ("session.create", "session.delete", "connect") for method, _params, _kwargs in r.wire_calls)


@pytest.mark.parametrize("required_state", ["enabled", "persisted-disabled", "missing"])
def test_sdk_resume_empty_disabled_wire_still_checks_required_skills(sdk_resume_wire, required_state):
    r = sdk_resume_wire
    if required_state == "persisted-disabled":
        r.persisted_disabled.add(r.required[0])
    elif required_state == "missing":
        r.missing_skills.add(r.required[0])

    assert r.run() is (required_state == "enabled")
    assert len(r.trace.resume_calls) == 1
    actual = r.trace.resume_calls[0]
    assert actual == {
        "session_id": "saved-main-session", "on_event": actual["on_event"],
        "on_permission_request": r.base_options["on_permission_request"],
        "continue_pending_work": False, "enable_config_discovery": True, "enable_skills": True,
        "skill_directories": r.base_options["skill_directories"], "disabled_mcp_servers": ["github-mcp-server"],
        "disabled_skills": [], "available_tools": ["view"], "excluded_tools": [],
        "request_extensions": False,
    }
    payload = r.resume_payload
    assert payload["disabledMcpServers"] == ["github-mcp-server"]
    assert "disabledSkills" not in payload, "SDK 1.0.11 omits an empty disabled_skills list"
    assert payload["enableSkills"] is payload["enableConfigDiscovery"] is True
    assert payload["continuePendingWork"] is False
    assert payload["skillDirectories"] == r.base_options["skill_directories"]
    assert payload["availableTools"] == ["view"] and payload["excludedTools"] == []
    assert not {"model", "provider", "streaming", "contextTier", "infiniteSessions", "toolSearch", "mcpServers"} & payload.keys()
    methods = [method for method, _params, _kwargs in r.wire_calls]
    disconnects = sum(method in _SDK_DISCONNECT_METHODS for method in methods)
    assert methods.count("session.resume") == methods.count("session.skills.list") == disconnects == 1
    assert "session.tools.initializeAndValidate" not in methods
    filter_updates = [params for method, params, _kwargs in r.wire_calls if method == "session.options.update" and "availableTools" in params]
    if required_state == "enabled":
        assert filter_updates == [{"sessionId": "saved-main-session", "availableTools": ["view"]}]
        assert _event_index(r.trace, "session.skills.list") < _event_index(r.trace, "sdk.send")
        assert len(r.trace.send_prompts) == 1
    else:
        assert filter_updates == r.trace.send_prompts == []
        assert "required Skill runtime is unavailable" in str(r.error.call_args_list)
        assert r.required[0] in str(r.error.call_args_list)
    if required_state == "persisted-disabled":
        assert r.persisted_disabled == {r.required[0]}, "omission cannot reset persisted Skill state"
    assert r.trace.create_calls == [] and r.client.stop_calls == 1
    assert all(row["phase"] == "main" and row["session_id"] == "saved-main-session" for row in r.trace.transitions)


def test_sdk_resume_nonempty_caller_disables_are_emitted(sdk_resume_wire):
    r = sdk_resume_wire
    r.options.update(disabled_mcp_servers=["caller-off", "caller-off"], disabled_skills=["old-optional", "old-optional"])

    assert r.run() is True
    assert r.resume_payload["disabledMcpServers"] == ["caller-off", "github-mcp-server"]
    assert r.resume_payload["disabledSkills"] == ["old-optional"]
    assert r.apply.await_args.kwargs["route"].disabled_mcp_servers == ("caller-off", "github-mcp-server")
    assert r.apply.await_args.kwargs["route"].disabled_skills == ("old-optional",)
    assert sum(method == "session.skills.list" for method, _params, _kwargs in r.wire_calls) == 1


def test_sdk_generated_routing_requests_use_public_timeout_signatures():
    """Characterize generated serialization, not hand-written raw RPC calls."""
    transport = SimpleNamespace(request=AsyncMock(side_effect=[
        {"skills": []}, {}, {"servers": []}, {"tools": [{"name": "lookup"}]}, {"success": True}, {},
    ]))
    session = _SDKSession("offline-generated", transport)

    async def scenario():
        await session.rpc.skills.list(timeout=0.25)
        await session.rpc.tools.initialize_and_validate(timeout=0.25)
        await session.rpc.mcp.list(timeout=0.25)
        await session.rpc.mcp.list_tools(MCPListToolsRequest(server_name="knowledge"), timeout=0.25)
        result = await session.rpc.options.update(SessionUpdateOptionsParams(available_tools=[], excluded_tools=["write"]), timeout=0.25)
        assert result.success is True
        await session.rpc.mcp.disable(MCPDisableRequest(server_name="other-knowledge"), timeout=0.25)

    asyncio.run(scenario())
    base = {"sessionId": "offline-generated"}
    assert transport.request.await_args_list == [
        call("session.skills.list", base, timeout=0.25),
        call("session.tools.initializeAndValidate", base, timeout=0.25),
        call("session.mcp.list", base, timeout=0.25),
        call("session.mcp.listTools", {**base, "serverName": "knowledge"}, timeout=0.25),
        call("session.options.update", {**base, "availableTools": [], "excludedTools": ["write"]}, timeout=0.25),
        call("session.mcp.disable", {**base, "serverName": "other-knowledge"}, timeout=0.25),
    ]