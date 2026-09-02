"""T35 durable-resume parity contracts for the three local surfaces.

Traceability: FR-LOCAL-SURFACE-02, FR-CLI-90, FR-GUI-50, FR-PROMPT-11.

The tests use one real temporary SQLite state snapshot, the real shared
``ResumeService``, an offscreen ``ResumeDialog``, and a fake HVE child.  They
must not open the platform default state database or contact SDK, Azure,
GitHub, or any network endpoint.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field, replace
import importlib
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Mapping, Sequence

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATABASE_NAME = "state.sqlite3"
_EXECUTION_ID = "execution-surface-parity"
_INSTANCE_ID = "aas-surface-parity"
_WORKFLOW_ID = "aas"
_LAUNCH_HEAD = "a" * 40
_CURRENT_HEAD = "b" * 40
_REPLAY_VALUES = {
    "additional_prompt": "ephemeral parity prompt",
    "issue_title": "ephemeral parity title",
}
_RISK_CODES = frozenset(
    {
        "unsupported_mode",
        "active_owner",
        "failed",
        "non_terminal",
        "head_drift",
        "missing_output",
        "missing_replay_value",
        "sdk_missing",
        "sdk_in_use",
    }
)


@dataclass
class _Trace:
    candidate_calls: list[dict[str, Any]] = field(default_factory=list)
    build_calls: list[dict[str, Any]] = field(default_factory=list)
    acquire_calls: list[dict[str, Any]] = field(default_factory=list)
    child_calls: list[tuple[list[str], dict[str, Any]]] = field(default_factory=list)
    store_paths: list[Path] = field(default_factory=list)
    external_attempts: list[str] = field(default_factory=list)
    autopilot_calls: int = 0


@dataclass(frozen=True)
class _Runtime:
    repo_root: Path
    database_path: Path
    trace: _Trace
    hve_main: Any
    resume_module: Any
    state_module: Any
    state_bridge: Any
    real_store_type: type[Any]
    real_service_type: type[Any]
    recording_service_type: type[Any]
    descriptor_type: type[Any]
    lease_token_type: type[Any]
    snapshot: Callable[[], tuple[Any, ...]]


@pytest.fixture(scope="module")
def qapp() -> Any:
    qt_widgets = pytest.importorskip("PySide6.QtWidgets")
    application_type = qt_widgets.QApplication
    return application_type.instance() or application_type([])


def _database_snapshot(database_path: Path) -> tuple[Any, ...]:
    """Return a deterministic snapshot of all durable control rows."""

    with sqlite3.connect(database_path) as connection:
        return tuple(
            tuple(
                tuple(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY rowid"
                ).fetchall()
            )
            for table in ("executions", "workflow_instances", "step_instances")
        )


def _flag_value(argv: Sequence[str], flag: str) -> str:
    values = list(argv)
    try:
        return values[values.index(flag) + 1]
    except (ValueError, IndexError) as exc:
        raise AssertionError(f"fake child is missing {flag}: {values!r}") from exc


@pytest.fixture()
def runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Runtime]:
    """Create one isolated real store and install only boundary-level spies."""

    hve_main = importlib.import_module("hve.__main__")
    resume_module = importlib.import_module("hve.resume_service")
    state_module = importlib.import_module("hve.run_state_store")
    state_bridge = importlib.import_module("hve.gui.state_bridge")
    prompt_execution = importlib.import_module("hve.prompt_execution")
    runtime_observability = importlib.import_module("hve.runtime_observability")

    real_store_type = state_module.RunStateStore
    real_service_type = resume_module.ResumeService
    descriptor_type = resume_module.WorkflowDescriptor
    lease_token_type = state_module.LeaseToken
    completed_process_type = subprocess.CompletedProcess

    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    database_path = tmp_path / _DATABASE_NAME
    trace = _Trace()

    with real_store_type(database_path) as setup_store:
        setup_service = real_service_type(setup_store, repo_root)
        setup_service.register_execution(
            "cli",
            (
                descriptor_type(
                    instance_id=_INSTANCE_ID,
                    workflow_id=_WORKFLOW_ID,
                    ordinal=0,
                    mode="standard",
                    argv=(
                        "orchestrate",
                        "--workflow",
                        _WORKFLOW_ID,
                        "--additional-prompt",
                        "not-persisted",
                        "--issue-title",
                        "not-persisted",
                    ),
                ),
            ),
            execution_id=_EXECUTION_ID,
            checkpoint_head=_LAUNCH_HEAD,
        )
        token = setup_store.acquire_lease(
            _EXECUTION_ID,
            _INSTANCE_ID,
            0,
            "fixture-owner",
        )
        token = setup_store.transition_workflow(token, "failed")
        setup_store.release_lease(token)

    class RecordingResumeService(real_service_type):
        def __init__(
            self,
            store: Any,
            root: str | Path,
            *,
            surface: str = "cli",
        ) -> None:
            super().__init__(store, root)
            self._test_surface = surface

        def list_candidates(self) -> tuple[Any, ...]:
            result = super().list_candidates()
            trace.candidate_calls.append(
                {"surface": self._test_surface, "result": result}
            )
            return result

        def build_plan(
            self,
            execution_id: str,
            *,
            action: str | None = None,
            replay_values: Mapping[str, str] | None = None,
            current_head: str | None = None,
        ) -> Any:
            result = super().build_plan(
                execution_id,
                action=action,
                replay_values=replay_values,
                current_head=current_head,
            )
            trace.build_calls.append(
                {
                    "surface": self._test_surface,
                    "execution_id": execution_id,
                    "action": action,
                    "replay_values": dict(replay_values or {}),
                    "current_head": current_head,
                    "result": result,
                }
            )
            return result

        def acquire(self, plan: Any, owner: str) -> Any:
            trace.acquire_calls.append(
                {
                    "surface": self._test_surface,
                    "plan": plan,
                    "owner": owner,
                }
            )
            return super().acquire(plan, owner)

    def isolated_store(path: str | os.PathLike[str] | None = None) -> Any:
        resolved = database_path if path is None else Path(path)
        resolved = resolved.resolve()
        trace.store_paths.append(resolved)
        assert resolved == database_path.resolve(), (
            "a resume surface attempted to open a non-test durable database: "
            f"{resolved}"
        )
        return real_store_type(resolved)

    def forbidden_default_path() -> Path:
        raise AssertionError("platform default durable state path must not be used")

    def deny_external(label: str) -> Callable[..., Any]:
        def blocked(*_args: Any, **_kwargs: Any) -> Any:
            trace.external_attempts.append(label)
            raise AssertionError(f"T35 forbids external access: {label}")

        return blocked

    def fake_child_run(
        argv: Sequence[str],
        *_args: Any,
        **kwargs: Any,
    ) -> Any:
        values = [str(value) for value in argv]
        if len(values) < 4 or values[1:4] != ["-m", "hve", "orchestrate"]:
            trace.external_attempts.append(f"subprocess.run:{values[:4]!r}")
            raise AssertionError(f"unexpected subprocess: {values!r}")

        trace.child_calls.append((values, dict(kwargs)))
        assert kwargs.get("shell") is False
        token = lease_token_type(
            execution_id=_flag_value(values, "--execution-id"),
            instance_id=_flag_value(values, "--instance-id"),
            owner=_flag_value(values, "--lease-owner"),
            generation=int(_flag_value(values, "--lease-generation")),
            state_version=int(_flag_value(values, "--expected-state-version")),
        )
        with real_store_type(database_path) as child_store:
            child_store.transition_workflow(
                token,
                "succeeded",
                run_id="fake-child",
            )
        return completed_process_type(values, 0)

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(state_module, "RunStateStore", isolated_store)
    monkeypatch.setattr(state_module, "default_state_path", forbidden_default_path)
    monkeypatch.setattr(resume_module, "ResumeService", RecordingResumeService)
    monkeypatch.setattr(prompt_execution, "resolve_head_commit", lambda _root: _CURRENT_HEAD)
    monkeypatch.setattr(runtime_observability, "is_child_process", lambda: False)
    monkeypatch.setattr(subprocess, "run", fake_child_run)
    monkeypatch.setattr(subprocess, "Popen", deny_external("subprocess.Popen"))
    monkeypatch.setattr(socket, "create_connection", deny_external("network.create_connection"))
    monkeypatch.setattr(socket.socket, "connect", deny_external("network.socket.connect"))
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False))

    yield _Runtime(
        repo_root=repo_root,
        database_path=database_path,
        trace=trace,
        hve_main=hve_main,
        resume_module=resume_module,
        state_module=state_module,
        state_bridge=state_bridge,
        real_store_type=real_store_type,
        real_service_type=real_service_type,
        recording_service_type=RecordingResumeService,
        descriptor_type=descriptor_type,
        lease_token_type=lease_token_type,
        snapshot=lambda: _database_snapshot(database_path),
    )


def _invoke_main(runtime: _Runtime, argv: Sequence[str]) -> int:
    try:
        return int(runtime.hve_main.main(list(argv)))
    except SystemExit as exc:
        pytest.fail(
            f"public HVE command rejected T35 argv {list(argv)!r}: {exc.code}",
            pytrace=False,
        )


def _candidate_fingerprint(candidate: Any) -> tuple[Any, ...]:
    return tuple(
        getattr(candidate, name)
        for name in (
            "execution_id",
            "repo_key",
            "instance_id",
            "workflow_id",
            "status",
            "mode",
            "state_version",
            "heartbeat_at",
            "updated_at",
            "surface",
        )
    )


def _plan_fingerprint(plan: Any) -> tuple[Any, ...]:
    return tuple(
        getattr(plan, name)
        for name in (
            "execution_id",
            "instance_id",
            "workflow_id",
            "action",
            "expected_state_version",
            "risk_reasons",
            "missing_replay_keys",
            "resume_plan_hash",
            "argv",
        )
    )


def _matching_plan(
    trace: _Trace,
    surface: str,
    *,
    action: str | None,
    replay_values: Mapping[str, str],
) -> Any:
    matches = [
        call["result"]
        for call in trace.build_calls
        if call["surface"] == surface
        and call["execution_id"] == _EXECUTION_ID
        and call["action"] == action
        and call["replay_values"] == dict(replay_values)
        and call["current_head"] == _CURRENT_HEAD
    ]
    assert matches, (
        f"{surface} did not call common ResumeService.build_plan with the "
        "shared execution/action/replay/HEAD snapshot"
    )
    return matches[-1]


def _select_action(dialog: Any, action: str) -> None:
    for index in range(dialog.action_combo.count()):
        if dialog.action_combo.itemData(index) == action:
            dialog.action_combo.setCurrentIndex(index)
            return
    pytest.fail(f"ResumeDialog does not expose common action {action!r}", pytrace=False)


def test_cli_gui_prompt_share_one_candidate_and_resume_plan_snapshot(
    runtime: _Runtime,
    qapp: Any,
) -> None:
    """All surfaces obtain byte-equivalent plan meaning from the shared service."""

    from PySide6.QtWidgets import QDialogButtonBox, QLineEdit

    dialog_module = importlib.import_module("hve.gui.resume_dialog")
    before_planning = runtime.snapshot()
    prompt_store = runtime.real_store_type(runtime.database_path)
    gui_store = runtime.real_store_type(runtime.database_path)
    dialog = None
    try:
        prompt_service = runtime.recording_service_type(
            prompt_store,
            runtime.repo_root,
            surface="prompt",
        )
        prompt_candidates = prompt_service.list_candidates()
        assert len(prompt_candidates) == 1
        prompt_service.build_plan(
            _EXECUTION_ID,
            action=None,
            replay_values=None,
            current_head=_CURRENT_HEAD,
        )
        prompt_service.build_plan(
            _EXECUTION_ID,
            action="restart-step",
            replay_values=_REPLAY_VALUES,
            current_head=_CURRENT_HEAD,
        )

        gui_service = runtime.recording_service_type(
            gui_store,
            runtime.repo_root,
            surface="gui",
        )
        dialog = dialog_module.ResumeDialog(
            gui_service,
            current_head=_CURRENT_HEAD,
        )
        qapp.processEvents()
        assert dialog.candidate_list.count() == 1
        assert _EXECUTION_ID in dialog.candidate_list.item(0).text()

        _select_action(dialog, "restart-step")
        qapp.processEvents()
        edits: dict[str, QLineEdit] = {}
        for key, value in _REPLAY_VALUES.items():
            edit = dialog.findChild(QLineEdit, f"resumeReplay_{key}")
            assert edit is not None, f"ResumeDialog is missing replay input {key!r}"
            edit.setText(value)
            edits[key] = edit
        for edit in edits.values():
            edit.editingFinished.emit()
            qapp.processEvents()

        confirm = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert confirm is not None and confirm.isEnabled()
        confirm.click()
        qapp.processEvents()
        gui_plan = dialog.selected_plan()
        assert gui_plan is not None
        assert dialog.selected_replay_values() == _REPLAY_VALUES

        # A non-interactive preview with unresolved replay data must plan from
        # the same snapshot but start no child.
        assert _invoke_main(runtime, ["resume", "--latest"]) != 0
        assert runtime.trace.child_calls == []
        assert runtime.snapshot() == before_planning

        candidate_snapshots = [
            _candidate_fingerprint(call["result"][0])
            for call in runtime.trace.candidate_calls
            if call["result"]
        ]
        assert len(candidate_snapshots) >= 3
        assert len(set(candidate_snapshots)) == 1

        preview_plans = [
            _matching_plan(runtime.trace, surface, action=None, replay_values={})
            for surface in ("prompt", "gui", "cli")
        ]
        assert len({_plan_fingerprint(plan) for plan in preview_plans}) == 1
        assert preview_plans[0].missing_replay_keys == tuple(_REPLAY_VALUES)
        assert "missing_replay_value" in preview_plans[0].risk_reasons

        approved_plans = [
            _matching_plan(
                runtime.trace,
                surface,
                action="restart-step",
                replay_values=_REPLAY_VALUES,
            )
            for surface in ("prompt", "gui")
        ]
        assert _plan_fingerprint(approved_plans[0]) == _plan_fingerprint(
            approved_plans[1]
        )
        assert approved_plans[0].expected_state_version == 1
        assert approved_plans[0].missing_replay_keys == ()
        assert approved_plans[0].risk_reasons == ("failed", "head_drift")

        # GUI and Prompt controllers both hand the approved common plan to the
        # existing public CLI controller; only that controller may acquire CAS.
        public_resume_argv = runtime.state_bridge.build_resume_argv(
            gui_plan,
            _REPLAY_VALUES,
        )
        assert _invoke_main(runtime, public_resume_argv) == 0
        cli_plan = _matching_plan(
            runtime.trace,
            "cli",
            action="restart-step",
            replay_values=_REPLAY_VALUES,
        )
        assert _plan_fingerprint(cli_plan) == _plan_fingerprint(gui_plan)
        assert len(runtime.trace.acquire_calls) == 1
        assert runtime.trace.acquire_calls[0]["surface"] == "cli"
        assert len(runtime.trace.child_calls) == 1
        child_argv, child_kwargs = runtime.trace.child_calls[0]
        assert child_kwargs.get("shell") is False
        assert _flag_value(child_argv, "--execution-id") == _EXECUTION_ID
        assert _flag_value(child_argv, "--instance-id") == _INSTANCE_ID

        with runtime.real_store_type(runtime.database_path) as verification_store:
            instance = verification_store.get_instance(_EXECUTION_ID, _INSTANCE_ID)
            assert instance is not None
            assert instance["status"] == "succeeded"
            assert instance["lease_owner"] is None
        assert runtime.trace.external_attempts == []
        assert runtime.trace.store_paths
        assert set(runtime.trace.store_paths) == {runtime.database_path.resolve()}
    finally:
        if dialog is not None:
            dialog.deleteLater()
            qapp.processEvents()
        gui_store.close()
        prompt_store.close()


def _find_definition(tree: ast.AST, name: str, kind: type[Any]) -> Any:
    matches = [node for node in ast.walk(tree) if isinstance(node, kind) and node.name == name]
    assert len(matches) == 1, f"expected one {name} definition, found {len(matches)}"
    return matches[0]


def _call_paths(node: ast.AST) -> set[str]:
    def dotted(value: ast.AST) -> str:
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            parent = dotted(value.value)
            return f"{parent}.{value.attr}" if parent else value.attr
        return ""

    return {
        dotted(call.func)
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
    }


def _prompt_resume_contract() -> str:
    path = _REPO_ROOT / ".github" / "skills" / "hve-prompt-edition" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    marker = "## durable resume controller 境界（FR-PROMPT-11）"
    start = text.index(marker)
    next_heading = text.find("\n## ", start + len(marker))
    return text[start:] if next_heading < 0 else text[start:next_heading]


def test_surfaces_import_and_call_the_shared_service_without_domain_forks() -> None:
    """AST/import checks reject surface-owned risk, hash, SQL, or lease CAS rules."""

    main_tree = ast.parse((_REPO_ROOT / "hve" / "__main__.py").read_text(encoding="utf-8"))
    dialog_tree = ast.parse(
        (_REPO_ROOT / "hve" / "gui" / "resume_dialog.py").read_text(encoding="utf-8")
    )
    bridge_tree = ast.parse(
        (_REPO_ROOT / "hve" / "gui" / "state_bridge.py").read_text(encoding="utf-8")
    )
    cli_resume = _find_definition(main_tree, "_cmd_resume", ast.FunctionDef)
    gui_dialog = _find_definition(dialog_tree, "ResumeDialog", ast.ClassDef)
    gui_bridge = _find_definition(bridge_tree, "build_resume_argv", ast.FunctionDef)

    cli_calls = _call_paths(cli_resume)
    gui_calls = _call_paths(gui_dialog)
    bridge_calls = _call_paths(gui_bridge)
    assert any(path.endswith("service.list_candidates") for path in cli_calls)
    assert any(path.endswith("service.build_plan") for path in cli_calls)
    assert any(path.endswith("service.acquire") for path in cli_calls)
    assert any(path.endswith("_service.list_candidates") for path in gui_calls)
    assert any(path.endswith("_service.build_plan") for path in gui_calls)
    assert not any(path.endswith(".acquire") for path in gui_calls)

    imports = [
        (node.module, alias.name)
        for node in ast.walk(cli_resume)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]
    assert ("resume_service", "ResumeService") in imports
    dialog_import_names = {
        alias.name
        for node in ast.walk(dialog_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not {"hashlib", "sqlite3", "RunStateStore", "LeaseToken", "ResumePlan"}.intersection(
        dialog_import_names
    )

    forbidden_calls = {
        "acquire_lease",
        "compute_resume_plan_hash",
        "compute_launch_plan_hash",
        "sha256",
        "execute",
    }
    for label, node, calls in (
        ("CLI", cli_resume, cli_calls),
        ("GUI dialog", gui_dialog, gui_calls),
        ("GUI bridge", gui_bridge, bridge_calls),
    ):
        terminal_names = {path.rsplit(".", 1)[-1] for path in calls}
        assert forbidden_calls.isdisjoint(terminal_names), (
            f"{label} owns forbidden hash/SQL/CAS calls: "
            f"{sorted(forbidden_calls.intersection(terminal_names))}"
        )
        literals = {
            constant.value
            for constant in ast.walk(node)
            if isinstance(constant, ast.Constant) and isinstance(constant.value, str)
        }
        assert _RISK_CODES.isdisjoint(literals), (
            f"{label} independently classifies common risk codes: "
            f"{sorted(_RISK_CODES.intersection(literals))}"
        )

    contract = _prompt_resume_contract()
    for required in (
        "ResumeService.list_candidates()",
        "ResumeService.build_plan()",
        "expected_state_version",
        "resume_plan_hash",
        "既存 `hve resume`",
        "Prompt Edition controller 自身は先行または重複して `acquire()` を呼ばない",
        "独自の resume 判定や別の実行エンジンを追加しない",
    ):
        assert required in contract


def _unsupported_config(mode: str) -> Any:
    return SimpleNamespace(
        dry_run=False,
        fleet_mode_enabled=mode == "fleet",
        cloud_session_enabled=mode == "cloud",
        create_issues=mode == "cloud-agent",
        assign_copilot_agent=mode == "cloud-agent",
    )


@pytest.mark.parametrize(
    "mode",
    ("fleet", "cloud", "autopilot", "cloud-agent"),
)
def test_unsupported_new_run_stays_unregistered_and_public_resume_starts_no_child(
    runtime: _Runtime,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    """Unsupported modes retain new-run exclusion and fail closed on resume."""

    before_new_run = runtime.snapshot()
    if mode == "autopilot":
        def fake_autopilot(_args: Any) -> int:
            runtime.trace.autopilot_calls += 1
            return 0

        monkeypatch.setattr(
            runtime.hve_main,
            "_cmd_orchestrate_autopilot_chain",
            fake_autopilot,
        )
        assert _invoke_main(
            runtime,
            [
                "orchestrate",
                "--autopilot-chain",
                "aad-web,asdw-web",
                "--autopilot-dry-run",
            ],
        ) == 0
        assert runtime.trace.autopilot_calls == 1
    else:
        config = _unsupported_config(mode)
        assert runtime.resume_module.standard_execution_is_registerable(
            config,
            {},
            existing_execution_id=None,
        ) is False
        assert runtime.hve_main._register_standard_execution(
            _WORKFLOW_ID,
            config,
            {},
            ("orchestrate", "--workflow", _WORKFLOW_ID),
            args=SimpleNamespace(_execution_id=None),
        ) is None
    assert runtime.snapshot() == before_new_run

    unsupported_execution_id = f"execution-unsupported-{mode}"
    unsupported_instance_id = f"aas-unsupported-{mode}"
    with runtime.real_store_type(runtime.database_path) as setup_store:
        standard_descriptor = runtime.descriptor_type(
            instance_id=unsupported_instance_id,
            workflow_id=_WORKFLOW_ID,
            ordinal=0,
            mode="standard",
            argv=("orchestrate", "--workflow", _WORKFLOW_ID),
        )
        runtime.real_service_type(setup_store, runtime.repo_root).register_execution(
            "cli",
            (standard_descriptor,),
            execution_id=unsupported_execution_id,
            checkpoint_head=_LAUNCH_HEAD,
        )
        unsupported_descriptor = replace(
            standard_descriptor,
            mode=mode,
        )
        plan_json = runtime.resume_module.canonical_json(
            {
                "instances": [
                    runtime.resume_module._descriptor_payload(
                        unsupported_descriptor
                    )
                ],
                "checkpoint_head": _LAUNCH_HEAD,
            }
        )
        setup_store._connection.execute(
            "UPDATE executions SET plan_json = ?, launch_plan_hash = ? "
            "WHERE execution_id = ?",
            (
                plan_json,
                runtime.resume_module.compute_launch_plan_hash(
                    (unsupported_descriptor,)
                ),
                unsupported_execution_id,
            ),
        )
        setup_store._connection.execute(
            "UPDATE workflow_instances SET mode = ? "
            "WHERE execution_id = ? AND instance_id = ?",
            (mode, unsupported_execution_id, unsupported_instance_id),
        )

    before_resume = runtime.snapshot()
    child_count = len(runtime.trace.child_calls)
    code = _invoke_main(
        runtime,
        [
            "resume",
            unsupported_execution_id,
            "--action",
            "restart-step",
        ],
    )

    assert code != 0
    assert len(runtime.trace.child_calls) == child_count
    assert runtime.snapshot() == before_resume
    plans = [
        call["result"]
        for call in runtime.trace.build_calls
        if call["surface"] == "cli"
        and call["execution_id"] == unsupported_execution_id
    ]
    assert plans
    assert all("unsupported_mode" in plan.risk_reasons for plan in plans)
    assert runtime.trace.external_attempts == []