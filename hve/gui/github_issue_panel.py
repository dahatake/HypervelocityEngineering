"""hve.gui.github_issue_panel — GitHub Issue の閲覧・編集・コメント（FR-GUI-26）。

GitHub API 呼び出しは `github_service` へ委譲し、`GitHubWorker` 経由で
GUI スレッド外で実行する。一覧・詳細の更新は利用者の明示操作のみで行い、
自動ポーリングは行わない。
"""

from __future__ import annotations

from functools import partial
from html import escape
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import github_service
from .github_threads import GitHubWorker

__all__ = ["GitHubIssuePanel"]


class GitHubIssuePanel(QWidget):
    """Issue 一覧・詳細・コメントを 1 画面で扱うパネル。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._repo: str = ""
        self._issues: List[dict] = []
        self._comments: List[dict] = []
        self._current: Optional[dict] = None
        self._login: str = ""
        self._workers: List[GitHubWorker] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        outer.addLayout(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_list_pane())
        splitter.addWidget(self._build_detail_pane())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("hveRole", "description")
        outer.addWidget(self.status_label)

        self._set_detail_enabled(False)

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(self.tr("状態")))
        self.state_combo = QComboBox()
        # tr() にはリテラルを渡す（変数渡しだと lupdate が抽出できない）
        self.state_combo.addItem(self.tr("オープン"), "open")
        self.state_combo.addItem(self.tr("クローズ"), "closed")
        self.state_combo.addItem(self.tr("すべて"), "all")
        row.addWidget(self.state_combo)
        self.refresh_button = QPushButton(self.tr("更新"))
        self.refresh_button.clicked.connect(self.refresh_issues)
        row.addWidget(self.refresh_button)
        row.addStretch(1)
        return row

    def _build_list_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        self.issue_list = QListWidget()
        self.issue_list.currentRowChanged.connect(self._on_issue_selected)
        layout.addWidget(self.issue_list)
        return pane

    def _build_detail_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.meta_label = QLabel("")
        self.meta_label.setWordWrap(True)
        self.meta_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.meta_label)

        self.url_label = QLabel("")
        self.url_label.setOpenExternalLinks(True)
        self.url_label.setWordWrap(True)
        layout.addWidget(self.url_label)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(self.tr("タイトル"))
        layout.addWidget(self.title_edit)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setPlaceholderText(self.tr("本文"))
        layout.addWidget(self.body_edit, stretch=2)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self.save_button = QPushButton(self.tr("タイトル / 本文を保存"))
        self.save_button.clicked.connect(self.save_issue)
        button_row.addWidget(self.save_button)
        self.state_button = QPushButton(self.tr("Issue をクローズ"))
        self.state_button.clicked.connect(self.toggle_state)
        button_row.addWidget(self.state_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        layout.addWidget(self._build_comment_group(), stretch=3)
        return pane

    def _build_comment_group(self) -> QWidget:
        box = QGroupBox(self.tr("コメント"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.comment_list = QListWidget()
        self.comment_list.currentRowChanged.connect(self._on_comment_selected)
        layout.addWidget(self.comment_list, stretch=1)

        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setPlaceholderText(self.tr("選択したコメント（自分のコメントのみ編集できます）"))
        layout.addWidget(self.comment_edit, stretch=1)

        self.save_comment_button = QPushButton(self.tr("コメントを更新"))
        self.save_comment_button.clicked.connect(self.save_comment)
        layout.addWidget(self.save_comment_button)

        self.new_comment_edit = QPlainTextEdit()
        self.new_comment_edit.setPlaceholderText(self.tr("新しいコメントを入力"))
        layout.addWidget(self.new_comment_edit, stretch=1)

        self.post_comment_button = QPushButton(self.tr("コメントを投稿"))
        self.post_comment_button.clicked.connect(self.post_comment)
        layout.addWidget(self.post_comment_button)
        return box

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_repo(self, repo: str) -> None:
        """対象リポジトリ（``owner/repo``）を設定する。"""
        self._repo = (repo or "").strip()

    def refresh_issues(self) -> None:
        """Issue 一覧を再取得する（利用者の明示操作のみ）。"""
        if not self._require_repo():
            return
        state = self.state_combo.currentData() or "open"
        self._status(self.tr("Issue 一覧を取得中..."))
        self._run(
            partial(github_service.list_issues, self._repo, state=state),
            self._on_issues_loaded,
        )

    def save_issue(self) -> None:
        """タイトルと本文を保存する。"""
        if self._current is None or not self._require_repo():
            return
        number = self._current["number"]
        self._status(self.tr("Issue #{n} を保存中...").format(n=number))
        self._run(
            partial(
                github_service.update_issue,
                self._repo,
                number,
                title=self.title_edit.text(),
                body=self.body_edit.toPlainText(),
            ),
            lambda _r: self._on_issue_changed(number, self.tr("Issue #{n} を保存しました。")),
        )

    def toggle_state(self) -> None:
        """open ⇔ closed を切り替える。"""
        if self._current is None or not self._require_repo():
            return
        number = self._current["number"]
        new_state = "open" if self._current.get("state") == "closed" else "closed"
        self._run(
            partial(github_service.update_issue, self._repo, number, state=new_state),
            lambda _r: self._on_issue_changed(
                number, self.tr("Issue #{n} の状態を変更しました。")
            ),
        )

    def post_comment(self) -> None:
        """新しいコメントを投稿する。"""
        if self._current is None or not self._require_repo():
            return
        body = self.new_comment_edit.toPlainText()
        if not body.strip():
            self._show_error(self.tr("コメント本文を入力してください。"))
            return
        number = self._current["number"]

        def _done(_result: Any) -> None:
            self.new_comment_edit.setPlainText("")
            self._status(self.tr("コメントを投稿しました。"))
            self._load_comments(number)

        self._run(partial(github_service.post_comment, self._repo, number, body), _done)

    def save_comment(self) -> None:
        """選択中の自分のコメントを更新する。"""
        comment = self._selected_comment()
        if comment is None or not self._is_own(comment) or not self._require_repo():
            return
        number = self._current["number"] if self._current else None
        body = self.comment_edit.toPlainText()

        def _done(_result: Any) -> None:
            self._status(self.tr("コメントを更新しました。"))
            if number is not None:
                self._load_comments(number)

        self._run(
            partial(github_service.update_comment, self._repo, comment["id"], body), _done
        )

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _run(
        self,
        task: Callable[[], Any],
        on_ok: Callable[[Any], None],
        on_ng: Optional[Callable[[str], None]] = None,
    ) -> None:
        """ワーカースレッドで `github_service` を呼び出す。

        ワーカーはこのパネルの Qt 子供にしない。実行中の QThread が親の破棄で
        剱除されるのを避けるためで、寿命は `_workers` と `shutdown()` で管理する。
        """
        worker = GitHubWorker(task)
        worker.succeeded.connect(on_ok)
        worker.failed.connect(on_ng or self._show_error)
        worker.finished.connect(self._on_worker_finished)
        self._workers.append(worker)  # GC 防止
        worker.start()

    def _on_worker_finished(self) -> None:
        worker = self.sender()
        if isinstance(worker, GitHubWorker) and worker in self._workers:
            self._workers.remove(worker)

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """実行中のワーカーの終了を待つ（ウィンドウを閉じるときに呼ぶ）。"""
        for worker in list(self._workers):
            worker.wait(timeout_ms)
        self._workers.clear()

    def _require_repo(self) -> bool:
        if self._repo:
            return True
        self._show_error(
            self.tr("リポジトリが未設定です。上部の入力欄で owner/repo を指定してください。")
        )
        return False

    def _status(self, message: str) -> None:
        self.status_label.setText(message)

    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_issues_loaded(self, issues: Any) -> None:
        self._issues = list(issues or [])
        self.issue_list.clear()
        for issue in self._issues:
            self.issue_list.addItem(f"#{issue.get('number')} {issue.get('title', '')}")
        self._status(self.tr("{n} 件の Issue を取得しました。").format(n=len(self._issues)))

    def _on_issue_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._issues):
            self._current = None
            self._set_detail_enabled(False)
            return
        self._load_issue(int(self._issues[row]["number"]))

    def _load_issue(self, number: int) -> None:
        self._run(
            partial(github_service.get_issue, self._repo, number), self._on_issue_loaded
        )

    def _on_issue_loaded(self, issue: Any) -> None:
        if not isinstance(issue, dict):
            self._show_error(self.tr("Issue の詳細を取得できませんでした。"))
            return
        self._current = issue
        self.title_edit.setText(str(issue.get("title") or ""))
        self.body_edit.setPlainText(str(issue.get("body") or ""))
        self.meta_label.setText(self._format_meta(issue))
        url = str(issue.get("html_url") or "")
        # API 由来の文字列を rich text へ直接埋め込まない
        self.url_label.setText(
            f'<a href="{escape(url, quote=True)}">{escape(url)}</a>' if url else ""
        )
        self.state_button.setText(
            self.tr("Issue を再オープン")
            if issue.get("state") == "closed"
            else self.tr("Issue をクローズ")
        )
        self._set_detail_enabled(True)
        self._load_comments(int(issue["number"]))

    def _on_issue_changed(self, number: int, template: str) -> None:
        self._status(template.format(n=number))
        self._load_issue(number)

    def _load_comments(self, number: int) -> None:
        if not self._login:
            self._run(github_service.current_user_login, self._on_login_loaded, lambda _m: None)
        self._run(
            partial(github_service.list_comments, self._repo, number),
            self._on_comments_loaded,
        )

    def _on_login_loaded(self, login: Any) -> None:
        self._login = str(login or "")

    def _on_comments_loaded(self, comments: Any) -> None:
        self._comments = list(comments or [])
        self.comment_list.clear()
        for comment in self._comments:
            login = self._comment_login(comment)
            created = str(comment.get("created_at") or "")
            first_line = str(comment.get("body") or "").splitlines()[:1]
            summary = first_line[0] if first_line else ""
            self.comment_list.addItem(f"{login} {created}  {summary}")
        self.comment_edit.setPlainText("")
        self._apply_comment_permissions(None)

    def _on_comment_selected(self, row: int) -> None:
        comment = self._comments[row] if 0 <= row < len(self._comments) else None
        self.comment_edit.setPlainText(str(comment.get("body") or "") if comment else "")
        self._apply_comment_permissions(comment)

    def _apply_comment_permissions(self, comment: Optional[dict]) -> None:
        editable = comment is not None and self._is_own(comment)
        self.comment_edit.setEnabled(editable)
        self.save_comment_button.setEnabled(editable)

    def _selected_comment(self) -> Optional[dict]:
        row = self.comment_list.currentRow()
        if 0 <= row < len(self._comments):
            return self._comments[row]
        return None

    def _is_own(self, comment: Dict[str, Any]) -> bool:
        return bool(self._login) and self._comment_login(comment) == self._login

    @staticmethod
    def _comment_login(comment: Dict[str, Any]) -> str:
        user = comment.get("user")
        return str(user.get("login")) if isinstance(user, dict) else ""

    @staticmethod
    def _format_meta(issue: Dict[str, Any]) -> str:
        def _names(key: str, field: str) -> str:
            values = issue.get(key)
            if not isinstance(values, list):
                return ""
            return ", ".join(
                str(v.get(field)) for v in values if isinstance(v, dict) and v.get(field)
            )

        author = issue.get("user")
        author_login = str(author.get("login")) if isinstance(author, dict) else ""
        parts = [
            f"#{issue.get('number')}",
            f"state: {issue.get('state')}",
            f"author: {author_login}",
        ]
        labels = _names("labels", "name")
        if labels:
            parts.append(f"labels: {labels}")
        assignees = _names("assignees", "login")
        if assignees:
            parts.append(f"assignees: {assignees}")
        return " | ".join(parts)

    def _set_detail_enabled(self, enabled: bool) -> None:
        for widget in (
            self.title_edit,
            self.body_edit,
            self.save_button,
            self.state_button,
            self.new_comment_edit,
            self.post_comment_button,
        ):
            widget.setEnabled(enabled)
        if not enabled:
            self._apply_comment_permissions(None)
