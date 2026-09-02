"""FR-CLI-90 — StepRunner durable SDK resume の fake-only RED 契約。

本ファイルは Copilot SDK、Azure、GitHub、ネットワークを一切呼ばない。durable
store と SDK client/session を fake に置換し、公開 ``run_step()`` の観測可能な
順序と fail-closed 動作を固定する。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import importlib
import json
import socket
import sys
import types
import unittest.mock
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Callable, Iterator, Optional

import pytest

from copilot.generated.session_events import SessionEventType, SessionResumeData

from hve.config import SDKConfig
from hve.console import Console


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

    def run(self, step_id: str = "1") -> bool:
        async def _scenario() -> bool:
            # Windows の asyncio は event loop 作成・破棄時に内部 socketpair を
            # 使用する。loop 作成後から Runner 完了までだけ connect を禁止する。
            with unittest.mock.patch.object(
                socket.socket,
                "connect",
                self.network_guard,
            ):
                return await self.runner.run_step(
                    step_id,
                    "durable runner test",
                    _MAIN_PROMPT,
                    workflow_id=None,
                )

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
            auto_self_improve=False,
            self_improve_skip=True,
        )
        context = SimpleNamespace(
            execution_id=store.execution_id,
            instance_id=store.instance_id,
            expected_state_version=store.state_version,
            recovery_action=action,
            lease_owner=store.token.owner,
            lease_generation=store.token.generation,
            split_fork_enabled=False,
            split_fork_depth=0,
            split_fork_max_depth=3,
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

    def test_disabled_split_fork_preserves_main_checkpoint_across_repeated_steps(
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

    def test_enabled_legacy_split_fork_records_its_phase(
        self,
        runtime_factory: Callable[..., _Runtime],
    ) -> None:
        runtime = runtime_factory(action=None, phase="main", session_id=None)
        runtime.runner._orchestrator_ctx.split_fork_enabled = True

        assert runtime.run() is True

        phases = [transition["phase"] for transition in runtime.trace.transitions]
        assert "main" in phases
        assert "split-fork" in phases

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
    ["pre-qa", "review", "self-improve"],
    ids=["pre-qa", "review", "self-improve"],
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
    assert runtime.trace.send_prompts == [_RECOVERY_PROMPT_SENTINEL]
    assert _MAIN_PROMPT not in runtime.trace.send_prompts[0]
    assert _RECOVERY_PROMPT_SENTINEL not in repr(runtime.trace.transitions)
    assert runtime.trace.create_calls == []