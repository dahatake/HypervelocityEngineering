"""hve.gui.page_workflow_select — Step 1: ワークフロー選択ページ。

設計書 §5 対応。

機能:
  - `workflow_registry.list_workflows()` からワークフロー一覧を取得し、
    チェックボックスで提示する。
  - ワークフロー選択時、そのワークフローのステップ一覧をチェックボックスで
    展開表示する（初期値: 全 ON）。
  - ステップの OFF/ON 操作時、`depends_on` を辿って依存関係を自動連動させる
    （OFF→依存先を自動 OFF / ON→依存元を自動 ON）。
  - 選択完了時は `selection_changed` シグナルを emit。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QSettings

from .help_popup import HelpPopupButton
from .page_intro import StepIntroBanner
from .workflow_display import format_workflow_label, format_workflow_label_html


# --------------------------------------------------------------------------
# 説明文辞書（設計書 §13.2 — `hve/__main__.py:L665-L675` の help テキスト由来）
# --------------------------------------------------------------------------

_WORKFLOW_DESCRIPTIONS = {
    "aas": "Architecture Design — アプリケーション設計（Step.1〜Step.7）",
    "aad-web": "Web App Design — Web 画面定義書・サービス定義書・TDD テスト仕様書",
    "asdw-web": "Web App Dev & Deploy — Web アプリ開発とデプロイ（TDD RED/GREEN）",
    "adfd": "Dataflow Design — バッチドメイン分析・ジョブ設計",
    "adfdv": "Dataflow Dev — データフローアプリ実装と Azure デプロイ",
    "akm": "Knowledge Management — knowledge/ D01〜D21 を 21 並列で生成",
    "aqod": "Original Docs Review — original-docs/ 質問票生成・横断レビュー",
    "adoc": "Source Codeからのドキュメント作成 — レイヤー別ドキュメント自動生成",
    "ard": "Auto Requirement Definition — 事業分析〜要件定義（4 グループ: 企業の事業分析 / 要求定義書作成 / KPI/OKR 定義（任意）/ ユースケース作成）",
}


# --------------------------------------------------------------------------
# カテゴリー定義（Step 1 のワークフロー一覧をカテゴリー枠でグルーピング表示）
# 未分類の ID は「その他」枠で末尾に表示する。
# --------------------------------------------------------------------------

_WORKFLOW_CATEGORIES: List[Tuple[str, List[str]]] = [
    ("Business Engineering (要求定義)", ["ard"]),
    ("Architecture Design",             ["aas"]),
    ("Software Engineering",            ["aad-web", "asdw-web", "adfd", "adfdv"]),
    ("Knowledge Management",            ["akm", "aqod", "adoc"]),
]


def _load_workflow_choices() -> List[Tuple[str, str]]:
    """`workflow_registry.list_workflows()` から (id, name) を取得する。

    インポートに失敗した場合は最低限のフォールバックを返す。
    """
    try:
        from hve.workflow_registry import list_workflows

        return [(wf.id, wf.name) for wf in list_workflows()]
    except Exception:
        # 実コード根拠（workflow_registry.py）に基づくフォールバック
        return [
            ("aas", "Architecture Design"),
            ("aad-web", "Web App Design"),
            ("asdw-web", "Web App Dev & Deploy"),
            ("adfd", "Dataflow Design"),
            ("adfdv", "Dataflow Dev"),
            ("akm", "Knowledge Management"),
            ("aqod", "Original Docs Review"),
            ("adoc", "Source Codeからのドキュメント作成"),
            ("ard", "Auto Requirement Definition"),
        ]


def _load_workflow_steps(wf_id: str) -> List[Tuple[str, str, List[str]]]:
    """指定ワークフローのステップ一覧 (step_id, title, depends_on) を返す。

    `is_container=True` のステップは除外する。
    """
    try:
        from hve.workflow_registry import get_workflow

        wf = get_workflow(wf_id)
        if wf is None:
            return []
        return [
            (s.id, s.title, list(s.depends_on))
            for s in wf.steps
            if not s.is_container
        ]
    except Exception:
        return []


# --------------------------------------------------------------------------
# StepsChecklistPanel — 1 ワークフロー分のステップチェックリスト
# --------------------------------------------------------------------------


class _WorkflowStepsGroup(QWidget):
    """1 ワークフローのステップ群（ヘッダ + チェックボックス列）。"""

    steps_changed = Signal(str, list)  # workflow_id, enabled_step_ids

    # ARD: 4 グループ体系のラベル定義。
    # `enabled_step_ids()` が返す ID は orchestrator 側の
    # `_ARD_GROUP_MAP` で実 Step ID ("1","1.1","1.2" / "2" / "4.1","4.2","4.3") に展開される。
    # "3" (KPI/OKR 定義・任意) は `_ARD_GROUP_MAP` に登録されていないため、orchestrator では `[sid]` で
    # そのまま実 Step ID として通る（既定 OFF、ユーザーが明示 ON した時のみ実行）。
    _ARD_GROUPS: List[Tuple[str, str, bool]] = [
        ("1", "企業の事業分析（事業分野候補列挙 → 分野別深掘り → 統合）", False),
        ("2", "要求定義書作成（Step 1 の出力があれば参考にし、無くてもよい）", True),
        ("3", "KPI/OKR 定義（任意・戦略的記述から KPI/OKR・計測データ・データ収集設計を生成）", True),
        ("4", "ユースケース作成（骨格抽出 → 詳細生成 → カタログ統合）", True),
    ]

    def __init__(
        self,
        workflow_id: str,
        workflow_name: str,
        steps: List[Tuple[str, str, List[str]]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._workflow_id = workflow_id
        # ARD はグループ ID を表示する。それ以外は registry の実 Step を表示する。
        self._steps: List[Tuple[str, str, List[str]]]
        if workflow_id == "ard":
            self._steps = [(gid, title, []) for gid, title, _on in self._ARD_GROUPS]
            self._default_on: Dict[str, bool] = {
                gid: default_on for gid, _title, default_on in self._ARD_GROUPS
            }
        else:
            self._steps = steps  # (id, title, depends_on)
            self._default_on = {sid: True for sid, _, _ in steps}
        self._checkboxes: Dict[str, QCheckBox] = {}
        self._depends_on: Dict[str, List[str]] = {sid: deps for sid, _, deps in self._steps}
        self._dependents: Dict[str, List[str]] = {sid: [] for sid, _, _ in self._steps}
        for sid, _, deps in self._steps:
            for d in deps:
                if d in self._dependents:
                    self._dependents[d].append(sid)
        # ARD の旧 hidden ステップ（"1.1" 選択時に Step "1" を自動付与）仕様は撤廃。
        # グループ ID "1" がそのまま `_ARD_GROUP_MAP` で 1/1.1/1.2 に展開される。
        self._hidden_step_ids: set = set()
        self._suppress_signals = False
        self._setup_ui(workflow_name)

    def _setup_ui(self, workflow_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header = QLabel(
            f"<b>{format_workflow_label_html(self._workflow_id, workflow_name)}</b> のステップ"
        )
        header.setStyleSheet("color: #333; padding: 2px 0;")
        layout.addWidget(header)

        # ARD: 4 グループ体系の説明
        if self._workflow_id == "ard":
            note = QLabel(
                self.tr("ℹ️ ARD は 4 グループ構成です。各グループは内部で複数の実 Step を順次実行します。\n"
                "Step 2（要求定義書作成）は Step 1 の出力があれば参考にしますが、無くても実行できます。")
            )
            note.setStyleSheet(
                "color: #555; background: #f5f5f5; "
                "padding: 4px 8px; border-left: 3px solid #888;"
            )
            note.setWordWrap(True)
            layout.addWidget(note)

        if not self._steps:
            empty = QLabel(self.tr("（ステップ情報が取得できませんでした）"))
            empty.setStyleSheet("color: #888; padding-left: 8px;")
            layout.addWidget(empty)
            return

        for step_id, title, _deps in self._steps:
            if step_id in self._hidden_step_ids:
                continue
            cb = QCheckBox(f"{step_id}  —  {title}")
            cb.setChecked(self._default_on.get(step_id, True))
            cb.setProperty("step_id", step_id)
            cb.toggled.connect(
                lambda checked, sid=step_id: self._on_step_toggled(sid, checked)
            )
            self._checkboxes[step_id] = cb

            row = QHBoxLayout()
            row.setContentsMargins(16, 0, 0, 0)
            row.addWidget(cb)
            row.addStretch()
            row_w = QWidget()
            row_w.setLayout(row)
            layout.addWidget(row_w)

    def enabled_step_ids(self) -> List[str]:
        # 可視チェックボックスの選択結果（ARD はグループ ID をそのまま返す）
        return [
            sid
            for sid, _, _ in self._steps
            if sid not in self._hidden_step_ids
            and self._checkboxes[sid].isChecked()
        ]

    def _on_step_toggled(self, step_id: str, checked: bool) -> None:
        if self._suppress_signals:
            return
        # ARD は各グループを単独で選択可能とするため依存伝播を行わない
        if self._workflow_id == "ard":
            self.steps_changed.emit(self._workflow_id, self.enabled_step_ids())
            return
        # 依存伝播 (Q3=b): OFF→依存先を自動 OFF / ON→依存元を自動 ON
        self._suppress_signals = True
        try:
            if not checked:
                for dep in self._collect_transitive(step_id, self._dependents):
                    cb = self._checkboxes.get(dep)
                    if cb is not None and cb.isChecked():
                        cb.setChecked(False)
            else:
                for dep in self._collect_transitive(step_id, self._depends_on):
                    cb = self._checkboxes.get(dep)
                    if cb is not None and not cb.isChecked():
                        cb.setChecked(True)
        finally:
            self._suppress_signals = False
        self.steps_changed.emit(self._workflow_id, self.enabled_step_ids())

    def _collect_transitive(
        self, start: str, graph: Dict[str, List[str]]
    ) -> List[str]:
        seen: List[str] = []
        stack: List[str] = list(graph.get(start, []))
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.append(node)
            stack.extend(graph.get(node, []))
        return seen


class WorkflowSelectPage(QWidget):
    """Step 1: ワークフロー選択ページ。

    Signals:
        selection_changed(list): 選択ワークフロー ID 一覧が変わると emit。
        steps_selection_changed(str, list): ステップ選択が変わると emit
            (workflow_id, enabled_step_ids)。
    """

    selection_changed = Signal(list)
    steps_selection_changed = Signal(str, list)
    autopilot_changed = Signal(bool, str)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        options_page: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._workflows: List[Tuple[str, str]] = _load_workflow_choices()
        self._selected_ids: List[str] = []
        self._step_groups: Dict[str, _WorkflowStepsGroup] = {}
        self._autopilot_enabled: bool = False
        self._options_page: Optional[QWidget] = options_page
        self._setup_ui()

    # ----------------------------------------------------------
    # 公開 API
    # ----------------------------------------------------------

    def selected_workflow_id(self) -> Optional[str]:
        return self._selected_ids[0] if self._selected_ids else None

    def selected_workflow_ids(self) -> List[str]:
        return list(self._selected_ids)

    def selected_workflow_name(self) -> Optional[str]:
        selected_id = self.selected_workflow_id()
        if selected_id is None:
            return None
        for wf_id, name in self._workflows:
            if wf_id == selected_id:
                return name
        return None

    def selected_workflow_names(self) -> List[str]:
        name_map = {wf_id: name for wf_id, name in self._workflows}
        return [name_map[wf_id] for wf_id in self._selected_ids if wf_id in name_map]

    def enabled_steps(self, workflow_id: str) -> List[str]:
        """指定ワークフローで ON のステップ ID 一覧を返す。"""
        grp = self._step_groups.get(workflow_id)
        if grp is None:
            return []
        return grp.enabled_step_ids()

    def all_enabled_steps(self) -> Dict[str, List[str]]:
        """選択中の全ワークフローについて ON ステップを返す。"""
        return {
            wf_id: grp.enabled_step_ids()
            for wf_id, grp in self._step_groups.items()
        }

    def apply_plan_review_gaps(self, suggestions) -> None:
        """Autopilot プランレビューで選択された ``GapSuggestion`` を反映する。

        各提案について:
          - 当該 workflow のチェックボックスを ON にする（未 ON の場合）
          - ``suggested_step_id`` + ``transitive_steps`` を ON にする
          - 既存 ON は維持（旧 ``auto_enable_workflow`` と異なり OFF にしない）
        """
        by_wf: Dict[str, set] = {}
        for s in suggestions:
            wf_id = getattr(s, "suggested_workflow_id", None)
            if not wf_id:
                continue
            target = by_wf.setdefault(wf_id, set())
            target.add(getattr(s, "suggested_step_id", ""))
            for t in getattr(s, "transitive_steps", []) or []:
                target.add(t)

        for workflow_id, step_ids in by_wf.items():
            for btn in self._group.buttons():
                if btn.property("workflow_id") == workflow_id and not btn.isChecked():
                    btn.setChecked(True)
                    break
            grp = self._step_groups.get(workflow_id)
            if grp is None or not step_ids:
                continue
            for sid, cb in grp._checkboxes.items():
                if sid in step_ids and not cb.isChecked():
                    cb.setChecked(True)

    # ----------------------------------------------------------
    # Autopilot 関連 公開 API
    # ----------------------------------------------------------

    def is_autopilot_enabled(self) -> bool:
        return self._autopilot_enabled

    def autopilot_catalog_path(self) -> str:
        if hasattr(self, "_autopilot_catalog_edit"):
            return self._autopilot_catalog_edit.text().strip()
        return ""

    def set_autopilot_catalog_path(self, path: str) -> None:
        if hasattr(self, "_autopilot_catalog_edit"):
            self._autopilot_catalog_edit.setText(path or "")

    # ----------------------------------------------------------
    # UI セットアップ
    # ----------------------------------------------------------

    def _setup_ui(self) -> None:
        desc = QLabel(
            self.tr("実行するワークフローを 1 つ以上選択してください。"
            "選択後、実行するステップをチェックボックスで調整できます。")
        )
        desc.setStyleSheet("color: #555; padding-left: 4px;")
        desc.setWordWrap(True)

        # --- ワークフロー チェックボックス群（カテゴリー別） ---
        self._group = QButtonGroup(self)
        self._group.setExclusive(False)
        wf_container = QWidget()
        wf_layout = QVBoxLayout(wf_container)
        wf_layout.setContentsMargins(8, 8, 8, 8)
        wf_layout.setSpacing(6)

        name_map = {wf_id: name for wf_id, name in self._workflows}
        categorized_ids: set = set()
        for _cat_name, ids in _WORKFLOW_CATEGORIES:
            categorized_ids.update(ids)
        uncategorized = [
            (wf_id, name) for wf_id, name in self._workflows
            if wf_id not in categorized_ids
        ]

        # カテゴリー定義 + 未分類 ID は末尾「その他」に集約
        categories: List[Tuple[str, List[Tuple[str, str]]]] = []
        for cat_name, ids in _WORKFLOW_CATEGORIES:
            items = [(wf_id, name_map[wf_id]) for wf_id in ids if wf_id in name_map]
            if items:
                categories.append((cat_name, items))
        if uncategorized:
            categories.append((self.tr("その他"), uncategorized))

        for cat_name, items in categories:
            header = QLabel(f"<b>{cat_name}</b>")
            header.setStyleSheet(
                "color: #222; padding: 6px 0 2px 0; "
                "border-bottom: 1px solid #ccc;"
            )
            wf_layout.addWidget(header)

            for wf_id, wf_name in items:
                label_text = format_workflow_label(wf_id, wf_name)
                checkbox = QCheckBox(label_text)
                checkbox.setProperty("workflow_id", wf_id)
                checkbox.toggled.connect(self._on_checkbox_toggled)
                self._group.addButton(checkbox)

                row = QHBoxLayout()
                row.setContentsMargins(16, 0, 0, 0)
                row.addWidget(checkbox)
                help_btn = HelpPopupButton.from_key(f"workflow.{wf_id}")
                if help_btn is not None:
                    row.addWidget(help_btn)
                row.addStretch()
                row_w = QWidget()
                row_w.setLayout(row)
                wf_layout.addWidget(row_w)
        wf_layout.addStretch()

        wf_scroll = QScrollArea()
        wf_scroll.setWidget(wf_container)
        wf_scroll.setWidgetResizable(True)

        # --- ステップ チェックリスト領域 ---
        self._steps_container = QWidget()
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(8, 8, 8, 8)
        self._steps_layout.setSpacing(8)
        self._steps_placeholder = QLabel(
            self.tr("（ワークフローを選択するとステップが表示されます）")
        )
        self._steps_placeholder.setStyleSheet("color: #888; padding: 8px;")
        self._steps_layout.addWidget(self._steps_placeholder)
        self._steps_layout.addStretch()

        steps_scroll = QScrollArea()
        steps_scroll.setWidget(self._steps_container)
        steps_scroll.setWidgetResizable(True)

        steps_header = QLabel(self.tr("実行ステップ（チェック ON のみ実行対象）"))
        steps_header.setStyleSheet("font-weight: bold; padding: 4px;")

        steps_section = QFrame()
        steps_section.setFrameShape(QFrame.Shape.StyledPanel)
        steps_section_layout = QVBoxLayout(steps_section)
        steps_section_layout.setContentsMargins(0, 0, 0, 0)
        steps_section_layout.addWidget(steps_header)
        steps_section_layout.addWidget(steps_scroll)

        # --- 左ペイン: 説明 · Autopilot · ワークフロー·ステップ ---
        # 旧 AutopilotInputPanel は廃止され、右ペインは OptionsPage 単独配置に統一された。
        # タイトル表示は HeaderBar (「① ワークフローの選択」) に集約されたため、ページ内タイトルは置かない。
        left_pane = QWidget()
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(16, 12, 8, 12)
        left_layout.addWidget(StepIntroBanner(0))
        left_layout.addWidget(desc)
        left_layout.addWidget(self._build_autopilot_section())
        left_layout.addWidget(wf_scroll, stretch=1)
        left_layout.addWidget(steps_section, stretch=1)

        # 左ペイン全体をスクロール可能にする
        left_scroll = QScrollArea()
        left_scroll.setWidget(left_pane)
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(0)
        left_pane.setMinimumWidth(0)

        # --- 右ペイン: OptionsPage 単独配置（旧 AutopilotInputPanel を統合）。
        # OptionsPage は内部に既に QScrollArea を持つため、ここでは二重ラップしない。
        # Autopilot ON/OFF いずれでも同じ OptionsPage を表示する。
        right_pane: QWidget
        if self._options_page is not None:
            self._options_page.setMinimumWidth(0)
            right_pane = self._options_page
        else:
            # 単体テスト互換: options_page 未指定時はプレースホルダを使う
            placeholder = QLabel(self.tr("（オプションページ未指定）"))
            placeholder.setStyleSheet("color: #888; padding: 16px;")
            right_pane = placeholder

        # --- QSplitter で左右分割 ---
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(left_scroll)
        self._splitter.addWidget(right_pane)
        # ペインの完全折りたたみを拒否（誤操作で UI が消える事故防止）
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setMinimumWidth(0)
        # 既定比率: 5:5
        self._splitter.setSizes([500, 500])

        # スプリッタ比率の永続化
        self._restore_splitter_sizes()
        self._splitter.splitterMoved.connect(self._save_splitter_sizes)

        # 全体レイアウト
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter, stretch=1)

    # ----------------------------------------------------------
    # Splitter サイズ永続化 (QSettings)
    # ----------------------------------------------------------

    _SPLITTER_SETTINGS_KEY = "gui/workflow_select/splitter_sizes"

    def _restore_splitter_sizes(self) -> None:
        MIN_PANE_WIDTH = 100
        try:
            settings = QSettings("hve", "hve-gui")
            v = settings.value(self._SPLITTER_SETTINGS_KEY, None)
            if isinstance(v, (list, tuple)) and len(v) == 2:
                sizes = [int(x) for x in v]
                # 両ペインとも最低幅以上を必須とし、片側 0 の復元を拒否
                if all(s >= MIN_PANE_WIDTH for s in sizes):
                    self._splitter.setSizes(sizes)
        except Exception:
            pass

    def _save_splitter_sizes(self, *_args) -> None:
        try:
            settings = QSettings("hve", "hve-gui")
            settings.setValue(self._SPLITTER_SETTINGS_KEY, self._splitter.sizes())
        except Exception:
            pass

    # ----------------------------------------------------------
    # Autopilot UI セットアップ
    # ----------------------------------------------------------

    def _build_autopilot_section(self) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #f6f8fa; border: 1px solid #d0d7de;"
            " border-radius: 4px; padding: 6px; }"
        )
        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(8, 6, 8, 6)
        vbox.setSpacing(4)

        self._autopilot_cb = QCheckBox(
            self.tr("🤖 Autopilot — Application Architecture Catalog "
                    "から実行ワークフローを自動判定する")
        )
        self._autopilot_cb.toggled.connect(self._on_autopilot_toggled)
        vbox.addWidget(self._autopilot_cb)

        note = QLabel(
            self.tr("ON にすると `推薦アーキテクチャ` に応じて "
                    "`aad-web → asdw-web` または `adfd → adfdv` を APP ごとに自動実行します。"
                    "下のワークフロー/ステップ選択は無効化されます。")
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555; padding-left: 24px;")
        vbox.addWidget(note)

        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 0, 0)
        row.addWidget(QLabel(self.tr("カタログパス:")))
        self._autopilot_catalog_edit = QLineEdit()
        self._autopilot_catalog_edit.setPlaceholderText(
            "docs/catalog/app-arch-catalog.md"
        )
        self._autopilot_catalog_edit.setEnabled(False)
        self._autopilot_catalog_edit.textChanged.connect(self._emit_autopilot_changed)
        row.addWidget(self._autopilot_catalog_edit, stretch=1)
        row_w = QWidget()
        row_w.setLayout(row)
        vbox.addWidget(row_w)

        return frame

    def _on_autopilot_toggled(self, checked: bool) -> None:
        self._autopilot_enabled = checked
        # 要件: Autopilot ON でも workflow 選択は有効維持。
        # OptionsPage は Autopilot ON/OFF に依らず常に右ペインに表示される（統合済み）。
        for grp in self._step_groups.values():
            grp.setEnabled(not checked)
        if hasattr(self, "_autopilot_catalog_edit"):
            self._autopilot_catalog_edit.setEnabled(checked)
        self._emit_autopilot_changed()
        # バナーも Autopilot 状態に追随させる
        self._notify_requirements_banner()

    def _emit_autopilot_changed(self, *_args) -> None:
        self.autopilot_changed.emit(
            self._autopilot_enabled,
            self._autopilot_catalog_edit.text().strip()
            if hasattr(self, "_autopilot_catalog_edit") else "",
        )
        # カタログパス変更時もバナー更新
        self._notify_requirements_banner()

    # ----------------------------------------------------------
    # シグナルハンドラ
    # ----------------------------------------------------------

    def _on_checkbox_toggled(self, _checked: bool) -> None:
        selected: List[str] = []
        for btn in self._group.buttons():
            wf_id = btn.property("workflow_id")
            if not isinstance(wf_id, str):
                continue
            if btn.isChecked():
                selected.append(wf_id)
        self._selected_ids = selected
        self._rebuild_steps_panel()
        self.selection_changed.emit(self.selected_workflow_ids())

    def _rebuild_steps_panel(self) -> None:
        # 既存グループのうち、選択解除されたものを削除
        for wf_id in list(self._step_groups.keys()):
            if wf_id not in self._selected_ids:
                grp = self._step_groups.pop(wf_id)
                self._steps_layout.removeWidget(grp)
                # setParent(None) のみだと可視状態の widget が一瞬トップレベル
                # ウィンドウ化してフラッシュ表示されるため、先に非表示化する。
                grp.setVisible(False)
                grp.setParent(None)
                grp.deleteLater()

        # 新規選択分のグループを追加
        name_map = {w: n for w, n in self._workflows}
        for wf_id in self._selected_ids:
            if wf_id in self._step_groups:
                continue
            steps = _load_workflow_steps(wf_id)
            grp = _WorkflowStepsGroup(wf_id, name_map.get(wf_id, wf_id), steps)
            grp.steps_changed.connect(self._on_steps_changed)
            if self._autopilot_enabled:
                grp.setEnabled(False)
            self._step_groups[wf_id] = grp
            # placeholder と末尾 stretch の前に挿入
            insert_at = max(0, self._steps_layout.count() - 1)
            self._steps_layout.insertWidget(insert_at, grp)

        # 表示順を `_selected_ids` の順（= ワークフロー定義の正準順）に整列。
        # 差分更新では新規分が末尾追加されるためクリック順に並ぶ問題を補正する。
        for idx, wf_id in enumerate(self._selected_ids):
            grp = self._step_groups.get(wf_id)
            if grp is None:
                continue
            current_idx = self._steps_layout.indexOf(grp)
            if current_idx != idx:
                self._steps_layout.removeWidget(grp)
                self._steps_layout.insertWidget(idx, grp)

        self._steps_placeholder.setVisible(not self._selected_ids)

        # 初期状態（全 ON）を一度 emit
        for wf_id, grp in self._step_groups.items():
            self.steps_selection_changed.emit(wf_id, grp.enabled_step_ids())

        # 必須要件サマリーバナーを更新（Task D）
        self._notify_requirements_banner()

    def _on_steps_changed(self, workflow_id: str, enabled_step_ids: List[str]) -> None:
        self.steps_selection_changed.emit(workflow_id, enabled_step_ids)
        self._notify_requirements_banner()

    # ----------------------------------------------------------
    # 必須要件サマリーバナー連携（Task D）
    # ----------------------------------------------------------

    def _collect_all_selected_steps(self) -> List[Tuple[str, List[str]]]:
        """選択ワークフロー × 選択ステップ ID 一覧を返す。"""
        return [
            (wf_id, grp.enabled_step_ids())
            for wf_id, grp in self._step_groups.items()
        ]

    def _notify_requirements_banner(self) -> None:
        """OptionsPage 側のバナーを最新の選択状態で更新する。"""
        if self._options_page is None:
            return
        updater = getattr(self._options_page, "update_requirements_banner", None)
        if not callable(updater):
            return
        try:
            updater(
                self._collect_all_selected_steps(),
                autopilot_mode=self._autopilot_enabled,
                autopilot_catalog_path=(
                    self._autopilot_catalog_edit.text().strip()
                    if hasattr(self, "_autopilot_catalog_edit") else None
                ) or None,
            )
        except Exception:
            # 表示更新失敗で本体機能を止めない
            pass
