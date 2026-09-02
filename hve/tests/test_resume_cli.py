"""Durable resume CLI RED contracts.

Traceability: FR-CLI-90, FR-STATE-05, NFR-CONC-02, NFR-SEC-01.
All durable collaborators and child processes are fakes.  The suite never opens
an actual state database, authenticates, starts an SDK session, or uses network.
"""

from __future__ import annotations

import argparse
import builtins
import dataclasses
import hashlib
import importlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence

import pytest
import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARITY_FIXTURE = _REPO_ROOT / "hve" / "tests" / "fixtures" / "option_parity_matrix.yaml"
_HEAD = "a" * 40
_ACTIVE_TRACE: "_Trace | None" = None


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
    action: str | None
    expected_state_version: int
    risk_reasons: tuple[str, ...]
    missing_replay_keys: tuple[str, ...]
    argv: tuple[str, ...]
    resume_plan_hash: str


class _Record(dict[str, Any]):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - diagnostics only
            raise AttributeError(name) from exc


@dataclass
class _Trace:
    candidates: list[_Record] = field(default_factory=list)
    instance_rows: list[_Record] = field(default_factory=list)
    plans: list[_ResumePlan] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    service_instances: list[Any] = field(default_factory=list)
    store_instances: list[Any] = field(default_factory=list)
    register_calls: list[dict[str, Any]] = field(default_factory=list)
    sanitize_calls: list[tuple[str, ...]] = field(default_factory=list)
    build_plan_calls: list[dict[str, Any]] = field(default_factory=list)
    acquire_calls: list[tuple[Any, str]] = field(default_factory=list)
    complete_reconciled_calls: list[tuple[Any, Any]] = field(default_factory=list)
    release_calls: list[Any] = field(default_factory=list)
    child_calls: list[tuple[list[str], dict[str, Any]]] = field(default_factory=list)
    workflow_calls: list[dict[str, Any]] = field(default_factory=list)
    external_calls: list[str] = field(default_factory=list)
    acquire_error: BaseException | None = None
    build_plan_error: BaseException | None = None
    register_error: BaseException | None = None
    child_returncode: int = 0
    child_returncodes: list[int] = field(default_factory=list)
    head_values: list[str] = field(default_factory=list)


def _trace() -> _Trace:
    assert _ACTIVE_TRACE is not None, "fake durable runtime is not active"
    return _ACTIVE_TRACE


class _FakeRunStateStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = path
        self.closed = False
        _trace().store_instances.append(self)

    def __enter__(self) -> "_FakeRunStateStore":
        _trace().events.append("store.enter")
        return self

    def __exit__(self, *_args: Any) -> None:
        self.closed = True
        _trace().events.append("store.exit")

    def close(self) -> None:
        self.closed = True
        _trace().events.append("store.close")

    def quick_check(self) -> bool:
        return True

    def get_execution(self, execution_id: str) -> _Record | None:
        return next(
            (item for item in _trace().candidates if item.execution_id == execution_id),
            None,
        )

    def get_instance(self, execution_id: str, instance_id: str) -> _Record:
        existing = next(
            (
                row
                for row in _trace().instance_rows
                if row.execution_id == execution_id
                and row.instance_id == instance_id
            ),
            None,
        )
        if existing is not None:
            return existing
        return _Record(
            execution_id=execution_id,
            instance_id=instance_id,
            workflow_id="aas",
            ordinal=0,
            status="pending",
            state_version=0,
        )

    def list_instances(self, execution_id: str) -> list[_Record]:
        return sorted(
            (
                row
                for row in _trace().instance_rows
                if row.execution_id == execution_id
            ),
            key=lambda row: row.ordinal,
        )

    def release_lease(self, token: Any) -> None:
        _trace().release_calls.append(token)
        _trace().events.append("lease.release")


class _FakeResumeService:
    def __init__(self, store: Any, repo_root: str | Path) -> None:
        self.store = store
        self.repo_root = Path(repo_root)
        _trace().service_instances.append(self)
        _trace().events.append("service.init")

    def new_execution_id(self) -> str:
        return "execution-new"

    def sanitize_argv(
        self, argv: Sequence[str]
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        values = tuple(str(value) for value in argv)
        _trace().sanitize_calls.append(values)
        return values, ()

    def register_execution(
        self,
        surface: str,
        descriptors: Sequence[Any],
        *,
        execution_id: str | None = None,
        checkpoint_head: str | None = None,
    ) -> str:
        trace = _trace()
        call = {
            "surface": surface,
            "descriptors": tuple(descriptors),
            "execution_id": execution_id or "execution-new",
            "checkpoint_head": checkpoint_head,
        }
        trace.register_calls.append(call)
        trace.events.append("register")
        if trace.register_error is not None:
            raise trace.register_error
        return str(call["execution_id"])

    def list_candidates(self) -> tuple[_Record, ...]:
        _trace().events.append("candidates")
        return tuple(_trace().candidates)

    def build_plan(
        self,
        execution_id: str,
        *,
        action: str | None = None,
        replay_values: dict[str, str] | None = None,
        current_head: str | None = None,
    ) -> _ResumePlan:
        trace = _trace()
        call = {
            "execution_id": execution_id,
            "action": action,
            "replay_values": replay_values,
            "current_head": current_head,
        }
        trace.build_plan_calls.append(call)
        trace.events.append("build-plan")
        if trace.build_plan_error is not None:
            raise trace.build_plan_error
        if not trace.plans:
            return _plan(execution_id=execution_id, action=action)
        index = min(len(trace.build_plan_calls) - 1, len(trace.plans) - 1)
        return trace.plans[index]

    def acquire(self, plan: _ResumePlan, owner: str) -> _LeaseToken:
        trace = _trace()
        trace.acquire_calls.append((plan, owner))
        trace.events.append("acquire")
        if trace.acquire_error is not None:
            raise trace.acquire_error
        return _LeaseToken(
            execution_id=plan.execution_id,
            instance_id=plan.instance_id,
            owner=owner,
            generation=1,
            state_version=plan.expected_state_version,
        )

    def complete_reconciled(
        self,
        plan: _ResumePlan,
        token: _LeaseToken,
    ) -> _LeaseToken:
        trace = _trace()
        trace.complete_reconciled_calls.append((plan, token))
        trace.events.append("reconciled.complete")
        if plan.argv:
            raise _DurableStateError("reconciled completion requires empty argv")
        current = next(
            row
            for row in trace.instance_rows
            if row.instance_id == plan.instance_id
        )
        current["status"] = "succeeded"
        current["state_version"] = int(current["state_version"]) + 1
        return dataclasses.replace(
            token,
            state_version=int(current["state_version"]),
        )


def _canonical_json(value: Any) -> str:
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _hash_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _candidate(
    execution_id: str,
    *,
    updated_at: str = "2026-08-28T00:00:00Z",
    status: str = "suspended",
    mode: str = "standard",
) -> _Record:
    return _Record(
        execution_id=execution_id,
        repo_key="repo-key",
        surface="cli",
        workflow_id="aas",
        status=status,
        mode=mode,
        created_at="2026-08-27T00:00:00Z",
        updated_at=updated_at,
        launch_plan_hash="b" * 64,
    )


def _plan(
    *,
    execution_id: str = "execution-1",
    instance_id: str = "aas#1",
    action: str | None = "restart-step",
    state_version: int = 7,
    risk_reasons: Sequence[str] = (),
    resume_hash: str = "c" * 64,
    argv: Sequence[str] = ("orchestrate", "--workflow", "aas"),
) -> _ResumePlan:
    return _ResumePlan(
        execution_id=execution_id,
        instance_id=instance_id,
        workflow_id="aas",
        action=action,
        expected_state_version=state_version,
        risk_reasons=tuple(risk_reasons),
        missing_replay_keys=(),
        argv=tuple(argv),
        resume_plan_hash=resume_hash,
    )


def _install_fake_durable_modules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    hve_main: Any,
) -> None:
    production_state_module = importlib.import_module("hve.run_state_store")
    production_service_module = importlib.import_module("hve.resume_service")
    state_module = types.ModuleType("hve.run_state_store")
    state_module.SCHEMA_VERSION = 1
    state_module.HEARTBEAT_INTERVAL_SECONDS = 5.0
    state_module.LEASE_TTL_SECONDS = 20.0
    state_module.BUSY_TIMEOUT_SECONDS = 1.0
    state_module.DurableStateError = _DurableStateError
    state_module.LeaseToken = _LeaseToken
    state_module.HeartbeatWorker = production_state_module.HeartbeatWorker
    state_module.RunStateStore = _FakeRunStateStore
    state_module.default_state_path = lambda: tmp_path / "run-state.sqlite3"
    state_module.compute_repo_key = lambda root: hashlib.sha256(
        str(Path(root).resolve()).encode("utf-8")
    ).hexdigest()

    service_module = types.ModuleType("hve.resume_service")
    service_module.WorkflowDescriptor = _WorkflowDescriptor
    service_module.ResumePlan = _ResumePlan
    service_module.ResumeService = _FakeResumeService
    service_module.canonical_json = _canonical_json
    service_module.compute_launch_plan_hash = _hash_value
    service_module.compute_resume_plan_hash = _hash_value
    service_module.build_resolved_replay_argv = (
        production_service_module.build_resolved_replay_argv
    )
    service_module.standard_execution_is_registerable = (
        production_service_module.standard_execution_is_registerable
    )
    service_module.reconcile_succeeded_steps = (
        production_service_module.reconcile_succeeded_steps
    )

    monkeypatch.setitem(sys.modules, "hve.run_state_store", state_module)
    monkeypatch.setitem(sys.modules, "hve.resume_service", service_module)
    hve_package = importlib.import_module("hve")
    monkeypatch.setattr(hve_package, "run_state_store", state_module, raising=False)
    monkeypatch.setattr(hve_package, "resume_service", service_module, raising=False)

    for name, value in (
        ("DurableStateError", _DurableStateError),
        ("LeaseToken", _LeaseToken),
        ("RunStateStore", _FakeRunStateStore),
        ("default_state_path", state_module.default_state_path),
        ("WorkflowDescriptor", _WorkflowDescriptor),
        ("ResumePlan", _ResumePlan),
        ("ResumeService", _FakeResumeService),
    ):
        monkeypatch.setattr(hve_main, name, value, raising=False)

    for module_name, replacements in (
        ("run_state_store", {"RunStateStore": _FakeRunStateStore}),
        ("resume_service", {"ResumeService": _FakeResumeService}),
    ):
        module = getattr(hve_main, module_name, None)
        if module is not None:
            for name, value in replacements.items():
                monkeypatch.setattr(module, name, value, raising=False)


def _is_hve_child(argv: Sequence[str]) -> bool:
    values = [str(value) for value in argv]
    return "orchestrate" in values and (
        "hve" in values or "-m" in values or values[0].endswith(("python", "python.exe"))
    )


def _install_subprocess_fakes(
    monkeypatch: pytest.MonkeyPatch,
    hve_main: Any,
) -> None:
    def fake_run(argv: Sequence[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args
        values = [str(value) for value in argv]
        if values and Path(values[0]).name.casefold() in {"git", "git.exe"}:
            return subprocess.CompletedProcess(values, 0, stdout=f"{_HEAD}\n", stderr="")
        if _is_hve_child(values):
            _trace().child_calls.append((values, dict(kwargs)))
            _trace().events.append("child")
            code = (
                _trace().child_returncodes.pop(0)
                if _trace().child_returncodes
                else _trace().child_returncode
            )
            if code == 0 and "--instance-id" in values:
                instance_id = values[values.index("--instance-id") + 1]
                for row in _trace().instance_rows:
                    if row.instance_id == instance_id:
                        row["status"] = "succeeded"
                        row["state_version"] = int(row["state_version"]) + 1
            return subprocess.CompletedProcess(values, code)
        _trace().external_calls.append(f"subprocess:{values[:2]}")
        raise AssertionError(f"unexpected external subprocess: {values!r}")

    class FakePopen:
        def __init__(self, argv: Sequence[str], *args: Any, **kwargs: Any) -> None:
            del args
            values = [str(value) for value in argv]
            if not _is_hve_child(values):
                _trace().external_calls.append(f"popen:{values[:2]}")
                raise AssertionError(f"unexpected external Popen: {values!r}")
            _trace().child_calls.append((values, dict(kwargs)))
            _trace().events.append("child")
            self.args = values
            self.returncode = _trace().child_returncode

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return self.returncode

        def communicate(self, input: Any = None, timeout: float | None = None) -> tuple[str, str]:
            del input, timeout
            return "", ""

        def __enter__(self) -> "FakePopen":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    def fake_check_output(argv: Sequence[str], *_args: Any, **_kwargs: Any) -> bytes:
        values = [str(value) for value in argv]
        if values and Path(values[0]).name.casefold() in {"git", "git.exe"}:
            return f"{_HEAD}\n".encode("ascii")
        _trace().external_calls.append(f"check-output:{values[:2]}")
        raise AssertionError(f"unexpected check_output: {values!r}")

    monkeypatch.setattr(hve_main.subprocess, "run", fake_run)
    monkeypatch.setattr(hve_main.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(hve_main.subprocess, "check_output", fake_check_output)


@dataclass(frozen=True)
class _Runtime:
    hve_main: Any
    trace: _Trace


@pytest.fixture()
def runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Runtime]:
    global _ACTIVE_TRACE

    hve_main = importlib.import_module("hve.__main__")
    trace = _Trace()
    _ACTIVE_TRACE = trace
    monkeypatch.chdir(tmp_path)
    _install_fake_durable_modules(monkeypatch, tmp_path, hve_main)
    _install_subprocess_fakes(monkeypatch, hve_main)

    from hve.config import SDKConfig
    from hve import orchestrator, prompt_execution

    monkeypatch.setattr(SDKConfig, "from_env", classmethod(lambda cls: cls()))
    monkeypatch.setattr(
        prompt_execution,
        "DurableStateError",
        _DurableStateError,
    )
    monkeypatch.setattr(
        prompt_execution,
        "resolve_head_commit",
        lambda _root: trace.head_values.pop(0) if trace.head_values else _HEAD,
    )
    monkeypatch.setattr(
        hve_main,
        "_start_startup_index_refresh",
        lambda _command: trace.events.append("index-refresh"),
    )
    monkeypatch.setattr(
        hve_main,
        "_ensure_run_workdir_env",
        lambda: trace.events.append("workdir-create"),
    )

    def startup_preflight(*_args: Any, **_kwargs: Any) -> bool:
        trace.events.append("startup-preflight")
        return True

    def external_preflight(label: str):
        def call(*_args: Any, **_kwargs: Any) -> bool:
            trace.external_calls.append(label)
            trace.events.append(label)
            return True

        return call

    monkeypatch.setattr(hve_main, "_run_startup_configuration_preflight", startup_preflight)
    monkeypatch.setattr(
        hve_main,
        "_run_copilot_auth_preflight",
        external_preflight("copilot-auth"),
    )
    monkeypatch.setattr(
        hve_main,
        "_run_workiq_auth_preflight",
        external_preflight("workiq-auth"),
    )
    monkeypatch.setattr(
        hve_main,
        "_run_azure_auth_preflight",
        external_preflight("azure-auth"),
    )

    async def fake_run_workflow(*args: Any, **kwargs: Any) -> dict[str, Any]:
        trace.workflow_calls.append({"args": args, "kwargs": kwargs})
        trace.events.append("run-workflow")
        return {"completed": ["1"], "failed": [], "skipped": [], "blocked": []}

    monkeypatch.setattr(orchestrator, "run_workflow", fake_run_workflow)

    def deny_network(*_args: Any, **_kwargs: Any) -> Any:
        trace.external_calls.append("network")
        raise AssertionError("durable resume CLI tests must not use network")

    monkeypatch.setattr(socket, "create_connection", deny_network)

    try:
        yield _Runtime(hve_main=hve_main, trace=trace)
    finally:
        _ACTIVE_TRACE = None


def _set_terminal(
    monkeypatch: pytest.MonkeyPatch,
    trace: _Trace,
    *,
    tty: bool,
    answers: Sequence[str] = (),
) -> None:
    stream = types.SimpleNamespace(isatty=lambda: tty)
    monkeypatch.setattr(sys, "stdin", stream)
    remaining = list(answers)

    def fake_input(prompt: str = "") -> str:
        trace.prompts.append(str(prompt))
        if not remaining:
            raise AssertionError(f"unexpected interactive prompt: {prompt}")
        return remaining.pop(0)

    monkeypatch.setattr(builtins, "input", fake_input)


def _invoke(runtime: _Runtime, argv: Sequence[str]) -> int:
    try:
        return int(runtime.hve_main.main(list(argv)))
    except SystemExit as exc:
        pytest.fail(
            f"FR-CLI-90 public command rejected argv {list(argv)!r}: SystemExit({exc.code})",
            pytrace=False,
        )


def _resume_parser(hve_main: Any) -> argparse.ArgumentParser:
    parser = hve_main._build_parser()
    try:
        args = parser.parse_args(["resume"])
    except SystemExit as exc:
        pytest.fail(
            f"FR-CLI-90: `hve resume` parser is missing: SystemExit({exc.code})",
            pytrace=False,
        )
    assert args.command == "resume"
    return parser


def _orchestrate_actions(hve_main: Any) -> dict[str, argparse.Action]:
    parser = hve_main._build_parser()
    subparsers = parser._subparsers._group_actions[0]
    return {
        action.dest: action
        for action in subparsers.choices["orchestrate"]._actions
        if action.dest != "help"
    }


def _hidden_argv(hve_main: Any) -> list[str]:
    actions = _orchestrate_actions(hve_main)
    values: dict[str, str] = {
        "_execution_id": "execution-existing",
        "_instance_id": "aas#existing",
        "_expected_state_version": "7",
        "_recovery_action": "restart-step",
        "_lease_owner": "resume-owner",
        "_lease_generation": "3",
    }
    missing = sorted(set(values) - set(actions))
    assert missing == [], f"missing hidden orchestrate destinations: {missing}"
    argv: list[str] = []
    for dest, value in values.items():
        option = next(
            (item for item in actions[dest].option_strings if item.startswith("--")),
            None,
        )
        assert option is not None, f"{dest} has no long option"
        argv.extend((option, value))
    return argv


def _child_namespace(runtime: _Runtime) -> argparse.Namespace:
    assert len(runtime.trace.child_calls) == 1
    argv = runtime.trace.child_calls[0][0]
    start = argv.index("orchestrate")
    return runtime.hve_main._build_parser().parse_args(argv[start:])


def _assert_no_resume_side_effects(trace: _Trace) -> None:
    assert trace.acquire_calls == []
    assert trace.release_calls == []
    assert trace.child_calls == []
    assert trace.external_calls == []


class TestResumeParser:
    def test_optional_execution_id_defaults_to_none(self, runtime: _Runtime) -> None:
        args = _resume_parser(runtime.hve_main).parse_args(["resume"])
        assert args.execution_id is None
        assert args.latest is False
        assert args.action is None

    def test_accepts_explicit_execution_id_and_action(self, runtime: _Runtime) -> None:
        args = _resume_parser(runtime.hve_main).parse_args(
            ["resume", "execution-42", "--action", "restart-step"]
        )
        assert args.execution_id == "execution-42"
        assert args.latest is False
        assert args.action == "restart-step"

    def test_accepts_latest_and_reuse_session(self, runtime: _Runtime) -> None:
        args = _resume_parser(runtime.hve_main).parse_args(
            ["resume", "--latest", "--action", "reuse-session"]
        )
        assert args.execution_id is None
        assert args.latest is True
        assert args.action == "reuse-session"

    def test_execution_id_and_latest_are_mutually_exclusive(self, runtime: _Runtime) -> None:
        parser = _resume_parser(runtime.hve_main)
        with pytest.raises(SystemExit):
            parser.parse_args(["resume", "execution-42", "--latest"])

    def test_unknown_recovery_action_is_rejected(self, runtime: _Runtime) -> None:
        parser = _resume_parser(runtime.hve_main)
        with pytest.raises(SystemExit):
            parser.parse_args(["resume", "execution-42", "--action", "continue"])

    def test_accepts_gui_supplied_expected_resume_hash(self, runtime: _Runtime) -> None:
        expected = "d" * 64
        args = _resume_parser(runtime.hve_main).parse_args(
            [
                "resume",
                "execution-42",
                "--action",
                "restart-step",
                "--expected-resume-hash",
                expected,
                "--replay-value",
                "additional_prompt=re-entered prompt",
            ]
        )
        assert args._expected_resume_hash == expected
        assert args._replay_values == ["additional_prompt=re-entered prompt"]

    def test_controller_only_resume_options_are_absent_from_help(
        self, runtime: _Runtime
    ) -> None:
        parser = runtime.hve_main._build_parser()
        subparsers = parser._subparsers._group_actions[0]
        resume_parser = subparsers.choices["resume"]
        actions = {action.dest: action for action in resume_parser._actions}
        help_text = resume_parser.format_help()

        for dest in ("_expected_resume_hash", "_replay_values"):
            assert actions[dest].help is argparse.SUPPRESS
            for option in actions[dest].option_strings:
                assert option not in help_text


class TestCandidateSelectionAndInteraction:
    def test_zero_candidates_fails_closed_without_external_work(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(runtime, ["resume"])

        assert code != 0
        assert runtime.trace.build_plan_calls == []
        _assert_no_resume_side_effects(runtime.trace)

    def test_one_candidate_is_displayed_and_confirmed_before_start(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        runtime.trace.candidates = [_candidate("execution-one")]
        runtime.trace.plans = [
            _plan(execution_id="execution-one"),
            _plan(execution_id="execution-one"),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=True, answers=("y",))

        assert _invoke(runtime, ["resume", "--action", "restart-step"]) == 0

        output = capsys.readouterr()
        assert "execution-one" in output.out + output.err
        assert runtime.trace.prompts, "the single implicit candidate was not confirmed"
        assert len(runtime.trace.build_plan_calls) == 2
        assert len(runtime.trace.acquire_calls) == 1
        assert len(runtime.trace.release_calls) == 1
        assert len(runtime.trace.child_calls) == 1
        assert runtime.trace.events.index("acquire") < runtime.trace.events.index("child")
        assert runtime.trace.events.index("child") < runtime.trace.events.index("lease.release")
        assert runtime.trace.external_calls == []

    def test_multiple_candidates_use_tty_menu_selection(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.candidates = [
            _candidate("execution-first"),
            _candidate("execution-second"),
        ]
        runtime.trace.plans = [
            _plan(execution_id="execution-second"),
            _plan(execution_id="execution-second"),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=True, answers=("2", "y"))

        assert _invoke(runtime, ["resume", "--action", "restart-step"]) == 0

        assert runtime.trace.build_plan_calls[0]["execution_id"] == "execution-second"
        assert len(runtime.trace.acquire_calls) == 1
        assert len(runtime.trace.release_calls) == 1
        assert len(runtime.trace.child_calls) == 1
        assert runtime.trace.external_calls == []

    def test_multiple_candidates_refuse_implicit_selection_without_tty(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.candidates = [
            _candidate("execution-first"),
            _candidate("execution-second"),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(runtime, ["resume", "--action", "restart-step"])

        assert code != 0
        assert runtime.trace.build_plan_calls == []
        _assert_no_resume_side_effects(runtime.trace)

    def test_latest_uses_service_order_without_tty_when_action_is_explicit(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.candidates = [
            _candidate("execution-new", updated_at="2026-08-28T02:00:00Z"),
            _candidate("execution-old", updated_at="2026-08-28T01:00:00Z"),
        ]
        runtime.trace.plans = [
            _plan(execution_id="execution-new"),
            _plan(execution_id="execution-new"),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        assert _invoke(
            runtime,
            ["resume", "--latest", "--action", "restart-step"],
        ) == 0

        assert [call["execution_id"] for call in runtime.trace.build_plan_calls] == [
            "execution-new",
            "execution-new",
        ]
        assert len(runtime.trace.child_calls) == 1
        assert len(runtime.trace.release_calls) == 1
        assert runtime.trace.external_calls == []

    def test_non_tty_risky_plan_requires_explicit_action(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.plans = [
            _plan(action=None, risk_reasons=("failed",)),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(runtime, ["resume", "execution-1"])

        assert code != 0
        assert [call["action"] for call in runtime.trace.build_plan_calls] == [None]
        _assert_no_resume_side_effects(runtime.trace)

    def test_user_cancellation_starts_no_lease_child_or_preflight(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.plans = [_plan()]
        _set_terminal(monkeypatch, runtime.trace, tty=True, answers=("n",))

        code = _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        )

        assert code != 0
        assert len(runtime.trace.build_plan_calls) == 1
        _assert_no_resume_side_effects(runtime.trace)

    def test_explicit_action_reaches_service_and_child_identity(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.plans = [
            _plan(action="reuse-session"),
            _plan(action="reuse-session"),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        assert _invoke(
            runtime,
            ["resume", "execution-1", "--action", "reuse-session"],
        ) == 0

        assert [call["action"] for call in runtime.trace.build_plan_calls] == [
            "reuse-session",
            "reuse-session",
        ]
        assert len(runtime.trace.acquire_calls) == 1
        child = _child_namespace(runtime)
        assert child._execution_id == "execution-1"
        assert child._instance_id == "aas#1"
        assert child._expected_state_version == 7
        assert child._recovery_action == "reuse-session"
        assert child._lease_owner == runtime.trace.acquire_calls[0][1]
        assert child._lease_generation == 1
        assert len(runtime.trace.release_calls) == 1
        assert runtime.trace.external_calls == []

    def test_gui_expected_hash_skips_tty_prompt_but_still_uses_cas(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        expected = "e" * 64
        runtime.trace.plans = [
            _plan(resume_hash=expected),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        assert _invoke(
            runtime,
            [
                "resume",
                "execution-1",
                "--action",
                "restart-step",
                "--expected-resume-hash",
                expected,
                "--replay-value",
                "additional_prompt=re-entered prompt",
            ],
        ) == 0

        assert runtime.trace.prompts == []
        assert len(runtime.trace.build_plan_calls) == 1
        assert runtime.trace.build_plan_calls[0]["replay_values"] == {
            "additional_prompt": "re-entered prompt",
        }
        assert len(runtime.trace.acquire_calls) == 1
        assert len(runtime.trace.child_calls) == 1
        assert len(runtime.trace.release_calls) == 1

    def test_gui_safe_plan_hash_does_not_change_for_an_implicit_restart(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        expected = "f" * 64
        runtime.trace.plans = [
            _plan(action=None, resume_hash=expected),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        assert _invoke(
            runtime,
            [
                "resume",
                "execution-1",
                "--expected-resume-hash",
                expected,
            ],
        ) == 0

        assert len(runtime.trace.build_plan_calls) == 1
        assert runtime.trace.build_plan_calls[0]["action"] is None
        child = _child_namespace(runtime)
        assert child._recovery_action == "restart-step"
        assert len(runtime.trace.acquire_calls) == 1
        assert len(runtime.trace.release_calls) == 1

    def test_child_failure_is_returned_and_parent_lease_is_released(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.plans = [_plan(), _plan()]
        runtime.trace.child_returncode = 9
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        )

        assert code == 9
        assert len(runtime.trace.child_calls) == 1
        assert len(runtime.trace.release_calls) == 1
        assert runtime.trace.events.index("child") < runtime.trace.events.index(
            "lease.release"
        )

    def test_ordered_execution_continues_with_the_next_incomplete_instance(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.instance_rows = [
            _Record(
                execution_id="execution-1",
                instance_id="aas#1",
                workflow_id="aas",
                ordinal=0,
                status="suspended",
                state_version=7,
            ),
            _Record(
                execution_id="execution-1",
                instance_id="aad-web#2",
                workflow_id="aad-web",
                ordinal=1,
                status="pending",
                state_version=0,
            ),
        ]
        runtime.trace.plans = [
            _plan(instance_id="aas#1", state_version=7),
            _plan(instance_id="aas#1", state_version=7),
            dataclasses.replace(
                _plan(instance_id="aad-web#2", state_version=0),
                workflow_id="aad-web",
                argv=("orchestrate", "--workflow", "aad-web"),
            ),
        ]
        next_head = "b" * 40
        runtime.trace.head_values = [_HEAD, _HEAD, next_head, next_head]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        assert _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        ) == 0

        assert len(runtime.trace.child_calls) == 2
        children = [_child[0] for _child in runtime.trace.child_calls]
        assert [
            child[child.index("--instance-id") + 1] for child in children
        ] == ["aas#1", "aad-web#2"]
        assert len(runtime.trace.acquire_calls) == 2
        assert len(runtime.trace.release_calls) == 2
        assert runtime.trace.build_plan_calls[-1]["current_head"] == next_head

    def test_ordered_controller_hash_stops_before_an_unapproved_next_plan(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        first_hash = "1" * 64
        next_hash = "2" * 64
        runtime.trace.instance_rows = [
            _Record(
                execution_id="execution-1",
                instance_id="aas#1",
                workflow_id="aas",
                ordinal=0,
                status="suspended",
                state_version=7,
            ),
            _Record(
                execution_id="execution-1",
                instance_id="aad-web#2",
                workflow_id="aad-web",
                ordinal=1,
                status="pending",
                state_version=0,
            ),
        ]
        runtime.trace.plans = [
            _plan(
                instance_id="aas#1",
                state_version=7,
                resume_hash=first_hash,
            ),
            dataclasses.replace(
                _plan(
                    instance_id="aad-web#2",
                    state_version=0,
                    resume_hash=next_hash,
                ),
                workflow_id="aad-web",
                argv=("orchestrate", "--workflow", "aad-web"),
            ),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(
            runtime,
            [
                "resume",
                "execution-1",
                "--action",
                "restart-step",
                "--expected-resume-hash",
                first_hash,
            ],
        )

        output = capsys.readouterr()
        assert code != 0
        assert len(runtime.trace.child_calls) == 1
        assert len(runtime.trace.acquire_calls) == 1
        assert len(runtime.trace.release_calls) == 1
        assert next_hash in output.out + output.err
        assert "再承認" in output.out + output.err

    def test_ordered_replay_values_do_not_leak_to_the_next_instance(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        first_hash = "5" * 64
        runtime.trace.instance_rows = [
            _Record(
                execution_id="execution-1",
                instance_id="aas#1",
                workflow_id="aas",
                ordinal=0,
                status="suspended",
                state_version=7,
            ),
            _Record(
                execution_id="execution-1",
                instance_id="aad-web#2",
                workflow_id="aad-web",
                ordinal=1,
                status="pending",
                state_version=0,
            ),
        ]
        runtime.trace.plans = [
            _plan(
                instance_id="aas#1",
                state_version=7,
                resume_hash=first_hash,
            ),
            dataclasses.replace(
                _plan(
                    instance_id="aad-web#2",
                    state_version=0,
                    resume_hash="6" * 64,
                ),
                workflow_id="aad-web",
                argv=("orchestrate", "--workflow", "aad-web"),
            ),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(
            runtime,
            [
                "resume",
                "execution-1",
                "--action",
                "restart-step",
                "--expected-resume-hash",
                first_hash,
                "--replay-value",
                "additional_prompt=first instance only",
            ],
        )

        assert code != 0
        assert len(runtime.trace.child_calls) == 1
        assert runtime.trace.build_plan_calls[0]["replay_values"] == {
            "additional_prompt": "first instance only",
        }
        assert runtime.trace.build_plan_calls[-1]["replay_values"] == {}

    def test_ordered_tty_requires_a_fresh_action_for_the_next_risky_instance(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.instance_rows = [
            _Record(
                execution_id="execution-1",
                instance_id="aas#1",
                workflow_id="aas",
                ordinal=0,
                status="suspended",
                state_version=7,
            ),
            _Record(
                execution_id="execution-1",
                instance_id="aad-web#2",
                workflow_id="aad-web",
                ordinal=1,
                status="suspended",
                state_version=0,
            ),
        ]
        first = _plan(
            instance_id="aas#1",
            action="reuse-session",
            state_version=7,
        )
        next_preview = dataclasses.replace(
            _plan(
                instance_id="aad-web#2",
                action=None,
                state_version=0,
                risk_reasons=("non_terminal",),
                resume_hash="7" * 64,
                argv=("orchestrate", "--workflow", "aad-web"),
            ),
            workflow_id="aad-web",
        )
        next_selected = dataclasses.replace(
            next_preview,
            action="restart-step",
            resume_plan_hash="8" * 64,
        )
        runtime.trace.plans = [
            first,
            first,
            next_preview,
            next_selected,
            next_selected,
        ]
        _set_terminal(
            monkeypatch,
            runtime.trace,
            tty=True,
            answers=("y", "2", "y"),
        )

        assert _invoke(
            runtime,
            ["resume", "execution-1", "--action", "reuse-session"],
        ) == 0

        assert [
            call["action"] for call in runtime.trace.build_plan_calls
        ] == [
            "reuse-session",
            "reuse-session",
            None,
            "restart-step",
            "restart-step",
        ]
        recovery_actions = [
            child[child.index("--recovery-action") + 1]
            for child, _kwargs in runtime.trace.child_calls
        ]
        assert recovery_actions == ["reuse-session", "restart-step"]

    def test_ordered_tty_rechecks_each_next_plan_after_confirmation(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.instance_rows = [
            _Record(
                execution_id="execution-1",
                instance_id="aas#1",
                workflow_id="aas",
                ordinal=0,
                status="suspended",
                state_version=7,
            ),
            _Record(
                execution_id="execution-1",
                instance_id="aad-web#2",
                workflow_id="aad-web",
                ordinal=1,
                status="pending",
                state_version=0,
            ),
        ]
        first = _plan(instance_id="aas#1", state_version=7)
        next_plan = dataclasses.replace(
            _plan(
                instance_id="aad-web#2",
                state_version=0,
                resume_hash="3" * 64,
            ),
            workflow_id="aad-web",
            argv=("orchestrate", "--workflow", "aad-web"),
        )
        stale_next_plan = dataclasses.replace(
            next_plan,
            resume_plan_hash="4" * 64,
        )
        runtime.trace.plans = [first, first, next_plan, stale_next_plan]
        _set_terminal(monkeypatch, runtime.trace, tty=True, answers=("y", "y"))

        code = _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        )

        assert code != 0
        assert len(runtime.trace.prompts) == 2
        assert len(runtime.trace.child_calls) == 1
        assert len(runtime.trace.acquire_calls) == 1
        assert len(runtime.trace.release_calls) == 1

    def test_reconciled_empty_argv_completes_without_starting_a_child(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.instance_rows = [
            _Record(
                execution_id="execution-1",
                instance_id="aas#1",
                workflow_id="aas",
                ordinal=0,
                status="suspended",
                state_version=7,
            ),
        ]
        reconciled = _plan(argv=())
        runtime.trace.plans = [reconciled, reconciled]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        assert _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        ) == 0

        assert runtime.trace.child_calls == []
        assert len(runtime.trace.complete_reconciled_calls) == 1
        assert len(runtime.trace.acquire_calls) == 1
        assert len(runtime.trace.release_calls) == 1
        assert runtime.trace.instance_rows[0].status == "succeeded"
        assert runtime.trace.events.index("acquire") < runtime.trace.events.index(
            "reconciled.complete"
        )
        assert runtime.trace.events.index(
            "reconciled.complete"
        ) < runtime.trace.events.index("lease.release")

    def test_ordered_execution_stops_at_the_first_failed_child(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.instance_rows = [
            _Record(
                execution_id="execution-1",
                instance_id=f"instance-{ordinal}",
                workflow_id="aas",
                ordinal=ordinal,
                status="suspended" if ordinal == 0 else "pending",
                state_version=7 if ordinal == 0 else 0,
            )
            for ordinal in range(3)
        ]
        runtime.trace.plans = [
            _plan(instance_id="instance-0", state_version=7),
            _plan(instance_id="instance-0", state_version=7),
            _plan(instance_id="instance-1", state_version=0),
        ]
        runtime.trace.child_returncodes = [0, 9, 0]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        assert _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        ) == 9

        assert len(runtime.trace.child_calls) == 2
        assert len(runtime.trace.acquire_calls) == 2
        assert len(runtime.trace.release_calls) == 2


class TestResumeIntegrityAndConcurrency:
    def test_unknown_head_fails_before_plan_lease_or_child(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.head_values = ["unknown"]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        )

        assert code != 0
        assert runtime.trace.build_plan_calls == []
        _assert_no_resume_side_effects(runtime.trace)

    def test_head_drift_after_approval_starts_no_lease_or_child(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.head_values = [_HEAD, "b" * 40]
        runtime.trace.plans = [_plan(), _plan()]
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        )

        assert code != 0
        assert len(runtime.trace.build_plan_calls) == 2
        assert runtime.trace.acquire_calls == []
        assert runtime.trace.child_calls == []

    def test_plan_hash_is_recomputed_after_approval_and_stale_hash_starts_nothing(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.plans = [
            _plan(resume_hash="1" * 64),
            _plan(resume_hash="2" * 64),
        ]
        _set_terminal(monkeypatch, runtime.trace, tty=True, answers=("y",))

        code = _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        )

        assert code != 0
        assert len(runtime.trace.build_plan_calls) == 2
        _assert_no_resume_side_effects(runtime.trace)

    def test_stale_state_version_cas_starts_no_child(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.plans = [_plan(), _plan()]
        runtime.trace.acquire_error = _DurableStateError("stale expected state version")
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(
            runtime,
            ["resume", "execution-1", "--action", "restart-step"],
        )

        assert code != 0
        assert len(runtime.trace.acquire_calls) == 1
        assert runtime.trace.child_calls == []
        assert runtime.trace.external_calls == []

    def test_active_owner_refusal_has_no_silent_restart_fallback(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.plans = [
            _plan(action="reuse-session"),
            _plan(action="reuse-session"),
        ]
        runtime.trace.acquire_error = _DurableStateError("active/in-use lease owner")
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(
            runtime,
            ["resume", "execution-1", "--action", "reuse-session"],
        )

        assert code != 0
        assert [call["action"] for call in runtime.trace.build_plan_calls] == [
            "reuse-session",
            "reuse-session",
        ]
        assert len(runtime.trace.acquire_calls) == 1
        assert runtime.trace.child_calls == []
        assert runtime.trace.external_calls == []

    def test_unsupported_execution_mode_is_nonzero_with_child_zero(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        runtime.trace.build_plan_error = _DurableStateError(
            "fleet/cloud execution is not resumable"
        )
        _set_terminal(monkeypatch, runtime.trace, tty=False)

        code = _invoke(
            runtime,
            ["resume", "execution-unsupported", "--action", "restart-step"],
        )

        assert code != 0
        assert len(runtime.trace.build_plan_calls) == 1
        _assert_no_resume_side_effects(runtime.trace)


class TestHiddenDurableIdentity:
    def test_orchestrate_parser_accepts_all_typed_internal_destinations(
        self,
        runtime: _Runtime,
    ) -> None:
        argv = ["orchestrate", "--workflow", "aas", *_hidden_argv(runtime.hve_main)]
        args = runtime.hve_main._build_parser().parse_args(argv)

        assert args._execution_id == "execution-existing"
        assert args._instance_id == "aas#existing"
        assert args._expected_state_version == 7
        assert isinstance(args._expected_state_version, int)
        assert args._recovery_action == "restart-step"

    def test_internal_destinations_are_absent_from_orchestrate_help(
        self,
        runtime: _Runtime,
    ) -> None:
        parser = runtime.hve_main._build_parser()
        subparsers = parser._subparsers._group_actions[0]
        orchestrate_parser = subparsers.choices["orchestrate"]
        actions = {
            action.dest: action
            for action in orchestrate_parser._actions
            if action.dest != "help"
        }
        help_text = orchestrate_parser.format_help()
        _hidden_argv(runtime.hve_main)  # guard against a vacuous help-only pass
        for dest in (
            "_execution_id",
            "_instance_id",
            "_expected_state_version",
            "_recovery_action",
            "_lease_owner",
            "_lease_generation",
            "_unattended",
        ):
            action = actions[dest]
            assert action.help is argparse.SUPPRESS
            for option in action.option_strings:
                assert option not in help_text

    @pytest.mark.parametrize(
        "dest",
        ["_expected_state_version", "_lease_generation"],
    )
    def test_internal_versions_reject_negative_values_at_parse_time(
        self, runtime: _Runtime, dest: str
    ) -> None:
        actions = _orchestrate_actions(runtime.hve_main)
        option = actions[dest].option_strings[0]
        with pytest.raises(SystemExit):
            runtime.hve_main._build_parser().parse_args(
                ["orchestrate", "--workflow", "aas", option, "-1"]
            )

    @pytest.mark.parametrize(
        "args",
        [
            ("--execution-id", "execution-only"),
            ("--instance-id", "instance-only"),
            (
                "--execution-id", "execution",
                "--instance-id", "instance",
                "--recovery-action", "restart-step",
            ),
        ],
    )
    def test_partial_internal_identity_fails_before_external_preflight(
        self,
        runtime: _Runtime,
        args: tuple[str, ...],
    ) -> None:
        code = _invoke(
            runtime,
            ["orchestrate", "--workflow", "aas", *args],
        )

        assert code != 0
        assert runtime.trace.register_calls == []
        assert runtime.trace.workflow_calls == []
        assert runtime.trace.external_calls == []

    def test_internal_destinations_are_declared_in_option_parity(
        self,
        runtime: _Runtime,
    ) -> None:
        del runtime
        fixture = yaml.safe_load(_PARITY_FIXTURE.read_text(encoding="utf-8"))
        assert set(fixture.get("orchestrate_cli_internal_dests") or ()) == {
            "_execution_id",
            "_instance_id",
            "_expected_state_version",
            "_recovery_action",
            "_lease_owner",
            "_lease_generation",
            "_unattended",
        }

    def test_internal_identity_reaches_immutable_orchestrator_context(
        self,
        runtime: _Runtime,
    ) -> None:
        code = _invoke(
            runtime,
            ["orchestrate", "--workflow", "aas", *_hidden_argv(runtime.hve_main)],
        )

        assert code == 0
        assert runtime.trace.register_calls == []
        assert len(runtime.trace.workflow_calls) == 1
        context = runtime.trace.workflow_calls[0]["kwargs"]["orchestrator_ctx"]
        assert context.execution_id == "execution-existing"
        assert context.instance_id == "aas#existing"
        assert context.expected_state_version == 7
        assert context.recovery_action == "restart-step"
        assert context.lease_owner == "resume-owner"
        assert context.lease_generation == 3
        with pytest.raises(dataclasses.FrozenInstanceError):
            context.execution_id = "mutated"


class _WizardConsole:
    def __init__(self, trace: _Trace) -> None:
        self.trace = trace
        self.s = types.SimpleNamespace(
            CYAN="",
            RESET="",
            DIM="",
            GREEN="",
            YELLOW="",
        )

    def banner(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def menu_select(self, label: str, _options: Sequence[str], **_kwargs: Any) -> int:
        self.trace.events.append(f"wizard.menu:{label}")
        if "実行モード" in label:
            return 0  # quick auto
        return 0

    def prompt_multi_select(self, *_args: Any, **_kwargs: Any) -> list[int]:
        return []

    def prompt_yes_no(self, label: str, **_kwargs: Any) -> bool:
        if "この設定で実行しますか" in label or "ワークベンチ" in label:
            return True
        return False

    def prompt_input(self, _label: str, *, default: Any = "", **_kwargs: Any) -> Any:
        return default

    def panel(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def warning(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def status(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def error(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def _print(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _install_quick_wizard(runtime: _Runtime, monkeypatch: pytest.MonkeyPatch) -> None:
    from hve import config, console, orchestrator, template_engine, workflow_registry, workiq
    from hve.workflow_registry import StepDef, WorkflowDef

    workflow = WorkflowDef(
        id="aas",
        name="AAS",
        label_prefix="aas",
        state_labels={},
        params=[],
        steps=[StepDef(id="1", title="Step 1", custom_agent=None)],
    )
    wizard_console = _WizardConsole(runtime.trace)
    monkeypatch.setattr(console, "Console", lambda **_kwargs: wizard_console)
    monkeypatch.setattr(workflow_registry, "list_workflows", lambda: [workflow])
    monkeypatch.setattr(workflow_registry, "get_workflow", lambda _workflow_id: workflow)
    monkeypatch.setattr(template_engine, "_WORKFLOW_DISPLAY_NAMES", {"aas": "AAS"})
    monkeypatch.setattr(config, "get_model_choices", lambda include_auto=True: ["Auto"])
    monkeypatch.setattr(workiq, "is_workiq_available", lambda: False)
    monkeypatch.setattr(workiq, "workiq_login", lambda _console: False)
    monkeypatch.setattr(workiq, "get_workiq_prompt_template", lambda _mode: "")

    async def fake_run_workflow(*args: Any, **kwargs: Any) -> dict[str, Any]:
        runtime.trace.workflow_calls.append({"args": args, "kwargs": kwargs})
        runtime.trace.events.append("run-workflow")
        return {"completed": ["1"], "failed": [], "skipped": [], "blocked": []}

    monkeypatch.setattr(orchestrator, "run_workflow", fake_run_workflow)


class TestExecutionRegistration:
    def test_unknown_head_fails_before_registration_or_external_work(
        self,
        runtime: _Runtime,
    ) -> None:
        runtime.trace.head_values = ["unknown"]

        code = _invoke(
            runtime,
            ["orchestrate", "--workflow", "aas", "--quiet"],
        )

        assert code != 0
        assert runtime.trace.register_calls == []
        assert runtime.trace.workflow_calls == []
        assert runtime.trace.external_calls == []

    def test_direct_orchestrate_registers_after_resolution_before_external_preflight(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        original_build_config = runtime.hve_main._build_config
        original_build_params = runtime.hve_main._build_params
        resolved_prompt = "ENV-DERIVED-REPLAY-SENTINEL"

        def build_config(args: argparse.Namespace) -> Any:
            runtime.trace.events.append("config-resolved")
            config = original_build_config(args)
            config.additional_prompt = resolved_prompt
            return config

        def build_params(args: argparse.Namespace) -> dict[str, Any]:
            runtime.trace.events.append("params-resolved")
            return original_build_params(args)

        monkeypatch.setattr(runtime.hve_main, "_build_config", build_config)
        monkeypatch.setattr(runtime.hve_main, "_build_params", build_params)

        assert _invoke(
            runtime,
            ["orchestrate", "--workflow", "aas", "--quiet", "--strict"],
        ) == 0

        assert len(runtime.trace.register_calls) == 1
        registration = runtime.trace.register_calls[0]
        descriptors = registration["descriptors"]
        assert len(descriptors) == 1
        assert descriptors[0].workflow_id == "aas"
        assert descriptors[0].ordinal == 0
        assert registration["checkpoint_head"] == _HEAD
        assert len(runtime.trace.sanitize_calls) == 1
        replay_argv = runtime.trace.sanitize_calls[0]
        assert "--additional-prompt" in replay_argv
        assert replay_argv[replay_argv.index("--additional-prompt") + 1] == resolved_prompt
        assert "--strict" in replay_argv
        assert runtime.trace.events.index("config-resolved") < runtime.trace.events.index(
            "register"
        )
        assert runtime.trace.events.index("params-resolved") < runtime.trace.events.index(
            "register"
        )
        assert runtime.trace.events.index("register") < runtime.trace.events.index(
            "copilot-auth"
        )
        assert runtime.trace.events.index("register") < runtime.trace.events.index(
            "index-refresh"
        )
        assert runtime.trace.events.index("register") < runtime.trace.events.index(
            "workdir-create"
        )
        assert runtime.trace.events.index("register") < runtime.trace.events.index(
            "run-workflow"
        )

    @pytest.mark.parametrize("command", ["run", "cli"])
    def test_interactive_entrypoint_registers_before_external_preflight(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
        command: str,
    ) -> None:
        _install_quick_wizard(runtime, monkeypatch)

        assert _invoke(runtime, [command, "--no-banner"]) == 0

        assert len(runtime.trace.register_calls) == 1
        descriptors = runtime.trace.register_calls[0]["descriptors"]
        assert len(descriptors) == 1
        assert descriptors[0].workflow_id == "aas"
        assert runtime.trace.events.index("register") < runtime.trace.events.index(
            "copilot-auth"
        )
        assert runtime.trace.events.index("register") < runtime.trace.events.index(
            "index-refresh"
        )
        assert runtime.trace.events.index("register") < runtime.trace.events.index(
            "run-workflow"
        )

    def test_registration_failure_is_fail_closed_before_auth_or_execution(
        self,
        runtime: _Runtime,
    ) -> None:
        runtime.trace.register_error = _DurableStateError("registration commit failed")

        code = _invoke(runtime, ["orchestrate", "--workflow", "aas", "--quiet"])

        assert code != 0
        assert len(runtime.trace.register_calls) == 1
        assert runtime.trace.workflow_calls == []
        assert runtime.trace.external_calls == []
        assert "index-refresh" not in runtime.trace.events
        assert "workdir-create" not in runtime.trace.events


class TestRegistrationExclusions:
    @pytest.mark.parametrize(
        "extra_args",
        [
            ("--dry-run",),
            ("--fleet-mode",),
            ("--cloud-session",),
            ("--create-issues", "--assign-copilot-agent", "--repo", "owner/repo"),
        ],
        ids=["dry-run", "fleet", "cloud-session", "github-cloud-agent"],
    )
    def test_unsupported_initial_modes_do_not_register(
        self,
        runtime: _Runtime,
        extra_args: tuple[str, ...],
    ) -> None:
        code = _invoke(
            runtime,
            ["orchestrate", "--workflow", "aas", "--quiet", *extra_args],
        )

        assert code == 0
        assert runtime.trace.register_calls == []
        assert len(runtime.trace.workflow_calls) == 1

    def test_autopilot_does_not_register(
        self,
        runtime: _Runtime,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        called: list[argparse.Namespace] = []

        def fake_autopilot(args: argparse.Namespace) -> int:
            called.append(args)
            runtime.trace.events.append("autopilot")
            return 0

        monkeypatch.setattr(
            runtime.hve_main,
            "_cmd_orchestrate_autopilot_chain",
            fake_autopilot,
        )

        code = _invoke(
            runtime,
            [
                "orchestrate",
                "--autopilot-chain",
                "aad-web,asdw-web",
                "--autopilot-dry-run",
            ],
        )

        assert code == 0
        assert len(called) == 1
        assert runtime.trace.register_calls == []
        assert runtime.trace.workflow_calls == []
