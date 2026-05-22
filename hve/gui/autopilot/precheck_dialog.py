"""hve.gui.autopilot.precheck_dialog — Step 1 事前検証結果表示ダイアログ。

旧名: ``AutopilotPrecheckDialog``。Step 1 [次へ] 統合 precheck へマージした際に
``Step1PrecheckDialog`` へリネームし中立化。

`AutopilotPrecheckResult` を受け取り、4 カテゴリ
(FILE / WIZARD_INPUT / SETTING / AUTH) ごとに不足項目を表示する。
不足あり時は ``QDialog.Rejected`` を返し、不足なしなら呼び出し側で
そもそも本ダイアログを開かない設計（main_window 側で result.is_ok() を判定）。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from hve.autopilot.precheck_model import (
    AutopilotPrecheckResult,
    PrecheckCategory,
    PrecheckItem,
)


_CATEGORY_LABEL = {
    PrecheckCategory.FILE: "📄 必須ファイル",
    PrecheckCategory.WIZARD_INPUT: "📝 Step 2 必須入力",
    PrecheckCategory.SETTING: "⚙️ Workflow 設定",
    PrecheckCategory.AUTH: "🔑 認証",
}


class Step1PrecheckDialog(QDialog):
    """Step 1 事前検証の結果を表示するモーダルダイアログ。

    旧名: ``AutopilotPrecheckDialog``。Autopilot ON/OFF いずれも共通で使用されるため
    Step 1 統合フローに中立化した名称へリネーム済み。
    """

    def __init__(
        self,
        result: AutopilotPrecheckResult,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Step 1 事前検証: 不足項目あり"))
        self.setMinimumSize(640, 480)
        self._result = result

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        header = QLabel(self.tr(
            "実行前に以下の不足項目を解決してください。"
            "解決後、もう一度 [次へ] を押してください。"
        ))
        header.setWordWrap(True)
        header.setStyleSheet("font-weight: bold; padding: 4px;")
        outer.addWidget(header)

        total_lbl = QLabel(self.tr("不足項目: {n} 件").format(n=result.count()))
        total_lbl.setStyleSheet("color: #c00; padding-left: 4px;")
        outer.addWidget(total_lbl)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(8)

        for cat in (
            PrecheckCategory.FILE,
            PrecheckCategory.WIZARD_INPUT,
            PrecheckCategory.SETTING,
            PrecheckCategory.AUTH,
        ):
            items = result.by_category(cat)
            if not items:
                continue
            content_layout.addWidget(self._build_category_group(cat, items))

        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            self.tr("閉じる")
        )
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------
    def _build_category_group(
        self,
        category: PrecheckCategory,
        items: list,
    ) -> QGroupBox:
        label = _CATEGORY_LABEL.get(category, str(category))
        group = QGroupBox(f"{label} — {len(items)} 件")
        group.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #d0d7de; "
            "border-radius: 4px; margin-top: 8px; padding: 8px; }"
            " QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        inner = QVBoxLayout(group)
        inner.setContentsMargins(8, 8, 8, 8)
        inner.setSpacing(6)
        for it in items:
            inner.addWidget(self._build_item_label(it))
        return group

    def _build_item_label(self, item: PrecheckItem) -> QLabel:
        wf = item.workflow_id or "-"
        step = f" / Step {item.step_id}" if item.step_id else ""
        head = f"[{wf}{step}] {item.field_name}"
        body = item.description or ""
        hint = item.remediation_hint or ""
        text = f"<b>{head}</b><br>{body}"
        if hint:
            text += f"<br><span style='color:#0969da;'>→ {hint}</span>"
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        lbl.setStyleSheet("padding: 4px; background: #fafbfc; border-radius: 3px;")
        return lbl

    def result_data(self) -> AutopilotPrecheckResult:
        """元の precheck 結果を返す（テスト用）。"""
        return self._result


__all__ = ["Step1PrecheckDialog"]
