"""hve.gui.app — QApplication 起動と複数 MainWindow 管理。

設計書 §9 対応。

エントリポイント: `run_app(argv)` が `hve/__main__.py` の `gui` サブコマンドから呼ばれる。

複数ウィンドウ管理:
  - 起動時に `MainWindow` を 1 つ生成する。
  - 「セッション」→「新規セッション...」で追加 `MainWindow` を開く。
  - 各 `MainWindow` は独立した `subprocess.Popen` を持つ。
  - 全ウィンドウが閉じられると `QApplication` が終了する。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List

from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtCore import QLoggingCategory, QThread, QTimer, Signal

from . import theme as _theme
from .fonts import preferred_ui_font
from .i18n import install_translator, resolve_language
from .main_window import MainWindow
from .settings_store import get_option


# ---------------------------------------------------------------------------
# テーマ適用（全画面）
# ---------------------------------------------------------------------------
# Windows / macOS の既定スタイルはネイティブテーマエンジンで描画するため
# QPalette を全描画には使わない（Qt 公式ドキュメントの警告どおり）。実測では
# ダークパレット適用下でも QLineEdit の背景が windows11 で #bcbdbf、
# windowsvista で #ffffff となり、文字とのコントラストが 1.2〜1.6:1 まで落ちた。
# Qt 同梱スタイルでパレットをそのまま反映するのは Fusion だけなので固定する。
_STYLE_NAME = "Fusion"


def apply_style_to_application() -> None:
    """アプリのスタイルを :data:`_STYLE_NAME` に固定する。"""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    style = QStyleFactory.create(_STYLE_NAME)
    if style is not None:
        app.setStyle(style)


def apply_theme_to_application(theme: str) -> None:
    """QApplication 全体にテーマを適用する。

    Args:
        theme: "dark" | "light"

    パレット（全 ColorRole）とアプリ全体スタイルシートの双方を差し替えるため、
    ``hveRole`` プロパティで配色されたウィジェットも再起動なしで追随する。
    """
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    resolved = _theme.set_current_theme(theme)
    app.setPalette(_theme.build_palette(resolved))
    app.setStyleSheet(_theme.build_stylesheet(resolved))


# モジュールレベルで生存ウィンドウを保持し、参照切れによる予期しない解放を防ぐ
_open_windows: List[MainWindow] = []
_session_counter = [1]

# 差分更新の完了ポーリング間隔。完了検知が遅れても実害は実行開始の待ち時間だけなので短くしない。
_INDEX_REFRESH_POLL_MS = 500
_index_refresh_timer: QTimer | None = None
_resource_snapshot_shared: object = None
_resource_snapshot_started = False
_resource_snapshot_thread: QThread | None = None
_RESOURCE_SNAPSHOT_THREAD_SHUTDOWN_TIMEOUT_MS = 16_000


class _StartupResourceSnapshotThread(QThread):
    done = Signal(object)

    def __init__(self, repo_root: Path, *, force_refresh: bool = False) -> None:
        super().__init__()
        self._repo_root = repo_root
        self._force_refresh = force_refresh

    def run(self) -> None:  # type: ignore[override]
        try:
            from ..toolsearch.resource_inventory import discover_sdk_resources
            from . import settings_store

            options = settings_store.load().get("options", {})
            snapshot = discover_sdk_resources(
                working_directory=self._repo_root,
                cli_path=str(options.get("cli_path") or "") or None,
                cli_url=str(options.get("cli_url") or "") or None,
                force_refresh=self._force_refresh,
            )
            self.done.emit(snapshot)
        except Exception as exc:
            self.done.emit(exc)


def _empty_resource_snapshot() -> object:
    from ..toolsearch.resource_inventory import ResourceSnapshot

    return ResourceSnapshot(
        plugin_state="unverified",
        mcp_state="unverified",
        skill_state="unverified",
        skill_ownership_state="unverified",
        plugins=(),
        mcp_servers=(),
        skills=(),
    )


def _coerce_resource_snapshot(result: object) -> object:
    required = (
        "plugin_state",
        "mcp_state",
        "skill_state",
        "skill_ownership_state",
        "plugins",
        "mcp_servers",
        "skills",
    )
    if all(hasattr(result, name) for name in required):
        return result
    return _empty_resource_snapshot()


def _project_workiq_capability(snapshot: object) -> object:
    from ..workiq import WorkIQCapability, workiq_capability_from_snapshot

    try:
        return workiq_capability_from_snapshot(snapshot)
    except Exception:
        return WorkIQCapability(
            state="unverified",
            reason_code="unverified",
        )


def _share_resource_snapshot(result: object) -> None:
    """snapshot を全 window へ同期する。``None`` は確認中を表す。"""
    global _resource_snapshot_shared
    snapshot = _coerce_resource_snapshot(result)
    _resource_snapshot_shared = snapshot
    for window in list(_open_windows):
        setter = getattr(window, "set_resource_snapshot", None)
        if not callable(setter):
            continue
        try:
            setter(snapshot)
        except RuntimeError:
            pass


def _on_resource_snapshot_check_finished(result: object) -> None:
    """SDK discovery worker 結果を正規化し、全 window へ共有する。"""
    _share_resource_snapshot(result)


def _release_resource_snapshot_thread(thread: QThread) -> None:
    """完了した static worker の global 参照を解放する。"""
    global _resource_snapshot_thread
    if _resource_snapshot_thread is thread:
        _resource_snapshot_thread = None


def request_resource_snapshot_refresh(
    repo_root: Path | None = None,
    *,
    force_refresh: bool = False,
) -> bool:
    """共有 SDK resource snapshot の再検出を開始する。"""
    global _resource_snapshot_thread
    if _resource_snapshot_thread is not None and _resource_snapshot_thread.isRunning():
        return False
    resolved_repo_root = Path(repo_root) if repo_root is not None else _resolve_repo_root()
    thread = _StartupResourceSnapshotThread(
        resolved_repo_root,
        force_refresh=force_refresh,
    )
    thread.done.connect(_on_resource_snapshot_check_finished)
    thread.finished.connect(lambda t=thread: _release_resource_snapshot_thread(t))
    thread.finished.connect(thread.deleteLater)
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.aboutToQuit.connect(thread.requestInterruption)
    _resource_snapshot_thread = thread
    try:
        thread.start()
    except Exception:
        _resource_snapshot_thread = None
        _share_resource_snapshot(_empty_resource_snapshot())
        thread.deleteLater()
        return False
    return True


def start_startup_resource_snapshot_check(repo_root: Path | None = None) -> bool:
    """GUI process につき 1 回だけ SDK resource snapshot worker を開始する。"""
    global _resource_snapshot_started
    if _resource_snapshot_started:
        return False
    _resource_snapshot_started = True
    return request_resource_snapshot_refresh(repo_root, force_refresh=False)


def _shutdown_resource_workers() -> None:
    """GUI終了時にresource/context workerを取消し、有界時間で回収する。"""
    threads: list[QThread] = []
    seen: set[int] = set()
    try:
        from .toolsearch_settings_section import _ACTIVE_CONTEXT_WORKERS

        context_threads = tuple(_ACTIVE_CONTEXT_WORKERS)
    except Exception:
        context_threads = ()
    for thread in (
        _resource_snapshot_thread,
        *context_threads,
    ):
        if thread is None or id(thread) in seen:
            continue
        seen.add(id(thread))
        threads.append(thread)

    for thread in threads:
        try:
            thread.requestInterruption()
        except RuntimeError:
            pass

    deadline = time.monotonic() + (_RESOURCE_SNAPSHOT_THREAD_SHUTDOWN_TIMEOUT_MS / 1000)
    for thread in threads:
        try:
            is_running = getattr(thread, "isRunning", None)
            if callable(is_running) and not is_running():
                continue
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if remaining_ms and hasattr(thread, "wait"):
                thread.wait(remaining_ms)
        except RuntimeError:
            pass


def _exec_with_resource_cleanup(app: QApplication) -> int:
    """Qt event loop終了後にresource/context workerを回収する。"""
    try:
        return app.exec()
    finally:
        _shutdown_resource_workers()


def start_startup_index_refresh(repo_root: Path) -> bool:
    """FR-GUI-22: 起動時の索引差分更新を開始し、完了を検知して画面を再評価する。

    Returns:
        完了ポーリングを開始したかどうか。
    """
    global _index_refresh_timer

    from .. import index_refresh

    # 既に別経路が開始している場合も実行ボタンを戻す側が必要なのでポーリングする。
    if not (index_refresh.start_background(repo_root) or index_refresh.is_running()):
        return False
    timer = QTimer()
    timer.setInterval(_INDEX_REFRESH_POLL_MS)
    timer.timeout.connect(_on_index_refresh_tick)
    timer.start()
    _index_refresh_timer = timer
    return True


def _on_index_refresh_tick() -> None:
    from .. import index_refresh

    if index_refresh.is_running():
        return
    if _index_refresh_timer is not None:
        _index_refresh_timer.stop()
    for win in list(_open_windows):
        refresh = getattr(win, "_refresh_navigation", None)
        if refresh is None:
            continue
        try:
            refresh()
        except RuntimeError:
            # 既に破棄されたウィンドウ。他のウィンドウの再評価は続ける。
            pass


def _find_repo_root_from(start: Path) -> Path | None:
    """Walk up from ``start`` and return the first ancestor containing
    ``.git`` or ``pyproject.toml``. Returns ``None`` if not found.
    """
    start = start.resolve()
    for d in (start, *start.parents):
        if (d / ".git").exists() or (d / "pyproject.toml").exists():
            return d
    return None


def _resolve_repo_root() -> Path:
    """Locate the repository root.

    1. Walk up from ``Path.cwd()`` looking for ``.git`` / ``pyproject.toml``.
    2. If not found (e.g. GUI launched from an unrelated directory),
       fall back to walking up from this package's install location
       (works for editable installs).
    3. Final fallback: ``Path.cwd()``.

    Used to anchor cwd-relative paths (e.g. ``.mdq/index.sqlite``) to the
    actual repository regardless of where the GUI was launched from.
    """
    root = _find_repo_root_from(Path.cwd())
    if root is not None:
        return root
    pkg_root = _find_repo_root_from(Path(__file__).resolve().parent)
    if pkg_root is not None:
        return pkg_root
    return Path.cwd().resolve()


def _configure_qt_logging() -> None:
    """無害な ``qt.text.font.db`` フォントフォールバック警告を抑止する。

    エージェント出力に文字化けで混入した Devanagari/Bengali 等の文字を
    ログビューが描画する際、Windows の既定フォント列が当該スクリプトの
    OpenType 整形テーブルを持たないため Qt が ``qt.text.font.db: OpenType
    support missing for ...`` を出力する。Qt は適切なフォントへフォールバック
    して正しく描画するため機能影響はなく、ターミナルを汚すノイズのみが問題となる。

    ``qt.text.font.db.warning=false``（warning レベルのみ無効化）では当該
    メッセージは抑止されない（実測で確認済み）ため、カテゴリ全体を無効化する。
    本カテゴリはフォント DB の診断ログ専用であり、無効化してもアプリの挙動や
    他カテゴリのログには影響しない。
    """
    QLoggingCategory.setFilterRules("qt.text.font.db=false")


def run_app(args=None) -> int:
    """GUI モードのエントリポイント。

    Args:
        args: ``argparse.Namespace`` または ``None``。
            ``autopilot_child=True`` のとき、Wizard をバイパスして子 Workbench を
            直接起動する。

    Returns:
        プロセス終了コード（0 = 正常、2 = 引数不正等）
    """
    _configure_qt_logging()

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])

    app.setApplicationName("HVE GUI Orchestrator")
    app.setApplicationDisplayName("HVE GUI Orchestrator")

    apply_style_to_application()

    try:
        stored_lang = get_option("language")
    except Exception:
        stored_lang = None
    language = resolve_language(stored_lang if isinstance(stored_lang, str) else None)
    install_translator(app, language)

    if sys.platform == "win32":
        app.setFont(preferred_ui_font(10))

    try:
        _initial_theme = get_option("theme") or "light"
    except Exception:
        _initial_theme = "light"
    apply_theme_to_application(_initial_theme)

    # Autopilot 子モード分岐
    if args is not None and getattr(args, "autopilot_child", False):
        rc = _open_autopilot_child_window(args)
        if rc != 0:
            return rc
        start_startup_resource_snapshot_check(_resolve_repo_root())
        return _exec_with_resource_cleanup(app)

    initial_catalog = getattr(args, "app_arch_catalog", None) if args is not None else None
    _open_first_window(initial_catalog=initial_catalog)
    repo_root = _resolve_repo_root()
    start_startup_resource_snapshot_check(repo_root)
    _run_startup_github_auth()
    start_startup_index_refresh(repo_root)
    return _exec_with_resource_cleanup(app)


def _run_startup_github_auth() -> None:
    """FR-GUI-24: 起動時に GitHub 認証を解決し、未解決ならログイン導線を提示する。

    認証の完了は GUI 起動の前提条件ではないため、ここでの失敗は起動を妨げない。
    """
    from . import startup_auth

    parent = _open_windows[0] if _open_windows else None
    try:
        startup_auth.ensure_startup_authentication(parent)
    except Exception as exc:  # noqa: BLE001 - 起動継続のため型を限定しない
        print(f"[hve.gui] GitHub 認証の解決に失敗しました: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Autopilot 子モード
# ---------------------------------------------------------------------------

_ALLOWED_AUTOPILOT_WORKFLOWS = {"aad-web", "asdw-web", "adfd", "adfdv"}


def _open_autopilot_child_window(args) -> int:
    """``--autopilot-child`` で起動された子 GUI ウィンドウを開く。"""
    from .workbench_window import WorkbenchWindow
    from .wizard import WizardResult

    app_id = (getattr(args, "app_id", None) or "").strip()
    chain_str = (getattr(args, "chain", None) or "").strip()
    catalog = getattr(args, "app_arch_catalog", None) or ""

    if not app_id:
        print("[hve.gui] --autopilot-child requires --app-id", file=sys.stderr)
        return 2
    if not chain_str:
        print("[hve.gui] --autopilot-child requires --chain", file=sys.stderr)
        return 2
    chain = [c.strip() for c in chain_str.split(",") if c.strip()]
    if not chain:
        print("[hve.gui] --chain is empty after parsing", file=sys.stderr)
        return 2
    invalid = [c for c in chain if c not in _ALLOWED_AUTOPILOT_WORKFLOWS]
    if invalid:
        print(
            f"[hve.gui] --chain contains unsupported workflow(s): {invalid}."
            f" Allowed: {sorted(_ALLOWED_AUTOPILOT_WORKFLOWS)}",
            file=sys.stderr,
        )
        return 2

    result = WizardResult(
        workflow=chain[0],
        app_id=app_id,
        autopilot_chain=chain,
        autopilot_child=True,
    )
    win = WorkbenchWindow(result, session_index=_session_counter[0])
    win.show()
    _open_windows.append(win)
    win.destroyed.connect(lambda _obj=None, w=win: _on_window_destroyed(w))
    if catalog:
        try:
            win._log_pane.append_line(f"[autopilot-child] catalog: {catalog}")
        except Exception:
            pass
    return 0


def _open_first_window(initial_catalog: str | None = None) -> None:
    """最初の MainWindow を開く。"""
    repo_root = _resolve_repo_root()
    win = MainWindow(
        session_index=_session_counter[0],
        on_new_session=_open_additional_window,
        repo_root=repo_root,
    )
    setter = getattr(win, "set_resource_snapshot", None)
    if callable(setter):
        setter(_resource_snapshot_shared)
    if initial_catalog:
        try:
            win._page_workflow.set_autopilot_catalog_path(initial_catalog)
        except Exception:
            pass
    win.show()
    win._on_login_clicked()
    _open_windows.append(win)
    win.destroyed.connect(lambda _obj=None, w=win: _on_window_destroyed(w))


def _open_additional_window() -> None:
    """「新規セッション」コールバックから呼ばれる。"""
    _session_counter[0] += 1
    repo_root = _resolve_repo_root()
    win = MainWindow(
        session_index=_session_counter[0],
        on_new_session=_open_additional_window,
        repo_root=repo_root,
    )
    setter = getattr(win, "set_resource_snapshot", None)
    if callable(setter):
        setter(_resource_snapshot_shared)
    win.show()
    _open_windows.append(win)
    win.destroyed.connect(lambda _obj=None, w=win: _on_window_destroyed(w))


def _on_window_destroyed(window: MainWindow) -> None:
    if window in _open_windows:
        _open_windows.remove(window)
