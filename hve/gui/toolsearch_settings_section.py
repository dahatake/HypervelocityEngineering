"""hve.gui.toolsearch_settings_section — 設定画面の Tool-Search セクション（FR-GUI-07）。

3 タブ構成:

- **基本**: `tool_search` / `tool_search_ranking`。この 2 つの入力欄は本セクションが単独で
  所有する（Step 1 右ペインと二重に持たない。FR-MAINT-07）。
- **ポリシー**: `hve/toolsearch/policy.json` の現在値を **読み取り専用**で表示する。
  編集はファイルの直接編集に委ねる（policy.json が単一の情報源）。
- **統計情報**: FR-TS-09 で収集したイベントを FR-TS-10 のダッシュボードで描画する。
  集計・整形は `hve.toolsearch.dashboard` / `stats` が所有し、ここでは再実装しない。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..toolsearch.dashboard import build_dashboard, render_html, render_text
from ..toolsearch.stats import default_events_path
from ..toolsearch.usage import default_usage_path
from .page_options import _LabeledField

_MONOSPACE_POINT_SIZE = 9


def _monospace(widget: QPlainTextEdit) -> None:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(_MONOSPACE_POINT_SIZE)
    widget.setFont(font)


class ToolSearchSection(QWidget):
    """Tool Search の設定・ポリシー・統計をまとめたセクション。"""

    def __init__(self, *, repo_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._repo_root = Path(repo_root)

        self.tool_search = QCheckBox(self.tr("SDK のツール定義遅延ロードを有効にする"))
        self.tool_search_ranking = QComboBox()
        self.tool_search_ranking.setEditable(False)
        self.tool_search_ranking.addItem(self.tr("SDK 組み込みのまま"), userData="sdk")
        self.tool_search_ranking.addItem(self.tr("HVE 実装へ差し替え"), userData="hve")

        self.policy_view = QPlainTextEdit()
        self.policy_view.setReadOnly(True)
        _monospace(self.policy_view)
        self.policy_path_label = QLabel("")
        self.policy_path_label.setWordWrap(True)

        self.stats_view = QPlainTextEdit()
        self.stats_view.setReadOnly(True)
        self.stats_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.stats_view.setMinimumHeight(320)
        _monospace(self.stats_view)
        self.paths_label = QLabel("")
        self.paths_label.setWordWrap(True)
        self.stats_result_label = QLabel("")
        self.stats_result_label.setWordWrap(True)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_basic_tab(), self.tr("基本"))
        self._tabs.addTab(self._build_policy_tab(), self.tr("ポリシー"))
        self._tabs.addTab(self._build_stats_tab(), self.tr("統計情報"))
        self._tabs.currentChanged.connect(self._on_tab_changed)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addWidget(self._tabs)

        self.reload_policy()
        self._refresh_paths_label()

    # ------------------------------------------------------------------
    # タブ構築
    # ------------------------------------------------------------------

    def _build_basic_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        layout.addWidget(_LabeledField(
            title=self.tr("ツール定義の遅延ロード (tool_search)"),
            description=self.tr(
                "ON（既定）にすると Copilot SDK の tool_search を有効化し、ツール定義を"
                " 先読みせず必要になってから読み込ませます。OFF にすると SDK 既定挙動に戻ります。"
            ),
            input_widget=self.tool_search,
        ))
        layout.addWidget(_LabeledField(
            title=self.tr("ランキング実装 (tool_search_ranking)"),
            description=self.tr(
                "上の遅延ロードを有効にしたときの検索実装を選びます。"
                "「HVE 実装へ差し替え」は日本語対応の BM25、pin ポリシー、"
                " Skill のカタログ合流、および統計収集を使います。"
                " 上の設定が OFF のときはこの設定は何もしません。"
                " 生成する AI Agent 向けの Foundry Toolbox 設定（Step 1 右ペイン）とは別物です。"
            ),
            input_widget=self.tool_search_ranking,
        ))

        note = QLabel(self.tr(
            "統計は「ツール定義の遅延ロード」が ON かつランキングが「HVE 実装へ差し替え」の"
            " ときにだけ収集されます。Cloud Session 経路では差し替えも収集も行いません。"
            " 各指標の意味は users-guide/tool-search-dashboard.md を参照してください。"
        ))
        note.setWordWrap(True)
        note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(note)
        layout.addStretch(1)
        return tab

    def _build_policy_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel(self.tr("<b>検索ポリシー（読み取り専用）</b>")))
        desc = QLabel(self.tr(
            "pin・検索専用語彙・フィールド重み・Step 別モードの単一の情報源は policy.json です。"
            " GUI からは書き換えません。変更はファイルを直接編集してください。"
        ))
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addWidget(self.policy_path_label)
        layout.addWidget(self.policy_view, 1)

        button = QPushButton(self.tr("再読み込み"))
        button.clicked.connect(self.reload_policy)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        return tab

    def _build_stats_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel(self.tr("<b>Tool Search 利用統計</b>")))
        desc = QLabel(self.tr(
            "検索が実際に呼ばれているか、返した結果が使われているかを測定します。"
            " 算出できない指標は 0 で埋めず「データ不足」と表示します。"
            " 各指標の定義は users-guide/tool-search-dashboard.md を参照。"
        ))
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addWidget(self.paths_label)
        layout.addWidget(self.stats_view, 1)

        reload_button = QPushButton(self.tr("再集計"))
        reload_button.clicked.connect(self.reload_stats)
        export_button = QPushButton(self.tr("HTML で書き出す"))
        export_button.clicked.connect(self._on_export_clicked)
        clear_button = QPushButton(self.tr("収集済みイベントを削除"))
        clear_button.clicked.connect(self._on_clear_clicked)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        for button in (reload_button, export_button, clear_button):
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.stats_result_label)
        return tab

    # ------------------------------------------------------------------
    # ポリシー
    # ------------------------------------------------------------------

    def reload_policy(self) -> None:
        from ..toolsearch.policy import PolicyError, ToolSearchPolicy

        path = ToolSearchPolicy.default_path()
        self.policy_path_label.setText(self.tr("参照元: ") + str(path))
        try:
            policy = ToolSearchPolicy.load()
        except PolicyError as exc:
            # 推測した既定値を見せない（実際に効いている設定と食い違うため）。
            self.policy_view.setPlainText(
                self.tr("policy.json を読み込めません。\n\n対象: ") + f"{path}\n\n{exc}"
            )
            return
        self.policy_view.setPlainText(_format_policy(policy))

    # ------------------------------------------------------------------
    # 統計
    # ------------------------------------------------------------------

    def reload_stats(self) -> None:
        self._refresh_paths_label()
        try:
            snapshot = build_dashboard(
                events_path=self._events_path(), usage_path=self._usage_path()
            )
            self.stats_view.setPlainText(render_text(snapshot, width=110))
        except Exception as exc:  # 統計の失敗で設定画面を壊さない
            self.stats_view.setPlainText(self.tr("統計を読み込めません: ") + str(exc))

    def _events_path(self) -> Path:
        return default_events_path(repo_root=self._repo_root)

    def _usage_path(self) -> Path:
        return default_usage_path(repo_root=self._repo_root)

    def _refresh_paths_label(self) -> None:
        self.paths_label.setText(
            self.tr("イベント: ")
            + f"{self._events_path()}\n"
            + self.tr("利用履歴: ")
            + f"{self._usage_path()}"
        )

    def _on_tab_changed(self, index: int) -> None:
        # イベントログは無制限に伸びるので、設定画面を開いただけでは読まない。
        if index == self._tabs.count() - 1:
            self.reload_stats()

    def export_html(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        snapshot = build_dashboard(
            events_path=self._events_path(), usage_path=self._usage_path()
        )
        target.write_text(render_html(snapshot), encoding="utf-8")

    def clear_events(self) -> None:
        self._events_path().unlink(missing_ok=True)

    def _on_export_clicked(self) -> None:
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("ダッシュボードを HTML として保存"),
            str(self._repo_root / "work" / "toolsearch-dashboard.html"),
            "HTML (*.html)",
        )
        if not chosen:
            return
        try:
            self.export_html(chosen)
        except OSError as exc:
            self.stats_result_label.setText(self.tr("書き出しに失敗しました: ") + str(exc))
            return
        self.stats_result_label.setText(self.tr("書き出しました: ") + chosen)

    def _on_clear_clicked(self) -> None:
        events = default_events_path()
        answer = QMessageBox.question(
            self,
            self.tr("収集済みイベントの削除"),
            self.tr("次のファイルを削除します。元に戻せません。\n\n") + str(events),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.clear_events()
        except OSError as exc:
            self.stats_result_label.setText(self.tr("削除に失敗しました: ") + str(exc))
            return
        self.stats_result_label.setText(self.tr("収集済みイベントを削除しました。"))
        self.reload_stats()

    # ------------------------------------------------------------------
    # テスト用アクセサ
    # ------------------------------------------------------------------

    def tab_count(self) -> int:
        return self._tabs.count()

    def tab_labels(self) -> Tuple[str, ...]:
        return tuple(self._tabs.tabText(i) for i in range(self._tabs.count()))


def _format_policy(policy) -> str:
    """`ToolSearchPolicy` を人間が読める形へ整形する（値の解釈は行わない）。"""
    lines = [
        f"version    : {policy.version}",
        f"limit      : {policy.limit}  (max {policy.max_limit})",
        f"tau        : {policy.tau}",
        "",
        "field_weights",
    ]
    lines += [f"  {name:<24} {weight}" for name, weight in policy.field_weights.items()]
    lines += ["", f"pins ({len(policy.pins)})"]
    lines += [f"  {key:<48} {mode}" for key, mode in sorted(policy.pins.items())]
    lines += ["", f"additional_search_text ({len(policy.additional_search_text)})"]
    lines += [f"  {key}" for key in sorted(policy.additional_search_text)]
    lines += ["", f"step_overrides ({len(policy.step_overrides)})"]
    lines += [
        f"  {key:<24} {override}" for key, override in sorted(policy.step_overrides.items())
    ]
    return "\n".join(lines)


__all__ = ["ToolSearchSection"]
