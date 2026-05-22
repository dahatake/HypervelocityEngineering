"""hve.gui.main_window — 3 ステップ単一ウィンドウ (MainWindow)。

設計書 §3 / §11.2 U1 対応。

レイアウト:
  QMainWindow
  └── QWidget (central)
      └── QVBoxLayout
          ├── HeaderBar              (§4)
          ├── QStackedWidget          (2 ステップの切替)
          │   ├── WorkflowSelectPage (Step 1: ワークフローの選択 — 右ペインに OptionsPage を埋め込み)
          │   └── WorkbenchPage       (Step 2: 実行)
          ├── StatusBanner            (全幅ステータス: {状況} {説明文})
          └── NavigationBar           ([戻る] / [次へ] / [実行])

ナビゲーション:
  - Step 1: [次へ] — 未選択時無効。precheck PASS でそのまま実行起動
  - Step 2: [戻る]（実行中不可）/ [停止]

メニュー:
  - 「セッション」→「新規セッション...」: 別ウィンドウを開く
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .header_bar import HeaderBar
from .copilot_chat_panel import CopilotChatPanel
from .page_options import OptionsPage
from .page_workbench import WorkbenchPage
from .page_workflow_select import WorkflowSelectPage
from .session_menu import build_session_menu
from .settings_window import SettingsWindow
from .auth_monitor import AuthMonitor
from .auth_providers import AuthState
from .auth_providers.registry import discover_providers
from .plugin_auth_dialog import PluginAuthDialog
from hve.workflow_registry import WorkflowDependency, get_meta_dependencies, get_workflow

from .status_banner import StatusBanner
from .status_kind import StatusKind
from .workflow_display import format_workflow_label

# ウィンドウタイトルに名前付きで列挙するワークフロー件数の上限。
# これを超える選択は ID のみ上位で列挙し、超過件数は ``+N more`` として表示する。
_TITLE_MAX_WORKFLOWS = 3  # 旧: タイトル番号表示用定数。現在 _update_title から参照なし。下位互換のため一時残置。
# TODO: 次回クリーンアップで削除する。


# ステップインデックス (2 ステップ構成: ワークフローの選択 / 実行)
_STEP_WORKFLOW = 0
_STEP_WORKBENCH = 1


def _build_step_seeds_for_workflow(workflow_id: str) -> list:
    """``WorkflowDef.steps`` から container 階層を反映した ``StepSeed`` リストを構築する。

    Phase 2 (Q3=B): container Step を親ノードとして展開し、配下の非 container Step を
    ``children`` に格納する。container 同士のネスト（"1" → "1.1" → "1.1.2"）にも対応する。

    親子判定ルール:
      - 各 Step ID の dotted prefix を逆順に試し、登録済みステップ ID と一致したものを親とする
        （例: "2.3T" → 親候補 "2.3"（存在しなければ）→ "2"）。
      - 親が見つからない場合は workflow 直下のトップレベル Step として返す。
      - 子を持たない container は表示価値が無いため除去する。
    """
    from .workbench_state import StepSeed

    wf = get_workflow(workflow_id)
    if wf is None:
        return []
    step_ids = {s.id for s in wf.steps}

    def _parent_id(step_id: str):
        if "." not in step_id:
            return None
        head, _ = step_id.rsplit(".", 1)
        while head:
            if head in step_ids:
                return head
            if "." not in head:
                return None
            head, _ = head.rsplit(".", 1)
        return None

    seed_by_id: Dict[str, "StepSeed"] = {}
    top_level: list = []
    for s in wf.steps:
        kind = "container" if getattr(s, "is_container", False) else "step"
        seed_by_id[s.id] = StepSeed(id=s.id, title=s.title, kind=kind)

    for s in wf.steps:
        seed = seed_by_id[s.id]
        parent = _parent_id(s.id)
        if parent is not None and parent in seed_by_id:
            seed_by_id[parent].children.append(seed)
        else:
            top_level.append(seed)

    def _prune_empty_containers(seeds: list) -> list:
        result = []
        for s in seeds:
            s.children = _prune_empty_containers(s.children)
            if s.kind == "container" and not s.children:
                continue
            result.append(s)
        return result

    return _prune_empty_containers(top_level)


def _sort_workflows_by_dependencies(selected_workflows: List[str]) -> List[str]:
    """選択ワークフローを依存関係に基づいて安定ソートする。"""
    selected = [w for w in selected_workflows if w]
    if len(selected) <= 1:
        return selected

    index_by_wf = {wf: i for i, wf in enumerate(selected)}
    edges: Dict[str, List[str]] = {wf: [] for wf in selected}
    indegree: Dict[str, int] = {wf: 0 for wf in selected}

    for wf in selected:
        deps = get_meta_dependencies(wf)
        for dep in deps:
            dep_wf = dep.workflow_id
            if dep_wf not in indegree:
                continue
            edges[dep_wf].append(wf)
            indegree[wf] += 1

    ready = [wf for wf, deg in indegree.items() if deg == 0]
    ready.sort(key=lambda w: index_by_wf[w])

    ordered: List[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for nxt in edges[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
                ready.sort(key=lambda w: index_by_wf[w])

    if len(ordered) != len(selected):
        raise ValueError("選択されたワークフロー間に循環依存があります。")

    return ordered


class MainWindow(QMainWindow):
    """3 ステップ単一ウィンドウ。

    Args:
        session_index: 複数ウィンドウ時の番号（タイトルに表示）
        on_new_session: 「新規セッション」メニューから呼ばれるコールバック（任意）
        repo_root: リポジトリルート（添付ファイル保存先などで使用）
    """

    def __init__(
        self,
        *,
        session_index: int = 1,
        on_new_session: Optional[Callable[[], None]] = None,
        repo_root: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._session_index = session_index
        self._on_new_session = on_new_session
        self._repo_root = repo_root or Path.cwd()
        self._selected_workflow_ids: List[str] = []
        self._autopilot_controller: Optional[object] = None
        # Step 1 統合 precheck のプランレビュー反復回数。
        # 旧名: _autopilot_plan_review_iterations。両モード共通カウンタへ統合した際にリネーム。
        self._step1_plan_review_iterations: int = 0
        # T12 (Wave 4 / A1) — 起動時 GitHub 認証強制モーダル進行中フラグ。
        # 現状参照は無いが、デバッグ・将来の closeEvent ガード等で利用可。
        self._startup_auth_blocking: bool = False

        # Issue-gui-session-workdir-isolation T5a/T9:
        # MainWindow 1 インスタンス = 1 GUI セッションとして、独立した
        # work/gui-runs/<session_run_id>/ を生成し、HVE_WORK_ROOT を子プロセス
        # に伝播する。設定値が読み取れない初期化タイミングでは "keep" 既定。
        try:
            from . import settings_store as _ss

            _policy = (_ss.get_option("gui_session_cleanup_policy") or "keep")
        except Exception:
            _policy = "keep"
        from .session_workdir import GuiSessionWorkdir

        self._session_workdir: GuiSessionWorkdir = GuiSessionWorkdir.create(
            self._repo_root,
            cleanup_policy=str(_policy),
        )
        # 起動バナー（Q10/T9）: 子プロセスのログより前に GUI 側で 1 度だけ出す。
        # stderr へ出力することで workbench_logger 系の取り込み経路にも乗せる
        # （Adv. Review Major #5）。失敗は黙殺せず stderr に出す（Major #11）。
        try:
            import sys as _sys

            _banner = (
                f"[gui] session_run_id={self._session_workdir.session_run_id}\n"
                f"[gui] HVE_WORK_ROOT={self._session_workdir.work_root}\n"
                f"[gui] cleanup_policy={self._session_workdir.cleanup_policy}"
            )
            print(_banner, file=_sys.stderr, flush=True)
        except Exception as _exc_banner:
            import sys as _sys

            print(
                f"[gui] session_workdir banner emit failed: {_exc_banner}",
                file=_sys.stderr,
            )

        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()
        # 設定の既定値を Step 2 ウィジェットへ反映
        self._on_settings_changed(None)
        self._refresh_navigation()

        # 横幅は設定に保存された値があればそれを使用、なければ既定 1100。
        # 高さは常に既定 800（要件: 横幅のみ永続化）。
        try:
            from . import settings_store as _ss

            saved_width = int(_ss.get_option("main_window_width") or 0)
        except Exception:
            saved_width = 0
        initial_width = saved_width if saved_width > 0 else 1100
        # B-5: ドラッグでの縮小を保証するための最小幅。
        self.setMinimumWidth(640)
        self.resize(initial_width, 800)

        # ユーザーによる横幅変更を保存するためのデバウンス保存タイマー。
        self._width_save_timer = QTimer(self)
        self._width_save_timer.setSingleShot(True)
        self._width_save_timer.setInterval(300)
        self._width_save_timer.timeout.connect(self._persist_window_width)
        # 起動直後の自動 resize を保存対象から除外する。
        self._width_persist_enabled = False
        QTimer.singleShot(0, lambda: setattr(self, "_width_persist_enabled", True))

        self._update_title()

        # T12 (Wave 4 / A1): アプリ起動時に GitHub Copilot 認証を強制。
        # 未認証の場合は他 UI 操作不可のモーダルを表示し、認証完了まで待機。
        QTimer.singleShot(0, self._enforce_startup_github_auth)

    # ----------------------------------------------------------
    # UI セットアップ
    # ----------------------------------------------------------

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        # ヘッダー右上: 「セッション」「設定」「Copilot」の3アイコンを1行統一
        style = self.style()

        def _make_tool_button(text: str, tooltip: str, std_pixmap, themed_name: str = "") -> QToolButton:
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tooltip)
            btn.setAutoRaise(True)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            icon = QIcon.fromTheme(themed_name) if themed_name else QIcon()
            if icon.isNull() and style is not None:
                icon = style.standardIcon(std_pixmap)
            if not icon.isNull():
                btn.setIcon(icon)
            # B-3: ウィンドウ縮小時にツールボタンが最小幅でレイアウトを
            # 押し広げすぎないよう minimumWidth=0 を許容する。
            # 注: 横方向を Ignored にすると addStretch() と組み合わさったときに
            # ボタン幅が 0 に潰れて何も表示されなくなる不具合があるため、
            # 横方向は既定 (Preferred) のままにする。
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            btn.setMinimumWidth(0)
            return btn

        self._btn_session = _make_tool_button(
            "セッション",
            "セッション操作（新規 / 停止）",
            QStyle.StandardPixmap.SP_FileDialogListView,
        )
        self._btn_session.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._session_menu = build_session_menu(
            self,
            on_new_session=self._on_new_session_triggered,
            on_stop_session=lambda: self._page_workbench.stop_orchestrator(),
        )
        self._btn_session.setMenu(self._session_menu)

        self._btn_settings = _make_tool_button(
            "設定",
            "設定",
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "preferences-system",
        )
        # 歯車アイコン (SVG) を優先的に適用
        _gear_path = Path(__file__).parent / "icons" / "gear.svg"
        if _gear_path.exists():
            _gear_icon = QIcon(str(_gear_path))
            if not _gear_icon.isNull():
                self._btn_settings.setIcon(_gear_icon)
        self._btn_settings.clicked.connect(self._open_settings_window)
        self._settings_window: Optional[SettingsWindow] = None

        self._btn_copilot = _make_tool_button(
            "Copilot",
            "GitHub Copilot Chat を開く",
            QStyle.StandardPixmap.SP_MessageBoxInformation,
        )
        self._btn_copilot.clicked.connect(self._on_copilot_clicked)

        # --- アプリ識別タイトルは画面内からは削除（要件: 「Windowのタイトルに: HVE Workbench。この文字は画面内からは削除」）。
        # 以前の self._title_label は本リファクタリングで取り除き、ウィンドウタイトル (setWindowTitle) で表示される。

        # --- Plugin / MCP Server 認証ボタン (Q1=A 同列右側) ---
        self._btn_plugin_auth = QPushButton(self.tr("🔐 PluginやMCP Serverへの認証"))
        self._btn_plugin_auth.setToolTip(
            self.tr("GitHub / Work IQ / MCP Server / 外部 CLI の認証をまとめて実行します")
        )
        self._btn_plugin_auth.clicked.connect(self._on_plugin_auth_clicked)
        # B-1: 長文ボタンが最小幅を支配するのを防ぐため minimumWidth=0。
        # 横方向 Ignored は addStretch() と組み合わさるとボタン幅が 0 に潰れて
        # 表示されなくなるため、Preferred を維持する。
        self._btn_plugin_auth.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._btn_plugin_auth.setMinimumWidth(0)
        # Q8=B: 初期状態は強調 (未認証想定)。後続 AuthMonitor で更新。
        self._apply_plugin_auth_button_style(highlighted=True)

        # C: ヘッダーに「表示」ボタン（横幅プリセット用）を追加する。
        self._btn_view = _make_tool_button(
            self.tr("表示"),
            self.tr("ウィンドウ横幅を変更します"),
            QStyle.StandardPixmap.SP_DesktopIcon,
        )
        self._btn_view.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_view.setMenu(self._build_view_menu())

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self._btn_plugin_auth)
        top_row.addWidget(self._btn_view)
        top_row.addWidget(self._btn_session)
        top_row.addWidget(self._btn_settings)
        top_row.addWidget(self._btn_copilot)

        # ヘッダー
        self._header = HeaderBar()

        # Copilot チャットドック（初期状態は非表示）
        self._copilot_dock = CopilotChatPanel(self, repo_root=self._repo_root)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._copilot_dock)
        self._copilot_dock.hide()

        # ページ群
        self._page_options = OptionsPage(repo_root=self._repo_root)
        # OptionsPage の repo_root を伝播（ARD 添付保存先の解決に使う）
        # set_workflow が呼ばれたタイミングで AttachmentPane の repo_root を上書き

        # WorkflowSelectPage に OptionsPage を右ペインとして埋め込む。2ペイン構成。
        self._page_workflow = WorkflowSelectPage(options_page=self._page_options)
        self._page_workflow.selection_changed.connect(self._on_workflow_selection_changed)
        self._page_workflow.autopilot_changed.connect(self._on_autopilot_toggled)

        self._page_workbench = WorkbenchPage()
        self._page_workbench.process_finished.connect(self._on_process_finished)
        # Issue-gui-session-workdir-isolation T5b:
        # GUI セッション分離のため HVE_WORK_ROOT 等を子プロセスに伝播させる。
        try:
            self._page_workbench.set_env_overrides(
                self._session_workdir.env_overrides()
            )
        except Exception:
            pass

        # T3.1: _workbench_stack を撤去し WorkbenchPage 単一運用へ移行。
        # Autopilot OFF/ON で同一ページを表示。
        # T4.1: AutopilotQueuePage / T4.2: ChainLogWindow / _chain_log_windows を撤去。
        self._stack = QStackedWidget()
        self._stack.addWidget(self._page_workflow)
        self._stack.addWidget(self._page_workbench)
        self._stack.setCurrentIndex(_STEP_WORKFLOW)
        # B: 各ページのコンテンツがウィンドウ最小幅を押し上げないよう
        # minimumWidth=0 とする。stretch=1 で全幅を取らせるため横方向は
        # Ignored ではなく Preferred を使用 (Ignored は意図しない 0 幅縮退を招く)。
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        self._stack.setMinimumWidth(0)

        # ナビゲーションバー
        self._btn_back = QPushButton(self.tr("← 戻る"))
        self._btn_back.clicked.connect(self._on_back_clicked)
        self._btn_next = QPushButton(self.tr("次へ →"))
        # 次へボタンに以前の「実行」スタイルを付与（precheck PASS でそのまま実行開始）。
        self._btn_next.setStyleSheet(
            "QPushButton { background-color: #1976d2; color: white; "
            "padding: 6px 16px; font-weight: bold; } "
            "QPushButton:disabled { background-color: #ccc; }"
        )
        self._btn_next.clicked.connect(self._on_next_clicked)
        # 後方互換保持用のダミー参照。UI には追加しない。
        self._btn_run = self._btn_next
        self._btn_stop = QPushButton(self.tr("■ 停止"))
        self._btn_stop.clicked.connect(self._on_stop_all_clicked)
        # [停止] ボタンによる全タスク停止要求中フラグ。
        # _on_process_finished が「停止されました（全タスク）」を表示するために参照する。
        self._stop_all_invoked: bool = False

        # B: nav ボタンはウィンドウ縮小時に潰れないよう minimumWidth=0 のみ設定し、
        # 横方向は Preferred を維持する (Ignored だと addStretch() と組み合わさり
        # ボタン幅が 0 に潰れて「戻る/次へ/実行/停止」ボタンが表示されない不具合が出る)。
        for _btn in (self._btn_back, self._btn_next, self._btn_stop):
            _btn.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
            )
            _btn.setMinimumWidth(0)

        # T1+T3 (gui-status-banner): [戻る]/[停止] の直上に全幅ステータスバナーを配置。
        # QStatusBar から _status_label を撤去し、本バナーに一本化する。
        self._status_banner = StatusBanner(central)
        # 互換シム: 既存テストコードが `_status_label.text()` を参照しているため、
        # バナーの description_label を同名属性として公開する。
        self._status_label = self._status_banner.description_label

        nav = QHBoxLayout()
        nav.addWidget(self._btn_back)
        nav.addStretch()
        nav.addWidget(self._btn_next)
        nav.addWidget(self._btn_stop)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(top_row)
        layout.addWidget(self._header)
        layout.addWidget(self._stack, stretch=1)
        layout.addWidget(self._status_banner)
        layout.addLayout(nav)

    def _open_settings_window(self) -> None:
        if self._settings_window is None or not self._settings_window.isVisible():
            self._settings_window = SettingsWindow(
                repo_root=self._repo_root, parent=self
            )
            self._settings_window.settings_changed.connect(
                self._on_settings_changed
            )
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _on_settings_changed(self, _settings: Optional[dict]) -> None:
        # Step 2 ウィジェットへ既定値を反映（次回ロードでも反映されるが即時更新）
        try:
            from . import settings_apply
            from . import settings_store

            settings_apply.apply_to_widgets(
                {
                    "C1": self._page_options.c1,
                    "C3": self._page_options.c3,
                    "C4": self._page_options.c4,
                    "C5": self._page_options.c5,
                    "C6": self._page_options.c6,
                    "C7": self._page_options.c7,
                    "AZURE": self._page_options.c_azure,
                    "C10": self._page_options.c10,
                    "C11": self._page_options.c11,
                    "C12": self._page_options.c12,
                    "C13": self._page_options.c13,
                    "C14": self._page_options.c14,
                },
                _settings or settings_store.load(),
            )
        except Exception:
            pass

        # Step 2 「作業状況」テーマを即時反映
        try:
            self._page_workbench.apply_theme_from_settings()
        except Exception:
            pass

        # GUI 全体（全 Top-Level Window）へテーマを適用
        try:
            from .app import apply_theme_to_application
            from . import settings_store as _ss
            theme = _ss.get_option("theme") or "light"
            apply_theme_to_application(theme)
        except Exception:
            pass
        # T6 (gui-status-banner): バナーの配色もテーマに追随。
        # _status_banner は __init__ で必ず生成されるため try/except は不要。
        try:
            from . import settings_store as _ss2
            self._status_banner.apply_theme(_ss2.get_option("theme") or "light")
        except Exception:
            pass

    def _setup_menu(self) -> None:
        # menuBar は廃止（ヘッダーアイコンに統合）
        menu_bar = self.menuBar()
        if menu_bar is not None:
            menu_bar.setVisible(False)

    # ------------------------------------------------------------------
    # T3 (gui-status-banner): 統一ステータス API
    # ------------------------------------------------------------------
    def _set_status(self, kind: StatusKind, message: str = "") -> None:
        """全幅ステータスバナーへ状況と説明文を反映する。

        `self._status_label` は `_status_banner.description_label` のエイリアスのため、
        本メソッド経由で description_label の表示テキストも自動的に更新される。
        """
        self._status_banner.set_status(kind, message)

    def _setup_status_bar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        # T3 (gui-status-banner / Q1=B): 左側の _status_label は撤去。
        # 状況メッセージは central の _status_banner へ一本化し、
        # QStatusBar には認証ステータス（右側の永続ウィジェット）のみ残置する。
        # --- 認証ステータス (右側) ---
        self._auth_status_label = QLabel(self.tr("🔄 認証状態確認中..."))
        self._auth_status_label.setMinimumWidth(0)
        self._auth_status_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        sb.addPermanentWidget(self._auth_status_label)
        # Q4=A: 「利用できるモデルの取得」ボタンは常時可視・初期 disabled。
        # GitHub 認証成功時のみ enabled になり、押下で models_api.fetch_models() のみ実行する。
        self._btn_login = QPushButton(self.tr("利用できるモデルの取得"))
        self._btn_login.setVisible(True)
        self._btn_login.setEnabled(False)
        self._btn_login.setToolTip(
            self.tr("GitHub 認証が完了するまで無効です。\n[PluginやMCP Serverへの認証] から認証してください。")
        )
        self._btn_login.clicked.connect(self._on_login_clicked)
        # 横方向 Ignored は addStretch() と組み合わさるとボタン幅が 0 に潰れて
        # 「利用できるモデルの取得」ボタンが表示されない不具合があるため Preferred を使用。
        self._btn_login.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._btn_login.setMinimumWidth(0)
        sb.addPermanentWidget(self._btn_login)

        # --- AuthMonitor 起動 (Q6=C 多重化) ---
        self._auth_monitor = AuthMonitor(self)
        self._auth_monitor.provider_state_changed.connect(self._on_auth_provider_state_changed)
        self._auth_monitor.snapshot_changed.connect(self._on_auth_snapshot_changed)
        self._auth_monitor.any_expired.connect(self._on_auth_any_expired)
        self._refresh_auth_providers()
        self._auth_monitor.start()
        self._auth_monitor.force_refresh()  # 起動直後 1 回実行

    # ----------------------------------------------------------
    # T12 (Wave 4 / A1): 起動時 GitHub Copilot 認証強制
    # ----------------------------------------------------------
    def _enforce_startup_github_auth(self) -> None:
        """起動直後に GitHub Copilot 認証を確認し、未認証ならモーダルで強制する。

        - 同期的に最新状態を取得 (force_refresh + worker.wait + processEvents)。
        - 認証済みなら何もしない。
        - 未認証なら central widget を `setEnabled(False)` にし、modal QMessageBox
          で「認証する / 終了」を提示。「認証する」を選んだ場合は
          ``PluginAuthDialog`` を開き、認証完了 (= GitHub が AUTHENTICATED) になるまで
          ループ。「終了」を選んだ場合はアプリを閉じる。

        実装ノート (敵対的レビュー対応):
            - ``worker.wait()`` はメインスレッドをブロックするため、worker thread から
              emit された ``done`` シグナルの queued slot は実行されない。``processEvents()``
              を明示的に呼んで slot を消化してから state を再評価する。
            - 起動時モーダルでは ``_startup_auth_blocking`` フラグを立て、closeEvent で
              認証完了まで × ボタン経由の close を ignore する。
        """
        import logging
        logger = logging.getLogger(__name__)

        def _sync_refresh(wait_ms: int = 30_000) -> None:
            """force_refresh → worker.wait → processEvents で state を確実に最新化。"""
            self._auth_monitor.force_refresh()
            worker = getattr(self._auth_monitor, "_worker", None)
            if worker is not None:
                worker.wait(wait_ms)
            # Critical: queued slot 消化のため明示的に event を処理
            QApplication.processEvents()

        # 初回 state が UNKNOWN なら 1 度同期更新
        if self._auth_monitor.latest_state("github") is AuthState.UNKNOWN:
            logger.info("startup auth: initial state UNKNOWN, syncing")
            _sync_refresh()

        if self._auth_monitor.latest_state("github") is AuthState.AUTHENTICATED:
            logger.info("startup auth: GitHub already authenticated")
            return

        logger.warning("startup auth: GitHub NOT authenticated, entering modal loop")
        self._startup_auth_blocking = True
        central = self.centralWidget()
        if central is not None:
            central.setEnabled(False)

        user_quit = False
        try:
            while self._auth_monitor.latest_state("github") is not AuthState.AUTHENTICATED:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle(self.tr("GitHub Copilot 認証が必要"))
                box.setText(
                    self.tr(
                        "本アプリケーションは GitHub Copilot 認証必須です。\n"
                        "認証が完了するまで操作できません。"
                    )
                )
                btn_auth = box.addButton(
                    self.tr("認証する"), QMessageBox.ButtonRole.AcceptRole
                )
                btn_quit = box.addButton(
                    self.tr("終了"), QMessageBox.ButtonRole.RejectRole
                )
                box.setDefaultButton(btn_auth)
                box.exec()
                if box.clickedButton() is btn_quit:
                    logger.warning("startup auth: user chose Quit")
                    user_quit = True
                    break
                logger.info("startup auth: opening PluginAuthDialog")
                self._on_plugin_auth_clicked()
                # 認証ダイアログ閉鎖後に同期で最新状態を取得
                _sync_refresh(wait_ms=60_000)
        finally:
            self._startup_auth_blocking = False
            if not user_quit and central is not None:
                central.setEnabled(True)

        if user_quit:
            # close は finally の後で実行 (setEnabled の余計な復元を避ける)
            QTimer.singleShot(0, self.close)

    # ----------------------------------------------------------
    # 認証状態 (Plugin / MCP Server)
    # ----------------------------------------------------------

    def _apply_plugin_auth_button_style(self, *, highlighted: bool) -> None:
        """Q8=B: 認証ボタンを状態に応じて強調 / 通常表示。"""
        if highlighted:
            self._btn_plugin_auth.setStyleSheet(
                "QPushButton { background-color: #ef6c00; color: white; "
                "padding: 6px 12px; font-weight: bold; border-radius: 4px; }"
                "QPushButton:hover { background-color: #f57c00; }"
            )
        else:
            self._btn_plugin_auth.setStyleSheet(
                "QPushButton { color: #555; padding: 6px 12px; }"
            )

    def _refresh_auth_providers(self) -> None:
        """Copilot CLI からプロバイダを再列挙して AuthMonitor へ反映。

        ``discover_providers()`` は内部で ``copilot mcp list`` / ``copilot plugin list``
        を呼び出すため、GUI 設定値の依存は無い。``settings`` は後方互換用に渡す。

        T10 (Wave 3): settings に ``mcp_enabled`` セクションを併合し、AuthMonitor
        へ供給する (provider.is_required(settings) で動的判定するため)。
        """
        try:
            from . import settings_store
            settings = settings_store.load()
        except Exception:
            settings = {}
        # mcp_enabled セクションを併合 (load() でも取得されるが明示的に上書き)
        try:
            from . import settings_store as _ss
            mcp_enabled = _ss.load_mcp_enabled()
            if mcp_enabled:
                settings = dict(settings)
                settings["mcp_enabled"] = mcp_enabled
        except Exception:
            pass
        providers = discover_providers(settings)
        self._auth_monitor.set_providers(providers, settings)

    @Slot(str, str)
    def _on_auth_provider_state_changed(self, provider_id: str, state_value: str) -> None:
        # T11: GitHub 認証成功時のみ [利用できるモデルの取得] を有効化
        if provider_id == "github":
            ok = state_value == AuthState.AUTHENTICATED.value
            self._btn_login.setEnabled(ok)
            if ok:
                self._btn_login.setToolTip(self.tr("利用できるモデル一覧を取得しキャッシュへ保存します。"))
            else:
                self._btn_login.setToolTip(
                    self.tr("GitHub 認証が完了するまで無効です。\n[PluginやMCP Serverへの認証] から認証してください。")
                )

    @Slot(dict)
    def _on_auth_snapshot_changed(self, snapshot: dict) -> None:
        # T16: ステータスバー右側に複数プロバイダのサマリを表示
        if not snapshot:
            self._auth_status_label.setText(self.tr("認証対象なし"))
            return
        icon_map = {
            AuthState.AUTHENTICATED.value: "✅",
            AuthState.NOT_AUTHENTICATED.value: "❌",
            AuthState.EXPIRED.value: "⚠️",
            AuthState.UNKNOWN.value: "❔",
            AuthState.CHECKING.value: "🔄",
            AuthState.NOT_APPLICABLE.value: "—",
        }
        parts = []
        all_ok = True
        for pid, sv in snapshot.items():
            short = pid if not pid.startswith("mcp:") else pid[4:]
            parts.append(f"{icon_map.get(sv, '?')}{short}")
            if sv != AuthState.AUTHENTICATED.value:
                all_ok = False
        self._auth_status_label.setText(" ".join(parts))
        self._apply_plugin_auth_button_style(highlighted=not all_ok)

    @Slot()
    def _on_auth_any_expired(self) -> None:
        # T15: 実行中に失効を検知したら自動停止して再認証を促す
        if self._page_workbench.is_running():
            try:
                self._page_workbench.stop_orchestrator()
            except Exception:
                pass
            QMessageBox.warning(
                self,
                self.tr("認証失効"),
                self.tr(
                    "実行中に Plugin / MCP Server の認証が失効しました。\n"
                    "ワークフローを停止しました。再認証してください。"
                ),
            )
        self._on_plugin_auth_clicked()

    def _on_plugin_auth_clicked(self) -> None:
        """Q1=A: 「PluginやMCP Serverへの認証」ボタン押下時のメイン処理。"""
        # 設定更新を反映してプロバイダを再列挙
        self._refresh_auth_providers()
        providers = self._auth_monitor.providers()
        if not providers:
            QMessageBox.information(
                self,
                self.tr("認証対象なし"),
                self.tr("認証対象の Plugin / MCP Server が設定されていません。"),
            )
            return
        dlg = PluginAuthDialog(providers, parent=self)
        dlg.completed.connect(self._auth_monitor.force_refresh)
        # T07: 個別プロバイダ認証完了の都度、当該プロバイダを invalidate して即時再チェック
        dlg.provider_authenticated.connect(
            lambda pid, _ok: self._auth_monitor.refresh_provider(pid)
        )
        dlg.exec()
        # ダイアログ閉じた後も明示的に状態を更新
        self._auth_monitor.force_refresh()

    def _on_login_clicked(self) -> None:
        """T11/T12: 「利用できるモデルの取得」押下時はモデル取得のみを行う。"""
        # GitHub 認証は新ボタン経由で完了している前提 (T11 で disabled 制御)
        if self._auth_monitor.latest_state("github") is not AuthState.AUTHENTICATED:
            QMessageBox.warning(
                self,
                self.tr("未認証"),
                self.tr("GitHub 認証が完了していません。[PluginやMCP Serverへの認証] から認証してください。"),
            )
            return
        self._btn_login.setEnabled(False)
        self._set_status(StatusKind.RUNNING, self.tr("モデル一覧を取得中..."))
        from PySide6.QtCore import QThread, Signal

        class _FetchModelsThread(QThread):
            done = Signal(object)  # list[str] | Exception

            def run(self) -> None:  # type: ignore[override]
                try:
                    from hve import models_api, models_cache
                    # entries 形式で取得し、effort/token_prices/context_size を含めて保存する。
                    # （旧 fetch_models() + save() は entries=[] で書き込んでしまうため使用しない）
                    entries = models_api.fetch_model_entries()
                    models = [e.id for e in entries]
                    if entries:
                        try:
                            models_cache.clear()
                            models_cache.save_entries(entries)
                        except OSError as exc:
                            self.done.emit(exc)
                            return
                    self.done.emit(models or [])
                except Exception as exc:
                    self.done.emit(exc)

        thread = _FetchModelsThread(self)
        thread.done.connect(self._on_models_fetched)
        self._fetch_models_thread = thread  # GC 防止
        thread.start()

    @Slot(object)
    def _on_models_fetched(self, result: object) -> None:
        self._btn_login.setEnabled(True)
        if isinstance(result, Exception):
            QMessageBox.warning(
                self,
                self.tr("モデル取得失敗"),
                self.tr("モデル一覧の取得に失敗しました: {err}").format(err=str(result)),
            )
            self._set_status(StatusKind.ERROR, self.tr("モデル取得失敗"))
            return
        # R2: Slot(object) のため result の静的型は object。実行時に iterable を期待。
        if result and hasattr(result, "__iter__"):
            models = list(result)  # type: ignore[call-overload]
        else:
            models = []
        self._set_status(
            StatusKind.SUCCESS,
            self.tr("モデル一覧を取得しました ({n} 件)").format(n=len(models)),
        )
        # 既存ウィジェットへ反映 (空配列時は既存リスト維持)
        if models:
            try:
                self._page_options.c1.reload_models()
            except Exception:
                pass
            if (
                self._settings_window is not None
                and self._settings_window.isVisible()
            ):
                try:
                    self._settings_window.reload_models()
                except Exception:
                    pass

    # ----------------------------------------------------------
    # ナビゲーション
    # ----------------------------------------------------------

    def _current_step(self) -> int:
        return self._stack.currentIndex()

    def _refresh_navigation(self) -> None:
        step = self._current_step()
        # 戻るボタン (Step 2 「実行」のみ有効、ただし実行中は不可)
        self._btn_back.setEnabled(
            step == _STEP_WORKBENCH and not self._page_workbench.is_running()
        )
        # 次へボタン (Step 1 のみ)
        self._btn_next.setVisible(step == _STEP_WORKFLOW)
        if step == _STEP_WORKFLOW:
            self._btn_next.setEnabled(
                len(self._page_workflow.selected_workflow_ids()) > 0
            )
        # 停止ボタン (Step 2 「実行」のみ)
        self._btn_stop.setVisible(step == _STEP_WORKBENCH)
        self._btn_stop.setEnabled(self._page_workbench.is_running())

        # ヘッダー進捗
        self._header.set_current_step(step)

        # ステータスバー
        if step == _STEP_WORKFLOW:
            wf_ids = self._page_workflow.selected_workflow_ids()
            wf = (
                ", ".join(format_workflow_label(wid) for wid in wf_ids)
                if wf_ids
                else self.tr("（未選択）")
            )
            self._set_status(
                StatusKind.IDLE,
                self.tr("ワークフローの選択: {wf}").format(wf=wf),
            )
        else:
            # Critical fix (gui-status-banner adversarial-review #1, #2):
            # Step 2 表示中は _on_process_finished / _show_autopilot_phase_failure
            # 等の呼び出し側が 成功/失敗/警告 ステータスをバナーに封入する。
            # _refresh_navigation が無条件 RUNNING で上書きすると色フリッカーや
            # 完了状態の取りこぼしが起きるため、「サブプロセスが実際に
            # 走行中」のときのみ RUNNING を設定し、それ以外はバナーを触らない。
            if self._page_workbench.is_running():
                self._set_status(StatusKind.RUNNING, self.tr("実行中"))

    def _on_back_clicked(self) -> None:
        if self._current_step() == _STEP_WORKBENCH and not self._page_workbench.is_running():
            self._stack.setCurrentIndex(_STEP_WORKFLOW)
            self._refresh_navigation()

    def _on_next_clicked(self) -> None:
        if self._current_step() == _STEP_WORKFLOW:
            wf_ids = self._page_workflow.selected_workflow_ids()
            if not wf_ids:
                return

            self._selected_workflow_ids = wf_ids
            wf_names = self._page_workflow.selected_workflow_names()
            wf_name_map = {
                wf_id: (wf_names[i] if i < len(wf_names) else "")
                for i, wf_id in enumerate(wf_ids)
            }
            self._page_options.set_workflows(wf_ids, wf_name_map)
            # ARD 添付ペインに repo_root を伝播
            pane = self._page_options.attachment_pane()
            if pane is not None and hasattr(pane, "set_repo_root"):
                pane.set_repo_root(self._repo_root)

            # --- Step 1 統合 precheck（両モード共通） ---
            # FILE/WIZARD_INPUT/SETTING/AUTH の 4 カテゴリ統合検査 + プランレビュー +
            # ギャップ適用ループ（最大 3 回）を Autopilot ON/OFF 共通で実行する。
            # Autopilot 固有の暗黙依存 / catalog 必須要求は autopilot_mode=True のときのみ
            # 追加で渡される（_run_step1_unified_precheck 内部で分岐）。
            autopilot_enabled = self._page_workflow.is_autopilot_enabled()
            if not self._run_step1_unified_precheck(
                wf_ids, autopilot_mode=autopilot_enabled
            ):
                return  # 不足あり / キャンセル: ダイアログ表示済み、Step 1 に留まる

            # --- Autopilot ON: 旧 Step 2 (オプション設定) をスキップして Step 2 「実行中」へ直接遷移 ---
            if autopilot_enabled:
                # 確認ダイアログ (Q5=b)
                if not self._confirm_autopilot_start(wf_ids):
                    return

                # Step 2 「実行」へ直接遷移し Autopilot 開始 (auth は precheck で検査済み)
                self._start_autopilot(skip_auth_recheck=True)
                return

            # Autopilot OFF: OptionsPage の入力検証 + 実行起動。
            # precheck / auth は _run_step1_unified_precheck で実施済みのため、
            # `_on_run_clicked` 側では skip する。
            self._on_run_clicked(skip_step1_precheck=True)

    def _wait_catalog_ready(self, catalog_path: Path, intervals) -> bool:
        """R3: catalog ファイルの「存在＋非零サイズ」を指数バックオフで待機。

        Args:
            catalog_path: 確認対象ファイル。
            intervals: 各リトライ前の待機秒数 tuple。

        Returns:
            ファイルが存在し size>0 になれば True。最終リトライでも条件不成立なら False。
        """
        import time
        # 即時 1 回チェック（既に書き込み済みの常道ケース）
        if MainWindow._is_catalog_ready(catalog_path):
            return True
        for delay in intervals:
            try:
                QApplication.processEvents()
            except Exception:
                pass
            time.sleep(delay)
            if MainWindow._is_catalog_ready(catalog_path):
                return True
        return False

    @staticmethod
    def _is_catalog_ready(catalog_path: Path) -> bool:
        """R3: catalog ファイルが存在し非零サイズかを判定（IO エラーは False 扱い）。"""
        try:
            return catalog_path.exists() and catalog_path.stat().st_size > 0
        except OSError:
            return False

    def _collect_ard_attachment_paths(self) -> List[str]:
        """T7: ARD 添付ペイン由来のパス（attached_docs / target_business_path）を収集する。

        ON/OFF 両経路で重複していた読取コードを集約。attach_pane 未設定や属性欠落・
        例外時は空 list を返す。
        """
        paths: List[str] = []
        try:
            attach_pane = self._page_options.attachment_pane()
        except Exception:
            return paths
        if attach_pane is None:
            return paths
        attach_str = getattr(attach_pane, "attached_docs_string", None)
        if callable(attach_str):
            try:
                v = attach_str()
            except Exception:
                v = None
            if v:
                paths.append(v)
        target_business = getattr(attach_pane, "target_business_path", None)
        if callable(target_business):
            try:
                tb = target_business()
            except Exception:
                tb = None
            if tb:
                paths.append(str(tb))
        return paths

    def _refresh_auth_states_sync(self) -> tuple:
        """T5: 認証プロバイダ状態を同期的に最新化する共通ヘルパ。

        ON/OFF 両経路で重複していた以下のシーケンスを集約:
          - _refresh_auth_providers() で設定反映
          - force_refresh() + worker.wait(30s) + processEvents()
          - providers / settings / states 取得

        Returns:
            (providers: list, settings: dict, states: dict[provider_id -> AuthState])
        """
        self._refresh_auth_providers()
        self._auth_monitor.force_refresh()
        worker = getattr(self._auth_monitor, "_worker", None)
        if worker is not None:
            worker.wait(30_000)
        # worker.wait() 中は queued slot が動かないため processEvents で消化。
        QApplication.processEvents()
        providers = list(self._auth_monitor.providers())
        settings = self._auth_monitor.current_settings()
        states = {p.id: self._auth_monitor.latest_state(p.id) for p in providers}
        return providers, settings, states

    def _verify_required_auth_before_run(self, *, skip_refresh: bool = False) -> bool:
        """ワークフロー実行直前に必須プロバイダの認証を再確認する (Q6=C, T14)。

        T11 (Wave 4): 必須判定は ``provider.is_required(settings)`` の動的判定に
        変更。Step 2 の Work IQ 設定 ON / `mcp_enabled` で ON の MCP サーバなどを
        実行時に評価し、認証が完了していなければ中断する。

        Returns:
            True なら実行続行可。False なら中断 (再認証ダイアログ起動済)。
        """
        from .auth_providers import provider_is_required
        # T5: skip_refresh=True なら直近 _refresh_auth_states_sync の結果を流用。
        if skip_refresh:
            providers = list(self._auth_monitor.providers())
            settings = self._auth_monitor.current_settings()
        else:
            providers, settings, _states = self._refresh_auth_states_sync()
        missing = []
        for p in providers:
            if not provider_is_required(p, settings):
                continue
            if self._auth_monitor.latest_state(p.id) is not AuthState.AUTHENTICATED:
                missing.append(p.display_name)
        if missing:
            QMessageBox.warning(
                self,
                self.tr("認証未完了"),
                self.tr(
                    "以下の必須プロバイダの認証が完了していません:\n  - {names}\n\n"
                    "[PluginやMCP Serverへの認証] から認証してください。"
                ).format(names="\n  - ".join(missing)),
            )
            self._on_plugin_auth_clicked()
            return False
        return True

    def _on_run_clicked(self, *, skip_step1_precheck: bool = False) -> None:
        # --- Autopilot 分岐 ---
        if self._page_workflow.is_autopilot_enabled():
            self._start_autopilot()
            return

        ok, msg = self._page_options.validate()
        if not ok:
            QMessageBox.warning(self, self.tr("入力エラー"), msg)
            return

        workflow_ids = list(self._selected_workflow_ids)
        if not workflow_ids:
            QMessageBox.warning(self, self.tr("入力エラー"), self.tr("ワークフローが選択されていません。"))
            return

        # T14: ワークフロー実行ガード — Q6=C ワークフロー実行直前にも認証再確認
        # skip_step1_precheck=True のとき: Step 1 [次へ] の統合 precheck で AUTH を
        # 検査済みのため再確認を省略する（_on_next_clicked からの遷移）。
        # Falseのとき: Step 2 → 実行直接呼び出し等の経路から、念のため再確認する。
        if not skip_step1_precheck:
            if not self._verify_required_auth_before_run():
                return

        try:
            ordered_workflows = _sort_workflows_by_dependencies(workflow_ids)
        except ValueError as e:
            QMessageBox.warning(self, self.tr("依存関係エラー"), str(e))
            return

        args_queue = []
        workflow_plan = []
        try:
            for wf_id in ordered_workflows:
                args = self._page_options.build_args_for_workflow(
                    wf_id,
                    repo_root=self._repo_root,
                )
                args_queue.append(args)

                wf = get_workflow(wf_id)
                wf_name = wf.name if wf is not None else wf_id
                steps: list = []
                if wf is not None:
                    steps = [
                        {
                            "id": s.id,
                            "title": s.title,
                            "depends_on": list(s.depends_on),
                        }
                        for s in wf.steps
                        if not s.is_container
                    ]
                workflow_plan.append(
                    {
                        "workflow_id": wf_id,
                        "workflow_name": wf_name,
                        "steps": steps,
                    }
                )
        except ValueError as e:
            QMessageBox.warning(self, self.tr("エラー"), str(e))
            return

        # --- 必須入力ファイル precheck ---
        # skip_step1_precheck=True のとき: Step 1 [次へ] で `_run_step1_unified_precheck`
        # により FILE/WIZARD_INPUT/SETTING/AUTH の 4 カテゴリ統合検査 + プランレビューが
        # 既に実施済みのため、ここでは再実行しない。
        # False のとき: Step 2 直接呼び出し等の経路から、必須入力ファイル検査のみ実行する。
        if not skip_step1_precheck:
            additional_prompts: Dict[str, str] = {}
            for wf_id, args in zip(ordered_workflows, args_queue):
                ap = getattr(args, "additional_prompt", None)
                if ap:
                    additional_prompts[wf_id] = ap
            extra_provided: Dict[str, list] = {}
            paths_for_ard = self._collect_ard_attachment_paths()
            if paths_for_ard:
                extra_provided["ard"] = paths_for_ard
            if not self._run_step1_unified_precheck(
                list(ordered_workflows),
                autopilot_mode=False,
            ):
                return

        self._stack.setCurrentIndex(_STEP_WORKBENCH)
        self._refresh_navigation()
        self._page_workbench.start_orchestrators(args_queue, workflow_plan=workflow_plan)
        self._refresh_navigation()
        self._update_title()

    # ------------------------------------------------------------------
    # Autopilot 実行
    # ------------------------------------------------------------------

    def _on_autopilot_toggled(self, enabled: bool, _catalog: str) -> None:
        """Autopilot ON/OFF 切替時のメインウィンドウ側ハンドラ。

        - ON/OFF いずれに切り替わっても、Step 1 統合 precheck のプランレビュー反復
          カウンタ（``_step1_plan_review_iterations``）をリセットする。
          このカウンタは両モード共通の ``_run_step1_unified_precheck`` 内で使用される
          ため、モード切替時に過去の反復状態を持ち越さない。
        - OptionsPage は Autopilot 状態に依らず右ペインに常表示（統合済み）。
        """
        self._step1_plan_review_iterations = 0

    def _run_step1_unified_precheck(
        self,
        wf_ids: list,
        *,
        autopilot_mode: bool,
    ) -> bool:
        """Step 1 [次へ] 押下時の統合 precheck + プランレビュー（両モード共通）。

        Autopilot ON/OFF で同一アルゴリズム（FILE/WIZARD_INPUT/SETTING/AUTH の 4
        カテゴリ統合 precheck → プランレビュー → ギャップ適用ループ）を実行する。
        Autopilot 固有の暗黙依存（``_AUTOPILOT_IMPLICIT_REQUIRED_PATHS``）と
        catalog 必須要求（``autopilot_required_artifacts``）は ``autopilot_mode``
        が True のときのみ追加で渡される。

        Args:
            wf_ids: 呼び出し時の選択 workflow ID。**初回参照のみ**で、ループ内では
                毎回 ``self._page_workflow.selected_workflow_ids()`` から再取得する
                （ギャップ適用により選択範囲が変化するため）。
            autopilot_mode: Autopilot 経路かどうか。True のとき以下を追加で渡す:
                ``implicit_required_paths`` / ``autopilot_required_artifacts`` /
                ``extra_provided[""]=[autopilot_catalog_path()]``。

        フロー:
          1. precheck（FILE/WIZARD_INPUT/SETTING/AUTH）を実行。不足ありなら
             ``Step1PrecheckDialog`` で通知し False。
          2. 不足なしなら ``build_step1_plan_review()`` でプランを構築し、
             ``Step1PlanReviewDialog`` で表示（ギャップ 0 件かつ設定 OFF なら skip）。
          3. ユーザーがギャップ提案を [適用] したら page_workflow に反映し、
             precheck から再実行（最大 3 回）。
          4. ループ上限到達時は警告し False。
          5. ユーザーが Dialog で [このプランで実行] を選択したら True。

        Returns:
            True: 後続処理（Autopilot 起動 / 通常実行）に進める。
            False: Step 1 に留まる。
        """
        from hve.autopilot.precheck_runner import run_step1_precheck
        from hve.autopilot.plan_review_runner import build_step1_plan_review
        from .auth_providers import AuthState
        from .autopilot.planner import default_catalog_path
        from .autopilot.precheck_dialog import Step1PrecheckDialog
        from .autopilot.plan_review_dialog import Step1PlanReviewDialog

        repo_root = Path(self._repo_root) if self._repo_root else Path.cwd()
        MAX_ITER = 3
        self._step1_plan_review_iterations = 0

        # 認証情報の同期取得をループ外に移動（ループ毎の 30s wait を排除）。
        providers, auth_settings, auth_states = self._refresh_auth_states_sync()

        while True:
            self._step1_plan_review_iterations += 1
            if self._step1_plan_review_iterations > MAX_ITER:
                QMessageBox.warning(
                    self,
                    self.tr("Step 1: プランレビュー上限到達"),
                    self.tr(
                        "ギャップ提案の適用ループが {n} 回を超えました。"
                        "手動でワークフロー / ステップを調整してから再度お試しください。"
                    ).format(n=MAX_ITER),
                )
                return False

            steps_by_wf = self._page_workflow.all_enabled_steps()
            wf_ids_now = self._page_workflow.selected_workflow_ids()

            # per-workflow wizard inputs は AutopilotInputPanel 廃止に伴い空とする。
            wizard_inputs: dict = {}

            # --- 追加プロンプト / パラメータ指定ファイルを収集 ---
            additional_prompts: dict = {}
            extra_provided: dict = {}
            # Autopilot ON 時のみ catalog パスを extra_provided に追加。
            if autopilot_mode:
                custom_catalog_for_extra = self._page_workflow.autopilot_catalog_path()
                if custom_catalog_for_extra:
                    extra_provided.setdefault("", []).append(custom_catalog_for_extra)
            # ARD: 添付ペイン由来の attached_docs / target_business_path（両モード共通）
            paths_for_ard = self._collect_ard_attachment_paths()
            if paths_for_ard:
                extra_provided["ard"] = paths_for_ard

            # --- Phase A: precheck ---
            # Autopilot 固有の暗黙依存と catalog 必須要求は autopilot_mode のときのみ渡す。
            implicit_required_paths = None
            autopilot_required: list = []
            if autopilot_mode:
                from hve.autopilot.plan_review_gap import (
                    _AUTOPILOT_IMPLICIT_REQUIRED_PATHS,
                )
                implicit_required_paths = _AUTOPILOT_IMPLICIT_REQUIRED_PATHS
                custom_catalog = self._page_workflow.autopilot_catalog_path()
                if custom_catalog:
                    catalog_path = Path(custom_catalog)
                    if not catalog_path.is_absolute():
                        catalog_path = repo_root / custom_catalog
                else:
                    catalog_path = default_catalog_path(repo_root)
                try:
                    catalog_rel = str(catalog_path.relative_to(repo_root))
                except ValueError:
                    catalog_rel = str(catalog_path)
                autopilot_required = [catalog_rel]

            result = run_step1_precheck(
                wf_ids_now,
                repo_root,
                steps_by_workflow=steps_by_wf,
                wizard_inputs_by_workflow=wizard_inputs,
                providers=providers,
                auth_settings=auth_settings,
                auth_states=auth_states,
                authenticated_marker=AuthState.AUTHENTICATED,
                additional_prompts=additional_prompts,
                extra_provided_paths_by_workflow=extra_provided,
                implicit_required_paths=implicit_required_paths,
                autopilot_required_artifacts=autopilot_required or None,
            )

            if not result.is_ok():
                dlg = Step1PrecheckDialog(result, parent=self)
                dlg.exec()
                self._set_status(
                    StatusKind.WARNING,
                    self.tr("Step 1: 事前検証で {n} 件の不足を検出しました。解決後 [次へ] を押してください。")
                    .format(n=result.count()),
                )
                return False

            # --- Phase B: プランレビュー（T4: ギャップ 0 件かつエラー無しは Dialog skip）---
            # E=2: Autopilot ON 時は build_plan を実行して execution_order を取得し、
            # プランレビュー画面に「実行順序」を表示する（選択 ≠ 実行順 の乖離検出用）。
            # 注: build_plan は Step 2 (_run_autopilot) でも再度呼ばれるため重複実行となる。
            # Step 1 と Step 2 の間に catalog が書き換わると結果が乖離する可能性あり（許容）。
            execution_order_for_review: list = []
            if autopilot_mode:
                try:
                    from .autopilot import AutopilotSelection
                    from .autopilot.planner import build_plan as _build_plan_for_review
                    _sel = AutopilotSelection.from_workflow_ids(wf_ids_now)
                    _plan = _build_plan_for_review(catalog_path, selection=_sel)
                    execution_order_for_review = _plan.execution_order()
                except (FileNotFoundError, ValueError, AttributeError, ImportError) as _e:
                    # プランレビュー表示用の補助情報のため、想定内エラーは空 list で続行。
                    # ブロード except はバグの沈黙劣化を招くため使用しない。
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "execution_order 計算に失敗: %s", _e
                    )
                    execution_order_for_review = []

            review = build_step1_plan_review(
                wf_ids_now,
                repo_root,
                steps_by_workflow=steps_by_wf,
                wizard_inputs_by_workflow=wizard_inputs,
                settings_by_workflow={},  # 現状 settings 入力は未配線（_REQUIRED_SETTING_KEYS が空のため実害なし）
                execution_order=execution_order_for_review,
            )
            applied_gaps: list = []
            # R5-c: 設定 `step1_show_plan_review_always` が True なら 0 件でも表示。
            from .settings_store import get_option as _get_option_for_review
            try:
                _show_always = bool(_get_option_for_review("step1_show_plan_review_always"))
            except Exception:
                _show_always = False
            if not review.gaps and not _show_always:
                # ギャップ 0 件 → Dialog skip して即承認扱い
                ret: int = int(QDialog.DialogCode.Accepted)
            else:
                plan_dlg = Step1PlanReviewDialog(review, parent=self)
                plan_dlg.gaps_applied.connect(lambda gs: applied_gaps.extend(gs))
                ret = int(plan_dlg.exec())

            if applied_gaps:
                # ギャップ適用 → workflow_select に反映 → ループ続行（再 precheck）
                self._page_workflow.apply_plan_review_gaps(applied_gaps)
                self._set_status(
                    StatusKind.RUNNING,
                    self.tr(
                        "Step 1: {n} 件のギャップ提案を適用しました。再検証中..."
                    ).format(n=len(applied_gaps)),
                )
                QApplication.processEvents()
                continue

            if ret == int(QDialog.DialogCode.Accepted):
                return True
            # Cancel
            return False

    def _confirm_autopilot_start(self, wf_ids: list) -> bool:
        """Autopilot 開始確認ダイアログ (Q5=b)。OK なら True を返す。"""
        from .settings_store import get_option

        try:
            mp_raw = get_option("autopilot_max_parallel")
            mp = int(mp_raw) if mp_raw is not None else 4
        except (TypeError, ValueError):
            mp = 4
        mp = max(1, min(16, mp))

        wf_text = ", ".join(w.upper() for w in wf_ids) or "(none)"
        answer = QMessageBox.question(
            self,
            self.tr("Autopilot 開始確認"),
            self.tr(
                "以下の設定で Autopilot を開始します。\n\n"
                "Workflow: {wf}\n"
                "並列上限: {mp}\n\n"
                "実行中はエラー以外で停止しません。続行しますか？"
            ).format(wf=wf_text, mp=mp),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _start_autopilot(self, *, skip_auth_recheck: bool = False) -> None:
        """Autopilot 計画 → Preview → 子プロセス並列起動。

        旧「事前ワークフロー」概念は廃止。依存ファイルのギャップ提案は Step 1 [次へ]
        押下時の `_run_step1_unified_precheck` 内で統合 precheck + プランレビュー
        として処理され、ユーザー確認後に workflow チェックへ反映される。

        Args:
            skip_auth_recheck: True のとき認証再確認をスキップする。
                Autopilot 経路では既に `_run_step1_unified_precheck` 内で AUTH 検査済み。
        """
        from .autopilot import AutopilotSelection, build_plan
        from .autopilot.child_launcher import AutopilotController
        from .autopilot.planner import default_catalog_path
        from .settings_store import get_option

        # gui-workbench-autopilot-display Critical #1: Autopilot 起動ごとに前回実行
        # 残骸（_workflow_plan / _current_workflow_id / state.workflows）をクリアする。
        # クリアしないと 2 回目以降の Autopilot で Header1 表示とツリーに前回の
        # workflow_id が累積表示される。
        try:
            self._page_workbench.reset_for_autopilot()
        except (AttributeError, RuntimeError):
            pass

        if not skip_auth_recheck:
            if not self._verify_required_auth_before_run():
                return

        custom = self._page_workflow.autopilot_catalog_path()
        if custom:
            catalog_path = Path(custom)
            if not catalog_path.is_absolute():
                catalog_path = Path(self._repo_root) / custom
        else:
            catalog_path = default_catalog_path(Path(self._repo_root))

        try:
            max_parallel_raw = get_option("autopilot_max_parallel")
            max_parallel = int(max_parallel_raw) if max_parallel_raw is not None else 4
        except (TypeError, ValueError):
            max_parallel = 4
        max_parallel = max(1, min(16, max_parallel))

        selected_workflows = self._page_workflow.selected_workflow_ids()
        selection = AutopilotSelection.from_workflow_ids(selected_workflows)
        plan = build_plan(catalog_path, max_parallel=max_parallel, selection=selection)

        if custom and not plan.catalog_exists:
            QMessageBox.critical(
                self,
                self.tr("Autopilot エラー"),
                self.tr("指定したカタログファイルが存在しません:\n{path}").format(
                    path=str(catalog_path)
                ),
            )
            return

        # メインワークフロー経路（downstream 不在で ARD/AAS をメインタスクとして実行）
        # downstream が選択されている場合 plan.main_workflows は空となり、
        # 通常の app_chains 経路で実行される。
        if plan.has_main_workflows():
            self._activate_autopilot_workbench()
            self._launch_autopilot_main_workflow_queue(list(plan.main_workflows))
            return

        # T3: pre_phase_only モード（catalog 不在/空 ＋ downstream 選択時）。
        # ARD/AAS のみ先行実行し、完了時に「downstream を続けて実行しますか？」
        # 確認 Dialog を出して半自動継続する。
        if plan.is_pre_phase_only():
            self._autopilot_pre_phase_followup = True
            self._autopilot_pre_phase_selection = selection
            self._autopilot_pre_phase_catalog_path = catalog_path
            self._autopilot_pre_phase_max_parallel = max_parallel
            self._activate_autopilot_workbench()
            # T3a: downstream workflow も placeholder として先行 seed する。
            # selection.workflows には Step 1 で選択した workflow_id が全件含まれる。
            downstream_seed = self._extract_downstream_workflow_ids(
                selection=selection, pre_phases=list(plan.pre_phases)
            )
            self._launch_autopilot_main_workflow_queue(
                list(plan.pre_phases), also_seed=downstream_seed
            )
            return

        # DAG 直列連結経路: pre_phases + app_chains 同時非空
        # ARD/AAS と downstream を同時選択 ＋ catalog 解決済みのケース。
        # pre_phases（ARD → AAS）を順次直列実行し、完了後に build_plan を再実行
        # して app_chains を AutopilotController 経由で並列実行する。
        # 注意: pre_phase_only と異なり downstream 継続 Dialog は出さない
        # （ユーザーが明示的に同時選択済みのため）。
        if plan.needs_chain_continuation():
            self._autopilot_chain_continuation_pending = True
            self._autopilot_chain_continuation_selection = selection
            self._autopilot_chain_continuation_catalog_path = catalog_path
            self._autopilot_chain_continuation_max_parallel = max_parallel
            self._activate_autopilot_workbench()
            # T3a: app_chains 内の downstream workflow を placeholder として先行 seed する。
            downstream_seed = self._extract_downstream_workflow_ids(
                plan=plan, pre_phases=list(plan.pre_phases)
            )
            self._launch_autopilot_main_workflow_queue(
                list(plan.pre_phases), also_seed=downstream_seed
            )
            return

        if plan.is_empty():
            # T8: skipped 内訳を提示し、原因（カタログのアーキテクチャ vs 選択 workflow）
            # をユーザーが判別できるようにする。
            skipped_lines = []
            for s in (plan.skipped or [])[:10]:
                skipped_lines.append(f"  - {s.app_id}: {s.architecture}  ({s.reason})")
            extra = "\n".join(skipped_lines) if skipped_lines else ""
            if plan.skipped and len(plan.skipped) > 10:
                extra += f"\n  ... ({len(plan.skipped) - 10} 件省略)"
            msg = self.tr(
                "実行対象 APP が 0 件です。\n"
                "Application Architecture Catalog ({catalog}) のアーキテクチャと、"
                "「ワークフローの選択」で有効化した workflow の組み合わせを確認してください。"
            ).format(catalog=str(catalog_path))
            if extra:
                msg += "\n\n" + self.tr("除外された APP:\n{detail}").format(detail=extra)
            QMessageBox.warning(self, self.tr("Autopilot 警告"), msg)
            return

        def _argv_factory(app_id: str, workflow_id: str) -> List[str]:
            # OptionsPage singleton から workflow 別 args を生成する。
            # 旧 AutopilotInputPanel / WorkflowOptionsSection による per-workflow 入力は廃止され、
            # 複数 workflow で同名フィールドは singleton 入力を共有する。
            args = self._page_options.build_args_for_workflow(
                workflow_id,
                repo_root=self._repo_root,
            )
            args.app_ids = app_id
            return args.to_argv()

        self._autopilot_controller = AutopilotController(
            plan,
            argv_factory=_argv_factory,
            env_overrides=self._session_workdir.env_overrides(),
            parent=self,
        )
        # Q14=a / Q4=A: 起動前に全 (workflow, app_id) 組合せを WorkbenchState へ事前登録。
        # これにより Step 1 で選んだ全 workflow が Step 2 ツリーに pending 状態で並ぶ。
        self._prepopulate_workbench_with_seeds(
            self._build_autopilot_workflow_seeds(plan)
        )
        self._autopilot_controller.progress.connect(self._on_autopilot_progress)
        self._autopilot_controller.finished.connect(self._on_autopilot_finished)
        self._autopilot_controller.start()
        # Critical #3: ユーザーに進行を視覚的に提示するため Step 2 (Workbench) へ遷移
        self._activate_autopilot_workbench()
        self._setup_autopilot_log_routing()
        self._stack.setCurrentIndex(_STEP_WORKBENCH)
        self._refresh_navigation()
        self._update_title()
        self._set_status(
            StatusKind.RUNNING,
            self.tr("Autopilot 実行中: 0/{total} (並列上限 {mp})").format(
                total=len(plan.app_chains), mp=plan.max_parallel
            ),
        )

    def _create_autopilot_phase_window(
        self,
        workflow_id: str,
        *,
        title_template: str,
        status_running_template: str,
        on_finished,
    ):
        """Autopilot 経路（prephase / main_workflow）共通のウィンドウ生成。

        Autopilot 経路（prephase / main_workflow）共通のサブプロセス起動。

        T3.3 (gui-unified-workbench Wave 3): 旧 ChainLogWindow 生成を廃止し、
        受信したログ行は WorkbenchPage.append_log へ一本化して配信する。
        返却値は reader 保持用ハンドル（SimpleNamespace）。
        """
        from types import SimpleNamespace
        from .state_bridge import launch_orchestrator, SubprocessReader
        from .wizard import WizardResult

        result = WizardResult(workflow=workflow_id)
        argv = result.to_orchestrate_argv()
        # title はログ表示用 (同一シグネチャ保持のため計算のみ残置)
        _ = title_template.format(
            wf=workflow_id.upper(),
            idx=self._session_index,
        )
        win = SimpleNamespace()

        # gui-workbench-stats-propagation F3a:
        # WorkflowInstance を running 状態へ遷移させ、started_at を set する。
        # これによりツリー上のワークフロー行 elapsed がカウントアップ開始する。
        # （Plan モード _start_next_in_queue と同じ振る舞いに揃える）
        try:
            self._page_workbench.update_workflow_instance_status(
                workflow_id, "running"
            )
        except (AttributeError, RuntimeError):
            pass

        try:
            proc = launch_orchestrator(
                argv,
                env_overrides=self._session_workdir.env_overrides(),
            )
        except OSError as e:
            # T3.2: WorkbenchPage 統一 API へ配信
            try:
                self._page_workbench.append_log(
                    workflow_id, "", f"[ERROR] サブプロセス起動失敗: {e}"
                )
            except (AttributeError, RuntimeError):
                pass
            QTimer.singleShot(0, lambda: on_finished(-1, workflow_id, win))
            return win

        reader = SubprocessReader(proc, parent=self)

        def _on_line(line: str, _wf=workflow_id) -> None:
            # gui-workbench-stats-propagation F1':
            # 旧コードは `[hve:stats] {...}` 行をここで破棄していたが、それにより
            # step_status / tool_invoked / skill_invoked 等の構造化イベントが
            # WorkbenchState へ届かず、ツリー Step ステータス・経過時間・
            # Footer Tools/Skills 集計が更新されなかった。表示抑止は
            # WorkbenchPage.append_log 内に移植済み。
            try:
                self._page_workbench.append_log(_wf, "", line)
            except (AttributeError, RuntimeError):
                pass

        def _on_done(code: int, _wf=workflow_id, _w=win) -> None:
            on_finished(code, _wf, _w)

        reader.line_received.connect(_on_line)
        reader.finished_with_code.connect(_on_done)
        reader.start()
        # reader をハンドルに保持して GC を防ぐ
        win._reader = reader  # type: ignore[attr-defined]

        self._set_status(
            StatusKind.RUNNING,
            status_running_template.format(wf=workflow_id.upper()),
        )
        return win

    def _show_autopilot_phase_failure(
        self,
        workflow_id: str,
        code: int,
        *,
        status_failed_template: str,
        msgbox_title: str,
        msgbox_body_template: str,
    ) -> None:
        """Autopilot 経路（prephase / main_workflow）共通の失敗通知。"""
        self._set_status(
            StatusKind.ERROR,
            status_failed_template.format(
                wf=workflow_id.upper(),
                code=code,
            ),
        )
        QMessageBox.critical(
            self,
            msgbox_title,
            msgbox_body_template.format(
                wf=workflow_id.upper(),
                code=code,
            ),
        )

    # ------------------------------------------------------------------
    # Autopilot: WorkbenchPage への事前一括登録ヘルパ
    # (Issue: tree-unification Phase 1 / Q4=A / Q14=a)
    # ------------------------------------------------------------------

    def _build_autopilot_workflow_seeds(self, plan) -> list:
        """``AutopilotPlan`` から WorkbenchPage に流し込む seed リストを構築する。

        命名規約 (Q14=a):
          - pre_phases / main_workflows  → ``instance_id = workflow_id`` (app_id なし)
          - app_chains の (app_id, workflow_id)
                                          → ``instance_id = f"{workflow_id}#{app_id}"``

        Step 1 で確定した「実行対象 workflow × APP」全 instance を pending 状態で
        事前登録し、Step 2 ツリーが起動直後から全ノードを表示できるようにする。
        順序は ``AutopilotPlan.execution_order()`` を踏襲し、Step 1 依存ソート後の
        実行順 (Q5=A) で並べる。

        Phase 2 (Q3=B): container Step を親ノードとして含め、配下の非 container Step
        を ``StepSeed.children`` に階層化する (任意ネスト、Q7=B)。
        """
        from .workbench_state import WorkflowInstanceSeed

        seeds: list = []

        # pre_phases (ARD/AAS) — app_id なし、instance_id = workflow_id
        for wf_id in (getattr(plan, "pre_phases", None) or []):
            seeds.append(
                WorkflowInstanceSeed(
                    instance_id=wf_id,
                    workflow_id=wf_id,
                    label=wf_id,
                    app_id=None,
                    steps=_build_step_seeds_for_workflow(wf_id),
                )
            )

        # main_workflows (downstream 不在時の ARD/AAS) — pre_phases と同じ規約
        for wf_id in (getattr(plan, "main_workflows", None) or []):
            if any(s.instance_id == wf_id for s in seeds):
                continue
            seeds.append(
                WorkflowInstanceSeed(
                    instance_id=wf_id,
                    workflow_id=wf_id,
                    label=wf_id,
                    app_id=None,
                    steps=_build_step_seeds_for_workflow(wf_id),
                )
            )

        # app_chains — (workflow_id, app_id) ごとに 1 instance
        for chain in (getattr(plan, "app_chains", None) or []):
            app_id = getattr(chain, "app_id", "") or ""
            for wf_id in (getattr(chain, "workflows", None) or []):
                inst_id = f"{wf_id}#{app_id}" if app_id else wf_id
                if any(s.instance_id == inst_id for s in seeds):
                    continue
                label = f"{wf_id} ({app_id})" if app_id else wf_id
                seeds.append(
                    WorkflowInstanceSeed(
                        instance_id=inst_id,
                        workflow_id=wf_id,
                        label=label,
                        app_id=app_id or None,
                        steps=_build_step_seeds_for_workflow(wf_id),
                    )
                )

        return seeds

    def _build_workflow_queue_seeds(self, workflows: list) -> list:
        """pre_phases / main_workflows キュー用 seed (app_id なし) を生成する。

        Phase 2 (Q3=B): container Step を親に持つ階層構造で生成する。
        """
        from .workbench_state import WorkflowInstanceSeed

        seeds: list = []
        for wf_id in workflows:
            seeds.append(
                WorkflowInstanceSeed(
                    instance_id=wf_id,
                    workflow_id=wf_id,
                    label=wf_id,
                    app_id=None,
                    steps=_build_step_seeds_for_workflow(wf_id),
                )
            )
        return seeds

    def _extract_downstream_workflow_ids(
        self,
        *,
        plan=None,
        selection=None,
        pre_phases: Optional[List[str]] = None,
    ) -> List[str]:
        """downstream workflow_id 群を抽出する (gui-workbench-autopilot-display T3a)。

        chain_continuation 経路では ``plan.app_chains[].workflows`` から、
        pre_phase_only 経路では ``selection.downstream_workflow_ids()`` から
        downstream workflow を導出する。いずれも ``pre_phases`` に含まれる
        workflow_id は除外する（case-insensitive）。

        Returns:
            placeholder seed として先行表示する workflow_id 群（順序保持・重複排除）。
        """
        pre_set = {(w or "").strip().lower() for w in (pre_phases or [])}
        result: List[str] = []
        seen: set = set()

        if plan is not None:
            for chain in (getattr(plan, "app_chains", None) or []):
                for wf_id in (getattr(chain, "workflows", None) or []):
                    key = (wf_id or "").strip().lower()
                    if not key or key in pre_set or key in seen:
                        continue
                    seen.add(key)
                    result.append(wf_id)
            return result

        if selection is not None:
            # レビュー #3: ハードコードを廃し AutopilotSelection.downstream_workflow_ids
            # に処理を委譲する。
            try:
                downstream_ids = list(selection.downstream_workflow_ids())
            except AttributeError:
                downstream_ids = []
            for wf_id in downstream_ids:
                key = (wf_id or "").strip().lower()
                if not key or key in pre_set or key in seen:
                    continue
                seen.add(key)
                result.append(wf_id)
            return result

        return result

    def _prepopulate_workbench_with_seeds(self, seeds: list) -> None:
        """WorkbenchPage 経由で ``WorkbenchState.prepopulate_workflow_instances`` を呼ぶ。

        WorkbenchPage が seeds を受理する公開 API
        (``prepopulate_workflow_instances``) を持たない場合は無視する（後方互換）。

        gui-workbench-autopilot-display T2: prepopulate 前にセッション run_id を
        Header1 に push し、``(UNKNOWN) [run unknown]`` 表示を解消する。
        """
        if not seeds:
            return
        # T2: セッション run_id を Header1 へ反映
        try:
            run_id = getattr(self._session_workdir, "session_run_id", "") or ""
            if run_id:
                self._page_workbench.update_identity_from_session(run_id)
        except (AttributeError, RuntimeError):
            pass
        try:
            self._page_workbench.prepopulate_workflow_instances(seeds)
        except AttributeError:
            # 古い WorkbenchPage 実装では API 未提供 → ログ流入時の lazy 生成にフォールバック。
            pass
        except (TypeError, RuntimeError):
            pass

    # ------------------------------------------------------------------
    # Autopilot メインワークフロー経路（downstream 不在で ARD/AAS を主タスクとして実行）
    # ------------------------------------------------------------------

    def _launch_autopilot_main_workflow_queue(
        self,
        workflows: List[str],
        *,
        also_seed: Optional[List[str]] = None,
    ) -> None:
        """pre_phases / main_workflows を実行キューとして起動する。

        Args:
            workflows: 実行対象 workflow_id（直列実行する）。
            also_seed: 実行はしないが Step 2 ツリーに pending 表示しておきたい
                workflow_id 群（gui-workbench-autopilot-display T3a）。chain_continuation
                経路で xx-web 等の downstream workflow を先行表示するために使う。
                placeholder seed の instance_id は ``workflow_id`` 単体で投入される
                ため、app_chains 起動時に T3b の remove_workflow_instance で削除される。
        """
        # Q14=a / Q4=A: pre_phases / main_workflows を事前一括登録
        seed_ids: List[str] = list(workflows)
        # レビュー #8: case-insensitive で重複検査
        seen_lower = {(w or "").strip().lower() for w in seed_ids}
        for wf_id in also_seed or ():
            key = (wf_id or "").strip().lower()
            if not key or key in seen_lower:
                continue
            seen_lower.add(key)
            seed_ids.append(wf_id)
        self._prepopulate_workbench_with_seeds(
            self._build_workflow_queue_seeds(seed_ids)
        )
        self._autopilot_main_workflow_queue = list(workflows)
        self._autopilot_main_workflow_index = 0
        self._launch_next_autopilot_main_workflow()

    def _launch_next_autopilot_main_workflow(self) -> None:
        if self._autopilot_main_workflow_index >= len(getattr(self, "_autopilot_main_workflow_queue", [])):
            # 連結経路: pre_phases キュー完走 → app_chains 起動へ継続
            if getattr(self, "_autopilot_chain_continuation_pending", False):
                self._autopilot_chain_continuation_pending = False
                self._continue_autopilot_with_app_chains()
                return
            # T3: pre_phase_only モードでキュー完了 → downstream 継続確認 Dialog
            if getattr(self, "_autopilot_pre_phase_followup", False):
                self._autopilot_pre_phase_followup = False
                self._prompt_autopilot_downstream_continuation()
                return
            self._set_status(StatusKind.SUCCESS, self.tr("Autopilot: 完了"))
            return

        workflow_id = self._autopilot_main_workflow_queue[self._autopilot_main_workflow_index]
        self._launch_autopilot_main_workflow(workflow_id)

    def _prompt_autopilot_downstream_continuation(self) -> None:
        """T3: pre_phase_only 完了時の半自動継続 Dialog。

        ARD/AAS 完了で catalog が生成された想定 → ユーザーに downstream 継続意思
        を確認し、Yes なら build_plan を再実行して downstream チェーンを起動する。
        """
        selection = getattr(self, "_autopilot_pre_phase_selection", None)
        catalog_path = getattr(self, "_autopilot_pre_phase_catalog_path", None)
        max_parallel = getattr(self, "_autopilot_pre_phase_max_parallel", 4)
        if selection is None or catalog_path is None:
            self._set_status(StatusKind.SUCCESS, self.tr("Autopilot: 完了"))
            return

        answer = QMessageBox.question(
            self,
            self.tr("Autopilot: downstream 継続確認"),
            self.tr(
                "ARD/AAS の事前位相が完了しました。\n"
                "Application Architecture Catalog から downstream ワークフロー\n"
                "(Web/Dataflow Design/Deploy 等) を続けて実行しますか？"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._set_status(
                StatusKind.SUCCESS,
                self.tr("Autopilot: 事前位相完了（downstream スキップ）"),
            )
            return

        # R3: catalog 書き込み完了タイミング保証
        # ARD/AAS の子プロセスが「完了 signal」を出した直後でも、OS の write/flush が
        # 遅延して catalog ファイルが未読の状態が残るケースがある。存在＋非零サイズ
        # を指数バックオフ (0.2/0.5/1.0/2.0s 計 4 回 ≈ 3.7s) でリトライ。
        wait_intervals = (0.2, 0.5, 1.0, 2.0)
        catalog_ready = self._wait_catalog_ready(catalog_path, wait_intervals)
        if not catalog_ready:
            QMessageBox.warning(
                self,
                self.tr("Autopilot 警告"),
                self.tr(
                    "Application Architecture Catalog の生成が確認できませんでした。\n"
                    "{path}\n"
                    "ARD/AAS の出力ログを確認のうえ、手動で再実行してください。"
                ).format(path=str(catalog_path)),
            )
            return

        # catalog を再読してプラン再構築
        self._start_autopilot_app_chains_controller(
            selection=selection,
            catalog_path=catalog_path,
            max_parallel=max_parallel,
            status_running_template=self.tr(
                "Autopilot 実行中 (downstream): {done}/{total} (並列上限 {mp})"
            ),
            empty_warning_template=self.tr(
                "downstream 実行対象 APP が 0 件です。\n"
                "Application Architecture Catalog ({path}) を確認してください。"
            ),
        )

    def _continue_autopilot_with_app_chains(self) -> None:
        """連結経路: pre_phases キュー完走後に app_chains を AutopilotController で起動する。

        ``_prompt_autopilot_downstream_continuation`` と異なり継続確認 Dialog は
        出さない（ユーザーが明示的に ARD/AAS+downstream を同時選択済みのため）。
        """
        selection = getattr(self, "_autopilot_chain_continuation_selection", None)
        catalog_path = getattr(self, "_autopilot_chain_continuation_catalog_path", None)
        max_parallel = getattr(self, "_autopilot_chain_continuation_max_parallel", 4)
        if selection is None or catalog_path is None:
            self._set_status(StatusKind.SUCCESS, self.tr("Autopilot: 完了"))
            return

        # R3: catalog 書き込み完了タイミング保証（pre_phase_only と同様）
        wait_intervals = (0.2, 0.5, 1.0, 2.0)
        catalog_ready = self._wait_catalog_ready(catalog_path, wait_intervals)
        if not catalog_ready:
            QMessageBox.warning(
                self,
                self.tr("Autopilot 警告"),
                self.tr(
                    "Application Architecture Catalog の生成が確認できませんでした。\n"
                    "{path}\n"
                    "ARD/AAS の出力ログを確認のうえ、手動で再実行してください。"
                ).format(path=str(catalog_path)),
            )
            return

        self._start_autopilot_app_chains_controller(
            selection=selection,
            catalog_path=catalog_path,
            max_parallel=max_parallel,
            status_running_template=self.tr(
                "Autopilot 実行中 (app_chains): {done}/{total} (並列上限 {mp})"
            ),
            empty_warning_template=self.tr(
                "app_chains 実行対象 APP が 0 件です。\n"
                "Application Architecture Catalog ({path}) を確認してください。"
            ),
        )

    def _start_autopilot_app_chains_controller(
        self,
        *,
        selection: "AutopilotSelection",
        catalog_path: Path,
        max_parallel: int,
        status_running_template: str,
        empty_warning_template: str,
    ) -> None:
        """build_plan 再実行 → AutopilotController 起動の共通ヘルパ。

        ``_prompt_autopilot_downstream_continuation`` と
        ``_continue_autopilot_with_app_chains`` から共用される。
        """
        from .autopilot.planner import build_plan
        from .autopilot.child_launcher import AutopilotController

        plan = build_plan(catalog_path, max_parallel=max_parallel, selection=selection)
        if plan.is_empty():
            QMessageBox.warning(
                self,
                self.tr("Autopilot 警告"),
                empty_warning_template.format(path=str(catalog_path)),
            )
            return

        def _argv_factory(app_id: str, workflow_id: str) -> List[str]:
            args = self._page_options.build_args_for_workflow(
                workflow_id,
                repo_root=self._repo_root,
            )
            args.app_ids = app_id
            return args.to_argv()

        self._autopilot_controller = AutopilotController(
            plan,
            argv_factory=_argv_factory,
            env_overrides=self._session_workdir.env_overrides(),
            parent=self,
        )
        # T3b: pre_phase 段階で先行投入した placeholder (instance_id=workflow_id) を
        # 本 seed ("{wf}#{app}") と二重表示しないよう削除しておく。
        try:
            chain_wf_ids: set = set()
            for chain in (getattr(plan, "app_chains", None) or []):
                for wf_id in (getattr(chain, "workflows", None) or []):
                    if wf_id:
                        chain_wf_ids.add(wf_id)
            for wf_id in chain_wf_ids:
                self._page_workbench.remove_workflow_instance(wf_id)
        except (AttributeError, RuntimeError):
            pass
        # Q14=a / Q4=A: downstream 継続経路でも (workflow, app_id) を事前登録
        self._prepopulate_workbench_with_seeds(
            self._build_autopilot_workflow_seeds(plan)
        )
        self._autopilot_controller.progress.connect(self._on_autopilot_progress)
        self._autopilot_controller.finished.connect(self._on_autopilot_finished)
        self._autopilot_controller.start()
        self._activate_autopilot_workbench()
        self._setup_autopilot_log_routing()
        self._stack.setCurrentIndex(_STEP_WORKBENCH)
        self._refresh_navigation()
        self._update_title()
        self._set_status(
            StatusKind.RUNNING,
            status_running_template.format(
                done=0,
                total=len(plan.app_chains),
                mp=plan.max_parallel,
            ),
        )

    def _launch_autopilot_main_workflow(self, workflow_id: str) -> None:
        self._autopilot_main_workflow_window = self._create_autopilot_phase_window(
            workflow_id,
            title_template=self.tr("Autopilot 実行: {wf} — Session #{idx}"),
            status_running_template=self.tr("Autopilot: 実行中 ({wf})"),
            on_finished=self._on_autopilot_main_workflow_finished,
        )

    @Slot(int)
    def _on_autopilot_main_workflow_finished(self, code: int, workflow_id: str, win) -> None:
        # gui-workbench-stats-propagation F3b:
        # WorkflowInstance.finished_at を確定させ、ツリー上のワークフロー行
        # elapsed のカウントアップを停止する。Plan モード _on_process_finished
        # と同じ振る舞いに揃える。
        try:
            self._page_workbench.mark_workflow_instance_finished(workflow_id, code)
        except (AttributeError, RuntimeError):
            pass
        if code == 0:
            self._autopilot_main_workflow_index += 1
            self._launch_next_autopilot_main_workflow()
        else:
            # 失敗時は後続の連結経路 / pre_phase_only continuation を
            # 不用意に発火させないようフラグをリセットする（Critical #2）
            self._autopilot_chain_continuation_pending = False
            self._autopilot_pre_phase_followup = False
            self._show_autopilot_phase_failure(
                workflow_id,
                code,
                status_failed_template=self.tr(
                    "Autopilot: 失敗 ({wf}, exit code={code})"
                ),
                msgbox_title=self.tr("ワークフロー失敗"),
                msgbox_body_template=self.tr(
                    "{wf} が exit code={code} で失敗しました。"
                    "Autopilot を中止します。"
                ),
            )

    @Slot(int, int)
    def _on_autopilot_progress(self, done: int, total: int) -> None:
        # R2: _autopilot_controller は Optional[object] 型のため属性アクセス前に
        # None ガードする（type: ignore で動的属性 _plan も許可）。
        controller = self._autopilot_controller
        mp = 4
        if controller is not None:
            try:
                mp = controller._plan.max_parallel  # type: ignore[attr-defined]
            except AttributeError:
                mp = 4
        self._set_status(
            StatusKind.RUNNING,
            self.tr("Autopilot 実行中: {done}/{total} (並列上限 {mp})").format(
                done=done, total=total, mp=mp,
            ),
        )

    def _setup_autopilot_log_routing(self) -> None:
        """Autopilot controller の log_line signal を WorkbenchPage へ配信する。

        T4.1/T4.2 (gui-unified-workbench Wave 4): AutopilotQueuePage / ChainLogWindow
        を完全撤去したため、chain_finished は受け付けない。ログは WorkbenchPage
        に一本化される。
        """
        controller = self._autopilot_controller
        if controller is None:
            return
        log_sig = getattr(controller, "log_line", None)
        if log_sig is None:
            return

        # gui-workbench-stats-propagation F3a (app_chains fallback):
        # AutopilotController に lane 開始シグナルが無いため、初回ログ受信時に
        # 1 回だけ running 化する（update_workflow_instance_status は started_at が
        # None のときだけ set するため冪等）。
        seen_running: "set[str]" = set()

        def _on_log(event) -> None:
            app_id = getattr(event, "app_id", "") or ""
            workflow_id = getattr(event, "workflow_id", "") or ""
            line = getattr(event, "line", "")
            # Q14=a / Q17=a: instance_id 命名規約を "{workflow_id}#{app_id}" に統一。
            # app_chain 内で複数 workflow が同 lane を直列実行する場合でも、
            # workflow ごとに別 instance として WorkbenchState で扱う。
            if app_id and workflow_id:
                instance_id = f"{workflow_id}#{app_id}"
            else:
                instance_id = workflow_id or app_id
            if instance_id and instance_id not in seen_running:
                seen_running.add(instance_id)
                try:
                    self._page_workbench.update_workflow_instance_status(
                        instance_id, "running"
                    )
                except (AttributeError, RuntimeError):
                    pass
            try:
                self._page_workbench.append_log(instance_id, workflow_id, line)
            except (AttributeError, RuntimeError):
                pass

        # gui-workbench-stats-propagation F3b (app_chains):
        # AutopilotController.chain_finished(app_id, rc) は **app 単位** の連鎖完了
        # で 1 回 emit される（per-workflow 完了 signal が無い）。同 app に複数
        # workflow（W1→W2→W3 直列）が紐づく場合、chain 完了時刻で一括 finished 化
        # すると先行 workflow の elapsed が水増しされ、失敗時には成功済み workflow
        # も failed 表示される懸念がある（敵対的レビュー Critical No.1）。
        # 本 PR では app_chains 経路の per-workflow finished 化は **既知制約** と
        # して見送り、controller 側に per-workflow 終了 signal を追加する別 issue
        # で対応する。代替として、後続 lane の初回ログ受信や進捗 progress 経由で
        # 状態が暗黙に揃うことに依存する（ベストエフォート）。

        try:
            log_sig.connect(_on_log)
        except (AttributeError, RuntimeError):
            pass

    def _activate_autopilot_workbench(self) -> None:
        """Autopilot 経路の Workbench ページアクティブ化。

        T4.1 (gui-unified-workbench Wave 4): AutopilotQueuePage を撤去し、
        スタック切り替えとナビゲーション・タイトル更新のみ負う。
        """
        self._stack.setCurrentIndex(_STEP_WORKBENCH)
        self._refresh_navigation()
        self._update_title()

    @Slot()
    def _on_autopilot_finished(self) -> None:
        self._set_status(StatusKind.SUCCESS, self.tr("Autopilot: 全 APP 完了"))

    def _on_stop_all_clicked(self) -> None:
        """[停止] ボタン: Autopilot Controller と Workbench の両方を停止する。

        - Autopilot 実行中であれば ``_autopilot_controller.cancel_all()`` を呼び出し、
          後続 app chain と子プロセスを停止する（closeEvent と同じ手順）。
        - Workbench の現行サブプロセスを段階的シャットダウン（state_bridge T1 経由）。
        - ステータスバナーに「停止されました（全タスク）」を表示する。
        """
        self._stop_all_invoked = True

        # ① Autopilot Controller を停止（存在し、cancel_all を持つときのみ）
        ctrl = getattr(self, "_autopilot_controller", None)
        if ctrl is not None:
            try:
                if hasattr(ctrl, "cancel_all"):
                    ctrl.cancel_all()
            except Exception as exc:
                import sys as _sys
                print(
                    f"[gui] autopilot cancel_all failed in _on_stop_all_clicked: {exc}",
                    file=_sys.stderr,
                )

        # ② Workbench (orchestrator サブプロセス) を停止
        try:
            self._page_workbench.stop_orchestrator()
        except Exception as exc:
            import sys as _sys
            print(
                f"[gui] stop_orchestrator failed in _on_stop_all_clicked: {exc}",
                file=_sys.stderr,
            )

        # ③ ステータスバナー更新
        try:
            self._set_status(
                StatusKind.WARNING, self.tr("停止されました（全タスク）")
            )
        except Exception:
            pass

    @Slot(int)
    def _on_process_finished(self, returncode: int) -> None:
        self._refresh_navigation()
        was_stopped = self._page_workbench.was_stopped_by_user()
        if was_stopped:
            if getattr(self, "_stop_all_invoked", False):
                self._set_status(
                    StatusKind.WARNING, self.tr("停止されました（全タスク）")
                )
                self._stop_all_invoked = False
            else:
                self._set_status(StatusKind.WARNING, self.tr("停止されました"))
            # 停止時はヘッダー完了化・ポップアップ表示を行わない
            return
        if self._page_workbench.was_fatal():
            # 致命的エラー検知 → 後続ワークフローを実行せず専用ポップアップを出す。
            info = self._page_workbench.fatal_info() or {}
            self._set_status(
                StatusKind.ERROR,
                self.tr("Step 2: 致命的エラーで停止しました"),
            )
            try:
                self._header.mark_aborted(True)
            except AttributeError:
                pass
            self._btn_stop.setVisible(False)
            # fatal 時は「戻る」ボタンを例外的に有効化し Step 2 へ戻れるようにする。
            self._btn_back.setEnabled(True)
            QTimer.singleShot(0, lambda i=dict(info): self._show_fatal_popup(i))
            return
        if returncode == 0:
            self._set_status(
                StatusKind.SUCCESS,
                self.tr("Step 2: 完了 (all workflows succeeded)"),
            )
            msg_text = self.tr("全てのタスクが終わりました")
            icon = QMessageBox.Icon.Information
        else:
            self._set_status(
                StatusKind.WARNING,
                f"Step 2: 完了 (一部失敗あり, returncode={returncode})",
            )
            msg_text = self.tr("全てのタスクが終わりました（一部失敗あり）\nreturncode={rc}").format(rc=returncode)
            icon = QMessageBox.Icon.Warning

        # ヘッダーの ③ を完了状態にする
        self._header.mark_completed(True)
        # 停止ボタンを非表示（既に無効化されているが UX 改善）
        self._btn_stop.setVisible(False)

        # ポップアップはイベントループをブロックしないよう非同期表示
        QTimer.singleShot(0, lambda: self._show_completion_popup(icon, msg_text))

    def _show_completion_popup(self, icon: "QMessageBox.Icon", msg_text: str) -> None:
        """全タスク完了ポップアップを表示する。closeEvent 中はスキップ。"""
        if not self.isVisible():
            return
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(self.tr("完了"))
        box.setText(msg_text)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def _show_fatal_popup(self, info: Mapping[str, str]) -> None:
        """orchestrator が検知した致命的エラーをユーザーに呈示する。

        closeEvent 中は表示しない。長文のエラーメッセージは ``setDetailedText`` で
        ダイアログ幅を超えないよう表示する。
        """
        if not self.isVisible():
            return
        exc_type = str(info.get("exception_type") or "FatalError")
        msg = str(info.get("message") or "")
        _SUMMARY_MAX = 200
        msg_summary = msg if len(msg) <= _SUMMARY_MAX else (msg[:_SUMMARY_MAX] + " …")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(self.tr("致命的エラー"))
        box.setText(
            self.tr(
                "ワークフロー実行中に致命的エラーが発生しました。\n"
                "後続ワークフローの実行を停止しました。\n\n"
                "エラー種別: {exc_type}\nメッセージ: {msg}"
            ).format(exc_type=exc_type, msg=msg_summary)
        )
        detail_lines: List[str] = []
        if len(msg) > _SUMMARY_MAX:
            detail_lines.append(f"メッセージ全文:\n{msg}")
        raw_payload = info.get("raw_payload")
        if raw_payload:
            detail_lines.append(f"raw payload:\n{raw_payload}")
        if detail_lines:
            box.setDetailedText("\n\n".join(detail_lines))
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def _on_workflow_selection_changed(self, _wf_ids: list) -> None:
        self._refresh_navigation()
        # 左ペインの workflow チェック変更 → 右ペイン OptionsPage を即時更新。
        # Autopilot ON/OFF いずれでも同じ挙動とする（旧 AutopilotInputPanel と
        # OptionsPage の二重表示を廃止し OptionsPage に統一）。
        wf_ids = self._page_workflow.selected_workflow_ids()
        wf_names = self._page_workflow.selected_workflow_names()
        wf_name_map = {
            wf_id: (wf_names[i] if i < len(wf_names) else "")
            for i, wf_id in enumerate(wf_ids)
        }
        self._page_options.set_workflows(wf_ids, wf_name_map)
        # ARD 添付ペインに repo_root を伝播（_on_next_clicked 内の同等処理と整合）
        pane = self._page_options.attachment_pane()
        if pane is not None and hasattr(pane, "set_repo_root"):
            pane.set_repo_root(self._repo_root)

    # ----------------------------------------------------------
    # 新規セッション
    # ----------------------------------------------------------

    def _on_new_session_triggered(self) -> None:
        if self._on_new_session is not None:
            self._on_new_session()
        else:
            QMessageBox.information(
                self,
                self.tr("新規セッション"),
                self.tr("新規セッション起動コールバックが設定されていません。"
                "（プログラム的に起動する場合は MainWindow(on_new_session=...) を渡してください。）"),
            )

    # ----------------------------------------------------------
    # タイトル / クローズ
    # ----------------------------------------------------------

    def _update_title(self) -> None:
        # 要件: ウィンドウタイトルは "HVE Workbench" を含む。
        # Q4=b により Session #N 部分も保持する。
        self.setWindowTitle(f"HVE Workbench - Session #{self._session_index}")

    def _on_copilot_clicked(self) -> None:
        self._copilot_dock.setVisible(not self._copilot_dock.isVisible())

    # ----------------------------------------------------------
    # C: 「表示」メニュー — 横幅プリセット
    # ----------------------------------------------------------
    def _build_view_menu(self) -> QMenu:
        """ヘッダーの「表示」ボタン用ドロップダウンメニューを構築する。"""
        menu = QMenu(self)
        for label, width in (
            (self.tr("横幅: コンパクト (800px)"), 800),
            (self.tr("横幅: 標準 (1100px)"), 1100),
            (self.tr("横幅: ワイド (1400px)"), 1400),
        ):
            act = QAction(label, self)
            # ループ変数キャプチャを避けるため既定値で束縛。
            act.triggered.connect(lambda _checked=False, w=width: self._apply_width_preset(w))
            menu.addAction(act)
        menu.addSeparator()
        act_save = QAction(self.tr("現在の幅を既定にする"), self)
        act_save.triggered.connect(self._save_current_width_as_default)
        menu.addAction(act_save)
        return menu

    def _apply_width_preset(self, width: int) -> None:
        """指定幅へリサイズする。永続化は既存の resizeEvent デバウンスに任せる。"""
        # 最大化中はそのままだと resize が無効になるため、通常状態へ戻す。
        if self.isMaximized():
            self.showNormal()
        self.resize(int(width), self.height())

    def _save_current_width_as_default(self) -> None:
        """現在の幅を main_window_width として即時保存する。"""
        try:
            from . import settings_store as _ss

            _ss.set_option("main_window_width", int(self.width()))
        except OSError:
            pass

    def resizeEvent(self, event: "QResizeEvent") -> None:  # type: ignore[override]
        super().resizeEvent(event)
        # 起動直後の自動 resize は無視。ユーザー操作（および以後の resize）を保存対象にする。
        if getattr(self, "_width_persist_enabled", False):
            timer = getattr(self, "_width_save_timer", None)
            if timer is not None:
                timer.start()

    def _persist_window_width(self) -> None:
        w = int(self.width())
        # 最小化や一時状態で width() が極端に小さい値を返すケースを除外。
        if w < 200:
            return
        try:
            from . import settings_store as _ss

            _ss.set_option("main_window_width", w)
        except OSError:
            # 設定保存失敗は致命的ではない。
            pass

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self._page_workbench.is_running():
            ret = QMessageBox.question(
                self,
                self.tr("確認"),
                self.tr("実行中のセッションがあります。終了しますか？"),
            )
            if ret != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._page_workbench.cleanup()
        self._copilot_dock.shutdown()
        try:
            self._auth_monitor.stop()
        except Exception:
            pass
        # --- Autopilot Controller の参照解放（detached の子プロセスは継続） ---
        ctrl = getattr(self, "_autopilot_controller", None)
        if ctrl is not None:
            # Issue-gui-session-workdir-isolation Critical#2:
            # cleanup_policy=purge/archive 時の rmtree/zip と子プロセスの書き込みが
            # 競合しないよう、まず子プロセスを確実に terminate→wait する。
            try:
                if hasattr(ctrl, "cancel_all"):
                    ctrl.cancel_all()
            except Exception as _exc_cancel:
                import sys as _sys
                print(
                    f"[gui] autopilot cancel_all failed during closeEvent: {_exc_cancel}",
                    file=_sys.stderr,
                )
            try:
                if hasattr(ctrl, "_timer") and ctrl._timer is not None:
                    ctrl._timer.stop()
                if hasattr(ctrl, "_running"):
                    ctrl._running.clear()
                if hasattr(ctrl, "_queue"):
                    ctrl._queue.clear()
            except Exception:
                pass
            self._autopilot_controller = None
        # Issue-gui-session-workdir-isolation T6:
        # GUI セッション作業ディレクトリの後処理（keep / archive / purge）。
        # 上記 cancel_all() で子プロセスを terminate 済みのため競合は起きない想定。
        # cleanup 失敗はサイレントに沈黙させず stderr へ報告する（Major#11 / #16）。
        sw = getattr(self, "_session_workdir", None)
        if sw is not None:
            try:
                sw.cleanup()
            except Exception as _exc_cleanup:
                import sys as _sys
                print(
                    f"[gui] session_workdir cleanup failed "
                    f"(policy={sw.cleanup_policy}, path={sw.work_root}): {_exc_cleanup}",
                    file=_sys.stderr,
                )
        super().closeEvent(event)
