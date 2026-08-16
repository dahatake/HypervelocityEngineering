"""hve.gui.copilot_interactive_session — GitHub Copilot CLI 対話セッションの薄い adapter。

FR-GUI-10 / FR-GUI-11。既存の PTY 抽象（[hve/gui/pty_backend.py]）と端末結線
（[hve/gui/widgets/terminal_session.py]）を再利用し、`copilot` の対話 TUI を
1 プロセスとして起動・維持する。CLI の画面出力は解釈せず、セッション管理・
モデル選択・ツール権限・MCP / Plugin / Skill の管理はすべて CLI に委ねる。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, Signal

from . import pty_backend
from .copilot_cli_bridge import CopilotCliBridge
from .widgets.terminal_session import TerminalSessionController

__all__ = [
    "CopilotInteractiveSession",
    "CopilotInteractiveSessionError",
    "build_interactive_argv",
]


class CopilotInteractiveSessionError(RuntimeError):
    """対話セッションを開始できない場合に送出する（fail-closed）。"""


def build_interactive_argv(
    binary: str,
    repo_root: Path,
    *,
    initial_prompt: Optional[str] = None,
) -> List[str]:
    """対話モードの `copilot` 起動引数を組み立てる。

    権限緩和フラグ（`--allow-all*` / `--yolo` / `--no-ask-user`）と使い捨て実行
    （`-p`）は付与しない（FR-GUI-11）。初期プロンプトは対話モード用 `-i` へ
    1 個の引数として渡し、シェル文字列へ連結しない。
    """
    argv = [str(binary), "-C", str(repo_root), "--no-auto-update"]
    if initial_prompt is not None and str(initial_prompt).strip():
        argv += ["-i", str(initial_prompt)]
    return argv


class _ViewRelay(QObject):
    """1 回の起動に対応する端末ビューの中継。

    `TerminalSessionController` は生成時にビューの signal へ接続するため、
    再起動のたびに実ビューへ直接接続すると接続が累積する。起動ごとに使い捨ての
    中継を挟むことで、停止したセッションの接続を残さない。
    """

    user_input = Signal(bytes)
    resized = Signal(int, int)

    def __init__(self, view) -> None:
        super().__init__()
        self._view = view

    def feed_output(self, data: bytes) -> None:
        self._view.feed_output(data)


class CopilotInteractiveSession(QObject):
    """`copilot` 対話プロセスと端末ビューを結ぶセッション。"""

    finished = Signal(int)

    def __init__(
        self,
        view,
        *,
        repo_root: Path,
        binary_resolver: Optional[Callable[[], Optional[str]]] = None,
        pty_available: Optional[Callable[[], bool]] = None,
        spawn: Optional[Callable[..., object]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._view = view
        self._repo_root = Path(repo_root)
        self._binary_resolver = binary_resolver or CopilotCliBridge.find_binary
        self._pty_available = pty_available or pty_backend.is_pty_available
        self._spawn = spawn or pty_backend.spawn
        self._controller: Optional[TerminalSessionController] = None
        self._relay: Optional[_ViewRelay] = None

        view.user_input.connect(self._forward_input)
        view.resized.connect(self._forward_resize)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_repo_root(self, repo_root: Path) -> None:
        self._repo_root = Path(repo_root)

    def is_running(self) -> bool:
        return self._controller is not None

    def start(self, *, initial_prompt: Optional[str] = None) -> None:
        """対話セッションを開始する。実行中の場合は何もしない。

        Raises:
            CopilotInteractiveSessionError: CLI / PTY backend が解決できない、
                またはプロセス起動に失敗した場合。
        """
        if self._controller is not None:
            return

        binary = self._binary_resolver()
        if not binary:
            raise CopilotInteractiveSessionError(
                "GitHub Copilot CLI が見つかりません。"
                f"推奨: {pty_backend.setup_command()} を実行してセットアップしてください。"
            )
        if not self._pty_available():
            raise CopilotInteractiveSessionError(pty_backend.missing_dependency_hint())

        argv = build_interactive_argv(binary, self._repo_root, initial_prompt=initial_prompt)
        try:
            pty_session = self._spawn(argv, cwd=str(self._repo_root))
        except Exception as exc:
            raise CopilotInteractiveSessionError(
                f"Copilot CLI の対話セッションを開始できませんでした: {exc}"
            ) from exc

        relay = _ViewRelay(self._view)
        controller = TerminalSessionController(pty_session, relay, parent=self)
        controller.finished.connect(self._on_finished)
        self._relay = relay
        self._controller = controller
        controller.start()

    def stop(self) -> None:
        """対話セッションを停止する。未起動の場合は何もしない。"""
        controller = self._controller
        self._clear()
        if controller is not None:
            controller.stop()
            controller.deleteLater()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _clear(self) -> None:
        self._controller = None
        self._relay = None

    def _forward_input(self, data: bytes) -> None:
        relay = self._relay
        if relay is not None:
            relay.user_input.emit(data)

    def _forward_resize(self, cols: int, rows: int) -> None:
        relay = self._relay
        if relay is not None:
            relay.resized.emit(int(cols), int(rows))

    def _on_finished(self, code: int) -> None:
        self._clear()
        self.finished.emit(int(code))
