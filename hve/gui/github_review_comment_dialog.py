"""Pull Request の取得済み patch へ行単位 review comment を投稿する Dialog。

FR-GUI-46 の範囲だけを扱い、汎用 diff viewer にはしない。GitHub が返した
unified hunk から座標を厳格に確定できる行だけを表示し、投稿は
``GitHubWorker`` 経由の利用者明示操作に限定する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
import re
from typing import Any, Callable, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import github_service
from .github_comment_editor import GitHubCommentEditor
from .github_threads import GitHubWorker

__all__ = [
    "CommentableDiffLine",
    "CommentableFile",
    "GitHubReviewCommentDialog",
    "build_commentable_files",
    "parse_commentable_diff_lines",
]

_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?: .*)?$"
)


@dataclass(frozen=True)
class CommentableDiffLine:
    """GitHub review comment API へ渡せる 1 行の immutable 座標。"""

    path: str
    line: int
    side: str
    text: str


@dataclass(frozen=True)
class CommentableFile:
    """commentable 行を 1 件以上持つ変更ファイル。"""

    path: str
    lines: tuple[CommentableDiffLine, ...]


@dataclass
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    old_used: int = 0
    new_used: int = 0
    rows: List[CommentableDiffLine] = field(default_factory=list)

    def complete(self) -> bool:
        return self.old_used == self.old_count and self.new_used == self.new_count


def _new_hunk(match: re.Match[str]) -> Optional[_Hunk]:
    old_start = int(match.group("old_start"))
    new_start = int(match.group("new_start"))
    old_count = int(match.group("old_count") or "1")
    new_count = int(match.group("new_count") or "1")
    if (old_count > 0 and old_start <= 0) or (
        new_count > 0 and new_start <= 0
    ):
        return None
    return _Hunk(
        old_start=old_start,
        old_count=old_count,
        new_start=new_start,
        new_count=new_count,
    )


def parse_commentable_diff_lines(
    path: str, patch: str
) -> tuple[CommentableDiffLine, ...]:
    """unified hunk から座標を確定できる行だけを返す。

    hunk header、行種別、宣言行数のいずれかが不正な hunk は丸ごと破棄する。
    hunk 外の行、file metadata、``\\ No newline ...`` は座標推測に使わない。
    """
    if not isinstance(path, str) or not path.strip():
        return ()
    if not isinstance(patch, str) or not patch:
        return ()

    parsed: List[CommentableDiffLine] = []
    hunk: Optional[_Hunk] = None

    def _finish() -> None:
        nonlocal hunk
        if hunk is not None and hunk.complete():
            parsed.extend(hunk.rows)
        hunk = None

    for raw_line in patch.splitlines():
        header = _HUNK_HEADER.fullmatch(raw_line)
        if header is not None:
            _finish()
            hunk = _new_hunk(header)
            continue
        if raw_line.startswith("@@"):
            _finish()
            continue
        if hunk is None:
            continue
        if raw_line.startswith("\\ No newline"):
            continue
        if hunk.complete() or not raw_line:
            hunk = None
            continue

        marker = raw_line[0]
        text = raw_line[1:]
        if marker == " ":
            if hunk.old_used >= hunk.old_count or hunk.new_used >= hunk.new_count:
                hunk = None
                continue
            line = hunk.new_start + hunk.new_used
            if line <= 0:
                hunk = None
                continue
            hunk.rows.append(CommentableDiffLine(path, line, "RIGHT", text))
            hunk.old_used += 1
            hunk.new_used += 1
        elif marker == "-":
            if hunk.old_used >= hunk.old_count:
                hunk = None
                continue
            line = hunk.old_start + hunk.old_used
            if line <= 0:
                hunk = None
                continue
            hunk.rows.append(CommentableDiffLine(path, line, "LEFT", text))
            hunk.old_used += 1
        elif marker == "+":
            if hunk.new_used >= hunk.new_count:
                hunk = None
                continue
            line = hunk.new_start + hunk.new_used
            if line <= 0:
                hunk = None
                continue
            hunk.rows.append(CommentableDiffLine(path, line, "RIGHT", text))
            hunk.new_used += 1
        else:
            hunk = None

    _finish()
    return tuple(parsed)


def build_commentable_files(files: Any) -> tuple[CommentableFile, ...]:
    """取得済み PR files から commentable なファイルだけを immutable 化する。"""
    if not isinstance(files, (list, tuple)):
        return ()
    result: List[CommentableFile] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("filename")
        patch = entry.get("patch")
        if not isinstance(path, str) or not path.strip():
            continue
        if not isinstance(patch, str) or not patch:
            continue
        lines = parse_commentable_diff_lines(path, patch)
        if lines:
            result.append(CommentableFile(path=path, lines=lines))
    return tuple(result)


class GitHubReviewCommentDialog(QDialog):
    """取得時点の repo / PR / commit / patch だけへ投稿する modal dialog。"""

    def __init__(
        self,
        repo: str,
        pull_request_number: int,
        commit_id: str,
        files: Sequence[dict[str, Any]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        resolved_repo = repo.strip() if isinstance(repo, str) else ""
        resolved_commit = commit_id.strip() if isinstance(commit_id, str) else ""
        if not resolved_repo:
            raise ValueError("repository is required")
        if (
            isinstance(pull_request_number, bool)
            or not isinstance(pull_request_number, int)
            or pull_request_number <= 0
        ):
            raise ValueError("pull request number must be positive")
        if not resolved_commit:
            raise ValueError("head SHA is required")
        commentable_files = build_commentable_files(list(files))
        if not commentable_files:
            raise ValueError("commentable patch is required")

        self._repo = resolved_repo
        self._pull_request_number = pull_request_number
        self._commit_id = resolved_commit
        self._files = commentable_files
        self._current_lines: tuple[CommentableDiffLine, ...] = ()
        self._workers: List[GitHubWorker] = []
        self._submit_token: Optional[object] = None
        self._submitted_successfully = False
        self._comments_token: Optional[object] = None

        self.setWindowTitle(self.tr("差分行へレビューコメント"))
        self.resize(820, 680)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(6)

        explanation = QLabel(
            self.tr(
                "取得済み patch から座標を確定できる行だけを表示します。"
                "投稿先を確認してから [レビューコメントを投稿] を押してください。"
            )
        )
        explanation.setWordWrap(True)
        explanation.setProperty("hveRole", "description")
        outer.addWidget(explanation)

        context_layout = QFormLayout()
        self.repo_label = QLabel(self._repo)
        self.pull_request_label = QLabel(f"#{self._pull_request_number}")
        self.commit_id_label = QLabel(self._commit_id)
        for label in (self.repo_label, self.pull_request_label, self.commit_id_label):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        context_layout.addRow(self.tr("Repository"), self.repo_label)
        context_layout.addRow(self.tr("Pull Request"), self.pull_request_label)
        context_layout.addRow(self.tr("Commit ID"), self.commit_id_label)
        outer.addLayout(context_layout)

        file_row = QHBoxLayout()
        file_row.addWidget(QLabel(self.tr("変更ファイル")))
        self.file_combo = QComboBox()
        for entry in self._files:
            self.file_combo.addItem(entry.path)
        self.file_combo.currentIndexChanged.connect(self._on_file_changed)
        file_row.addWidget(self.file_combo, stretch=1)
        outer.addLayout(file_row)

        self.line_table = QTableWidget(0, 3)
        self.line_table.setHorizontalHeaderLabels(
            [self.tr("Side"), self.tr("Line"), self.tr("内容")]
        )
        self.line_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.line_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.line_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.line_table.verticalHeader().setVisible(False)
        header = self.line_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.line_table.itemSelectionChanged.connect(self._on_line_selection_changed)
        outer.addWidget(self.line_table, stretch=3)

        target_box = QGroupBox(self.tr("投稿先（確定値）"))
        target_layout = QFormLayout(target_box)
        self.path_label = QLabel("-")
        self.line_label = QLabel("-")
        self.side_label = QLabel("-")
        for label in (self.path_label, self.line_label, self.side_label):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
        target_layout.addRow(self.tr("Path"), self.path_label)
        target_layout.addRow(self.tr("Line"), self.line_label)
        target_layout.addRow(self.tr("Side"), self.side_label)
        outer.addWidget(target_box)

        self.body_edit = GitHubCommentEditor()
        self.body_edit.set_placeholder_text(self.tr("レビューコメントを入力"))
        self.body_edit.textChanged.connect(self._update_submit_state)
        outer.addWidget(self.body_edit, stretch=2)

        comments_box = QGroupBox(self.tr("既存の review comment"))
        comments_layout = QVBoxLayout(comments_box)
        comments_layout.setContentsMargins(8, 4, 8, 4)
        self.review_comment_list = QListWidget()
        comments_layout.addWidget(self.review_comment_list)
        outer.addWidget(comments_box, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("hveRole", "description")
        outer.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton(self.tr("キャンセル"))
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)
        self.submit_button = QPushButton(self.tr("レビューコメントを投稿"))
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self.submit_review_comment)
        button_row.addWidget(self.submit_button)
        outer.addLayout(button_row)

        self._on_file_changed(self.file_combo.currentIndex())
        self._update_submit_state()
        self._load_review_comments()

    def current_target(self) -> Optional[CommentableDiffLine]:
        """利用者が明示選択した immutable 投稿座標。"""
        row = self.line_table.currentRow()
        if (
            row < 0
            or row >= len(self._current_lines)
            or not self.line_table.selectedItems()
        ):
            return None
        return self._current_lines[row]

    def submit_review_comment(self) -> None:
        """選択済み座標へ、利用者の明示操作で 1 件だけ投稿する。"""
        if self._submit_token is not None or self._submitted_successfully:
            return
        target = self.current_target()
        body = self.body_edit.text()
        if target is None:
            self.status_label.setText(self.tr("投稿する差分行を選択してください。"))
            self._update_submit_state()
            return
        if not body.strip():
            self.status_label.setText(self.tr("レビューコメント本文を入力してください。"))
            self._update_submit_state()
            return

        token = object()
        self._submit_token = token
        self._set_submit_busy(True)
        self.status_label.setText(self.tr("レビューコメントを投稿中..."))

        def _done(result: Any) -> None:
            if self._submit_token is not token:
                return
            self._submit_token = None
            if not self._is_created_comment(result):
                self._set_submit_busy(False)
                self.status_label.setText(
                    self.tr("レビューコメントの投稿結果を解釈できませんでした。")
                )
                return
            self._submitted_successfully = True
            self.status_label.setText(self.tr("レビューコメントを投稿しました。"))
            self.accept()

        def _failed(message: str) -> None:
            if self._submit_token is not token:
                return
            self._submit_token = None
            self._set_submit_busy(False)
            self.status_label.setText(
                self.tr("レビューコメントの投稿に失敗しました: {message}").format(
                    message=message
                )
            )

        self._run(
            partial(
                github_service.create_pull_request_review_comment,
                self._repo,
                self._pull_request_number,
                body,
                self._commit_id,
                target.path,
                target.line,
                target.side,
            ),
            _done,
            _failed,
        )

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """実行中 worker の終了を待ち、QThread の早期破棄を防ぐ。"""
        for worker in list(self._workers):
            worker.wait(timeout_ms)
        self._workers.clear()

    def reject(self) -> None:  # type: ignore[override]
        if self._submit_token is not None:
            self.status_label.setText(
                self.tr("レビューコメントの投稿完了までお待ちください。")
            )
            return
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._submit_token is not None:
            event.ignore()
            self.status_label.setText(
                self.tr("レビューコメントの投稿完了までお待ちください。")
            )
            return
        super().closeEvent(event)

    def _on_file_changed(self, index: int) -> None:
        self._current_lines = (
            self._files[index].lines if 0 <= index < len(self._files) else ()
        )
        self.line_table.clearContents()
        self.line_table.setRowCount(len(self._current_lines))
        for row, entry in enumerate(self._current_lines):
            values = (entry.side, str(entry.line), entry.text)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.line_table.setItem(row, column, item)
        self.line_table.clearSelection()
        self.line_table.setCurrentItem(None)  # type: ignore[call-overload]
        self._on_line_selection_changed()

    def _on_line_selection_changed(self) -> None:
        target = self.current_target()
        self.path_label.setText(target.path if target is not None else "-")
        self.line_label.setText(str(target.line) if target is not None else "-")
        self.side_label.setText(target.side if target is not None else "-")
        self._update_submit_state()

    def _update_submit_state(self) -> None:
        self.submit_button.setEnabled(
            self._submit_token is None
            and not self._submitted_successfully
            and self.current_target() is not None
            and bool(self.body_edit.text().strip())
        )

    def _set_submit_busy(self, busy: bool) -> None:
        self.file_combo.setEnabled(not busy)
        self.line_table.setEnabled(not busy)
        self.body_edit.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)
        self._update_submit_state()

    def _load_review_comments(self) -> None:
        if self._comments_token is not None:
            return
        token = object()
        self._comments_token = token

        def _done(result: Any) -> None:
            if self._comments_token is not token:
                return
            self._comments_token = None
            rows = self._normalize_comment_rows(result)
            if rows is None:
                self.status_label.setText(
                    self.tr("review comment 一覧の応答を解釈できませんでした。")
                )
                return
            self.review_comment_list.clear()
            for row in rows:
                self.review_comment_list.addItem(row)

        def _failed(message: str) -> None:
            if self._comments_token is not token:
                return
            self._comments_token = None
            self.status_label.setText(
                self.tr("review comment 一覧の取得に失敗しました: {message}").format(
                    message=message
                )
            )

        self._run(
            partial(
                github_service.list_pull_request_review_comments,
                self._repo,
                self._pull_request_number,
            ),
            _done,
            _failed,
        )

    def _run(
        self,
        task: Callable[[], Any],
        on_ok: Callable[[Any], None],
        on_ng: Optional[Callable[[str], None]] = None,
    ) -> None:
        worker = GitHubWorker(task)
        worker.succeeded.connect(on_ok)
        worker.failed.connect(on_ng or self.status_label.setText)
        worker.finished.connect(self._on_worker_finished)
        self._workers.append(worker)
        try:
            worker.start()
        except RuntimeError as exc:
            if worker in self._workers:
                self._workers.remove(worker)
            (on_ng or self.status_label.setText)(
                self.tr("GitHub ワーカーの起動に失敗しました: {kind}").format(
                    kind=type(exc).__name__
                )
            )

    def _on_worker_finished(self) -> None:
        worker = self.sender()
        if isinstance(worker, GitHubWorker) and worker in self._workers:
            self._workers.remove(worker)

    @staticmethod
    def _is_created_comment(result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        value = result.get("id")
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return False
        try:
            return int(value) > 0
        except ValueError:
            return False

    @staticmethod
    def _normalize_comment_rows(comments: Any) -> Optional[List[str]]:
        if not isinstance(comments, list):
            return None
        rows: List[str] = []
        for comment in comments:
            if not isinstance(comment, dict):
                return None
            user = comment.get("user")
            login = str(user.get("login") or "") if isinstance(user, dict) else ""
            path = str(comment.get("path") or "")
            side = str(comment.get("side") or "")
            line = comment.get("line")
            if line is None:
                line = comment.get("original_line")
            created = str(comment.get("created_at") or "")
            body = comment.get("body")
            first_line = str(body or "").splitlines()[:1]
            rows.append(
                f"{login} {path}:{line if line is not None else ''} "
                f"{side} {created}  {first_line[0] if first_line else ''}"
            )
        return rows
