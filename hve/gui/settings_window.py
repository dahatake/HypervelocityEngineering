"""hve.gui.settings_window — VS Code 風の設定ウィンドウ。

レイアウト:
  - 上部: 検索バー
  - 左ペイン: QTreeWidget (カテゴリツリー)
  - 右ペイン: QStackedWidget (選択カテゴリのフォーム)

設定変更は自動保存（VS Code 流）。既存の `page_options._C1..._C16` ウィジェットを
再利用し、設定パネル内で同じ入力体験を提供する。
Markdown-Query セクションの実体は
``tools/skills/markdown_query/gui/settings_section.py`` (`MdqIndexSection`) へ移設済み。
本ファイルは import 経由でそれを参照し、skill_sections レジストリに登録するのみ。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from . import settings_store, skill_sections
from .i18n import available_languages
from .page_options import (
    _C1Basic,
    _C3AutoPrompt,
    _C4WorkIQ,
    _C5IssuePR,
    _C7Connection,
    _C10AppId,
    _C11AKM,
    _C12AQOD,
    _C13ADOC,
    _C14ARD,
    _CAzure,
    _LabeledField,
)



# ---------------------------------------------------------------------------
# Markdown-Query セクション
# ---------------------------------------------------------------------------
# 実体は tools/skills/markdown_query/gui/settings_section.py へ移設済み。
# HVE GUI 側はその ``MdqIndexSection`` を import し、``_MdqIndexSection``
# エイリアスとして公開する（settings_apply 側で属性名 ``mdq_watch`` /
# ``mdq_watch_debounce_ms`` を参照するため、クラス名は維持しなくて良いが
# 参照しやすさのため別名を残す）。
from tools.skills.markdown_query.gui.settings_section import (
    MdqIndexSection as _MdqIndexSection,
)
# ---------------------------------------------------------------------------
# Language セクション
# ---------------------------------------------------------------------------
class _LanguageSection(QWidget):
    """GUI 表示言語の選択セクション。

    変更時には ``QMessageBox`` で再起動を案内する。実際の翻訳ロードは次回
    ``run_app`` 起動時に ``hve.gui.i18n.install_translator`` が行う。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.language = QComboBox()
        for code, display in available_languages():
            self.language.addItem(display, code)

        form = QFormLayout()
        form.addRow("表示言語 / Language:", self.language)

        notice = QLabel(
            self.tr("変更はアプリの再起動後に反映されます。\n"
            "Changes take effect after the app restarts.")
        )
        notice.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.addLayout(form)
        root.addWidget(notice)
        root.addStretch(1)

        self._suppress_notice = True  # 初期反映時の誤通知を抑制
        self.language.currentIndexChanged.connect(self._on_changed)

    def _on_changed(self, _idx: int) -> None:
        if self._suppress_notice:
            self._suppress_notice = False
            return
        QMessageBox.information(
            self,
            self.tr("再起動が必要です / Restart required"),
            self.tr("言語の変更を反映するには HVE GUI を再起動してください。\n"
            "Please restart HVE GUI to apply the language change."),
        )


# ---------------------------------------------------------------------------
# Autopilot セクション
# ---------------------------------------------------------------------------
class _CAutopilotSection(QWidget):
    """Autopilot モードの動作設定セクション。

    現状の設定項目:
      - ``autopilot_max_parallel`` (int, 1〜16, 既定 4)
      - ``step1_show_plan_review_always`` (bool, 既定 False, R5-c)
        旧名: ``autopilot_show_plan_review_always``。Step 1 [次へ] 統合 precheck で
        Autopilot ON/OFF いずれでも参照される共通設定として中立化済み。
      - ``autopilot_show_app_id_picker`` (bool, 既定 True)
        AAS 完了後 / downstream 起動前に APP-ID 選択ダイアログを表示するか。
      - ``autopilot_app_id_picker_timeout_sec`` (int, 30〜3600, 既定 300)
        上記ダイアログのタイムアウト秒数。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.autopilot_max_parallel = QSpinBox()
        self.autopilot_max_parallel.setRange(1, 16)
        self.autopilot_max_parallel.setValue(4)
        layout.addWidget(_LabeledField(
            title=self.tr("並列上限 (autopilot_max_parallel)"),
            description=self.tr(
                "Autopilot モードで同時に起動する子 GUI プロセスの最大数。"
                " 範囲 1〜16、既定 4。"
                " Copilot CLI のレート制限を考慮して安全側を選んでください。"
            ),
            input_widget=self.autopilot_max_parallel,
        ))

        # R5-c: プランレビュー Dialog 常時表示（Step 1 [次へ] 共通設定）
        self.step1_show_plan_review_always = QCheckBox(
            self.tr("プランレビュー Dialog を常に表示する")
        )
        layout.addWidget(_LabeledField(
            title=self.tr("プランレビュー表示 (step1_show_plan_review_always)"),
            description=self.tr(
                "ON にすると、Step 1 [次へ] 押下時にギャップ提案が 0 件のときも"
                " 実行プランの入出力一覧を確認する Dialog を表示します。"
                " OFF（既定）はギャップ 0 件のとき自動的に Dialog を skip します。"
                " Autopilot ON/OFF のいずれでも適用されます。"
            ),
            input_widget=self.step1_show_plan_review_always,
        ))

        # APP-ID 選択ダイアログ ON/OFF（AAS 完了後・downstream 起動前）
        self.autopilot_show_app_id_picker = QCheckBox(
            self.tr("APP-ID 選択画面の表示")
        )
        layout.addWidget(_LabeledField(
            title=self.tr("APP-ID 選択画面 (autopilot_show_app_id_picker)"),
            description=self.tr(
                "ON（既定）にすると、AAS 完了後 / downstream 起動前に APP-ID 選択"
                " ダイアログを表示します。ユーザーは downstream（Web/Dataflow 等）"
                " の実行対象 APP-ID を絞り込めます。"
                " OFF の場合は Application Architecture Catalog 全件を downstream に"
                " 流します（旧挙動）。"
            ),
            input_widget=self.autopilot_show_app_id_picker,
        ))

        # APP-ID 選択ダイアログのタイムアウト秒数
        self.autopilot_app_id_picker_timeout_sec = QSpinBox()
        self.autopilot_app_id_picker_timeout_sec.setRange(30, 3600)
        self.autopilot_app_id_picker_timeout_sec.setValue(300)
        self.autopilot_app_id_picker_timeout_sec.setSuffix(self.tr(" 秒"))
        layout.addWidget(_LabeledField(
            title=self.tr(
                "APP-ID 選択タイムアウト (autopilot_app_id_picker_timeout_sec)"
            ),
            description=self.tr(
                "APP-ID 選択ダイアログのタイムアウト秒数（既定 300 秒 = 5 分）。"
                " タイムアウト経過時はその時点のチェック状態で自動 OK となり、"
                " 選択中の APP-ID で downstream が実行されます。"
                " 範囲 30〜3600 秒。"
                " 上記「APP-ID 選択画面の表示」が OFF のときは無効。"
            ),
            input_widget=self.autopilot_app_id_picker_timeout_sec,
        ))

        layout.addStretch(1)


# ---------------------------------------------------------------------------
# エクスプローラー（ファイルツリー）監視ルート設定セクション
# ---------------------------------------------------------------------------
class _CExplorerSection(QWidget):
    """エクスプローラーの監視ルートを編集するセクション。

    保存キー: ``explorer_roots`` (";" 区切りのリポジトリ相対 / 絶対パスリスト)。

    UI:
        - QListWidget でフォルダ一覧を表示
        - 「追加…」 ``QFileDialog.getExistingDirectory()``
        - 「削除」 選択行を取り除く
        - 設定値の橋渡し用に **非表示 QLineEdit** ``explorer_roots`` を保持し、
          settings_apply のジェネリック ``_get/_set`` 経由で自動保存されるようにする。

    Note:
        本ウィジェットは設定値の "編集" のみを担当する。実ディレクトリ作成は
        ``hve.gui.explorer_roots.resolve_explorer_roots()`` で行われる。
    """

    def __init__(self, repo_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QFileDialog, QListWidget

        self._repo_root = repo_root

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel(self.tr("エクスプローラー監視フォルダー"))
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel(
            self.tr(
                "左サイドバーのエクスプローラーに表示するフォルダーを設定します。"
                " 未存在のフォルダーは保存時と GUI 起動時に自動作成されます。"
                " リポジトリ相対パス（例: docs）と絶対パスの両方が使えます。"
            )
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #6a737d;")
        layout.addWidget(desc)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton(self.tr("追加…"))
        self._btn_remove = QPushButton(self.tr("削除"))
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # settings_apply が参照するフィールド。非表示で値だけ保持する。
        # Tab フォーカスを受け取らないよう NoFocus を明示（UX 上、隠し要素には不要）。
        self.explorer_roots = QLineEdit()
        self.explorer_roots.setVisible(False)
        self.explorer_roots.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.explorer_roots)

        # 入出力同期。
        # textChanged は外部からの setText（設定ロード時）に応答して QListWidget を
        # 再構築する。内部の _commit_list_to_text 経由でも textChanged が再発火するが、
        # 同値による setText は emit されない Qt の仕様により再帰しない。
        self.explorer_roots.textChanged.connect(self._on_text_changed)
        self._btn_add.clicked.connect(self._on_add_clicked)
        self._btn_remove.clicked.connect(self._on_remove_clicked)

        self._file_dialog_factory = QFileDialog  # テスト差し替え用

    # ------------------------------------------------------------------
    # ;-区切り文字列 → QListWidget の同期
    # ------------------------------------------------------------------
    def _on_text_changed(self, text: str) -> None:
        self._list.clear()
        for token in (text or "").split(";"):
            t = token.strip()
            if t:
                self._list.addItem(t)

    def _commit_list_to_text(self) -> None:
        tokens = [self._list.item(i).text().strip() for i in range(self._list.count())]
        tokens = [t for t in tokens if t]
        new_text = ";".join(tokens)
        if new_text != self.explorer_roots.text():
            self.explorer_roots.setText(new_text)
            # textChanged は同じ値だと発火しないが、editingFinished で自動保存される。
            # 明示的に editingFinished を emit してオートセーブを駆動する。
            self.explorer_roots.editingFinished.emit()

    def _on_add_clicked(self) -> None:
        d = self._file_dialog_factory.getExistingDirectory(
            self,
            self.tr("フォルダーを選択"),
            str(self._repo_root),
        )
        if not d:
            return
        # リポジトリ相対化を試みる（相対が可能なら相対、無理なら絶対のまま）。
        chosen = Path(d).resolve()
        try:
            rel = chosen.relative_to(self._repo_root.resolve())
            token = rel.as_posix()
        except ValueError:
            token = chosen.as_posix()
        # 重複は追加しない
        existing = {self._list.item(i).text() for i in range(self._list.count())}
        if token in existing:
            return
        self._list.addItem(token)
        self._commit_list_to_text()

    def _on_remove_clicked(self) -> None:
        rows = sorted({i.row() for i in self._list.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for r in rows:
            self._list.takeItem(r)
        self._commit_list_to_text()


# ---------------------------------------------------------------------------
# SettingsWindow 本体
# ---------------------------------------------------------------------------
# VS Code 風のカテゴリ階層定義。
# (group_label, [(node_label, section_key)])
_CATEGORY_TREE: List[Tuple[str, List[Tuple[str, str]]]] = [
    (
        "一般",
        [
            ("基本設定", "C1"),
            ("自動プロンプト", "C3"),
            ("Autopilot", "AUTOPILOT"),
            ("言語 / Language", "LANG"),
            ("エクスプローラー", "EXPLORER"),
        ],
    ),
    (
        "連携",
        [
            ("Git", "C5"),
            ("Azure", "AZURE"),
            ("MCP / CLI 接続", "C7"),
            ("Work IQ", "C4"),
        ],
    ),
    # 「ワークフロー固有設定」(C10/C11/C12/C13) は Step 1 右ペインのワークフロー枠で
    # 編集する設計に統一したため設定画面からは削除。C14 (ARD) は従来通り Step 1 右ペインのみ。
    # `_C10AppId` / `_C11AKM` 等のクラスは OptionsPage が直接インスタンス化するため
    # import は残置する（`_section_factory` 内の C10〜C13 分岐も維持）。
    (
        "skills",
        # スキル名子ノードは hve.gui.skill_sections レジストリから動的に
        # 生成される（SettingsWindow._setup_ui 内で _build_category_tree を介して
        # 展開）。ここではコンテナ・センチネルとして空リストを保持する。
        [],
    ),
]


def _build_category_tree() -> List[Tuple[str, List[Tuple[str, str]]]]:
    """``_CATEGORY_TREE`` の ``skills`` 配下をレジストリ内容で展開して返す。

    レジストリへの登録が無い場合、``skills`` カテゴリは空リストのまま返される
    （SettingsWindow 側で空グループは表示されるがリーフが無いため選択不能）。
    """
    expanded: List[Tuple[str, List[Tuple[str, str]]]] = []
    for label, items in _CATEGORY_TREE:
        if label == "skills":
            entries = [(e.label, e.key)
                       for e in skill_sections.get_registry().entries()]
            expanded.append((label, entries))
        else:
            expanded.append((label, items))
    return expanded


class SettingsWindow(QMainWindow):
    """VS Code 風の設定ウィンドウ（非モーダル）。"""

    settings_changed = Signal(dict)  # 保存後の設定 dict を通知

    def __init__(
        self,
        *,
        repo_root: Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._repo_root = repo_root
        self._settings: Dict[str, Dict[str, Any]] = settings_store.load()
        self._sections: Dict[str, QWidget] = {}
        self._tree_items: List[QTreeWidgetItem] = []
        self._stack_index_by_key: Dict[str, int] = {}

        self.setWindowTitle(self.tr("HVE 設定"))
        self.resize(1000, 700)
        self._setup_ui()
        self._apply_settings_to_widgets()
        self._wire_autosave()

    # ----------------------------------------------------------
    # UI セットアップ
    # ----------------------------------------------------------
    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        # 検索バー
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(self.tr("設定を検索..."))
        self._search_edit.textChanged.connect(self._on_search_changed)

        # 左ペイン: ツリー
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.itemSelectionChanged.connect(self._on_tree_selection_changed)

        # 右ペイン: Stacked
        self._stack = QStackedWidget()

        for group_label, items in _build_category_tree():
            group_item = QTreeWidgetItem([group_label])
            group_item.setFlags(group_item.flags() & ~Qt.ItemIsSelectable)
            self._tree.addTopLevelItem(group_item)
            for node_label, key in items:
                child = QTreeWidgetItem([node_label])
                child.setData(0, Qt.UserRole, key)
                group_item.addChild(child)
                self._tree_items.append(child)

                widget = self._build_section_widget(key)
                self._sections[key] = widget
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                # 設定画面では水平スクロールを抑止する（page_options.py の
                # メイン scroll と同様）。長いタイトル/入力行は内部で折り返す。
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                # widget を上詰めで表示するため、末尾に stretch を持つ
                # コンテナで包んでから scroll に渡す。
                container = QWidget()
                container_layout = QVBoxLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(0)
                container_layout.addWidget(widget)
                container_layout.addStretch(1)
                scroll.setWidget(container)
                idx = self._stack.addWidget(scroll)
                self._stack_index_by_key[key] = idx

        self._tree.expandAll()

        # 既定の選択: 最初のリーフ
        if self._tree_items:
            self._tree.setCurrentItem(self._tree_items[0])

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        # 左ペインの初期幅を 260 に拡大（長いノードラベル例:
        # "Source Codeからのドキュメント作成 (ADOC)" の水平スクロールを回避）。
        splitter.setSizes([260, 740])

        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        # 検索バーは「{ラベル} {テキストボックス(幅最大)}」の左寄せ配置にする。
        _search_row = QHBoxLayout()
        _search_label = QLabel(self.tr("検索:"))
        _search_label.setMaximumWidth(280)
        _search_row.addWidget(_search_label, 0)
        _search_row.addWidget(self._search_edit, 1)
        root.addLayout(_search_row)
        root.addWidget(splitter, stretch=1)

        # ステータス: 自動保存表示
        self._status_label = QLabel(self.tr("変更は自動的に保存されます"))
        self._status_label.setStyleSheet("color: #6a737d; padding: 4px;")
        root.addWidget(self._status_label)

    def _build_section_widget(self, key: str) -> QWidget:
        if key == "C1":
            return _C1Basic()
        if key == "C3":
            return _C3AutoPrompt()
        if key == "C4":
            return _C4WorkIQ()
        if key == "C5":
            return _C5IssuePR()
        if key == "C7":
            return _C7Connection()
        if key == "AZURE":
            return _CAzure()
        if key == "C10":
            return _C10AppId()
        if key == "C11":
            return _C11AKM()
        if key == "C12":
            return _C12AQOD()
        if key == "C13":
            return _C13ADOC()
        if key == "C14":
            return _C14ARD()
        if key == "LANG":
            return _LanguageSection()
        if key == "AUTOPILOT":
            return _CAutopilotSection()
        if key == "EXPLORER":
            return _CExplorerSection(self._repo_root)
        # skills レジストリ経由で登録されたセクション
        entry = skill_sections.get_registry().get(key)
        if entry is not None:
            return entry.section_factory(self._repo_root, None)
        return QLabel(f"(未実装: {key})")

    # ----------------------------------------------------------
    # 設定値 ↔ ウィジェットの双方向反映
    # ----------------------------------------------------------
    def _apply_settings_to_widgets(self) -> None:
        """settings_store の値を各ウィジェットへ反映する。"""
        from . import settings_apply

        settings_apply.apply_to_widgets(self._sections, self._settings)

    def _wire_autosave(self) -> None:
        """各ウィジェットの変更シグナルを購読し、自動保存する。"""
        from . import settings_apply

        settings_apply.wire_autosave(
            self._sections,
            on_changed=self._on_widget_changed,
        )

    def reload_models(self) -> None:
        """モデルキャッシュ更新後に呼ばれる。C1 セクションのモデル系コンボを再投入する。"""
        widget = self._sections.get("C1")
        if widget is None:
            return
        fn = getattr(widget, "reload_models", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def _on_widget_changed(self) -> None:
        from . import settings_apply

        # 全ウィジェットから値を取り出し、設定 dict に反映してから保存。
        # 別経路（例: _MdqIndexSection._persist_settings()）でファイルへ書かれた
        # 最新値（[mdq] target_folders 等）を、起動時スナップショット self._settings
        # の古い値で上書きしないよう、保存直前にファイルから再読込してマージする。
        new_options = settings_apply.collect_from_widgets(self._sections)
        latest = settings_store.load()
        self._settings = latest
        self._settings.setdefault("options", {}).update(new_options)
        try:
            settings_store.save(self._settings)
            self._status_label.setText(self.tr("✅ 自動保存しました"))
        except Exception as e:  # pragma: no cover - defensive
            logging.getLogger(__name__).warning(
                "settings auto-save failed", exc_info=True
            )
            self._status_label.setText(f"⚠ 保存失敗: {e}")
        self.settings_changed.emit(self._settings)

    # ----------------------------------------------------------
    # ツリー選択
    # ----------------------------------------------------------
    def _on_tree_selection_changed(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            return
        key = items[0].data(0, Qt.UserRole)
        if key and key in self._stack_index_by_key:
            self._stack.setCurrentIndex(self._stack_index_by_key[key])

    # ----------------------------------------------------------
    # 検索（簡易: ノードラベル部分一致でフィルタ）
    # ----------------------------------------------------------
    def _on_search_changed(self, text: str) -> None:
        query = text.strip().lower()
        for item in self._tree_items:
            label = item.text(0).lower()
            visible = (not query) or (query in label)
            item.setHidden(not visible)
            parent = item.parent()
            if parent is not None:
                # 子が1つでも表示なら親も表示
                any_visible = any(
                    not parent.child(i).isHidden()
                    for i in range(parent.childCount())
                )
                parent.setHidden(not any_visible)

    # ----------------------------------------------------------
    # 公開 API
    # ----------------------------------------------------------
    def current_settings(self) -> Dict[str, Dict[str, Any]]:
        """現在の設定 dict のコピーを返す。"""
        return {sec: dict(vals) for sec, vals in self._settings.items()}

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        # 念のため最終保存
        self._on_widget_changed()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# 組み込み Skill (Markdown-Query) を skill_sections レジストリへ登録
# ---------------------------------------------------------------------------
# _MdqIndexSection クラス定義より後に呼ぶ必要があるためモジュール末尾で実行する。
# 重複登録は SkillSectionRegistry.register が上書きするため安全。
skill_sections.register_skill_section(
    key="MDQ",
    label="Markdown-Query",
    section_factory=lambda repo_root, parent: _MdqIndexSection(
        repo_root=repo_root, parent=parent
    ),
)
