"""hve.gui.widgets.terminal_session — PtySession と端末ビューを繋ぐ配線層。

:class:`hve.gui.pty_backend.PtySession`（子プロセスの PTY）と
:class:`hve.gui.widgets.xterm_terminal_view.XtermTerminalView`（xterm.js 描画）を
結線し、双方向のデータ受け渡しと終了検知を行う。

配線内容:
        - 専用 ``QThread`` 上の ``QTimer`` ポーリング（既定 20ms）で
            ``session.read_nowait()`` の出力を読み、GUI スレッドで
            ``view.feed_output()`` へ流す。
    - ``view.user_input`` シグナル（端末入力）を ``session.write()`` へ転送。
    - ``view.resized`` シグナル（端末サイズ変更）を ``session.resize()`` へ転送。
    - 子プロセス終了を検知したら残出力をドレインし ``finished(exit_code)`` を発火。

本クラスは ``XtermTerminalView`` の具象に依存せず、``feed_output`` メソッドと
``user_input`` / ``resized`` シグナルを持つ任意の ``QObject`` を ``view`` として
受け取る（QWebEngine 非依存で単体テスト可能にするため）。

Windows の ``pywinpty`` は ``read_nowait`` が短時間ブロックし得るため、PTY 読み取りは
GUI スレッドではなく worker thread で行う。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

__all__ = ["TerminalSessionController"]


class _TerminalReaderWorker(QObject):
    """PTY セッションを worker thread 上でポーリングする内部 worker。"""

    output_ready = Signal(bytes)
    finished = Signal(int)

    def __init__(self, session, *, poll_interval_ms: int) -> None:
        super().__init__()
        self._session = session
        self._finished_emitted = False
        self._timer = QTimer(self)
        self._timer.setInterval(max(1, int(poll_interval_ms)))
        self._timer.timeout.connect(self._on_poll)

    @Slot()
    def start(self) -> None:
        """PTY 出力ポーリングを開始する。"""
        if not self._finished_emitted and not self._timer.isActive():
            self._timer.start()

    @Slot()
    def _on_poll(self) -> None:
        data = self._safe_read()
        if data:
            self.output_ready.emit(data)
        if not self._session.is_alive():
            # 終了済み: 残バッファを空になるまで吸い出してから確定する。
            while True:
                more = self._safe_read()
                if not more:
                    break
                self.output_ready.emit(more)
            self._finish()

    def _safe_read(self) -> bytes:
        try:
            return self._session.read_nowait()
        except Exception:
            return b""

    def _finish(self) -> None:
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self._timer.stop()
        # exit_code() が稀に None を返す場合は -1（失敗相当）として通知する。
        # exit code 単独では成否を断定せず、呼び出し側で独立に確認すること
        # （gh ログインは B1 ダイアログが ``gh auth token`` 取得で成否を確認する）。
        code = self._session.exit_code()
        self.finished.emit(int(code) if code is not None else -1)
        QThread.currentThread().quit()


class TerminalSessionController(QObject):
    """PTY セッションと端末ビューを結線するコントローラ。

    使い方::

        session = pty_backend.spawn(["gh", "auth", "login"])
        view = XtermTerminalView()
        controller = TerminalSessionController(session, view)
        controller.finished.connect(lambda code: ...)
        view.ready.connect(controller.start)   # xterm 初期化完了後に開始
    """

    # 子プロセス終了時に exit code（取得不能時は -1）を通知する。
    finished = Signal(int)

    def __init__(
        self,
        session,
        view,
        *,
        poll_interval_ms: int = 20,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._view = view
        self._finished_emitted = False
        self._stopped = False

        self._thread = QThread(self)
        self._worker = _TerminalReaderWorker(
            session,
            poll_interval_ms=poll_interval_ms,
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.start)
        self._worker.output_ready.connect(self._on_output_ready)
        self._worker.finished.connect(self._on_worker_finished)
        self._thread.finished.connect(self._worker.deleteLater)

        # ビュー → PTY 方向は GUI スレッドから直接書き込む。
        # Windows の pywinpty read() は worker thread 上でブロックし得るため、
        # 同じ worker event loop に write/resize/stop を queued 接続すると、
        # gh の入力待ち中に入力が届かずデッドロックする。
        view.user_input.connect(self._on_user_input)
        view.resized.connect(self._on_resized)

    # ------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------
    def start(self) -> None:
        """ポーリングを開始する。xterm 初期化完了後に呼ぶこと。"""
        if self._finished_emitted or self._stopped or self._thread.isRunning():
            return
        self._thread.start()

    def stop(self) -> None:
        """ポーリングを停止し、子プロセスを穏便に終了させる。"""
        if self._stopped:
            return
        self._stopped = True
        if self._thread.isRunning():
            try:
                self._session.close()
            except Exception:
                pass
            self._thread.quit()
            self._thread.wait(3000)
        else:
            try:
                self._session.close()
            except Exception:
                pass

    # ------------------------------------------------------------
    # 内部スロット
    # ------------------------------------------------------------
    @Slot(bytes)
    def _on_output_ready(self, data: bytes) -> None:
        self._view.feed_output(data)

    @Slot(bytes)
    def _on_user_input(self, data: bytes) -> None:
        try:
            self._session.write(data)
        except Exception:
            # 入力書き込み失敗は致命的でない（端末側にエコーされないだけ）。
            pass

    @Slot(int, int)
    def _on_resized(self, cols: int, rows: int) -> None:
        try:
            self._session.resize(int(cols), int(rows))
        except Exception:
            pass

    @Slot(int)
    def _on_worker_finished(self, code: int) -> None:
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self.finished.emit(int(code))
