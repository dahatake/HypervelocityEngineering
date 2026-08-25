"""hve.gui.tests.test_github_pr_panel

FR-GUI-27: GUI からの Pull Request 閲覧・コメントの単体テスト（offscreen）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.github_service import GitHubServiceError  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


_PULLS = [
    {
        "number": 42,
        "title": "機能追加",
        "state": "open",
        "user": {"login": "alice"},
        "head": {"ref": "copilot-sdk/aad-1234abcd"},
        "base": {"ref": "main"},
        "merged": False,
        "draft": False,
        "body": "PR 本文",
        "html_url": "https://github.com/o/r/pull/42",
    },
    {
        "number": 41,
        "title": "バグ修正",
        "state": "closed",
        "user": {"login": "bob"},
        "head": {"ref": "fix/x"},
        "base": {"ref": "main"},
        "merged": True,
        "draft": False,
        "body": "",
        "html_url": "https://github.com/o/r/pull/41",
    },
]

_FILES = [
    {"filename": "hve/github_api.py", "status": "modified"},
    {"filename": "hve/gui/github_pr_panel.py", "status": "added"},
]

_COMMENTS = [
    {"id": 7, "user": {"login": "alice"}, "body": "LGTM", "created_at": "2026-08-03T00:00:00Z"},
]


@pytest.fixture
def panel(qapp, monkeypatch):
    from hve.gui import github_pr_panel as module

    calls: Dict[str, List[Any]] = {
        "list_pull_requests": [],
        "get_pull_request": [],
        "post_comment": [],
    }

    monkeypatch.setattr(
        module.github_service,
        "list_pull_requests",
        lambda repo, state="open", per_page=50: calls["list_pull_requests"].append(
            (repo, state)
        )
        or list(_PULLS),
    )
    monkeypatch.setattr(
        module.github_service,
        "get_pull_request",
        lambda repo, number: calls["get_pull_request"].append((repo, number))
        or next(p for p in _PULLS if p["number"] == int(number)),
    )
    monkeypatch.setattr(
        module.github_service, "list_pull_request_files", lambda repo, number: list(_FILES)
    )
    monkeypatch.setattr(
        module.github_service, "list_comments", lambda repo, number: list(_COMMENTS)
    )
    monkeypatch.setattr(
        module.github_service,
        "post_comment",
        lambda repo, number, body: calls["post_comment"].append((repo, number, body)),
    )

    widget = module.GitHubPullRequestPanel()
    widget.set_repo("o/r")

    def _sync(task, on_ok, on_ng=None):
        try:
            result = task()
        except GitHubServiceError as exc:
            (on_ng or widget._show_error)(str(exc))
        else:
            on_ok(result)

    monkeypatch.setattr(widget, "_run", _sync)
    widget._calls = calls  # type: ignore[attr-defined]
    return widget


class TestPullRequestPanel:
    def test_refresh_populates_list(self, panel) -> None:
        panel.refresh_pull_requests()
        assert panel.pr_list.count() == 2
        assert "#42" in panel.pr_list.item(0).text()
        assert "機能追加" in panel.pr_list.item(0).text()

    def test_state_filter_is_passed_through(self, panel) -> None:
        panel.state_combo.setCurrentIndex(panel.state_combo.findData("closed"))
        panel.refresh_pull_requests()
        assert panel._calls["list_pull_requests"][-1] == ("o/r", "closed")

    def test_state_combo_offers_three_states(self, panel) -> None:
        values = [panel.state_combo.itemData(i) for i in range(panel.state_combo.count())]
        assert values == ["open", "closed", "all"]

    def test_selecting_pr_shows_detail(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        meta = panel.meta_label.text()
        assert "#42" in meta and "open" in meta and "alice" in meta
        assert "copilot-sdk/aad-1234abcd" in meta and "main" in meta
        assert panel.body_view.toPlainText() == "PR 本文"
        assert "https://github.com/o/r/pull/42" in panel.url_label.text()

    def test_merged_state_is_shown(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(1)
        assert "merged" in panel.meta_label.text()

    def test_changed_files_are_listed(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        assert panel.file_list.count() == 2
        assert "hve/github_api.py" in panel.file_list.item(0).text()
        assert "modified" in panel.file_list.item(0).text()

    def test_comments_are_listed(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        assert panel.comment_list.count() == 1
        assert "alice" in panel.comment_list.item(0).text()

    def test_post_comment_sends_and_clears_input(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        panel.new_comment_edit.setPlainText("レビューコメント")
        panel.post_comment()
        assert panel._calls["post_comment"][-1] == ("o/r", 42, "レビューコメント")
        assert panel.new_comment_edit.toPlainText() == ""

    def test_post_comment_requires_selection(self, panel) -> None:
        panel.new_comment_edit.setPlainText("孤児コメント")
        panel.post_comment()
        assert panel._calls["post_comment"] == []

    def test_body_view_is_read_only(self, panel) -> None:
        """PR 本文の編集は本要件の対象外。"""
        assert panel.body_view.isReadOnly()


class TestNoPullRequestCreation:
    def test_panel_has_no_create_action(self, panel) -> None:
        """FR-GUI-27: GUI から PR を新規作成する操作を提供しないこと。"""
        from PySide6.QtWidgets import QPushButton

        labels = [b.text() for b in panel.findChildren(QPushButton)]
        assert not any("作成" in label for label in labels), labels

    def test_module_does_not_use_create_pull_request(self) -> None:
        import ast
        from pathlib import Path

        import hve.gui.github_pr_panel as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        names = {
            node.attr for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Attribute)
        }
        assert "create_pull_request" not in names


class TestPullRequestPanelErrors:
    def test_service_error_is_shown(self, panel, monkeypatch) -> None:
        from hve.gui import github_pr_panel as module

        def _boom(*_a, **_kw):
            raise GitHubServiceError("権限が不足しています。")

        monkeypatch.setattr(module.github_service, "list_pull_requests", _boom)
        panel.refresh_pull_requests()
        assert panel.pr_list.count() == 0
        assert "権限が不足しています。" in panel.status_label.text()

    def test_file_listing_failure_does_not_hide_detail(self, panel, monkeypatch) -> None:
        """変更ファイル取得に失敗しても PR 詳細の表示は残ること。"""
        from hve.gui import github_pr_panel as module

        def _boom(*_a, **_kw):
            raise GitHubServiceError("ファイル一覧を取得できません。")

        panel.refresh_pull_requests()
        monkeypatch.setattr(module.github_service, "list_pull_request_files", _boom)
        panel.pr_list.setCurrentRow(0)
        assert "#42" in panel.meta_label.text()
        assert panel.file_list.count() == 0
        assert "ファイル一覧を取得できません。" in panel.status_label.text()

    def test_refresh_without_repo_reports_error(self, qapp, monkeypatch) -> None:
        from hve.gui import github_pr_panel as module

        monkeypatch.setattr(
            module.github_service,
            "list_pull_requests",
            lambda *_a, **_kw: pytest.fail("must not call API without a repository"),
        )
        widget = module.GitHubPullRequestPanel()
        widget.refresh_pull_requests()
        assert widget.status_label.text()


class TestWorkerLifetime:
    def test_shutdown_releases_workers(self, qapp, monkeypatch) -> None:
        from hve.gui import github_pr_panel as module

        monkeypatch.setattr(
            module.github_service,
            "list_pull_requests",
            lambda repo, state="open", per_page=50: [],
        )
        widget = module.GitHubPullRequestPanel()
        widget.set_repo("o/r")
        widget.refresh_pull_requests()
        widget.shutdown()
        assert widget._workers == []

    def test_url_label_escapes_api_text(self, qapp, monkeypatch) -> None:
        from hve.gui import github_pr_panel as module

        widget = module.GitHubPullRequestPanel()
        widget.set_repo("o/r")
        monkeypatch.setattr(widget, "_load_files", lambda _n: None)
        monkeypatch.setattr(widget, "_load_comments", lambda _n: None)
        widget._on_pull_request_loaded(
            {
                "number": 1,
                "title": "t",
                "state": "open",
                "body": "",
                "head": {"ref": "h"},
                "base": {"ref": "b"},
                "html_url": 'https://example.invalid/"><img src=x>',
            }
        )
        assert "<img" not in widget.url_label.text()
        assert "&lt;img" in widget.url_label.text()
