"""FR-GUI-36: MainWindow の自動 Post 結線契約。

GUI thread で GitHub API を呼ばず、`GitHubWorker` 経由で実行することと、
workflow ごとにコントローラを分離することを固定する。
"""

from __future__ import annotations

import ast
import inspect
import os
from typing import Any, Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


def _source(name: str) -> str:
    from hve.gui import main_window

    return inspect.getsource(getattr(main_window.MainWindow, name))


class TestWorkerBoundary:
    """FR-GUI-28 / FR-GUI-36: API 呼び出しは worker 経由。"""

    def test_dispatch_uses_github_worker(self) -> None:
        source = _source("_dispatch_github_auto_post")
        assert "GitHubWorker(" in source
        assert "worker.start()" in source

    def test_dispatch_calls_service_layer_only(self) -> None:
        source = _source("_dispatch_github_auto_post")
        assert "github_service.create_comment" in source
        assert "github_service.update_comment" in source
        assert "github_api" not in source

    def test_dispatch_does_not_call_service_on_gui_thread(self) -> None:
        """service 呼び出しは partial で worker へ渡すだけであること。"""
        import textwrap

        tree = ast.parse(textwrap.dedent(_source("_dispatch_github_auto_post")))
        direct_calls: List[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "github_service"
                and func.attr in {"create_comment", "update_comment"}
            ):
                direct_calls.append(func.attr)
        assert direct_calls == []

    def test_failure_message_is_not_forwarded_verbatim(self) -> None:
        source = _source("_dispatch_github_auto_post")
        assert 'error="post_failed"' in source


class TestPerWorkflowIsolation:
    """FR-GUI-36: run ごとに 1 コメント。workflow を跨いで snapshot を混ぜない。"""

    def test_controller_is_keyed_by_workflow(self) -> None:
        source = _source("_github_auto_post_controller")
        assert "_auto_post_controllers" in source
        assert "controllers[workflow_id]" in source

    def test_feed_and_finalize_take_workflow_id(self) -> None:
        from hve.gui import main_window

        for name in ("_feed_github_auto_post", "_finalize_github_auto_post"):
            params = list(
                inspect.signature(getattr(main_window.MainWindow, name)).parameters
            )
            assert params[1] == "workflow_id", name

    def test_close_stops_every_controller(self) -> None:
        source = _source("_close_github_auto_post")
        assert ".values()" in source
        assert "controller.close()" in source


class TestControllerSelection:
    """設定値に従ってコントローラを生成・停止する。"""

    def _window_stub(self, mode: str) -> Any:
        from hve.gui import main_window

        class _Stub:
            pass

        stub = _Stub()
        stub._auto_post_controllers = {}
        stub._github_auto_post_controller = (
            main_window.MainWindow._github_auto_post_controller.__get__(stub)
        )
        return stub

    def test_off_returns_none(self, monkeypatch) -> None:
        from hve.gui import settings_store

        monkeypatch.setattr(settings_store, "get_option", lambda key, default=None: "off")
        stub = self._window_stub("off")
        assert stub._github_auto_post_controller("aas") is None

    def test_enabled_creates_one_controller_per_workflow(self, monkeypatch) -> None:
        from hve.gui import settings_store

        monkeypatch.setattr(settings_store, "get_option", lambda key, default=None: "both")
        stub = self._window_stub("both")

        first = stub._github_auto_post_controller("aas")
        again = stub._github_auto_post_controller("aas")
        other = stub._github_auto_post_controller("ard")

        assert first is not None
        assert first is again
        assert other is not first

    def test_mode_change_is_applied_to_existing_controller(self, monkeypatch) -> None:
        from hve.gui import settings_store

        values: Dict[str, str] = {"mode": "issue"}
        monkeypatch.setattr(
            settings_store, "get_option", lambda key, default=None: values["mode"]
        )
        stub = self._window_stub("issue")
        controller = stub._github_auto_post_controller("aas")
        assert controller.target_mode == "issue"

        values["mode"] = "both"
        assert stub._github_auto_post_controller("aas").target_mode == "both"

    def test_switching_to_off_disables_existing_controller(self, monkeypatch) -> None:
        from hve.gui import settings_store

        values: Dict[str, str] = {"mode": "issue"}
        monkeypatch.setattr(
            settings_store, "get_option", lambda key, default=None: values["mode"]
        )
        stub = self._window_stub("issue")
        controller = stub._github_auto_post_controller("aas")

        values["mode"] = "off"
        assert stub._github_auto_post_controller("aas") is None
        assert controller.target_mode == "off"
