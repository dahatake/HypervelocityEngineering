"""Bottom status banner widget (T1: gui-status-banner).

`MainWindow` の `[戻る] / [次へ] / [停止]` ナビゲーション行の直上に常時配置
する全幅ステータスバナー。`{状況ラベル} {説明文}` を 1 行で表示する。

設計:
- 状況カテゴリは `status_kind.StatusKind` (idle/running/success/warning/error)。
- 配色はライト/ダーク 2 テーマ。`apply_theme(name)` でテーマ切替。
- 横方向は `Expanding` で親幅いっぱい、縦方向は最小 40px（コンテンツ駆動で伸長可）。
- `{状況ラベル}` は bold、`{説明文}` は通常ウェイト。間に `setSpacing(8)` で 8px の余白。
- ライトテーマはマテリアル系既定色、ダークテーマはライト配色を反転したもの
  （厳密な WCAG コントラスト検証は未実施。色覚多様性配慮は将来課題）。

公開 API:
- `set_status(kind: StatusKind, message: str) -> None`
- `apply_theme(theme: str) -> None`  # "light" / "dark"
- 公開属性: `status_label` (QLabel), `description_label` (QLabel)
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from .status_kind import StatusKind


# (background, foreground) per kind, per theme.
_PALETTE: dict[str, dict[StatusKind, tuple[str, str]]] = {
    "light": {
        StatusKind.IDLE: ("#eceff1", "#37474f"),
        StatusKind.RUNNING: ("#e3f2fd", "#0d47a1"),
        StatusKind.SUCCESS: ("#e8f5e9", "#1b5e20"),
        StatusKind.WARNING: ("#fff8e1", "#e65100"),
        StatusKind.ERROR: ("#ffebee", "#b71c1c"),
    },
    "dark": {
        StatusKind.IDLE: ("#37474f", "#eceff1"),
        StatusKind.RUNNING: ("#0d47a1", "#e3f2fd"),
        StatusKind.SUCCESS: ("#1b5e20", "#e8f5e9"),
        StatusKind.WARNING: ("#e65100", "#fff8e1"),
        StatusKind.ERROR: ("#b71c1c", "#ffebee"),
    },
}

_BANNER_MIN_HEIGHT = 40


class StatusBanner(QWidget):
    """ナビゲーション行直上の全幅ステータスバナー。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBanner")
        # Major fix (#4): setFixedHeight は高 DPI/フォントスケール変更で切れるため
        # setMinimumHeight に変更。コンテンツ駆動の伸長を許容する。
        self.setMinimumHeight(_BANNER_MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        self.status_label = QLabel(StatusKind.IDLE.default_label, self)
        self.status_label.setObjectName("StatusBannerStatus")
        # Major fix (#6): RichText 解釈を回避するため PlainText 固定。
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        font = self.status_label.font()
        font.setBold(True)
        self.status_label.setFont(font)
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self.description_label = QLabel("", self)
        self.description_label.setObjectName("StatusBannerDescription")
        self.description_label.setTextFormat(Qt.TextFormat.PlainText)
        self.description_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        # 横方向に伸びる。長文は親幅で末端が切れるため、フルテキストは tooltip で補完する。
        self.description_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        layout.addWidget(self.status_label)
        layout.addWidget(self.description_label, stretch=1)

        self._kind: StatusKind = StatusKind.IDLE
        self._theme: str = "light"
        self._last_style_key: Optional[tuple[str, StatusKind]] = None
        self._apply_style()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_status(self, kind: StatusKind, message: str = "") -> None:
        """状況カテゴリと説明文を更新する。"""
        if not isinstance(kind, StatusKind):
            raise TypeError(f"kind must be StatusKind, got {type(kind).__name__}")
        self._kind = kind
        self.status_label.setText(kind.default_label)
        text = message or ""
        self.description_label.setText(text)
        # Major fix (#5): 長文の切り捨て対策として、tooltip にフルテキストを提示する。
        self.description_label.setToolTip(text)
        self._apply_style()

    def apply_theme(self, theme: str) -> None:
        """テーマを切り替える（"light" / "dark"）。未知のテーマは light 扱い。"""
        self._theme = theme if theme in _PALETTE else "light"
        self._apply_style()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def current_kind(self) -> StatusKind:
        return self._kind

    def _apply_style(self) -> None:
        # Minor fix (#16): 同じ (theme, kind) なら setStyleSheet 再適用をスキップ。
        key = (self._theme, self._kind)
        if key == self._last_style_key:
            return
        bg, fg = _PALETTE[self._theme][self._kind]
        # Minor fix (#28): 直接子セレクタ `>` を使い、将来の子孫追加で意図せぬ波及を防ぐ。
        self.setStyleSheet(
            f"QWidget#StatusBanner {{ background-color: {bg}; }} "
            f"QWidget#StatusBanner > QLabel {{ color: {fg}; background-color: transparent; }}"
        )
        self._last_style_key = key
