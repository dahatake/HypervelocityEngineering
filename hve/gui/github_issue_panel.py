"""hve.gui.github_issue_panel — GitHub Issue の閲覧・編集・コメント（FR-GUI-26）。

GitHub API 呼び出しは `github_service` へ委譲し、`GitHubWorker` 経由で
GUI スレッド外で実行する。一覧・詳細の更新は利用者の明示操作のみで行い、
自動ポーリングは行わない。
"""

from __future__ import annotations

from functools import partial
from html import escape
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import github_service
from .github_comment_editor import GitHubCommentEditor
from .github_threads import GitHubWorker
from hve.github_copilot_assignment_contract import (
    CopilotAssignmentContractError,
    validate_copilot_assignment_response,
)
from hve.github_title_generator import generate_github_title

__all__ = ["GitHubIssuePanel"]

_ISSUES_PER_PAGE = 50


class GitHubIssuePanel(QWidget):
    """Issue 一覧・詳細・コメントを 1 画面で扱うパネル。"""

    issue_selected = Signal(object)
    issue_created = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._repo: str = ""
        self._issues: List[dict] = []
        self._visible: List[dict] = []
        self._comments: List[dict] = []
        self._current: Optional[dict] = None
        self._login: str = ""
        self._workers: List[GitHubWorker] = []
        self._loaded_repo: str = ""
        self._created_issue_number: Optional[int] = None
        self._created_issue_warnings: List[str] = []
        self._linked_number: Optional[int] = None
        self._suppress_selection_signal = False
        self._creation_metadata: Optional[Dict[str, List[Any]]] = None
        self._metadata_load_token: Optional[object] = None
        self._metadata_save_token: Optional[object] = None
        self._copilot_assignment_token: Optional[object] = None
        self._issue_target_repo: str = ""
        self._issue_target_number: Optional[int] = None
        self._issue_target_epoch = 0
        self._operation_epoch = 0
        self._create_controls_requested_enabled = True
        self._issue_load_generation = 0
        self._next_issue_cursor: Optional[str] = None
        self._issue_cursor_history: set[str] = set()
        self._issues_have_more = False
        self._list_request_in_flight = False
        self._list_request_serial = 0
        self._active_list_request_token: Optional[int] = None
        self._pending_issue_refresh: Optional[tuple[str, str]] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        outer.addLayout(self._build_toolbar())
        outer.addWidget(self._build_create_group())

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
        self.state_combo.currentIndexChanged.connect(
            self._on_issue_list_context_changed
        )
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
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.tr("番号・タイトルで絞り込み"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_list_filter)
        layout.addWidget(self.filter_edit)
        self.issue_list = QListWidget()
        self.issue_list.currentRowChanged.connect(self._on_issue_selected)
        layout.addWidget(self.issue_list)
        self.load_more_button = QPushButton(self.tr("さらに読み込む"))
        self.load_more_button.setEnabled(False)
        self.load_more_button.clicked.connect(self.load_more_issues)
        layout.addWidget(self.load_more_button)
        return pane

    def _build_create_group(self) -> QWidget:
        box = QGroupBox(self.tr("Issue を作成"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.create_title_edit = QLineEdit()
        self.create_title_edit.setPlaceholderText(self.tr("新しい Issue のタイトル"))
        layout.addWidget(self.create_title_edit)

        self.create_body_edit = GitHubCommentEditor()
        self.create_body_edit.set_placeholder_text(self.tr("新しい Issue の本文（Markdown）"))
        layout.addWidget(self.create_body_edit)

        metadata_row = QHBoxLayout()
        labels_column = QVBoxLayout()
        labels_column.addWidget(QLabel(self.tr("ラベル")))
        self.create_labels_list = QListWidget()
        self.create_labels_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.create_labels_list.setMaximumHeight(90)
        labels_column.addWidget(self.create_labels_list)
        metadata_row.addLayout(labels_column)

        assignees_column = QVBoxLayout()
        assignees_column.addWidget(QLabel(self.tr("担当者")))
        self.create_assignees_list = QListWidget()
        self.create_assignees_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.create_assignees_list.setMaximumHeight(90)
        assignees_column.addWidget(self.create_assignees_list)
        metadata_row.addLayout(assignees_column)
        layout.addLayout(metadata_row)

        milestone_row = QHBoxLayout()
        milestone_row.addWidget(QLabel(self.tr("マイルストーン")))
        self.create_milestone_combo = QComboBox()
        self.create_milestone_combo.addItem(self.tr("指定なし"), None)
        milestone_row.addWidget(self.create_milestone_combo, stretch=1)
        self.load_metadata_button = QPushButton(self.tr("作成候補を取得"))
        self.load_metadata_button.clicked.connect(self.load_creation_metadata)
        milestone_row.addWidget(self.load_metadata_button)
        layout.addLayout(milestone_row)

        self.create_and_link_checkbox = QCheckBox(
            self.tr("作成後、このタスクに関連付ける")
        )
        self.create_and_link_checkbox.setChecked(True)
        layout.addWidget(self.create_and_link_checkbox)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self.generate_title_button = QPushButton(self.tr("Copilot でタイトルを生成"))
        self.generate_title_button.clicked.connect(self.generate_issue_title)
        button_row.addWidget(self.generate_title_button)
        self.create_issue_button = QPushButton(self.tr("Issue を作成"))
        self.create_issue_button.clicked.connect(self.create_issue)
        button_row.addWidget(self.create_issue_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        return box

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

        self.body_edit = GitHubCommentEditor()
        self.body_edit.set_placeholder_text(self.tr("本文"))
        layout.addWidget(self.body_edit, stretch=2)

        layout.addWidget(self._build_metadata_edit_group())
        layout.addWidget(self._build_copilot_assignment_group())

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

    def _build_metadata_edit_group(self) -> QWidget:
        box = QGroupBox(self.tr("既存 Issue の metadata"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        metadata_row = QHBoxLayout()
        labels_column = QVBoxLayout()
        labels_column.addWidget(QLabel(self.tr("ラベル")))
        self.edit_labels_list = QListWidget()
        self.edit_labels_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.edit_labels_list.setMaximumHeight(90)
        labels_column.addWidget(self.edit_labels_list)
        metadata_row.addLayout(labels_column)

        assignees_column = QVBoxLayout()
        assignees_column.addWidget(QLabel(self.tr("担当者")))
        self.edit_assignees_list = QListWidget()
        self.edit_assignees_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.edit_assignees_list.setMaximumHeight(90)
        assignees_column.addWidget(self.edit_assignees_list)
        metadata_row.addLayout(assignees_column)
        layout.addLayout(metadata_row)

        milestone_row = QHBoxLayout()
        milestone_row.addWidget(QLabel(self.tr("マイルストーン")))
        self.edit_milestone_combo = QComboBox()
        self.edit_milestone_combo.addItem(self.tr("未設定"), 0)
        milestone_row.addWidget(self.edit_milestone_combo, stretch=1)
        self.save_metadata_button = QPushButton(self.tr("metadata を保存"))
        self.save_metadata_button.clicked.connect(self.save_issue_metadata)
        milestone_row.addWidget(self.save_metadata_button)
        layout.addLayout(milestone_row)

        self.metadata_guidance_label = QLabel("")
        self.metadata_guidance_label.setWordWrap(True)
        self.metadata_guidance_label.setProperty("hveRole", "description")
        layout.addWidget(self.metadata_guidance_label)
        return box

    def _build_copilot_assignment_group(self) -> QWidget:
        box = QGroupBox(self.tr("Copilot cloud agent"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        base_row = QHBoxLayout()
        base_row.addWidget(QLabel(self.tr("base branch")))
        self.copilot_base_branch_edit = QLineEdit()
        self.copilot_base_branch_edit.setPlaceholderText(
            self.tr("空欄の場合は GitHub の既定ブランチ")
        )
        base_row.addWidget(self.copilot_base_branch_edit, stretch=1)
        self.assign_copilot_button = QPushButton(self.tr("Copilotへ割り当て"))
        self.assign_copilot_button.clicked.connect(self.assign_copilot_agent)
        base_row.addWidget(self.assign_copilot_button)
        layout.addLayout(base_row)

        self.copilot_assignment_guidance_label = QLabel(
            self.tr(
                "この割当 API は public preview であり、変更される可能性があります。"
                "fine-grained PAT は Metadata: read と Actions: read and write、"
                "Contents: read and write、Issues: read and write、"
                "Pull requests: read and write が必要です。"
                "classic PAT は repo scope が必要です。"
            )
        )
        self.copilot_assignment_guidance_label.setWordWrap(True)
        self.copilot_assignment_guidance_label.setProperty(
            "hveRole", "description"
        )
        layout.addWidget(self.copilot_assignment_guidance_label)
        return box

    def _build_comment_group(self) -> QWidget:
        box = QGroupBox(self.tr("コメント"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.comment_list = QListWidget()
        self.comment_list.currentRowChanged.connect(self._on_comment_selected)
        layout.addWidget(self.comment_list, stretch=1)

        self.comment_edit = GitHubCommentEditor()
        self.comment_edit.set_placeholder_text(self.tr("選択したコメント（自分のコメントのみ編集できます）"))
        layout.addWidget(self.comment_edit, stretch=1)

        self.save_comment_button = QPushButton(self.tr("コメントを更新"))
        self.save_comment_button.clicked.connect(self.save_comment)
        layout.addWidget(self.save_comment_button)

        self.new_comment_edit = GitHubCommentEditor()
        self.new_comment_edit.set_placeholder_text(self.tr("新しいコメントを入力"))
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
        resolved = (repo or "").strip()
        changed = resolved != self._repo
        if changed:
            self._advance_operation_epoch()
            self._copilot_assignment_token = None
            self._set_issue_target(resolved, None)
            self._created_issue_number = None
            self._created_issue_warnings = []
            self._linked_number = None
            self._pending_issue_refresh = None
            self.create_labels_list.clear()
            self.create_assignees_list.clear()
            self.create_milestone_combo.clear()
            self.create_milestone_combo.addItem(self.tr("指定なし"), None)
            self._creation_metadata = None
            self._metadata_load_token = None
            self._metadata_save_token = None
            self._issue_load_generation += 1
            self._issues = []
            self._visible = []
            self._comments = []
            self._current = None
            previous_signal_state = self.issue_list.blockSignals(True)
            try:
                self.issue_list.clear()
            finally:
                self.issue_list.blockSignals(previous_signal_state)
            self.comment_list.clear()
            self.title_edit.clear()
            self.body_edit.clear()
            self.meta_label.clear()
            self.url_label.clear()
            self.copilot_base_branch_edit.clear()
            self.comment_edit.clear()
            self.new_comment_edit.clear()
            self._set_detail_enabled(False)
        self._repo = resolved
        if changed:
            self._invalidate_issue_list_context()
            self._sync_metadata_editor()
            self._status("")
            self._sync_assignment_guarded_controls()

    def load_creation_metadata(self) -> None:
        """Issue 作成候補を利用者の明示操作で取得する（FR-GUI-41）。"""
        if (
            self._copilot_assignment_token is not None
            or self._metadata_load_token is not None
            or self._metadata_save_token is not None
        ):
            return
        if not self._require_repo():
            return
        repo_at_request = self._repo
        operation_epoch = self._advance_operation_epoch()
        token = object()
        self._metadata_load_token = token
        self.load_metadata_button.setEnabled(False)
        self._set_metadata_editor_enabled(False)
        self._sync_copilot_assignment_controls()
        self._status(self.tr("Issue の作成候補を取得中..."), operation_epoch)

        def _done(result: Any) -> None:
            if self._metadata_load_token is not token:
                if (
                    self._repo != repo_at_request
                    and self._metadata_load_token is None
                    and self._copilot_assignment_token is None
                    and self._operation_epoch == operation_epoch + 1
                ):
                    self._status(
                        self.tr(
                            "リポジトリが変更されたため、古い作成候補を破棄しました。"
                        )
                    )
                return
            self._metadata_load_token = None
            self._sync_copilot_assignment_controls()
            if not self._operation_is_current(operation_epoch):
                self._sync_assignment_guarded_controls()
                return
            if self._repo != repo_at_request:
                self._sync_metadata_editor()
                self._status(
                    self.tr("リポジトリが変更されたため、古い作成候補を破棄しました。"),
                    operation_epoch,
                )
                return
            self._on_creation_metadata_loaded(result)

        def _failed(message: str) -> None:
            if self._metadata_load_token is not token:
                return
            self._metadata_load_token = None
            if not self._operation_is_current(operation_epoch):
                self._sync_assignment_guarded_controls()
                return
            self._sync_metadata_editor()
            self._sync_copilot_assignment_controls()
            self._show_error(message, operation_epoch)

        self._run(
            partial(github_service.list_issue_creation_metadata, self._repo),
            _done,
            _failed,
        )

    def select_issue(self, number: int) -> bool:
        """取得済み一覧から番号一致の Issue を選択する。"""
        if self._copilot_assignment_token is not None:
            return False
        for row, issue in enumerate(self._visible):
            if issue.get("number") == number:
                self._suppress_selection_signal = True
                try:
                    self.issue_list.setCurrentRow(row)
                finally:
                    self._suppress_selection_signal = False
                return True
        return False

    def set_linked_issue(self, number: Optional[int]) -> None:
        """関連付けた Issue を一覧取得後に選択する（FR-GUI-40）。"""
        self._linked_number = number or None
        self._apply_linked_selection()

    def _apply_linked_selection(self) -> None:
        if self._linked_number is not None and self.select_issue(self._linked_number):
            self._linked_number = None

    def load_once(self) -> None:
        """リポジトリ確定時の初期取得（FR-GUI-31）。

        同じリポジトリに対して 2 回以上取得しない。以降の更新は [更新] 押下に限る。
        """
        if not self._repo or self._loaded_repo == self._repo:
            return
        self._loaded_repo = self._repo
        self.refresh_issues()

    def refresh_issues(self) -> None:
        """Issue 一覧を再取得する（利用者の明示操作のみ）。"""
        if self._copilot_assignment_token is not None or self._list_request_in_flight:
            return
        if not self._require_repo():
            return
        self._request_issues(cursor=None, append=False)

    def _refresh_issues_after_mutation(self) -> None:
        """作成後の page 1 refresh を実行中 request の後へ queue する。"""
        if not self._repo:
            return
        context = (self._repo, self.state_combo.currentData() or "open")
        if self._list_request_in_flight:
            self._pending_issue_refresh = context
            return
        self.refresh_issues()

    def load_more_issues(self) -> None:
        """利用者の明示操作で次の Issue ページを取得する（FR-GUI-48）。"""
        if (
            self._copilot_assignment_token is not None
            or self._list_request_in_flight
            or not self._issues_have_more
        ):
            return
        if not self._require_repo():
            return
        cursor = self._next_issue_cursor
        if not cursor:
            return
        self._request_issues(
            cursor=cursor,
            append=True,
        )

    def create_issue(self) -> None:
        """title / Markdown body から通常 Issue を作成する（FR-GUI-35）。"""
        if (
            self._copilot_assignment_token is not None
            or self._metadata_save_token is not None
        ):
            return
        if not self._require_repo():
            return
        title = self.create_title_edit.text()
        body = self.create_body_edit.text()
        if not title.strip():
            if not body.strip():
                self._show_error(self.tr("Issue のタイトルまたは本文を入力してください。"))
                return
            self._request_issue_title(body, create_after=True)
            return

        self._create_issue_with_values(title, body)

    def generate_issue_title(self) -> None:
        """本文から Issue title を生成し、入力欄へ反映する（FR-GUI-39）。"""
        if (
            self._copilot_assignment_token is not None
            or self._metadata_save_token is not None
        ):
            return
        body = self.create_body_edit.text()
        if not body.strip():
            self._show_error(self.tr("Issue の本文を入力してください。"))
            return
        self._request_issue_title(body, create_after=False)

    def _request_issue_title(self, body: str, *, create_after: bool) -> None:
        if (
            self._copilot_assignment_token is not None
            or self._metadata_save_token is not None
        ):
            return
        repo_at_request = self._repo
        operation_epoch = self._advance_operation_epoch()
        self._set_create_enabled(False)
        self._status(
            self.tr("Copilot CLI で Issue のタイトルを生成中..."),
            operation_epoch,
        )
        try:
            from . import settings_store

            cli_path = str(settings_store.get_option("cli_path") or "").strip() or None
        except Exception:
            cli_path = None

        def _done(result: Any) -> None:
            title = str(result or "").strip()
            if not title:
                self._set_create_enabled(True)
                self._show_error(
                    self.tr("Copilot CLI からタイトルを取得できませんでした。"),
                    operation_epoch,
                )
                return
            if self._repo != repo_at_request:
                self.create_title_edit.setText(title)
                self._set_create_enabled(True)
                if create_after:
                    self._status(
                        self.tr(
                            "リポジトリが変更されたため、タイトルだけを反映し Issue は作成しませんでした。"
                        )
                    )
                else:
                    self._status(self.tr("Copilot CLI でタイトルを生成しました。"))
                return
            if not self._operation_is_current(operation_epoch):
                self._set_create_enabled(True)
                return
            self.create_title_edit.setText(title)
            self._set_create_enabled(True)
            self._status(
                self.tr("Copilot CLI でタイトルを生成しました。"),
                operation_epoch,
            )
            if create_after:
                self._create_issue_with_values(title, body)

        def _failed(message: str) -> None:
            self._set_create_enabled(True)
            self._show_error(message, operation_epoch)

        self._run(
            partial(generate_github_title, "issue", body, cli_path=cli_path),
            _done,
            _failed,
        )

    def _create_issue_with_values(self, title: str, body: str) -> None:
        """検証済み title / body で Issue 作成 API を呼ぶ。"""

        if self._copilot_assignment_token is not None:
            return

        repo_at_create = self._repo
        labels = [item.text() for item in self.create_labels_list.selectedItems()]
        assignees = [
            item.text() for item in self.create_assignees_list.selectedItems()
        ]
        milestone = self.create_milestone_combo.currentData()
        link_after_create = self.create_and_link_checkbox.isChecked()
        operation_epoch = self._advance_operation_epoch()
        self._set_create_enabled(False)
        self._status(self.tr("Issue を作成中..."), operation_epoch)

        def _done(result: Any) -> None:
            number = int(result["number"])
            warnings = self._format_metadata_warnings(result.get("warnings", []))
            if self._repo != repo_at_create:
                self.create_title_edit.clear()
                self.create_body_edit.clear()
                self.create_labels_list.clearSelection()
                self.create_assignees_list.clearSelection()
                self.create_milestone_combo.setCurrentIndex(0)
                self._set_create_enabled(True)
                self._created_issue_number = None
                self._created_issue_warnings = []
                self._status(
                    self.tr("Issue #{n} を {repo} に作成しました。").format(
                        n=number, repo=repo_at_create
                    )
                )
                return
            if not self._operation_is_current(operation_epoch):
                self._set_create_enabled(True)
                return
            self.create_title_edit.clear()
            self.create_body_edit.clear()
            self.create_labels_list.clearSelection()
            self.create_assignees_list.clearSelection()
            self.create_milestone_combo.setCurrentIndex(0)
            self._set_create_enabled(True)
            if link_after_create:
                self.issue_created.emit(
                    {
                        "number": number,
                        "repo": repo_at_create,
                        "source": "created_in_hub",
                    }
                )
            self._created_issue_number = number
            self._created_issue_warnings = warnings
            if warnings:
                self._status(
                    self.tr("Issue #{n} は作成されましたが、警告があります: {warnings}").format(
                        n=number,
                        warnings="; ".join(warnings),
                    ),
                    operation_epoch,
                )
            else:
                self._status(
                    self.tr("Issue #{n} を作成しました。").format(n=number),
                    operation_epoch,
                )
            self._refresh_issues_after_mutation()

        def _failed(message: str) -> None:
            self._set_create_enabled(True)
            self._show_error(message, operation_epoch)

        self._run(
            partial(
                github_service.create_issue_details,
                repo_at_create,
                title,
                body,
                labels=labels,
                assignees=assignees,
                milestone=milestone,
            ),
            _done,
            _failed,
        )

    def save_issue(self) -> None:
        """タイトルと本文を保存する。"""
        if (
            self._copilot_assignment_token is not None
            or self._metadata_save_token is not None
            or self._current is None
            or not self._require_repo()
        ):
            return
        number = self._current["number"]
        operation_epoch = self._advance_operation_epoch()
        self._status(
            self.tr("Issue #{n} を保存中...").format(n=number),
            operation_epoch,
        )
        self._run(
            partial(
                github_service.update_issue,
                self._repo,
                number,
                title=self.title_edit.text(),
                body=self.body_edit.text(),
            ),
            lambda _r: self._on_issue_changed(
                number,
                self.tr("Issue #{n} を保存しました。"),
                operation_epoch,
            ),
            lambda message: self._show_error(message, operation_epoch),
        )

    def assign_copilot_agent(self) -> None:
        """選択中 Issue を確認後に Copilot cloud agent へ割り当てる。"""
        if (
            self._copilot_assignment_token is not None
            or self._metadata_load_token is not None
            or self._metadata_save_token is not None
        ):
            return

        current_issue = self._current
        number = self._current_issue_number()
        if current_issue is None or number is None:
            self._show_error(
                self.tr("Copilot へ割り当てる Issue を選択してください。")
            )
            return
        if not self._repo:
            self._require_repo()
            return
        try:
            repo = github_service.resolve_repo(self._repo)
        except github_service.GitHubServiceError as exc:
            self._show_error(str(exc))
            return

        base_branch = self.copilot_base_branch_edit.text().strip() or None
        target_epoch = self._issue_target_epoch
        if not self._confirm_copilot_assignment(repo, number, base_branch):
            return
        if not self._matches_copilot_assignment_target(repo, number, target_epoch):
            self._show_error(
                self.tr(
                    "確認中に対象が変更されたため、Copilot 割当を送信しませんでした。"
                )
            )
            return

        token = object()
        operation_epoch = self._advance_operation_epoch()
        self._copilot_assignment_token = token
        self._sync_assignment_guarded_controls()
        self._status(
            self.tr("Issue #{n} を Copilot cloud agent へ割り当て中...").format(
                n=number
            )
        )

        def _done(result: Any) -> None:
            if self._copilot_assignment_token is not token:
                return
            target_matches = self._matches_copilot_assignment_target(
                repo, number, target_epoch
            )
            self._copilot_assignment_token = None
            self._sync_assignment_guarded_controls()
            if not target_matches:
                self._status(
                    self.tr(
                        "選択中の Issue またはリポジトリが変更されたため、"
                        "古い Copilot 割当応答を破棄しました。"
                    ),
                    operation_epoch,
                )
                return
            try:
                validate_copilot_assignment_response(result, number)
            except CopilotAssignmentContractError as exc:
                self._show_error(
                    self.tr(
                        "Copilot 割当結果を解釈できませんでした: {detail}"
                    ).format(detail=str(exc)),
                    operation_epoch,
                )
                return
            self._status(
                self.tr(
                    "Issue #{n} を Copilot cloud agent へ割り当てました。"
                ).format(n=number),
                operation_epoch,
            )

        def _failed(message: str) -> None:
            if self._copilot_assignment_token is not token:
                return
            target_matches = self._matches_copilot_assignment_target(
                repo, number, target_epoch
            )
            self._copilot_assignment_token = None
            self._sync_assignment_guarded_controls()
            if not target_matches:
                self._status(
                    self.tr(
                        "選択中の Issue またはリポジトリが変更されたため、"
                        "古い Copilot 割当エラーを破棄しました。"
                    ),
                    operation_epoch,
                )
                return
            self._show_error(message, operation_epoch)

        self._run(
            partial(
                github_service.assign_copilot_agent,
                repo,
                number,
                base_branch,
            ),
            _done,
            _failed,
        )

    def _confirm_copilot_assignment(
        self,
        repo: str,
        number: int,
        base_branch: Optional[str],
    ) -> bool:
        branch_display = base_branch or self.tr("GitHub の既定ブランチ")
        answer = QMessageBox.question(
            self,
            self.tr("Copilot cloud agent への割当"),
            self.tr(
                "次の Issue を Copilot cloud agent へ割り当てます。\n"
                "Issue: #{number}\n"
                "repository: {repo}\n"
                "base branch: {branch}\n\n"
                "よろしいですか？"
            ).format(number=number, repo=repo, branch=branch_display),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _current_issue_number(self) -> Optional[int]:
        current_issue = self._current
        if not isinstance(current_issue, dict):
            return None
        number = current_issue.get("number")
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or number <= 0
        ):
            return None
        return number

    def _set_issue_target(self, repo: str, number: Optional[int]) -> None:
        resolved_repo = (repo or "").strip()
        resolved_number = (
            number
            if isinstance(number, int) and not isinstance(number, bool) and number > 0
            else None
        )
        if (
            resolved_repo != self._issue_target_repo
            or resolved_number != self._issue_target_number
        ):
            self._issue_target_epoch += 1
            self._issue_target_repo = resolved_repo
            self._issue_target_number = resolved_number

    def _matches_copilot_assignment_target(
        self,
        repo: str,
        number: int,
        target_epoch: int,
    ) -> bool:
        return (
            self._repo == repo
            and self._issue_target_repo == repo
            and self._issue_target_number == number
            and self._issue_target_epoch == target_epoch
        )

    def _sync_copilot_assignment_controls(self) -> None:
        enabled = (
            self._copilot_assignment_token is None
            and self._metadata_load_token is None
            and self._metadata_save_token is None
            and bool(self._repo)
            and self._current_issue_number() is not None
        )
        self.copilot_base_branch_edit.setEnabled(enabled)
        self.assign_copilot_button.setEnabled(enabled)

    def save_issue_metadata(self) -> None:
        """取得済み候補から選択した既存 Issue metadata を明示保存する。"""
        if (
            self._copilot_assignment_token is not None
            or self._metadata_load_token is not None
            or self._metadata_save_token is not None
        ):
            return
        if self._current is None or not self._require_repo():
            return
        if self._creation_metadata is None:
            self._show_error(
                self.tr("先に [作成候補を取得] を実行してから metadata を保存してください。")
            )
            self._sync_metadata_editor()
            return

        repo_at_request = self._repo
        number = int(self._current["number"])
        labels = [item.text() for item in self.edit_labels_list.selectedItems()]
        assignees = [
            item.text() for item in self.edit_assignees_list.selectedItems()
        ]
        milestone = int(self.edit_milestone_combo.currentData() or 0)
        issue_generation_at_request = self._issue_load_generation
        operation_epoch = self._advance_operation_epoch()
        token = object()
        self._metadata_save_token = token
        self.load_metadata_button.setEnabled(False)
        self._set_metadata_editor_enabled(False)
        self._sync_assignment_guarded_controls()
        self._status(
            self.tr("Issue #{n} の metadata を保存中...").format(n=number),
            operation_epoch,
        )

        def _request_target_snapshot() -> Optional[Dict[str, Any]]:
            current_issue: Optional[dict] = self._current
            if (
                self._repo != repo_at_request
                or current_issue is None
                or self._issue_load_generation != issue_generation_at_request
            ):
                return None
            current_number_value: Any = current_issue.get("number")
            if current_number_value is None:
                return None
            try:
                if int(current_number_value) != number:
                    return None
            except (TypeError, ValueError):
                return None
            return current_issue

        def _done(result: Any) -> None:
            if self._metadata_save_token is not token:
                return
            self._metadata_save_token = None
            self._sync_assignment_guarded_controls()
            if not self._operation_is_current(operation_epoch):
                self._sync_assignment_guarded_controls()
                return
            current_issue = _request_target_snapshot()
            if current_issue is None:
                self._sync_metadata_editor()
                self._status(
                    self.tr(
                        "選択中の Issue が変更されたため、古い metadata 応答を破棄しました。"
                    )
                )
                return
            if not isinstance(result, dict):
                self._set_metadata_editor_enabled(True)
                self._show_error(
                    self.tr("Issue metadata の更新結果を解釈できませんでした。"),
                    operation_epoch,
                )
                return
            try:
                response_number = int(result.get("number", number))
            except (TypeError, ValueError):
                response_number = -1
            if response_number != number:
                self._set_metadata_editor_enabled(True)
                self._show_error(
                    self.tr("Issue metadata の更新対象と応答が一致しませんでした。"),
                    operation_epoch,
                )
                return

            updated: Dict[str, Any] = dict(current_issue)
            updated["labels"] = [
                dict(item)
                for item in result.get("labels", [])
                if isinstance(item, dict)
            ]
            updated["assignees"] = [
                dict(item)
                for item in result.get("assignees", [])
                if isinstance(item, dict)
            ]
            response_milestone = result.get("milestone")
            updated["milestone"] = (
                dict(response_milestone)
                if isinstance(response_milestone, dict)
                else None
            )

            actual_labels = set(self._metadata_names(updated, "labels", "name"))
            actual_assignees = set(
                self._metadata_names(updated, "assignees", "login")
            )
            actual_milestone = self._issue_milestone_number(updated)
            mismatches: List[str] = []
            if actual_labels != set(labels):
                mismatches.append("labels")
            if actual_assignees != set(assignees):
                mismatches.append("assignees")
            if actual_milestone != milestone:
                mismatches.append("milestone")

            self._current = updated
            self.meta_label.setText(self._format_meta(updated))
            self._sync_metadata_editor()
            if mismatches:
                self._status(
                    self.tr(
                        "Issue #{n} の metadata を保存しましたが、警告: "
                        "指定と応答が一致しない項目があります ({fields})。"
                    ).format(n=number, fields=", ".join(mismatches))
                )
            else:
                self._status(
                    self.tr("Issue #{n} の metadata を保存しました。").format(
                        n=number
                    )
                )

        def _failed(message: str) -> None:
            if self._metadata_save_token is not token:
                return
            self._metadata_save_token = None
            self._sync_assignment_guarded_controls()
            if not self._operation_is_current(operation_epoch):
                self._sync_assignment_guarded_controls()
                return
            if _request_target_snapshot() is None:
                self._sync_metadata_editor()
                self._status(
                    self.tr(
                        "選択中の Issue が変更されたため、古い metadata エラーを破棄しました。"
                    )
                )
                return
            self._set_metadata_editor_enabled(True)
            self._show_error(message, operation_epoch)

        self._run(
            partial(
                github_service.update_issue,
                repo_at_request,
                number,
                labels=labels,
                assignees=assignees,
                milestone=milestone,
            ),
            _done,
            _failed,
        )

    def toggle_state(self) -> None:
        """open ⇔ closed を切り替える。"""
        if (
            self._copilot_assignment_token is not None
            or self._metadata_save_token is not None
            or self._current is None
            or not self._require_repo()
        ):
            return
        number = self._current["number"]
        new_state = "open" if self._current.get("state") == "closed" else "closed"
        operation_epoch = self._advance_operation_epoch()
        self._run(
            partial(github_service.update_issue, self._repo, number, state=new_state),
            lambda _r: self._on_issue_changed(
                number,
                self.tr("Issue #{n} の状態を変更しました。"),
                operation_epoch,
            ),
            lambda message: self._show_error(message, operation_epoch),
        )

    def post_comment(self) -> None:
        """新しいコメントを投稿する。"""
        if (
            self._copilot_assignment_token is not None
            or self._metadata_save_token is not None
            or self._current is None
            or not self._require_repo()
        ):
            return
        body = self.new_comment_edit.text()
        if not body.strip():
            self._show_error(self.tr("コメント本文を入力してください。"))
            return
        number = self._current["number"]
        operation_epoch = self._advance_operation_epoch()

        def _done(_result: Any) -> None:
            if not self._operation_is_current(operation_epoch):
                return
            self.new_comment_edit.clear()
            self._status(self.tr("コメントを投稿しました。"), operation_epoch)
            self._load_comments(number, operation_epoch)

        self._run(
            partial(github_service.post_comment, self._repo, number, body),
            _done,
            lambda message: self._show_error(message, operation_epoch),
        )

    def save_comment(self) -> None:
        """選択中の自分のコメントを更新する。"""
        comment = self._selected_comment()
        if (
            self._copilot_assignment_token is not None
            or self._metadata_save_token is not None
            or comment is None
            or not self._is_own(comment)
            or not self._require_repo()
        ):
            return
        number = self._current["number"] if self._current else None
        body = self.comment_edit.text()
        operation_epoch = self._advance_operation_epoch()

        def _done(_result: Any) -> None:
            if not self._operation_is_current(operation_epoch):
                return
            self._status(self.tr("コメントを更新しました。"), operation_epoch)
            if number is not None:
                self._load_comments(number, operation_epoch)

        self._run(
            partial(github_service.update_comment, self._repo, comment["id"], body),
            _done,
            lambda message: self._show_error(message, operation_epoch),
        )

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _request_issues(
        self,
        *,
        cursor: Optional[str],
        append: bool,
    ) -> None:
        if self._copilot_assignment_token is not None:
            return
        if append and (not isinstance(cursor, str) or not cursor):
            self._show_error(self.tr("Issue 一覧の継続 cursor が不正です。"))
            return
        if not append:
            self._next_issue_cursor = None
            self._issue_cursor_history.clear()
            self._issues_have_more = False

        repo_at_request = self._repo
        state_at_request = self.state_combo.currentData() or "open"
        operation_epoch_at_request = self._operation_epoch
        self._list_request_serial += 1
        request_token = self._list_request_serial
        self._active_list_request_token = request_token
        self._list_request_in_flight = True
        self._update_issue_list_controls()
        progress_message = (
            self.tr("Issue をさらに取得中...")
            if append
            else self.tr("Issue 一覧を取得中...")
        )
        self._status(progress_message)

        def _done(issues: Any) -> None:
            if request_token != self._active_list_request_token:
                return
            if not self._is_issue_list_context(repo_at_request, state_at_request):
                self._finish_issue_list_request(request_token)
                return
            if not isinstance(issues, list) or any(
                not self._is_valid_issue_list_item(issue) for issue in issues
            ):
                self._report_issue_list_failure(
                    self.tr("Issue 一覧の応答を解釈できませんでした。"),
                    append=append,
                )
                self._finish_issue_list_request(request_token)
                return
            next_cursor = getattr(issues, "next_url", None)
            if next_cursor is not None and (
                not isinstance(next_cursor, str) or not next_cursor
            ):
                self._report_issue_list_failure(
                    self.tr("Issue 一覧の継続 cursor を解釈できませんでした。"),
                    append=append,
                )
                self._finish_issue_list_request(request_token)
                return
            cursor_history = set(self._issue_cursor_history)
            if append and cursor is not None:
                cursor_history.add(cursor)
            if next_cursor is not None and next_cursor in cursor_history:
                self._report_issue_list_failure(
                    self.tr("Issue 一覧の継続 cursor に循環を検出しました。"),
                    append=append,
                )
                self._finish_issue_list_request(request_token)
                return
            page_items = list(issues)
            self._issue_cursor_history = cursor_history
            self._next_issue_cursor = next_cursor
            self._issues_have_more = next_cursor is not None
            report_status = self._operation_epoch == operation_epoch_at_request
            self._on_issues_loaded(
                page_items,
                append=append,
                report_status=report_status,
            )
            if not report_status and self.status_label.text() == progress_message:
                self._status("")
            self._finish_issue_list_request(request_token)

        def _failed(message: str) -> None:
            if request_token != self._active_list_request_token:
                return
            stale = not self._is_issue_list_context(
                repo_at_request, state_at_request
            )
            if not stale and self._operation_epoch == operation_epoch_at_request:
                self._report_issue_list_failure(message, append=append)
            elif self.status_label.text() == progress_message:
                self._status("")
            self._finish_issue_list_request(request_token)

        def _task() -> Any:
            options: dict[str, Any] = {
                "state": state_at_request,
                "per_page": _ISSUES_PER_PAGE,
            }
            if append and cursor is not None:
                options["cursor"] = cursor
            return github_service.list_issues(
                repo_at_request,
                **options,
            )

        self._run(_task, _done, _failed)

    @staticmethod
    def _is_valid_issue_list_item(issue: Any) -> bool:
        if not isinstance(issue, dict):
            return False
        number = issue.get("number")
        return (
            isinstance(number, int)
            and not isinstance(number, bool)
            and number > 0
        )

    def _report_issue_list_failure(self, message: str, *, append: bool) -> None:
        if (
            not append
            and self._created_issue_number is not None
            and self._pending_issue_refresh is None
        ):
            self._on_issue_refresh_failed(message)
            return
        self._show_error(message)

    def _on_issue_list_context_changed(self, *_args: Any) -> None:
        if self._copilot_assignment_token is not None:
            return
        self._invalidate_issue_list_context()

    def _invalidate_issue_list_context(self) -> None:
        self._list_request_serial += 1
        self._active_list_request_token = None
        self._list_request_in_flight = False
        self._next_issue_cursor = None
        self._issue_cursor_history.clear()
        self._issues_have_more = False
        self._pending_issue_refresh = None
        self._update_issue_list_controls()

    def _is_issue_list_context(self, repo: str, state: str) -> bool:
        return self._repo == repo and (self.state_combo.currentData() or "open") == state

    def _finish_issue_list_request(self, request_token: int) -> None:
        if request_token != self._active_list_request_token:
            return
        self._active_list_request_token = None
        self._list_request_in_flight = False
        self._update_issue_list_controls()
        pending = self._pending_issue_refresh
        self._pending_issue_refresh = None
        if pending is not None and self._is_issue_list_context(*pending):
            self.refresh_issues()

    def _update_issue_list_controls(self) -> None:
        target_controls_enabled = self._copilot_assignment_token is None
        self.refresh_button.setEnabled(
            target_controls_enabled and not self._list_request_in_flight
        )
        self.load_more_button.setEnabled(
            target_controls_enabled
            and not self._list_request_in_flight
            and self._issues_have_more
        )

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
        try:
            worker.start()
        except RuntimeError as exc:
            if worker in self._workers:
                self._workers.remove(worker)
            (on_ng or self._show_error)(
                self.tr("GitHub ワーカーの起動に失敗しました: {kind}").format(
                    kind=type(exc).__name__
                )
            )

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

    def _advance_operation_epoch(self) -> int:
        self._operation_epoch += 1
        return self._operation_epoch

    def _operation_is_current(self, operation_epoch: int) -> bool:
        return operation_epoch == self._operation_epoch

    def _status(self, message: str, operation_epoch: Optional[int] = None) -> None:
        if operation_epoch is not None and not self._operation_is_current(operation_epoch):
            return
        self.status_label.setText(message)

    def _show_error(self, message: str, operation_epoch: Optional[int] = None) -> None:
        if operation_epoch is not None and not self._operation_is_current(operation_epoch):
            return
        self.status_label.setText(message)

    def _set_create_enabled(self, enabled: bool) -> None:
        self._create_controls_requested_enabled = enabled
        self._apply_create_controls_enabled()

    def _apply_create_controls_enabled(self) -> None:
        enabled = (
            self._create_controls_requested_enabled
            and self._copilot_assignment_token is None
            and self._metadata_save_token is None
        )
        for widget in (
            self.create_title_edit,
            self.create_body_edit,
            self.create_labels_list,
            self.create_assignees_list,
            self.create_milestone_combo,
            self.create_and_link_checkbox,
            self.generate_title_button,
            self.create_issue_button,
        ):
            widget.setEnabled(enabled)
        self.load_metadata_button.setEnabled(
            enabled
            and self._copilot_assignment_token is None
            and self._metadata_load_token is None
            and self._metadata_save_token is None
        )

    def _on_creation_metadata_loaded(self, result: Any) -> None:
        if not isinstance(result, dict):
            self._sync_metadata_editor()
            self._show_error(self.tr("Issue の作成候補を取得できませんでした。"))
            return
        labels: List[Dict[str, Any]] = [
            {"name": str(item["name"])}
            for item in result.get("labels", [])
            if isinstance(item, dict) and item.get("name")
        ]
        assignees: List[Dict[str, Any]] = [
            {"login": str(item["login"])}
            for item in result.get("assignees", [])
            if isinstance(item, dict) and item.get("login")
        ]
        milestones: List[Dict[str, Any]] = [
            {"number": int(item["number"]), "title": str(item["title"])}
            for item in result.get("milestones", [])
            if isinstance(item, dict) and item.get("title") and item.get("number")
        ]
        self._creation_metadata = {
            "labels": labels,
            "assignees": assignees,
            "milestones": milestones,
        }
        self.create_labels_list.clear()
        for label in labels:
            self.create_labels_list.addItem(str(label["name"]))
        self.create_assignees_list.clear()
        for assignee in assignees:
            self.create_assignees_list.addItem(str(assignee["login"]))
        self.create_milestone_combo.clear()
        self.create_milestone_combo.addItem(self.tr("指定なし"), None)
        for milestone in milestones:
            self.create_milestone_combo.addItem(
                str(milestone["title"]), int(milestone["number"])
            )
        self._sync_metadata_editor()
        self._status(self.tr("Issue の作成候補を取得しました。"))

    def _sync_metadata_editor(self) -> None:
        self.edit_labels_list.clear()
        self.edit_assignees_list.clear()
        self.edit_milestone_combo.clear()
        self.edit_milestone_combo.addItem(self.tr("未設定"), 0)

        metadata = self._creation_metadata
        if metadata is None:
            self.metadata_guidance_label.setText(
                self.tr(
                    "編集候補は未取得です。Issue 作成面の [作成候補を取得] を実行してください。"
                )
            )
            self._set_metadata_editor_enabled(False)
            return

        for item in metadata["labels"]:
            self.edit_labels_list.addItem(str(item["name"]))
        for item in metadata["assignees"]:
            self.edit_assignees_list.addItem(str(item["login"]))
        for item in metadata["milestones"]:
            self.edit_milestone_combo.addItem(
                str(item["title"]), int(item["number"])
            )

        if self._current is None:
            self.metadata_guidance_label.setText(
                self.tr("metadata を編集する Issue を選択してください。")
            )
            self._set_metadata_editor_enabled(False)
            return

        current_labels = set(self._metadata_names(self._current, "labels", "name"))
        current_assignees = set(
            self._metadata_names(self._current, "assignees", "login")
        )
        candidate_labels = {
            str(item["name"]) for item in metadata["labels"]
        }
        candidate_assignees = {
            str(item["login"]) for item in metadata["assignees"]
        }
        candidate_milestones = {
            int(item["number"]) for item in metadata["milestones"]
        }
        current_only: List[str] = []
        for value in sorted(current_labels - candidate_labels):
            self.edit_labels_list.addItem(value)
            current_only.append("labels")
        for value in sorted(current_assignees - candidate_assignees):
            self.edit_assignees_list.addItem(value)
            current_only.append("assignees")

        milestone_number = self._issue_milestone_number(self._current)
        if milestone_number and milestone_number not in candidate_milestones:
            milestone = self._current.get("milestone")
            title = (
                str(milestone.get("title") or f"#{milestone_number}")
                if isinstance(milestone, dict)
                else f"#{milestone_number}"
            )
            self.edit_milestone_combo.addItem(
                self.tr("{title}（現在値・候補外）").format(title=title),
                milestone_number,
            )
            current_only.append("milestone")

        for row in range(self.edit_labels_list.count()):
            item = self.edit_labels_list.item(row)
            item.setSelected(item.text() in current_labels)
        for row in range(self.edit_assignees_list.count()):
            item = self.edit_assignees_list.item(row)
            item.setSelected(item.text() in current_assignees)

        milestone_index = self.edit_milestone_combo.findData(milestone_number)
        self.edit_milestone_combo.setCurrentIndex(max(0, milestone_index))

        if current_only:
            self.metadata_guidance_label.setText(
                self.tr(
                    "作成候補にない現在値も保持して選択表示しています: {fields}"
                ).format(fields=", ".join(dict.fromkeys(current_only)))
            )
        else:
            self.metadata_guidance_label.setText(
                self.tr("Issue 作成面で取得済みの候補を再利用しています。")
            )
        self._set_metadata_editor_enabled(
            self._metadata_load_token is None and self._metadata_save_token is None
        )

    def _set_metadata_editor_enabled(self, enabled: bool) -> None:
        enabled = enabled and self._copilot_assignment_token is None
        for widget in (
            self.edit_labels_list,
            self.edit_assignees_list,
            self.edit_milestone_combo,
            self.save_metadata_button,
        ):
            widget.setEnabled(enabled)
        self.load_metadata_button.setEnabled(
            self._copilot_assignment_token is None
            and self._metadata_load_token is None
            and self._metadata_save_token is None
            and self.create_issue_button.isEnabled()
        )

    @staticmethod
    def _metadata_names(issue: Dict[str, Any], key: str, field: str) -> List[str]:
        values = issue.get(key)
        if not isinstance(values, list):
            return []
        return [
            str(value[field])
            for value in values
            if isinstance(value, dict) and value.get(field)
        ]

    @staticmethod
    def _issue_milestone_number(issue: Dict[str, Any]) -> int:
        milestone = issue.get("milestone")
        if not isinstance(milestone, dict):
            return 0
        try:
            return int(milestone.get("number") or 0)
        except (TypeError, ValueError):
            return 0

    def _format_metadata_warnings(self, values: Any) -> List[str]:
        warnings: List[str] = []
        for value in values if isinstance(values, list) else []:
            if not isinstance(value, dict):
                continue
            kind = value.get("kind")
            item = value.get("value")
            if kind == "label":
                warnings.append(
                    self.tr("ラベル '{value}' は反映されませんでした。").format(
                        value=item
                    )
                )
            elif kind == "assignee":
                warnings.append(
                    self.tr("担当者 '{value}' は反映されませんでした。").format(
                        value=item
                    )
                )
            elif kind == "milestone":
                warnings.append(
                    self.tr("マイルストーン #{value} は反映されませんでした。").format(
                        value=item
                    )
                )
        return warnings

    def _on_issue_refresh_failed(self, message: str) -> None:
        created_number = self._created_issue_number
        warnings = list(self._created_issue_warnings)
        self._created_issue_number = None
        self._created_issue_warnings = []
        if created_number is None:
            self._show_error(message)
            return
        self._show_error(
            self.tr("Issue #{n} は作成済みですが、一覧の更新に失敗しました: {message}{warnings}").format(
                n=created_number,
                message=message,
                warnings=("; " + "; ".join(warnings)) if warnings else "",
            )
        )

    def _on_issues_loaded(
        self,
        issues: Any,
        *,
        append: bool = False,
        report_status: bool = True,
    ) -> None:
        page_items = [issue for issue in list(issues or []) if isinstance(issue, dict)]
        combined = [*self._issues, *page_items] if append else page_items
        self._issues = self._deduplicate_issues(combined)
        self._apply_list_filter()
        created_number = self._created_issue_number
        warnings = list(self._created_issue_warnings)
        if (
            not append
            and self._pending_issue_refresh is None
            and created_number is not None
        ):
            found = False
            found = self.select_issue(created_number)
            if found:
                message = self.tr("Issue #{n} を作成し、一覧から選択しました。").format(
                    n=created_number
                )
            else:
                message = self.tr(
                    "Issue #{n} を作成しました。現在の一覧または絞り込みには表示されていません。"
                ).format(n=created_number)
            if warnings:
                message += " " + self.tr("警告: {warnings}").format(
                    warnings="; ".join(warnings)
                )
            if report_status:
                self._status(message)
            self._created_issue_number = None
            self._created_issue_warnings = []
            return
        if self._issues and report_status:
            self._status(
                self.tr("{n} 件の Issue を取得しました。").format(n=len(self._issues))
            )
        elif report_status and (self.state_combo.currentData() or "open") == "open":
            self._status(
                self.tr(
                    "オープンな Issue は 0 件です。「状態」を「すべて」にして [更新] すると"
                    "クローズ済みの Issue も表示されます。"
                )
            )
        elif report_status:
            self._status(self.tr("対象の Issue は 0 件です。"))
        self._apply_linked_selection()

    @staticmethod
    def _deduplicate_issues(issues: List[dict]) -> List[dict]:
        unique: List[dict] = []
        seen_numbers: set[Any] = set()
        for issue in issues:
            number = issue.get("number")
            if number is not None and number in seen_numbers:
                continue
            if number is not None:
                seen_numbers.add(number)
            unique.append(issue)
        return unique

    def _apply_list_filter(self, *_args: Any) -> None:
        """取得済み一覧をクライアント側だけで絞り込む（FR-GUI-31）。

        一覧の再構築中は選択シグナルを止める。選択中 Issue が新しい表示一覧に
        残る場合は詳細・編集中の値を保持し、消えた場合だけ詳細を破棄する。
        """
        if self._copilot_assignment_token is not None:
            return
        selected_number: Optional[int] = None
        selected_row = self.issue_list.currentRow()
        if 0 <= selected_row < len(self._visible):
            selected_value: Any = self._visible[selected_row].get("number")
            if isinstance(selected_value, int) and not isinstance(selected_value, bool):
                selected_number = selected_value
        if selected_number is None:
            current_issue: Optional[dict] = self._current
            current_value: Any = (
                current_issue.get("number") if current_issue is not None else None
            )
            if isinstance(current_value, int) and not isinstance(current_value, bool):
                selected_number = current_value

        keyword = self.filter_edit.text().strip().lower()
        self._visible = [
            issue
            for issue in self._issues
            if not keyword or keyword in self._issue_label(issue).lower()
        ]
        restored_row = -1
        previous_signal_state = self.issue_list.blockSignals(True)
        try:
            self.issue_list.clear()
            for row, issue in enumerate(self._visible):
                self.issue_list.addItem(self._issue_label(issue))
                if selected_number is not None and issue.get("number") == selected_number:
                    restored_row = row
            if restored_row >= 0:
                self.issue_list.setCurrentRow(restored_row)
        finally:
            self.issue_list.blockSignals(previous_signal_state)

        if selected_number is not None and restored_row < 0:
            self._clear_issue_detail()

    @staticmethod
    def _issue_label(issue: Dict[str, Any]) -> str:
        return f"#{issue.get('number')} {issue.get('title', '')}"

    def _on_issue_selected(self, row: int) -> None:
        if self._copilot_assignment_token is not None:
            return
        if row < 0 or row >= len(self._visible):
            self._clear_issue_detail()
            return
        number = int(self._visible[row]["number"])
        self._set_issue_target(self._repo, number)
        self._current = None
        self._set_detail_enabled(False)
        if not self._suppress_selection_signal:
            self._linked_number = None
            self.issue_selected.emit(number)
        self._load_issue(number)

    def _load_issue(
        self,
        number: int,
        operation_epoch: Optional[int] = None,
    ) -> None:
        if self._copilot_assignment_token is not None:
            return
        if operation_epoch is None:
            operation_epoch = self._advance_operation_epoch()
        self._issue_load_generation += 1
        generation = self._issue_load_generation
        repo_at_request = self._repo

        def _done(issue: Any) -> None:
            if (
                generation != self._issue_load_generation
                or self._repo != repo_at_request
                or not self._operation_is_current(operation_epoch)
            ):
                return
            self._on_issue_loaded(issue)

        def _failed(message: str) -> None:
            if (
                generation != self._issue_load_generation
                or self._repo != repo_at_request
                or not self._operation_is_current(operation_epoch)
            ):
                return
            self._show_error(message, operation_epoch)

        self._run(
            partial(github_service.get_issue, repo_at_request, number), _done, _failed
        )

    def _on_issue_loaded(self, issue: Any) -> None:
        if not isinstance(issue, dict):
            self._show_error(self.tr("Issue の詳細を取得できませんでした。"))
            return
        number = issue.get("number")
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            self._show_error(self.tr("Issue の詳細を取得できませんでした。"))
            return
        self._set_issue_target(self._repo, number)
        self._current = issue
        self.title_edit.setText(str(issue.get("title") or ""))
        self.body_edit.set_text(str(issue.get("body") or ""))
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

    def _on_issue_changed(
        self,
        number: int,
        template: str,
        operation_epoch: int,
    ) -> None:
        if not self._operation_is_current(operation_epoch):
            return
        self._status(template.format(n=number), operation_epoch)
        self._load_issue(number, operation_epoch)

    def _load_comments(
        self,
        number: int,
        operation_epoch: Optional[int] = None,
    ) -> None:
        if (
            self._copilot_assignment_token is not None
            and operation_epoch is None
        ):
            return
        if operation_epoch is None:
            operation_epoch = self._operation_epoch
        repo_at_request = self._repo
        issue_number_at_request = int(number)
        issue_generation_at_request = self._issue_load_generation

        def _matches_request_target() -> bool:
            current_issue: Optional[dict] = self._current
            if (
                not self._operation_is_current(operation_epoch)
                or
                self._repo != repo_at_request
                or current_issue is None
                or self._issue_load_generation != issue_generation_at_request
            ):
                return False
            current_number_value: Any = current_issue.get("number")
            if current_number_value is None:
                return False
            try:
                return int(current_number_value) == issue_number_at_request
            except (TypeError, ValueError):
                return False

        def _done(comments: Any) -> None:
            if _matches_request_target():
                self._on_comments_loaded(comments)

        def _failed(message: str) -> None:
            if _matches_request_target():
                self._show_error(message, operation_epoch)

        if not self._login:
            self._run(
                github_service.current_user_login,
                lambda login: (
                    self._on_login_loaded(login)
                    if self._operation_is_current(operation_epoch)
                    else None
                ),
                lambda _m: None,
            )
        self._run(
            partial(
                github_service.list_comments,
                repo_at_request,
                issue_number_at_request,
            ),
            _done,
            _failed,
        )

    def _clear_issue_detail(self) -> None:
        """選択対象が消えたときだけ Issue 詳細と進行中世代を破棄する。"""
        if self._copilot_assignment_token is not None:
            return
        self._advance_operation_epoch()
        self._set_issue_target(self._repo, None)
        self._issue_load_generation += 1
        self._current = None
        self._comments = []
        self.title_edit.clear()
        self.body_edit.clear()
        self.meta_label.clear()
        self.url_label.clear()
        self.comment_list.clear()
        self.comment_edit.clear()
        self.new_comment_edit.clear()
        self._set_detail_enabled(False)

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
        self.comment_edit.clear()
        self._apply_comment_permissions(None)

    def _on_comment_selected(self, row: int) -> None:
        comment = self._comments[row] if 0 <= row < len(self._comments) else None
        self.comment_edit.set_text(str(comment.get("body") or "") if comment else "")
        self._apply_comment_permissions(comment)

    def _apply_comment_permissions(self, comment: Optional[dict]) -> None:
        editable = (
            self._copilot_assignment_token is None
            and comment is not None
            and self._is_own(comment)
        )
        self.comment_edit.set_read_only(not editable)
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
        author = issue.get("user")
        author_login = str(author.get("login")) if isinstance(author, dict) else ""
        parts = [
            f"#{issue.get('number')}",
            f"state: {issue.get('state')}",
            f"author: {author_login}",
        ]
        labels = ", ".join(GitHubIssuePanel._metadata_names(issue, "labels", "name"))
        if labels:
            parts.append(f"labels: {labels}")
        assignees = ", ".join(
            GitHubIssuePanel._metadata_names(issue, "assignees", "login")
        )
        if assignees:
            parts.append(f"assignees: {assignees}")
        milestone = issue.get("milestone")
        if isinstance(milestone, dict) and milestone.get("title"):
            parts.append(f"milestone: {milestone['title']}")
        return " | ".join(parts)

    def _set_detail_enabled(self, enabled: bool) -> None:
        effective_enabled = (
            enabled
            and self._copilot_assignment_token is None
            and self._metadata_save_token is None
        )
        for widget in (
            self.title_edit,
            self.body_edit,
            self.save_button,
            self.state_button,
            self.new_comment_edit,
            self.post_comment_button,
            self.comment_list,
            self.comment_edit,
        ):
            widget.setEnabled(effective_enabled)
        if not effective_enabled:
            self._apply_comment_permissions(None)
        else:
            self._apply_comment_permissions(self._selected_comment())
        self._sync_metadata_editor()
        self._sync_copilot_assignment_controls()

    def _sync_assignment_guarded_controls(self) -> None:
        target_controls_enabled = self._copilot_assignment_token is None
        self.state_combo.setEnabled(target_controls_enabled)
        self.filter_edit.setEnabled(target_controls_enabled)
        self.issue_list.setEnabled(target_controls_enabled)
        self._update_issue_list_controls()
        effective_detail = (
            self._current is not None
            and target_controls_enabled
            and self._metadata_save_token is None
        )
        for widget in (
            self.title_edit,
            self.body_edit,
            self.save_button,
            self.state_button,
            self.new_comment_edit,
            self.post_comment_button,
            self.comment_list,
            self.comment_edit,
        ):
            widget.setEnabled(effective_detail)
        if effective_detail:
            self._apply_comment_permissions(self._selected_comment())
        else:
            self._apply_comment_permissions(None)
        metadata_enabled = (
            target_controls_enabled
            and self._creation_metadata is not None
            and self._current is not None
            and self._metadata_load_token is None
            and self._metadata_save_token is None
        )
        self._set_metadata_editor_enabled(metadata_enabled)
        self._apply_create_controls_enabled()
        self._sync_copilot_assignment_controls()
