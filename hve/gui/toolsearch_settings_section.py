"""hve.gui.toolsearch_settings_section — 設定画面の Tool-Search セクション（FR-GUI-07）。

4 タブ構成:

- **基本**: `tool_search` / `tool_search_ranking`。この 2 つの入力欄は本セクションが単独で
  所有する（Step 1 右ペインと二重に持たない。FR-MAINT-07）。
- **Skill Layer**: workflow / step に対する `workflow_defaults`、`required_skills`、
  `optional_skills` の閲覧専用サマリーを表示し、Core / Required / Optional / Extend の
  レイヤー分離を可視化する。実行時の強制は `runner.py` / `skill_resolver.py` が担う。
- **ポリシー**: `hve/toolsearch/policy.json` の現在値を表示し、`version` を除く各項目を
  編集して同じファイルへ保存する。保存は `ToolSearchPolicy.save()` に委ね、検証・未知キー
  保持・改行の扱いを GUI 側で再実装しない。項目の説明文は `help_content` が所有する。
- **統計情報**: FR-TS-09 で収集したイベントを FR-TS-10 のダッシュボードで描画する。
  集計・整形は `hve.toolsearch.dashboard` / `stats` が所有し、ここでは再実装しない。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Tuple

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..toolsearch.dashboard import build_dashboard, render_html, render_text
from ..toolsearch.stats import default_events_path
from ..toolsearch.usage import default_usage_path
from .help_popup import with_help
from .page_options import _LabeledField

_MONOSPACE_POINT_SIZE = 9

# `policy.json` の編集項目と画面上の見出し。ヒントのキーはここから導出するため、
# 項目を足せば説明の欠落が `policy_help_keys()` の検査で必ず露見する。
_POLICY_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("version", "書式バージョン (version)"),
    ("limit", "1 回の検索で返す既定件数 (limit)"),
    ("max_limit", "1 回の検索で返す上限件数 (max_limit)"),
    ("tau", "低スコア候補の打ち切り比率 (tau)"),
    ("field_weights", "検索スコアのフィールド重み (field_weights)"),
    ("pins", "常時公開 / 検索対象の指定 (pins)"),
    ("additional_search_text", "検索専用語彙 (additional_search_text)"),
    ("step_overrides", "Step 別の検索モード (step_overrides)"),
)

_PIN_MODES: Tuple[str, ...] = ("always", "auto", "never")
_STEP_MODES: Tuple[str, ...] = ("search", "pin_only")
_WEIGHT_FIELDS: Tuple[str, ...] = (
    "name",
    "additional_search_text",
    "description",
    "arg_terms",
)

# 小数入力欄の桁数。読み込んだ値を丸めない範囲で必要な分だけ広げる。
_MIN_DECIMALS = 2
_MAX_DECIMALS = 10

_SKILL_LAYER_FOOTER = (
    "",
    "Note: this panel is informational only. Execution-time requirement resolution is done",
    "in hve/skill_resolver.py and hve/runner.py; this panel does not change the runtime policy.",
)


def _monospace(widget: QPlainTextEdit) -> None:
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(_MONOSPACE_POINT_SIZE)
    widget.setFont(font)


def _set_without_rounding(box: QDoubleSpinBox, value: float) -> None:
    """入力欄の桁数で読み込んだ値を丸めないよう、必要な分だけ桁を広げてから入れる。"""
    decimals = len(f"{float(value):.{_MAX_DECIMALS}f}".rstrip("0").partition(".")[2])
    box.setDecimals(max(_MIN_DECIMALS, decimals))
    box.setValue(value)


class _ContextWorker(QThread):
    """コンテキスト実測を UI スレッド外で実行する（MCP 接続待ちで数秒ブロックするため）。"""

    finished_with = Signal(int, str, str)

    def __init__(self, runner: Callable[[], Tuple[int, str, str]], parent=None) -> None:
        super().__init__(parent)
        self._runner = runner

    def run(self) -> None:  # pragma: no cover - QThread の実行本体
        try:
            code, out, err = self._runner()
        except Exception as exc:  # 実測失敗で GUI を落とさない
            self.finished_with.emit(1, "", str(exc))
            return
        self.finished_with.emit(code, out, err)


class _KeyValueTable(QWidget):
    """`policy.json` の「キー → 値」表を編集する表ウィジェット。

    ``choices`` を渡すと値の列を選択式にする（渡さないと自由入力）。
    キーの書式検証は保存時に `ToolSearchPolicy` が行うため、ここでは行わない。
    """

    def __init__(
        self,
        key_header: str,
        value_header: str,
        *,
        choices: Tuple[str, ...] = (),
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._choices = choices

        self._table = QTableWidget(0, 2, self)
        self._table.setHorizontalHeaderLabels([key_header, value_header])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setMinimumHeight(150)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        add_button = QPushButton(self.tr("行を追加"))
        add_button.clicked.connect(self._on_add_clicked)
        remove_button = QPushButton(self.tr("選択行を削除"))
        remove_button.clicked.connect(self._on_remove_clicked)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        for button in (add_button, remove_button):
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._table)
        layout.addLayout(buttons)

    def set_rows(self, mapping: Mapping[str, str]) -> None:
        self._table.setRowCount(0)
        for key in sorted(mapping):
            self.add_row(key, mapping[key])

    def add_row(self, key: str = "", value: str = "") -> None:
        index = self._table.rowCount()
        self._table.insertRow(index)
        self._table.setItem(index, 0, QTableWidgetItem(key))
        if self._choices:
            combo = QComboBox()
            combo.addItems(self._choices)
            if value in self._choices:
                combo.setCurrentText(value)
            self._table.setCellWidget(index, 1, combo)
        else:
            self._table.setItem(index, 1, QTableWidgetItem(value))

    def rows(self) -> Dict[str, str]:
        """キーが空の行は落として「キー → 値」を返す。"""
        result: Dict[str, str] = {}
        for index in range(self._table.rowCount()):
            key_item = self._table.item(index, 0)
            key = key_item.text().strip() if key_item is not None else ""
            if not key:
                continue
            if self._choices:
                combo = self._table.cellWidget(index, 1)
                result[key] = combo.currentText() if combo is not None else self._choices[0]
            else:
                value_item = self._table.item(index, 1)
                result[key] = value_item.text().strip() if value_item is not None else ""
        return result

    def _on_add_clicked(self) -> None:
        self.add_row("", self._choices[0] if self._choices else "")

    def _on_remove_clicked(self) -> None:
        rows = sorted({index.row() for index in self._table.selectedIndexes()}, reverse=True)
        for index in rows:
            self._table.removeRow(index)


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

        self.skill_layer_view = QPlainTextEdit()
        self.skill_layer_view.setReadOnly(True)
        _monospace(self.skill_layer_view)

        self.policy_path_label = QLabel("")
        self.policy_path_label.setWordWrap(True)
        self.policy_result_label = QLabel("")
        self.policy_result_label.setWordWrap(True)
        self.policy_version_label = QLabel("")
        self.policy_limit = QSpinBox()
        self.policy_limit.setRange(1, 100)
        self.policy_max_limit = QSpinBox()
        self.policy_max_limit.setRange(1, 100)
        self.policy_tau = QDoubleSpinBox()
        self.policy_tau.setRange(0.0, 1.0)
        self.policy_tau.setDecimals(_MIN_DECIMALS)
        self.policy_tau.setSingleStep(0.05)
        self.policy_weights: Dict[str, QDoubleSpinBox] = {}
        for name in _WEIGHT_FIELDS:
            box = QDoubleSpinBox()
            box.setRange(0.0, 100.0)
            box.setDecimals(_MIN_DECIMALS)
            box.setSingleStep(0.1)
            self.policy_weights[name] = box
        self.policy_pins = _KeyValueTable(
            self.tr("ツール ID / ワイルドカード"), self.tr("モード"), choices=_PIN_MODES
        )
        self.policy_search_text = _KeyValueTable(
            self.tr("ツール ID / ワイルドカード"), self.tr("検索専用の語（空白区切り）")
        )
        self.policy_step_overrides = _KeyValueTable(
            self.tr("ワークフロー ID:Step ID"), self.tr("モード"), choices=_STEP_MODES
        )
        self._policy_loaded = False
        self._policy_version = 0

        self.stats_view = QPlainTextEdit()
        self.stats_view.setReadOnly(True)
        self.stats_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.stats_view.setMinimumHeight(320)
        _monospace(self.stats_view)
        self.paths_label = QLabel("")
        self.paths_label.setWordWrap(True)
        self.stats_diagnosis_label = QLabel("")
        self.stats_diagnosis_label.setWordWrap(True)
        self.stats_result_label = QLabel("")
        self.stats_result_label.setWordWrap(True)

        self.context_view = QPlainTextEdit()
        self.context_view.setReadOnly(True)
        self.context_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.context_view.setMinimumHeight(320)
        _monospace(self.context_view)
        self.context_result_label = QLabel("")
        self.context_result_label.setWordWrap(True)
        self._context_worker: Optional[_ContextWorker] = None

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._build_basic_tab(), self.tr("基本"))
        self._tabs.addTab(self._build_skill_layer_tab(), self.tr("Skill Layer"))
        self._tabs.addTab(self._build_policy_tab(), self.tr("ポリシー"))
        self._stats_tab_index = self._tabs.addTab(
            self._build_stats_tab(), self.tr("統計情報")
        )
        self._tabs.addTab(self._build_context_tab(), self.tr("コンテキスト内訳"))
        self._tabs.currentChanged.connect(self._on_tab_changed)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addWidget(self._tabs)

        self.reload_skill_layer()
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
                "ON（既定）にすると Copilot SDK の tool_search を有効化します。"
                " SDK 仕様では、ツール定義を先読みせず必要になってから読み込ませる設定です。"
                " OFF にすると当該引数を渡さず SDK 既定挙動に戻ります。"
                " ただし現行 CLI では遅延公開が発火しません（下の実測を参照）。"
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

        self.basic_note = QLabel(self.tr(
            "実測 (2026-08-13 / Copilot CLI 1.0.79 / SDK 1.0.7): この CLI では遅延公開が発火しません。"
            " 同一構成で比較すると、無効時と defer_threshold=1 指定時のツール定義トークンは 52,756 で完全に一致し、"
            " 全ツールの defer_loading は null、tool_search_tool もツール一覧に現れませんでした。"
            " したがって上の設定を ON にしてもコンテキストは減りません。\n"
            "「HVE 実装へ差し替え」は Skill をツールとして登録するため、遅延公開が効かない現状では"
            " ツール定義が 12,160 tokens 増えます（実測 47,115 → 59,275）。既定の「SDK 組み込みのまま」を推奨します。\n"
            "コンテキストを減らす目的では、公開する MCP サーバー自体を絞ってください。"
            " 現在の層別内訳は「コンテキスト内訳」タブで実測できます。\n"
            "統計は上の設定が ON かつランキングが「HVE 実装へ差し替え」のときにだけ収集されます。"
            " Cloud Session 経路では差し替えも収集も行いません。"
            " 各指標の意味は users-guide/tool-search-dashboard.md を参照してください。"
        ))
        self.basic_note.setWordWrap(True)
        self.basic_note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.basic_note)
        layout.addStretch(1)
        return tab

    def _build_skill_layer_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel(self.tr("<b>Skill Layer（読み取り専用）</b>")))
        self.skill_layer_note = QLabel(self.tr(
            "workflow_defaults / required_skills / optional_skills は Step ごとの読み取り専用要約です。"
            " 実際の強制は runner.py と skill_resolver.py が行い、この画面では表示のみを担います。"
            " Core / Extend は policy.json 上の分類であり、Extend が実際に遅延公開されるかは"
            " CLI 側の deferral 実装に依存します（実測では現行 CLI で発火していません）。"
        ))
        self.skill_layer_note.setWordWrap(True)
        layout.addWidget(self.skill_layer_note)
        layout.addWidget(self.skill_layer_view, 1)

        button = QPushButton(self.tr("再読み込み"))
        button.clicked.connect(self.reload_skill_layer)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        return tab

    def _build_policy_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel(self.tr("<b>検索ポリシー</b>")))
        desc = QLabel(self.tr(
            "pin・検索専用語彙・フィールド重み・Step 別モードの単一の情報源は policy.json です。"
            " ここでの編集は下の「保存」を押すまでファイルへ書き込みません"
            "（この画面の他の設定と違い自動保存されません）。"
            " 保存した内容は次に開始する Step 実行から反映されます。"
            " 各項目名の右にある「?」で意味と増減の影響を確認できます。"
        ))
        desc.setWordWrap(True)
        layout.addWidget(desc)
        self.policy_legend_label = QLabel(self.tr(
            "凡例: pins の always = 常時公開（検索させない）/ auto = 検索で発見させる /"
            " never = 検索結果へ返さない（索引から消すのは excluded_tools だけ）。"
            " limit = 1 回の検索で返す上限件数。tau = トップスコアに対する打ち切り比率"
            "（score >= tau * top_score だけを返す）。field_weights = BM25 のフィールド重み。"
            " 詳細は users-guide/tool-search.md を参照してください。"
        ))
        self.policy_legend_label.setWordWrap(True)
        layout.addWidget(self.policy_legend_label)
        layout.addWidget(self.policy_path_label)

        self._policy_editor = QWidget()
        editor = QVBoxLayout(self._policy_editor)
        editor.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.addRow(self._policy_label("version"), self.policy_version_label)
        form.addRow(self._policy_label("limit"), self.policy_limit)
        form.addRow(self._policy_label("max_limit"), self.policy_max_limit)
        form.addRow(self._policy_label("tau"), self.policy_tau)
        editor.addLayout(form)

        editor.addWidget(self._policy_label("field_weights"))
        weights = QFormLayout()
        for name in _WEIGHT_FIELDS:
            weights.addRow(QLabel(name), self.policy_weights[name])
        editor.addLayout(weights)

        for field, table in (
            ("pins", self.policy_pins),
            ("additional_search_text", self.policy_search_text),
            ("step_overrides", self.policy_step_overrides),
        ):
            editor.addWidget(self._policy_label(field))
            editor.addWidget(table)

        layout.addWidget(self._policy_editor)

        save_button = QPushButton(self.tr("保存"))
        save_button.clicked.connect(self.save_policy)
        reload_button = QPushButton(self.tr("再読み込み（編集を破棄）"))
        reload_button.clicked.connect(self.reload_policy)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        for button in (save_button, reload_button):
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.policy_result_label)
        return tab

    def _policy_label(self, field: str) -> QWidget:
        """項目名と「?」ヒントを並べたラベルを返す（説明文は help_content が所有）。"""
        title = dict(_POLICY_FIELDS)[field]
        return with_help(title, f"toolsearch.{field}", self)

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
        layout.addWidget(self.stats_diagnosis_label)
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

    def _build_context_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel(self.tr("<b>コンテキスト内訳の実測</b>")))
        desc = QLabel(self.tr(
            "Step 実行と同じ経路でセッションを張り、システムプロンプト・組み込みツール定義・"
            "MCP サーバーごとの実トークン数を取得します。"
            "プロンプトは送らないためモデル推論は発生しません。推定値は使いません。"
            " ボタンを押したときだけ実行します（MCP 接続待ちで数秒かかります）。"
        ))
        desc.setWordWrap(True)
        layout.addWidget(desc)
        pointer = QLabel(self.tr(
            "実測対象の MCP サーバーは「各サービス連携 > MCP / CLI 接続」で設定します。"
        ))
        pointer.setWordWrap(True)
        layout.addWidget(pointer)
        layout.addWidget(self.context_view, 1)

        self._context_button = QPushButton(self.tr("実測する"))
        self._context_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._context_button.clicked.connect(self.measure_context)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._context_button)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(self.context_result_label)
        return tab

    # ------------------------------------------------------------------
    # ポリシー
    # ------------------------------------------------------------------

    def reload_skill_layer(self) -> None:
        try:
            self.skill_layer_view.setPlainText(_format_skill_layer(self._repo_root))
        except Exception as exc:  # 表示専用で UI を壊さない
            self.skill_layer_view.setPlainText(
                self.tr("Skill Layer を読み込めません: ") + str(exc)
            )

    def reload_policy(self) -> None:
        from ..toolsearch.policy import PolicyError, ToolSearchPolicy

        path = ToolSearchPolicy.default_path(self._repo_root)
        self.policy_path_label.setText(self.tr("参照元 / 保存先: ") + str(path))
        try:
            policy = ToolSearchPolicy.load(repo_root=self._repo_root)
        except PolicyError as exc:
            # 推測した既定値を見せない（実際に効いている設定と食い違うため）。
            self._policy_loaded = False
            self._policy_editor.setVisible(False)
            self.policy_result_label.setText(
                self.tr("policy.json を読み込めません。\n\n対象: ") + f"{path}\n\n{exc}"
            )
            return

        self._policy_loaded = True
        self._policy_version = policy.version
        self._policy_editor.setVisible(True)
        self.policy_version_label.setText(str(policy.version))
        self.policy_limit.setValue(policy.limit)
        self.policy_max_limit.setValue(policy.max_limit)
        _set_without_rounding(self.policy_tau, policy.tau)
        for name, box in self.policy_weights.items():
            _set_without_rounding(box, float(policy.field_weights[name]))
        self.policy_pins.set_rows(dict(policy.pins))
        self.policy_search_text.set_rows(dict(policy.additional_search_text))
        self.policy_step_overrides.set_rows(
            {key: str(value.get("mode", "search")) for key, value in policy.step_overrides.items()}
        )
        self.policy_result_label.setText("")

    def save_policy(self) -> None:
        """検証を通った値だけを、表示したファイルへ書き戻す。"""
        from ..toolsearch.policy import PolicyError, ToolSearchPolicy

        if not self._policy_loaded:
            self.policy_result_label.setText(self.tr(
                "policy.json を読み込めていないため保存しません。"
                "既存の内容を空値で上書きしないよう、ファイルを直接修正してから再読み込みしてください。"
            ))
            return

        path = ToolSearchPolicy.default_path(self._repo_root)
        candidate = ToolSearchPolicy(
            version=self._policy_version,
            limit=self.policy_limit.value(),
            max_limit=self.policy_max_limit.value(),
            tau=self.policy_tau.value(),
            field_weights={name: box.value() for name, box in self.policy_weights.items()},
            pins=self.policy_pins.rows(),
            additional_search_text=self.policy_search_text.rows(),
            step_overrides={
                key: {"mode": mode} for key, mode in self.policy_step_overrides.rows().items()
            },
        )
        try:
            candidate.save(path)
        except PolicyError as exc:
            self.policy_result_label.setText(
                self.tr("保存しませんでした（ファイルは変更していません）: ") + str(exc)
            )
            return
        except OSError as exc:
            self.policy_result_label.setText(self.tr("保存に失敗しました: ") + str(exc))
            return
        self.policy_result_label.setText(
            self.tr("保存しました: ")
            + f"{path}\n"
            + self.tr("次に開始する Step 実行から反映されます（実行中のセッションは変わりません）。")
        )

    def policy_help_keys(self) -> Tuple[str, ...]:
        return tuple(f"toolsearch.{field}" for field, _ in _POLICY_FIELDS)

    # ------------------------------------------------------------------
    # 統計
    # ------------------------------------------------------------------

    def reload_stats(self) -> None:
        self._refresh_paths_label()
        self.stats_diagnosis_label.setText(self._collection_diagnosis())
        try:
            snapshot = build_dashboard(
                events_path=self._events_path(), usage_path=self._usage_path()
            )
            self.stats_view.setPlainText(render_text(snapshot, width=110))
        except Exception as exc:  # 統計の失敗で設定画面を壊さない
            self.stats_view.setPlainText(self.tr("統計を読み込めません: ") + str(exc))

    def _has_collected_events(self) -> bool:
        path = self._events_path()
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    def _collection_diagnosis(self) -> str:
        """イベントが 0 件のとき、設定値から判定できる未充足条件だけを述べる。"""
        if self._has_collected_events():
            return ""
        unmet = []
        if not self.tool_search.isChecked():
            unmet.append(self.tr("「ツール定義の遅延ロード」が OFF"))
        if self.tool_search_ranking.currentData() != "hve":
            unmet.append(self.tr("「ランキング実装」が「SDK 組み込みのまま」"))
        if unmet:
            return (
                self.tr("収集済みイベントは 0 件です。未充足の収集条件: ")
                + " / ".join(unmet)
            )
        return self.tr(
            "収集済みイベントは 0 件です。設定側の収集条件は満たしています。"
            " 残る条件は CLI がモデルへ tool_search_tool を公開していることですが、"
            " これはこの画面からは確認できません。"
        )

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
        # 末尾判定にするとタブを増やしたときに別タブで発火するため、統計タブの位置で判定する。
        if index == self._stats_tab_index:
            self.reload_stats()

    # ------------------------------------------------------------------
    # コンテキスト内訳（FR-TS-11）
    # ------------------------------------------------------------------

    def _run_context_command(self) -> Tuple[int, str, str]:
        """CLI をそのまま呼ぶ。GUI 側で集計や推定はしない。"""
        kwargs = {}
        if sys.platform == "win32":
            # pythonw から起動した GUI でコンソール窓を開かせない。
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(  # noqa: S603 - 引数は固定でシェルを介さない
            [sys.executable, "-m", "hve", "toolsearch", "context"],
            cwd=str(self._repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()

    def measure_context(self) -> None:
        if self._context_worker is not None and self._context_worker.isRunning():
            return
        self.context_result_label.setText(self.tr("実測中…"))
        self._context_button.setEnabled(False)
        worker = _ContextWorker(self._run_context_command, self)
        worker.finished_with.connect(self.apply_context_result)
        worker.finished.connect(worker.deleteLater)
        self._context_worker = worker
        worker.start()

    def wait_for_context_measurement(self, msec: int) -> bool:
        """実測ワーカーの終了を待つ（テストと終了処理用）。"""
        if self._context_worker is None:
            return True
        return self._context_worker.wait(msec)

    def apply_context_result(self, code: int, out: str, err: str) -> None:
        """CLI の出力をそのまま描画する。失敗時は数値を推定で埋めない。"""
        self._context_button.setEnabled(True)
        if code == 0:
            self.context_view.setPlainText(out)
            self.context_result_label.setText("")
            return
        reason = err or out or self.tr("理由を取得できませんでした。")
        self.context_result_label.setText(self.tr("実測に失敗しました: ") + reason)

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


def _format_skill_layer(repo_root: Path) -> str:
    """`skill_manifest.json` と `policy.json` から Skill Layer を読み取り専用で再構成する。"""
    import json

    from ..toolsearch.policy import PolicyError, ToolSearchPolicy
    from ..toolsearch.session import default_skill_roots
    from ..toolsearch.skill_catalog import discover_skills

    manifest_path = repo_root / "hve" / "skill_manifest.json"
    manifest_missing = not manifest_path.is_file()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}

    try:
        policy = ToolSearchPolicy.load(repo_root=repo_root)
    except PolicyError:
        policy = None

    core: list[str] = []
    extend: list[str] = []
    if policy is not None:
        for skill in discover_skills(default_skill_roots(repo_root)):
            bucket = core if policy.pin_for(skill.entry_id) == "always" else extend
            bucket.append(skill.name)
        core.sort()
        extend.sort()

    lines: list[str] = [
        "Skill Layer",
        "==========",
        "",
        f"Core / always (defer=never): {len(core)}",
    ]
    lines.extend(f"  - {name}" for name in core or ["(none)"])

    lines += ["", f"Extend / auto (defer=auto): {len(extend)}"]
    lines.extend(f"  - {name}" for name in extend or ["(none)"])

    if manifest_missing:
        lines += [
            "",
            "workflow_defaults / required_skills / optional_skills: not available",
            f"  - {manifest_path.as_posix()} does not exist in this repository.",
        ]
        lines += _SKILL_LAYER_FOOTER
        return "\n".join(lines)

    defaults = manifest.get("workflow_defaults", {})
    if isinstance(defaults, dict):
        lines += ["", "workflow_defaults:"]
        for workflow_id in sorted(defaults):
            items = defaults[workflow_id]
            if not isinstance(items, list):
                items = []
            value = ", ".join(str(item) for item in items) if items else "(none)"
            lines.append(f"  - {workflow_id}: {value}")
    else:
        lines += ["", "workflow_defaults:", "  - (not defined)"]

    required = manifest.get("required_skills", {})
    if isinstance(required, dict):
        lines += ["", "required_skills:"]
        for workflow_id in sorted(required):
            step_map = required[workflow_id]
            if not isinstance(step_map, dict):
                continue
            for step_id in sorted(step_map):
                items = step_map[step_id]
                if not isinstance(items, list):
                    items = []
                value = ", ".join(str(item) for item in items) if items else "(none)"
                lines.append(f"  - {workflow_id}:{step_id}: {value}")
    else:
        lines += ["", "required_skills:", "  - (not defined)"]

    optional = manifest.get("optional_skills", {})
    if isinstance(optional, dict):
        lines += ["", "optional_skills:"]
        for workflow_id in sorted(optional):
            step_map = optional[workflow_id]
            if not isinstance(step_map, dict):
                continue
            for step_id in sorted(step_map):
                items = step_map[step_id]
                if not isinstance(items, list):
                    items = []
                value = ", ".join(str(item) for item in items) if items else "(none)"
                lines.append(f"  - {workflow_id}:{step_id}: {value}")
    else:
        lines += ["", "optional_skills:", "  - (not defined)"]

    lines += _SKILL_LAYER_FOOTER
    return "\n".join(lines)


__all__ = ["ToolSearchSection"]
