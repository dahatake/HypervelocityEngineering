"""hve.gui.github_window — GitHub 連携設定 / Issue / Pull Request の単一 Hub。

FR-GUI-35: GitHub 関連の設定画面は 1 か所とし、本 Hub だけが可視 owner となる。
FR-GUI-26 / FR-GUI-27 の 2 パネルと、既存の C5「GitHub」設定ウィジェットを
タブでまとめ、対象リポジトリを共有する。`SettingsWindow` と同じく非モーダルの
`QMainWindow` として開く。リポジトリ確定時に一覧を 1 回だけ取得する（FR-GUI-31）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QLabel,
    QGroupBox,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import github_service
from .github_issue_panel import GitHubIssuePanel
from .github_pr_panel import GitHubPullRequestPanel

__all__ = ["GitHubWindow"]


class GitHubWindow(QMainWindow):
    """GitHub 連携設定 / Issue / Pull Request を扱う非モーダル Hub。"""

    # 連携設定を保存したことを通知する（既存の settings_changed と同じ契約）。
    settings_changed = Signal(object)
    task_context_changed = Signal(object)

    def __init__(
        self, repo_root: Optional[Path] = None, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("GitHub"))
        self.resize(1100, 800)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self._task_context = None
        layout.addWidget(self._build_task_context_card())

        # FR-GUI-35: 設定入力は既存の C5 ウィジェットを再利用し、複製しない。
        from .page_options import _C5IssuePR

        self.settings_section = _C5IssuePR()
        self.issue_panel = GitHubIssuePanel()
        self.pr_panel = GitHubPullRequestPanel()
        self.pr_panel.set_repository_root(repo_root or Path.cwd())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._wrap_scrollable(self.settings_section), self.tr("連携設定"))
        self.tabs.addTab(self.issue_panel, self.tr("Issue"))
        self.tabs.addTab(self.pr_panel, self.tr("Pull Request"))
        layout.addWidget(self.tabs, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("hveRole", "description")
        layout.addWidget(self.status_label)

        self._wire_settings_section()
        self.issue_panel.issue_selected.connect(
            lambda number: self.task_context_changed.emit(
                {"issue_number": number, "source": "manual"}
            )
        )
        self.issue_panel.issue_created.connect(
            lambda result: self.task_context_changed.emit(
                {
                    "issue_number": result.get("number"),
                    "repo": result.get("repo"),
                    "source": "created_in_hub",
                }
            )
        )
        self.pr_panel.pull_request_selected.connect(
            lambda number: self.task_context_changed.emit(
                {"pr_number": number, "source": "manual"}
            )
        )
        self.pr_panel.pull_request_created.connect(
            lambda result: self.task_context_changed.emit(
                {
                    "pr_number": result.get("number"),
                    "repo": result.get("repo"),
                    "source": result.get("source") or "created_in_hub",
                }
            )
        )
        self.settings_section.branch.editingFinished.connect(
            lambda: self.pr_panel.set_base_branch(self.settings_section.branch.text())
        )
        self.pr_panel.set_base_branch(self.settings_section.branch.text())
        self._resolve_initial_repo()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap_scrollable(widget: QWidget) -> QWidget:
        """設定セクションを縦スクロール可能な領域へ収める。"""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        return area

    def _build_task_context_card(self) -> QWidget:
        box = QGroupBox(self.tr("現在のタスク"))
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        self.task_context_label = QLabel(self.tr("関連付けなし"))
        self.task_context_label.setWordWrap(True)
        self.task_context_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.task_context_label)
        row = QHBoxLayout()
        self.unlink_issue_button = QPushButton(self.tr("Issue の関連付けを解除"))
        self.unlink_issue_button.clicked.connect(
            lambda: self.task_context_changed.emit({"clear_issue": True})
        )
        row.addWidget(self.unlink_issue_button)
        self.unlink_pr_button = QPushButton(self.tr("Pull Request の関連付けを解除"))
        self.unlink_pr_button.clicked.connect(
            lambda: self.task_context_changed.emit({"clear_pr": True})
        )
        row.addWidget(self.unlink_pr_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.unlink_issue_button.setEnabled(False)
        self.unlink_pr_button.setEnabled(False)
        return box

    def _wire_settings_section(self) -> None:
        """C5 設定の変更を保存し、リポジトリ確定を両パネルへ伝える。"""
        from . import settings_apply

        settings_apply.apply_to_widgets(
            {"C5": self.settings_section}, self._load_settings()
        )
        settings_apply.wire_autosave(
            {"C5": self.settings_section}, on_changed=self._persist_settings
        )
        self.settings_section.repo.editingFinished.connect(self.apply_repo)

    @staticmethod
    def _load_settings() -> dict:
        from . import settings_store

        try:
            return settings_store.load()
        except Exception:
            return {}

    def _persist_settings(self) -> None:
        """C5 の現在値を既存 store へ保存する（設定の所有者は 1 か所）。"""
        from . import settings_apply, settings_store

        try:
            values = settings_apply.collect_from_widgets({"C5": self.settings_section})
            for key, value in values.items():
                settings_store.set_option(key, value)
        except Exception as exc:  # 保存失敗で Hub を壊さない
            # 例外本文をそのまま出さず、例外型名だけを示す（NFR-SEC-01）。
            self.status_label.setText(
                self.tr("設定の保存に失敗しました（{reason}）。").format(
                    reason=type(exc).__name__
                )
            )
            return
        # 他面（Step 2 ウィジェット等）が古い値を使わないよう通知する。
        try:
            self.settings_changed.emit(None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def apply_repo(self) -> None:
        """入力されたリポジトリを両パネルへ反映する。"""
        try:
            repo = github_service.resolve_repo(self.settings_section.repo.text())
        except github_service.GitHubServiceError as exc:
            self.status_label.setText(str(exc))
            return
        self.settings_section.repo.setText(repo)
        self._set_repo(repo)
        self.status_label.setText(
            self.tr("対象リポジトリ: {repo}").format(repo=repo)
        )

    def set_console_source(
        self, provider: Optional[Callable[[], str]], run_id: str = ""
    ) -> None:
        """コンソール出力の取得元を PR パネルへ伝える（FR-GUI-33）。"""
        self.pr_panel.set_console_source(provider, run_id)

    def set_linked_pull_request(self, number: Optional[int]) -> None:
        """関連付けた Pull Request を PR パネルへ伝える（FR-GUI-32）。"""
        self.pr_panel.set_linked_pull_request(number)

    def set_task_context(self, context: Any) -> None:
        """現在の run-scoped GitHub task context を表示する（FR-GUI-40）。"""
        self._task_context = context
        if context is None:
            self.task_context_label.setText(self.tr("関連付けなし"))
            self.unlink_issue_button.setEnabled(False)
            self.unlink_pr_button.setEnabled(False)
            return
        key = context.key
        issue = f"#{context.issue_number}" if context.issue_number else "-"
        pull = f"#{context.pr_number}" if context.pr_number else "-"
        branch = context.head_branch or "-"
        base = context.base_branch or "-"
        self.task_context_label.setText(
            self.tr(
                "Run: {run} | Workflow: {workflow} | Instance: {instance}\n"
                "Repository: {repo} | Issue: {issue} | Pull Request: {pull} | "
                "Branch: {branch} → {base} | Source: {source}"
            ).format(
                run=key.session_run_id,
                workflow=key.workflow_id or "-",
                instance=key.instance_id or "-",
                repo=context.repo or "-",
                issue=issue,
                pull=pull,
                branch=branch,
                base=base,
                source=context.source,
            )
        )
        self.unlink_issue_button.setEnabled(context.issue_number is not None)
        self.unlink_pr_button.setEnabled(context.pr_number is not None)
        self.issue_panel.set_linked_issue(context.issue_number)
        self.pr_panel.set_task_target(context.repo, context.pr_number)
        self.pr_panel.set_linked_pull_request(context.pr_number)
        self.pr_panel.set_related_issue(context.issue_number)

    def task_context(self) -> Any:
        return self._task_context

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        """設定を保存し、実行中のワーカーの終了を待ってから閉じる。

        保存で予期しない例外が起きても worker の回収を必ず行う。
        """
        try:
            self._persist_settings()
        finally:
            self.issue_panel.shutdown()
            self.pr_panel.shutdown()
            super().closeEvent(event)

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _set_repo(self, repo: str) -> None:
        """両パネルへリポジトリを設定し、未取得なら 1 回だけ取得する（FR-GUI-31）。"""
        self.issue_panel.set_repo(repo)
        self.pr_panel.set_repo(repo)
        self.issue_panel.load_once()
        self.pr_panel.load_once()

    def _resolve_initial_repo(self) -> None:
        try:
            repo = github_service.resolve_repo(self.settings_section.repo.text() or None)
        except github_service.GitHubServiceError as exc:
            self.status_label.setText(str(exc))
            return
        self.settings_section.repo.setText(repo)
        self._set_repo(repo)
