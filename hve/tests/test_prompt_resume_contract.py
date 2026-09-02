"""FR-PROMPT-11 / FR-LOCAL-SURFACE-02 — Prompt durable resume RED contracts.

The Prompt surface must preserve request v1, register an approved normal plan as one
ordered durable execution, and delegate resume planning/CAS to the shared service.
All runtime collaborators in this file are fakes; no network or real durable store is
opened.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import re
import socket
import subprocess
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

import pytest


_SKILL = Path(".github/skills/hve-prompt-edition/SKILL.md")
_HEAD_COMMIT = "a" * 40
_EXECUTION_ID = "prompt-execution-001"
_ACTIVE_STATE: "_FakeState | None" = None


class _DurableStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class _LeaseToken:
    execution_id: str
    instance_id: str
    owner: str
    generation: int
    state_version: int


@dataclass(frozen=True)
class _WorkflowDescriptor:
    instance_id: str
    workflow_id: str
    ordinal: int
    mode: str = "standard"
    argv: tuple[str, ...] = ()
    missing_replay_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ResumePlan:
    execution_id: str
    instance_id: str
    workflow_id: str
    action: str
    expected_state_version: int
    risk_reasons: tuple[str, ...]
    missing_replay_keys: tuple[str, ...]
    argv: tuple[str, ...]
    resume_plan_hash: str


@dataclass
class _FakeState:
    execution_id: str = _EXECUTION_ID
    runner_codes: list[int] = field(default_factory=list)
    runner_calls: list[tuple[list[str], dict[str, Any]]] = field(default_factory=list)
    store_instances: list[Any] = field(default_factory=list)
    service_instances: list[Any] = field(default_factory=list)
    register_calls: list[dict[str, Any]] = field(default_factory=list)
    build_plan_calls: list[dict[str, Any]] = field(default_factory=list)
    acquire_calls: list[tuple[Any, str]] = field(default_factory=list)
    events: list[tuple[str, Any]] = field(default_factory=list)
    register_error: BaseException | None = None
    network_attempts: int = 0


def _state() -> _FakeState:
    assert _ACTIVE_STATE is not None, "fake runtime is not active"
    return _ACTIVE_STATE


class _FakeRunStateStore:
    def __init__(self, path: "str | Path | None" = None):
        self.path = path
        self.closed = False
        _state().store_instances.append(self)

    def __enter__(self) -> "_FakeRunStateStore":
        _state().events.append(("store-enter", self.path))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.closed = True
        _state().events.append(("store-exit", self.path))

    def quick_check(self) -> bool:
        return True


class _FakeResumeService:
    def __init__(self, store: Any, repo_root: "str | Path"):
        self.store = store
        self.repo_root = Path(repo_root)
        _state().service_instances.append(self)
        _state().events.append(("service", self.repo_root))

    def new_execution_id(self) -> str:
        return _state().execution_id

    def sanitize_argv(
        self, argv: Sequence[str]
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return tuple(argv), ()

    def register_execution(
        self,
        surface: str,
        descriptors: Sequence[Any],
        *,
        execution_id: str | None = None,
        checkpoint_head: str | None = None,
    ) -> str:
        state = _state()
        descriptor_tuple = tuple(descriptors)
        resolved_id = execution_id or state.execution_id
        call = {
            "surface": surface,
            "descriptors": descriptor_tuple,
            "execution_id": resolved_id,
            "checkpoint_head": checkpoint_head,
        }
        state.register_calls.append(call)
        state.events.append(("register", call))
        if state.register_error is not None:
            raise state.register_error
        return resolved_id

    def list_candidates(self) -> tuple[Any, ...]:
        return ()

    def build_plan(
        self,
        execution_id: str,
        *,
        action: str | None = None,
        replay_values: dict[str, str] | None = None,
        current_head: str | None = None,
    ) -> _ResumePlan:
        call = {
            "execution_id": execution_id,
            "action": action,
            "replay_values": replay_values,
            "current_head": current_head,
        }
        _state().build_plan_calls.append(call)
        payload = json.dumps(call, sort_keys=True, default=str).encode("utf-8")
        return _ResumePlan(
            execution_id=execution_id,
            instance_id="aas#1",
            workflow_id="aas",
            action=action or "restart-step",
            expected_state_version=7,
            risk_reasons=(),
            missing_replay_keys=(),
            argv=("orchestrate", "--workflow", "aas"),
            resume_plan_hash=hashlib.sha256(payload).hexdigest(),
        )

    def acquire(self, plan: _ResumePlan, owner: str) -> _LeaseToken:
        _state().acquire_calls.append((plan, owner))
        _state().events.append(("acquire", plan.resume_plan_hash))
        return _LeaseToken(
            execution_id=plan.execution_id,
            instance_id=plan.instance_id,
            owner=owner,
            generation=1,
            state_version=plan.expected_state_version,
        )


class _FakeRunner:
    def __call__(self, argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        state = _state()
        copied = list(argv)
        state.runner_calls.append((copied, dict(kwargs)))
        state.events.append(("child", copied))
        code = state.runner_codes.pop(0) if state.runner_codes else 0
        return subprocess.CompletedProcess(copied, code)


@dataclass(frozen=True)
class _PromptRuntime:
    state: _FakeState
    hve_main: Any
    prompt_execution: Any
    settings_store: Any


def _canonical_json(value: Any) -> str:
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _hash_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _install_fake_modules(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state_module = types.ModuleType("hve.run_state_store")
    state_module.SCHEMA_VERSION = 1
    state_module.HEARTBEAT_INTERVAL_SECONDS = 5.0
    state_module.LEASE_TTL_SECONDS = 20.0
    state_module.BUSY_TIMEOUT_SECONDS = 1.0
    state_module.DurableStateError = _DurableStateError
    state_module.LeaseToken = _LeaseToken
    state_module.RunStateStore = _FakeRunStateStore
    state_module.default_state_path = lambda: tmp_path / "fake-run-state.sqlite3"
    state_module.compute_repo_key = lambda root: hashlib.sha256(
        str(Path(root)).encode("utf-8")
    ).hexdigest()

    service_module = types.ModuleType("hve.resume_service")
    service_module.WorkflowDescriptor = _WorkflowDescriptor
    service_module.ResumePlan = _ResumePlan
    service_module.ResumeService = _FakeResumeService
    service_module.canonical_json = _canonical_json
    service_module.compute_launch_plan_hash = _hash_value
    service_module.compute_resume_plan_hash = _hash_value

    monkeypatch.setitem(sys.modules, "hve.run_state_store", state_module)
    monkeypatch.setitem(sys.modules, "hve.resume_service", service_module)

    hve_package = importlib.import_module("hve")
    monkeypatch.setattr(hve_package, "run_state_store", state_module, raising=False)
    monkeypatch.setattr(hve_package, "resume_service", service_module, raising=False)


@pytest.fixture()
def prompt_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> "Iterator[_PromptRuntime]":
    """Install fake runner/store/service seams and fail on every network attempt."""
    global _ACTIVE_STATE

    # Import the real modules before replacing dependency modules so cached aliases are
    # restored cleanly after each test, including after the production modules exist.
    prompt_execution = importlib.import_module("hve.prompt_execution")
    hve_main = importlib.import_module("hve.__main__")
    settings_store = importlib.import_module("hve.gui.settings_store")

    state = _FakeState()
    _ACTIVE_STATE = state
    _install_fake_modules(monkeypatch, tmp_path)

    for module in (prompt_execution, hve_main):
        monkeypatch.setattr(module, "RunStateStore", _FakeRunStateStore, raising=False)
        monkeypatch.setattr(module, "ResumeService", _FakeResumeService, raising=False)
        monkeypatch.setattr(module, "WorkflowDescriptor", _WorkflowDescriptor, raising=False)
        monkeypatch.setattr(module, "DurableStateError", _DurableStateError, raising=False)

    settings_path = tmp_path / ".settings.txt"
    monkeypatch.setattr(settings_store, "_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(settings_store, "settings_path", lambda: settings_path)
    monkeypatch.setattr(prompt_execution, "resolve_head_commit", lambda _root: _HEAD_COMMIT)
    monkeypatch.setattr(prompt_execution, "_default_runner", _FakeRunner())
    monkeypatch.setattr(
        prompt_execution,
        "_verify_durable_child_completion",
        lambda _execution_id, _instance_id: True,
    )

    def deny_network(*_args: Any, **_kwargs: Any) -> Any:
        state.network_attempts += 1
        raise AssertionError("Prompt durable resume contract tests must not use the network")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    monkeypatch.setattr(socket.socket, "connect", deny_network)

    try:
        yield _PromptRuntime(state, hve_main, prompt_execution, settings_store)
    finally:
        _ACTIVE_STATE = None


def _write_request(tmp_path: Path, workflows: list[dict[str, Any]] | None = None) -> Path:
    payload = {
        "schema_version": 1,
        "goal": "耐久実行の契約を確認する",
        "workflows": workflows or [{"workflow_id": "aas"}],
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _plan_hash(runtime: _PromptRuntime, request_path: Path) -> str:
    prompt_request = importlib.import_module("hve.prompt_request")
    request = prompt_request.load_request(request_path)
    plan = runtime.prompt_execution.build_execution_plan(
        request,
        settings=runtime.settings_store.load(),
        repo_root=Path.cwd(),
        head_commit=_HEAD_COMMIT,
    )
    return plan.sha256


def _run_approved(
    runtime: _PromptRuntime,
    request_path: Path,
    *,
    codes: Sequence[int] = (),
) -> int:
    runtime.state.runner_codes[:] = list(codes)
    return runtime.hve_main.main(
        [
            "prompt",
            "run",
            "--request",
            str(request_path),
            "--expected-sha256",
            _plan_hash(runtime, request_path),
        ]
    )


class TestRequestV1Compatibility:
    def test_resume_controls_do_not_change_request_v1(self):
        prompt_request = importlib.import_module("hve.prompt_request")
        assert prompt_request.SCHEMA_VERSION == 1

        parsed = prompt_request.parse_request(
            {
                "schema_version": 1,
                "goal": "既存 request",
                "workflows": [{"workflow_id": "aas"}],
            }
        )
        assert [item.name for item in dataclasses.fields(parsed)] == [
            "schema_version",
            "goal",
            "workflows",
            "settings_overrides",
        ]

        with pytest.raises(prompt_request.PromptRequestError):
            prompt_request.parse_request(
                {
                    "schema_version": 1,
                    "goal": "resume controls must stay outside request v1",
                    "workflows": [{"workflow_id": "aas"}],
                    "execution_id": "must-not-be-added",
                    "resume_plan_hash": "must-not-be-added",
                }
            )


class TestNormalPromptDurableRegistration:
    def test_plan_only_does_not_register_a_durable_execution(
        self, tmp_path: Path, prompt_runtime: _PromptRuntime
    ):
        request = _write_request(
            tmp_path,
            [{"workflow_id": "aad-web"}, {"workflow_id": "aas"}],
        )
        prompt_runtime.state.runner_codes[:] = [0, 0]

        code = prompt_runtime.hve_main.main(
            ["prompt", "plan", "--request", str(request)]
        )

        assert code == 0
        assert prompt_runtime.state.register_calls == []
        assert len(prompt_runtime.state.runner_calls) == 2
        assert all("--dry-run" in argv for argv, _ in prompt_runtime.state.runner_calls)
        assert prompt_runtime.state.network_attempts == 0

    def test_stale_normal_sha_starts_no_registration_or_child(
        self, tmp_path: Path, prompt_runtime: _PromptRuntime
    ):
        request = _write_request(tmp_path)

        code = prompt_runtime.hve_main.main(
            [
                "prompt",
                "run",
                "--request",
                str(request),
                "--expected-sha256",
                "b" * 64,
            ]
        )

        assert code != 0
        assert prompt_runtime.state.register_calls == []
        assert prompt_runtime.state.runner_calls == []
        assert prompt_runtime.state.network_attempts == 0

    def test_matching_sha_registers_all_ordered_instances_once_before_first_child(
        self, tmp_path: Path, prompt_runtime: _PromptRuntime
    ):
        request = _write_request(
            tmp_path,
            [{"workflow_id": "aad-web"}, {"workflow_id": "aas"}],
        )
        original_request = request.read_bytes()

        code = _run_approved(prompt_runtime, request, codes=[0, 0])

        assert code == 0
        assert len(prompt_runtime.state.register_calls) == 1, (
            "approved Prompt run must register every Workflow in one service call"
        )
        call = prompt_runtime.state.register_calls[0]
        descriptors = call["descriptors"]
        assert call["surface"] == "prompt"
        assert call["checkpoint_head"] == _HEAD_COMMIT
        assert [item.workflow_id for item in descriptors] == ["aas", "aad-web"]
        assert len({item.instance_id for item in descriptors}) == len(descriptors)
        assert [item.ordinal for item in descriptors] == [0, 1]
        assert [item.workflow_id for item in sorted(descriptors, key=lambda item: item.ordinal)] == [
            "aas",
            "aad-web",
        ]

        event_names = [name for name, _payload in prompt_runtime.state.events]
        assert event_names.count("register") == 1
        assert event_names.index("register") < event_names.index("child")
        assert request.read_bytes() == original_request
        assert prompt_runtime.state.network_attempts == 0

    def test_all_children_share_execution_id_and_have_registered_unique_instance_ids(
        self, tmp_path: Path, prompt_runtime: _PromptRuntime
    ):
        request = _write_request(
            tmp_path,
            [{"workflow_id": "aad-web"}, {"workflow_id": "aas"}],
        )

        assert _run_approved(prompt_runtime, request, codes=[0, 0]) == 0
        assert len(prompt_runtime.state.runner_calls) == 2

        parser = prompt_runtime.hve_main._build_parser()
        child_args = [
            parser.parse_args(argv[3:])
            for argv, _kwargs in prompt_runtime.state.runner_calls
        ]
        execution_ids = [getattr(args, "_execution_id", None) for args in child_args]
        instance_ids = [getattr(args, "_instance_id", None) for args in child_args]
        assert execution_ids == [_EXECUTION_ID, _EXECUTION_ID]
        assert None not in instance_ids
        assert len(set(instance_ids)) == len(instance_ids)

        assert len(prompt_runtime.state.register_calls) == 1
        descriptors = prompt_runtime.state.register_calls[0]["descriptors"]
        registered = {item.workflow_id: item.instance_id for item in descriptors}
        assert {
            args.workflow: args._instance_id for args in child_args
        } == registered
        assert prompt_runtime.state.network_attempts == 0

    def test_durable_registration_failure_starts_no_child(
        self, tmp_path: Path, prompt_runtime: _PromptRuntime
    ):
        request = _write_request(tmp_path)
        prompt_runtime.state.register_error = _DurableStateError("simulated write failure")

        code = _run_approved(prompt_runtime, request, codes=[0])

        assert code != 0
        assert prompt_runtime.state.runner_calls == []
        assert prompt_runtime.state.network_attempts == 0

    def test_existing_fail_fast_stops_after_first_failed_child(
        self, tmp_path: Path, prompt_runtime: _PromptRuntime
    ):
        request = _write_request(
            tmp_path,
            [{"workflow_id": "aad-web"}, {"workflow_id": "aas"}],
        )

        code = _run_approved(prompt_runtime, request, codes=[9, 0])

        assert code == 9
        assert len(prompt_runtime.state.runner_calls) == 1
        assert prompt_runtime.state.network_attempts == 0



def _durable_resume_skill_contract() -> str:
    assert _SKILL.exists(), f"missing Prompt Edition Skill: {_SKILL}"
    text = _SKILL.read_text(encoding="utf-8")
    heading = re.search(r"(?m)^## [^\n]*FR-PROMPT-11[^\n]*$", text)
    assert heading is not None, (
        "Prompt Edition Skill has no bounded FR-PROMPT-11 controller section"
    )
    next_heading = re.search(r"(?m)^## ", text[heading.end() :])
    end = (
        len(text)
        if next_heading is None
        else heading.end() + next_heading.start()
    )
    return text[heading.start() : end]


class TestPromptResumeControllerSkill:
    def test_resume_plan_is_rebuilt_and_cas_acquired_only_after_explicit_approval(self):
        body = _durable_resume_skill_contract()
        for token in (
            "ResumeService",
            "build_plan",
            "resume_plan_hash",
            "expected_state_version",
            "acquire",
            "明示承認",
            "再計算",
            "CAS",
            "stale",
            "再提示",
            "再承認",
            "最初の失敗",
        ):
            assert token in body, f"durable resume controller contract is missing {token!r}"
        assert "ordinal" in body or "順序" in body

        first_plan = body.index("build_plan")
        presentation = body.index("提示", first_plan)
        approval = body.index("明示承認", presentation)
        rebuilt_plan = body.index("build_plan", approval)
        recalculated_hash = body.index("resume_plan_hash", rebuilt_plan)
        acquire = body.index("acquire", recalculated_hash)
        assert first_plan < presentation < approval < rebuilt_plan < recalculated_hash < acquire
        assert re.search(
            r"stale.*?(?:child|子プロセス).*?(?:0\s*件|起動しない|起動せず).*?再提示.*?再承認",
            body,
            re.DOTALL,
        )

    def test_each_ordered_resume_plan_requires_separate_approval(self):
        body = _durable_resume_skill_contract()
        assert "後続 `ResumePlan`" in body
        assert "別の明示承認" in body
        assert "先行planのhashを後続planへ流用してはならない" in body
        assert "instance完了時に平文値を破棄" in body

    def test_resume_is_natural_language_only_and_keeps_request_v1_unchanged(self):
        body = _durable_resume_skill_contract()
        assert re.search(r"request v1.*?(?:変更しない|不変)", body, re.DOTALL)
        assert "command" in body or "コマンド" in body
        assert "request path" in body
        assert "execution hash" in body or "resume_plan_hash" in body
        assert re.search(
            r"利用者.*?(?:command|コマンド).*?request path.*?"
            r"(?:execution hash|resume_plan_hash).*?(?:求めない|求めてはならない)",
            body,
            re.DOTALL,
        )
