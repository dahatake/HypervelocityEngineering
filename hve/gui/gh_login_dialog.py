"""hve.gui.gh_login_dialog — GitHub CLI ログイン用の埋め込み端末ダイアログ。

設定画面（C5「GitHub」）から開き、``gh auth login`` を埋め込み端末（xterm.js）で
対話実行する。事前チェックで ``gh`` 不在 / PTY バックエンド不在を検出した場合は、
端末を起動せず案内文を表示する。

成否の最終判定はダイアログ単独では行わない（A1 設計どおり exit code は補助情報）。
呼び出し側（C5 の「GitHub CLI でログイン」ボタンハンドラ）が ``gh_cli.capture_gh_token``
でトークンを独立に確認し、``GH_TOKEN`` へ注入する。

テスト容易性:
    - ``XtermTerminalView`` は ``_build_terminal_ui`` 内で遅延 import するため、
      案内文パスでは QtWebEngine を読み込まない。
    - ``pty_backend.spawn`` / ``XtermTerminalView`` は import 元属性を差し替える
      ことで mock 可能（実 ``gh`` を起動せずに配線を検証できる）。
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import gh_cli, pty_backend
from .widgets.terminal_session import TerminalSessionController

__all__ = ["GhLoginDialog"]

# ``gh auth login`` を既定ホスト（github.com）で起動する固定 argv。
_GH_LOGIN_ARGV = ["gh", "auth", "login"]


class GhLoginDialog(QDialog):
    """``gh auth login`` を埋め込み端末で実行するモーダルダイアログ。"""

    # gh プロセス終了時に exit code を通知する（補助情報）。
    login_completed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("GitHub CLI でログイン"))
        self.resize(720, 480)

        self._controller: Optional[TerminalSessionController] = None
        self._session: Optional[pty_backend.PtySession] = None
        self._exit_code: Optional[int] = None

        self._layout = QVBoxLayout(self)
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)

        error = self._precheck()
        if error:
            self._build_guidance_ui(error)
        else:
            self._build_terminal_ui()

    # ------------------------------------------------------------
    # 公開プロパティ
    # ------------------------------------------------------------
    @property
    def exit_code(self) -> Optional[int]:
        """gh プロセスの exit code（未終了 / 未起動時は ``None``）。"""
        return self._exit_code

    @property
    def terminal_started(self) -> bool:
        """埋め込み端末が起動した（事前チェック通過 + spawn 成功）か。"""
        return self._controller is not None

    # ------------------------------------------------------------
    # 事前チェック
    # ------------------------------------------------------------
    def _precheck(self) -> Optional[str]:
        """端末ログインの前提を検査し、満たさない場合は案内文を返す。"""
        if gh_cli.find_gh_binary() is None:
            setup_command = (
                r"hve\setup-hve.cmd"
                if sys.platform.startswith("win")
                else "./hve/setup-hve.sh"
            )
            return self.tr(
                "GitHub CLI (gh) が見つかりません。"
                "推奨: {setup} を実行してGUI依存を再セットアップしてください。"
                "手動インストール: https://cli.github.com/"
            ).format(
                setup=setup_command
            )
        if not pty_backend.is_pty_available():
            return pty_backend.missing_dependency_hint()
        return None

    # ------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------
    def _build_guidance_ui(self, message: str) -> None:
        intro = QLabel(
            self.tr("埋め込み端末でのログインは利用できません。以下の案内に従ってください。")
        )
        intro.setWordWrap(True)
        self._layout.addWidget(intro)

        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._layout.addWidget(msg)

        self._layout.addWidget(self._status_label)

        close_btn = QPushButton(self.tr("閉じる"))
        close_btn.clicked.connect(self.reject)
        self._layout.addWidget(close_btn)

    def _build_terminal_ui(self) -> None:
        # 案内文パスで QtWebEngine を読み込まないよう遅延 import する。
        from .widgets.xterm_terminal_view import XtermTerminalView

        view = XtermTerminalView(self)
        self._layout.addWidget(view, 1)
        self._status_label.setText(
            self.tr("`gh auth login` を実行中です。端末の指示に従ってください。")
        )
        self._layout.addWidget(self._status_label)

        close_btn = QPushButton(self.tr("閉じる"))
        close_btn.clicked.connect(self.accept)
        self._layout.addWidget(close_btn)

        try:
            session = pty_backend.spawn(list(_GH_LOGIN_ARGV))
        except pty_backend.PtyBackendError as exc:
            self._status_label.setText(
                self.tr("端末の起動に失敗しました: {err}").format(err=exc)
            )
            return

        self._session = session
        controller = TerminalSessionController(session, view, parent=self)
        self._controller = controller
        controller.finished.connect(self._on_login_finished)
        # xterm 初期化完了後にポーリングを開始する。
        # NOTE: 開始は XtermTerminalView の ``ready`` 契約に依存する。QtWebEngine が
        # 初期化に失敗し ``ready`` が発火しない場合、端末は無出力のまま待機する。
        view.ready.connect(controller.start)

    # ------------------------------------------------------------
    # スロット
    # ------------------------------------------------------------
    def _on_login_finished(self, exit_code: int) -> None:
        self._exit_code = exit_code
        if exit_code == 0:
            self._status_label.setText(
                self.tr("ログインプロセスが終了しました（正常終了）。[閉じる] を押してください。")
            )
        else:
            self._status_label.setText(
                self.tr("ログインプロセスが終了しました（exit={code}）。").format(code=exit_code)
            )
        self.login_completed.emit(exit_code)

    # ------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------
    def _stop_terminal(self) -> None:
        """起動済みの端末 controller を一度だけ停止する。"""
        controller = self._controller
        if controller is None:
            return
        self._controller = None
        self._session = None
        controller.stop()

    def done(self, result: int) -> None:  # type: ignore[override]
        self._stop_terminal()
        super().done(result)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._stop_terminal()
        super().closeEvent(event)
