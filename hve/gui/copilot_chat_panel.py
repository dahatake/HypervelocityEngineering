"""hve.gui.copilot_chat_panel — GitHub Copilot CLI と対話するドックパネル。

設計（改訂版）:
  - `copilot` CLI の対話モードは TTY 前提の TUI のため、QProcess（パイプ stdin/stdout）
    では入力/出力が成立しない。旧実装が応答しなかった主因はこの非互換。
  - 本実装は送信ごとに **非インタラクティブ `-p/--prompt` モード** で `copilot` を
    spawn し、stdout をパネルへ流し込む。
  - リポジトリと実行中ワークフローのデータ（`work/`, `docs/` 等）を
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

import codecs
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
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
from .steering_ipc_writer import write_steering_request
from .widgets.wrap_helpers import apply_cjk_wrap


_MAX_INPUT_BYTES = 8 * 1024

# ANSI CSI/Fe エスケープシーケンス（色付け・カーソル移動・スピナー消去等）の検出用。
# ECMA-48 / VT100 の標準的なパターン（`strip-ansi` 系実装で広く使われる形）:
#   ESC の後に「単一の Fe 文字（@-Z, \, _）」または
#   「`[`(CSI) + パラメータバイト(0-?) + 中間バイト( -/) + 終端バイト(@-~)」が続く。
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _sanitize_stream_text(text: str) -> str:
    """Copilot CLI ストリーミング断片を表示用に正規化する。

    ``QPlainTextEdit`` は端末エミュレータではないため、以下をそのまま挿入すると
    表示が崩れる（合成データ（\\r・ANSI混じりの文字列）を ``_append_copilot_delta``
    へ直接投入するオフスクリーンQt検証で確認済み。実 ``copilot`` CLI プロセスは
    実行していないため、実際に \\r/ANSI を出力するかどうか自体は未確認）。

    - ANSI CSI/Fe エスケープシーケンス: 解釈されず生の制御文字として挿入され、
      グリフ抜け・不可視文字混入の原因になるため除去する。
    - ``\r\n``: ``\n`` へ正規化する（Windows 改行対策）。
    - 単独の ``\r``（行末上書き用途。スピナー等）: ``QPlainTextEdit`` に
      「その場で上書き」する機能はなく、そのまま挿入すると Qt が改段落として
      扱ってしまい、スピナーの全フレームが個別の行として残ってしまう。
      本関数では除去し、後続テキストは直前の内容にそのまま連結させる
      （完全な端末再現ではないが、余分な行の氾濫は防げる）。
    """
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "")
    return text


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
        self._status.setProperty("hveRole", "description")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._history = QPlainTextEdit()
        self._history.setReadOnly(True)
        self._history.setFont(preferred_log_font(10))
        # 他のログ系ペイン（page_workbench.py の _LogPane 等）と同じ折り返しpolicyを
        # 適用する。CJK混在テキストでも横スクロールを発生させず、ウィジェット幅で
        # 折り返す（WrapAtWordBoundaryOrAnywhere）。
        apply_cjk_wrap(self._history)
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

        # Steering（実行中ワークフローへの割り込み送信）トグル。既定 OFF。
        # 対象ワークフローが単一 step 実行中かつ IPC ディレクトリが利用可能な
        # 場合のみ有効化する（不明点2・8）。
        self._steering_checkbox = QCheckBox(
            self.tr("実行中ワークフローへ割り込む (Steering)")
        )
        self._steering_checkbox.setEnabled(False)
        self._steering_checkbox.setToolTip(
            self.tr("単一ステップ実行中のワークフローが無いため利用できません。")
        )
        layout.addWidget(self._steering_checkbox)

        self.setWidget(container)
        self.resize(420, 600)

        self._process: Optional[QProcess] = None
        self._copilot_path: Optional[str] = shutil.which("copilot")
        # Copilot応答のストリーミング表示用状態（断片ごとの改行を防ぎ、実データ中の
        # 実際の改行のみを段落区切りとして扱うための状態）。
        self._utf8_decoder: Optional[codecs.IncrementalDecoder] = None
        self._copilot_turn_open: bool = False

        # Steering 機能: WorkbenchPage への参照（main_window.py から
        # set_workbench_page() 経由で注入される）。
        self._workbench_page: Optional[Any] = None
        self._steering_poll_timer = QTimer(self)
        self._steering_poll_timer.setInterval(1000)
        self._steering_poll_timer.timeout.connect(self._update_steering_availability)
        self._steering_poll_timer.start()

        self._update_status()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_repo_root(self, repo_root: Path) -> None:
        """リポジトリルートを更新する（ワークフロー切替時に呼び出し可）。"""
        self._repo_root = Path(repo_root)
        self._update_status()

    def set_workbench_page(self, page: Any) -> None:
        """Steering 機能用に WorkbenchPage への参照を設定する。

        ``main_window.py`` の WorkbenchPage 生成直後に呼び出される。
        ``page`` は ``resolve_active_main_step_id()`` / ``active_steering_ipc_dir()``
        の 2 メソッドを持つオブジェクトを期待する（duck typing、テスト用フェイクでも可）。
        """
        self._workbench_page = page
        self._update_steering_availability()

    # ------------------------------------------------------------------
    # Steering（実行中ワークフローへの割り込み送信）
    # ------------------------------------------------------------------

    def _update_steering_availability(self) -> None:
        """WorkbenchPage の状態を見て Steering トグルの有効/無効を更新する。

        単一ステップ実行中かつ IPC ディレクトリが利用可能な場合のみ有効化する
        （不明点2: 並列実行時は無効化、不明点8: フォールバックはボタン無効化）。
        """
        page = self._workbench_page
        step_id: Optional[str] = None
        ipc_dir: Optional[str] = None
        if page is not None:
            try:
                step_id = page.resolve_active_main_step_id()
                ipc_dir = page.active_steering_ipc_dir()
            except Exception:
                step_id = None
                ipc_dir = None
        available = bool(step_id) and bool(ipc_dir)
        self._steering_checkbox.setEnabled(available)
        if not available:
            self._steering_checkbox.setChecked(False)
            self._steering_checkbox.setToolTip(
                self.tr("単一ステップ実行中のワークフローが無いため利用できません。")
            )
        else:
            self._steering_checkbox.setToolTip(
                self.tr("ON: 送信内容は実行中ステップ ({step}) への割り込みメッセージとして送信されます。").format(
                    step=step_id
                )
            )

    def _send_steering_message(self, text: str) -> bool:
        """Steering IPC ファイルへ書き込む。成功すれば True を返す。"""
        page = self._workbench_page
        if page is None:
            return False
        try:
            step_id = page.resolve_active_main_step_id()
            ipc_dir = page.active_steering_ipc_dir()
        except Exception:
            return False
        if not step_id or not ipc_dir:
            return False
        try:
            write_steering_request(Path(ipc_dir), step_id, text)
        except OSError as exc:
            self._append("system", f"Steering 送信に失敗しました: {exc}")
            return False
        self._append(
            "system",
            f"⚡ Steering: 実行中ステップ ({step_id}) へ割り込みメッセージを送信しました。"
            " 応答はワークフロー実行ログに反映されます。",
        )
        return True

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

        # Steering トグルが ON の場合は IPC 書き込みのみで完結し、既存の
        # 使い捨て copilot -p 経路（QProcess）は使わない。
        if self._steering_checkbox.isChecked():
            self._append("you", text)
            self._input.clear()
            self._send_steering_message(text)
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
        # work/, docs/, knowledge/ もこの中に含まれる。
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
        # 新しいリクエストごとにデコーダとストリーミング状態をリセットする。
        self._utf8_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._copilot_turn_open = False

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
            self._finalize_copilot_stream()
            self._append("system", "ユーザー操作により停止しました。")

    def _on_stdout(self) -> None:
        proc = self._process
        if proc is None:
            return
        raw = bytes(proc.readAllStandardOutput())
        if not raw:
            return
        if self._utf8_decoder is None:
            self._utf8_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        # マルチバイト文字が読み取り境界で分割されても、IncrementalDecoder が
        # 未確定分を内部保持するため文字化けしない。
        text = self._utf8_decoder.decode(raw)
        if text:
            self._append_copilot_delta(text)

    def _on_error(self, err: QProcess.ProcessError) -> None:
        self._finalize_copilot_stream()
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
        self._finalize_copilot_stream()
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
        # you/system の発言は常に新しい段落として扱うため、進行中の Copilot
        # ストリーミング段落があればここで閉じる（次の Copilot 応答は新規段落から
        # 再開する）。
        self._copilot_turn_open = False
        cursor = QTextCursor(self._history.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self._history.document().isEmpty():
            # ユーザーの新規発言（you）の前のみ空行を挿入し、会話のターン境界を
            # 視覚的に明確にする。systemはステータス注記に近いので詰めて表示する。
            cursor.insertText("\n\n" if role == "you" else "\n")
        cursor.insertText(f"{prefix} {text}")
        self._autoscroll()

    def _append_copilot_delta(self, delta: str) -> None:
        """Copilot 応答のストリーミング断片を、現在の応答段落へ連結して追記する。

        ``QPlainTextEdit.appendPlainText`` は呼ぶたびに新しい段落を作ってしまうため
        （Qt仕様）、ここではカーソルを文末へ移動して ``insertText`` で追記する。
        断片自体の到着境界が新しい行を作ることはなく、``delta`` 内に実際の改行
        (``\n``) が含まれる場合のみ新しい段落になる。

        ターン開始時（``_copilot_turn_open`` が ``False`` から ``True`` になる瞬間）のみ
        空行を挿入して会話のターン境界を明確にする（``_append`` の you と対の仕様）。

        Note:
            ``self._history.textCursor()``（ウィジェットの対話用カーソル）ではなく
            ``QTextCursor(self._history.document())`` で**独立したカーソル**を
            生成して編集する。ウィジェット側のカーソルを操作すると、ユーザーが
            ログをドラッグ選択してコピーしようとしている最中に選択範囲が毎回
            末尾へ強制移動されてしまう（読み取り専用でもカーソル移動・選択は可能）。
            文書末尾への追記は、それより前にある既存の選択範囲の位置に影響しない。
        """
        delta = _sanitize_stream_text(delta)
        if not delta:
            return
        cursor = QTextCursor(self._history.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self._copilot_turn_open:
            if not self._history.document().isEmpty():
                cursor.insertText("\n\n")
            cursor.insertText("[Copilot] ")
            self._copilot_turn_open = True
        cursor.insertText(delta)
        self._autoscroll()

    def _autoscroll(self) -> None:
        """履歴ビューを最新行が見えるよう末尾までスクロールする。"""
        scrollbar = self._history.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())

    def _finalize_copilot_stream(self) -> None:
        """ストリーミング用デコーダに残る未確定バイト列を flush する。

        プロセスの終了/停止/エラー時に呼び出す。マルチバイト文字の末尾断片が
        途中で打ち切られた場合でも、確定できる範囲を表示に反映してから破棄する。
        デコーダは常に ``errors="replace"`` で生成しているため ``decode()`` が
        ``UnicodeDecodeError`` を送出することはない。
        """
        if self._utf8_decoder is None:
            return
        remainder = self._utf8_decoder.decode(b"", final=True)
        if remainder:
            self._append_copilot_delta(remainder)
        self._utf8_decoder = None

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
