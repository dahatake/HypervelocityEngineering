"""FR-GUI-51: GUI startup の Work IQ capability 表示・操作契約。"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve import workiq  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _capability(state: str):
    return workiq.WorkIQCapability(
        state=state,
        reason_code=state,
        enabled_server_names=("workiq",) if state == "ready" else (),
    )


def _resource_snapshot(state: str):
    from hve.toolsearch.resource_inventory import ResourceItem, ResourceSnapshot

    return ResourceSnapshot(
        plugin_state="ready" if state == "ready" else "unverified",
        mcp_state="ready" if state in {"ready", "not-configured"} else "unverified",
        skill_state="ready" if state == "ready" else "unverified",
        skill_ownership_state="ready" if state == "ready" else "unverified",
        plugins=(),
        mcp_servers=(
            ResourceItem(
                kind="mcp_server",
                name="workiq",
                enabled=True,
                source_kind="plugin",
            ),
        ) if state == "ready" else (),
        skills=(),
    )


def _workiq_inputs(widget):
    # FR-GUI-51（v3.38）: capability に連動するのは「Work IQ を知識源に加える」だけ。
    return (widget.workiq,)


def test_c4_stays_visible_but_disables_inputs_and_explains_saved_intent(qapp) -> None:
    from hve.gui.page_options import _C4WorkIQ

    widget = _C4WorkIQ()
    try:
        widget.show()
        qapp.processEvents()
        widget.workiq.setChecked(True)
        widget.set_workiq_capability(_capability("not-configured"), saved_requested=True)

        assert widget.isVisible() is True
        assert widget.workiq.isChecked() is True
        assert all(control.isEnabled() is False for control in _workiq_inputs(widget))
        status = widget.workiq_availability_status.text()
        assert "保存設定: 有効" in status
        assert "この起動: 無効" in status
        assert "未設定" in status
    finally:
        widget.deleteLater()


def test_unverified_disables_inputs_and_shows_unavailable_state(qapp) -> None:
    from hve.gui.page_options import _C4WorkIQ

    widget = _C4WorkIQ()
    try:
        widget.set_workiq_capability(_capability("unverified"), saved_requested=True)

        assert all(control.isEnabled() is False for control in _workiq_inputs(widget))
        assert "確認不能" in widget.workiq_availability_status.text()
    finally:
        widget.deleteLater()


def test_checking_state_disables_inputs_and_ready_reenables_them(qapp) -> None:
    from hve.gui.page_options import _C4WorkIQ

    widget = _C4WorkIQ()
    try:
        widget.set_workiq_capability(None, saved_requested=False)
        assert all(control.isEnabled() is False for control in _workiq_inputs(widget))
        assert "確認中" in widget.workiq_availability_status.text()

        widget.set_workiq_capability(_capability("ready"), saved_requested=False)
        assert all(control.isEnabled() is True for control in _workiq_inputs(widget))
        assert "設定済み" in widget.workiq_availability_status.text()
    finally:
        widget.deleteLater()


def test_knowledge_sources_field_stays_editable_and_reaches_args(qapp) -> None:
    """FR-KD-01 / FR-GUI-51: 知識源欄は capability によらず編集でき、argv へ渡る。"""
    from hve.gui.orchestrate_args import OrchestrateArgs
    from hve.gui.page_options import _C4WorkIQ

    widget = _C4WorkIQ()
    try:
        widget.set_workiq_capability(_capability("not-configured"), saved_requested=False)
        assert widget.knowledge_sources.isEnabled() is True
        widget.knowledge_sources.setText(" confluence,jira ")
        args = OrchestrateArgs(workflow="aas")
        widget.to_args(args)
        assert args.knowledge_sources == "confluence,jira"
        argv = args.to_argv()
        index = argv.index("--knowledge-source")
        assert argv[index + 1] == "confluence,jira"
        for removed in ("workiq_akm_review", "workiq_dxx", "workiq_prompt_qa", "workiq_per_question_timeout"):
            assert not hasattr(widget, removed)
    finally:
        widget.deleteLater()


def test_c11_workiq_source_is_disabled_without_unchecking(qapp) -> None:
    from hve.gui.page_options import _C11AKM

    widget = _C11AKM()
    try:
        widget.sources_workiq.setChecked(True)
        widget.set_workiq_capability(_capability("not-configured"))

        assert widget.sources_workiq.isChecked() is True
        assert widget.sources_workiq.isEnabled() is False
        assert widget.sources_qa.isEnabled() is True
        assert widget.sources_original_docs.isEnabled() is True
    finally:
        widget.deleteLater()


def test_options_page_normalizes_effective_args_without_changing_saved_widgets(qapp) -> None:
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    try:
        page.set_workflow("akm")
        page.c4.workiq.setChecked(True)
        page.c4.knowledge_sources.setText("jira")
        page.c11.sources_workiq.setChecked(True)
        page.c11.sources_qa.setChecked(True)
        page.c11.sources_original_docs.setChecked(False)
        page.set_workiq_capability(_capability("not-configured"))

        args = page.build_args_for_workflow("akm")

        assert page.c4.workiq.isChecked() is True
        assert page.c4.knowledge_sources.text() == "jira"
        assert page.c11.sources_workiq.isChecked() is True
        assert args.workiq is False
        assert args.knowledge_sources == "jira"
        assert args.sources == "qa"
    finally:
        page.deleteLater()


def test_saved_workiq_request_blocks_navigation_only_while_checking(qapp) -> None:
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    try:
        page.c4.workiq.setChecked(True)
        page.set_workiq_capability(None)
        assert page.is_workiq_check_pending() is True

        page.set_workiq_capability(_capability("not-configured"))
        assert page.is_workiq_check_pending() is False
    finally:
        page.deleteLater()


def test_checking_blocks_navigation_even_without_saved_workiq(qapp) -> None:
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    try:
        page.set_workiq_capability(None)
        assert page.is_workiq_check_pending() is True
    finally:
        page.deleteLater()


def test_workiq_screen_has_no_hve_auth_or_removed_runtime_controls(qapp) -> None:
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    try:
        for name in (
            "workiq_auth_requested",
            "workiq_auth_button",
            "workiq_auth_status",
            "workiq_prompt_review",
            "workiq_request_timeout",
        ):
            assert not hasattr(page.c4, name)
        assert not hasattr(page, "workiq_auth_requested")
        assert not hasattr(page.c11, "workiq_auth_requested")
    finally:
        page.deleteLater()


def test_workiq_availability_is_visible_in_akm_workflow_group(qapp) -> None:
    from hve.gui.page_options import OptionsPage

    page = OptionsPage()
    try:
        page.set_workflow("akm", "Knowledge Management")
        page.set_workiq_capability(_capability("not-configured"))
        page.show()
        qapp.processEvents()

        assert page.c4.workiq_availability_status.isVisible() is True
        assert "未設定" in page.c4.workiq_availability_status.text()
    finally:
        page.deleteLater()


def test_run_app_starts_resource_snapshot_before_blocking_github_auth(qapp, monkeypatch) -> None:
    from hve.gui import app as app_module

    calls: list[str] = []
    monkeypatch.setattr(
        app_module,
        "_open_first_window",
        lambda initial_catalog=None: calls.append("window"),
    )
    monkeypatch.setattr(app_module, "_run_startup_github_auth", lambda: calls.append("github"))
    monkeypatch.setattr(app_module, "start_startup_index_refresh", lambda _root: False)
    monkeypatch.setattr(
        app_module,
        "start_startup_resource_snapshot_check",
        lambda _repo_root=None: calls.append("resource") or True,
    )
    monkeypatch.setattr(
        app_module,
        "_shutdown_resource_workers",
        lambda: calls.append("cleanup"),
    )
    monkeypatch.setattr(QApplication, "exec", lambda _self: 0)

    monkeypatch.setattr(app_module, "_open_windows", [])
    assert app_module.run_app(None) == 0
    assert calls == ["window", "resource", "github", "cleanup"]


def test_static_worker_start_failure_is_unverified_and_not_retried(
    qapp, monkeypatch
) -> None:
    from hve.gui import app as app_module

    received: list[object] = []

    class _Signal:
        def connect(self, _callback):
            return None

    class _Thread:
        done = _Signal()
        finished = _Signal()

        def __init__(self, *_args, **_kwargs):
            return None

        def start(self):
            raise RuntimeError("synthetic start failure")

        def requestInterruption(self):
            return None

        def deleteLater(self):
            return None

    monkeypatch.setattr(app_module, "_StartupResourceSnapshotThread", _Thread)
    monkeypatch.setattr(
        app_module,
        "_share_resource_snapshot",
        lambda value: received.append(value),
    )
    monkeypatch.setattr(app_module, "_resource_snapshot_started", False)
    monkeypatch.setattr(app_module, "_resource_snapshot_thread", None)

    assert app_module.start_startup_resource_snapshot_check(Path.cwd()) is False
    assert app_module._resource_snapshot_started is True
    assert app_module._resource_snapshot_thread is None
    assert received[-1].mcp_state == "unverified"


def test_startup_discovery_starts_only_once_per_process(qapp, monkeypatch) -> None:
    from hve.gui import app as app_module

    starts: list[object] = []

    class _Signal:
        def connect(self, _callback):
            return None

    class _Thread:
        done = _Signal()
        finished = _Signal()

        def __init__(self, *_args, **_kwargs):
            return None

        def start(self):
            starts.append(self)

        def requestInterruption(self):
            return None

        def deleteLater(self):
            return None

    monkeypatch.setattr(app_module, "_StartupResourceSnapshotThread", _Thread)
    monkeypatch.setattr(app_module, "_resource_snapshot_started", False)
    monkeypatch.setattr(app_module, "_resource_snapshot_thread", None)

    assert app_module.start_startup_resource_snapshot_check(Path.cwd()) is True
    assert app_module.start_startup_resource_snapshot_check(Path.cwd()) is False
    assert len(starts) == 1


def test_live_auth_worker_surface_is_removed(qapp) -> None:
    from hve.gui import app as app_module

    assert not hasattr(app_module, "_WorkIQLiveAuthThread")
    assert not hasattr(app_module, "start_workiq_live_auth")
    assert not hasattr(app_module, "_workiq_auth_thread")
    assert not hasattr(app_module, "_workiq_auth_in_progress")
    assert not hasattr(app_module, "_workiq_live_auth_confirmed")


def test_gui_shutdown_interrupts_resource_and_context_workers_before_waiting(
    monkeypatch,
) -> None:
    from hve.gui import app as app_module
    from hve.gui import toolsearch_settings_section

    events: list[str] = []

    class _Thread:
        def __init__(self, name: str) -> None:
            self.name = name

        def requestInterruption(self) -> None:
            events.append(f"interrupt:{self.name}")

        def isRunning(self) -> bool:
            return True

        def wait(self, timeout_ms: int) -> bool:
            assert timeout_ms > 0
            assert events[:2] == ["interrupt:resource", "interrupt:context"]
            events.append(f"wait:{self.name}")
            return True

    monkeypatch.setattr(app_module, "_resource_snapshot_thread", _Thread("resource"))
    monkeypatch.setattr(
        toolsearch_settings_section,
        "_ACTIVE_CONTEXT_WORKERS",
        {_Thread("context")},
    )

    app_module._shutdown_resource_workers()

    assert events == [
        "interrupt:resource",
        "interrupt:context",
        "wait:resource",
        "wait:context",
    ]


def test_additional_window_receives_snapshot_without_reprobing(qapp, monkeypatch) -> None:
    from hve.gui import app as app_module

    received: list[object] = []

    class _Signal:
        def connect(self, _callback):
            return None

    class _Window:
        def __init__(self, **_kwargs):
            self.destroyed = _Signal()

        def set_resource_snapshot(self, snapshot):
            received.append(snapshot)

        def show(self):
            return None

    snapshot = _resource_snapshot("not-configured")
    monkeypatch.setattr(app_module, "MainWindow", _Window)
    monkeypatch.setattr(app_module, "_resolve_repo_root", lambda: Path.cwd())
    monkeypatch.setattr(app_module, "_resource_snapshot_shared", snapshot)
    monkeypatch.setattr(app_module, "_open_windows", [])

    app_module._open_additional_window()

    assert received == [snapshot]


def test_settings_window_receives_main_window_snapshot(qapp, monkeypatch) -> None:
    from hve.gui import main_window as main_window_module

    received: list[object] = []

    class _Signal:
        def connect(self, _callback):
            return None

    class _SettingsWindow:
        settings_changed = _Signal()
        fetch_models_requested = _Signal()
        def __init__(self, **_kwargs):
            self._visible = False

        def isVisible(self):
            return self._visible

        def set_resource_snapshot(self, snapshot):
            received.append(snapshot)

        def set_resource_refresh_callback(self, _callback):
            return None

        def show(self):
            self._visible = True

        def raise_(self):
            return None

        def activateWindow(self):
            return None

    snapshot = _resource_snapshot("unverified")
    owner = SimpleNamespace(
        _settings_window=None,
        _repo_root=Path.cwd(),
        _resource_snapshot=snapshot,
        _resource_snapshot_initialized=True,
        _request_resource_snapshot_refresh=lambda force_refresh=True: bool(force_refresh),
        _on_settings_changed=lambda *_args: None,
        _on_login_clicked=lambda *_args: None,
        _model_fetch_is_active=lambda: False,
        _set_model_fetch_controls_enabled=lambda _enabled: None,
    )
    monkeypatch.setattr(main_window_module, "SettingsWindow", _SettingsWindow)

    main_window_module.MainWindow._open_settings_window(owner)

    assert received == [snapshot]


def test_window_wiring_has_no_workiq_auth_signal_or_handler(qapp) -> None:
    from hve.gui.main_window import MainWindow
    from hve.gui.settings_window import SettingsWindow

    assert not hasattr(MainWindow, "_on_workiq_auth_requested")
    assert not hasattr(SettingsWindow, "workiq_auth_requested")

    main_source = Path(MainWindow.__module__.replace(".", "/") + ".py")
    if not main_source.exists():
        main_source = Path(__file__).resolve().parents[1] / "main_window.py"
    settings_source = Path(__file__).resolve().parents[1] / "settings_window.py"
    assert "workiq_auth_requested" not in main_source.read_text(encoding="utf-8")
    assert "workiq_auth_requested" not in settings_source.read_text(encoding="utf-8")


def test_settings_window_counts_saved_akm_workiq_source_without_c11_section(qapp) -> None:
    from hve.gui.page_options import _C4WorkIQ
    from hve.gui.settings_window import SettingsWindow

    c4 = _C4WorkIQ()
    owner = SimpleNamespace(
        _workiq_capability=None,
        _workiq_capability_initialized=False,
        _sections={"C4": c4},
        _settings={"options": {"sources_workiq": True}},
    )
    try:
        SettingsWindow.set_workiq_capability(owner, _capability("not-configured"))
        assert "保存設定: 有効" in c4.workiq_availability_status.text()
    finally:
        c4.deleteLater()


def test_resource_worker_exception_becomes_unverified_and_is_shared(qapp, monkeypatch) -> None:
    from hve.gui import app as app_module

    received: list[object] = []
    window = SimpleNamespace(set_resource_snapshot=lambda value: received.append(value))
    monkeypatch.setattr(app_module, "_open_windows", [window])

    app_module._on_resource_snapshot_check_finished(RuntimeError("synthetic failure"))

    assert app_module._resource_snapshot_shared.mcp_state == "unverified"
    assert app_module._project_workiq_capability(app_module._resource_snapshot_shared).state == "unverified"
    assert received == [app_module._resource_snapshot_shared]


def test_startup_ready_snapshot_is_shared_directly_without_live_auth(
    qapp, monkeypatch
) -> None:
    from hve.gui import app as app_module

    received: list[object] = []
    monkeypatch.setattr(app_module, "_open_windows", [])
    monkeypatch.setattr(
        app_module,
        "_share_resource_snapshot",
        lambda value: received.append(value),
    )

    snapshot = _resource_snapshot("ready")
    app_module._on_resource_snapshot_check_finished(snapshot)

    assert received == [snapshot]
