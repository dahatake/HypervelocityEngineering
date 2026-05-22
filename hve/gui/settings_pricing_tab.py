"""hve.gui.settings_pricing_tab — 料金 / 為替レート / ステータスライン設定タブ。

Wave 4 (T4.3) の独立ウィジェット。``SettingsDialog`` 等から ``addTab()`` 経由で
組み込むことを想定する。本タブは以下のフィールドを編集できる:

- USD → JPY 換算レート (浮動小数, デフォルト 150.0)
- 通貨表示モード ("auto" / "usd" / "jpy" / "both")
- 月初自動取得の有効/無効
- ステータスライン (CUI) の有効/無効
- 「料金表を今すぐ更新」ボタン (``hve pricing refresh`` 相当)
- 最終取得日時 / モデル件数 / プラン件数の読み取り専用表示

値の永続化は呼び出し側 (SettingsDialog) が担う。本タブは ``values()`` で現在値
を返すのみで、副作用を持たない（ただし「今すぐ更新」ボタンのみ ``fetch`` を
直接呼ぶ）。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


_DASH = "-"

_CURRENCY_CHOICES = (
    ("auto", "自動 (ja → 両方, 他 → USD)"),
    ("both", "両方 ($X (¥Y))"),
    ("usd", "USD のみ"),
    ("jpy", "JPY のみ"),
)


class SettingsPricingTab(QWidget):
    """料金 / ステータスライン関連設定タブ。"""

    # 設定値が変更された (UI 操作で) 都度 emit。永続化は呼び出し側で実施。
    values_changed = Signal()

    def __init__(
        self,
        *,
        usd_jpy_rate: float = 150.0,
        currency: str = "auto",
        auto_refresh: bool = True,
        statusline_enabled: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._build_ui(
            usd_jpy_rate=usd_jpy_rate,
            currency=currency,
            auto_refresh=auto_refresh,
            statusline_enabled=statusline_enabled,
        )
        self._reload_cache_status()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------
    def _build_ui(
        self,
        *,
        usd_jpy_rate: float,
        currency: str,
        auto_refresh: bool,
        statusline_enabled: bool,
    ) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # --- 為替レート ---
        form = QFormLayout()
        form.setSpacing(6)

        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0.01, 9999.99)
        self._rate_spin.setDecimals(2)
        self._rate_spin.setSingleStep(0.5)
        self._rate_spin.setSuffix(" 円/USD")
        self._rate_spin.setValue(float(usd_jpy_rate))
        self._rate_spin.valueChanged.connect(lambda *_: self.values_changed.emit())
        form.addRow(self.tr("USD/JPY レート (固定値)"), self._rate_spin)

        # --- 通貨表示モード ---
        self._currency_combo = QComboBox()
        for value, label in _CURRENCY_CHOICES:
            self._currency_combo.addItem(label, userData=value)
        idx = next(
            (i for i, (v, _) in enumerate(_CURRENCY_CHOICES) if v == (currency or "auto").lower()),
            0,
        )
        self._currency_combo.setCurrentIndex(idx)
        self._currency_combo.currentIndexChanged.connect(lambda *_: self.values_changed.emit())
        form.addRow(self.tr("通貨表示モード"), self._currency_combo)

        # --- 月初自動取得 ---
        self._auto_refresh_cb = QCheckBox(self.tr("月初に料金表を自動取得する"))
        self._auto_refresh_cb.setChecked(bool(auto_refresh))
        self._auto_refresh_cb.stateChanged.connect(lambda *_: self.values_changed.emit())
        form.addRow("", self._auto_refresh_cb)

        # --- CUI ステータスライン ---
        self._statusline_cb = QCheckBox(self.tr("CUI ステータスラインを有効にする"))
        self._statusline_cb.setChecked(bool(statusline_enabled))
        self._statusline_cb.stateChanged.connect(lambda *_: self.values_changed.emit())
        form.addRow("", self._statusline_cb)

        root.addLayout(form)
        root.addWidget(_hline())

        # --- 料金表 取得状況 ---
        info_title = QLabel(self.tr("料金表キャッシュ"))
        info_title.setStyleSheet("font-weight: bold; color: #222;")
        root.addWidget(info_title)

        self._fetched_label = QLabel(_DASH)
        self._fetched_label.setStyleSheet("color: #555;")
        self._fetched_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._counts_label = QLabel(_DASH)
        self._counts_label.setStyleSheet("color: #555;")

        self._cache_path_label = QLabel(_DASH)
        self._cache_path_label.setStyleSheet("color: #888; font-size: 8pt;")
        self._cache_path_label.setWordWrap(True)
        self._cache_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        meta = QFormLayout()
        meta.addRow(self.tr("最終取得日時"), self._fetched_label)
        meta.addRow(self.tr("モデル / プラン件数"), self._counts_label)
        meta.addRow(self.tr("キャッシュ パス"), self._cache_path_label)
        root.addLayout(meta)

        # --- 更新ボタン ---
        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton(self.tr("🔄 料金表を今すぐ更新"))
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch(1)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #5a6473;")
        btn_row.addWidget(self._status_label)
        root.addLayout(btn_row)

        root.addStretch(1)

    # ------------------------------------------------------------------
    # データ取得
    # ------------------------------------------------------------------
    def values(self) -> dict:
        """編集中の値を dict で返す (永続化は呼び出し側)。"""
        return {
            "pricing_usd_jpy_rate": float(self._rate_spin.value()),
            "pricing_currency": str(self._currency_combo.currentData() or "auto"),
            "pricing_auto_refresh": bool(self._auto_refresh_cb.isChecked()),
            "pricing_statusline_enabled": bool(self._statusline_cb.isChecked()),
        }

    # ------------------------------------------------------------------
    # 料金表ハンドラ
    # ------------------------------------------------------------------
    def _reload_cache_status(self) -> None:
        try:
            from ..pricing import default_cache_path, load_cached_pricing  # type: ignore
        except Exception:
            self._fetched_label.setText(_DASH)
            self._counts_label.setText(_DASH)
            self._cache_path_label.setText(_DASH)
            return

        path = default_cache_path()
        self._cache_path_label.setText(str(path))
        pricing = load_cached_pricing(path)
        if pricing is None:
            self._fetched_label.setText(self.tr("(未取得)"))
            self._counts_label.setText(_DASH)
            return
        self._fetched_label.setText(
            f"{pricing.fetched_at}  [{pricing.status}]"
        )
        self._counts_label.setText(
            self.tr("モデル: {0} / プラン: {1}").format(
                len(pricing.models), len(pricing.plans)
            )
        )

    def _on_refresh_clicked(self) -> None:
        self._refresh_btn.setEnabled(False)
        self._status_label.setText(self.tr("取得中..."))
        try:
            from ..pricing import (  # type: ignore
                PricingFetchError,
                default_cache_path,
                fetch_copilot_pricing,
                save_cached_pricing,
            )
        except Exception as exc:
            self._status_label.setText(self.tr("失敗: pricing モジュール不可 ({0})").format(exc))
            self._refresh_btn.setEnabled(True)
            return
        try:
            pricing = fetch_copilot_pricing(timeout=10.0)
        except PricingFetchError as exc:
            self._status_label.setText(self.tr("取得失敗: {0}").format(exc))
            self._refresh_btn.setEnabled(True)
            return
        except Exception as exc:  # pragma: no cover
            self._status_label.setText(self.tr("予期せぬエラー: {0}").format(exc))
            self._refresh_btn.setEnabled(True)
            return
        save_cached_pricing(pricing, default_cache_path())
        self._status_label.setText(
            self.tr("✅ 取得完了 (status={0})").format(pricing.status)
        )
        self._reload_cache_status()
        self._refresh_btn.setEnabled(True)


def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    f.setStyleSheet("color: #e0e3e8;")
    return f
