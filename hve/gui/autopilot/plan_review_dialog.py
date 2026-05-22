"""hve.gui.autopilot.plan_review_dialog — Step 1 事前検証プランレビュー Dialog。

旧名: ``AutopilotPlanReviewDialog``。Step 1 [次へ] 統合 precheck へマージした際に
``Step1PlanReviewDialog`` へリネームし中立化。

`AutopilotPlanReview` を 4 タブで表示する:
  1. 入力一覧
  2. 出力一覧（[再生成する] チェック付き）
  3. パラメータ一覧
  4. ギャップ提案（[適用する] チェック + [選択した提案を適用] ボタン）

[選択した提案を適用] が押されると、選択行の ``GapSuggestion`` を
``gaps_applied`` シグナルで通知する。
[OK] / [キャンセル] は標準ボタンで `QDialog.Accepted/Rejected` を返す。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from hve.autopilot.plan_review_model import (
    AutopilotPlanReview,
    FileStatus,
    GapSuggestion,
    ParameterCategory,
    PlannedInput,
    PlannedOutput,
    ParameterEntry,
)


_STATUS_LABEL = {
    FileStatus.EXISTING_REUSABLE: "✅ 既存（流用可）",
    FileStatus.MISSING_PRODUCED: "🛠 他ステップが生成予定",
    FileStatus.MISSING_GAP: "⚠ 不足（ギャップ）",
    FileStatus.UNKNOWN: "❓ 不明",
}


class Step1PlanReviewDialog(QDialog):
    """Step 1 事前検証プランレビュー Dialog。

    旧名: ``AutopilotPlanReviewDialog``。Autopilot ON/OFF いずれも共通で使用されるため
    Step 1 統合フローに中立化した名称へリネーム済み。
    """

    gaps_applied = Signal(list)
    """選択された ``List[GapSuggestion]`` を引数に発火。"""

    def __init__(
        self,
        review: AutopilotPlanReview,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Step 1 事前検証: プランレビュー"))
        self.setMinimumSize(880, 560)
        self._review = review
        self._gap_checkboxes: List[Tuple[QCheckBox, GapSuggestion]] = []
        self._regen_checkboxes: Dict[Tuple[str, str, str], QCheckBox] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        header = QLabel(self.tr(
            "実行プランを確認してください。"
            "ギャップ提案がある場合は対象を選択し [選択した提案を適用] を押すと、"
            "対応ステップが自動チェックされ再検証されます。"
        ))
        header.setWordWrap(True)
        header.setStyleSheet("padding: 4px;")
        outer.addWidget(header)

        summary = QLabel(self._format_summary())
        summary.setStyleSheet("padding: 2px 4px; color: #444;")
        outer.addWidget(summary)

        # E=2: 実行順序の表示（pre_phases → app_chains → main_workflows）
        if review.execution_order:
            order_text = " → ".join(wf.upper() for wf in review.execution_order)
            exec_order_label = QLabel(self.tr("実行順序: {order}").format(order=order_text))
            exec_order_label.setWordWrap(True)
            exec_order_label.setStyleSheet(
                "padding: 4px 6px; background: #f4f7fb; "
                "border: 1px solid #d3dbe6; border-radius: 3px; color: #1f3a5f;"
            )
            outer.addWidget(exec_order_label)

        tabs = QTabWidget()
        tabs.addTab(self._build_inputs_tab(), self.tr("入力一覧 ({n})").format(n=len(review.inputs)))
        tabs.addTab(self._build_outputs_tab(), self.tr("出力一覧 ({n})").format(n=len(review.outputs)))
        tabs.addTab(self._build_params_tab(), self.tr("パラメータ ({n})").format(n=len(review.parameters)))
        tabs.addTab(self._build_gaps_tab(), self.tr("ギャップ提案 ({n})").format(n=len(review.gaps)))
        outer.addWidget(tabs, stretch=1)

        # ボタン群
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setText(self.tr("このプランで実行"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("キャンセル"))
        # ギャップが残っている場合は OK を無効化（誤実行防止、Critical #2）
        if review.has_blocking_gaps:
            self._ok_button.setEnabled(False)
            self._ok_button.setToolTip(self.tr(
                "ギャップ提案を [適用] するか、不足ファイルを手動配置してから実行してください。"
            ))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------
    def _format_summary(self) -> str:
        r = self._review
        existing = sum(1 for i in r.inputs if i.status == FileStatus.EXISTING_REUSABLE)
        produced = sum(1 for i in r.inputs if i.status == FileStatus.MISSING_PRODUCED)
        gap = sum(1 for i in r.inputs if i.status == FileStatus.MISSING_GAP)
        out_existing = sum(1 for o in r.outputs if o.already_exists)
        return self.tr(
            "入力: {ein} 件流用可 / {pin} 件生成予定 / {gin} 件ギャップ ｜ "
            "出力: 全 {tot_out} 件 ({eo} 件は既存)"
        ).format(
            ein=existing, pin=produced, gin=gap,
            tot_out=len(r.outputs), eo=out_existing,
        )

    # ---------------- Tab 1: 入力 ----------------
    def _build_inputs_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        table = QTableWidget()
        cols = [
            self.tr("Workflow"),
            self.tr("Step"),
            self.tr("Path"),
            self.tr("Status"),
            self.tr("Producer"),
        ]
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.setRowCount(len(self._review.inputs))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for row, inp in enumerate(self._review.inputs):
            producer_text = (
                f"{inp.producer[0]} / {inp.producer[1]}" if inp.producer else ""
            )
            # 暗黙依存ステップ ID をユーザー向け表記に変換 (Major #9)
            step_text = (
                self.tr("(暗黙依存)") if inp.step_id == "<implicit>" else inp.step_id
            )
            self._set_row(
                table, row,
                [inp.workflow_id, step_text, inp.path, _STATUS_LABEL.get(inp.status, str(inp.status)), producer_text],
            )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(True)
        lay.addWidget(table)
        return w

    # ---------------- Tab 2: 出力 ----------------
    def _build_outputs_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        table = QTableWidget()
        cols = [
            self.tr("Workflow"),
            self.tr("Step"),
            self.tr("Path"),
            self.tr("Existing"),
            self.tr("mtime"),
            self.tr("size"),
            self.tr("再生成する"),
        ]
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.setRowCount(len(self._review.outputs))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for row, out in enumerate(self._review.outputs):
            self._set_row(
                table, row,
                [
                    out.workflow_id,
                    out.step_id,
                    out.path,
                    self.tr("はい (流用可)") if out.already_exists else self.tr("いいえ"),
                    out.mtime_iso or "",
                    str(out.size_bytes) if out.size_bytes is not None else "",
                ],
            )
            # 「再生成する」チェックボックス（既存ファイルのみ意味あり）
            cb = QCheckBox()
            cb.setEnabled(out.already_exists)
            cb.setToolTip(
                self.tr("ON にすると既存ファイルを上書きして再生成します") if out.already_exists
                else self.tr("既存ファイルなし — 再生成チェックは無効")
            )
            self._regen_checkboxes[(out.workflow_id, out.step_id, out.path)] = cb
            container = QWidget()
            cl = QVBoxLayout(container)
            cl.setContentsMargins(4, 0, 4, 0)
            cl.addWidget(cb, alignment=Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(row, len(cols) - 1, container)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(table)
        return w

    # ---------------- Tab 3: パラメータ ----------------
    def _build_params_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        if not self._review.parameters:
            lay.addWidget(QLabel(self.tr(
                "必須パラメータはありません（Wizard Step 2 / Workflow Settings の宣言値による）。"
            )))
            lay.addStretch(1)
            return w
        table = QTableWidget()
        cols = [
            self.tr("Workflow"),
            self.tr("Field"),
            self.tr("Category"),
            self.tr("Required"),
            self.tr("Present"),
            self.tr("Value"),
        ]
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.setRowCount(len(self._review.parameters))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, p in enumerate(self._review.parameters):
            self._set_row(
                table, row,
                [
                    p.workflow_id,
                    p.field_name,
                    self.tr("Wizard") if p.category == ParameterCategory.WIZARD else self.tr("Setting"),
                    self.tr("はい") if p.is_required else self.tr("いいえ"),
                    self.tr("入力済み") if p.value_present else self.tr("未入力"),
                    p.value_preview or "",
                ],
            )
        table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(table)
        return w

    # ---------------- Tab 4: ギャップ ----------------
    def _build_gaps_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        if not self._review.gaps:
            lay.addWidget(QLabel(self.tr(
                "ギャップなし — 追加すべきステップはありません。"
            )))
            lay.addStretch(1)
            return w

        intro = QLabel(self.tr(
            "以下の入力ファイルは生成元ステップがチェックされていません。"
            "[適用する] にチェックを入れて [選択した提案を適用] を押すと、"
            "対応 Workflow / Step が自動的に有効化され、再検証されます。"
        ))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        table = QTableWidget()
        cols = [
            self.tr("適用する"),
            self.tr("不足パス"),
            self.tr("追加 Workflow"),
            self.tr("追加 Step"),
            self.tr("併せて有効化される Step"),
        ]
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.setRowCount(len(self._review.gaps))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, g in enumerate(self._review.gaps):
            cb = QCheckBox()
            cb.setChecked(True)  # デフォルトで全選択
            self._gap_checkboxes.append((cb, g))
            container = QWidget()
            cl = QVBoxLayout(container)
            cl.setContentsMargins(4, 0, 4, 0)
            cl.addWidget(cb, alignment=Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(row, 0, container)
            self._set_row(
                table, row,
                [
                    g.missing_path,
                    g.suggested_workflow_id,
                    g.suggested_step_id,
                    ", ".join(g.transitive_steps),
                ],
                start_col=1,
            )
        table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(table)

        apply_btn = QPushButton(self.tr("選択した提案を適用"))
        apply_btn.clicked.connect(self._on_apply_clicked)
        lay.addWidget(apply_btn)
        return w

    # ------------------------------------------------------------------
    def _set_row(
        self,
        table: QTableWidget,
        row: int,
        values,
        *,
        start_col: int = 0,
    ) -> None:
        for offset, v in enumerate(values):
            col = start_col + offset
            if v is None:
                continue
            item = QTableWidgetItem(str(v))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, col, item)

    def _on_apply_clicked(self) -> None:
        selected = [g for cb, g in self._gap_checkboxes if cb.isChecked()]
        if not selected:
            # 0 件選択時はユーザーに通知（Minor #14）
            QMessageBox.information(
                self,
                self.tr("Autopilot プランレビュー"),
                self.tr("適用する提案にチェックを入れてから [選択した提案を適用] を押してください。"),
            )
            return
        self.gaps_applied.emit(selected)
        # Dialog はそのまま閉じる（main_window 側で再検証ループ）
        self.accept()

    # ------------------------------------------------------------------
    def selected_regenerate_paths(self) -> Set[Tuple[str, str, str]]:
        """[再生成する] が ON の (workflow_id, step_id, path) 集合を返す。

        .. note::
            現状、本メソッドの返り値は main_window から取得されておらず、
            orchestrator への ``--force-rebuild`` 伝播も未実装である。
            ユーザーが UI 上でチェックを ON にしても実行挙動には影響しない。
            将来 orchestrator 側に force-rebuild API が追加された際に配線する。
        """
        return {key for key, cb in self._regen_checkboxes.items() if cb.isChecked()}

    def review(self) -> AutopilotPlanReview:
        return self._review


__all__ = ["Step1PlanReviewDialog"]
