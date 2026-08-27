"""hve.gui.github_pr_panel — GitHub Pull Request の閲覧・作成・コメント。

直接作成は現在の local branch だけを対象にし、Orchestrator の branch 作成・commit
経路とは分離する（FR-GUI-42）。
コンソール出力の投稿（FR-GUI-33）と push / head ブランチ削除（FR-GUI-34）を含む。
"""

from __future__ import annotations

from functools import partial
from html import escape
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from . import git_ops, github_service
from .github_comment_editor import GitHubCommentEditor
from .github_comment_format import format_console_log_comment
from .github_review_comment_dialog import (
    GitHubReviewCommentDialog,
    build_commentable_files,
)
from .github_threads import GitHubWorker
from hve.github_review_contract import (
    ALLOWED_EVENTS,
    ReviewValidationError,
    validate_pull_request_review,
)
from hve.github_title_generator import generate_github_title

__all__ = ["GitHubPullRequestPanel"]

_DELETABLE_STATES = ("closed",)
_PULL_REQUESTS_PER_PAGE = 50
_MERGE_METHODS = ("merge", "squash", "rebase")
_SUCCESSFUL_CHECK_CONCLUSIONS = frozenset(("success", "neutral", "skipped"))


class GitHubPullRequestPanel(QWidget):
    """Pull Request 一覧・詳細・変更ファイル・コメントを扱うパネル。"""

    pull_request_selected = Signal(object)
    pull_request_created = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._repo: str = ""
        self._pulls: List[dict] = []
        self._visible: List[dict] = []
        self._current: Optional[dict] = None
        self._workers: List[GitHubWorker] = []
        self._loaded_repo: str = ""
        self._console_provider: Optional[Callable[[], str]] = None
        self._console_run_id: str = ""
        self._linked_number: Optional[int] = None
        self._suppress_selection_signal = False
        self._repo_root = Path.cwd()
        self._created_pr_number: Optional[int] = None
        self._created_pr_was_existing = False
        self._default_branch: str = ""
        self._create_preflight: Optional[git_ops.PullRequestPreflight] = None
        self._pending_pr_metadata: Optional[dict[str, Any]] = None
        self._post_create_metadata_message: str = ""
        self._created_pr_url: str = ""
        self._next_pull_request_cursor: Optional[str] = None
        self._pull_request_cursor_history: set[str] = set()
        self._pull_requests_have_more = False
        self._list_request_in_flight = False
        self._list_request_serial = 0
        self._active_list_request_token: Optional[int] = None
        self._pending_pull_request_refresh: Optional[tuple[str, str]] = None
        self._pull_request_load_generation = 0
        self._current_pull_request_generation: Optional[int] = None
        self._current_files: Optional[List[dict[str, Any]]] = None
        self._current_files_head_sha: str = ""
        self._review_request_token: Optional[object] = None
        self._review_submit_token: Optional[object] = None
        self._check_runs_request_token: Optional[object] = None
        self._merge_request_token: Optional[object] = None
        self._check_runs: Optional[List[dict[str, Any]]] = None
        self._check_runs_context: Optional[
            tuple[str, int, int, str, str, str]
        ] = None

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
            self._on_pull_request_list_context_changed
        )
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
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.tr("番号・タイトルで絞り込み"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_list_filter)
        layout.addWidget(self.filter_edit)
        self.pr_list = QListWidget()
        self.pr_list.currentRowChanged.connect(self._on_pull_request_selected)
        layout.addWidget(self.pr_list)
        self.load_more_button = QPushButton(self.tr("さらに読み込む"))
        self.load_more_button.setEnabled(False)
        self.load_more_button.clicked.connect(self.load_more_pull_requests)
        layout.addWidget(self.load_more_button)
        return pane

    def _build_create_group(self) -> QWidget:
        box = QGroupBox(self.tr("Pull Request を作成"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        branch_row = QHBoxLayout()
        branch_row.addWidget(QLabel(self.tr("Base branch")))
        self.create_base_edit = QLineEdit("main")
        self.create_base_edit.textChanged.connect(self._invalidate_create_preflight)
        branch_row.addWidget(self.create_base_edit)
        branch_row.addWidget(QLabel(self.tr("Head branch")))
        self.create_head_label = QLabel(self.tr("未確認"))
        branch_row.addWidget(self.create_head_label)
        self.create_preflight_button = QPushButton(self.tr("作成前チェック"))
        self.create_preflight_button.clicked.connect(self.refresh_create_preflight)
        branch_row.addWidget(self.create_preflight_button)
        layout.addLayout(branch_row)

        self.create_compare_label = QLabel(self.tr("作成前チェックを実行してください。"))
        self.create_compare_label.setWordWrap(True)
        self.create_compare_label.setProperty("hveRole", "description")
        layout.addWidget(self.create_compare_label)
        self.created_pr_url_label = QLabel("")
        self.created_pr_url_label.setOpenExternalLinks(True)
        self.created_pr_url_label.setWordWrap(True)
        layout.addWidget(self.created_pr_url_label)

        self.create_title_edit = QLineEdit()
        self.create_title_edit.setPlaceholderText(self.tr("Pull Request のタイトル"))
        layout.addWidget(self.create_title_edit)
        self.create_body_edit = GitHubCommentEditor()
        self.create_body_edit.set_placeholder_text(
            self.tr("Pull Request の本文（Markdown、任意）")
        )
        layout.addWidget(self.create_body_edit)

        issue_row = QHBoxLayout()
        issue_row.addWidget(QLabel(self.tr("関連 Issue")))
        self.create_issue_edit = QLineEdit()
        self.create_issue_edit.setValidator(QIntValidator(1, 2_147_483_647, self))
        self.create_issue_edit.setPlaceholderText("123")
        issue_row.addWidget(self.create_issue_edit)
        self.create_close_issue_checkbox = QCheckBox(
            self.tr("default branch への merge 時に Issue を閉じる")
        )
        self.create_close_issue_checkbox.setChecked(False)
        issue_row.addWidget(self.create_close_issue_checkbox)
        layout.addLayout(issue_row)

        self.create_labels_edit = QLineEdit()
        self.create_labels_edit.setPlaceholderText(self.tr("ラベル（カンマ区切り）"))
        layout.addWidget(self.create_labels_edit)
        self.create_assignees_edit = QLineEdit()
        self.create_assignees_edit.setPlaceholderText(self.tr("担当者（カンマ区切り）"))
        layout.addWidget(self.create_assignees_edit)
        self.create_milestone_edit = QLineEdit()
        self.create_milestone_edit.setValidator(QIntValidator(1, 2_147_483_647, self))
        self.create_milestone_edit.setPlaceholderText(self.tr("マイルストーン番号（任意）"))
        layout.addWidget(self.create_milestone_edit)
        self.create_reviewers_edit = QLineEdit()
        self.create_reviewers_edit.setPlaceholderText(
            self.tr("レビュアー（ユーザー名、カンマ区切り）")
        )
        layout.addWidget(self.create_reviewers_edit)
        self.create_team_reviewers_edit = QLineEdit()
        self.create_team_reviewers_edit.setPlaceholderText(
            self.tr("レビュアーチーム（slug、カンマ区切り）")
        )
        layout.addWidget(self.create_team_reviewers_edit)

        action_row = QHBoxLayout()
        self.generate_title_button = QPushButton(self.tr("Copilot でタイトルを生成"))
        self.generate_title_button.clicked.connect(self.generate_pull_request_title)
        action_row.addWidget(self.generate_title_button)
        self.load_template_button = QPushButton(self.tr("既定テンプレートを読み込む"))
        self.load_template_button.clicked.connect(self.load_default_template)
        action_row.addWidget(self.load_template_button)
        self.create_draft_checkbox = QCheckBox(self.tr("Draft"))
        self.create_draft_checkbox.setChecked(False)
        action_row.addWidget(self.create_draft_checkbox)
        self.create_pull_request_button = QPushButton(self.tr("Pull Request を作成"))
        self.create_pull_request_button.clicked.connect(self.create_pull_request)
        action_row.addWidget(self.create_pull_request_button)
        self.retry_metadata_button = QPushButton(self.tr("metadata を再試行"))
        self.retry_metadata_button.setEnabled(False)
        self.retry_metadata_button.clicked.connect(self.retry_pull_request_metadata)
        action_row.addWidget(self.retry_metadata_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)
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

        self.body_view = QPlainTextEdit()
        self.body_view.setReadOnly(True)
        layout.addWidget(self.body_view, stretch=2)

        files_box = QGroupBox(self.tr("変更ファイル"))
        files_layout = QVBoxLayout(files_box)
        files_layout.setContentsMargins(8, 4, 8, 4)
        self.file_list = QListWidget()
        files_layout.addWidget(self.file_list)
        self.review_comment_button = QPushButton(
            self.tr("差分行へレビューコメント")
        )
        self.review_comment_button.clicked.connect(
            self.open_review_comment_dialog
        )
        files_layout.addWidget(self.review_comment_button)
        self.review_comment_hint_label = QLabel("")
        self.review_comment_hint_label.setWordWrap(True)
        self.review_comment_hint_label.setProperty("hveRole", "description")
        files_layout.addWidget(self.review_comment_hint_label)
        layout.addWidget(files_box, stretch=2)

        layout.addWidget(self._build_branch_group())
        layout.addWidget(self._build_merge_group(), stretch=2)
        layout.addWidget(self._build_review_group(), stretch=3)
        layout.addWidget(self._build_comment_group(), stretch=3)
        return pane

    def _build_branch_group(self) -> QWidget:
        box = QGroupBox(self.tr("ブランチ"))
        row = QHBoxLayout(box)
        row.setContentsMargins(8, 4, 8, 4)
        self.push_button = QPushButton(self.tr("現在のブランチを push"))
        self.push_button.setToolTip(
            self.tr("現在のローカルブランチを origin へ push します（git push -u origin <ブランチ>）。")
        )
        self.push_button.clicked.connect(self.push_current_branch)
        row.addWidget(self.push_button)
        self.delete_branch_button = QPushButton(self.tr("head ブランチを削除"))
        self.delete_branch_button.setToolTip(
            self.tr("マージ済みまたはクローズ済みの PR の head ブランチを origin から削除します。")
        )
        self.delete_branch_button.clicked.connect(self.delete_head_branch)
        row.addWidget(self.delete_branch_button)
        row.addStretch(1)
        return box

    def _build_merge_group(self) -> QWidget:
        box = QGroupBox(self.tr("check-runs / merge"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.check_run_list = QListWidget()
        layout.addWidget(self.check_run_list, stretch=1)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        self.refresh_check_runs_button = QPushButton(
            self.tr("check-runs を更新")
        )
        self.refresh_check_runs_button.clicked.connect(self.refresh_check_runs)
        action_row.addWidget(self.refresh_check_runs_button)
        action_row.addWidget(QLabel(self.tr("merge method")))
        self.merge_method_combo = QComboBox()
        for method in _MERGE_METHODS:
            self.merge_method_combo.addItem(method, method)
        action_row.addWidget(self.merge_method_combo)
        self.merge_button = QPushButton(self.tr("Pull Request をマージ"))
        self.merge_button.clicked.connect(self.merge_current_pull_request)
        action_row.addWidget(self.merge_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.merge_guidance_label = QLabel("")
        self.merge_guidance_label.setWordWrap(True)
        self.merge_guidance_label.setProperty("hveRole", "description")
        layout.addWidget(self.merge_guidance_label)
        return box

    def _build_review_group(self) -> QWidget:
        self.review_group = QGroupBox(self.tr("レビュー"))
        layout = QVBoxLayout(self.review_group)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.review_list = QListWidget()
        layout.addWidget(self.review_list, stretch=1)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.addWidget(QLabel(self.tr("種類")))
        self.review_event_combo = QComboBox()
        for event in ALLOWED_EVENTS:
            self.review_event_combo.addItem(event, event)
        action_row.addWidget(self.review_event_combo)
        self.refresh_reviews_button = QPushButton(self.tr("レビューを更新"))
        self.refresh_reviews_button.clicked.connect(
            self.refresh_pull_request_reviews
        )
        action_row.addWidget(self.refresh_reviews_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.review_body_edit = GitHubCommentEditor()
        self.review_body_edit.set_placeholder_text(
            self.tr("レビュー本文（APPROVE は省略可能）")
        )
        layout.addWidget(self.review_body_edit, stretch=1)

        self.submit_review_button = QPushButton(self.tr("レビューを提出"))
        self.submit_review_button.clicked.connect(self.submit_review)
        layout.addWidget(self.submit_review_button)
        return self.review_group

    def _build_comment_group(self) -> QWidget:
        box = QGroupBox(self.tr("コメント"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self.comment_list = QListWidget()
        layout.addWidget(self.comment_list, stretch=1)

        self.new_comment_edit = GitHubCommentEditor()
        self.new_comment_edit.set_placeholder_text(self.tr("新しいコメントを入力"))
        layout.addWidget(self.new_comment_edit, stretch=1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self.post_comment_button = QPushButton(self.tr("コメントを投稿"))
        self.post_comment_button.clicked.connect(self.post_comment)
        button_row.addWidget(self.post_comment_button)
        self.post_console_button = QPushButton(self.tr("コンソール出力を投稿"))
        self.post_console_button.setToolTip(
            self.tr("作業状況画面のコンソール出力（末尾 300 行）を折りたたみ形式で投稿します。")
        )
        self.post_console_button.clicked.connect(self.post_console_log)
        button_row.addWidget(self.post_console_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        return box

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_repo(self, repo: str) -> None:
        """対象リポジトリ（``owner/repo``）を設定する。"""
        resolved = (repo or "").strip()
        changed = resolved != self._repo
        if changed:
            self._default_branch = ""
            self._loaded_repo = ""
            self._linked_number = None
            self._created_pr_number = None
            self._created_pr_was_existing = False
            self._post_create_metadata_message = ""
            self._created_pr_url = ""
            self.created_pr_url_label.clear()
            self._invalidate_create_preflight()
            self._clear_pending_metadata()
            self._invalidate_pull_request_detail_context(clear_reviews=True)
            self._pulls = []
            self._visible = []
            self.filter_edit.clear()
            previous_signal_state = self.pr_list.blockSignals(True)
            try:
                self.pr_list.clear()
            finally:
                self.pr_list.blockSignals(previous_signal_state)
        self._repo = resolved
        if changed:
            self._invalidate_pull_request_list_context()
            self._update_review_controls()

    def set_repository_root(self, repo_root: Path) -> None:
        self._repo_root = Path(repo_root)
        self.create_head_label.setText(self.tr("未確認"))
        self.load_default_template()

    def set_base_branch(self, branch: str) -> None:
        value = (branch or "").strip() or "main"
        if self.create_base_edit.text() != value:
            self.create_base_edit.setText(value)

    def set_related_issue(self, number: Optional[int]) -> None:
        self.create_issue_edit.setText(str(number) if number else "")

    def set_task_target(self, repo: str, pr_number: Optional[int]) -> None:
        pending = self._pending_pr_metadata
        if pending is None:
            return
        if (
            str(pending.get("repo") or "").casefold() != (repo or "").casefold()
            or pending.get("pr_number") != pr_number
        ):
            self._clear_pending_metadata()

    def load_default_template(self) -> None:
        """未編集の本文へ repository の既定 PR template を読み込む。"""
        if self.create_body_edit.text():
            return
        template = git_ops.load_pull_request_template(self._repo_root)
        if template:
            self.create_body_edit.set_text(template)

    def refresh_create_preflight(self) -> None:
        if not self._require_repo():
            return
        repo_at_request = self._repo
        base_at_request = self.create_base_edit.text().strip()
        root_at_request = self._repo_root
        self.create_preflight_button.setEnabled(False)
        self._status(self.tr("Pull Request の作成前チェック中..."))

        def _task() -> dict:
            local = git_ops.inspect_pull_request(root_at_request, base_at_request)
            self._require_matching_repo(local, repo_at_request)
            result: dict[str, Any] = {"local": local}
            if local.ready:
                result["repository"] = github_service.get_repository_metadata(
                    repo_at_request
                )
                compare = github_service.compare_commits(
                    repo_at_request, base_at_request, local.head_branch
                )
                self._require_remote_compare(compare)
                result["compare"] = compare
                result["existing"] = github_service.find_open_pull_request(
                    repo_at_request, local.head_branch, base_at_request
                )
            return result

        def _done(result: Any) -> None:
            self.create_preflight_button.setEnabled(True)
            if self._repo != repo_at_request or self.create_base_edit.text().strip() != base_at_request:
                self._status(self.tr("対象が変更されたため、古い作成前チェック結果を破棄しました。"))
                return
            self._apply_create_preflight(result)

        def _failed(message: str) -> None:
            self.create_preflight_button.setEnabled(True)
            if self._repo != repo_at_request or self.create_base_edit.text().strip() != base_at_request:
                return
            self._invalidate_create_preflight()
            self.create_compare_label.setText(
                self.tr("作成前チェックに失敗しました。")
            )
            self._show_error(message)

        self._run(_task, _done, _failed)

    def generate_pull_request_title(self) -> None:
        body = self.create_body_edit.text()
        if not body.strip():
            self._show_error(self.tr("タイトル生成に使う Pull Request 本文を入力してください。"))
            return
        self._set_create_enabled(False)
        self._status(self.tr("Copilot CLI で Pull Request のタイトルを生成中..."))
        try:
            from . import settings_store

            cli_path = str(settings_store.get_option("cli_path") or "").strip() or None
        except Exception:
            cli_path = None

        def _done(result: Any) -> None:
            self.create_title_edit.setText(str(result or "").strip())
            self._set_create_enabled(True)
            self._status(self.tr("Copilot CLI でタイトルを生成しました。"))

        def _failed(message: str) -> None:
            self._set_create_enabled(True)
            self._show_error(message)

        self._run(
            partial(generate_github_title, "pull_request", body, cli_path=cli_path),
            _done,
            _failed,
        )

    def create_pull_request(self) -> None:
        if not self._require_repo():
            return
        title = self.create_title_edit.text().strip()
        if not title:
            self._show_error(self.tr("Pull Request のタイトルを入力してください。"))
            return
        base = self.create_base_edit.text().strip()
        if not base:
            self._show_error(self.tr("base branch を入力してください。"))
            return
        issue_text = self.create_issue_edit.text().strip()
        issue_number = int(issue_text) if issue_text.isdigit() else None
        body = self.create_body_edit.text()
        draft = self.create_draft_checkbox.isChecked()
        close_issue = self.create_close_issue_checkbox.isChecked()
        metadata = self._creation_metadata_values()
        repo_at_create = self._repo
        root_at_create = self._repo_root
        self._set_create_enabled(False)
        self._status(self.tr("Pull Request を作成中..."))

        def _task() -> dict:
            local = git_ops.inspect_pull_request(root_at_create, base)
            self._require_matching_repo(local, repo_at_create)
            if not local.published:
                raise git_ops.GitOpsError(
                    f"branch '{local.head_branch}' は origin に未公開です。先に明示的に push してください。"
                )
            if local.unpushed_commits:
                raise git_ops.GitOpsError(
                    f"未 push commit が {local.unpushed_commits} 件あります。先に明示的に push してください。"
                )
            existing = github_service.find_open_pull_request(
                repo_at_create, local.head_branch, base
            )
            if existing is not None:
                return {"existing": existing, "local": local}
            repository = github_service.get_repository_metadata(repo_at_create)
            default_branch = str(repository.get("default_branch") or "")
            compare = github_service.compare_commits(
                repo_at_create, base, local.head_branch
            )
            self._require_remote_compare(compare)
            final_body = self._with_related_issue(
                body,
                issue_number,
                close_issue=close_issue,
                base_branch=base,
                default_branch=default_branch,
            )
            pull = github_service.create_pull_request(
                repo_at_create,
                title,
                final_body,
                local.head_branch,
                base,
                draft=draft,
            )
            return {"pull_request": pull, "local": local}

        def _done(result: Any) -> None:
            self._set_create_enabled(True)
            existing = result.get("existing") if isinstance(result, dict) else None
            pull = result.get("pull_request") if isinstance(result, dict) else None
            target = existing if isinstance(existing, dict) else pull
            if not isinstance(target, dict) or not target.get("number"):
                self._show_error(self.tr("Pull Request の番号を取得できませんでした。"))
                return
            number = int(target["number"])
            self._set_created_pr_url(number, str(target.get("html_url") or ""))
            if self._repo != repo_at_create or self.create_base_edit.text().strip() != base:
                action = (
                    self.tr("既存 Pull Request")
                    if existing is not None
                    else self.tr("Pull Request")
                )
                self._status(
                    self.tr(
                        "対象が変更されました。{action} #{n} は {repo} の base '{base}' に存在しますが、現在のタスクへは関連付けません。"
                    ).format(
                        action=action,
                        n=number,
                        repo=repo_at_create,
                        base=base,
                    )
                )
                return
            source = "created_in_hub"
            self.pull_request_created.emit(
                {"number": number, "repo": repo_at_create, "source": source}
            )
            self._created_pr_number = number
            self._created_pr_was_existing = existing is not None
            self._linked_number = number
            if existing is not None:
                self._status(
                    self.tr("同じ head / base の既存 Pull Request #{n} を選択します。").format(
                        n=number
                    )
                )
            else:
                self.create_title_edit.clear()
                self.create_body_edit.clear()
                self._clear_creation_metadata_fields()
                self.load_default_template()
                self._status(self.tr("Pull Request #{n} を作成しました。").format(n=number))
            if existing is None and self._has_metadata_values(metadata):
                self._apply_post_create_metadata(repo_at_create, number, metadata)
            elif self._repo == repo_at_create:
                self._refresh_pull_requests_after_mutation()

        def _failed(message: str) -> None:
            self._set_create_enabled(True)
            self._show_error(message)

        self._run(_task, _done, _failed)

    def retry_pull_request_metadata(self) -> None:
        pending = dict(self._pending_pr_metadata or {})
        if not pending:
            return
        repo = str(pending.pop("repo", ""))
        number = pending.pop("pr_number", None)
        if not repo or number is None:
            return
        self.retry_metadata_button.setEnabled(False)
        self._run(
            partial(
                github_service.apply_pull_request_metadata,
                repo,
                number,
                **pending,
            ),
            lambda result: self._on_post_create_metadata(number, repo, result),
            lambda _message: self._on_post_create_metadata(
                number,
                repo,
                {
                    "warnings": [{"kind": "post_create_unknown"}],
                    "retry": None,
                },
            ),
        )

    def set_console_source(
        self, provider: Optional[Callable[[], str]], run_id: str = ""
    ) -> None:
        """コンソール出力の取得元を設定する（FR-GUI-33）。"""
        self._console_provider = provider
        self._console_run_id = (run_id or "").strip()
        self._update_console_button_state()

    def select_pull_request(self, number: int) -> bool:
        """取得済み一覧から番号一致の PR を選択する（FR-GUI-32）。

        一覧の再取得は行わない。該当が無ければ選択を変えずに False を返す。
        """
        for row, pull in enumerate(self._visible):
            if pull.get("number") == number:
                self._suppress_selection_signal = True
                try:
                    self.pr_list.setCurrentRow(row)
                finally:
                    self._suppress_selection_signal = False
                return True
        return False

    def set_linked_pull_request(self, number: Optional[int]) -> None:
        """関連付けた PR を選択する（FR-GUI-32）。

        一覧は非同期に到着するため、未取得なら取得完了後に適用する。
        """
        self._linked_number = number or None
        self._apply_linked_selection()

    def _apply_linked_selection(self) -> None:
        if self._linked_number is None:
            return
        if self.select_pull_request(self._linked_number):
            self._linked_number = None

    def load_once(self) -> None:
        """リポジトリ確定時の初期取得（FR-GUI-31）。"""
        if not self._repo or self._loaded_repo == self._repo:
            return
        self._loaded_repo = self._repo
        self.refresh_pull_requests()

    def refresh_pull_requests(self) -> None:
        """PR 一覧を再取得する（利用者の明示操作のみ）。"""
        if self._merge_request_token is not None:
            return
        if self._review_submit_token is not None:
            if self._repo:
                self._pending_pull_request_refresh = (
                    self._repo,
                    self.state_combo.currentData() or "open",
                )
            return
        if self._list_request_in_flight:
            return
        if not self._require_repo():
            return
        self._request_pull_requests(cursor=None, append=False)

    def _refresh_pull_requests_after_mutation(self) -> None:
        """作成・metadata 更新後の page 1 refresh を取りこぼさない。"""
        if not self._repo:
            return
        context = (self._repo, self.state_combo.currentData() or "open")
        if (
            self._list_request_in_flight
            or self._review_submit_token is not None
            or self._review_request_token is not None
        ):
            self._pending_pull_request_refresh = context
            return
        self.refresh_pull_requests()

    def load_more_pull_requests(self) -> None:
        """利用者の明示操作で次の PR ページを取得する（FR-GUI-48）。"""
        if (
            self._merge_request_token is not None
            or self._review_submit_token is not None
            or self._list_request_in_flight
            or not self._pull_requests_have_more
        ):
            return
        if not self._require_repo():
            return
        cursor = self._next_pull_request_cursor
        if not cursor:
            return
        self._request_pull_requests(
            cursor=cursor,
            append=True,
        )

    def refresh_pull_request_reviews(self) -> None:
        """選択中 Pull Request の review 一覧を明示的に再取得する。"""
        context = self._current_review_context()
        if (
            self._merge_request_token is not None
            or context is None
            or self._review_request_token is not None
            or self._review_submit_token is not None
            or self._list_request_in_flight
        ):
            return
        self._request_pull_request_reviews(*context)

    def refresh_check_runs(self) -> None:
        """選択中 Pull Request の head に対する check-runs を明示取得する。"""
        context = self._current_merge_context()
        if (
            context is None
            or self._check_runs_request_token is not None
            or self._merge_request_token is not None
            or self._list_request_in_flight
        ):
            self._update_merge_controls()
            return

        repo, number, _generation, head_sha, _head_ref, _base_ref = context
        token = object()
        self._check_runs_request_token = token
        self._check_runs = None
        self._check_runs_context = None
        self.check_run_list.clear()
        self._update_merge_controls()
        self._status(
            self.tr("Pull Request #{n} の check-runs を取得中...").format(
                n=number
            )
        )

        def _done(result: Any) -> None:
            if self._check_runs_request_token is not token:
                return
            self._check_runs_request_token = None
            if not self._is_merge_context(context):
                self._update_merge_controls()
                return
            rows = self._normalize_check_runs(result)
            if rows is None:
                self._check_runs = None
                self._check_runs_context = None
                self.check_run_list.clear()
                self._update_merge_controls()
                self._show_error(
                    self.tr("check-runs の応答を解釈できませんでした。")
                )
                return
            self._check_runs = rows
            self._check_runs_context = context
            self.check_run_list.clear()
            for row in rows:
                conclusion = row.get("conclusion")
                self.check_run_list.addItem(
                    f"{row['name']}  status={row['status']}  "
                    f"conclusion={conclusion if conclusion is not None else '-'}"
                )
            self._update_merge_controls()
            self._status(
                self.tr("Pull Request #{n} の check-runs を取得しました。").format(
                    n=number
                )
            )

        def _failed(message: str) -> None:
            if self._check_runs_request_token is not token:
                return
            self._check_runs_request_token = None
            if self._is_merge_context(context):
                self._check_runs = None
                self._check_runs_context = None
                self.check_run_list.clear()
                self._show_error(message)
            self._update_merge_controls()

        self._run(
            partial(github_service.list_check_runs, repo, head_sha),
            _done,
            _failed,
        )

    def merge_current_pull_request(self) -> None:
        """check-runs が成功した選択中 Pull Request を確認後にマージする。"""
        context = self._current_merge_context()
        method = self.merge_method_combo.currentData()
        if (
            context is None
            or not isinstance(method, str)
            or method not in _MERGE_METHODS
            or not self._merge_is_ready(context)
            or self._merge_request_token is not None
        ):
            self._update_merge_controls()
            self._show_error(
                self.merge_guidance_label.text()
                or self.tr("Pull Request を安全にマージできる状態ではありません。")
            )
            return

        repo, number, _generation, head_sha, head_ref, base_ref = context
        if not self._confirm_merge_pull_request(
            number,
            head_ref,
            base_ref,
            method,
        ):
            return
        if not self._is_merge_context(context) or not self._merge_is_ready(context):
            self._update_merge_controls()
            self._show_error(
                self.tr(
                    "確認中に Pull Request の対象または head が変更されたため、"
                    "マージを送信しませんでした。"
                )
            )
            return

        token = object()
        self._merge_request_token = token
        self._update_review_controls()
        self._update_merge_controls()
        self._update_review_comment_controls()
        self._status(
            self.tr(
                "{repo} の Pull Request #{n} を {method} でマージ中..."
            ).format(repo=repo, n=number, method=method)
        )

        def _done(result: Any) -> None:
            if self._merge_request_token is not token:
                return
            self._merge_request_token = None
            current_context = self._is_merge_context(context)
            if not self._is_confirmed_merge_result(result):
                self._clear_check_runs_context()
                self._update_review_controls()
                self._update_merge_controls()
                self._update_review_comment_controls()
                self._show_error(
                    self.tr(
                        "{repo} の Pull Request #{n} のマージ結果を解釈できませんでした。"
                    ).format(repo=repo, n=number)
                )
                return
            if current_context and self._current is not None:
                updated = dict(self._current)
                updated["merged"] = True
                updated["state"] = "closed"
                self._current = updated
                self.meta_label.setText(self._format_meta(updated))
                self._update_branch_button_state()
            self._update_review_controls()
            self._update_merge_controls()
            self._update_review_comment_controls()
            self._status(
                self.tr(
                    "{repo} の Pull Request #{n} を {method} でマージしました。"
                ).format(repo=repo, n=number, method=method)
            )

        def _failed(message: str) -> None:
            if self._merge_request_token is not token:
                return
            self._merge_request_token = None
            self._clear_check_runs_context()
            self._update_review_controls()
            self._update_merge_controls()
            self._update_review_comment_controls()
            self._show_error(
                self.tr(
                    "{repo} の Pull Request #{n} のマージに失敗しました: {message}"
                ).format(repo=repo, n=number, message=message)
            )

        self._run(
            partial(
                github_service.merge_pull_request,
                repo,
                number,
                method,
                sha=head_sha,
            ),
            _done,
            _failed,
        )

    def open_review_comment_dialog(self) -> None:
        """取得済み patch と head SHA を固定して行コメント Dialog を開く。"""
        if (
            self._merge_request_token is not None
            or self._review_submit_token is not None
        ):
            return
        context = self._review_comment_launch_context()
        if context is None:
            self._update_review_comment_controls()
            self._show_error(
                self.review_comment_hint_label.text()
                or self.tr("差分行へのレビューコメントを開始できません。")
            )
            return
        repo, number, commit_id, files = context
        try:
            dialog = GitHubReviewCommentDialog(
                repo,
                number,
                commit_id,
                files,
                self,
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return
        try:
            result = dialog.exec()
        finally:
            shutdown = getattr(dialog, "shutdown", None)
            if callable(shutdown):
                shutdown()
        if result == QDialog.DialogCode.Accepted:
            self._status(
                self.tr(
                    "{repo} の Pull Request #{n} へレビューコメントを投稿しました。"
                ).format(repo=repo, n=number)
            )

    def submit_review(self) -> None:
        """選択中 Pull Request へ review を提出する（FR-GUI-45）。"""
        if (
            self._merge_request_token is not None
            or self._review_submit_token is not None
            or self._list_request_in_flight
        ):
            return
        context = self._current_review_context()
        if context is None or not self._require_repo():
            return
        try:
            event, body = validate_pull_request_review(
                self.review_event_combo.currentData(),
                self.review_body_edit.text(),
            )
        except ReviewValidationError as exc:
            self._show_error(exc.user_message)
            return
        if self._review_request_token is not None:
            return

        repo_at_request, number, generation = context
        token = object()
        self._review_submit_token = token
        self._update_review_controls()
        self._status(
            self.tr("Pull Request #{n} のレビューを提出中...").format(n=number)
        )

        def _done(result: Any) -> None:
            if self._review_submit_token is not token:
                return
            self._review_submit_token = None
            current_context = self._is_review_context(
                repo_at_request, number, generation
            )
            self._update_review_controls()
            if not self._is_review_submit_result(result):
                self._show_error(
                    self.tr(
                        "{repo} の Pull Request #{n} へのレビュー提出結果を解釈できませんでした。"
                    ).format(repo=repo_at_request, n=number)
                )
                self._start_pending_pull_request_refresh_if_ready()
                return
            if not current_context:
                self._status(
                    self.tr(
                        "{repo} の Pull Request #{n} へレビューを提出しました。"
                        "現在の表示対象が変更されたため、一覧は更新していません。"
                    ).format(repo=repo_at_request, n=number)
                )
                self._start_pending_pull_request_refresh_if_ready()
                return
            self.review_body_edit.clear()
            self._status(
                self.tr(
                    "{repo} の Pull Request #{n} へレビューを提出しました。"
                    "レビュー一覧を更新中..."
                ).format(repo=repo_at_request, n=number)
            )
            self._request_pull_request_reviews(
                repo_at_request,
                number,
                generation,
                submitted=True,
            )
            self._start_pending_pull_request_refresh_if_ready()

        def _failed(message: str) -> None:
            if self._review_submit_token is not token:
                return
            self._review_submit_token = None
            self._update_review_controls()
            self._show_error(
                self.tr(
                    "{repo} の Pull Request #{n} へのレビュー提出に失敗しました: {message}"
                ).format(repo=repo_at_request, n=number, message=message)
            )
            self._start_pending_pull_request_refresh_if_ready()

        self._run(
            partial(
                github_service.create_pull_request_review,
                repo_at_request,
                number,
                event,
                body,
            ),
            _done,
            _failed,
        )

    def post_comment(self) -> None:
        """会話コメントを投稿する。"""
        if (
            self._merge_request_token is not None
            or self._review_submit_token is not None
            or self._current is None
            or not self._require_repo()
        ):
            return
        body = self.new_comment_edit.text()
        if not body.strip():
            self._show_error(self.tr("コメント本文を入力してください。"))
            return
        number = self._current["number"]

        def _done(_result: Any) -> None:
            self.new_comment_edit.clear()
            self._status(self.tr("コメントを投稿しました。"))
            self._load_comments(number)

        self._run(partial(github_service.post_comment, self._repo, number, body), _done)

    def post_console_log(self) -> None:
        """作業状況画面のコンソール出力を選択中 PR へ投稿する（FR-GUI-33）。"""
        if (
            self._merge_request_token is not None
            or self._review_submit_token is not None
            or self._current is None
            or not self._require_repo()
        ):
            return
        if self._console_provider is None:
            self._show_error(self.tr("コンソール出力の取得元が設定されていません。"))
            return
        raw = self._console_provider() or ""
        if not raw.strip():
            self._show_error(self.tr("投稿できるコンソール出力がありません。"))
            return
        number = self._current["number"]
        body = format_console_log_comment(raw, run_id=self._console_run_id or None)

        def _done(_result: Any) -> None:
            self._status(self.tr("コンソール出力を PR #{n} へ投稿しました。").format(n=number))
            self._load_comments(number)

        self._run(partial(github_service.post_comment, self._repo, number, body), _done)

    def push_current_branch(self) -> None:
        """現在のローカルブランチを origin へ push する（FR-GUI-34）。"""
        if (
            self._merge_request_token is not None
            or self._review_submit_token is not None
        ):
            return
        self._status(self.tr("現在のブランチを push 中..."))
        self._run(
            partial(git_ops.push_current_branch, self._repo_root),
            lambda branch: self._status(
                self.tr("ブランチ '{b}' を push しました。").format(b=branch)
            ),
        )

    def delete_head_branch(self) -> None:
        """選択中 PR の head ブランチをリモートから削除する（FR-GUI-34）。"""
        if (
            self._merge_request_token is not None
            or self._review_submit_token is not None
            or self._current is None
            or not self._require_repo()
        ):
            return
        if not self._is_branch_deletable(self._current):
            self._show_error(
                self.tr("マージ済みまたはクローズ済みの PR だけが削除対象です。")
            )
            return
        if not self._is_own_head_repo(self._current):
            self._show_error(
                self.tr("head が別リポジトリ（fork）の PR は削除対象外です。")
            )
            return
        branch = self._head_ref(self._current)
        if not branch:
            self._show_error(self.tr("head ブランチを特定できません。"))
            return
        if not self._confirm_delete_branch(branch):
            return

        def _done(_result: Any) -> None:
            self._status(
                self.tr("ブランチ '{b}' を origin から削除しました。").format(b=branch)
            )
            # 削除済み ref への再実行は 404 になるため、この場で閉じる。
            self.delete_branch_button.setEnabled(False)

        self._run(partial(github_service.delete_branch, self._repo, branch), _done)

    def _confirm_delete_branch(self, branch: str) -> bool:
        """リモートブランチ削除の確認を取る（FR-GUI-34）。"""
        answer = QMessageBox.question(
            self,
            self.tr("head ブランチの削除"),
            self.tr("origin のブランチ '{b}' を削除します。よろしいですか？").format(b=branch),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """実行中のワーカーの終了を待つ（ウィンドウを閉じるときに呼ぶ）。"""
        for worker in list(self._workers):
            worker.wait(timeout_ms)
        self._workers.clear()

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _request_pull_requests(
        self,
        *,
        cursor: Optional[str],
        append: bool,
    ) -> None:
        if append and (not isinstance(cursor, str) or not cursor):
            self._show_error(self.tr("Pull Request 一覧の継続 cursor が不正です。"))
            return
        if not append:
            self._next_pull_request_cursor = None
            self._pull_request_cursor_history.clear()
            self._pull_requests_have_more = False
        repo_at_request = self._repo
        state_at_request = self.state_combo.currentData() or "open"
        self._list_request_serial += 1
        request_token = self._list_request_serial
        self._active_list_request_token = request_token
        self._list_request_in_flight = True
        self._update_review_controls()
        self._status(
            self.tr("Pull Request をさらに取得中...")
            if append
            else self.tr("Pull Request 一覧を取得中...")
        )

        def _done(pulls: Any) -> None:
            if request_token != self._active_list_request_token:
                return
            if not self._is_pull_request_list_context(
                repo_at_request, state_at_request
            ):
                self._finish_pull_request_list_request(request_token)
                return
            if not isinstance(pulls, list) or any(
                not isinstance(pull, dict)
                or self._pull_request_number(pull) is None
                for pull in pulls
            ):
                self._show_error(
                    self.tr("Pull Request 一覧の応答を解釈できませんでした。")
                )
                self._finish_pull_request_list_request(request_token)
                return
            next_cursor = getattr(pulls, "next_url", None)
            if next_cursor is not None and (
                not isinstance(next_cursor, str) or not next_cursor
            ):
                self._show_error(
                    self.tr("Pull Request 一覧の継続 cursor を解釈できませんでした。")
                )
                self._finish_pull_request_list_request(request_token)
                return
            cursor_history = set(self._pull_request_cursor_history)
            if append and cursor is not None:
                cursor_history.add(cursor)
            if next_cursor is not None and next_cursor in cursor_history:
                self._show_error(
                    self.tr("Pull Request 一覧の継続 cursor に循環を検出しました。")
                )
                self._finish_pull_request_list_request(request_token)
                return
            page_items = list(pulls)
            self._pull_request_cursor_history = cursor_history
            self._next_pull_request_cursor = next_cursor
            self._pull_requests_have_more = next_cursor is not None
            self._on_pull_requests_loaded(page_items, append=append)
            self._finish_pull_request_list_request(request_token)

        def _failed(message: str) -> None:
            if request_token != self._active_list_request_token:
                return
            stale = not self._is_pull_request_list_context(
                repo_at_request, state_at_request
            )
            if not stale:
                self._show_error(message)
            self._finish_pull_request_list_request(request_token)

        list_options: dict[str, Any] = {
            "state": state_at_request,
            "per_page": _PULL_REQUESTS_PER_PAGE,
        }
        if append and cursor is not None:
            list_options["cursor"] = cursor
        self._run(
            partial(
                github_service.list_pull_requests,
                repo_at_request,
                **list_options,
            ),
            _done,
            _failed,
        )

    def _on_pull_request_list_context_changed(self, *_args: Any) -> None:
        self._invalidate_pull_request_list_context()

    def _invalidate_pull_request_list_context(self) -> None:
        self._list_request_serial += 1
        self._active_list_request_token = None
        self._list_request_in_flight = False
        self._next_pull_request_cursor = None
        self._pull_request_cursor_history.clear()
        self._pull_requests_have_more = False
        self._pending_pull_request_refresh = None
        self._update_review_controls()

    def _is_pull_request_list_context(self, repo: str, state: str) -> bool:
        return self._repo == repo and (self.state_combo.currentData() or "open") == state

    def _finish_pull_request_list_request(self, request_token: int) -> None:
        if request_token != self._active_list_request_token:
            return
        self._active_list_request_token = None
        self._list_request_in_flight = False
        self._update_review_controls()
        self._start_pending_pull_request_refresh_if_ready()

    def _start_pending_pull_request_refresh_if_ready(self) -> None:
        pending = self._pending_pull_request_refresh
        if (
            pending is None
            or self._list_request_in_flight
            or self._review_submit_token is not None
            or self._review_request_token is not None
        ):
            return
        self._pending_pull_request_refresh = None
        if self._is_pull_request_list_context(*pending):
            self.refresh_pull_requests()

    def _update_pull_request_list_controls(self) -> None:
        submit_busy = (
            self._review_submit_token is not None
            or self._merge_request_token is not None
        )
        self.pr_list.setEnabled(not submit_busy)
        self.filter_edit.setEnabled(not submit_busy)
        self.state_combo.setEnabled(not submit_busy)
        self.refresh_button.setEnabled(
            not submit_busy and not self._list_request_in_flight
        )
        self.load_more_button.setEnabled(
            not submit_busy
            and not self._list_request_in_flight
            and self._pull_requests_have_more
        )

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

    def _invalidate_create_preflight(self, *_args: Any) -> None:
        self._create_preflight = None

    def _apply_create_preflight(self, result: Any) -> None:
        if not isinstance(result, dict) or not isinstance(
            result.get("local"), git_ops.PullRequestPreflight
        ):
            self._show_error(self.tr("作成前チェック結果を取得できませんでした。"))
            return
        local = result["local"]
        compare_value = result.get("compare")
        compare: Dict[str, Any] = (
            compare_value if isinstance(compare_value, dict) else {}
        )
        self._create_preflight = local
        repository = result.get("repository")
        self._default_branch = (
            str(repository.get("default_branch") or "")
            if isinstance(repository, dict)
            else ""
        )
        self.create_head_label.setText(local.head_branch)
        self.create_compare_label.setText(
            self.tr(
                "{head} → {base}: commits {commits}, files {files}, "
                "remote ahead {remote_ahead}, remote behind {remote_behind}, "
                "published {published}, unpushed {unpushed}"
            ).format(
                head=local.head_branch,
                base=local.base_branch,
                commits=local.ahead_commits,
                files=local.changed_files,
                remote_ahead=compare.get("ahead_by", "-"),
                remote_behind=compare.get("behind_by", "-"),
                published="yes" if local.published else "no",
                unpushed=local.unpushed_commits,
            )
        )
        existing = result.get("existing")
        if isinstance(existing, dict) and existing.get("number"):
            self._status(
                self.tr("同じ head / base の open Pull Request #{n} が存在します。").format(
                    n=existing["number"]
                )
            )
        elif local.ready:
            self._status(self.tr("Pull Request を作成できます。"))
        else:
            self._status(self.tr("作成前に現在の branch を明示的に push してください。"))

    @staticmethod
    def _require_matching_repo(
        local: git_ops.PullRequestPreflight, target_repo: str
    ) -> None:
        if not local.origin_repo or local.origin_repo.casefold() != target_repo.casefold():
            raise git_ops.GitOpsError(
                "現在の checkout の origin と対象 GitHub repository が一致しません。"
            )

    @staticmethod
    def _require_remote_compare(compare: Any) -> None:
        ahead = compare.get("ahead_by") if isinstance(compare, dict) else None
        if isinstance(ahead, bool) or not isinstance(ahead, int):
            raise git_ops.GitOpsError("GitHub の compare 結果を確認できませんでした。")
        if ahead <= 0:
            raise git_ops.GitOpsError(
                "GitHub 上の base branch に対する新しい commit がありません。"
            )

    def _set_create_enabled(self, enabled: bool) -> None:
        for widget in (
            self.create_base_edit,
            self.create_title_edit,
            self.create_body_edit,
            self.create_issue_edit,
            self.create_close_issue_checkbox,
            self.create_draft_checkbox,
            self.create_labels_edit,
            self.create_assignees_edit,
            self.create_milestone_edit,
            self.create_reviewers_edit,
            self.create_team_reviewers_edit,
            self.create_preflight_button,
            self.generate_title_button,
            self.load_template_button,
            self.create_pull_request_button,
        ):
            widget.setEnabled(enabled)

    @staticmethod
    def _csv_values(text: str) -> List[str]:
        return list(dict.fromkeys(value.strip() for value in text.split(",") if value.strip()))

    def _creation_metadata_values(self) -> dict[str, Any]:
        milestone_text = self.create_milestone_edit.text().strip()
        return {
            "labels": self._csv_values(self.create_labels_edit.text()),
            "assignees": self._csv_values(self.create_assignees_edit.text()),
            "milestone": int(milestone_text) if milestone_text.isdigit() else None,
            "reviewers": self._csv_values(self.create_reviewers_edit.text()),
            "team_reviewers": self._csv_values(
                self.create_team_reviewers_edit.text()
            ),
        }

    @staticmethod
    def _has_metadata_values(metadata: dict[str, Any]) -> bool:
        return any(value for value in metadata.values())

    def _clear_creation_metadata_fields(self) -> None:
        for edit in (
            self.create_labels_edit,
            self.create_assignees_edit,
            self.create_milestone_edit,
            self.create_reviewers_edit,
            self.create_team_reviewers_edit,
        ):
            edit.clear()

    def _clear_pending_metadata(self) -> None:
        self._pending_pr_metadata = None
        self.retry_metadata_button.setEnabled(False)

    def _set_created_pr_url(self, number: int, url: str) -> None:
        self._created_pr_url = (url or "").strip()
        if self._created_pr_url:
            safe_url = escape(self._created_pr_url, quote=True)
            self.created_pr_url_label.setText(
                f'<a href="{safe_url}">{escape(self._created_pr_url)}</a>'
            )
        else:
            self.created_pr_url_label.setText(
                self.tr("Pull Request #{n} が作成されました。").format(n=number)
            )

    def _apply_post_create_metadata(
        self, repo: str, number: int, metadata: dict[str, Any]
    ) -> None:
        self._run(
            partial(
                github_service.apply_pull_request_metadata,
                repo,
                number,
                **metadata,
            ),
            lambda result: self._on_post_create_metadata(number, repo, result),
            lambda _message: self._on_post_create_metadata(
                number,
                repo,
                {
                    "warnings": [{"kind": "post_create_unknown"}],
                    "retry": None,
                },
            ),
        )

    def _on_post_create_metadata(self, number: int, repo: str, result: Any) -> None:
        warnings = result.get("warnings", []) if isinstance(result, dict) else []
        retry = result.get("retry") if isinstance(result, dict) else None
        self._pending_pr_metadata = (
            {"repo": repo, **retry} if isinstance(retry, dict) else None
        )
        self.retry_metadata_button.setEnabled(self._pending_pr_metadata is not None)
        warning_kinds = {
            item.get("kind") for item in warnings if isinstance(item, dict)
        }
        messages: List[str] = []
        if "metadata" in warning_kinds:
            messages.append(self.tr("ラベル・担当者・マイルストーン"))
        if "reviewers" in warning_kinds:
            messages.append(self.tr("レビュアー"))
        if "post_create_unknown" in warning_kinds:
            messages.append(self.tr("分類できない後処理エラー（安全のため再試行不可）"))
        if messages:
            message = self.tr(
                "Pull Request #{n} は作成済みですが、次の後処理に失敗しました: {items}"
            ).format(n=number, items=", ".join(messages))
        else:
            message = self.tr(
                "Pull Request #{n} の metadata を反映しました。"
            ).format(
                n=number
            )
        self._post_create_metadata_message = message
        self._status(message)
        if self._repo == repo:
            self._refresh_pull_requests_after_mutation()
        else:
            self._post_create_metadata_message = ""

    @staticmethod
    def _with_related_issue(
        body: str,
        issue_number: Optional[int],
        *,
        close_issue: bool,
        base_branch: str,
        default_branch: str,
    ) -> str:
        if issue_number is None:
            return body
        reference = (
            f"Closes #{issue_number}"
            if close_issue and default_branch and base_branch == default_branch
            else f"#{issue_number}"
        )
        return f"{reference}\n\n{body}".rstrip()

    def _on_pull_requests_loaded(self, pulls: Any, *, append: bool = False) -> None:
        page_items = [pull for pull in list(pulls or []) if isinstance(pull, dict)]
        combined = [*self._pulls, *page_items] if append else page_items
        self._pulls = self._deduplicate_pull_requests(combined)
        self._apply_list_filter(
            preserve_selection=append or self._has_review_draft()
        )
        if self._pulls:
            self._status(
                self.tr("{n} 件の Pull Request を取得しました。").format(n=len(self._pulls))
            )
        elif (self.state_combo.currentData() or "open") == "open":
            self._status(
                self.tr(
                    "オープンな Pull Request は 0 件です。「状態」を「すべて」にして [更新] すると"
                    "クローズ済みの Pull Request も表示されます。"
                )
            )
        else:
            self._status(self.tr("対象の Pull Request は 0 件です。"))
        self._apply_linked_selection()
        created_number = self._created_pr_number
        if not append and created_number is not None:
            found = self.select_pull_request(created_number)
            if found and self._created_pr_was_existing:
                self._status(
                    self.tr("同じ head / base の既存 Pull Request #{n} を選択しました。").format(
                        n=created_number
                    )
                )
            elif found:
                self._status(
                    self.tr("Pull Request #{n} を一覧から選択しました。").format(
                        n=created_number
                    )
                )
            elif self._created_pr_was_existing:
                self._status(
                    self.tr(
                        "同じ head / base の既存 Pull Request #{n} が存在します。現在の一覧には表示されていません。"
                    ).format(n=created_number)
                )
            else:
                self._status(
                    self.tr(
                        "Pull Request #{n} を作成しました。現在の一覧には表示されていません。"
                    ).format(n=created_number)
                )
            self._created_pr_number = None
            self._created_pr_was_existing = False
        if not append and self._post_create_metadata_message:
            self._status(self._post_create_metadata_message)
            self._post_create_metadata_message = ""

    @staticmethod
    def _deduplicate_pull_requests(pulls: List[dict]) -> List[dict]:
        unique: List[dict] = []
        seen_numbers: set[Any] = set()
        for pull in pulls:
            number = pull.get("number")
            if number is not None and number in seen_numbers:
                continue
            if number is not None:
                seen_numbers.add(number)
            unique.append(pull)
        return unique

    def _apply_list_filter(
        self,
        *_args: Any,
        preserve_selection: Optional[bool] = None,
    ) -> None:
        """取得済み一覧を絞り込み、残る選択と review draft を保持する。"""
        if preserve_selection is None:
            preserve_selection = bool(_args)
        had_current = self._current is not None
        selected_number: Optional[int] = None
        if preserve_selection:
            selected_row = self.pr_list.currentRow()
            if 0 <= selected_row < len(self._visible):
                selected_number = self._pull_request_number(self._visible[selected_row])
            if selected_number is None and self._current is not None:
                selected_number = self._pull_request_number(self._current)

        keyword = self.filter_edit.text().strip().lower()
        self._visible = [
            pr for pr in self._pulls if not keyword or keyword in self._pr_label(pr).lower()
        ]
        restored_row = -1
        previous_signal_state = self.pr_list.blockSignals(True)
        try:
            self.pr_list.clear()
            for row, pr in enumerate(self._visible):
                self.pr_list.addItem(self._pr_label(pr))
                if self._pull_request_number(pr) == selected_number:
                    restored_row = row
            if restored_row >= 0:
                self.pr_list.setCurrentRow(restored_row)
        finally:
            self.pr_list.blockSignals(previous_signal_state)

        if (selected_number is not None and restored_row < 0) or (
            not preserve_selection and had_current
        ):
            self._invalidate_pull_request_detail_context(clear_reviews=True)

    def _has_review_draft(self) -> bool:
        return bool(self.review_body_edit.text()) or (
            self.review_event_combo.currentData() != ALLOWED_EVENTS[0]
        )

    @staticmethod
    def _pr_label(pr: Dict[str, Any]) -> str:
        return f"#{pr.get('number')} {pr.get('title', '')}"

    @staticmethod
    def _pull_request_number(pr: Dict[str, Any]) -> Optional[int]:
        value = pr.get("number")
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return None
        try:
            number = int(value)
        except ValueError:
            return None
        return number if number > 0 else None

    def _on_pull_request_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._visible):
            self._invalidate_pull_request_detail_context(clear_reviews=True)
            self._current = None
            self._set_detail_enabled(False)
            return
        # 明示選択は保留中の関連付けを消費する（後続の更新で設定値へ引き戻さない）。
        number = self._pull_request_number(self._visible[row])
        if number is None:
            self._invalidate_pull_request_detail_context(clear_reviews=True)
            self._current = None
            self._set_detail_enabled(False)
            self._show_error(self.tr("Pull Request の選択対象を解釈できませんでした。"))
            return
        self._current = None
        self._set_detail_enabled(False)
        if not self._suppress_selection_signal:
            self._linked_number = None
            self.pull_request_selected.emit(number)
        self._load_pull_request(number)

    def _load_pull_request(self, number: int) -> None:
        self._invalidate_pull_request_detail_context(clear_reviews=True)
        generation = self._pull_request_load_generation
        repo_at_request = self._repo

        def _done(pr: Any) -> None:
            if (
                generation != self._pull_request_load_generation
                or self._repo != repo_at_request
            ):
                return
            self._on_pull_request_loaded(
                pr,
                repo_at_request=repo_at_request,
                number_at_request=number,
                generation=generation,
            )

        def _failed(message: str) -> None:
            if (
                generation != self._pull_request_load_generation
                or self._repo != repo_at_request
            ):
                return
            self._show_error(message)

        self._run(
            partial(github_service.get_pull_request, repo_at_request, number),
            _done,
            _failed,
        )

    def _on_pull_request_loaded(
        self,
        pr: Any,
        *,
        repo_at_request: Optional[str] = None,
        number_at_request: Optional[int] = None,
        generation: Optional[int] = None,
    ) -> None:
        if not isinstance(pr, dict):
            self._show_error(self.tr("Pull Request の詳細を取得できませんでした。"))
            return
        number = self._pull_request_number(pr)
        if number is None:
            self._show_error(self.tr("Pull Request の詳細を解釈できませんでした。"))
            return
        if number_at_request is not None and number != number_at_request:
            self._show_error(self.tr("Pull Request の取得対象と応答が一致しませんでした。"))
            return
        self._current_files = None
        self._current_files_head_sha = ""
        self._clear_check_runs_context()
        self._current = pr
        self._current_pull_request_generation = generation
        self.meta_label.setText(self._format_meta(pr))
        url = str(pr.get("html_url") or "")
        # API 由来の文字列を rich text へ直接埋め込まない
        self.url_label.setText(
            f'<a href="{escape(url, quote=True)}">{escape(url)}</a>' if url else ""
        )
        self.body_view.setPlainText(str(pr.get("body") or ""))
        self._set_detail_enabled(True)
        self._load_files(number)
        self._load_comments(number)
        if repo_at_request is not None and generation is not None:
            self._request_pull_request_reviews(
                repo_at_request,
                number,
                generation,
            )

    def _load_files(self, number: int) -> None:
        context = self._current_review_context()
        if context is None or context[1] != number:
            return
        repo, _, generation = context
        self._current_files = None
        self._current_files_head_sha = ""
        self.file_list.clear()
        self._update_review_comment_controls()

        def _done(files: Any) -> None:
            if self._is_review_context(repo, number, generation):
                self._on_files_loaded(files)

        def _failed(message: str) -> None:
            if self._is_review_context(repo, number, generation):
                self._current_files = None
                self._current_files_head_sha = ""
                self._update_review_comment_controls()
                self._show_error(message)

        self._run(
            partial(github_service.list_pull_request_files, repo, number),
            _done,
            _failed,
        )

    def _on_files_loaded(self, files: Any) -> None:
        self.file_list.clear()
        if not isinstance(files, list) or any(
            not isinstance(entry, dict) for entry in files
        ):
            self._current_files = None
            self._current_files_head_sha = ""
            self._update_review_comment_controls()
            self._show_error(
                self.tr("変更ファイル一覧の応答を解釈できませんでした。")
            )
            return
        snapshot_value = getattr(files, "head_sha", None)
        snapshot_head_sha = (
            snapshot_value.strip()
            if isinstance(snapshot_value, str)
            else ""
        )
        self._current_files = [dict(entry) for entry in files]
        self._current_files_head_sha = snapshot_head_sha
        for entry in self._current_files:
            self.file_list.addItem(
                f"{entry.get('filename', '')}  [{entry.get('status', '')}]"
            )
        self._update_review_comment_controls()

    def _load_comments(self, number: int) -> None:
        context = self._current_review_context()
        if context is None or context[1] != number:
            return
        repo, _, generation = context

        def _done(comments: Any) -> None:
            if self._is_review_context(repo, number, generation):
                self._on_comments_loaded(comments)

        def _failed(message: str) -> None:
            if self._is_review_context(repo, number, generation):
                self._show_error(message)

        self._run(
            partial(github_service.list_comments, repo, number),
            _done,
            _failed,
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

    def _request_pull_request_reviews(
        self,
        repo: str,
        number: int,
        generation: int,
        *,
        submitted: bool = False,
    ) -> None:
        if self._review_request_token is not None:
            return
        if not self._is_review_context(repo, number, generation):
            return
        token = object()
        self._review_request_token = token
        self._update_review_controls()

        def _done(result: Any) -> None:
            if self._review_request_token is not token:
                return
            self._review_request_token = None
            if not self._is_review_context(repo, number, generation):
                self._update_review_controls()
                self._start_pending_pull_request_refresh_if_ready()
                return
            rows = self._normalize_review_rows(result)
            if rows is None:
                self._update_review_controls()
                if submitted:
                    self._show_error(
                        self.tr(
                            "{repo} の Pull Request #{n} へレビューは提出済みですが、"
                            "一覧の更新に失敗しました（応答を解釈できません）。"
                        ).format(repo=repo, n=number)
                    )
                else:
                    self._show_error(
                        self.tr("レビュー一覧の応答を解釈できませんでした。")
                    )
                self._start_pending_pull_request_refresh_if_ready()
                return
            self.review_list.clear()
            for row in rows:
                self.review_list.addItem(row)
            self._update_review_controls()
            if submitted:
                self._status(
                    self.tr(
                        "{repo} の Pull Request #{n} へレビューを提出し、"
                        "一覧を更新しました。"
                    ).format(repo=repo, n=number)
                )
            self._start_pending_pull_request_refresh_if_ready()

        def _failed(message: str) -> None:
            if self._review_request_token is not token:
                return
            self._review_request_token = None
            if not self._is_review_context(repo, number, generation):
                self._update_review_controls()
                self._start_pending_pull_request_refresh_if_ready()
                return
            self._update_review_controls()
            if submitted:
                self._show_error(
                    self.tr(
                        "{repo} の Pull Request #{n} へレビューは提出済みですが、"
                        "一覧の更新に失敗しました: {message}"
                    ).format(repo=repo, n=number, message=message)
                )
            else:
                self._show_error(message)
            self._start_pending_pull_request_refresh_if_ready()

        self._run(
            partial(github_service.list_pull_request_reviews, repo, number),
            _done,
            _failed,
        )

    @staticmethod
    def _normalize_review_rows(reviews: Any) -> Optional[List[str]]:
        if not isinstance(reviews, list):
            return None
        rows: List[str] = []
        for review in reviews:
            if not isinstance(review, dict):
                return None
            user = review.get("user")
            login = user.get("login") if isinstance(user, dict) else None
            state = review.get("state")
            if not isinstance(login, str) or not login.strip():
                return None
            if not isinstance(state, str) or not state.strip():
                return None
            if "submitted_at" not in review or "body" not in review:
                return None
            submitted_at = review.get("submitted_at")
            body = review.get("body")
            if submitted_at is not None and not isinstance(submitted_at, str):
                return None
            if body is not None and not isinstance(body, str):
                return None
            first_line = (body or "").splitlines()[:1]
            rows.append(
                f"{login} {state} {submitted_at or ''}  "
                f"{first_line[0] if first_line else ''}"
            )
        return rows

    @staticmethod
    def _is_review_submit_result(result: Any) -> bool:
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
    def _normalize_check_runs(check_runs: Any) -> Optional[List[dict[str, Any]]]:
        if not isinstance(check_runs, list):
            return None
        normalized: List[dict[str, Any]] = []
        for check_run in check_runs:
            if not isinstance(check_run, dict):
                return None
            name = check_run.get("name")
            status = check_run.get("status")
            if "conclusion" not in check_run:
                return None
            conclusion = check_run.get("conclusion")
            if not isinstance(name, str) or not name.strip():
                return None
            if not isinstance(status, str) or not status.strip():
                return None
            if conclusion is not None and (
                not isinstance(conclusion, str) or not conclusion.strip()
            ):
                return None
            normalized.append(
                {
                    "name": name,
                    "status": status,
                    "conclusion": conclusion,
                }
            )
        return normalized

    def _current_merge_context(
        self,
    ) -> Optional[tuple[str, int, int, str, str, str]]:
        review_context = self._current_review_context()
        if review_context is None or self._current is None:
            return None
        repo, number, generation = review_context
        head_sha = self._head_sha(self._current)
        head_ref = self._head_ref(self._current)
        base = self._current.get("base")
        base_ref = (
            str(base.get("ref") or "").strip()
            if isinstance(base, dict)
            else ""
        )
        if not head_sha or not head_ref or not base_ref:
            return None
        return repo, number, generation, head_sha, head_ref, base_ref

    def _is_merge_context(
        self,
        context: tuple[str, int, int, str, str, str],
    ) -> bool:
        return self._current_merge_context() == context

    def _merge_is_ready(
        self,
        context: tuple[str, int, int, str, str, str],
    ) -> bool:
        if (
            not self._is_merge_context(context)
            or self._check_runs is None
            or self._check_runs_context != context
            or self._check_runs_request_token is not None
            or self._merge_request_token is not None
            or self._review_submit_token is not None
            or self._list_request_in_flight
            or self._current is None
            or self._current.get("merged") is True
            or str(self._current.get("state") or "") != "open"
            or self._current.get("draft") is True
        ):
            return False
        return all(
            check_run.get("status") == "completed"
            and check_run.get("conclusion") in _SUCCESSFUL_CHECK_CONCLUSIONS
            for check_run in self._check_runs
        )

    @staticmethod
    def _is_confirmed_merge_result(result: Any) -> bool:
        return isinstance(result, dict) and result.get("merged") is True

    def _confirm_merge_pull_request(
        self,
        number: int,
        head_ref: str,
        base_ref: str,
        method: str,
    ) -> bool:
        answer = QMessageBox.question(
            self,
            self.tr("Pull Request のマージ"),
            self.tr(
                "次の Pull Request を同期マージします。\n"
                "Pull Request: #{number}\n"
                "head: {head}\n"
                "base: {base}\n"
                "merge method: {method}\n\n"
                "よろしいですか？"
            ).format(
                number=number,
                head=head_ref,
                base=base_ref,
                method=method,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _clear_check_runs_context(self) -> None:
        self._check_runs_request_token = None
        self._check_runs = None
        self._check_runs_context = None
        self.check_run_list.clear()

    def _update_merge_controls(self) -> None:
        review_context = self._current_review_context()
        context = self._current_merge_context()
        request_busy = self._check_runs_request_token is not None
        merge_busy = self._merge_request_token is not None
        other_busy = self._review_submit_token is not None or self._list_request_in_flight

        self.check_run_list.setEnabled(review_context is not None and not merge_busy)
        self.refresh_check_runs_button.setEnabled(
            context is not None
            and not request_busy
            and not merge_busy
            and not other_busy
        )
        self.merge_method_combo.setEnabled(context is not None and not merge_busy)

        if review_context is None:
            message = self.tr("Pull Request の詳細を選択してください。")
        elif context is None:
            message = self.tr(
                "Pull Request の head SHA または head / base branch を確認できません。"
            )
        elif self._current is not None and self._current.get("merged") is True:
            message = self.tr("この Pull Request はマージ済みです。")
        elif self._current is not None and self._current.get("draft") is True:
            message = self.tr("Draft Pull Request はマージできません。")
        elif request_busy:
            message = self.tr("check-runs を取得中です。")
        elif merge_busy:
            message = self.tr("Pull Request をマージ中です。")
        elif self._check_runs is None:
            message = self.tr(
                "[check-runs を更新] で head commit の状態を取得してください。"
            )
        elif self._check_runs_context != context:
            message = self.tr(
                "Pull Request の head が check-runs 取得後に変更されました。"
                "再度 check-runs を取得してください。"
            )
        elif not self._merge_is_ready(context):
            message = self.tr(
                "未完了または成功扱いでない check-run があるためマージできません。"
            )
        else:
            message = self.tr(
                "check-runs は完了しています。merge method を確認してください。"
            )

        self.merge_guidance_label.setText(message)
        self.merge_button.setEnabled(
            context is not None and self._merge_is_ready(context)
        )

    def _current_review_context(self) -> Optional[tuple[str, int, int]]:
        generation = self._current_pull_request_generation
        if self._current is None or generation is None:
            return None
        number = self._pull_request_number(self._current)
        if number is None:
            return None
        if not self._is_review_context(self._repo, number, generation):
            return None
        return self._repo, number, generation

    def _is_review_context(self, repo: str, number: int, generation: int) -> bool:
        if (
            self._repo != repo
            or self._current is None
            or self._pull_request_load_generation != generation
            or self._current_pull_request_generation != generation
        ):
            return False
        return self._pull_request_number(self._current) == number

    def _invalidate_pull_request_detail_context(
        self, *, clear_reviews: bool
    ) -> None:
        self._pull_request_load_generation += 1
        self._current_pull_request_generation = None
        self._current = None
        self._current_files = None
        self._current_files_head_sha = ""
        self._clear_check_runs_context()
        self._invalidate_review_context(clear_reviews=clear_reviews)
        self.meta_label.clear()
        self.url_label.clear()
        self.body_view.clear()
        self.file_list.clear()
        self.comment_list.clear()
        self.new_comment_edit.clear()
        self._set_detail_enabled(False)

    def _invalidate_review_context(self, *, clear_reviews: bool) -> None:
        self._review_request_token = None
        if clear_reviews:
            self.review_list.clear()
        self.review_body_edit.clear()
        approve_index = self.review_event_combo.findData(ALLOWED_EVENTS[0])
        if approve_index >= 0:
            self.review_event_combo.setCurrentIndex(approve_index)
        self._update_review_controls()

    def _update_review_controls(self) -> None:
        ready = self._current_review_context() is not None
        request_busy = self._review_request_token is not None
        submit_busy = (
            self._review_submit_token is not None
            or self._merge_request_token is not None
        )
        list_busy = self._list_request_in_flight
        self.review_event_combo.setEnabled(ready and not submit_busy and not list_busy)
        self.review_body_edit.setEnabled(ready and not submit_busy and not list_busy)
        self.refresh_reviews_button.setEnabled(
            ready and not request_busy and not submit_busy and not list_busy
        )
        self.submit_review_button.setEnabled(
            ready and not request_busy and not submit_busy and not list_busy
        )
        detail_mutation_enabled = (
            ready
            and self._merge_request_token is None
            and self._review_submit_token is None
        )
        self.new_comment_edit.setEnabled(detail_mutation_enabled)
        self.post_comment_button.setEnabled(detail_mutation_enabled)
        self._update_pull_request_list_controls()
        self._update_merge_controls()
        self._update_review_comment_controls()
        self._update_console_button_state()
        self._update_branch_button_state()

    def _review_comment_launch_context(
        self,
    ) -> Optional[tuple[str, int, str, List[dict[str, Any]]]]:
        context = self._current_review_context()
        if context is None:
            return None
        repo, number, _generation = context
        current_head_sha = self._head_sha(self._current or {})
        commit_id = self._current_files_head_sha
        if (
            not current_head_sha
            or not commit_id
            or commit_id != current_head_sha
            or self._current_files is None
        ):
            return None
        files = [dict(entry) for entry in self._current_files]
        if not build_commentable_files(files):
            return None
        return repo, number, commit_id, files

    def _update_review_comment_controls(self) -> None:
        context = self._current_review_context()
        if self._merge_request_token is not None:
            enabled = False
            message = self.tr("Pull Request のマージ中は起動できません。")
        elif self._review_submit_token is not None:
            enabled = False
            message = self.tr("Pull Request のレビュー提出中は起動できません。")
        elif context is None:
            enabled = False
            message = self.tr("Pull Request の詳細を選択してください。")
        elif not self._head_sha(self._current or {}):
            enabled = False
            message = self.tr(
                "Pull Request の head SHA を取得できないため起動できません。"
            )
        elif self._current_files is None:
            enabled = False
            message = self.tr(
                "変更ファイルを取得してからレビューコメントを開始してください。"
            )
        elif not self._current_files_head_sha:
            enabled = False
            message = self.tr(
                "変更ファイルの head SHA を確認できないため起動できません。"
            )
        elif self._current_files_head_sha != self._head_sha(self._current or {}):
            enabled = False
            message = self.tr(
                "Pull Request の head SHA と変更ファイルの取得時点が一致しません。"
                "詳細を更新してから再試行してください。"
            )
        else:
            commentable = build_commentable_files(self._current_files)
            enabled = bool(commentable)
            if enabled:
                line_count = sum(len(entry.lines) for entry in commentable)
                message = self.tr(
                    "patch を持つ {files} ファイル、{lines} 行へ投稿できます。"
                ).format(files=len(commentable), lines=line_count)
            else:
                message = self.tr(
                    "取得済み変更ファイルに、座標を確定できる patch がありません。"
                )
        self.review_comment_button.setEnabled(enabled)
        self.review_comment_hint_label.setText(message)

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
        parts = [
            f"#{pr.get('number')}",
            f"state: {state}",
            f"author: {author_login}",
            f"{_ref('head')} → {_ref('base')}",
        ]
        for key, field, label in (
            ("labels", "name", "labels"),
            ("assignees", "login", "assignees"),
            ("requested_reviewers", "login", "reviewers"),
            ("requested_teams", "slug", "teams"),
        ):
            values = pr.get(key)
            names = (
                [str(item.get(field)) for item in values if isinstance(item, dict) and item.get(field)]
                if isinstance(values, list)
                else []
            )
            if names:
                parts.append(f"{label}: {', '.join(names)}")
        milestone = pr.get("milestone")
        if isinstance(milestone, dict) and milestone.get("title"):
            parts.append(f"milestone: {milestone['title']}")
        return " | ".join(parts)

    def _set_detail_enabled(self, enabled: bool) -> None:
        for widget in (
            self.body_view,
            self.file_list,
            self.check_run_list,
            self.comment_list,
            self.review_list,
            self.new_comment_edit,
            self.post_comment_button,
        ):
            widget.setEnabled(enabled)
        self._update_review_controls()
        self._update_review_comment_controls()
        self._update_console_button_state()
        self._update_branch_button_state()

    def _update_console_button_state(self) -> None:
        self.post_console_button.setEnabled(
            self._merge_request_token is None
            and self._review_submit_token is None
            and self._current is not None
            and self._console_provider is not None
        )

    def _update_branch_button_state(self) -> None:
        self.delete_branch_button.setEnabled(
            self._merge_request_token is None
            and self._review_submit_token is None
            and self._current is not None
            and self._is_branch_deletable(self._current)
            and bool(self._head_ref(self._current))
            and self._is_own_head_repo(self._current)
        )
        self.push_button.setEnabled(
            self._merge_request_token is None
            and self._review_submit_token is None
        )

    def _is_own_head_repo(self, pr: Dict[str, Any]) -> bool:
        """head が対象リポジトリ自身のブランチか（FR-GUI-34: origin のブランチに限る）。

        fork 由来の PR で同名ブランチを origin から誤削除しないため、
        head のリポジトリを特定できない場合も削除不可とする。
        """
        head = pr.get("head")
        repo = head.get("repo") if isinstance(head, dict) else None
        if not isinstance(repo, dict):
            return False
        return str(repo.get("full_name") or "") == self._repo

    @staticmethod
    def _is_branch_deletable(pr: Dict[str, Any]) -> bool:
        """FR-GUI-34: merged または closed の PR だけを削除対象とする。"""
        return bool(pr.get("merged")) or str(pr.get("state") or "") in _DELETABLE_STATES

    @staticmethod
    def _head_ref(pr: Dict[str, Any]) -> str:
        head = pr.get("head")
        return str(head.get("ref") or "") if isinstance(head, dict) else ""

    @staticmethod
    def _head_sha(pr: Dict[str, Any]) -> str:
        head = pr.get("head")
        value = head.get("sha") if isinstance(head, dict) else None
        return value.strip() if isinstance(value, str) else ""
