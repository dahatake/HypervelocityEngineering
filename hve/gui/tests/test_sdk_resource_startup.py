"""FR-GUI-51 / FR-GUI-53: GUI process-wide SDK resource snapshot wiring."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.toolsearch.resource_inventory import ResourceItem, ResourceSnapshot  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _snapshot() -> ResourceSnapshot:
    return ResourceSnapshot(
        plugin_state="ready",
        mcp_state="ready",
        skill_state="ready",
        skill_ownership_state="ready",
        plugins=(
            ResourceItem(
                kind="plugin",
                name="docs-plugin",
                enabled=True,
                source_kind="marketplace",
                plugin_marketplace="trusted",
                plugin_version="1.2.3",
            ),
        ),
        mcp_servers=(
            ResourceItem(
                kind="mcp_server",
                name="workiq",
                enabled=True,
                source_kind="plugin",
                owner_plugin="docs-plugin",
                plugin_marketplace="trusted",
                plugin_version="1.2.3",
            ),
        ),
        skills=(
            ResourceItem(
                kind="skill",
                name="answer-docs",
                enabled=True,
                source_kind="plugin",
                owner_plugin="docs-plugin",
                plugin_marketplace="trusted",
                plugin_version="1.2.3",
                description="Answer from approved documentation",
            ),
        ),
    )


def test_resource_snapshot_worker_failure_shares_one_unverified_snapshot(
    qapp, monkeypatch
) -> None:
    from hve.gui import app as app_module

    received_snapshot: list[object] = []
    monkeypatch.setattr(
        app_module,
        "_open_windows",
        [
            SimpleNamespace(set_resource_snapshot=lambda value: received_snapshot.append(value)),
            SimpleNamespace(set_resource_snapshot=lambda value: received_snapshot.append(value)),
        ],
    )

    app_module._on_resource_snapshot_check_finished(RuntimeError("synthetic failure"))

    assert len(received_snapshot) == 2
    assert received_snapshot[0] is received_snapshot[1]
    assert getattr(received_snapshot[0], "mcp_state", None) == "unverified"
    assert app_module._project_workiq_capability(received_snapshot[0]).state == "unverified"
    assert app_module._resource_snapshot_shared is received_snapshot[0]


def test_additional_window_receives_shared_snapshot_object_identity(qapp, monkeypatch) -> None:
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

    snapshot = _snapshot()
    monkeypatch.setattr(app_module, "MainWindow", _Window)
    monkeypatch.setattr(app_module, "_resolve_repo_root", lambda: Path.cwd())
    monkeypatch.setattr(app_module, "_resource_snapshot_shared", snapshot, raising=False)
    monkeypatch.setattr(app_module, "_open_windows", [])

    app_module._open_additional_window()

    assert received == [snapshot]


def test_main_window_passes_same_snapshot_and_refresh_callback_to_settings(qapp, monkeypatch) -> None:
    from hve.gui import main_window as main_window_module

    snapshot = _snapshot()
    received_snapshot: list[object] = []
    received_callbacks = []

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

        def set_resource_snapshot(self, value):
            received_snapshot.append(value)

        def set_resource_refresh_callback(self, callback):
            received_callbacks.append(callback)

        def set_workiq_capability(self, _capability):
            raise AssertionError("resource snapshot path should be used")

        def show(self):
            self._visible = True

        def raise_(self):
            return None

        def activateWindow(self):
            return None

    owner = SimpleNamespace(
        _settings_window=None,
        _repo_root=Path.cwd(),
        _resource_snapshot=snapshot,
        _resource_snapshot_initialized=True,
        _workiq_capability=None,
        _on_settings_changed=lambda *_args: None,
        _on_login_clicked=lambda *_args: None,
        _model_fetch_is_active=lambda: False,
        _set_model_fetch_controls_enabled=lambda _enabled: None,
        _request_resource_snapshot_refresh=lambda force_refresh=True: bool(force_refresh),
    )
    monkeypatch.setattr(main_window_module, "SettingsWindow", _SettingsWindow)

    main_window_module.MainWindow._open_settings_window(owner)

    assert received_snapshot == [snapshot]
    assert len(received_callbacks) == 1
    assert received_callbacks[0](True) is True


def test_shutdown_interrupts_resource_and_context_workers_before_waiting(monkeypatch) -> None:
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
            events.append(f"wait:{self.name}")
            return True

    monkeypatch.setattr(app_module, "_resource_snapshot_thread", _Thread("resource"))
    monkeypatch.setattr(toolsearch_settings_section, "_ACTIVE_CONTEXT_WORKERS", {_Thread("context")})

    app_module._shutdown_resource_workers()

    assert events == [
        "interrupt:resource",
        "interrupt:context",
        "wait:resource",
        "wait:context",
    ]


def test_startup_surface_has_only_generic_resource_names() -> None:
    from hve.gui import app as app_module
    from hve.gui import page_options

    for legacy_name in (
        "_StartupWorkIQThread",
        "_workiq_capability_snapshot",
        "_workiq_check_started",
        "_workiq_check_thread",
        "start_startup_workiq_check",
        "_shutdown_workiq_workers",
        "_exec_with_workiq_cleanup",
    ):
        assert not hasattr(app_module, legacy_name), legacy_name
    assert not hasattr(page_options, "_ACTIVE_PLUGIN_REFRESH_THREADS")
    assert not hasattr(page_options, "_PluginResourceRefreshThread")


def test_run_app_uses_generic_resource_startup_before_github_auth(qapp, monkeypatch) -> None:
    from hve.gui import app as app_module

    calls: list[str] = []
    monkeypatch.setattr(app_module, "_open_first_window", lambda initial_catalog=None: calls.append("window"))
    monkeypatch.setattr(app_module, "start_startup_resource_snapshot_check", lambda _root=None: calls.append("resource") or True)
    monkeypatch.setattr(app_module, "_run_startup_github_auth", lambda: calls.append("github"))
    monkeypatch.setattr(app_module, "start_startup_index_refresh", lambda _root: False)
    monkeypatch.setattr(app_module, "_shutdown_resource_workers", lambda: calls.append("cleanup"))
    monkeypatch.setattr(QApplication, "exec", lambda _self: 0)
    monkeypatch.setattr(app_module, "_open_windows", [])

    assert app_module.run_app(None) == 0
    assert calls == ["window", "resource", "github", "cleanup"]
