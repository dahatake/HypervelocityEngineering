"""Durable resume GUI RED contracts.

Traceability: FR-GUI-15, FR-GUI-38, FR-GUI-50, FR-LOCAL-SURFACE-02,
NFR-CONC-02, NFR-REL-03, and NFR-SEC-01.

The planned production modules are imported while each test is running so a
missing implementation remains a named failure instead of aborting collection.
All launchers and readers are fakes: this suite must not start a process or make
an Azure, GitHub, Copilot SDK, or network call.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence
from unittest.mock import MagicMock

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
)


_RESUME_MODULE = "hve.resume_service"
_STATE_MODULE = "hve.run_state_store"
_DIALOG_MODULE = "hve.gui.resume_dialog"


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _module(requirement: str, module_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"{requirement}: missing production module {exc.name or module_name}",
            pytrace=False,
        )


def _resume_api(requirement: str) -> Any:
    module = _module(requirement, _RESUME_MODULE)
    missing = [
        name
        for name in ("WorkflowDescriptor", "ResumePlan", "ResumeService")
        if not hasattr(module, name)
    ]
    if missing:
        pytest.fail(
            f"{requirement}: {_RESUME_MODULE} is missing API: {', '.join(missing)}",
            pytrace=False,
        )
    return module


def _state_api(requirement: str) -> Any:
    module = _module(requirement, _STATE_MODULE)
    if not hasattr(module, "DurableStateError"):
        pytest.fail(
            f"{requirement}: {_STATE_MODULE} is missing DurableStateError",
            pytrace=False,
        )
    return module


def _dialog_api(requirement: str) -> Any:
    module = _module(requirement, _DIALOG_MODULE)
    if not hasattr(module, "ResumeDialog"):
        pytest.fail(
            f"{requirement}: {_DIALOG_MODULE} is missing ResumeDialog",
            pytrace=False,
        )
    return module


def _required_attr(owner: Any, name: str, requirement: str) -> Any:
    value = getattr(owner, name, None)
    if not callable(value):
        pytest.fail(
            f"{requirement}: {owner.__name__ if isinstance(owner, type) else type(owner).__name__} "
            f"is missing callable {name}",
            pytrace=False,
        )
    return value


class _Candidate(dict[str, Any]):
    """Candidate test record usable through either mapping or attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _candidate(
    *,
    execution_id: str = "execution-visible-17",
    instance_id: str = "aas-1",
    workflow_id: str = "aas",
    status: str = "suspended",
    heartbeat_age_seconds: float = 17.25,
    mode: str = "standard",
    state_version: int = 41,
) -> _Candidate:
    return _Candidate(
        execution_id=execution_id,
        instance_id=instance_id,
        workflow_id=workflow_id,
        status=status,
        heartbeat_age_seconds=heartbeat_age_seconds,
        heartbeat_at="heartbeat-visible-17",
        mode=mode,
        state_version=state_version,
    )


def _plan(
    api: Any,
    *,
    execution_id: str = "execution-visible-17",
    instance_id: str = "aas-1",
    workflow_id: str = "aas",
    action: str | None = None,
    expected_state_version: int = 41,
    risk_reasons: Sequence[str] = (),
    missing_replay_keys: Sequence[str] = (),
    hash_character: str = "a",
) -> Any:
    return api.ResumePlan(
        execution_id=execution_id,
        instance_id=instance_id,
        workflow_id=workflow_id,
        action=action,
        expected_state_version=expected_state_version,
        risk_reasons=tuple(risk_reasons),
        missing_replay_keys=tuple(missing_replay_keys),
        argv=("orchestrate", "--workflow", workflow_id),
        resume_plan_hash=hash_character * 64,
    )


class _FakeResumeService:
    def __init__(
        self,
        candidates: Sequence[Any],
        resolver: Callable[..., Any],
    ) -> None:
        self._candidates = list(candidates)
        self._resolver = resolver
        self.list_calls = 0
        self.build_calls: list[dict[str, Any]] = []

    def list_candidates(self) -> list[Any]:
        self.list_calls += 1
        return list(self._candidates)

    def build_plan(
        self,
        execution_id: str,
        *,
        action: str | None = None,
        replay_values: Mapping[str, str] | None = None,
        current_head: str | None = None,
    ) -> Any:
        call = {
            "execution_id": execution_id,
            "action": action,
            "replay_values": (
                None if replay_values is None else dict(replay_values)
            ),
            "current_head": current_head,
        }
        self.build_calls.append(call)
        return self._resolver(**call)


def _dialog_text(dialog: QDialog) -> str:
    parts: list[str] = []
    parts.extend(label.text() for label in dialog.findChildren(QLabel))
    parts.extend(button.text() for button in dialog.findChildren(QAbstractButton))
    for combo in dialog.findChildren(QComboBox):
        parts.extend(combo.itemText(index) for index in range(combo.count()))
    for widget in dialog.findChildren(QListWidget):
        parts.extend(widget.item(index).text() for index in range(widget.count()))
    for widget in dialog.findChildren(QPlainTextEdit):
        parts.append(widget.toPlainText())
    for widget in dialog.findChildren(QTextEdit):
        parts.append(widget.toPlainText())
    return "\n".join(part for part in parts if part)


def _confirm_button(dialog: QDialog) -> QPushButton:
    button_box = dialog.findChild(QDialogButtonBox)
    if button_box is not None:
        for standard in (
            QDialogButtonBox.StandardButton.Ok,
            QDialogButtonBox.StandardButton.Yes,
            QDialogButtonBox.StandardButton.Apply,
            QDialogButtonBox.StandardButton.Save,
        ):
            button = button_box.button(standard)
            if button is not None:
                return button

    named = [
        button
        for button in dialog.findChildren(QPushButton)
        if any(
            marker in button.objectName().casefold()
            for marker in ("resume", "confirm", "accept")
        )
    ]
    if len(named) == 1:
        return named[0]
    pytest.fail(
        "FR-GUI-50: ResumeDialog has no unambiguous confirmation button",
        pytrace=False,
    )


def _combo_values(combo: QComboBox) -> set[str]:
    values: set[str] = set()
    for index in range(combo.count()):
        values.add(str(combo.itemText(index)))
        data = combo.itemData(index)
        if data is not None:
            values.add(str(data))
    return values


def _action_combo(dialog: QDialog) -> QComboBox:
    required = {"reuse-session", "restart-step"}
    for combo in dialog.findChildren(QComboBox):
        if required.issubset(_combo_values(combo)):
            return combo
    pytest.fail(
        "FR-GUI-50: ResumeDialog does not expose both common recovery actions",
        pytrace=False,
    )


def _select_combo_value(combo: QComboBox, value: str) -> None:
    for index in range(combo.count()):
        if value in {str(combo.itemText(index)), str(combo.itemData(index))}:
            combo.setCurrentIndex(index)
            return
    pytest.fail(f"ResumeDialog combo does not contain {value!r}", pytrace=False)


def _replay_edit(dialog: QDialog, key: str) -> QLineEdit:
    for label in dialog.findChildren(QLabel):
        if key in label.text() and isinstance(label.buddy(), QLineEdit):
            return label.buddy()
    for edit in dialog.findChildren(QLineEdit):
        metadata = " ".join(
            (
                edit.objectName(),
                edit.accessibleName(),
                edit.placeholderText(),
            )
        )
        if key in metadata:
            return edit
    pytest.fail(
        f"NFR-SEC-01: ResumeDialog has no input for missing replay key {key!r}",
        pytrace=False,
    )


def _selected_plan(dialog: QDialog) -> Any:
    if not hasattr(dialog, "selected_plan"):
        pytest.fail(
            "FR-GUI-50: ResumeDialog is missing selected_plan()",
            pytrace=False,
        )
    selected = getattr(dialog, "selected_plan")
    return selected() if callable(selected) else selected


def _selected_replay_values(dialog: QDialog) -> dict[str, str]:
    if not hasattr(dialog, "selected_replay_values"):
        pytest.fail(
            "FR-GUI-50: ResumeDialog is missing selected_replay_values()",
            pytrace=False,
        )
    selected = getattr(dialog, "selected_replay_values")
    values = selected() if callable(selected) else selected
    assert isinstance(values, Mapping)
    return {str(key): str(value) for key, value in values.items()}


def _new_dialog(service: Any, *, current_head: str = "head-now") -> QDialog:
    dialog_api = _dialog_api("FR-GUI-50 resume dialog")
    dialog = dialog_api.ResumeDialog(service, current_head=current_head)
    assert isinstance(dialog, QDialog)
    return dialog


class TestResumeDialog:
    def test_dialog_opens_only_from_explicit_resume_action(
        self,
        qapp: QApplication,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        dialog_api = _dialog_api("FR-GUI-50 explicit Resume action")
        api = _resume_api("FR-GUI-50 explicit Resume action")
        main_window_module = importlib.import_module("hve.gui.main_window")
        callback = _required_attr(
            main_window_module.MainWindow,
            "_on_resume_clicked",
            "FR-GUI-50 explicit Resume action",
        )
        plan = _plan(api)
        service = _FakeResumeService([_candidate()], lambda **_: plan)
        constructed: list[Any] = []

        class _AcceptedDialog:
            def __init__(self, supplied_service: Any, *args: Any, **kwargs: Any) -> None:
                constructed.append((supplied_service, args, kwargs))

            def exec(self) -> int:
                return QDialog.DialogCode.Accepted

            def selected_plan(self) -> Any:
                return plan

            def selected_replay_values(self) -> dict[str, str]:
                return {}

            def clear_transient_state(self) -> None:
                constructed.append("cleared")

        monkeypatch.setattr(dialog_api, "ResumeDialog", _AcceptedDialog)
        monkeypatch.setattr(
            main_window_module,
            "ResumeDialog",
            _AcceptedDialog,
            raising=False,
        )

        window = MagicMock()
        window.tr = lambda text: text
        window._resume_service = service
        window._durable_resume_service = service
        window._get_resume_service.return_value = service
        window._create_resume_service.return_value = service
        window._page_workbench.is_running.return_value = False

        callback(window)
        qapp.processEvents()

        assert len(constructed) == 2
        assert constructed[0][0] is service
        assert constructed[1] == "cleared"
        window._page_workbench.start_resume.assert_called_once()
        call = window._page_workbench.start_resume.call_args
        assert plan in call.args or plan in call.kwargs.values()
        assert call.kwargs.get("replay_values", {}) == {}

    def test_zero_candidates_disables_resume_without_building_a_plan(
        self,
        qapp: QApplication,
    ) -> None:
        _dialog_api("FR-GUI-50 zero candidates")
        _resume_api("FR-GUI-50 zero candidates")
        service = _FakeResumeService(
            [],
            lambda **_: pytest.fail("build_plan must not run for zero candidates"),
        )
        dialog = _new_dialog(service)
        try:
            qapp.processEvents()
            text = _dialog_text(dialog).casefold()
            assert service.list_calls == 1
            assert service.build_calls == []
            assert _confirm_button(dialog).isEnabled() is False
            assert "0" in text
            assert "候補" in text or "candidate" in text
        finally:
            dialog.deleteLater()

    def test_safe_plan_displays_common_state_and_requires_confirmation(
        self,
        qapp: QApplication,
    ) -> None:
        _dialog_api("FR-GUI-50 safe confirmation")
        api = _resume_api("FR-GUI-50 safe confirmation")
        candidate = _candidate()
        plan = _plan(api)
        service = _FakeResumeService([candidate], lambda **_: plan)
        dialog = _new_dialog(service)
        try:
            qapp.processEvents()
            text = _dialog_text(dialog)
            for expected in (
                candidate.execution_id,
                candidate.workflow_id,
                candidate.status,
                str(candidate.state_version),
                candidate.heartbeat_at,
            ):
                assert expected in text
            assert service.build_calls == [
                {
                    "execution_id": candidate.execution_id,
                    "action": None,
                    "replay_values": None,
                    "current_head": "head-now",
                }
            ]
            confirm = _confirm_button(dialog)
            assert confirm.isEnabled() is True
            assert dialog.result() != QDialog.DialogCode.Accepted
            confirm.click()
            assert dialog.result() == QDialog.DialogCode.Accepted
            assert _selected_plan(dialog) is plan
        finally:
            dialog.deleteLater()

    def test_risky_plan_requires_an_explicit_common_service_action(
        self,
        qapp: QApplication,
    ) -> None:
        _dialog_api("FR-GUI-50 risk action")
        api = _resume_api("FR-GUI-50 risk action")
        risk = "RISK-FROM-COMMON-SERVICE"
        preview = _plan(api, risk_reasons=(risk,))
        selected = _plan(
            api,
            action="restart-step",
            risk_reasons=(risk,),
            hash_character="b",
        )

        def resolve(*, action: str | None, **_: Any) -> Any:
            return selected if action == "restart-step" else preview

        service = _FakeResumeService([_candidate()], resolve)
        dialog = _new_dialog(service)
        try:
            qapp.processEvents()
            assert risk in _dialog_text(dialog)
            assert _confirm_button(dialog).isEnabled() is False

            _select_combo_value(_action_combo(dialog), "restart-step")
            qapp.processEvents()

            assert service.build_calls[-1]["action"] == "restart-step"
            assert _confirm_button(dialog).isEnabled() is True
            _confirm_button(dialog).click()
            assert _selected_plan(dialog) is selected
        finally:
            dialog.deleteLater()

    def test_missing_replay_values_are_collected_before_plan_rebuild(
        self,
        qapp: QApplication,
    ) -> None:
        _dialog_api("NFR-SEC-01 missing replay values")
        api = _resume_api("NFR-SEC-01 missing replay values")
        keys = ("additional_prompt", "issue_title")
        incomplete = _plan(api, missing_replay_keys=keys)
        complete = _plan(api, hash_character="c")

        def resolve(
            *, replay_values: Mapping[str, str] | None, **_: Any
        ) -> Any:
            if replay_values and all(replay_values.get(key) for key in keys):
                return complete
            return incomplete

        service = _FakeResumeService([_candidate()], resolve)
        dialog = _new_dialog(service)
        try:
            qapp.processEvents()
            assert _confirm_button(dialog).isEnabled() is False
            for key in keys:
                assert key in _dialog_text(dialog)

            first = _replay_edit(dialog, keys[0])
            second = _replay_edit(dialog, keys[1])
            first.setText("re-entered prompt")
            first.editingFinished.emit()
            second.setText("re-entered title")
            second.editingFinished.emit()
            qapp.processEvents()

            assert service.build_calls[-1]["replay_values"] == {
                "additional_prompt": "re-entered prompt",
                "issue_title": "re-entered title",
            }
            assert _confirm_button(dialog).isEnabled() is True
            _confirm_button(dialog).click()
            assert _selected_plan(dialog) is complete
            assert _selected_replay_values(dialog) == {
                "additional_prompt": "re-entered prompt",
                "issue_title": "re-entered title",
            }
            clear_transient = _required_attr(
                dialog,
                "clear_transient_state",
                "NFR-SEC-01 transient replay cleanup",
            )
            clear_transient()
            assert _selected_plan(dialog) is None
            assert _selected_replay_values(dialog) == {}
            assert first.text() == ""
            assert second.text() == ""
        finally:
            dialog.deleteLater()

    def test_stale_cas_is_shown_once_without_automatic_retry(
        self,
        qapp: QApplication,
    ) -> None:
        _dialog_api("NFR-CONC-02 stale CAS")
        api = _resume_api("NFR-CONC-02 stale CAS")
        state_api = _state_api("NFR-CONC-02 stale CAS")
        preview = _plan(api, risk_reasons=("lease expired",))
        marker = "STALE-CAS-FROM-COMMON-SERVICE"

        def resolve(*, action: str | None, **_: Any) -> Any:
            if action is not None:
                raise state_api.DurableStateError(marker)
            return preview

        service = _FakeResumeService([_candidate()], resolve)
        dialog = _new_dialog(service)
        try:
            _select_combo_value(_action_combo(dialog), "restart-step")
            qapp.processEvents()
            qapp.processEvents()

            action_calls = [
                call for call in service.build_calls if call["action"] is not None
            ]
            assert len(action_calls) == 1
            assert marker in _dialog_text(dialog)
            assert _confirm_button(dialog).isEnabled() is False
        finally:
            dialog.deleteLater()

    def test_unsupported_mode_error_is_displayed_from_the_common_service(
        self,
        qapp: QApplication,
    ) -> None:
        _dialog_api("FR-GUI-50 unsupported mode")
        _resume_api("FR-GUI-50 unsupported mode")
        state_api = _state_api("FR-GUI-50 unsupported mode")
        marker = "UNSUPPORTED-MODE-FROM-COMMON-SERVICE"

        def unsupported(**_: Any) -> Any:
            raise state_api.DurableStateError(marker)

        service = _FakeResumeService(
            [_candidate(mode="cloud")],
            unsupported,
        )
        dialog = _new_dialog(service)
        try:
            qapp.processEvents()
            assert len(service.build_calls) == 1
            assert marker in _dialog_text(dialog)
            assert _confirm_button(dialog).isEnabled() is False
            assert _selected_plan(dialog) is None
        finally:
            dialog.deleteLater()

    def test_risk_state_is_never_reclassified_from_candidate_fields(
        self,
        qapp: QApplication,
    ) -> None:
        _dialog_api("FR-LOCAL-SURFACE-02 service-only risk decision")
        api = _resume_api("FR-LOCAL-SURFACE-02 service-only risk decision")

        service_safe = _FakeResumeService(
            [_candidate(status="failed", heartbeat_age_seconds=999.0)],
            lambda **_: _plan(api),
        )
        safe_dialog = _new_dialog(service_safe)
        service_risky = _FakeResumeService(
            [_candidate(status="suspended", heartbeat_age_seconds=0.0)],
            lambda **_: _plan(
                api,
                risk_reasons=("OUTPUT-RISK-FROM-COMMON-SERVICE",),
            ),
        )
        risky_dialog = _new_dialog(service_risky)
        try:
            qapp.processEvents()
            assert _confirm_button(safe_dialog).isEnabled() is True
            assert _confirm_button(risky_dialog).isEnabled() is False
            assert "OUTPUT-RISK-FROM-COMMON-SERVICE" in _dialog_text(risky_dialog)
        finally:
            safe_dialog.deleteLater()
            risky_dialog.deleteLater()


def test_hve_resume_is_not_presented_as_copilot_cli_resume(
    qapp: QApplication,
) -> None:
    _dialog_api("FR-GUI-15 HVE versus Copilot resume boundary")
    api = _resume_api("FR-GUI-15 HVE versus Copilot resume boundary")
    service = _FakeResumeService([_candidate()], lambda **_: _plan(api))
    dialog = _new_dialog(service)
    try:
        qapp.processEvents()
        text = _dialog_text(dialog).casefold()
        assert "execution-visible-17" in text
        assert "/resume" not in text
        assert "copilot cli" not in text
        assert "model checkpoint" not in text
        assert "モデルチェックポイント" not in text
    finally:
        dialog.deleteLater()


def _field(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        return record[name]
    return getattr(record, name)


class _RecordingResumeService:
    def __init__(self, execution_ids: Sequence[str], events: list[str]) -> None:
        self._execution_ids = list(execution_ids)
        self._next_execution = 0
        self._reserved: set[str] = set()
        self.events = events
        self.registration_calls: list[dict[str, Any]] = []
        self.register_error: BaseException | None = None

    def new_execution_id(self) -> str:
        if self._next_execution >= len(self._execution_ids):
            raise AssertionError("test service ran out of execution IDs")
        execution_id = self._execution_ids[self._next_execution]
        self._next_execution += 1
        self._reserved.add(execution_id)
        return execution_id

    def register_execution(
        self,
        surface: str,
        descriptors: Sequence[Any],
        *,
        execution_id: str | None = None,
        checkpoint_head: str | None = None,
    ) -> str:
        if execution_id is None:
            execution_id = self.new_execution_id()
        self.events.append("register")
        self.registration_calls.append(
            {
                "surface": surface,
                "descriptors": tuple(descriptors),
                "execution_id": execution_id,
                "checkpoint_head": checkpoint_head,
            }
        )
        if self.register_error is not None:
            raise self.register_error
        return execution_id


class _SignalProbe:
    def __init__(self) -> None:
        self._slots: list[Callable[..., Any]] = []

    def connect(self, slot: Callable[..., Any]) -> None:
        self._slots.append(slot)

    def emit(self, *args: Any) -> None:
        for slot in tuple(self._slots):
            slot(*args)


class _FakeProcess:
    _next_pid = 2000

    def __init__(self, args: Sequence[str] | None = None) -> None:
        type(self)._next_pid += 1
        self.pid = type(self)._next_pid
        self.returncode: int | None = None
        self.stdout = None
        self.args = args

    def poll(self) -> int | None:
        return self.returncode


class _FakeReader:
    def __init__(self, process: _FakeProcess, *, parent: Any = None) -> None:
        self._proc = process
        self.parent = parent
        self.line_received = _SignalProbe()
        self.finished_with_code = _SignalProbe()
        self.started = False
        self.stop_calls = 0
        self.delete_calls = 0
        self.wait_calls: list[int] = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stop_calls += 1

    def deleteLater(self) -> None:
        self.delete_calls += 1

    def wait(self, timeout: int) -> None:
        self.wait_calls.append(timeout)


class _NoDiskStore:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_NoDiskStore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None


class _NormalPlanHarness:
    def __init__(
        self,
        *,
        window: Any,
        page: Any,
        readers: list[_FakeReader],
        launch_argvs: list[list[str]],
        qapp: QApplication,
    ) -> None:
        self.window = window
        self.page = page
        self.readers = readers
        self.launch_argvs = launch_argvs
        self.qapp = qapp

    def start(
        self,
        workflow_ids: Sequence[str],
        *,
        legacy_run_id: str | None = None,
    ) -> None:
        main_window_module = importlib.import_module("hve.gui.main_window")
        self.window._selected_workflow_ids = list(workflow_ids)
        self.window._test_legacy_run_id = legacy_run_id
        main_window_module.MainWindow._on_run_clicked(
            self.window,
            skip_step1_precheck=True,
        )

    def finish_current_job(self) -> None:
        assert self.readers
        reader = self.readers[-1]
        reader._proc.returncode = 0
        reader.finished_with_code.emit(0)
        self.qapp.processEvents()
        self.qapp.processEvents()
        assert self.page.is_running() is False

    def stop_and_close(self) -> None:
        if self.page.is_running():
            self.page.stop_orchestrator()
            reader = self.readers[-1]
            reader._proc.returncode = 0
            reader.finished_with_code.emit(0)
            self.qapp.processEvents()
        self.page.deleteLater()


def _normal_plan_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    service: _RecordingResumeService,
) -> _NormalPlanHarness:
    api = _resume_api("FR-GUI-50 normal plan registration")
    dialog_api = _dialog_api("FR-GUI-50 normal Start must not open Resume dialog")
    main_window_module = importlib.import_module("hve.gui.main_window")
    page_module = importlib.import_module("hve.gui.page_workbench")
    args_module = importlib.import_module("hve.gui.orchestrate_args")

    def service_factory(*args: Any, **kwargs: Any) -> _RecordingResumeService:
        return service

    monkeypatch.setattr(api, "ResumeService", service_factory)
    for module in (main_window_module, page_module):
        monkeypatch.setattr(
            module,
            "ResumeService",
            service_factory,
            raising=False,
        )

    try:
        state_module = importlib.import_module(_STATE_MODULE)
    except ModuleNotFoundError:
        state_module = None
    if state_module is not None:
        monkeypatch.setattr(
            state_module,
            "default_state_path",
            lambda: tmp_path / "unused-state.sqlite3",
            raising=False,
        )
        monkeypatch.setattr(
            state_module,
            "RunStateStore",
            _NoDiskStore,
            raising=False,
        )
    for module in (main_window_module, page_module):
        if hasattr(module, "RunStateStore"):
            monkeypatch.setattr(module, "RunStateStore", _NoDiskStore)

    def forbidden_process(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("T08 must not start a real process")

    monkeypatch.setattr(subprocess, "Popen", forbidden_process)
    monkeypatch.setattr(subprocess, "run", forbidden_process)

    readers: list[_FakeReader] = []
    launch_argvs: list[list[str]] = []

    def fake_launch(
        argv: Sequence[str],
        *,
        env_overrides: Mapping[str, str] | None = None,
    ) -> _FakeProcess:
        launch_argvs.append(list(argv))
        service.events.append("launch")
        return _FakeProcess()

    def reader_factory(
        process: _FakeProcess,
        *,
        parent: Any = None,
    ) -> _FakeReader:
        reader = _FakeReader(process, parent=parent)
        readers.append(reader)
        return reader

    monkeypatch.setattr(page_module, "launch_orchestrator", fake_launch)
    monkeypatch.setattr(page_module, "SubprocessReader", reader_factory)

    def forbidden_dialog(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("normal Start must not open ResumeDialog")

    monkeypatch.setattr(dialog_api, "ResumeDialog", forbidden_dialog)
    monkeypatch.setattr(
        main_window_module,
        "ResumeDialog",
        forbidden_dialog,
        raising=False,
    )
    monkeypatch.setattr(
        main_window_module,
        "_sort_workflows_by_dependencies",
        lambda workflow_ids: list(workflow_ids),
    )
    monkeypatch.setattr(
        main_window_module,
        "resolve_head_commit",
        lambda _repo_root: "head-gui-registration",
    )

    page = page_module.WorkbenchPage()
    page._resume_service = service
    page._durable_resume_service = service
    page._get_resume_service = lambda: service
    page._create_resume_service = lambda: service

    window = MagicMock()
    window.tr = lambda text: text
    window._repo_root = tmp_path
    window._resume_service = service
    window._durable_resume_service = service
    window._get_resume_service.return_value = service
    window._create_resume_service.return_value = service
    window._page_workbench = page
    window._register_normal_gui_plan.side_effect = (
        lambda args_queue: main_window_module.MainWindow._register_normal_gui_plan(
            window, args_queue
        )
    )
    window._page_options.validate.return_value = (True, "")
    window._page_workflow.is_autopilot_enabled.return_value = False
    window._resolve_steps_for_workflow.side_effect = (
        lambda workflow_id, steps: (steps, set())
    )
    window._run_step1_unified_precheck.return_value = True

    def build_args(workflow_id: str, *, repo_root: Path) -> Any:
        return args_module.OrchestrateArgs(
            workflow=workflow_id,
            repo_root=repo_root,
            resume_run=window._test_legacy_run_id,
        )

    window._test_legacy_run_id = None
    window._page_options.build_args_for_workflow.side_effect = build_args

    return _NormalPlanHarness(
        window=window,
        page=page,
        readers=readers,
        launch_argvs=launch_argvs,
        qapp=qapp,
    )


class TestNormalPlanRegistration:
    def test_unknown_head_starts_no_registered_child(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        main_window_module = importlib.import_module("hve.gui.main_window")
        events: list[str] = []
        service = _RecordingResumeService(["execution-no-head"], events)
        harness = _normal_plan_harness(tmp_path, monkeypatch, qapp, service)
        warnings: list[tuple[Any, ...]] = []
        monkeypatch.setattr(
            main_window_module,
            "resolve_head_commit",
            lambda _repo_root: "unknown",
        )
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *args, **_kwargs: warnings.append(args),
        )
        try:
            harness.start(("aas",))

            assert service.registration_calls == []
            assert harness.launch_argvs == []
            assert warnings
        finally:
            harness.stop_and_close()

    def test_queue_is_registered_once_before_launch_and_children_share_identity(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        events: list[str] = []
        service = _RecordingResumeService(["execution-gui-one"], events)
        harness = _normal_plan_harness(tmp_path, monkeypatch, qapp, service)
        try:
            harness.start(("ard", "aas"))

            assert events[:2] == ["register", "launch"]
            assert len(service.registration_calls) == 1
            registration = service.registration_calls[0]
            assert registration["surface"] == "gui"
            descriptors = registration["descriptors"]
            assert [_field(item, "workflow_id") for item in descriptors] == [
                "ard",
                "aas",
            ]
            assert [_field(item, "ordinal") for item in descriptors] == [0, 1]
            instance_ids = [_field(item, "instance_id") for item in descriptors]
            assert len(set(instance_ids)) == 2

            queued = harness.page._args_queue
            assert [getattr(item, "_execution_id", None) for item in queued] == [
                registration["execution_id"],
                registration["execution_id"],
            ]
            assert [getattr(item, "_instance_id", None) for item in queued] == instance_ids
            assert len(harness.launch_argvs) == 1
            first_launch = harness.launch_argvs[0]
            assert first_launch[first_launch.index("--execution-id") + 1] == (
                registration["execution_id"]
            )
            assert first_launch[first_launch.index("--instance-id") + 1] == (
                instance_ids[0]
            )
            assert "--expected-state-version" not in first_launch
            assert "--lease-owner" not in first_launch
        finally:
            harness.stop_and_close()

    def test_each_start_in_the_same_window_gets_a_distinct_execution_id(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        events: list[str] = []
        service = _RecordingResumeService(
            ("execution-gui-first", "execution-gui-second"),
            events,
        )
        harness = _normal_plan_harness(tmp_path, monkeypatch, qapp, service)
        try:
            harness.start(("ard",))
            first_id = getattr(harness.page._args_queue[0], "_execution_id", None)
            harness.finish_current_job()

            harness.start(("aas",))
            second_id = getattr(harness.page._args_queue[0], "_execution_id", None)

            assert len(service.registration_calls) == 2
            assert first_id == service.registration_calls[0]["execution_id"]
            assert second_id == service.registration_calls[1]["execution_id"]
            assert first_id != second_id
        finally:
            harness.stop_and_close()

    def test_registration_failure_starts_no_child_and_mutates_no_args(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        state_api = _state_api("FR-GUI-50 registration failure")
        events: list[str] = []
        service = _RecordingResumeService(["execution-failed"], events)
        service.register_error = state_api.DurableStateError(
            "injected GUI registration failure"
        )
        harness = _normal_plan_harness(tmp_path, monkeypatch, qapp, service)
        warnings: list[tuple[Any, ...]] = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *args, **_kwargs: warnings.append(args),
        )
        try:
            harness.start(("aas",))

            assert len(service.registration_calls) == 1
            assert harness.launch_argvs == []
            assert harness.page._args_queue == []
            assert events == ["register"]
            assert warnings
        finally:
            harness.stop_and_close()


def test_legacy_run_id_is_not_imported_into_a_new_execution(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    legacy_run_id = "legacy-jsonl-run-42"
    service = _RecordingResumeService(["unused-modern-execution"], events)
    harness = _normal_plan_harness(tmp_path, monkeypatch, qapp, service)
    try:
        harness.start(("aas",), legacy_run_id=legacy_run_id)

        queued = harness.page._args_queue[0]
        assert service.registration_calls == []
        assert queued.resume_run == legacy_run_id
        assert getattr(queued, "_execution_id", None) is None
        assert getattr(queued, "_instance_id", None) is None
    finally:
        harness.stop_and_close()


class TestResumeChildLifecycle:
    def test_resume_child_reuses_workbench_log_stop_and_finish_path(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        api = _resume_api("FR-GUI-50 resume child lifecycle")
        page_module = importlib.import_module("hve.gui.page_workbench")
        plan = _plan(api, action="restart-step")
        launched: list[list[str]] = []
        readers: list[_FakeReader] = []

        def forbidden_process(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("T08 must not start a real process")

        def fake_launch(
            argv: Sequence[str],
            *,
            env_overrides: Mapping[str, str] | None = None,
        ) -> _FakeProcess:
            launched.append(list(argv))
            return _FakeProcess()

        def reader_factory(
            process: _FakeProcess,
            *,
            parent: Any = None,
        ) -> _FakeReader:
            reader = _FakeReader(process, parent=parent)
            readers.append(reader)
            return reader

        monkeypatch.setattr(subprocess, "Popen", forbidden_process)
        monkeypatch.setattr(subprocess, "run", forbidden_process)
        monkeypatch.setattr(page_module, "launch_orchestrator", fake_launch)
        monkeypatch.setattr(page_module, "SubprocessReader", reader_factory)

        page = page_module.WorkbenchPage()
        logs: list[str] = []
        page._log_pane.append_line = logs.append
        completed: list[int] = []
        page.process_finished.connect(completed.append)
        start_resume = _required_attr(
            page,
            "start_resume",
            "FR-GUI-50 resume child Workbench convergence",
        )

        try:
            start_resume(plan, repo_root=tmp_path)
            assert launched == [[
                "resume",
                plan.execution_id,
                "--action",
                plan.action,
                "--expected-resume-hash",
                plan.resume_plan_hash,
            ]]
            assert len(readers) == 1
            reader = readers[0]
            assert reader.started is True

            reader.line_received.emit("RESUME-LOG-THROUGH-WORKBENCH")
            assert any("RESUME-LOG-THROUGH-WORKBENCH" in line for line in logs)

            page.stop_orchestrator()
            assert reader.stop_calls == 1
            reader._proc.returncode = 0
            reader.finished_with_code.emit(0)
            qapp.processEvents()

            assert completed == [0]
            assert page.is_running() is False
        finally:
            page.deleteLater()

    def test_resume_replay_plaintext_is_scrubbed_after_process_launch(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        api = _resume_api("NFR-SEC-01 GUI replay lifetime")
        page_module = importlib.import_module("hve.gui.page_workbench")
        plan = _plan(api, action="restart-step")
        sentinel = "TRANSIENT-REPLAY-SENTINEL"
        launched: list[list[str]] = []
        readers: list[_FakeReader] = []

        monkeypatch.setattr(
            page_module,
            "launch_orchestrator",
            lambda argv, **_kwargs: (
                launched.append(list(argv)) or _FakeProcess(argv)
            ),
        )
        monkeypatch.setattr(
            page_module,
            "SubprocessReader",
            lambda process, parent=None: (
                readers.append(_FakeReader(process, parent=parent)) or readers[-1]
            ),
        )

        page = page_module.WorkbenchPage()
        try:
            page.start_resume(
                plan,
                repo_root=tmp_path,
                replay_values={"additional_prompt": sentinel},
            )

            assert sentinel in repr(launched)
            assert sentinel not in repr(page._explicit_argv_queue)
            assert sentinel not in repr(readers[0]._proc.args)
            readers[0]._proc.returncode = 0
            readers[0].finished_with_code.emit(0)
            qapp.processEvents()
        finally:
            page.deleteLater()