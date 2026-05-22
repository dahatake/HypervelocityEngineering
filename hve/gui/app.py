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
from pathlib import Path
from typing import List

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor

from .fonts import preferred_ui_font
from .i18n import install_translator, resolve_language
from .main_window import MainWindow
from .settings_store import get_option


# ---------------------------------------------------------------------------
# テーマ適用（全画面）
# ---------------------------------------------------------------------------
_LIGHT_PALETTE_COLORS = {
    QPalette.Window: "#f3f3f3",
    QPalette.WindowText: "#1f2328",
    QPalette.Base: "#ffffff",
    QPalette.AlternateBase: "#f6f8fa",
    QPalette.Text: "#1f2328",
    QPalette.Button: "#f3f3f3",
    QPalette.ButtonText: "#1f2328",
    QPalette.Highlight: "#0969da",
    QPalette.HighlightedText: "#ffffff",
    QPalette.ToolTipBase: "#ffffff",
    QPalette.ToolTipText: "#1f2328",
}
_DARK_PALETTE_COLORS = {
    QPalette.Window: "#1f2328",
    QPalette.WindowText: "#e6edf3",
    QPalette.Base: "#0d1117",
    QPalette.AlternateBase: "#161b22",
    QPalette.Text: "#e6edf3",
    QPalette.Button: "#21262d",
    QPalette.ButtonText: "#e6edf3",
    QPalette.Highlight: "#58a6ff",
    QPalette.HighlightedText: "#0d1117",
    QPalette.ToolTipBase: "#21262d",
    QPalette.ToolTipText: "#e6edf3",
}


def apply_theme_to_application(theme: str) -> None:
    """QApplication 全体にテーマを適用する。

    Args:
        theme: "dark" | "light"

    QPalette ベースで安全に切り替え、全 Top-Level Window に反映される。
    """
    app = QApplication.instance()
    if app is None:
        return
    palette = QPalette()
    colors = _DARK_PALETTE_COLORS if theme == "dark" else _LIGHT_PALETTE_COLORS
    for role, hexstr in colors.items():
        palette.setColor(role, QColor(hexstr))
    app.setPalette(palette)


# モジュールレベルで生存ウィンドウを保持し、参照切れによる予期しない解放を防ぐ
_open_windows: List[MainWindow] = []
_session_counter = [1]


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


def run_app(args=None) -> int:
    """GUI モードのエントリポイント。

    Args:
        args: ``argparse.Namespace`` または ``None``。
            ``autopilot_child=True`` のとき、Wizard をバイパスして子 Workbench を
            直接起動する。

    Returns:
        プロセス終了コード（0 = 正常、2 = 引数不正等）
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])

    app.setApplicationName("HVE GUI Orchestrator")
    app.setApplicationDisplayName("HVE GUI Orchestrator")

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
        return app.exec()

    initial_catalog = getattr(args, "app_arch_catalog", None) if args is not None else None
    _open_first_window(initial_catalog=initial_catalog)
    return app.exec()


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
    if initial_catalog:
        try:
            win._page_workflow.set_autopilot_catalog_path(initial_catalog)
        except Exception:
            pass
    win.show()
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
    win.show()
    _open_windows.append(win)
    win.destroyed.connect(lambda _obj=None, w=win: _on_window_destroyed(w))


def _on_window_destroyed(window: MainWindow) -> None:
    if window in _open_windows:
        _open_windows.remove(window)
