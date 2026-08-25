"""hve.gui.tests.test_github_issue_panel

FR-GUI-26: GUI からの Issue 閲覧・編集・コメントの単体テスト（offscreen）。

`github_service` を monkeypatch し、ワーカーは同期実行へ差し替えて検証する。
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


_ISSUES = [
    {
        "number": 12,
        "title": "既存の不具合",
        "state": "open",
        "user": {"login": "alice"},
        "labels": [{"name": "bug"}],
        "assignees": [{"login": "bob"}],
        "body": "本文 12",
        "html_url": "https://github.com/o/r/issues/12",
    },
    {
        "number": 9,
        "title": "改善提案",
        "state": "open",
        "user": {"login": "bob"},
        "labels": [],
        "assignees": [],
        "body": "本文 9",
        "html_url": "https://github.com/o/r/issues/9",
    },
]

_COMMENTS = [
    {"id": 100, "user": {"login": "alice"}, "body": "他人のコメント", "created_at": "2026-08-01T00:00:00Z"},
    {"id": 101, "user": {"login": "me"}, "body": "自分のコメント", "created_at": "2026-08-02T00:00:00Z"},
]


@pytest.fixture
def panel(qapp, monkeypatch):
    """サービス層を stub 化し、ワーカーを同期実行にした Issue パネル。"""
    from hve.gui import github_issue_panel as module

    calls: Dict[str, List[Any]] = {
        "list_issues": [],
        "get_issue": [],
        "update_issue": [],
        "post_comment": [],
        "update_comment": [],
    }

    monkeypatch.setattr(
        module.github_service,
        "list_issues",
        lambda repo, state="open", per_page=50: calls["list_issues"].append((repo, state))
        or list(_ISSUES),
    )
    monkeypatch.setattr(
        module.github_service,
        "get_issue",
        lambda repo, number: calls["get_issue"].append((repo, number))
        or next(i for i in _ISSUES if i["number"] == int(number)),
    )
    monkeypatch.setattr(
        module.github_service, "list_comments", lambda repo, number: list(_COMMENTS)
    )
    monkeypatch.setattr(module.github_service, "current_user_login", lambda: "me")
    monkeypatch.setattr(
        module.github_service,
        "update_issue",
        lambda repo, number, **kw: calls["update_issue"].append((repo, number, kw))
        or {"number": int(number)},
    )
    monkeypatch.setattr(
        module.github_service,
        "post_comment",
        lambda repo, number, body: calls["post_comment"].append((repo, number, body)),
    )
    monkeypatch.setattr(
        module.github_service,
        "update_comment",
        lambda repo, comment_id, body: calls["update_comment"].append(
            (repo, comment_id, body)
        )
        or {"id": comment_id},
    )

    widget = module.GitHubIssuePanel()
    widget.set_repo("o/r")
    # ワーカーを同期実行へ差し替え（イベントループ不要）
    def _sync(task, on_ok, on_ng=None):
        try:
            result = task()
        except GitHubServiceError as exc:
            if on_ng is not None:
                on_ng(str(exc))
            else:
                widget._show_error(str(exc))
        else:
            on_ok(result)

    monkeypatch.setattr(widget, "_run", _sync)
    widget._calls = calls  # type: ignore[attr-defined]
    return widget


class TestIssuePanel:
    def test_refresh_populates_list(self, panel) -> None:
        panel.refresh_issues()
        assert panel.issue_list.count() == 2
        assert "#12" in panel.issue_list.item(0).text()
        assert "既存の不具合" in panel.issue_list.item(0).text()

    def test_state_filter_is_passed_through(self, panel) -> None:
        panel.state_combo.setCurrentIndex(panel.state_combo.findData("all"))
        panel.refresh_issues()
        assert panel._calls["list_issues"][-1] == ("o/r", "all")

    def test_state_combo_offers_three_states(self, panel) -> None:
        values = [panel.state_combo.itemData(i) for i in range(panel.state_combo.count())]
        assert values == ["open", "closed", "all"]

    def test_selecting_issue_loads_detail(self, panel) -> None:
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        assert panel.title_edit.text() == "既存の不具合"
        assert panel.body_edit.toPlainText() == "本文 12"
        meta = panel.meta_label.text()
        assert "#12" in meta and "open" in meta and "alice" in meta
        assert "bug" in meta and "bob" in meta
        assert "https://github.com/o/r/issues/12" in panel.url_label.text()

    def test_selecting_issue_loads_comments(self, panel) -> None:
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        assert panel.comment_list.count() == 2
        assert "alice" in panel.comment_list.item(0).text()

    def test_save_sends_only_title_and_body(self, panel) -> None:
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        panel.title_edit.setText("新タイトル")
        panel.body_edit.setPlainText("新本文")
        panel.save_issue()
        repo, number, kw = panel._calls["update_issue"][-1]
        assert (repo, number) == ("o/r", 12)
        assert kw == {"title": "新タイトル", "body": "新本文"}

    def test_save_without_selection_is_noop(self, panel) -> None:
        panel.save_issue()
        assert panel._calls["update_issue"] == []

    def test_toggle_state_closes_open_issue(self, panel) -> None:
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        panel.toggle_state()
        _repo, number, kw = panel._calls["update_issue"][-1]
        assert number == 12
        assert kw == {"state": "closed"}

    def test_toggle_state_reopens_closed_issue(self, panel, monkeypatch) -> None:
        from hve.gui import github_issue_panel as module

        closed = dict(_ISSUES[0], state="closed")
        monkeypatch.setattr(module.github_service, "get_issue", lambda repo, number: closed)
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        panel.toggle_state()
        _repo, _number, kw = panel._calls["update_issue"][-1]
        assert kw == {"state": "open"}

    def test_post_comment_sends_and_clears_input(self, panel) -> None:
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        panel.new_comment_edit.setPlainText("コメント本文")
        panel.post_comment()
        assert panel._calls["post_comment"][-1] == ("o/r", 12, "コメント本文")
        assert panel.new_comment_edit.toPlainText() == ""

    def test_post_comment_requires_selection(self, panel) -> None:
        panel.new_comment_edit.setPlainText("孤児コメント")
        panel.post_comment()
        assert panel._calls["post_comment"] == []

    def test_own_comment_is_editable(self, panel) -> None:
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        panel.comment_list.setCurrentRow(1)  # login == "me"
        assert panel.comment_edit.isEnabled()
        assert panel.save_comment_button.isEnabled()
        assert panel.comment_edit.toPlainText() == "自分のコメント"

    def test_other_comment_is_read_only(self, panel) -> None:
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        panel.comment_list.setCurrentRow(0)  # login == "alice"
        assert not panel.comment_edit.isEnabled()
        assert not panel.save_comment_button.isEnabled()

    def test_update_own_comment(self, panel) -> None:
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        panel.comment_list.setCurrentRow(1)
        panel.comment_edit.setPlainText("編集後")
        panel.save_comment()
        assert panel._calls["update_comment"][-1] == ("o/r", 101, "編集後")

    def test_update_other_comment_is_blocked(self, panel) -> None:
        panel.refresh_issues()
        panel.issue_list.setCurrentRow(0)
        panel.comment_list.setCurrentRow(0)
        panel.comment_edit.setPlainText("勝手に編集")
        panel.save_comment()
        assert panel._calls["update_comment"] == []


class TestIssuePanelErrors:
    def test_service_error_is_shown_and_list_stays_empty(self, panel, monkeypatch) -> None:
        from hve.gui import github_issue_panel as module

        def _boom(*_a, **_kw):
            raise GitHubServiceError("対象が見つかりません。")

        monkeypatch.setattr(module.github_service, "list_issues", _boom)
        panel.refresh_issues()
        assert panel.issue_list.count() == 0
        assert "対象が見つかりません。" in panel.status_label.text()

    def test_refresh_without_repo_reports_error(self, qapp, monkeypatch) -> None:
        from hve.gui import github_issue_panel as module

        monkeypatch.setattr(
            module.github_service,
            "list_issues",
            lambda *_a, **_kw: pytest.fail("must not call API without a repository"),
        )
        widget = module.GitHubIssuePanel()
        widget.refresh_issues()
        assert widget.status_label.text()


class TestNoAutoPolling:
    def test_panel_has_no_timer(self, panel) -> None:
        """FR-GUI-26: 自動ポーリングを行わないこと。"""
        from PySide6.QtCore import QTimer

        assert panel.findChildren(QTimer) == []


class TestWorkerLifetime:
    def test_real_worker_is_released_after_completion(self, qapp, monkeypatch) -> None:
        """実ワーカー使用時に完了後の参照が解放されること。"""
        from hve.gui import github_issue_panel as module

        monkeypatch.setattr(
            module.github_service, "list_issues", lambda repo, state="open", per_page=50: []
        )
        widget = module.GitHubIssuePanel()
        widget.set_repo("o/r")
        widget.refresh_issues()
        assert widget._workers, "worker should be tracked while running"
        widget.shutdown()
        assert widget._workers == []

    def test_url_label_escapes_api_text(self, qapp, monkeypatch) -> None:
        """API 由来文字列を rich text へ直接埋め込まないこと。"""
        from hve.gui import github_issue_panel as module

        widget = module.GitHubIssuePanel()
        widget.set_repo("o/r")
        monkeypatch.setattr(widget, "_load_comments", lambda _n: None)
        widget._on_issue_loaded(
            {
                "number": 1,
                "title": "t",
                "state": "open",
                "body": "",
                "html_url": 'https://example.invalid/"><img src=x>',
            }
        )
        assert "<img" not in widget.url_label.text()
        assert "&lt;img" in widget.url_label.text()
