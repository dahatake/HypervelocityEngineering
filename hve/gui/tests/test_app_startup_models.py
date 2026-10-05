"""FR-GUI-52: 通常 GUI 起動時の利用可能モデル一覧更新契約。

初回ウィンドウの呼び出し配線に加え、モデル取得workerの開始・重複抑止・完了解放・
close延期と、取得結果をcacheおよび表示中surfaceへ反映する境界を検証する。
SDK応答の変換詳細は ``hve/tests/test_models_api.py`` が担う。
"""

from __future__ import annotations

import inspect
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtWidgets import QApplication, QMessageBox


class _Signal:
    def __init__(self) -> None:
        self.callbacks: list[Callable[..., object]] = []

    def connect(self, callback: Callable[..., object]) -> None:
        self.callbacks.append(callback)


def _install_fake_main_window(monkeypatch, app_module, events: list[str]):
    class _Window:
        def __init__(self, **_kwargs) -> None:
            self.destroyed = _Signal()

        def set_resource_snapshot(self, _snapshot: object) -> None:
            events.append("capability")

        def show(self) -> None:
            events.append("show")

        def _on_login_clicked(self) -> None:
            events.append("models")

    monkeypatch.setattr(app_module, "MainWindow", _Window)
    return _Window


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _new_main_window(monkeypatch, tmp_path: Path):
    from hve.gui import settings_store
    from hve.gui.main_window import MainWindow

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HVE_MODELS_CACHE_PATH", str(tmp_path / "models.json"))
    monkeypatch.setattr(
        settings_store,
        "settings_path",
        lambda: tmp_path / "settings.json",
    )
    return MainWindow(repo_root=tmp_path)


def _process_events(qapp: QApplication) -> None:
    for _ in range(5):
        qapp.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _wait_for_threads(qapp: QApplication, window, timeout_ms: int = 3_000) -> None:
    threads = [
        thread
        for thread in window.findChildren(QThread)
        if type(thread).__name__ == "_FetchModelsThread"
    ]
    for thread in threads:
        try:
            assert thread.wait(timeout_ms)
        except RuntimeError:
            pass
    _process_events(qapp)


def _dispose_window(qapp: QApplication, window) -> None:
    _wait_for_threads(qapp, window)
    window.close()
    window.deleteLater()
    _process_events(qapp)


def test_first_window_starts_existing_model_refresh_once_after_show(
    monkeypatch, tmp_path: Path
) -> None:
    from hve.gui import app as app_module

    events: list[str] = []
    _install_fake_main_window(monkeypatch, app_module, events)
    monkeypatch.setattr(app_module, "_resolve_repo_root", lambda: tmp_path)
    monkeypatch.setattr(app_module, "_open_windows", [])
    monkeypatch.setattr(app_module, "_session_counter", [1])
    monkeypatch.setattr(app_module, "_resource_snapshot_shared", None)

    app_module._open_first_window()

    assert events == ["capability", "show", "models"]
    source = inspect.getsource(app_module._open_first_window)
    assert "fetch_model_entries" not in source
    assert "models_cache" not in source


def test_additional_window_does_not_start_automatic_model_refresh(
    monkeypatch, tmp_path: Path
) -> None:
    from hve.gui import app as app_module

    events: list[str] = []
    _install_fake_main_window(monkeypatch, app_module, events)
    monkeypatch.setattr(app_module, "_resolve_repo_root", lambda: tmp_path)
    monkeypatch.setattr(app_module, "_open_windows", [])
    monkeypatch.setattr(app_module, "_session_counter", [1])
    monkeypatch.setattr(app_module, "_resource_snapshot_shared", None)

    app_module._open_additional_window()

    assert events == ["capability", "show"]


def test_model_cache_survives_when_refreshed_entries_cannot_be_saved(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    from hve import models_cache
    from hve.models_api import ModelEntry

    cache_path = tmp_path / "models.json"
    models_cache.save(["cached-model"], path=cache_path)
    window = _new_main_window(monkeypatch, tmp_path)
    cached_index = window._page_options.c1.model.findData("cached-model")
    assert cached_index >= 0
    window._page_options.c1.model.setCurrentIndex(cached_index)
    try:
        with (
            patch(
                "hve.models_api.fetch_model_entries",
                return_value=[ModelEntry(id="fresh-model", name="Fresh Model")],
            ),
            patch(
                "hve.models_cache.save_entries",
                side_effect=OSError("synthetic cache write failure"),
            ),
            patch("hve.gui.main_window.QMessageBox.warning") as warning,
        ):
            window._on_login_clicked()
            _wait_for_threads(qapp, window)

        cached = models_cache.load(path=cache_path, allow_stale=True)
        assert cached is not None
        assert cached.models == ["cached-model"]
        assert window._page_options.c1.model.currentData() == "cached-model"
        assert window._btn_login.isEnabled()
        assert window._status_label.text() == "モデル取得失敗"
        warning.assert_called_once()
    finally:
        _dispose_window(qapp, window)


def test_model_thread_start_failure_is_reported_without_escaping(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    window = _new_main_window(monkeypatch, tmp_path)
    window._open_settings_window()
    settings_button = window._settings_window._sections["C1"].fetch_models_button
    try:
        with (
            patch.object(
                QThread,
                "start",
                side_effect=RuntimeError("synthetic start failure"),
            ),
            patch("hve.gui.main_window.QMessageBox.warning") as warning,
        ):
            window._on_login_clicked()

        assert window._fetch_models_thread is None
        assert window._btn_login.isEnabled()
        assert settings_button.isEnabled()
        assert window._status_label.text() == "モデル取得失敗"
        warning.assert_called_once()
    finally:
        _dispose_window(qapp, window)


def test_model_fetch_busy_state_blocks_duplicate_requests_on_both_buttons(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    window = _new_main_window(monkeypatch, tmp_path)
    window._open_settings_window()
    started = threading.Event()
    release = threading.Event()

    def blocked_fetch():
        started.set()
        release.wait(3)
        return []

    try:
        with patch("hve.models_api.fetch_model_entries", side_effect=blocked_fetch):
            window._on_login_clicked()
            assert started.wait(1)
            first_thread = window._fetch_models_thread
            settings_button = window._settings_window._sections["C1"].fetch_models_button
            status_enabled = window._btn_login.isEnabled()
            settings_enabled = settings_button.isEnabled()
            window._on_login_clicked()
            settings_button.click()
            tracked_thread = window._fetch_models_thread
            child_count = sum(
                type(thread).__name__ == "_FetchModelsThread"
                for thread in window.findChildren(QThread)
            )
            release.set()
            _wait_for_threads(qapp, window)

        assert status_enabled is False
        assert settings_enabled is False
        assert tracked_thread is first_thread
        assert child_count == 1
        assert window._btn_login.isEnabled()
        assert settings_button.isEnabled()
    finally:
        release.set()
        _dispose_window(qapp, window)


def test_model_fetch_reference_blocks_reentry_before_thread_reports_running(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    window = _new_main_window(monkeypatch, tmp_path)
    thread = None
    try:
        with patch.object(QThread, "start", autospec=True, return_value=None):
            window._on_login_clicked()
            thread = window._fetch_models_thread
            window._on_login_clicked()
            assert window._fetch_models_thread is thread
            assert sum(
                type(child).__name__ == "_FetchModelsThread"
                for child in window.findChildren(QThread)
            ) == 1
    finally:
        window._fetch_models_thread = None
        if thread is not None:
            thread.deleteLater()
        _dispose_window(qapp, window)


def test_settings_button_opened_during_fetch_inherits_busy_state(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    window = _new_main_window(monkeypatch, tmp_path)
    started = threading.Event()
    release = threading.Event()

    def blocked_fetch():
        started.set()
        release.wait(3)
        return []

    try:
        with patch("hve.models_api.fetch_model_entries", side_effect=blocked_fetch):
            window._on_login_clicked()
            assert started.wait(1)
            window._open_settings_window()
            settings_button = window._settings_window._sections["C1"].fetch_models_button
            enabled_while_busy = settings_button.isEnabled()
            release.set()
            _wait_for_threads(qapp, window)

        assert enabled_while_busy is False
        assert settings_button.isEnabled()
    finally:
        release.set()
        _dispose_window(qapp, window)


def test_finished_model_fetch_thread_is_released(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    from hve.models_api import ModelEntry

    window = _new_main_window(monkeypatch, tmp_path)
    try:
        with patch(
            "hve.models_api.fetch_model_entries",
            return_value=[ModelEntry(id="fresh-model", name="Fresh Model")],
        ):
            window._on_login_clicked()
            thread = window._fetch_models_thread
            _wait_for_threads(qapp, window)

        assert window._fetch_models_thread is None
        with pytest.raises(RuntimeError):
            thread.isFinished()
        assert all(
            type(child).__name__ != "_FetchModelsThread"
            for child in window.findChildren(QThread)
        )
    finally:
        _dispose_window(qapp, window)


def test_close_is_deferred_until_model_fetch_finishes(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    window = _new_main_window(monkeypatch, tmp_path)
    started = threading.Event()
    release = threading.Event()

    def blocked_fetch():
        started.set()
        release.wait(3)
        return []

    try:
        window.show()
        with patch("hve.models_api.fetch_model_entries", side_effect=blocked_fetch):
            window._on_login_clicked()
            assert started.wait(1)
            close_result = window.close()
            visible_while_busy = window.isVisible()
            release.set()
            _wait_for_threads(qapp, window)
            deadline = time.monotonic() + 1
            while window.isVisible() and time.monotonic() < deadline:
                _process_events(qapp)

        assert close_result is False
        assert visible_while_busy is True
        assert not window.isVisible()
    finally:
        release.set()
        _dispose_window(qapp, window)


def test_deferred_close_reenables_window_if_running_session_close_is_rejected(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    from hve.models_api import ModelEntry

    window = _new_main_window(monkeypatch, tmp_path)
    started = threading.Event()
    release = threading.Event()

    def blocked_fetch():
        started.set()
        release.wait(3)
        return [ModelEntry(id="close-rejected-model", name="Close Rejected")]

    try:
        window.show()
        monkeypatch.setattr(window, "_is_any_execution_running", lambda: True)
        with (
            patch("hve.models_api.fetch_model_entries", side_effect=blocked_fetch),
            patch(
                "hve.gui.main_window.QMessageBox.question",
                return_value=QMessageBox.StandardButton.No,
            ) as question,
        ):
            window._on_login_clicked()
            assert started.wait(1)
            assert window.close() is False
            release.set()
            _wait_for_threads(qapp, window)
            _process_events(qapp)

        assert question.call_count == 1
        assert window.isVisible()
        assert window.isEnabled()
        assert window._page_options.c1.model.findData("close-rejected-model") >= 0
        assert "取得完了後に終了" not in window._status_label.text()
    finally:
        monkeypatch.setattr(window, "_is_any_execution_running", lambda: False)
        release.set()
        _dispose_window(qapp, window)


def test_deferred_close_does_not_hide_fetch_failure_if_close_is_rejected(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    window = _new_main_window(monkeypatch, tmp_path)
    started = threading.Event()
    release = threading.Event()

    def blocked_failure():
        started.set()
        release.wait(3)
        raise RuntimeError("synthetic fetch failure")

    try:
        window.show()
        monkeypatch.setattr(window, "_is_any_execution_running", lambda: True)
        with (
            patch("hve.models_api.fetch_model_entries", side_effect=blocked_failure),
            patch(
                "hve.gui.main_window.QMessageBox.question",
                return_value=QMessageBox.StandardButton.No,
            ),
            patch("hve.gui.main_window.QMessageBox.warning") as warning,
        ):
            window._on_login_clicked()
            assert started.wait(1)
            assert window.close() is False
            release.set()
            _wait_for_threads(qapp, window)
            _process_events(qapp)

        warning.assert_called_once()
        assert "synthetic fetch failure" in warning.call_args.args[2]
        assert window.isVisible()
        assert window.isEnabled()
        assert "取得完了後に終了" not in window._status_label.text()
    finally:
        monkeypatch.setattr(window, "_is_any_execution_running", lambda: False)
        release.set()
        _dispose_window(qapp, window)


def test_empty_model_result_preserves_cache_selection_and_reports_zero(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    from hve import models_cache

    cache_path = tmp_path / "models.json"
    models_cache.save(["cached-model"], path=cache_path)
    window = _new_main_window(monkeypatch, tmp_path)
    cached_index = window._page_options.c1.model.findData("cached-model")
    assert cached_index >= 0
    window._page_options.c1.model.setCurrentIndex(cached_index)
    try:
        with patch("hve.models_api.fetch_model_entries", return_value=[]):
            window._on_login_clicked()
            _wait_for_threads(qapp, window)

        cached = models_cache.load(path=cache_path, allow_stale=True)
        assert cached is not None
        assert cached.models == ["cached-model"]
        assert window._page_options.c1.model.currentData() == "cached-model"
        assert window._status_label.text() == "モデル一覧を取得しました (0 件)"
    finally:
        _dispose_window(qapp, window)


def test_model_result_does_not_hide_startup_index_blocker(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    from hve import index_refresh

    window = _new_main_window(monkeypatch, tmp_path)
    monkeypatch.setattr(index_refresh, "is_running", lambda: True)
    try:
        window._on_models_fetched([])

        assert "索引" in window._status_label.text()
        assert "差分更新中" in window._status_label.text()
    finally:
        monkeypatch.setattr(index_refresh, "is_running", lambda: False)
        _dispose_window(qapp, window)


def test_model_result_does_not_hide_startup_workiq_blocker(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    window = _new_main_window(monkeypatch, tmp_path)
    try:
        window.set_workiq_capability(None)
        window._on_models_fetched([])

        assert "Work IQ" in window._status_label.text()
        assert "完了するまで実行できません" in window._status_label.text()
    finally:
        _dispose_window(qapp, window)


def test_model_result_does_not_hide_running_workflow_status(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    from hve.gui.status_kind import StatusKind

    window = _new_main_window(monkeypatch, tmp_path)
    window._stack.setCurrentIndex(1)
    monkeypatch.setattr(window._page_workbench, "is_running", lambda: True)
    window._set_status(StatusKind.RUNNING, "実行中")
    try:
        window._on_models_fetched([])

        assert window._status_label.text() == "実行中"
    finally:
        monkeypatch.setattr(window._page_workbench, "is_running", lambda: False)
        _dispose_window(qapp, window)


def test_nonempty_model_result_updates_cache_and_visible_model_surfaces(
    qapp, monkeypatch, tmp_path: Path
) -> None:
    from hve import models_cache
    from hve.models_api import ModelEntry

    cache_path = tmp_path / "models.json"
    models_cache.save(["cached-model"], path=cache_path)
    window = _new_main_window(monkeypatch, tmp_path)
    window._open_settings_window()
    settings_c1 = window._settings_window._sections["C1"]
    try:
        with patch(
            "hve.models_api.fetch_model_entries",
            return_value=[ModelEntry(id="fresh-model", name="Fresh Model")],
        ):
            window._on_login_clicked()
            _wait_for_threads(qapp, window)

        cached = models_cache.load(path=cache_path, allow_stale=True)
        assert cached is not None
        assert cached.models == ["fresh-model"]
        assert window._page_options.c1.model.findData("fresh-model") >= 0
        assert settings_c1.model.findData("fresh-model") >= 0
        assert window._status_label.text() == "モデル一覧を取得しました (1 件)"
    finally:
        _dispose_window(qapp, window)


def test_one_model_surface_reload_failure_does_not_skip_other_surfaces(
    qapp, monkeypatch, tmp_path: Path, caplog
) -> None:
    window = _new_main_window(monkeypatch, tmp_path)
    c3_reload = Mock()
    monkeypatch.setattr(
        window._page_options.c1,
        "reload_models",
        Mock(side_effect=RuntimeError("synthetic reload failure")),
    )
    monkeypatch.setattr(window._page_options.c3, "reload_models", c3_reload)
    try:
        with caplog.at_level("WARNING", logger="hve.gui.main_window"):
            window._on_models_fetched(["fresh-model"])
        c3_reload.assert_called_once_with()
        assert "model surface reload failed" in caplog.text
    finally:
        _dispose_window(qapp, window)


def test_autopilot_child_does_not_open_the_refreshing_first_window(
    qapp, monkeypatch
) -> None:
    """Autopilot child 分岐が通常初回ウィンドウを通らないことだけを検証する。"""
    from hve.gui import app as app_module

    calls: list[str] = []
    monkeypatch.setattr(app_module, "_configure_qt_logging", lambda: None)
    monkeypatch.setattr(app_module, "apply_style_to_application", lambda: None)
    monkeypatch.setattr(app_module, "apply_theme_to_application", lambda _theme: None)
    monkeypatch.setattr(app_module, "get_option", lambda _key: None)
    monkeypatch.setattr(app_module, "install_translator", lambda *_args: None)
    monkeypatch.setattr(
        app_module,
        "_open_first_window",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("normal first window must not open")
        ),
    )
    monkeypatch.setattr(
        app_module,
        "_open_autopilot_child_window",
        lambda _args: calls.append("autopilot") or 0,
    )
    monkeypatch.setattr(app_module, "start_startup_resource_snapshot_check", lambda *_args: False)
    monkeypatch.setattr(app_module, "_exec_with_resource_cleanup", lambda _app: 0)

    args = type("Args", (), {"autopilot_child": True})()

    assert app_module.run_app(args) == 0
    assert calls == ["autopilot"]
    child_source = inspect.getsource(app_module._open_autopilot_child_window)
    assert "_on_login_clicked" not in child_source
    assert "fetch_model_entries" not in child_source
