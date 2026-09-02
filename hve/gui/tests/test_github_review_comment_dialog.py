"""FR-GUI-46: Pull Request の差分行 review comment UI 契約。"""

from __future__ import annotations

import os
from typing import Any, Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from hve.gui.github_comment_editor import GitHubCommentEditor  # noqa: E402
from hve.gui.github_service import GitHubServiceError  # noqa: E402


_PATCH = "\n".join(
    (
        "diff --git a/src/app.py b/src/app.py",
        "index 1111111..2222222 100644",
        "--- a/src/app.py",
        "+++ b/src/app.py",
        "@@ -10,3 +20,4 @@ def run():",
        " context before",
        "-removed",
        "+added",
        " context after",
        "+tail",
        "\\ No newline at end of file",
        "@@ malformed @@",
        "-must not infer old",
        "+must not infer new",
        "@@ -30 +40 @@",
        "-old singleton",
        "+new singleton",
    )
)

_FILES = [
    {"filename": "src/app.py", "status": "modified", "patch": _PATCH},
    {"filename": "assets/logo.png", "status": "modified"},
]

_COMMENTS = [
    {
        "id": 2,
        "user": {"login": "second-by-api-order"},
        "path": "src/app.py",
        "line": 21,
        "side": "RIGHT",
        "body": "second comment\nnot shown",
        "created_at": "2026-08-27T02:00:00Z",
    },
    {
        "id": 1,
        "user": {"login": "first-by-time"},
        "path": "src/app.py",
        "line": 11,
        "side": "LEFT",
        "body": "first comment",
        "created_at": "2026-08-27T01:00:00Z",
    },
]


class _FilesSnapshot(list):
    def __init__(self, values, *, head_sha: str = "abc123") -> None:
        super().__init__(values)
        self.head_sha = head_sha


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _dispose_dialog(widget, qapp) -> None:
    workers = list(widget._workers)
    widget.shutdown(0)
    for worker in workers:
        worker.deleteLater()
    widget.close()
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def _line_signature(rows) -> list[tuple[str, int, str, str]]:
    return [(row.path, row.line, row.side, row.text) for row in rows]


class TestStrictPatchParsing:
    def test_emits_only_commentable_lines_with_exact_coordinates(self) -> None:
        from hve.gui.github_review_comment_dialog import (
            parse_commentable_diff_lines,
        )

        rows = parse_commentable_diff_lines("src/app.py", _PATCH)

        assert _line_signature(rows) == [
            ("src/app.py", 20, "RIGHT", "context before"),
            ("src/app.py", 11, "LEFT", "removed"),
            ("src/app.py", 21, "RIGHT", "added"),
            ("src/app.py", 22, "RIGHT", "context after"),
            ("src/app.py", 23, "RIGHT", "tail"),
            ("src/app.py", 30, "LEFT", "old singleton"),
            ("src/app.py", 40, "RIGHT", "new singleton"),
        ]

    @pytest.mark.parametrize(
        "patch",
        [
            "-outside\n+outside",
            "@@ broken @@\n-old\n+new",
            "@@ -1,2 +1,2 @@\n-old\n+new",
            "@@ -1 +1 @@\n?unknown",
            "@@ -x +1 @@\n-old\n+new",
        ],
    )
    def test_never_infers_coordinates_for_outside_or_malformed_hunks(
        self, patch: str
    ) -> None:
        from hve.gui.github_review_comment_dialog import (
            parse_commentable_diff_lines,
        )

        assert parse_commentable_diff_lines("src/app.py", patch) == ()

    def test_zero_count_added_and_deleted_hunks_are_supported(self) -> None:
        from hve.gui.github_review_comment_dialog import (
            parse_commentable_diff_lines,
        )

        patch = "\n".join(
            (
                "@@ -0,0 +1,2 @@",
                "+one",
                "+two",
                "@@ -5,2 +7,0 @@",
                "-old one",
                "-old two",
            )
        )

        assert _line_signature(parse_commentable_diff_lines("new.txt", patch)) == [
            ("new.txt", 1, "RIGHT", "one"),
            ("new.txt", 2, "RIGHT", "two"),
            ("new.txt", 5, "LEFT", "old one"),
            ("new.txt", 6, "LEFT", "old two"),
        ]

    def test_file_builder_skips_missing_patch_blank_path_and_empty_hunks(self) -> None:
        from hve.gui.github_review_comment_dialog import build_commentable_files

        files = build_commentable_files(
            [
                *_FILES,
                {"filename": "", "patch": "@@ -1 +1 @@\n-old\n+new"},
                {"filename": "empty.txt", "patch": ""},
                {"filename": "bad.txt", "patch": "@@ bad @@\n-old\n+new"},
            ]
        )

        assert [entry.path for entry in files] == ["src/app.py"]
        assert len(files[0].lines) == 7


@pytest.fixture
def dialog(qapp, monkeypatch):
    from hve.gui import github_review_comment_dialog as module

    calls: dict[str, list[Any]] = {
        "list_pull_request_review_comments": [],
        "create_pull_request_review_comment": [],
    }
    state: dict[str, Any] = {
        "comments": list(_COMMENTS),
        "create_result": {"id": 99},
    }

    def _list_comments(repo: str, number: Any, per_page: int = 100) -> Any:
        calls["list_pull_request_review_comments"].append(
            (repo, int(number), per_page)
        )
        result = state["comments"]
        if isinstance(result, Exception):
            raise result
        return list(result) if isinstance(result, list) else result

    def _create_comment(
        repo: str,
        number: Any,
        body: str,
        commit_id: str,
        path: str,
        line: int,
        side: str,
    ) -> Any:
        calls["create_pull_request_review_comment"].append(
            (repo, int(number), body, commit_id, path, line, side)
        )
        result = state["create_result"]
        if isinstance(result, Exception):
            raise result
        return dict(result) if isinstance(result, dict) else result

    monkeypatch.setattr(
        module.github_service,
        "list_pull_request_review_comments",
        _list_comments,
    )
    monkeypatch.setattr(
        module.github_service,
        "create_pull_request_review_comment",
        _create_comment,
    )
    monkeypatch.setattr(
        module.GitHubWorker,
        "start",
        lambda self, *_args, **_kwargs: self.run(),
    )

    widget = module.GitHubReviewCommentDialog(
        "o/r",
        42,
        "abc123",
        _FILES,
    )
    widget._test_calls = calls  # type: ignore[attr-defined]
    widget._test_state = state  # type: ignore[attr-defined]
    yield widget
    _dispose_dialog(widget, qapp)


def _select_line(dialog, row: int) -> None:
    dialog.line_table.setCurrentCell(row, 0)


def _table_texts(table) -> list[list[str]]:
    return [
        [table.item(row, col).text() for col in range(table.columnCount())]
        for row in range(table.rowCount())
    ]


class TestDialogSurface:
    def test_shows_only_commentable_rows_and_immutable_target_fields(
        self, dialog
    ) -> None:
        assert dialog.file_combo.count() == 1
        assert dialog.file_combo.currentText() == "src/app.py"
        assert dialog.line_table.rowCount() == 7
        assert _table_texts(dialog.line_table)[0] == ["RIGHT", "20", "context before"]
        assert isinstance(dialog.body_edit, GitHubCommentEditor)
        assert "o/r" in dialog.repo_label.text()
        assert "#42" in dialog.pull_request_label.text()
        assert "abc123" in dialog.commit_id_label.text()

        _select_line(dialog, 1)

        assert dialog.path_label.text() == "src/app.py"
        assert dialog.line_label.text() == "11"
        assert dialog.side_label.text() == "LEFT"

    def test_lists_existing_review_comments_once_in_api_order(self, dialog) -> None:
        assert dialog._test_calls["list_pull_request_review_comments"] == [
            ("o/r", 42, 100)
        ]
        rows = [
            dialog.review_comment_list.item(index).text()
            for index in range(dialog.review_comment_list.count())
        ]
        assert "second-by-api-order" in rows[0]
        assert "first-by-time" in rows[1]
        assert "not shown" not in rows[0]

    def test_submit_requires_explicit_line_and_nonempty_body(self, dialog) -> None:
        dialog.body_edit.set_text("comment")
        assert not dialog.submit_button.isEnabled()

        _select_line(dialog, 2)
        assert dialog.submit_button.isEnabled()

        dialog.body_edit.set_text(" \n ")
        assert not dialog.submit_button.isEnabled()
        assert dialog._test_calls["create_pull_request_review_comment"] == []


class TestDialogSubmission:
    def test_submit_uses_exact_selected_values_and_accepts_only_on_success(
        self, dialog
    ) -> None:
        _select_line(dialog, 2)
        dialog.body_edit.set_text("Please fix this.")

        dialog.submit_button.click()

        assert dialog._test_calls["create_pull_request_review_comment"] == [
            (
                "o/r",
                42,
                "Please fix this.",
                "abc123",
                "src/app.py",
                21,
                "RIGHT",
            )
        ]
        assert dialog.result() == int(QDialog.DialogCode.Accepted)

        dialog.submit_review_comment()
        assert len(dialog._test_calls["create_pull_request_review_comment"]) == 1

    def test_failure_preserves_body_file_line_and_reenables(self, dialog) -> None:
        _select_line(dialog, 1)
        dialog.body_edit.set_text("keep this body")
        dialog._test_state["create_result"] = GitHubServiceError("submit failed")

        dialog.submit_button.click()

        target = dialog.current_target()
        assert target is not None
        assert (target.path, target.line, target.side) == (
            "src/app.py",
            11,
            "LEFT",
        )
        assert dialog.body_edit.text() == "keep this body"
        assert dialog.submit_button.isEnabled()
        assert dialog.result() != int(QDialog.DialogCode.Accepted)
        assert "submit failed" in dialog.status_label.text()

    def test_failure_preserves_nondefault_file_selection(
        self, qapp, monkeypatch
    ) -> None:
        from hve.gui import github_review_comment_dialog as module

        calls: list[tuple[Any, ...]] = []
        monkeypatch.setattr(
            module.github_service,
            "list_pull_request_review_comments",
            lambda *_args, **_kwargs: [],
        )

        def _fail(*args: Any) -> dict:
            calls.append(args)
            raise GitHubServiceError("keep selection")

        monkeypatch.setattr(
            module.github_service,
            "create_pull_request_review_comment",
            _fail,
        )
        monkeypatch.setattr(
            module.GitHubWorker,
            "start",
            lambda self, *_args, **_kwargs: self.run(),
        )
        widget = module.GitHubReviewCommentDialog(
            "o/r",
            42,
            "abc123",
            [
                {
                    "filename": "src/first.py",
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                },
                {
                    "filename": "src/second.py",
                    "patch": "@@ -8 +9 @@\n-before\n+after",
                },
            ],
        )
        try:
            widget.file_combo.setCurrentIndex(1)
            _select_line(widget, 1)
            widget.body_edit.set_text("preserve all")

            widget.submit_review_comment()

            target = widget.current_target()
            assert target is not None
            assert widget.file_combo.currentIndex() == 1
            assert (target.path, target.line, target.side) == (
                "src/second.py",
                9,
                "RIGHT",
            )
            assert widget.body_edit.text() == "preserve all"
            assert widget.submit_button.isEnabled()
            assert calls == [
                (
                    "o/r",
                    42,
                    "preserve all",
                    "abc123",
                    "src/second.py",
                    9,
                    "RIGHT",
                )
            ]
        finally:
            _dispose_dialog(widget, qapp)

    @pytest.mark.parametrize("result", [None, {}, {"id": 0}, {"id": "bad"}])
    def test_malformed_success_response_is_failure(self, dialog, result: Any) -> None:
        _select_line(dialog, 0)
        dialog.body_edit.set_text("keep")
        dialog._test_state["create_result"] = result

        dialog.submit_button.click()

        assert dialog.body_edit.text() == "keep"
        assert dialog.submit_button.isEnabled()
        assert dialog.result() != int(QDialog.DialogCode.Accepted)
        assert "解釈" in dialog.status_label.text()

    def test_double_submit_is_blocked_while_worker_is_pending(
        self, dialog, monkeypatch
    ) -> None:
        pending: list[
            tuple[
                Callable[[], Any],
                Callable[[Any], None],
                Callable[[str], None] | None,
            ]
        ] = []

        def _defer(task, on_ok, on_ng=None) -> None:
            pending.append((task, on_ok, on_ng))

        monkeypatch.setattr(dialog, "_run", _defer)
        _select_line(dialog, 2)
        dialog.body_edit.set_text("only once")

        dialog.submit_review_comment()
        dialog.submit_review_comment()

        assert len(pending) == 1
        assert not dialog.submit_button.isEnabled()
        task, on_ok, _on_ng = pending.pop()
        result = task()
        on_ok(result)
        assert dialog._test_calls["create_pull_request_review_comment"] == [
            ("o/r", 42, "only once", "abc123", "src/app.py", 21, "RIGHT")
        ]

    def test_constructor_copies_context_before_source_mutation(
        self, qapp, monkeypatch
    ) -> None:
        from hve.gui import github_review_comment_dialog as module

        source_files = [
            {
                "filename": "src/original.py",
                "patch": "@@ -1 +1 @@\n-old\n+new",
            }
        ]
        captured: dict[str, tuple[Any, ...]] = {}
        monkeypatch.setattr(
            module.github_service,
            "list_pull_request_review_comments",
            lambda *_args, **_kwargs: [],
        )

        def _capture_create(*args: Any) -> dict[str, int]:
            captured["args"] = args
            return {"id": 1}

        monkeypatch.setattr(
            module.github_service,
            "create_pull_request_review_comment",
            _capture_create,
        )
        monkeypatch.setattr(
            module.GitHubWorker,
            "start",
            lambda self, *_args, **_kwargs: self.run(),
        )
        widget = module.GitHubReviewCommentDialog(
            "o/original", 7, "frozen-sha", source_files
        )
        try:
            source_files[0]["filename"] = "src/mutated.py"
            source_files[0]["patch"] = "@@ -9 +9 @@\n-x\n+y"
            _select_line(widget, 1)
            widget.body_edit.set_text("frozen target")

            widget.submit_review_comment()

            assert captured == {
                "args": (
                    "o/original",
                    7,
                    "frozen target",
                    "frozen-sha",
                    "src/original.py",
                    1,
                    "RIGHT",
                )
            }
        finally:
            _dispose_dialog(widget, qapp)


class TestPanelLaunchContract:
    @pytest.fixture(autouse=True)
    def _dispose_loaded_panels(self, qapp):
        self._loaded_panels: list[Any] = []
        yield
        for panel in reversed(self._loaded_panels):
            panel.shutdown(0)
            panel.close()
            panel.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()

    def _loaded_panel(self, qapp, monkeypatch, *, head: dict[str, Any]):
        from hve.gui import github_pr_panel as module

        widget = module.GitHubPullRequestPanel()
        self._loaded_panels.append(widget)
        widget.set_repo("o/r")
        monkeypatch.setattr(widget, "_load_files", lambda _number: None)
        monkeypatch.setattr(widget, "_load_comments", lambda _number: None)
        monkeypatch.setattr(
            widget,
            "_request_pull_request_reviews",
            lambda *_args, **_kwargs: None,
        )
        generation = widget._pull_request_load_generation
        widget._on_pull_request_loaded(
            {
                "number": 42,
                "title": "target",
                "state": "open",
                "head": head,
                "base": {"ref": "main"},
                "body": "",
            },
            repo_at_request="o/r",
            number_at_request=42,
            generation=generation,
        )
        return module, widget

    def test_files_not_fetched_disables_launch_with_guidance(
        self, qapp, monkeypatch
    ) -> None:
        _module, panel = self._loaded_panel(
            qapp,
            monkeypatch,
            head={"ref": "feature", "sha": "abc123"},
        )

        assert not panel.review_comment_button.isEnabled()
        assert "取得" in panel.review_comment_hint_label.text()

    def test_missing_head_sha_disables_launch_with_guidance(
        self, qapp, monkeypatch
    ) -> None:
        _module, panel = self._loaded_panel(
            qapp,
            monkeypatch,
            head={"ref": "feature"},
        )
        panel._on_files_loaded(_FilesSnapshot(_FILES))

        assert not panel.review_comment_button.isEnabled()
        assert "head SHA" in panel.review_comment_hint_label.text()

    def test_files_from_a_different_head_disable_launch(
        self, qapp, monkeypatch
    ) -> None:
        _module, panel = self._loaded_panel(
            qapp,
            monkeypatch,
            head={"ref": "feature", "sha": "detail-snapshot-sha"},
        )

        panel._on_files_loaded(
            _FilesSnapshot(_FILES, head_sha="files-snapshot-sha")
        )

        assert not panel.review_comment_button.isEnabled()
        assert "head SHA" in panel.review_comment_hint_label.text()

    def test_files_without_snapshot_head_disable_launch(
        self, qapp, monkeypatch
    ) -> None:
        _module, panel = self._loaded_panel(
            qapp,
            monkeypatch,
            head={"ref": "feature", "sha": "detail-snapshot-sha"},
        )

        panel._on_files_loaded(list(_FILES))

        assert not panel.review_comment_button.isEnabled()
        assert "head SHA" in panel.review_comment_hint_label.text()

    @pytest.mark.parametrize(
        "files",
        [
            [],
            [{"filename": "binary.dat", "status": "modified"}],
            [{"filename": "bad.py", "patch": "@@ bad @@\n-old\n+new"}],
        ],
    )
    def test_no_commentable_patch_disables_launch(
        self, qapp, monkeypatch, files
    ) -> None:
        _module, panel = self._loaded_panel(
            qapp,
            monkeypatch,
            head={"ref": "feature", "sha": "abc123"},
        )
        panel._on_files_loaded(_FilesSnapshot(files))

        assert not panel.review_comment_button.isEnabled()
        assert "patch" in panel.review_comment_hint_label.text()

    def test_ready_context_launches_dialog_with_frozen_repo_number_sha_and_files(
        self, qapp, monkeypatch
    ) -> None:
        module, panel = self._loaded_panel(
            qapp,
            monkeypatch,
            head={"ref": "feature", "sha": "abc123"},
        )
        panel._on_files_loaded(_FilesSnapshot(_FILES))
        captured: list[tuple[Any, ...]] = []

        class _FakeDialog:
            def __init__(self, repo, number, commit_id, files, parent=None):
                captured.append((repo, number, commit_id, files, parent))

            def exec(self):
                return QDialog.DialogCode.Rejected

        monkeypatch.setattr(module, "GitHubReviewCommentDialog", _FakeDialog)

        assert panel.review_comment_button.isEnabled()
        panel.open_review_comment_dialog()

        assert len(captured) == 1
        repo, number, commit_id, files, parent = captured[0]
        assert (repo, number, commit_id, parent) == (
            "o/r",
            42,
            "abc123",
            panel,
        )
        assert files is not _FILES
        assert files[0] is not _FILES[0]
        assert files[0]["patch"] == _PATCH
        assert panel._current_files is not None
