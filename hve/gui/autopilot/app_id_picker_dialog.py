"""hve.gui.autopilot.app_id_picker_dialog — AAS 完了後の APP-ID 選択ダイアログ。

AAS が ``docs/catalog/app-arch-catalog.md`` を生成・更新した直後、
downstream（aad-web / asdw-web / adfd / adfdv）を起動する前にユーザーに
表示する。ユーザーは downstream の実行対象 APP-ID を絞り込める。

設定 ``autopilot_show_app_id_picker`` が True（既定）かつ
``selection.pre_phases()`` に ``"aas"`` が含まれる場合にのみ表示される。

タイムアウト経過時はその時点のチェック状態で自動 ``accept()`` する
（初期状態は全項目チェック ON のため、放置時は catalog 全件実行となる）。
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


def format_remaining(sec: int) -> str:
    """残り秒数を ``MM:SS`` 形式の文字列に整形する（純ロジック、Qt 非依存）。

    負値は 0 として扱う。3600 秒以上は ``MM`` 部分が 60 を超えた表記となる
    （例: 3700 → ``"61:40"``）。SpinBox 上限 3600 秒の運用では 60 分未満。
    """
    if sec < 0:
        sec = 0
    minutes = sec // 60
    seconds = sec % 60
    return f"{minutes:02d}:{seconds:02d}"


class AppIdPickerDialog(QDialog):
    """APP-ID 選択ダイアログ（チェックリスト + タイムアウト付き）。

    Args:
        parent: 親ウィジェット（通常は MainWindow）。
        app_entries: ``[(app_id, architecture), ...]`` のタプル列。
            ``parse_catalog()`` の戻り値 ``Dict[str, str]`` を
            ``list(catalog.items())`` に変換して渡す。
        timeout_sec: タイムアウト秒数。0 / 負値は 1 にサニタイズされる。

    Returns:
        - ``exec()`` が ``Accepted`` を返したら ``selected_app_ids()`` で
          チェック中の APP-ID を取得できる。チェック 0 件で OK 押下も許可される
          （呼び元で `[]` を「実行対象なし」として扱うこと）。
        - ``Rejected`` ならキャンセル扱い。
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        app_entries: Sequence[Tuple[str, str]],
        timeout_sec: int = 300,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("APP-ID 選択"))
        self.setModal(True)

        # サニタイズ: 0 / 負値 / 非数値は 1 に丸める（即 accept を防ぐため最低 1 秒）
        try:
            self._remaining = max(1, int(timeout_sec))
        except (TypeError, ValueError):
            self._remaining = 1

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(self.tr(
            "downstream（Web / Dataflow Design / Deploy 等）の実行対象 APP-ID を"
            " 選択してください。\n"
            " タイムアウト経過時はその時点のチェック状態で自動的に実行されます。"
        )))

        self._list = QListWidget(self)
        for app_id, arch in app_entries:
            display = f"{app_id}  ({arch})" if arch else str(app_id)
            item = QListWidgetItem(display, self._list)
            # チェック可能フラグを付与し、初期状態は全項目チェック ON
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            # APP-ID を Qt.UserRole に保持（表示文字列から逆引きしないため）
            item.setData(Qt.ItemDataRole.UserRole, str(app_id))
        layout.addWidget(self._list)

        self._remaining_label = QLabel(self)
        self._remaining_label.setText(
            self.tr("残り {t}").format(t=format_remaining(self._remaining))
        )
        layout.addWidget(self._remaining_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 1 秒ごとに残り時間を減算し、0 到達で accept() する。
        # 親を self にして dialog 破棄時に確実に停止する。
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------
    def selected_app_ids(self) -> List[str]:
        """チェック中の APP-ID をリストで返す（``exec()`` 後に呼ぶ想定）。

        チェック 0 件のときは空 list を返す（呼び元で「実行対象なし」と扱う）。
        """
        result: List[str] = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                app_id = item.data(Qt.ItemDataRole.UserRole)
                if app_id:
                    result.append(str(app_id))
        return result

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------
    def _on_tick(self) -> None:
        self._remaining -= 1
        # ラベルを先に更新（最後の "残り 00:00" 表示を保証）
        self._remaining_label.setText(
            self.tr("残り {t}").format(t=format_remaining(self._remaining))
        )
        if self._remaining <= 0:
            # タイムアウト: 現在のチェック状態で自動 accept
            self.accept()

    def done(self, result: int) -> None:  # noqa: D401 — Qt override
        """accept / reject の最終経路。タイマー停止を保証する。"""
        try:
            self._timer.stop()
        except Exception:
            pass
        super().done(result)


__all__ = ["AppIdPickerDialog", "format_remaining"]
