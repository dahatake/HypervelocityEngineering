"""hve.gui.github_pr_panel — GitHub Pull Request の閲覧とコメント（FR-GUI-27）。

PR の新規作成は提供しない。PR 作成は `--create-pr` / `--create-issues` 経路が担い、
当該経路が PR 作成前に必ずローカル作業ブランチを作成する。
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
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import github_service
from .github_threads import GitHubWorker

__all__ = ["GitHubPullRequestPanel"]


class GitHubPullRequestPanel(QWidget):
    """Pull Request 一覧・詳細・変更ファイル・コメントを扱うパネル。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._repo: str = ""
        self._pulls: List[dict] = []
        self._current: Optional[dict] = None
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
        self.refresh_button.clicked.connect(self.refresh_pull_requests)
        row.addWidget(self.refresh_button)
        row.addStretch(1)
        return row

    def _build_list_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pr_list = QListWidget()
        self.pr_list.currentRowChanged.connect(self._on_pull_request_selected)
        layout.addWidget(self.pr_list)
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

        self.body_view = QPlainTextEdit()
        self.body_view.setReadOnly(True)
        layout.addWidget(self.body_view, stretch=2)

        files_box = QGroupBox(self.tr("変更ファイル"))
        files_layout = QVBoxLayout(files_box)
        files_layout.setContentsMargins(8, 4, 8, 4)
        self.file_list = QListWidget()
        files_layout.addWidget(self.file_list)
        layout.addWidget(files_box, stretch=2)

        layout.addWidget(self._build_comment_group(), stretch=3)
        return pane

    def _build_comment_group(self) -> QWidget:
        box = QGroupBox(self.tr("コメント"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.comment_list = QListWidget()
        layout.addWidget(self.comment_list, stretch=1)

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

    def refresh_pull_requests(self) -> None:
        """PR 一覧を再取得する（利用者の明示操作のみ）。"""
        if not self._require_repo():
            return
        state = self.state_combo.currentData() or "open"
        self._status(self.tr("Pull Request 一覧を取得中..."))
        self._run(
            partial(github_service.list_pull_requests, self._repo, state=state),
            self._on_pull_requests_loaded,
        )

    def post_comment(self) -> None:
        """会話コメントを投稿する。"""
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

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """実行中のワーカーの終了を待つ（ウィンドウを閉じるときに呼ぶ）。"""
        for worker in list(self._workers):
            worker.wait(timeout_ms)
        self._workers.clear()

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _run(
        self,
        task: Callable[[], Any],
        on_ok: Callable[[Any], None],
        on_ng: Optional[Callable[[str], None]] = None,
    ) -> None:
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

    def _on_pull_requests_loaded(self, pulls: Any) -> None:
        self._pulls = list(pulls or [])
        self.pr_list.clear()
        for pr in self._pulls:
            self.pr_list.addItem(f"#{pr.get('number')} {pr.get('title', '')}")
        self._status(
            self.tr("{n} 件の Pull Request を取得しました。").format(n=len(self._pulls))
        )

    def _on_pull_request_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._pulls):
            self._current = None
            self._set_detail_enabled(False)
            return
        number = int(self._pulls[row]["number"])
        self._run(
            partial(github_service.get_pull_request, self._repo, number),
            self._on_pull_request_loaded,
        )

    def _on_pull_request_loaded(self, pr: Any) -> None:
        if not isinstance(pr, dict):
            self._show_error(self.tr("Pull Request の詳細を取得できませんでした。"))
            return
        self._current = pr
        self.meta_label.setText(self._format_meta(pr))
        url = str(pr.get("html_url") or "")
        # API 由来の文字列を rich text へ直接埋め込まない
        self.url_label.setText(
            f'<a href="{escape(url, quote=True)}">{escape(url)}</a>' if url else ""
        )
        self.body_view.setPlainText(str(pr.get("body") or ""))
        self._set_detail_enabled(True)
        number = int(pr["number"])
        self._load_files(number)
        self._load_comments(number)

    def _load_files(self, number: int) -> None:
        self.file_list.clear()
        self._run(
            partial(github_service.list_pull_request_files, self._repo, number),
            self._on_files_loaded,
        )

    def _on_files_loaded(self, files: Any) -> None:
        self.file_list.clear()
        for entry in files or []:
            if not isinstance(entry, dict):
                continue
            self.file_list.addItem(
                f"{entry.get('filename', '')}  [{entry.get('status', '')}]"
            )

    def _load_comments(self, number: int) -> None:
        self._run(
            partial(github_service.list_comments, self._repo, number),
            self._on_comments_loaded,
        )

    def _on_comments_loaded(self, comments: Any) -> None:
        self.comment_list.clear()
        for comment in comments or []:
            if not isinstance(comment, dict):
                continue
            user = comment.get("user")
            login = str(user.get("login")) if isinstance(user, dict) else ""
            created = str(comment.get("created_at") or "")
            lines = str(comment.get("body") or "").splitlines()[:1]
            self.comment_list.addItem(f"{login} {created}  {lines[0] if lines else ''}")

    @staticmethod
    def _format_meta(pr: Dict[str, Any]) -> str:
        def _ref(key: str) -> str:
            value = pr.get(key)
            return str(value.get("ref")) if isinstance(value, dict) else ""

        author = pr.get("user")
        author_login = str(author.get("login")) if isinstance(author, dict) else ""
        state = str(pr.get("state") or "")
        if pr.get("merged"):
            state = f"{state} (merged)"
        elif pr.get("draft"):
            state = f"{state} (draft)"
        return " | ".join(
            [
                f"#{pr.get('number')}",
                f"state: {state}",
                f"author: {author_login}",
                f"{_ref('head')} → {_ref('base')}",
            ]
        )

    def _set_detail_enabled(self, enabled: bool) -> None:
        for widget in (self.new_comment_edit, self.post_comment_button):
            widget.setEnabled(enabled)
