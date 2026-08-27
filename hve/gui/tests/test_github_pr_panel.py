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

from hve.gui.git_ops import GitOpsError  # noqa: E402
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
        "head": {"ref": "copilot-sdk/aad-1234abcd", "repo": {"full_name": "o/r"}},
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
        "head": {"ref": "fix/x", "repo": {"full_name": "o/r"}},
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
        "delete_branch": [],
    }

    def _list_pull_requests(
        repo: str,
        state: str = "open",
        per_page: int = 50,
        page: int = 1,
    ) -> List[dict[str, Any]]:
        calls["list_pull_requests"].append((repo, state))
        return list(_PULLS)

    def _get_pull_request(repo: str, number: Any) -> dict[str, Any]:
        calls["get_pull_request"].append((repo, number))
        return next(pull for pull in _PULLS if pull["number"] == int(number))

    monkeypatch.setattr(
        module.github_service,
        "list_pull_requests",
        _list_pull_requests,
    )
    monkeypatch.setattr(
        module.github_service,
        "get_pull_request",
        _get_pull_request,
    )
    monkeypatch.setattr(
        module.github_service, "list_pull_request_files", lambda repo, number: list(_FILES)
    )
    monkeypatch.setattr(
        module.github_service, "list_comments", lambda repo, number: list(_COMMENTS)
    )
    monkeypatch.setattr(
        module.github_service, "list_pull_request_reviews", lambda repo, number: []
    )
    monkeypatch.setattr(
        module.github_service,
        "post_comment",
        lambda repo, number, body: calls["post_comment"].append((repo, number, body)),
    )
    monkeypatch.setattr(
        module.github_service,
        "delete_branch",
        lambda repo, branch: calls["delete_branch"].append((repo, branch)),
    )

    widget = module.GitHubPullRequestPanel()
    widget.set_repo("o/r")

    def _sync(task, on_ok, on_ng=None):
        try:
            result = task()
        except (GitHubServiceError, GitOpsError) as exc:
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
        panel.new_comment_edit.set_text("レビューコメント")
        panel.post_comment()
        assert panel._calls["post_comment"][-1] == ("o/r", 42, "レビューコメント")
        assert panel.new_comment_edit.text() == ""

    def test_post_comment_requires_selection(self, panel) -> None:
        panel.new_comment_edit.set_text("孤児コメント")
        panel.post_comment()
        assert panel._calls["post_comment"] == []

    def test_body_view_is_read_only(self, panel) -> None:
        """PR 本文の編集は本要件の対象外。"""
        assert panel.body_view.isReadOnly()


class TestPullRequestCreationEntry:
    def test_panel_has_create_action(self, panel) -> None:
        """FR-GUI-42: GUI から PR を新規作成する操作を提供すること。"""
        from PySide6.QtWidgets import QPushButton

        labels = [b.text() for b in panel.findChildren(QPushButton)]
        assert "Pull Request を作成" in labels

    def test_module_uses_service_create_pull_request(self) -> None:
        import ast
        from pathlib import Path

        import hve.gui.github_pr_panel as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        names = {
            node.attr for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Attribute)
        }
        assert "create_pull_request" in names


class TestCommentEditorWiring:
    """FR-GUI-30: PR の新規コメント欄が共通ウィジェットであること。"""

    def test_new_comment_uses_shared_editor(self, panel) -> None:
        from hve.gui.github_comment_editor import GitHubCommentEditor

        assert isinstance(panel.new_comment_edit, GitHubCommentEditor)

    def test_editor_keeps_markdown_source(self, panel) -> None:
        source = "- [ ] a\n\n```sh\nls\n```"
        panel.new_comment_edit.set_text(source)
        assert panel.new_comment_edit.text() == source


class TestEmptyResultGuidance:
    """FR-GUI-31: 0 件時に絞り込み状態と切り替え手段を提示すること。"""

    def test_open_zero_suggests_all_state(self, panel, monkeypatch) -> None:
        from hve.gui import github_pr_panel as module

        monkeypatch.setattr(
            module.github_service,
            "list_pull_requests",
            lambda repo, state="open", per_page=50, page=1: [],
        )
        panel.refresh_pull_requests()
        text = panel.status_label.text()
        assert "オープン" in text
        assert "すべて" in text

    def test_all_state_zero_does_not_suggest_switching(self, panel, monkeypatch) -> None:
        from hve.gui import github_pr_panel as module

        monkeypatch.setattr(
            module.github_service,
            "list_pull_requests",
            lambda repo, state="open", per_page=50, page=1: [],
        )
        panel.state_combo.setCurrentIndex(panel.state_combo.findData("all"))
        panel.refresh_pull_requests()
        assert "すべて" not in panel.status_label.text()


class TestClientSideFilter:
    """FR-GUI-31: 絞り込みが追加の API 呼び出しを行わないこと。"""

    def test_filter_narrows_visible_rows(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.filter_edit.setText("バグ")
        assert panel.pr_list.count() == 1
        assert "#41" in panel.pr_list.item(0).text()

    def test_filter_does_not_call_api(self, panel) -> None:
        panel.refresh_pull_requests()
        before = len(panel._calls["list_pull_requests"])
        panel.filter_edit.setText("バグ")
        assert len(panel._calls["list_pull_requests"]) == before

    def test_selection_uses_filtered_row(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.filter_edit.setText("バグ")
        panel.pr_list.setCurrentRow(0)
        assert panel._calls["get_pull_request"][-1] == ("o/r", 41)


class TestLoadOnce:
    """FR-GUI-31: リポジトリ確定時に 1 回だけ取得すること。"""

    def test_loads_on_first_call(self, panel) -> None:
        panel.load_once()
        assert len(panel._calls["list_pull_requests"]) == 1

    def test_second_call_for_same_repo_does_not_refetch(self, panel) -> None:
        panel.load_once()
        panel.load_once()
        assert len(panel._calls["list_pull_requests"]) == 1

    def test_no_repo_does_not_load(self, panel) -> None:
        panel.set_repo("")
        panel.load_once()
        assert panel._calls["list_pull_requests"] == []


class TestConsoleLogPost:
    """FR-GUI-33: コンソール出力の PR コメント投稿。"""

    def test_button_disabled_without_provider(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        assert not panel.post_console_button.isEnabled()

    def test_button_enabled_with_provider_and_selection(self, panel) -> None:
        panel.set_console_source(lambda: "log")
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        assert panel.post_console_button.isEnabled()

    def test_button_disabled_without_selection(self, panel) -> None:
        panel.set_console_source(lambda: "log")
        assert not panel.post_console_button.isEnabled()

    def test_posts_formatted_body(self, panel) -> None:
        panel.set_console_source(lambda: "line1\nline2", run_id="20260825T000000-abcdef")
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        panel.post_console_log()
        repo, number, body = panel._calls["post_comment"][-1]
        assert (repo, number) == ("o/r", 42)
        assert body.startswith("### HVE コンソール出力")
        assert "| run-id | `20260825T000000-abcdef` |" in body
        assert "| 総行数 | 2 |" in body
        assert "line2" in body

    def test_does_not_post_empty_console(self, panel) -> None:
        panel.set_console_source(lambda: "   ")
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        panel.post_console_log()
        assert panel._calls["post_comment"] == []
        assert panel.status_label.text()

    def test_does_not_post_without_provider(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        panel.post_console_log()
        assert panel._calls["post_comment"] == []

    def test_does_not_post_without_selection(self, panel) -> None:
        panel.set_console_source(lambda: "log")
        panel.post_console_log()
        assert panel._calls["post_comment"] == []


class TestPushAndDeleteBranch:
    """FR-GUI-34: push と head ブランチ削除。"""

    def test_push_and_delete_are_separate_buttons(self, panel) -> None:
        assert panel.push_button is not panel.delete_branch_button

    def test_push_calls_git_ops_only(self, panel, monkeypatch) -> None:
        from hve.gui import github_pr_panel as module

        seen: List[str] = []

        def _push_current_branch(*_args: Any, **_kwargs: Any) -> str:
            seen.append("pushed")
            return "feature-x"

        monkeypatch.setattr(
            module.git_ops,
            "push_current_branch",
            _push_current_branch,
        )
        panel.push_current_branch()
        assert seen == ["pushed"]
        assert "feature-x" in panel.status_label.text()
        assert panel._calls["delete_branch"] == []

    def test_push_failure_is_reported(self, panel, monkeypatch) -> None:
        from hve.gui import github_pr_panel as module

        def _boom(*_args, **_kwargs):
            raise GitOpsError("push に失敗しました: rejected")

        monkeypatch.setattr(module.git_ops, "push_current_branch", _boom)
        panel.push_current_branch()
        assert "rejected" in panel.status_label.text()

    def test_delete_disabled_for_open_pr(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)  # #42 open
        assert not panel.delete_branch_button.isEnabled()

    def test_delete_enabled_for_merged_pr(self, panel) -> None:
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(1)  # #41 merged/closed
        assert panel.delete_branch_button.isEnabled()

    def test_delete_requires_confirmation(self, panel, monkeypatch) -> None:
        monkeypatch.setattr(panel, "_confirm_delete_branch", lambda _b: False)
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(1)
        panel.delete_head_branch()
        assert panel._calls["delete_branch"] == []

    def test_delete_uses_github_service_with_head_ref(self, panel, monkeypatch) -> None:
        monkeypatch.setattr(panel, "_confirm_delete_branch", lambda _b: True)
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(1)
        panel.delete_head_branch()
        assert panel._calls["delete_branch"] == [("o/r", "fix/x")]

    def test_delete_button_is_disabled_after_success(self, panel, monkeypatch) -> None:
        monkeypatch.setattr(panel, "_confirm_delete_branch", lambda _b: True)
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(1)
        panel.delete_head_branch()
        assert not panel.delete_branch_button.isEnabled()

    @pytest.mark.parametrize(
        "pr,expected",
        [
            ({"state": "open", "merged": False}, False),
            ({"state": "closed", "merged": False}, True),
            ({"state": "closed", "merged": True}, True),
            ({"state": "open", "merged": True}, True),
            ({}, False),
        ],
    )
    def test_deletable_state_matrix(self, panel, pr, expected) -> None:
        assert panel._is_branch_deletable(pr) is expected

    def test_missing_head_ref_blocks_delete(self, panel, monkeypatch) -> None:
        from hve.gui import github_pr_panel as module

        monkeypatch.setattr(panel, "_confirm_delete_branch", lambda _b: True)
        monkeypatch.setattr(
            module.github_service,
            "get_pull_request",
            lambda repo, number: {"number": 41, "state": "closed", "merged": True},
        )
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(1)
        panel.delete_head_branch()
        assert panel._calls["delete_branch"] == []
        assert not panel.delete_branch_button.isEnabled()

    def test_delete_blocked_for_open_pr_even_if_invoked(self, panel, monkeypatch) -> None:
        monkeypatch.setattr(panel, "_confirm_delete_branch", lambda _b: True)
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        panel.delete_head_branch()
        assert panel._calls["delete_branch"] == []

    def test_delete_does_not_touch_local_branch(self) -> None:
        import ast
        from pathlib import Path

        import hve.gui.github_pr_panel as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        names = {
            node.attr for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Attribute)
        }
        assert "delete_local_branch" not in names
        assert "_git_delete_local_branch" not in names


class TestForkHeadIsNotDeleted:
    """FR-GUI-34: 削除対象は origin のブランチに限る（fork の head を誤削除しない）。"""

    def _select_fork_pr(self, panel, monkeypatch, head_repo) -> None:
        from hve.gui import github_pr_panel as module

        monkeypatch.setattr(
            module.github_service,
            "get_pull_request",
            lambda repo, number: {
                "number": 41,
                "state": "closed",
                "merged": True,
                "head": {"ref": "fix/x", "repo": head_repo},
                "base": {"ref": "main"},
            },
        )
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(1)

    def test_button_is_disabled_for_a_fork_head(self, panel, monkeypatch) -> None:
        self._select_fork_pr(panel, monkeypatch, {"full_name": "someone/r"})
        assert not panel.delete_branch_button.isEnabled()

    def test_direct_invocation_does_not_delete_a_fork_head(self, panel, monkeypatch) -> None:
        monkeypatch.setattr(panel, "_confirm_delete_branch", lambda _b: True)
        self._select_fork_pr(panel, monkeypatch, {"full_name": "someone/r"})
        panel.delete_head_branch()
        assert panel._calls["delete_branch"] == []

    def test_missing_head_repo_blocks_delete(self, panel, monkeypatch) -> None:
        monkeypatch.setattr(panel, "_confirm_delete_branch", lambda _b: True)
        self._select_fork_pr(panel, monkeypatch, None)
        panel.delete_head_branch()
        assert panel._calls["delete_branch"] == []
        assert not panel.delete_branch_button.isEnabled()

    def test_same_repo_head_is_still_deletable(self, panel, monkeypatch) -> None:
        monkeypatch.setattr(panel, "_confirm_delete_branch", lambda _b: True)
        self._select_fork_pr(panel, monkeypatch, {"full_name": "o/r"})
        panel.delete_head_branch()
        assert panel._calls["delete_branch"] == [("o/r", "fix/x")]

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
            lambda repo, state="open", per_page=50, page=1: [],
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


class TestLinkedPullRequestSelection:
    """FR-GUI-32: 設定で関連付けた PR を読込済み一覧から事前選択すること。"""

    def test_known_number_selects_the_row(self, panel) -> None:
        panel.refresh_pull_requests()
        assert panel.select_pull_request(41) is True
        assert panel.pr_list.currentRow() == 1
        assert panel._current is not None
        assert panel._current["number"] == 41

    def test_unknown_number_does_not_select(self, panel) -> None:
        panel.refresh_pull_requests()
        assert panel.select_pull_request(999) is False
        assert panel.pr_list.currentRow() == -1
        assert panel._current is None

    def test_unknown_number_does_not_call_api(self, panel) -> None:
        panel.refresh_pull_requests()
        before = len(panel._calls["get_pull_request"])
        panel.select_pull_request(999)
        assert len(panel._calls["get_pull_request"]) == before

    def test_selection_does_not_refetch_the_list(self, panel) -> None:
        panel.refresh_pull_requests()
        before = len(panel._calls["list_pull_requests"])
        panel.select_pull_request(42)
        assert len(panel._calls["list_pull_requests"]) == before

    def test_without_loaded_list_it_is_a_noop(self, panel) -> None:
        assert panel.select_pull_request(42) is False
        assert panel._calls["list_pull_requests"] == []
        assert panel._calls["get_pull_request"] == []

    def test_linked_number_is_applied_after_the_list_arrives(self, panel) -> None:
        """一覧は非同期に届くため、指定時点で未取得でも後から選択されること。"""
        panel.set_linked_pull_request(41)
        assert panel.pr_list.currentRow() == -1
        panel.refresh_pull_requests()
        assert panel.pr_list.currentRow() == 1
        assert panel._current is not None
        assert panel._current["number"] == 41

    def test_linked_number_is_applied_only_once(self, panel) -> None:
        """消費済みの関連付けを、以後の更新のたびに再適用しないこと。"""
        panel.set_linked_pull_request(41)
        panel.refresh_pull_requests()
        assert panel.pr_list.currentRow() == 1
        panel.refresh_pull_requests()
        assert panel.pr_list.currentRow() == -1
        assert panel._linked_number is None

    def test_linked_number_absent_from_the_list_leaves_selection(self, panel) -> None:
        panel.set_linked_pull_request(999)
        panel.refresh_pull_requests()
        assert panel.pr_list.currentRow() == -1
        assert panel._current is None

    @pytest.mark.parametrize("value", [None, 0])
    def test_unset_linked_number_selects_nothing(self, panel, value) -> None:
        panel.set_linked_pull_request(value)
        panel.refresh_pull_requests()
        assert panel.pr_list.currentRow() == -1

    def test_manual_selection_discards_a_pending_link(self, panel) -> None:
        """一覧に無い番号の保留が残留し、後から利用者の選択を上書きしないこと。"""
        panel.set_linked_pull_request(999)
        panel.refresh_pull_requests()
        panel.pr_list.setCurrentRow(0)
        assert panel._linked_number is None
