"""hve.gui.workflow_requirements_banner — 必須要件サマリー バナー Widget（Task B）。

設計プラン「ワークフロー必須要件サマリーバナー」§7 Task B に対応する Widget 層。

責務:
  - ``RequirementsSummary`` を受け取って、QFrame で視覚的に表示する。
  - 状態表現はアイコン（✅/⚠/—）+ テキスト主体、色は補助（WCAG 配慮）。
  - 文言は ``self.tr(...)`` でラップ（i18n 対応）。

公開 API:
  - ``set_summary(summary)``: サマリーを反映。``None`` を渡すと「対象なし」表示。
  - ``setVisible(bool)``: 標準 QWidget API。

依存:
  - Task A-1/A-2 の ``RequirementsSummary`` / ``RequirementItem`` 型のみ。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .workflow_step_requirements import RequirementsSummary


# 状態 → アイコン文字（テキスト主体）
_STATUS_ICON = {
    "ok": "✅",
    "warn": "⚠",
    "info": "—",
}

# 全体ステータス → 補助色（境界線色のみに利用、テキストは黒）
_OVERALL_BORDER_COLOR = {
    "ok": "#2e7d32",    # 緑
    "warn": "#ed6c02",  # 橙
    "none": "#9e9e9e",  # 灰
}


class WorkflowRequirementsBanner(QFrame):
    """ワークフロー必須要件サマリー表示バナー。

    QFrame ベース。可読性のため固定 padding、文字色はシステム既定。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkflowRequirementsBanner")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 6, 8, 6)
        self._layout.setSpacing(3)

        # ヘッダラベル（タイトル）
        self._header = QLabel(self.tr("📋 このステップに必要な前提"))
        self._header.setStyleSheet("font-weight: bold;")
        self._layout.addWidget(self._header)

        # ガイダンステキスト（折り返し有）
        self._guidance = QLabel("")
        self._guidance.setWordWrap(True)
        self._guidance.setStyleSheet("color: #444;")
        self._layout.addWidget(self._guidance)

        # 項目リスト（動的生成）
        self._items_container = QWidget()
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(2)
        self._layout.addWidget(self._items_container)

        self._apply_border("none")
        self.set_summary(None)

    # ----------------------------------------------------------------
    # 公開 API
    # ----------------------------------------------------------------

    def set_summary(self, summary: Optional[RequirementsSummary]) -> None:
        """サマリーを反映。None なら「対象なし」表示。"""
        # 既存項目をクリア
        while self._items_layout.count():
            it = self._items_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if summary is None:
            self._header.setText(self.tr("📋 このステップに必要な前提"))
            self._guidance.setText(
                self.tr("ワークフロー / ステップを選択すると、ここに必要条件が表示されます。")
            )
            self._apply_border("none")
            return

        # ヘッダ: ワークフロー ID + ステップ ID を併記
        self._header.setText(self.tr(
            "📋 このステップに必要な前提  [{wf} / Step {sid}]"
        ).format(wf=summary.workflow_id, sid=summary.step_id))

        self._guidance.setText(summary.guidance_text or "")

        # 項目をリスト表示
        if not summary.items:
            blank = QLabel(self.tr("  （必須要件なし）"))
            blank.setStyleSheet("color: #666;")
            self._items_layout.addWidget(blank)
        else:
            for item in summary.items:
                icon = _STATUS_ICON.get(item.status, "—")
                text = f"  {icon}  {item.label}"
                if item.detail:
                    text += f": {item.detail}"
                lbl = QLabel(text)
                lbl.setWordWrap(True)
                if item.status == "warn":
                    lbl.setStyleSheet("color: #b00020;")  # 補助色（赤系）
                elif item.status == "ok":
                    lbl.setStyleSheet("color: #1b5e20;")  # 補助色（緑系）
                else:
                    lbl.setStyleSheet("color: #555;")
                self._items_layout.addWidget(lbl)

        self._apply_border(summary.overall_status)

    # ----------------------------------------------------------------
    # 内部
    # ----------------------------------------------------------------

    def _apply_border(self, status: str) -> None:
        """全体ステータスに応じた境界線色を適用。"""
        color = _OVERALL_BORDER_COLOR.get(status, "#9e9e9e")
        self.setStyleSheet(
            f"QFrame#WorkflowRequirementsBanner {{"
            f"  border: 2px solid {color};"
            f"  border-radius: 4px;"
            f"  background: #fafafa;"
            f"}}"
        )
