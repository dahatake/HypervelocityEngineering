"""test_cloud_session_gui.py — Cloud Session GUI helper tests."""

from __future__ import annotations

import json
from typing import Callable, cast

import pytest

pytest.importorskip("PySide6")

from hve.gui.main_window import MainWindow
from hve.gui.page_workbench import _is_safe_cloud_session_url, _parse_cloud_session_line
from hve.gui.status_kind import StatusKind
from hve.gui.workbench_state import WorkbenchState


class _FakeMainWindow:
    def __init__(self) -> None:
        self.status_calls: list[tuple[StatusKind, str]] = []

    def tr(self, text: str) -> str:
        return text

    def _set_status(self, kind: StatusKind, message: str = "") -> None:
        self.status_calls.append((kind, message))


def _call_cloud_session_url_changed(window: _FakeMainWindow, url: str) -> None:
    handler = cast(Callable[[_FakeMainWindow, str], None], MainWindow._on_cloud_session_url_changed)
    return handler(window, url)


def test_parse_cloud_session_line_accepts_valid_payload() -> None:
    line = "[hve:cloud-session] " + json.dumps(
        {"step_id": "1", "subtask_kind": "main", "url": "https://example.com"}
    )
    payload = _parse_cloud_session_line(line)
    assert payload is not None
    assert payload["step_id"] == "1"
    assert payload["url"] == "https://example.com"


def test_parse_cloud_session_line_rejects_malformed_payload() -> None:
    assert _parse_cloud_session_line("[hve:cloud-session] {bad json") is None
    assert _parse_cloud_session_line("not a cloud line") is None
    assert _parse_cloud_session_line("[hve:cloud-session] []") is None


def test_is_safe_cloud_session_url_allows_http_https_only() -> None:
    assert _is_safe_cloud_session_url("https://example.com/session")
    assert _is_safe_cloud_session_url("http://example.com/session")
    assert not _is_safe_cloud_session_url("javascript:alert(1)")
    assert not _is_safe_cloud_session_url("file:///tmp/x")
    assert not _is_safe_cloud_session_url("https://")
    assert not _is_safe_cloud_session_url("//example.com/session")
    assert not _is_safe_cloud_session_url("https:///path")
    assert not _is_safe_cloud_session_url("https://example.com/\nnext")


def test_workbench_state_records_latest_cloud_session_url_once() -> None:
    state = WorkbenchState(workflow_id="akm", run_id="run", model="model")
    state.record_cloud_session_url(
        "akm",
        step_id="1",
        subtask_kind="main",
        url="https://example.com/session-1",
    )
    state.record_cloud_session_url(
        "akm",
        step_id="1",
        subtask_kind="review",
        url="https://example.com/session-2",
    )
    inst = state.workflows["akm"]
    assert inst.latest_cloud_session_url == "https://example.com/session-2"
    assert inst.cloud_session_urls["1:main"] == "https://example.com/session-1"
    assert inst.cloud_session_urls["1:review"] == "https://example.com/session-2"


def test_main_window_cloud_session_url_updates_status_only() -> None:
    window = _FakeMainWindow()

    result = _call_cloud_session_url_changed(window, "https://example.com/session")

    assert result is None
    assert window.status_calls == [
        (StatusKind.RUNNING, "Cloud Session: Mission Control URL を取得しました")
    ]


def test_main_window_cloud_session_url_ignores_empty_url() -> None:
    window = _FakeMainWindow()

    result = _call_cloud_session_url_changed(window, "")

    assert result is None
    assert window.status_calls == []
