"""hve.gui.github_picker_dialog — 実行タスクへ関連付ける Issue / PR の選択（FR-GUI-32）。

一覧の取得は `github_service` へ委譲し、`GitHubWorker` 経由で GUI スレッド外で実行する。
選択結果は番号だけを返し、設定画面の入力欄へ反映する。
"""

from __future__ import annotations

from functools import partial
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import github_service
from .github_threads import GitHubWorker

__all__ = ["GitHubPickerDialog"]

_ISSUE = "issue"
_PULL_REQUEST = "pr"


class GitHubPickerDialog(QDialog):
    """Issue または Pull Request を一覧から 1 件選ぶダイアログ。"""

    def __init__(
        self, repo: str, kind: str = _ISSUE, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._repo = (repo or "").strip()
        self._kind = kind if kind in (_ISSUE, _PULL_REQUEST) else _ISSUE
        self._items: List[dict] = []
        self._visible: List[dict] = []
        self._workers: List[GitHubWorker] = []

        self.setWindowTitle(
            self.tr("Issue を選択")
            if self._kind == _ISSUE
            else self.tr("Pull Request を選択")
        )
        self.resize(560, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

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
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.tr("番号・タイトルで絞り込み"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        self.item_list = QListWidget()
        self.item_list.itemDoubleClicked.connect(lambda _i: self.accept())
        layout.addWidget(self.item_list, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("hveRole", "description")
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.refresh()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """一覧を取得する。"""
        if not self._repo:
            self.status_label.setText(
                self.tr("リポジトリ (owner/repo) を先に指定してください。")
            )
            return
        state = self.state_combo.currentData() or "open"
        fetch = (
            github_service.list_issues
            if self._kind == _ISSUE
            else github_service.list_pull_requests
        )
        self.status_label.setText(self.tr("一覧を取得中..."))
        self._run(partial(fetch, self._repo, state=state), self._on_loaded)

    def selected_number(self) -> Optional[int]:
        """選択中の番号。未選択なら ``None``。"""
        row = self.item_list.currentRow()
        if 0 <= row < len(self._visible):
            return int(self._visible[row]["number"])
        return None

    def shutdown(self, timeout_ms: int = 5000) -> None:
        for worker in list(self._workers):
            worker.wait(timeout_ms)
        self._workers.clear()

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _run(self, task, on_ok) -> None:
        worker = GitHubWorker(task)
        worker.succeeded.connect(on_ok)
        worker.failed.connect(self.status_label.setText)
        worker.finished.connect(self._on_worker_finished)
        self._workers.append(worker)  # GC 防止
        worker.start()

    def _on_worker_finished(self) -> None:
        worker = self.sender()
        if isinstance(worker, GitHubWorker) and worker in self._workers:
            self._workers.remove(worker)

    def _on_loaded(self, items: Any) -> None:
        self._items = [i for i in (items or []) if isinstance(i, dict) and "number" in i]
        self._apply_filter()
        if self._items:
            self.status_label.setText(
                self.tr("{n} 件を取得しました。").format(n=len(self._items))
            )
        elif (self.state_combo.currentData() or "open") == "open":
            self.status_label.setText(
                self.tr("オープンな対象は 0 件です。「状態」を「すべて」にして [更新] してください。")
            )
        else:
            self.status_label.setText(self.tr("対象は 0 件です。"))

    def _apply_filter(self, *_args: Any) -> None:
        keyword = self.filter_edit.text().strip().lower()
        self._visible = [
            item
            for item in self._items
            if not keyword or keyword in self._label(item).lower()
        ]
        self.item_list.clear()
        for item in self._visible:
            self.item_list.addItem(self._label(item))

    @staticmethod
    def _label(item: Dict[str, Any]) -> str:
        return f"#{item.get('number')} {item.get('title', '')}"
