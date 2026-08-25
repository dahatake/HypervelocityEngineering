"""hve.gui.github_window — GitHub Issue / Pull Request 用の独立ウィンドウ。

FR-GUI-26 / FR-GUI-27 の 2 パネルをタブでまとめ、対象リポジトリを共有する。
`SettingsWindow` と同じく非モーダルの `QMainWindow` として開く。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import github_service
from .github_issue_panel import GitHubIssuePanel
from .github_pr_panel import GitHubPullRequestPanel

__all__ = ["GitHubWindow"]


class GitHubWindow(QMainWindow):
    """Issue / Pull Request を閲覧・編集する非モーダルウィンドウ。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("GitHub Issue / Pull Request"))
        self.resize(1100, 800)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addLayout(self._build_repo_row())

        self.issue_panel = GitHubIssuePanel()
        self.pr_panel = GitHubPullRequestPanel()
        tabs = QTabWidget()
        tabs.addTab(self.issue_panel, "Issue")
        tabs.addTab(self.pr_panel, "Pull Request")
        layout.addWidget(tabs, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("hveRole", "description")
        layout.addWidget(self.status_label)

        self._resolve_initial_repo()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_repo_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(self.tr("リポジトリ")))
        self.repo_edit = QLineEdit()
        self.repo_edit.setPlaceholderText("owner/repo")
        self.repo_edit.returnPressed.connect(self.apply_repo)
        row.addWidget(self.repo_edit, stretch=1)
        self.apply_button = QPushButton(self.tr("適用"))
        self.apply_button.clicked.connect(self.apply_repo)
        row.addWidget(self.apply_button)
        return row

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def apply_repo(self) -> None:
        """入力されたリポジトリを両パネルへ反映する。"""
        try:
            repo = github_service.resolve_repo(self.repo_edit.text())
        except github_service.GitHubServiceError as exc:
            self.status_label.setText(str(exc))
            return
        self.repo_edit.setText(repo)
        self.issue_panel.set_repo(repo)
        self.pr_panel.set_repo(repo)
        self.status_label.setText(
            self.tr("対象リポジトリ: {repo}").format(repo=repo)
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        """実行中のワーカーの終了を待ってから閉じる。"""
        self.issue_panel.shutdown()
        self.pr_panel.shutdown()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _resolve_initial_repo(self) -> None:
        try:
            repo = github_service.resolve_repo(None)
        except github_service.GitHubServiceError as exc:
            self.status_label.setText(str(exc))
            return
        self.repo_edit.setText(repo)
        self.issue_panel.set_repo(repo)
        self.pr_panel.set_repo(repo)
