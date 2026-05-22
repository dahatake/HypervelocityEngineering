"""hve.gui.qa_answer_dialog — QA 質問票への回答を入力するダイアログ（表形式）。

CLI ↔ GUI IPC フローでの責務:
    - `qa_ipc_manager.QAIpcManager` が IPC ディレクトリの `*.request.json` を検出すると
      `QAMerger.parse_qa_file()` で QADocument をロードし、本ダイアログをモーダル表示する。
    - ユーザーが [Submit] を押すと、回答が以下の形式でシリアライズされ
      `submitted(str)` シグナルで通知される（呼び出し側が `<step_id>.answers.md` に書き出す）。
        - 選択肢付き質問: `番号: ラベル`（例: `1: A`）
        - 自由記述質問:   `番号:: 自由記述テキスト`（例: `2:: 詳細回答内容`）
    - [全て既定値で進める] / [キャンセル] はそれぞれ `adopt_all_defaults()` / `cancelled()`
      シグナルを発火する。

表形式 UI（C 仕様: 全質問を 1 つの表に並べる）:
    - 1 行 = 1 質問
    - 列: [No.] [優先度] [分類] [質問文] [既定値候補] [理由] [回答]
    - 回答列は QComboBox（選択肢あり）または QLineEdit（自由記述）
    - 各行はダイアログ表示時に既定値候補で初期選択される
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from ..qa_merger import QADocument, QAQuestion
except ImportError:  # pragma: no cover
    from qa_merger import QADocument, QAQuestion  # type: ignore[no-redef]


_PRIORITY_COLORS = {
    "最重要": "#d32f2f",
    "高": "#f57c00",
    "中": "#1976d2",
    "低": "#757575",
}

_COL_NO = 0
_COL_PRIORITY = 1
_COL_CATEGORY = 2
_COL_QUESTION = 3
_COL_DEFAULT = 4
_COL_REASON = 5
_COL_ANSWER = 6
_COL_HEADERS = ["No.", "優先度", "分類", "質問", "既定値候補", "理由", "回答"]


class _QuestionRow:
    """1 質問分の入力状態（QComboBox or QLineEdit を保持）。

    `selected_label()` / `freetext_value()` / `serialize()` で
    Submit 時の出力テキストを生成する。
    """

    def __init__(self, question: QAQuestion) -> None:
        self.question = question
        self.combo: Optional[QComboBox] = None
        self.line_edit: Optional[QLineEdit] = None

    @property
    def is_free_text(self) -> bool:
        return not self.question.choices

    def selected_label(self) -> str:
        """選択中の英字ラベルを返す。自由記述/未選択時は空文字。"""
        if self.combo is None:
            return ""
        data = self.combo.currentData()
        return str(data) if data else ""

    def freetext_value(self) -> str:
        """自由記述の入力値を返す。選択肢式の場合は空文字。"""
        if self.line_edit is None:
            return ""
        return self.line_edit.text().strip()

    def serialize(self) -> str:
        """Submit 用の 1 行テキストを返す。値が空なら空文字（呼び出し側で省略）。"""
        if self.is_free_text:
            text = self.freetext_value()
            if not text:
                return ""
            return f"{self.question.no}:: {text}"
        label = self.selected_label()
        if not label:
            return ""
        return f"{self.question.no}: {label}"


class QAAnswerDialog(QDialog):
    """QA 質問票への回答を入力する表形式ダイアログ。

    Signals:
        submitted(str): "番号: ラベル" / "番号:: 自由記述" 形式の回答テキスト
        cancelled(): ユーザーがキャンセル
        adopt_all_defaults(): 全て既定値で進める
    """

    submitted = Signal(str)
    cancelled = Signal()
    adopt_all_defaults = Signal()

    def __init__(
        self,
        qa_document: QADocument,
        step_id: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._doc = qa_document
        self._step_id = step_id
        self._rows: List[_QuestionRow] = []
        self._closing_via_button = False  # closeEvent 二重発火防止

        # 非モーダル: Workbench ログ閲覧可
        self.setModal(False)
        title = self.tr("QA 回答入力")
        if step_id:
            title = f"{title} - Step {step_id}"
        self.setWindowTitle(title)
        self.resize(1100, 600)

        outer = QVBoxLayout(self)

        # ヘッダー
        header_text = qa_document.title or self.tr("QA 質問票")
        header_label = QLabel(f"<h2>{header_text}</h2>")
        header_label.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(header_label)

        if qa_document.preamble:
            pre_label = QLabel(qa_document.preamble)
            pre_label.setWordWrap(True)
            outer.addWidget(pre_label)

        info_label = QLabel(
            self.tr(
                "全質問が表形式で表示されます。既定値候補が初期選択されています。"
                "必要に応じて回答列を変更し、[Submit] を押してください。"
                "自由記述質問は直接入力できます。"
            )
        )
        info_label.setWordWrap(True)
        outer.addWidget(info_label)

        if not qa_document.questions:
            empty_label = QLabel(self.tr("質問が含まれていません。"))
            outer.addWidget(empty_label)
        else:
            self._table = self._build_table(qa_document.questions)
            outer.addWidget(self._table, stretch=1)

        # ボタンバー
        btn_bar = QHBoxLayout()
        self._defaults_btn = QPushButton(self.tr("全て既定値で進める"))
        self._defaults_btn.clicked.connect(self._on_defaults)
        btn_bar.addWidget(self._defaults_btn)
        btn_bar.addStretch(1)
        self._cancel_btn = QPushButton(self.tr("キャンセル"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_bar.addWidget(self._cancel_btn)
        self._submit_btn = QPushButton(self.tr("Submit"))
        self._submit_btn.setDefault(True)
        self._submit_btn.clicked.connect(self._on_submit)
        btn_bar.addWidget(self._submit_btn)
        outer.addLayout(btn_bar)

    # ------------------------------------------------------------------
    # テーブル構築
    # ------------------------------------------------------------------

    def _build_table(self, questions: List[QAQuestion]) -> QTableWidget:
        table = QTableWidget(len(questions), len(_COL_HEADERS), self)
        table.setHorizontalHeaderLabels(_COL_HEADERS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)

        hh = table.horizontalHeader()
        hh.setSectionResizeMode(_COL_NO, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_PRIORITY, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_CATEGORY, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_QUESTION, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(_COL_DEFAULT, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(_COL_REASON, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(_COL_ANSWER, QHeaderView.ResizeMode.Interactive)

        for row_idx, q in enumerate(questions):
            row = _QuestionRow(q)
            self._rows.append(row)

            table.setItem(row_idx, _COL_NO, QTableWidgetItem(f"Q{q.no}"))

            priority_item = QTableWidgetItem(q.priority or "")
            if q.priority and q.priority in _PRIORITY_COLORS:
                priority_item.setForeground(QColor("white"))
                priority_item.setBackground(QColor(_PRIORITY_COLORS[q.priority]))
            table.setItem(row_idx, _COL_PRIORITY, priority_item)

            table.setItem(row_idx, _COL_CATEGORY, QTableWidgetItem(q.category or ""))
            table.setItem(row_idx, _COL_QUESTION, QTableWidgetItem(q.question or ""))
            table.setItem(row_idx, _COL_DEFAULT, QTableWidgetItem(q.default_answer or ""))
            table.setItem(row_idx, _COL_REASON, QTableWidgetItem(q.reason or ""))

            answer_widget = self._build_answer_widget(row)
            table.setCellWidget(row_idx, _COL_ANSWER, answer_widget)

        table.resizeRowsToContents()
        return table

    def _build_answer_widget(self, row: _QuestionRow) -> QWidget:
        """回答セルの入力ウィジェットを作成する（QComboBox or QLineEdit）。"""
        q = row.question
        if q.choices:
            combo = QComboBox()
            default_label = self._extract_default_label(q)
            selected_index = 0
            for i, choice in enumerate(q.choices):
                combo.addItem(f"{choice.label}) {choice.text}", userData=choice.label.upper())
                if default_label and choice.label.upper() == default_label.upper():
                    selected_index = i
            combo.setCurrentIndex(selected_index)
            row.combo = combo
            return combo
        # 自由記述（編集可）
        line_edit = QLineEdit()
        line_edit.setText(q.default_answer or "")
        line_edit.setPlaceholderText(self.tr("自由記述で回答を入力"))
        row.line_edit = line_edit
        return line_edit

    @staticmethod
    def _extract_default_label(question: QAQuestion) -> str:
        """default_answer から先頭の単一英字ラベルを抽出する。

        想定形式: "A) はい" / "A: はい" / "A"
        """
        if not question.default_answer:
            return ""
        text = question.default_answer.strip()
        if not text:
            return ""
        first = text[0]
        if first.isalpha() and len(first) == 1:
            return first.upper()
        return ""

    # ------------------------------------------------------------------
    # 後方互換 API（既存テスト用）
    # ------------------------------------------------------------------

    @property
    def _question_widgets(self) -> List[_QuestionRow]:
        """旧 API: 各質問の入力状態リストを返す。"""
        return self._rows

    # ------------------------------------------------------------------
    # ボタンハンドラ
    # ------------------------------------------------------------------

    def _on_submit(self) -> None:
        """Submit: 選択肢は `N: A`、自由記述は `N:: <text>` 形式で出力。"""
        lines: List[str] = []
        for row in self._rows:
            text = row.serialize()
            if text:
                lines.append(text)
        content = "\n".join(lines)
        self._closing_via_button = True
        self.submitted.emit(content)
        self.accept()

    def _on_defaults(self) -> None:
        self._closing_via_button = True
        self.adopt_all_defaults.emit()
        self.accept()

    def _on_cancel(self) -> None:
        self._closing_via_button = True
        self.cancelled.emit()
        self.reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # × ボタン / ESC でダイアログが閉じられた場合のみ cancelled を emit する。
        # Submit / Defaults / Cancel ボタン経由で閉じる場合は _closing_via_button=True なので二重発火しない。
        if not self._closing_via_button:
            self.cancelled.emit()
        super().closeEvent(event)
