"""Status kind enum for the bottom status banner.

T2 (gui-status-banner): `MainWindow._set_status(kind, message)` で使用する
状況カテゴリを定義する。各 kind は表示ラベル（日本語既定値）を保持する。

ライト/ダーク配色は `status_banner.StatusBanner` 側で管理する。

i18n: ラベルは Qt の `QCoreApplication.translate("StatusKind", ...)` 経由で
解決するため、`.ts` ファイル側でコンテキスト名 `StatusKind` に対する翻訳を
登録すれば英語等へ切替可能。
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QCoreApplication


class StatusKind(str, Enum):
    """ステータスバナーの状況カテゴリ。

    値は `str` を兼ねるため、stylesheet の objectName やテストでの
    文字列比較にそのまま利用できる。
    """

    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

    @property
    def default_label(self) -> str:
        """表示ラベル（i18n 対応・既定値は日本語）。"""
        source = _SOURCE_LABELS[self]
        return QCoreApplication.translate("StatusKind", source)


_SOURCE_LABELS: dict[StatusKind, str] = {
    StatusKind.IDLE: "待機",
    StatusKind.RUNNING: "実行中",
    StatusKind.SUCCESS: "成功",
    StatusKind.WARNING: "警告",
    StatusKind.ERROR: "失敗",
}
