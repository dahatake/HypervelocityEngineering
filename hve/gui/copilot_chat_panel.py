"""hve.gui.copilot_chat_panel — GitHub Copilot CLI と対話するドックパネル。

設計（改訂版）:
  - `copilot` CLI の対話モードは TTY 前提の TUI のため、QProcess（パイプ stdin/stdout）
    では入力/出力が成立しない。旧実装が応答しなかった主因はこの非互換。
  - 本実装は送信ごとに **非インタラクティブ `-p/--prompt` モード** で `copilot` を
    spawn し、stdout をパネルへ流し込む。
  - リポジトリと実行中ワークフローのデータ（`work/`, `session-state/`, `docs/` 等）を
    参照可能にするため、リポジトリルートで起動 (`-C`) する。`-C` 配下は自動的に
    アクセス許可されるため `--add-dir` は付与しない。
  - 非インタラクティブ実行には `--allow-all-tools` が必須（公式ヘルプ参照）。

セキュリティ:
  - `QProcess.start(program, args)` を直接呼ぶ（シェル経由ではない）ため shell injection は発生しない。
  - 入力長は 8KB に制限。
  - 既知の制約: Windows では `copilot` 実体が `.CMD` シムのため、プロンプト中の
    `"`/`^`/`&`/`|` などは Qt 6 のクォーティングを経た上で cmd.exe に再解釈される。
    意図しない展開リスクがあるためユーザーへ status 行で注意喚起する。

根拠:
  - `copilot --help` 出力（`-p/--prompt`, `--allow-all-tools`, `--add-dir`, `-C`,
    `--no-ask-user` の存在を確認）。
  - GitHub Copilot CLI 公式: https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .fonts import preferred_log_font


_MAX_INPUT_BYTES = 8 * 1024


class CopilotChatPanel(QDockWidget):
    """右側にドッキングするチャットパネル。

    送信のたびに `copilot -p <prompt> --allow-all-tools --no-ask-user -C <repo>` を
    非インタラクティブモードで起動し、stdout/stderr をマージして表示する。
    """

    def __init__(  # noqa: D401
        self,
        parent: Optional[QWidget] = None,
        *,
        repo_root: Optional[Path] = None,
    ) -> None:
        super().__init__("GitHub Copilot Chat", parent)
        self.setObjectName("CopilotChatDock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )

        self._repo_root: Path = Path(repo_root) if repo_root else Path.cwd()

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._status = QLabel()
        self._status.setStyleSheet("color: #424242;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._history = QPlainTextEdit()
        self._history.setReadOnly(True)
        self._history.setFont(preferred_log_font(10))
        layout.addWidget(self._history, stretch=1)

        input_row = QHBoxLayout()
        input_label = QLabel(self.tr("メッセージ:"))
        input_label.setMaximumWidth(280)
        self._input = QLineEdit()
        self._input.setPlaceholderText(self.tr("メッセージを入力して Enter で送信..."))
        self._input.returnPressed.connect(self._on_send)
        self._send_btn = QPushButton(self.tr("送信"))
        self._send_btn.clicked.connect(self._on_send)
        self._stop_btn = QPushButton(self.tr("停止"))
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)
        input_row.addWidget(input_label, 0)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(self._send_btn)
        input_row.addWidget(self._stop_btn)
        layout.addLayout(input_row)

        self.setWidget(container)
        self.resize(420, 600)

        self._process: Optional[QProcess] = None
        self._copilot_path: Optional[str] = shutil.which("copilot")
        self._update_status()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_repo_root(self, repo_root: Path) -> None:
        """リポジトリルートを更新する（ワークフロー切替時に呼び出し可）。"""
        self._repo_root = Path(repo_root)
        self._update_status()

    # ------------------------------------------------------------------
    # 状態表示
    # ------------------------------------------------------------------

    def _update_status(self) -> None:
        if self._copilot_path is None:
            self._status.setText(
                self.tr("⚠️ `copilot` コマンドが見つかりません。\n"
                "インストール: https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli")
            )
            self._input.setEnabled(False)
            self._send_btn.setEnabled(False)
        else:
            self._status.setText(
                f"✅ Copilot CLI: {self._copilot_path}\n"
                f"📁 Context: {self._repo_root}\n"
                "⚠️ 非対話モード (`-p` + `--allow-all-tools` + `--no-ask-user`) で実行します。\n"
                "   Copilot がツール実行（ファイル書込・コマンド実行等）を確認なしで行います。"
            )

    # ------------------------------------------------------------------
    # 送受信
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        if len(text.encode("utf-8")) > _MAX_INPUT_BYTES:
            self._append("system", f"入力が長すぎます (上限 {_MAX_INPUT_BYTES} バイト)")
            return
        if self._copilot_path is None:
            self._append("system", "copilot CLI が利用できません。")
            return
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            self._append("system", "前のリクエストがまだ実行中です。完了をお待ちください。")
            return

        self._append("you", text)
        self._input.clear()

        # `-C` でリポジトリルートに chdir するため、その配下は --add-dir なしで参照可能。
        # work/, session-state/, docs/, knowledge/ もこの中に含まれる。
        args: list[str] = [
            "-p",
            text,
            "--allow-all-tools",
            "--no-ask-user",
            "-C",
            str(self._repo_root),
        ]

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.setWorkingDirectory(str(self._repo_root))
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.errorOccurred.connect(self._on_error)
        proc.finished.connect(self._on_finished)
        self._process = proc

        self._append("system", "実行: copilot -p ... （リポジトリ全体を参照可能）")
        self._set_running(True)
        try:
            proc.start(self._copilot_path, args)
        except Exception as exc:  # pragma: no cover - defensive
            self._append("system", f"起動に失敗しました: {exc}")
            self._set_running(False)
            self._process = None

    def _on_stop(self) -> None:
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.terminate()
            if not self._process.waitForFinished(2000):
                self._process.kill()
            self._append("system", "ユーザー操作により停止しました。")

    def _on_stdout(self) -> None:
        proc = self._process
        if proc is None:
            return
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self._append("copilot", data.rstrip("\n"))

    def _on_error(self, err: QProcess.ProcessError) -> None:
        self._append("system", f"プロセスエラー: {err}")
        # `errorOccurred` 後に `finished` が来ないケース（FailedToStart 等）に備えて
        # UI を必ず解放する。`finished` も来た場合は二重実行になるが副作用なし。
        proc = self._process
        if proc is not None and proc.state() == QProcess.ProcessState.NotRunning:
            self._set_running(False)
            proc.deleteLater()
            self._process = None

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        status_label = (
            "正常終了" if status == QProcess.ExitStatus.NormalExit else "異常終了(クラッシュ)"
        )
        self._append("system", f"完了 (exit={code}, {status_label})")
        self._set_running(False)
        proc = self._process
        if proc is not None:
            proc.deleteLater()
        self._process = None

    def _set_running(self, running: bool) -> None:
        self._send_btn.setEnabled(not running)
        self._input.setEnabled(not running)
        self._stop_btn.setEnabled(running)

    def _append(self, role: str, text: str) -> None:
        prefix = {
            "you": "[あなた]",
            "copilot": "[Copilot]",
            "system": "[system]",
        }.get(role, role)
        self._history.appendPlainText(f"{prefix} {text}")
        scrollbar = self._history.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    # ------------------------------------------------------------------
    # 終了処理
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """ウィンドウクローズ時に呼ばれる。"""
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.terminate()
            if not self._process.waitForFinished(3000):
                self._process.kill()
                self._process.waitForFinished(1000)
