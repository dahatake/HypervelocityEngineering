"""hve.gui.page_options — Step 2: オプション選択ページ (16 カテゴリのアコーディオン)。

設計書 §6 対応。

設計上の特徴:
  - `QToolBox` ベースのアコーディオン形式（§6.3 確定）
  - 16 カテゴリ（§6.2）を網羅
  - BooleanOptionalAction は 3 状態 `QComboBox` で表現（§6.5）
  - 選択ワークフローに応じて C10〜C14 を表示制御（§6.4）
  - 必須未入力時は `validate()` が False を返す

ARD 添付ファイル D&D 拡張（§7）は `page_options_ard.py` に分離。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QToolBox,
    QVBoxLayout,
    QWidget,
)

from .orchestrate_args import OrchestrateArgs
from .workflow_display import format_workflow_label
from .workflow_requirements_banner import WorkflowRequirementsBanner
from .workflow_step_requirements import (
    WORKFLOW_TO_SECTION,
    pick_target_step,
    summarize_requirements,
)
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QCheckBox


# --------------------------------------------------------------------------
# モデル選択肢の動的取得 + ModelEntry ルックアップ
#
# `_load_model_choices()` を `_C1Basic.__init__` と `_C1Basic.reload_models()`
# の両方から呼び出すことで、起動時はキャッシュ優先で取得しつつ、
# 「利用できるモデルの取得」成功後は GUI 再起動なしで最新一覧へ更新できる。
#
# 解決順 (GUI 起動時の同期 SDK 呼び出しを避けるためキャッシュ優先):
#   1. `models_cache` に有効/期限切れの何れかキャッシュがあればその ID 一覧
#   2. なければ `hve.config.FALLBACK_MODEL_CHOICES`
# 先頭に "Auto" を付加。
# --------------------------------------------------------------------------


def _load_model_choices() -> List[str]:
    """キャッシュ優先でモデル ID 一覧を取得 (起動時ブロックを避ける)。

    MODEL_AUTO_VALUE ("Auto") を必ず先頭に置き、キャッシュ/フォールバック側に
    含まれる大小無視で "auto" と一致する ID および重複 ID は除外して、
    ドロップダウンに "Auto" と "auto" が同時に出るような重複表示を防ぐ。
    """
    try:
        from hve import models_cache as _cache
        from hve.config import FALLBACK_MODEL_CHOICES, MODEL_AUTO_VALUE
    except ImportError:  # pragma: no cover
        return ["Auto", "claude-opus-4.7", "claude-opus-4.6", "gpt-5.5"]

    cached = _cache.load(allow_stale=True)
    raw = list(cached.models) if (cached and cached.models) else list(FALLBACK_MODEL_CHOICES)

    auto_lower = MODEL_AUTO_VALUE.lower()
    seen: set = set()
    deduped: List[str] = []
    for m in raw:
        if not isinstance(m, str) or not m:
            continue
        key = m.lower()
        if key == auto_lower:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)

    return [MODEL_AUTO_VALUE, *deduped]


def _load_model_entries_map() -> Dict[str, object]:
    """キャッシュから {model_id: ModelEntry} の辞書を構築する。

    v1 キャッシュや entries 欠落時は空 dict。Auto モデルや FALLBACK_MODEL_CHOICES
    に対しては ModelEntry が存在しないため、呼び出し側は欠落を許容すること。
    """
    try:
        from hve import models_cache as _cache
    except ImportError:  # pragma: no cover
        return {}
    cached = _cache.load(allow_stale=True)
    if not cached or not getattr(cached, "entries", None):
        return {}
    return {e.id: e for e in cached.entries}


def _format_context_size_label(max_tokens: Optional[int]) -> str:
    """`max_context_window_tokens` を「200K tokens (200,000)」形式に整形する。

    None または 0 以下なら空文字を返す（ラベル非表示用途）。
    1000 未満は概数表記を省略する。
    """
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        return ""
    n = int(max_tokens)
    if n >= 1000:
        approx = f"{n // 1000}K"
        return f"Context Size: {approx} tokens ({n:,})"
    return f"Context Size: {n:,} tokens"


def _format_cost_label(entry: Optional["object"]) -> str:
    """ModelEntry の token_prices を「In $3.00/1M · Out $15.00/1M · Cache $0.30/1M」形式に整形する。

    すべて None または 0 以下なら空文字。Effort 別の price は SDK が提供しないためモデル単位の表示。
    Premium Request 倍率 (multiplier) は SDK 0.3.0 では取得不可のため省略。
    NOTE: 価格が API 上 0 で返るケースは「データ欠落」と同等に手り None 扱いとする。
    """
    if entry is None:
        return ""
    ip = getattr(entry, "input_price_usd_per_1m", None)
    op = getattr(entry, "output_price_usd_per_1m", None)
    cp = getattr(entry, "cache_price_usd_per_1m", None)
    parts: List[str] = []
    if isinstance(ip, (int, float)) and ip > 0:
        parts.append(f"In ${ip:.2f}/1M")
    if isinstance(op, (int, float)) and op > 0:
        parts.append(f"Out ${op:.2f}/1M")
    if isinstance(cp, (int, float)) and cp > 0:
        parts.append(f"Cache ${cp:.2f}/1M")
    return " · ".join(parts)



# --------------------------------------------------------------------------
# ヘルパー: ラベル付きフィールド（タイトル + 説明 + 入力ウィジェット）
# --------------------------------------------------------------------------


def _is_text_input_widget(widget: QWidget) -> bool:
    """テキスト入力系ウィジェットか判定する。

    対象: ``QLineEdit`` / ``QPlainTextEdit`` / ``QTextEdit`` /
    ``_FilePickerWidget``（QLineEdit + Browse ボタンの組み合わせ）。

    判定ヒット時、``_LabeledField`` はラベル右側で入力欄を左寄り＋
    幅最大化（stretch=1, SizePolicy.Expanding）で配置する。
    """
    # _FilePickerWidget は本ファイル下部で定義されるため文字列比較で判定。
    if widget.__class__.__name__ == "_FilePickerWidget":
        return True
    if isinstance(widget, (QLineEdit, QPlainTextEdit, QTextEdit)):
        return True
    return False


class _LabeledField(QWidget):
    """1 項目を「タイトル(太字) + 詳細説明(小・グレー) + 入力ウィジェット」の縦並びで表示する。

    GitHub Issue Template 風の見やすい表示を実現するための共通ウィジェット。

    Args:
        title: 太字タイトル（パラメーター名ではなく日本語説明）。
        description: 詳細説明文（CLI help テキストより）。
        input_widget: 実際の入力ウィジェット（QComboBox / QCheckBox / QSpinBox 等）。
        required: True のときタイトル右に "*必須" を付与する。
    """

    def __init__(
        self,
        title: str,
        description: str,
        input_widget: QWidget,
        *,
        required: bool = False,
        help_key: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        # 1 行レイアウト: [ラベル(左) + ?ヘルプ] ... stretch ... [入力(右)]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        title_text = title
        if required:
            title_text = f"{title}  *必須"
        title_label = QLabel(title_text)
        title_label.setStyleSheet(
            "font-weight: bold; color: #1f2328; padding: 0; font-size: 10pt;"
        )
        # 長い日本語タイトル（例: "Code Review Agent 完了待ちタイムアウト（秒）"）が
        # 横に押し広がって水平スクロールを誘発するのを防ぐため、折り返しを許可する。
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # 左ブロック: ラベル + ヘルプボタン
        from .help_content import HelpEntry, option_help
        from .help_popup import HelpPopupButton

        layout.addWidget(title_label, 0, Qt.AlignLeft | Qt.AlignVCenter)

        # help_key 指定時は users-guide リンクを含む HelpEntry を、未指定時は
        # 既存 description を popup 内容として用いる HelpEntry を生成。
        popup_entry: Optional[HelpEntry] = None
        if help_key:
            entry = option_help(help_key)
            short = entry.short or description
            popup_entry = HelpEntry(short=short, guide_path=entry.guide_path)
        elif description:
            popup_entry = HelpEntry(short=description)

        if popup_entry is not None and popup_entry.short:
            btn = HelpPopupButton(popup_entry, self)
            layout.addWidget(btn, 0, Qt.AlignLeft | Qt.AlignVCenter)

        # テキスト入力系ウィジェットは後段で stretch=1 を付与して幅最大化させるため、
        # ここでは stretch を挿入しない。非テキスト系は従来通り右寄せにするため、
        # 後段の else 節で addStretch(1) を補う。
        _is_text_input = _is_text_input_widget(input_widget)
        if not _is_text_input:
            layout.addStretch(1)

        # 説明文は行内に表示せず、入力ウィジェットのツールチップに統合
        # （ヘルプポップアップにも description が連携される）。
        if description:
            try:
                input_widget.setToolTip(description)
            except Exception:
                pass

        # 入力ウィジェットの横幅を抑制（右寄せで暴走させない）。
        # 設定画面の幅を縮めても水平スクロールが出ないよう、最小幅を 160 に
        # 緩和する（QComboBox の典型表示には十分）。
        try:
            if input_widget.minimumWidth() < 160:
                input_widget.setMinimumWidth(160)
        except Exception:
            pass

        # テキスト入力系ウィジェットはラベル右側で「左寄り＋幅最大化（動的伸縮）」
        # とする。非テキスト系（QComboBox/QCheckBox/QSpinBox 等）は従来通り
        # 右側固定配置を維持して見栄えの暴走を防ぐ。
        if _is_text_input:
            # ラベルが長過ぎて入力欄を圧迫しないようラベル最大幅を制限。
            try:
                title_label.setMaximumWidth(280)
            except Exception:
                pass
            try:
                from PySide6.QtWidgets import QSizePolicy as _QSP
                input_widget.setSizePolicy(_QSP.Expanding, input_widget.sizePolicy().verticalPolicy())
            except Exception:
                pass
            layout.addWidget(input_widget, 1, Qt.AlignVCenter)
        else:
            layout.addWidget(input_widget, 0, Qt.AlignRight | Qt.AlignVCenter)

        # 各設定行は sizeHint の高さに固定し、親 QVBoxLayout 内で縦に
        # 引き伸ばされないようにする（QScrollArea の余白吸収は親側で行う）。
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._input_widget = input_widget
        self._title_label = title_label

    def input_widget(self) -> QWidget:
        """ラップした入力ウィジェットを返す。"""
        return self._input_widget


# --------------------------------------------------------------------------
# ヘルパー: FilePicker ウィジェット
# --------------------------------------------------------------------------


class _FilePickerWidget(QWidget):
    """QLineEdit + Browse ボタンの組み合わせ。

    Args:
        mode: "file" | "dir"
        title: ダイアログのウィンドウタイトル
        filters: QFileDialog フィルター文字列（"file" モードのみ有効）
        multi: True の場合は複数選択（スペース区切りで結合）
    """

    def __init__(
        self,
        mode: str = "file",
        title: str = "",
        filters: str = "すべてのファイル (*)",
        multi: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._mode = mode
        self._title = title
        self._filters = filters
        self._multi = multi

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = QLineEdit()
        btn = QPushButton("📂")
        btn.setFixedWidth(36)
        btn.setToolTip("ファイルを選択" if mode == "file" else "フォルダを選択")
        btn.clicked.connect(self._browse)

        layout.addWidget(self._edit, 1)
        layout.addWidget(btn, 0)

    def _browse(self) -> None:
        start = self._edit.text().strip() or str(Path.cwd())
        if self._mode == "dir":
            path = QFileDialog.getExistingDirectory(
                self, self._title or "フォルダを選択", start
            )
            if path:
                self._edit.setText(path)
        elif self._multi:
            paths, _ = QFileDialog.getOpenFileNames(
                self, self._title or "ファイルを選択", start, self._filters
            )
            if paths:
                existing = self._edit.text().strip()
                merged = (existing + " " if existing else "") + " ".join(paths)
                self._edit.setText(merged.strip())
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, self._title or "ファイルを選択", start, self._filters
            )
            if path:
                self._edit.setText(path)

    # --- QLineEdit 互換インターフェース ---

    def text(self) -> str:
        return self._edit.text()

    def setText(self, text: str) -> None:
        self._edit.setText(text)

    def setPlaceholderText(self, text: str) -> None:
        self._edit.setPlaceholderText(text)


# --------------------------------------------------------------------------
# ヘルパー: 3 状態 QComboBox
# --------------------------------------------------------------------------


class TriStateCombo(QComboBox):
    """`argparse.BooleanOptionalAction` 用の 3 状態セレクタ。

    UserData:
      "inherit" → None
      "on"      → True
      "off"     → False
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.addItem(self.tr("継承（未指定）"), userData="inherit")
        self.addItem(self.tr("明示 ON"), userData="on")
        self.addItem(self.tr("明示 OFF"), userData="off")

    def get_tristate(self) -> Optional[bool]:
        data = self.currentData()
        if data == "on":
            return True
        if data == "off":
            return False
        return None

    def set_tristate(self, value: Optional[bool]) -> None:
        if value is True:
            self.setCurrentIndex(1)
        elif value is False:
            self.setCurrentIndex(2)
        else:
            self.setCurrentIndex(0)


# --------------------------------------------------------------------------
# 個別カテゴリの内部ウィジェット
# 各クラスは to_args(args: OrchestrateArgs) でフィールドを書き戻す
# --------------------------------------------------------------------------


class _C1Basic(QWidget):
    """C1: 基本設定 — モデル名 + reasoning effort + Context Size 上限表示

    各モデル選択行の直下に「Effort コンボ + Context Size 上限ラベル」を横並びで表示する。
    Effort 選択肢はモデル選択時に SDK キャッシュ (ModelEntry.supported_reasoning_efforts)
    から動的に投入され、`default_reasoning_effort` を初期選択する。Context Size は
    `max_context_window_tokens` を「200K tokens (200,000)」形式で表示する（読み取り専用）。

    継承動作（review_model / qa_model が「（継承）」のとき）:
      - 対応する Effort コンボは disable + 「（モデル設定を継承）」固定表示。
      - Context Size ラベルも空文字（継承時は主モデル側の表示で代替）。
    """

    # --- secondary コンボの「継承」項目に使用するセンチネル値 ---
    _INHERIT_SENTINEL = "__INHERIT__"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        choices = _load_model_choices()
        self._entries_map: Dict[str, object] = _load_model_entries_map()

        # --model: 編集不可ドロップダウン、デフォルト Auto
        self.model = QComboBox()
        self.model.setEditable(False)
        self._populate_main_combo(self.model, choices)
        self.model.setCurrentIndex(0)  # Auto
        self.effort = QComboBox()
        self.effort.setEditable(False)
        self.context_size_label = QLabel("")
        self.cost_label = QLabel("")
        layout.addWidget(_LabeledField(
            title=self.tr("使用するモデル"),
            description=(
                self.tr("使用するモデル名（既定: Auto）。"
                "「Auto」を指定すると GitHub が最適モデルを自動選択します。")
            ),
            input_widget=self._build_model_effort_row(
                self.model, self.effort, self.context_size_label, self.cost_label
            ),
            required=True,
        ))

        # --review-model: 先頭に「継承」項目を追加
        self.review_model = QComboBox()
        self.review_model.setEditable(False)
        self._populate_secondary_combo(self.review_model, choices)
        self.review_model.setCurrentIndex(0)
        self.review_effort = QComboBox()
        self.review_effort.setEditable(False)
        self.review_context_size_label = QLabel("")
        self.review_cost_label = QLabel("")
        layout.addWidget(_LabeledField(
            title=self.tr("レビュー用モデル"),
            description=(
                self.tr("敵対的レビュー（レビュー自動投入）および Code Review Agent"
                "（ローカルでコードレビュー実行）で使用するモデル。"
                "未指定時は上の「使用するモデル」と同じになります。")
            ),
            input_widget=self._build_model_effort_row(
                self.review_model, self.review_effort, self.review_context_size_label, self.review_cost_label
            ),
        ))

        # --qa-model
        self.qa_model = QComboBox()
        self.qa_model.setEditable(False)
        self._populate_secondary_combo(self.qa_model, choices)
        self.qa_model.setCurrentIndex(0)
        self.qa_effort = QComboBox()
        self.qa_effort.setEditable(False)
        self.qa_context_size_label = QLabel("")
        self.qa_cost_label = QLabel("")
        layout.addWidget(_LabeledField(
            title=self.tr("QA 用モデル"),
            description=(
                self.tr("QA 質問票生成（QA 自動投入）で使用するモデル。"
                "未指定時は上の「使用するモデル」と同じになります。")
            ),
            input_widget=self._build_model_effort_row(
                self.qa_model, self.qa_effort, self.qa_context_size_label, self.qa_cost_label
            ),
        ))

        # モデル選択変更時に Effort/Context Size/Cost を再評価
        self.model.currentIndexChanged.connect(
            lambda _idx: self._refresh_effort_row(self.model, self.effort, self.context_size_label, self.cost_label, is_secondary=False)
        )
        self.review_model.currentIndexChanged.connect(
            lambda _idx: self._refresh_effort_row(self.review_model, self.review_effort, self.review_context_size_label, self.review_cost_label, is_secondary=True)
        )
        self.qa_model.currentIndexChanged.connect(
            lambda _idx: self._refresh_effort_row(self.qa_model, self.qa_effort, self.qa_context_size_label, self.qa_cost_label, is_secondary=True)
        )

        # 初期状態を反映（Auto 選択時は disable + 空）
        self._refresh_effort_row(self.model, self.effort, self.context_size_label, self.cost_label, is_secondary=False)
        self._refresh_effort_row(self.review_model, self.review_effort, self.review_context_size_label, self.review_cost_label, is_secondary=True)
        self._refresh_effort_row(self.qa_model, self.qa_effort, self.qa_context_size_label, self.qa_cost_label, is_secondary=True)

        # --- 旧 _C2Parallel から移動: 並列実行上限 ---
        self.max_parallel = QSpinBox()
        self.max_parallel.setRange(1, 200)
        self.max_parallel.setValue(15)
        layout.addWidget(_LabeledField(
            title=self.tr("並列実行上限"),
            description=self.tr("同時に実行する Custom Agent の上限数（既定: 15）。"),
            input_widget=self.max_parallel,
        ))

        # --- 旧 _C8Timeout から移動: タイムアウト系 ---
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(60.0, 999999.0)
        self.timeout.setDecimals(0)
        self.timeout.setValue(21600.0)
        layout.addWidget(_LabeledField(
            title=self.tr("idle タイムアウト（秒）"),
            description=self.tr("アイドル状態からのタイムアウト秒数（既定: 21600 = 6 時間）。"),
            input_widget=self.timeout,
        ))

        self.review_timeout = QDoubleSpinBox()
        self.review_timeout.setRange(60.0, 999999.0)
        self.review_timeout.setDecimals(0)
        self.review_timeout.setValue(7200.0)
        layout.addWidget(_LabeledField(
            title=self.tr("Code Review Agent 完了待ちタイムアウト（秒）"),
            description=self.tr("Code Review Agent レビュー完了待ちタイムアウト秒数（既定: 7200 = 2 時間）。"),
            input_widget=self.review_timeout,
        ))

        # --- 旧 _C6Output から移動: 表示テーマ（全画面に反映） ---
        self.theme = QComboBox()
        self.theme.setEditable(False)
        self.theme.addItem(self.tr("ダーク"), userData="dark")
        self.theme.addItem(self.tr("ライト"), userData="light")
        self.theme.setCurrentIndex(1)
        layout.addWidget(_LabeledField(
            title=self.tr("表示テーマ"),
            description=(
                self.tr("GUI 全画面の配色を選択します（ダーク / ライト、既定: ライト）。"
                "設定変更は即時、すべてのウィンドウに反映されます。")
            ),
            input_widget=self.theme,
        ))

        # --- 旧 _C6Output から移動: コンソール出力レベル ---
        self.verbosity = QComboBox()
        self.verbosity.setEditable(False)
        self.verbosity.addItem(self.tr("（未指定）"), userData=None)
        for v in ("quiet", "compact", "normal", "verbose"):
            self.verbosity.addItem(v, userData=v)
        # デフォルトを「未指定」として CLI 既定値（compact）に委ねる
        self.verbosity.setCurrentIndex(0)
        layout.addWidget(_LabeledField(
            title=self.tr("コンソール出力レベル"),
            description=(
                self.tr("quiet (エラーのみ) / compact (重要イベントのみ、CLI 既定) / "
                "normal (compact + intent/subagent) / verbose (全詳細)。")
            ),
            input_widget=self.verbosity,
        ))

    def _build_model_effort_row(
        self,
        model_combo: QComboBox,
        effort_combo: QComboBox,
        context_label: QLabel,
        cost_label: QLabel,
    ) -> QWidget:
        """モデル + Effort + Context size + Cost を 2 行に分けて構築する。

        旧実装では 1 行に全要素を並べていたが最低幅が 500px を超え、
        設定画面の幅を縮めた際に水平スクロールを誘発していた。
        1 行目 ``[model] [Effort label] [effort]``、2 行目 ``[context] [cost]``
        の 2 行構成に変更する。呼び出し側互換のため引数の各 widget は
        そのまま参照可能（属性として保持される）。
        """
        composite = QWidget(self)
        v = QVBoxLayout(composite)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        try:
            model_combo.setMinimumWidth(180)
        except Exception:
            pass
        try:
            effort_combo.setMinimumWidth(120)
        except Exception:
            pass
        effort_description = self.tr(
            "モデルがサポートする reasoning effort 値（SDK から取得）。"
            "Auto モデルおよび reasoning effort 非対応モデルでは選択できません。"
        )
        try:
            effort_combo.setToolTip(effort_description)
        except Exception:
            pass

        effort_label = QLabel(self.tr("Effort"))
        effort_label.setStyleSheet("color: #1f2328; font-size: 10pt; padding: 0 4px;")
        effort_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        context_label.setStyleSheet("color: #57606a; font-size: 9pt;")
        context_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        cost_label.setStyleSheet("color: #57606a; font-size: 9pt;")
        cost_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        try:
            cost_label.setToolTip(self.tr(
                "GitHub Copilot API の token_prices より計算した USD/1M tokens 単価。"
                "In=入力 / Out=出力 / Cache=キャッシュ。モデル単位で Effort 依存せず。"
            ))
        except Exception:
            pass

        # 1 行目: [model] [Effort label] [effort]
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)
        row1.addWidget(model_combo, 0, Qt.AlignLeft | Qt.AlignVCenter)
        row1.addWidget(effort_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        row1.addWidget(effort_combo, 0, Qt.AlignLeft | Qt.AlignVCenter)
        row1.addStretch(1)

        # 2 行目: [context size] [cost]（細字・補足情報）
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)
        row2.addWidget(context_label, 0, Qt.AlignLeft | Qt.AlignVCenter)
        row2.addWidget(cost_label, 1, Qt.AlignLeft | Qt.AlignVCenter)

        v.addLayout(row1)
        v.addLayout(row2)
        composite.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        return composite

    def _populate_main_combo(self, combo: QComboBox, choices: List[str]) -> None:
        """主モデル用: choices をそのまま追加(先頭は Auto を含む想定)。"""
        for m in choices:
            combo.addItem(m, userData=m)

    def _populate_secondary_combo(self, combo: QComboBox, choices: List[str]) -> None:
        """副モデル用(review/qa): 先頭に「継承」(userData=None)、続いて Auto を除いた残り。"""
        combo.addItem(self.tr("（上の「使用するモデル」を継承）"), userData=None)
        for m in choices[1:]:  # choices[0] == Auto を除外
            combo.addItem(m, userData=m)

    def _refresh_effort_row(
        self,
        model_combo: QComboBox,
        effort_combo: QComboBox,
        context_label: QLabel,
        cost_label: QLabel,
        *,
        is_secondary: bool,
    ) -> None:
        """モデル選択に応じて Effort コンボ／Context Size／Cost ラベルを更新する。

        - 副モデル + 「継承」: Effort コンボは disable + 「（モデル設定を継承）」固定、Context/Cost ラベル空。
        - Auto モデル選択: Effort 無効、Context/Cost ラベル空（Auto は ModelEntry を一意特定できないため）。
        - ModelEntry あり + supports_reasoning_effort=True + supported_reasoning_efforts 非空:
            選択肢を投入し default_reasoning_effort を初期選択。Context ラベルに上限、Cost ラベルに token_prices を表示。
        - 上記以外: Effort 無効 + 空、Context/Cost ラベル空。

        autosave 連鎖を避けるため blockSignals でラップし、最終的にデフォルト値を反映した状態で
        effort_combo.currentIndexChanged を 1 回だけ明示発火させて自動保存をトリガする。
        """
        try:
            from hve.config import MODEL_AUTO_VALUE
        except ImportError:  # pragma: no cover
            MODEL_AUTO_VALUE = "Auto"

        model_value = model_combo.currentData()

        was_blocked = effort_combo.blockSignals(True)
        emit_change = False
        try:
            effort_combo.clear()

            # ケース1: 副モデルで「継承」(None) → 固定表示 + disable
            if is_secondary and model_value is None:
                effort_combo.addItem(self.tr("（モデル設定を継承）"), userData=None)
                effort_combo.setCurrentIndex(0)
                effort_combo.setEnabled(False)
                context_label.setText("")
                cost_label.setText("")
                return

            # ケース2: Auto モデル選択時
            if not model_value or model_value == MODEL_AUTO_VALUE:
                effort_combo.setEnabled(False)
                context_label.setText("")
                cost_label.setText("")
                return

            # ケース3: ModelEntry ルックアップ
            entry = self._entries_map.get(model_value)
            supports = bool(getattr(entry, "supports_reasoning_effort", False)) if entry else False
            sre = getattr(entry, "supported_reasoning_efforts", None) if entry else None

            if entry and supports and sre:
                for v in sre:
                    effort_combo.addItem(str(v), userData=str(v))
                # default_reasoning_effort を初期選択
                default = getattr(entry, "default_reasoning_effort", None)
                if isinstance(default, str):
                    for i in range(effort_combo.count()):
                        if effort_combo.itemData(i) == default:
                            effort_combo.setCurrentIndex(i)
                            break
                effort_combo.setEnabled(True)
                emit_change = True  # autosave をトリガ（モデル変更で effort が変わったため）
            else:
                effort_combo.setEnabled(False)

            # Context Size 上限ラベル
            max_ctx = getattr(entry, "max_context_window_tokens", None) if entry else None
            context_label.setText(_format_context_size_label(max_ctx))

            # Cost ラベル
            cost_label.setText(_format_cost_label(entry))
        finally:
            effort_combo.blockSignals(was_blocked)
            if emit_change:
                # blockSignals 解除後に手動で発火（autosave 接続にデフォルト Effort を保存させる）
                try:
                    effort_combo.currentIndexChanged.emit(effort_combo.currentIndex())
                except Exception:
                    pass

    def reload_models(self) -> None:
        """モデルキャッシュ更新後に呼び出される。3 コンボを再投入し選択値を保持する。

        - 空相当(Auto のみ)受信時は何もしない(既存表示維持)。
        - blockSignals でラップし、wire_autosave 経由の保存連鎖を抑止する。
        - 選択値が新リストに不在の場合は既定 index 0(main=Auto / secondary=継承)へ。
        - 例外は内部で握り潰す。
        """
        try:
            choices = _load_model_choices()
        except Exception:
            return
        if not choices or len(choices) <= 1:
            return

        # ModelEntry マップも更新
        try:
            self._entries_map = _load_model_entries_map()
        except Exception:
            self._entries_map = {}

        for combo, populator in (
            (self.model, self._populate_main_combo),
            (self.review_model, self._populate_secondary_combo),
            (self.qa_model, self._populate_secondary_combo),
        ):
            prev = combo.currentData()
            was_blocked = combo.blockSignals(True)
            try:
                combo.clear()
                populator(combo, choices)
                restored = False
                if prev is not None:
                    for i in range(combo.count()):
                        if combo.itemData(i) == prev:
                            combo.setCurrentIndex(i)
                            restored = True
                            break
                if not restored:
                    combo.setCurrentIndex(0)
            finally:
                combo.blockSignals(was_blocked)

        # 各 Effort 行も再評価
        self._refresh_effort_row(self.model, self.effort, self.context_size_label, self.cost_label, is_secondary=False)
        self._refresh_effort_row(self.review_model, self.review_effort, self.review_context_size_label, self.review_cost_label, is_secondary=True)
        self._refresh_effort_row(self.qa_model, self.qa_effort, self.qa_context_size_label, self.qa_cost_label, is_secondary=True)

    def to_args(self, args: OrchestrateArgs) -> None:
        # --model: Auto はそのまま CLI に渡す（CLI 側で受理される文字列）
        model_val = self.model.currentData()
        args.model = model_val if model_val else None
        args.review_model = self.review_model.currentData()
        args.qa_model = self.qa_model.currentData()
        # reasoning_effort: 無効/未選択時は None
        def _effort_value(combo: QComboBox) -> Optional[str]:
            if not combo.isEnabled():
                return None
            d = combo.currentData()
            return d if isinstance(d, str) and d else None
        args.reasoning_effort = _effort_value(self.effort)
        args.review_reasoning_effort = _effort_value(self.review_effort)
        args.qa_reasoning_effort = _effort_value(self.qa_effort)

        # 旧 _C2Parallel / _C8Timeout から移動した項目
        args.max_parallel = self.max_parallel.value()
        args.timeout = self.timeout.value()
        args.review_timeout = self.review_timeout.value()
        # theme は GUI のみで使用するため OrchestrateArgs には渡さない
        args.verbosity = self.verbosity.currentData()


class _C3AutoPrompt(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.auto_qa = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("QA 自動投入"),
            description=self.tr("QA 質問票を自動的に投入します（既定: 無効）。"),
            input_widget=self.auto_qa,
        ))

        # QA 回答モード（auto_qa=True のときのみ有効）
        # 値: "autopilot" = AI が既定回答を全て自動採用
        #     "user"      = GUI ダイアログで全質問への回答をユーザーが入力
        self.qa_answer_mode = QComboBox()
        self.qa_answer_mode.addItem(self.tr("Autopilot (全自動)"), userData="autopilot")
        self.qa_answer_mode.addItem(self.tr("ユーザー回答"), userData="user")
        self.qa_answer_mode.setCurrentIndex(0)
        layout.addWidget(_LabeledField(
            title=self.tr("QA 回答モード"),
            description=(
                self.tr(
                    "Autopilot: AI が作成した既定回答を全て自動採用してメインタスクへ適用します。\n"
                    "ユーザー回答: AI が作成した質問と既定回答を GUI ダイアログに表示し、"
                    "ユーザーが回答を入力してから Submit するとメインタスクへ適用します。\n"
                    "「QA 自動投入」が無効のときは設定値は無視されます（既定: Autopilot）。"
                )
            ),
            input_widget=self.qa_answer_mode,
        ))

        # auto_qa 連動で qa_answer_mode をグレーアウト
        def _on_auto_qa_toggled(checked: bool) -> None:
            self.qa_answer_mode.setEnabled(bool(checked))
        self.auto_qa.toggled.connect(_on_auto_qa_toggled)
        _on_auto_qa_toggled(self.auto_qa.isChecked())

        self.force_interactive = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("TTY 判定をバイパスして対話モード強制"),
            description=(
                self.tr("QA 回答入力の TTY 判定をバイパスしてインタラクティブモードを強制します。"
                "IDE ターミナル等で stdin が非 TTY 扱いになる場合に使用（既定: 無効）。")
            ),
            input_widget=self.force_interactive,
        ))

        self.auto_contents_review = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("レビュー自動投入"),
            description=self.tr("Review を自動的に投入します（既定: 無効）。"),
            input_widget=self.auto_contents_review,
        ))

        self.auto_coding_agent_review = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("ローカルでコードレビュー実行"),
            description=(
                self.tr("Copilot CLI SDK でローカルにコードレビューを実行します。"
                "git diff を使用して差分を取得し、ローカルセッションでレビュー。"
                "GH_TOKEN / リポジトリ指定は不要（既定: 無効）。")
            ),
            input_widget=self.auto_coding_agent_review,
        ))

        self.auto_coding_agent_review_auto_approval = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("コードレビュー修正プランを自動承認"),
            description=self.tr("Code Review Agent の修正プランを全て自動承認します（既定: 無効）。"),
            input_widget=self.auto_coding_agent_review_auto_approval,
        ))

        # --- 旧 _C16Misc から移動: 自己改善ループ ---
        self.self_improve = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("自己改善ループを有効化"),
            description=(
                self.tr("自己改善ループ（Phase 4）を有効化します。"
                "HVE_AUTO_SELF_IMPROVE=true 環境変数でも有効化できます。")
            ),
            input_widget=self.self_improve,
        ))

        # --- 旧 _C15AdditionalPrompt から移動: 追加プロンプト / コメント ---
        self.additional_prompt = QPlainTextEdit()
        self.additional_prompt.setFixedHeight(80)
        self.additional_prompt.setPlaceholderText(self.tr("全 Custom Agent prompt の末尾に追記"))
        layout.addWidget(_LabeledField(
            title=self.tr("追加プロンプト"),
            description=self.tr("全 Custom Agent prompt の末尾に追記する文字列（省略可）。"),
            input_widget=self.additional_prompt,
        ))

        self.context_max_chars = QSpinBox()
        self.context_max_chars.setRange(0, 10_000_000)
        self.context_max_chars.setValue(0)
        self.context_max_chars.setSpecialValueText("（既定 20000 文字を使用）")
        layout.addWidget(_LabeledField(
            title=self.tr("コンテキスト最大文字数"),
            description=(
                self.tr("各フェーズで注入するコンテキストの最大文字数。"
                "0 のとき SDKConfig 既定値 20,000 を使用。")
            ),
            input_widget=self.context_max_chars,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        args.auto_qa = self.auto_qa.isChecked()
        args.force_interactive = self.force_interactive.isChecked()
        args.auto_contents_review = self.auto_contents_review.isChecked()
        args.auto_coding_agent_review = self.auto_coding_agent_review.isChecked()
        args.auto_coding_agent_review_auto_approval = (
            self.auto_coding_agent_review_auto_approval.isChecked()
        )

        # QA 回答モード: auto_qa が有効なときのみ CLI へ渡す
        if args.auto_qa:
            _ui_mode = self.qa_answer_mode.currentData() or "autopilot"
            if _ui_mode == "user":
                # GUI ユーザー回答モード: CLI 側は "gui-file" として動作
                # IPC ディレクトリは <repo_root>/.hve/qa-ipc/<uuid>/ に生成
                import tempfile
                ipc_root = Path(args.repo_root) / ".hve" / "qa-ipc"
                try:
                    ipc_root.mkdir(parents=True, exist_ok=True)
                    args.qa_ipc_dir = tempfile.mkdtemp(prefix="gui-", dir=str(ipc_root))
                    args.qa_answer_mode = "gui-file"
                except OSError:
                    # IPC dir 作成失敗 → Autopilot にフォールバック
                    args.qa_answer_mode = "autopilot"
                    args.qa_ipc_dir = None
            else:
                args.qa_answer_mode = "autopilot"
                args.qa_ipc_dir = None
        else:
            # auto_qa 無効時は qa_answer_mode を渡さず既存挙動を維持
            args.qa_answer_mode = None
            args.qa_ipc_dir = None

        # 旧 _C16Misc から移動: self_improve
        args.self_improve = self.self_improve.isChecked()
        # 旧 _C15AdditionalPrompt から移動
        args.additional_prompt = self.additional_prompt.toPlainText().strip() or None
        v = self.context_max_chars.value()
        args.context_max_chars = v if v > 0 else None


class _C4WorkIQ(QWidget):
    """C4: Work IQ — CLI 固有オプション 11 個"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        notice = QLabel(
            self.tr("Work IQ 経由の M365 データ参照設定。")
        )
        notice.setStyleSheet("color: #6a737d; padding: 4px;")
        notice.setWordWrap(True)
        layout.addWidget(notice)

        self.workiq = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("Work IQ を有効化"),
            description=(
                self.tr("Work IQ 経由の M365 データ（メール・チャット・会議・ファイル）参照を有効にします。"
                "QA フェーズと、AKM 実行後レビューの後方互換トリガーとしても扱われます"
                "（既定: 無効、@microsoft/workiq インストール必須）。")
            ),
            input_widget=self.workiq,
        ))

        self.workiq_akm_review = TriStateCombo()
        layout.addWidget(_LabeledField(
            title=self.tr("AKM 実行後レビューで Work IQ 検証"),
            description=(
                self.tr("AKM 実行後レビューで Work IQ 検証を有効/無効化します。"
                "未指定時は上の「Work IQ を有効化」または WORKIQ_ENABLED 環境変数を継承。")
            ),
            input_widget=self.workiq_akm_review,
        ))

        self.workiq_akm_ingest = TriStateCombo()
        layout.addWidget(_LabeledField(
            title=self.tr("AKM 入力ソースとして Work IQ"),
            description=(
                self.tr("AKM の入力ソースとして Work IQ を有効/無効化します。"
                "未指定時は取り込みソースに 'workiq' が含まれるかで自動判定。")
            ),
            input_widget=self.workiq_akm_ingest,
        ))

        self.workiq_dxx = QLineEdit()
        self.workiq_dxx.setPlaceholderText(self.tr("例: D01,D04"))
        layout.addWidget(_LabeledField(
            title=self.tr("Work IQ 取り込み対象 Dxx"),
            description=(
                self.tr("AKM Work IQ 取り込み対象 Dxx をカンマ区切りで指定（例: D01,D04）。"
                "省略時は全 D01〜D21 を対象。")
            ),
            input_widget=self.workiq_dxx,
        ))

        self.workiq_draft = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("Work IQ 回答ドラフト作成"),
            description=self.tr("QA フェーズで質問ごとに Work IQ 回答ドラフトを生成します（既定: 無効）。"),
            input_widget=self.workiq_draft,
        ))

        self.workiq_draft_output_dir = _FilePickerWidget(
            mode="dir", title=self.tr("QA ドラフト出力フォルダを選択")
        )
        self.workiq_draft_output_dir.setPlaceholderText(self.tr("例: qa"))
        layout.addWidget(_LabeledField(
            title=self.tr("Work IQ 補助レポート出力先"),
            description=(
                self.tr("Work IQ 補助レポートの出力先ディレクトリ。"
                "未指定時: 設定/環境変数、最終既定値は 'qa'。")
            ),
            input_widget=self.workiq_draft_output_dir,
        ))

        self.workiq_tenant_id = QLineEdit()
        self.workiq_tenant_id.setPlaceholderText(self.tr("例: common, contoso.onmicrosoft.com, <UUID>"))
        layout.addWidget(_LabeledField(
            title=self.tr("Work IQ テナント ID"),
            description=(
                self.tr("Work IQ の Entra テナント ID（省略時: common）。"
                "複数テナント選択可能なアカウントで特定テナントを固定したい場合に使用。")
            ),
            input_widget=self.workiq_tenant_id,
        ))

        self.workiq_prompt_qa = QPlainTextEdit()
        self.workiq_prompt_qa.setFixedHeight(60)
        layout.addWidget(_LabeledField(
            title=self.tr("QA 用プロンプト上書き"),
            description=(
                self.tr("Work IQ の QA 用プロンプトを上書きします（{target_content} プレースホルダ使用可。"
                "省略時はデフォルトプロンプト）。")
            ),
            input_widget=self.workiq_prompt_qa,
        ))

        self.workiq_prompt_km = QPlainTextEdit()
        self.workiq_prompt_km.setFixedHeight(60)
        layout.addWidget(_LabeledField(
            title=self.tr("KM 用プロンプト上書き"),
            description=self.tr("Work IQ の KM 用プロンプトを上書きします（AKM 実行後レビューで使用）。"),
            input_widget=self.workiq_prompt_km,
        ))

        self.workiq_prompt_review = QPlainTextEdit()
        self.workiq_prompt_review.setFixedHeight(60)
        layout.addWidget(_LabeledField(
            title=self.tr("Original Docs レビュー用プロンプト上書き（互換用）"),
            description=self.tr("Work IQ の Original Docs レビュー用プロンプトを上書きします（互換用）。"),
            input_widget=self.workiq_prompt_review,
        ))

        self.workiq_per_question_timeout = QLineEdit()
        _timeout_validator = QDoubleValidator(0.0, 86400.0, 1, self.workiq_per_question_timeout)
        _timeout_validator.setNotation(QDoubleValidator.StandardNotation)
        self.workiq_per_question_timeout.setValidator(_timeout_validator)
        self.workiq_per_question_timeout.setPlaceholderText(
            self.tr("（既定 1200 秒 = 20 分を使用）")
        )
        layout.addWidget(_LabeledField(
            title=self.tr("QA 質問ごとのタイムアウト（秒）"),
            description=(
                self.tr("Work IQ: QA 質問ごとのクエリタイムアウト秒数（数値のみ）。"
                "未入力または 0 のとき環境変数/設定（既定 1200 秒 = 20 分）を使用。")
            ),
            input_widget=self.workiq_per_question_timeout,
        ))

        self.workiq_request_timeout = QLineEdit()
        _req_timeout_validator = QDoubleValidator(0.0, 86400.0, 1, self.workiq_request_timeout)
        _req_timeout_validator.setNotation(QDoubleValidator.StandardNotation)
        self.workiq_request_timeout.setValidator(_req_timeout_validator)
        self.workiq_request_timeout.setPlaceholderText(
            self.tr("（既定 300 秒 = 5 分を使用）")
        )
        layout.addWidget(_LabeledField(
            title=self.tr("Work IQ Request Timeout（秒）"),
            description=(
                self.tr("Work IQ MCP サーバーへのツール呼び出し 1 回あたりのタイムアウト秒数（数値のみ）。"
                "Copilot SDK の MCP クライアントが発行する -32001 (Request timed out) を防ぐための設定。"
                "未入力または 0 のとき環境変数 WORKIQ_REQUEST_TIMEOUT / 設定（既定 300 秒 = 5 分）を使用。")
            ),
            input_widget=self.workiq_request_timeout,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        args.workiq = self.workiq.isChecked()
        args.workiq_akm_review = self.workiq_akm_review.get_tristate()
        args.workiq_akm_ingest = self.workiq_akm_ingest.get_tristate()
        args.workiq_dxx = self.workiq_dxx.text().strip() or None
        args.workiq_draft = self.workiq_draft.isChecked()
        args.workiq_draft_output_dir = self.workiq_draft_output_dir.text().strip() or None
        args.workiq_tenant_id = self.workiq_tenant_id.text().strip() or None
        args.workiq_prompt_qa = self.workiq_prompt_qa.toPlainText().strip() or None
        args.workiq_prompt_km = self.workiq_prompt_km.toPlainText().strip() or None
        args.workiq_prompt_review = self.workiq_prompt_review.toPlainText().strip() or None
        timeout_text = self.workiq_per_question_timeout.text().strip().replace(",", ".")
        try:
            timeout = float(timeout_text) if timeout_text else 0.0
        except ValueError:
            timeout = 0.0
        args.workiq_per_question_timeout = timeout if timeout > 0 else None
        req_timeout_text = self.workiq_request_timeout.text().strip().replace(",", ".")
        try:
            req_timeout = float(req_timeout_text) if req_timeout_text else 0.0
        except ValueError:
            req_timeout = 0.0
        args.workiq_request_timeout = req_timeout if req_timeout > 0 else None


class _C5IssuePR(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.create_issues = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("GitHub Issue を作成"),
            description=(
                self.tr("GitHub Issue を作成します。新規ブランチと PR が自動的に作成されます"
                "（リポジトリ指定と GH_TOKEN が必要、既定: 作成しない）。")
            ),
            input_widget=self.create_issues,
        ))

        self.create_pr = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("GitHub Pull Request を作成"),
            description=(
                self.tr("ローカル実行後に GitHub PR を作成します。"
                "ベースブランチから新ブランチを作成して作業し、完了後に PR をリクエスト。"
                "⚠ PR 作成のみで自動マージは行いません（既定: 作成しない）。")
            ),
            input_widget=self.create_pr,
        ))

        self.ignore_paths = QLineEdit()
        self.ignore_paths.setPlaceholderText(self.tr("例: docs/ legacy/"))
        layout.addWidget(_LabeledField(
            title=self.tr("git add 除外パス"),
            description=(
                self.tr("git add 時に除外するパス（スペース区切りで複数指定可）。"
                "未指定時は config のデフォルト値を使用。")
            ),
            input_widget=self.ignore_paths,
        ))

        self.repo = QLineEdit()
        self.repo.setPlaceholderText("owner/repo")
        layout.addWidget(_LabeledField(
            title=self.tr("リポジトリ (owner/repo)"),
            description=self.tr("リポジトリ（owner/repo 形式）。REPO 環境変数からも取得可能。"),
            input_widget=self.repo,
        ))

        self.issue_title = QLineEdit()
        layout.addWidget(_LabeledField(
            title=self.tr("Issue タイトル（上書き）"),
            description=(
                self.tr("Issue 作成時の Root Issue タイトルを上書きします（省略可）。"
                "未指定時は '[PREFIX] ワークフロー名' を使用。")
            ),
            input_widget=self.issue_title,
        ))

        # --- 旧 _C9BranchSteps から移動 ---
        self.branch = QLineEdit("main")
        layout.addWidget(_LabeledField(
            title=self.tr("ベースブランチ"),
            description=self.tr("ベースブランチ（既定: main）。"),
            input_widget=self.branch,
        ))

        self.steps = QLineEdit()
        self.steps.setPlaceholderText(self.tr("例: 1,2.1,3"))
        layout.addWidget(_LabeledField(
            title=self.tr("実行ステップ"),
            description=self.tr("カンマ区切りで実行ステップを指定（例: 1,2.1,3）。省略時は全ステップ。"),
            input_widget=self.steps,
        ))

        # --- 旧 _C11AKM から移動: PR 自動 Approve & Auto-merge ---
        self.enable_auto_merge = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("PR 自動 Approve & Auto-merge"),
            description=self.tr("AKM: PR の自動 Approve & Auto-merge を有効化します（既定: 無効）。"),
            input_widget=self.enable_auto_merge,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        args.create_issues = self.create_issues.isChecked()
        args.create_pr = self.create_pr.isChecked()
        text = self.ignore_paths.text().strip()
        args.ignore_paths = text.split() if text else []
        args.repo = self.repo.text().strip() or None
        args.issue_title = self.issue_title.text().strip() or None
        # 旧 _C9BranchSteps / _C11AKM から移動
        args.branch = self.branch.text().strip() or "main"
        args.steps = self.steps.text().strip() or None
        args.enable_auto_merge = self.enable_auto_merge.isChecked()


class _C6Output(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.verbose = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("詳細出力"),
            description=(
                self.tr("詳細出力（下の「コンソール出力レベル」が verbose のときと同等。"
                "レベルが指定された場合はそちらが優先）。")
            ),
            input_widget=self.verbose,
        ))

        self.quiet = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("出力抑制"),
            description=(
                self.tr("出力抑制（下の「コンソール出力レベル」が quiet のときと同等。"
                "レベルが指定された場合はそちらが優先）。")
            ),
            input_widget=self.quiet,
        ))

        self.show_stream = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("モデル応答ストリーム表示"),
            description=self.tr("モデル応答のトークンストリーム表示を有効化します（既定: 無効）。"),
            input_widget=self.show_stream,
        ))

        self.log_level = QComboBox()
        self.log_level.setEditable(False)
        for lv in ("none", "error", "warning", "info", "debug", "all"):
            self.log_level.addItem(lv, userData=lv)
        self.log_level.setCurrentText("error")
        layout.addWidget(_LabeledField(
            title=self.tr("Copilot CLI ログレベル"),
            description=self.tr("Copilot CLI のログレベル: none / error / warning / info / debug / all（既定: error）。"),
            input_widget=self.log_level,
        ))

        self.no_color = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("ANSI カラー出力を無効化"),
            description=(
                self.tr("ANSI カラー出力を無効化します（既定: 無効）。"
                "NO_COLOR 環境変数（no-color.org 規格）でも制御可能。")
            ),
            input_widget=self.no_color,
        ))

        self.banner = TriStateCombo()
        layout.addWidget(_LabeledField(
            title=self.tr("起動時バナー表示"),
            description=(
                self.tr("起動時バナー表示を制御します（明示 ON: 表示、明示 OFF: 抑止、未指定: 既存の自動判定）。")
            ),
            input_widget=self.banner,
        ))

        self.screen_reader = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("スクリーンリーダー対応モード"),
            description=self.tr("絵文字を日本語ラベルに置換し、スピナーを無効化します（既定: 無効）。"),
            input_widget=self.screen_reader,
        ))

        self.timestamp_style = QComboBox()
        self.timestamp_style.setEditable(False)
        for ts in ("prefix", "suffix", "off"):
            self.timestamp_style.addItem(ts, userData=ts)
        self.timestamp_style.setCurrentText("prefix")
        layout.addWidget(_LabeledField(
            title=self.tr("タイムスタンプ表示位置"),
            description=self.tr("prefix=行頭（既定）/ suffix=行末（DIM）/ off=非表示。"),
            input_widget=self.timestamp_style,
        ))

        self.final_only = QCheckBox(self.tr("有効化"))
        layout.addWidget(_LabeledField(
            title=self.tr("DAG 完了サマリのみ出力"),
            description=(
                self.tr("DAG 完了時のサマリと各ステップの最終応答のみを出力します"
                "（CI/スクリプト連携用、既定: 無効）。")
            ),
            input_widget=self.final_only,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        args.verbose = self.verbose.isChecked()
        args.quiet = self.quiet.isChecked()
        args.show_stream = self.show_stream.isChecked()
        args.log_level = self.log_level.currentData() or "error"
        args.no_color = self.no_color.isChecked()
        args.banner = self.banner.get_tristate()
        args.screen_reader = self.screen_reader.isChecked()
        args.timestamp_style = self.timestamp_style.currentData() or "prefix"
        args.final_only = self.final_only.isChecked()


class _C7Connection(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.cli_path = _FilePickerWidget(
            mode="file",
            title=self.tr("Copilot CLI 実行ファイルを選択"),
        )
        self.cli_path.setPlaceholderText(self.tr("Copilot CLI 実行ファイルパス"))
        layout.addWidget(_LabeledField(
            title=self.tr("Copilot CLI 実行ファイルパス"),
            description=self.tr("Copilot CLI 実行ファイルパス（省略時: PATH から自動検出）。"),
            input_widget=self.cli_path,
        ))

        self.cli_url = QLineEdit()
        self.cli_url.setPlaceholderText(self.tr("例: localhost:4321"))
        layout.addWidget(_LabeledField(
            title=self.tr("外部 CLI サーバー URL"),
            description=self.tr("外部 CLI サーバー URL（例: localhost:4321）。"),
            input_widget=self.cli_url,
        ))

        # ----------------------------------------------------------
        # T5 (Wave 1 / C2): MCP Server 利用 ON/OFF 設定
        # ----------------------------------------------------------
        self._mcp_section_label = QLabel(
            self.tr("MCP Server 利用設定（ON のサーバは Step 2 実行前に認証必須）")
        )
        self._mcp_section_label.setStyleSheet("color: #6a737d; padding: 6px 0 2px 0;")
        layout.addWidget(self._mcp_section_label)

        self._mcp_container = QWidget(self)
        self._mcp_container_layout = QVBoxLayout(self._mcp_container)
        self._mcp_container_layout.setContentsMargins(0, 0, 0, 0)
        self._mcp_container_layout.setSpacing(2)
        layout.addWidget(self._mcp_container)

        # サーバ名 -> QCheckBox
        self._mcp_checkboxes: Dict[str, QCheckBox] = {}
        self._mcp_empty_label: Optional[QLabel] = None
        self._populate_mcp_servers()

    # ----------------------------------------------------------
    def _populate_mcp_servers(self) -> None:
        """`copilot mcp list` から MCP サーバ名を取得し、トグル UI を構築する。

        既存設定 (settings_store の ``mcp_enabled`` セクション) を初期チェック状態として反映。
        """
        try:
            from .copilot_cli_bridge import CopilotCliBridge
            servers = CopilotCliBridge.list_mcp_servers()
            server_names = sorted(servers.keys()) if isinstance(servers, dict) else []
        except Exception:
            server_names = []

        # 既存設定読込
        try:
            from . import settings_store
            mcp_enabled = settings_store.load_mcp_enabled()
        except Exception:
            mcp_enabled = {}

        # 既存ウィジェットをクリア
        while self._mcp_container_layout.count():
            item = self._mcp_container_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._mcp_checkboxes.clear()
        self._mcp_empty_label = None

        if not server_names:
            self._mcp_empty_label = QLabel(
                self.tr("MCP Server が登録されていません（`copilot mcp add` 後に再起動してください）。")
            )
            self._mcp_empty_label.setStyleSheet("color: #888; padding: 2px;")
            self._mcp_container_layout.addWidget(self._mcp_empty_label)
            return

        for name in server_names:
            cb = QCheckBox(name)
            cb.setChecked(bool(mcp_enabled.get(name, False)))
            cb.toggled.connect(self._on_mcp_toggle)
            self._mcp_container_layout.addWidget(cb)
            self._mcp_checkboxes[name] = cb

    # ----------------------------------------------------------
    def _on_mcp_toggle(self, _checked: bool) -> None:
        """各 MCP トグルの状態変化を即座に settings_store に永続化する。"""
        try:
            from . import settings_store
            current = {name: cb.isChecked() for name, cb in self._mcp_checkboxes.items()}
            settings_store.save_mcp_enabled(current)
        except Exception:
            pass

    # ----------------------------------------------------------
    def refresh_mcp_servers(self) -> None:
        """外部から MCP サーバ一覧を再列挙したい場合のフック (現状未使用)。"""
        self._populate_mcp_servers()

    def mcp_enabled_dict(self) -> Dict[str, bool]:
        """現在のチェック状態を ``{server_name: bool}`` で返す。"""
        return {name: cb.isChecked() for name, cb in self._mcp_checkboxes.items()}

    def to_args(self, args: OrchestrateArgs) -> None:
        args.cli_path = self.cli_path.text().strip() or None
        args.cli_url = self.cli_url.text().strip() or None


class _CAzure(QWidget):
    """連携 / Azure：Azure 連携設定。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.resource_group = QLineEdit()
        layout.addWidget(_LabeledField(
            title=self.tr("Azure リソースグループ名"),
            description=self.tr("Azure リソースグループ名。"),
            input_widget=self.resource_group,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        args.resource_group = self.resource_group.text().strip() or None


class _C10AppId(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.app_ids = QLineEdit()
        self.app_ids.setPlaceholderText(self.tr("例: AAD-WEB-001,AAD-WEB-002"))
        layout.addWidget(_LabeledField(
            title=self.tr("対象アプリケーション (APP-ID)"),
            description=(
                self.tr("対象アプリケーション (APP-ID) — カンマ区切りで複数指定可。"
                "AAD-WEB/ASDW-WEB は Web フロントエンド + クラウド、ADFD/ADFDV はデータデータフロー処理の APP-ID のみ採用します。"
                "未指定時は docs/catalog/app-arch-catalog.md から自動選択します。")
            ),
            input_widget=self.app_ids,
        ))

        self.app_id = QLineEdit()
        self.app_id.setPlaceholderText(self.tr("ADFDV 等で使用、カンマ区切り可"))
        layout.addWidget(_LabeledField(
            title=self.tr("データフローアプリ ID"),
            description=(
                self.tr("データフローアプリ ID（ADFDV 等で使用、カンマ区切り可）。"
                "APP-ID フィルタ後、対象 Batch APP の文脈で実行します。")
            ),
            input_widget=self.app_id,
        ))

        self.usecase_id = QLineEdit()
        layout.addWidget(_LabeledField(
            title=self.tr("ユースケース ID"),
            description=self.tr("ユースケース ID（ASDW 等で使用）。"),
            input_widget=self.usecase_id,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        args.app_ids = self.app_ids.text().strip() or None
        args.app_id = self.app_id.text().strip() or None
        args.usecase_id = self.usecase_id.text().strip() or None


class _C11AKM(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --sources: QCheckBox 群（複数選択可、CSV 結合）
        sources_widget = QWidget()
        sources_layout = QVBoxLayout(sources_widget)
        sources_layout.setContentsMargins(0, 0, 0, 0)
        sources_layout.setSpacing(2)
        self.sources_qa = QCheckBox(self.tr("qa（質問票回答）"))
        self.sources_original_docs = QCheckBox(self.tr("original-docs（オリジナルドキュメント）"))
        self.sources_workiq = QCheckBox(self.tr("workiq（Work IQ 経由の M365 データ）"))
        # 既定: qa + original-docs
        self.sources_qa.setChecked(True)
        self.sources_original_docs.setChecked(True)
        sources_layout.addWidget(self.sources_qa)
        sources_layout.addWidget(self.sources_original_docs)
        sources_layout.addWidget(self.sources_workiq)
        layout.addWidget(_LabeledField(
            title=self.tr("取り込みソース"),
            description=(
                self.tr("AKM の取り込みソース（複数選択可）。"
                "qa / original-docs / workiq から 1 つ以上を選択（既定: qa + original-docs）。")
            ),
            input_widget=sources_widget,
        ))

        self.target_files = _FilePickerWidget(
            mode="file",
            multi=True,
            title=self.tr("対象ファイルを選択"),
        )
        self.target_files.setPlaceholderText(self.tr("複数選択可（スペース区切りで追加）"))
        layout.addWidget(_LabeledField(
            title=self.tr("対象ファイル"),
            description=self.tr("対象ファイルパス（省略時: 上で選択した取り込みソース配下の全件）。"),
            input_widget=self.target_files,
        ))

        self.force_refresh = TriStateCombo()
        layout.addWidget(_LabeledField(
            title=self.tr("既存Knowledgeファイルの再生成"),
            description=(
                self.tr("既存 knowledge/ 出力を完全に再生成します"
                "（明示 ON で有効化、既定: 無効）。")
            ),
            input_widget=self.force_refresh,
        ))

        self.custom_source_dir = _FilePickerWidget(
            mode="dir",
            title=self.tr("追加ファイルのフォルダを選択"),
        )
        self.custom_source_dir.setPlaceholderText(self.tr("複数指定はスペース区切り"))
        layout.addWidget(_LabeledField(
            title=self.tr("追加ファイル"),
            description=self.tr("追加で取り込むファイル/フォルダ（複数指定可、スペース区切り）。"),
            input_widget=self.custom_source_dir,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        # --sources: チェックされた項目を CSV で結合（空なら None）
        selected_sources = []
        if self.sources_qa.isChecked():
            selected_sources.append("qa")
        if self.sources_original_docs.isChecked():
            selected_sources.append("original-docs")
        if self.sources_workiq.isChecked():
            selected_sources.append("workiq")
        args.sources = ",".join(selected_sources) if selected_sources else None

        text = self.target_files.text().strip()
        args.target_files = text.split() if text else []
        args.force_refresh = self.force_refresh.get_tristate()
        text = self.custom_source_dir.text().strip()
        args.custom_source_dir = text.split() if text else []


class _C12AQOD(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # target-scope: フォルダピッカー化
        self.target_scope = _FilePickerWidget(
            mode="dir",
            title=self.tr("チェック対象ファイルのフォルダを選択"),
        )
        self.target_scope.setPlaceholderText(self.tr("（空欄=original-docs/）"))
        layout.addWidget(_LabeledField(
            title=self.tr("チェック対象ファイルのフォルダパス"),
            description=self.tr("チェック対象ファイルのフォルダパス（省略時: original-docs/）。"),
            input_widget=self.target_scope,
        ))

        self.depth = QComboBox()
        self.depth.setEditable(False)
        self.depth.addItem(self.tr("（未指定）"), userData=None)
        self.depth.addItem(self.tr("標準（standard）"), userData="standard")
        self.depth.addItem(self.tr("軽量（lightweight）"), userData="lightweight")
        # デフォルトは standard（インデックス 1）
        self.depth.setCurrentIndex(1)
        layout.addWidget(_LabeledField(
            title=self.tr("分析の深さ"),
            description=self.tr("standard（標準）または lightweight（軽量）から選択（既定: standard）。"),
            input_widget=self.depth,
        ))

        self.focus_areas = QLineEdit()
        layout.addWidget(_LabeledField(
            title=self.tr("分析の観点"),
            description=self.tr("分析の重点観点を自由記述（任意）。"),
            input_widget=self.focus_areas,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        args.target_scope = self.target_scope.text().strip() or None
        args.depth = self.depth.currentData()
        args.focus_areas = self.focus_areas.text().strip() or None


class _C13ADOC(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.target_dirs = _FilePickerWidget(
            mode="dir",
            title=self.tr("ドキュメント対象フォルダを選択"),
        )
        self.target_dirs.setPlaceholderText(self.tr("カンマ区切り（空欄=全体）"))
        layout.addWidget(_LabeledField(
            title=self.tr("ドキュメント生成対象ディレクトリ"),
            description=self.tr("カンマ区切り（省略時: 全体）。"),
            input_widget=self.target_dirs,
        ))

        self.exclude_patterns = QLineEdit()
        self.exclude_patterns.setPlaceholderText(
            self.tr("例: node_modules/,vendor/,dist/,*.lock,__pycache__/")
        )
        layout.addWidget(_LabeledField(
            title=self.tr("除外パターン"),
            description=(
                self.tr("カンマ区切り（既定: node_modules/, vendor/, dist/, *.lock, __pycache__/）。")
            ),
            input_widget=self.exclude_patterns,
        ))

        self.doc_purpose = QComboBox()
        self.doc_purpose.setEditable(False)
        self.doc_purpose.addItem(self.tr("（未指定）"), userData=None)
        for p in ("all", "onboarding", "refactoring", "migration"):
            self.doc_purpose.addItem(p, userData=p)
        # デフォルトは all（インデックス 1）
        self.doc_purpose.setCurrentIndex(1)
        layout.addWidget(_LabeledField(
            title=self.tr("ドキュメントの主目的"),
            description=(
                self.tr("all（全目的）/ onboarding（新規参画支援）/ refactoring（リファクタ）/ "
                "migration（移行）から選択（既定: all）。")
            ),
            input_widget=self.doc_purpose,
        ))

        self.max_file_lines = QSpinBox()
        self.max_file_lines.setRange(0, 100000)
        self.max_file_lines.setValue(0)
        self.max_file_lines.setSpecialValueText("（既定 500 行を使用）")
        layout.addWidget(_LabeledField(
            title=self.tr("大規模ファイル分割閾値（行数）"),
            description=self.tr("行数で指定。0 のとき既定 500 行を使用。"),
            input_widget=self.max_file_lines,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        args.target_dirs = self.target_dirs.text().strip() or None
        args.exclude_patterns = self.exclude_patterns.text().strip() or None
        args.doc_purpose = self.doc_purpose.currentData()
        v = self.max_file_lines.value()
        args.max_file_lines = v if v > 0 else None


class _C14ARD(QWidget):
    """C14: ARD 固有オプション。

    `--attached-docs` の D&D 拡張は `page_options_ard.py` の AttachmentPane
    が別パネルとして処理する。本クラスは `--attached-docs` を直接編集する
    フィールドのみ提供する。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        # _setup_ui からの後付け追加（添付ペイン）に対応するため layout 参照を公開
        self._layout = layout

        self.company_name = QLineEdit()
        layout.addWidget(_LabeledField(
            title=self.tr("対象企業名"),
            description=self.tr("Step 1 (Untargeted) を実行する場合は必須。"),
            input_widget=self.company_name,
        ))

        self.target_business = _FilePickerWidget(
            mode="file",
            title=self.tr("事業分析基準ファイルを選択"),
            filters=self.tr("Markdown (*.md *.txt);;すべてのファイル (*)"),
        )
        layout.addWidget(_LabeledField(
            title=self.tr("業務エリア"),
            description=(
                self.tr("対象業務名（または基準ファイル）。省略時は Step 1 → 2 → 3、指定時は Step 2 直行。"
                "文章のほか、フォルダパスまたは複数ファイルパス（カンマ区切り）も指定可能。")
            ),
            input_widget=self.target_business,
        ))

        self.survey_base_date = QLineEdit()
        self.survey_base_date.setPlaceholderText(self.tr("YYYY-MM-DD（空欄=実行日）"))
        layout.addWidget(_LabeledField(
            title=self.tr("調査基準日 (YYYY-MM-DD)"),
            description=self.tr("省略時は実行日。"),
            input_widget=self.survey_base_date,
        ))

        self.survey_period_years = QSpinBox()
        self.survey_period_years.setRange(0, 200)
        self.survey_period_years.setValue(0)
        self.survey_period_years.setSpecialValueText("（既定 30 年を使用）")
        layout.addWidget(_LabeledField(
            title=self.tr("調査期間年数"),
            description=self.tr("0 のとき既定 30 年を使用。"),
            input_widget=self.survey_period_years,
        ))

        self.target_region = QLineEdit()
        self.target_region.setPlaceholderText(self.tr("例: 日本 / 北米"))
        layout.addWidget(_LabeledField(
            title=self.tr("対象地域"),
            description=self.tr("省略時は『グローバル全体』。"),
            input_widget=self.target_region,
        ))

        self.analysis_purpose = QLineEdit()
        self.analysis_purpose.setPlaceholderText(self.tr("例: 中長期成長戦略の立案"))
        layout.addWidget(_LabeledField(
            title=self.tr("分析目的"),
            description=self.tr("省略時は『中長期成長戦略の立案』。"),
            input_widget=self.analysis_purpose,
        ))

        self.target_recommendation_id = QLineEdit()
        self.target_recommendation_id.setPlaceholderText(self.tr("例: SR-1"))
        layout.addWidget(_LabeledField(
            title=self.tr("採用 Strategic Recommendation ID"),
            description=(
                self.tr("Step 1 完了後に採用する Strategic Recommendation の ID（例: SR-1）。"
                "指定時は対話モードでもこの ID を優先して採用。"
                "省略時は非対話モードでは最初の SR、対話モードではメニュー選択（既定: 先頭）を使用。")
            ),
            input_widget=self.target_recommendation_id,
        ))

        self.attached_docs = QLineEdit()
        self.attached_docs.setPlaceholderText(self.tr("カンマ区切り（添付 D&D 領域から自動入力）"))
        layout.addWidget(_LabeledField(
            title=self.tr("添付資料パス"),
            description=self.tr("カンマ区切り。下の添付 D&D 領域からの選択で上書きされます。"),
            input_widget=self.attached_docs,
        ))

    def to_args(self, args: OrchestrateArgs) -> None:
        args.company_name = self.company_name.text().strip() or None
        args.target_business = self.target_business.text().strip() or None
        args.survey_base_date = self.survey_base_date.text().strip() or None
        v = self.survey_period_years.value()
        args.survey_period_years = v if v > 0 else None
        args.target_region = self.target_region.text().strip() or None
        args.analysis_purpose = self.analysis_purpose.text().strip() or None
        args.target_recommendation_id = (
            self.target_recommendation_id.text().strip() or None
        )
        args.attached_docs = self.attached_docs.text().strip() or None


# --------------------------------------------------------------------------
# メインクラス: OptionsPage
# --------------------------------------------------------------------------


# Step 2 で表示するフィールドのワークフロー別マップ。
# 各エントリは (category_attr, _LabeledField タイトル) のペア。
# - `category_attr`: OptionsPage の属性名 (例: "c10", "c14")
# - タイトル: `_LabeledField(title=...)` 引数の文字列と完全一致
# 複数ワークフロー選択時は和集合で表示し、重複は自動的に統合される。
# `aas` は空。`追加プロンプト` (C15) は全ワークフロー共通で最下段に表示。
_STEP2_FIELDS_BY_WORKFLOW: Dict[str, List[Tuple[str, str]]] = {
    "ard": [
        ("c14", "業務エリア"),
        ("c4", "Work IQ 回答ドラフト作成"),
    ],
    "aas": [],
    "aad-web": [
        ("c10", "対象アプリケーション (APP-ID)"),
    ],
    "asdw-web": [
        ("c10", "Azure リソースグループ名"),
    ],
    "adfd": [
        ("c10", "データフローアプリ ID"),
    ],
    "adfdv": [
        ("c10", "Azure リソースグループ名"),
    ],
    "akm": [
        ("c4", "Work IQ 回答ドラフト作成"),
        ("c4", "QA 用プロンプト上書き"),
        ("c4", "KM 用プロンプト上書き"),
        ("c11", "取り込みソース"),
        ("c11", "対象ファイル"),
        ("c11", "既存Knowledgeファイルの再生成"),
        ("c11", "追加ファイル"),
    ],
    "aqod": [
        ("c12", "チェック対象ファイルのフォルダパス"),
        ("c12", "分析の深さ"),
        ("c12", "分析の観点"),
    ],
    "adoc": [
        ("c13", "ドキュメント生成対象ディレクトリ"),
        ("c13", "除外パターン"),
        ("c13", "ドキュメントの主目的"),
    ],
    "aag": [],
    "aagd": [],
}

# 全ワークフロー共通で常に表示するフィールド（最下段）。
# 追加プロンプトは Step 1 右ペイン（OptionsPage）の最上部に常時表示するため、
# `_refresh_specific_categories` / `_pin_additional_prompt_top` で個別制御する。
_STEP2_COMMON_FIELDS: List[Tuple[str, str]] = []

# Step 2 から完全に外すカテゴリ（設定画面のみで編集）。
# C3（自動プロンプト）はカテゴリ全体としては非表示扱いだが、
# 内包する「追加プロンプト」`_LabeledField` のみ最上部に常時表示する例外処理を
# `_refresh_specific_categories` で行う。
_STEP2_HIDDEN_CATEGORIES = {"C1", "C3", "C5", "C6", "C7", "AZURE"}

# C3 カテゴリ内で「追加プロンプト」以外のフィールド（タイトル文字列）。
# Step 1 右ペインでは C3 内の他フィールドを表示しないため明示的に hide する。
# 文字列は `_C3AutoPrompt.__init__` で `_LabeledField(title=...)` に渡している値と完全一致。
_C3_NON_ADDITIONAL_PROMPT_TITLES: Tuple[str, ...] = (
    "QA 自動投入",
    "QA 回答モード",
    "TTY 判定をバイパスして対話モード強制",
    "レビュー自動投入",
    "ローカルでコードレビュー実行",
    "コードレビュー修正プランを自動承認",
    "自己改善ループを有効化",
    "コンテキスト最大文字数",
)

# Step 2 表示カテゴリの正準順 (Workflow Step 順, ARD 先頭)。
# `_reorder_visible_categories` が選択 Workflow の集合から表示順を決定する際に参照。
# - 各 Workflow の主カテゴリを正準順で並べる。
# - Step 2 で固有カテゴリを持たない Workflow (aas / aag / aagd) は
#   `_WORKFLOW_TO_PRIMARY_CATEGORY` に意図的に未登録。
# - 共有カテゴリ C4 (Work IQ) は `_C4_OWNER_WORKFLOWS` (= `_STEP2_FIELDS_BY_WORKFLOW`
#   から動的に導出される) のいずれかが選択された場合に
#   「最初に出現した所有 Workflow の主カテゴリ直後」へ 1 回だけ挿入する。
_WORKFLOW_CANONICAL_ORDER: List[str] = [
    "ard", "aas", "aad-web", "asdw-web", "adfd", "adfdv",
    "aag", "aagd", "akm", "aqod", "adoc",
]
_WORKFLOW_TO_PRIMARY_CATEGORY: Dict[str, str] = {
    "ard": "C14",
    "aad-web": "C10",
    "asdw-web": "C10",
    "adfd": "C10",
    "adfdv": "C10",
    "akm": "C11",
    "aqod": "C12",
    "adoc": "C13",
}
# C4 を所有する Workflow を `_STEP2_FIELDS_BY_WORKFLOW` から動的に導出する。
# (`_STEP2_FIELDS_BY_WORKFLOW` との二重管理を避け、同期漏れを防止)。
_C4_OWNER_WORKFLOWS: set = {
    wf_id
    for wf_id, fields in _STEP2_FIELDS_BY_WORKFLOW.items()
    if any(attr == "c4" for attr, _ in fields)
}


class OptionsPage(QWidget):
    """Step 2: オプション選択ページ。

    Signals:
        validity_changed(bool): 入力が「実行」可能になったかどうか
    """

    validity_changed = Signal(bool)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        repo_root: Optional[Path] = None,
    ) -> None:
        super().__init__(parent)
        self._repo_root: Path = Path(repo_root) if repo_root is not None else Path.cwd()
        self._workflow_id: Optional[str] = None
        self._workflow_name: Optional[str] = None
        self._workflow_ids: List[str] = []
        self._workflow_name_map: Dict[str, str] = {}

        # 各カテゴリのインスタンス（参照保持）
        self.c1 = _C1Basic()
        self.c3 = _C3AutoPrompt()
        self.c4 = _C4WorkIQ()
        self.c5 = _C5IssuePR()
        self.c6 = _C6Output()
        self.c7 = _C7Connection()
        self.c_azure = _CAzure()
        self.c10 = _C10AppId()
        self.c11 = _C11AKM()
        self.c12 = _C12AQOD()
        self.c13 = _C13ADOC()
        self.c14 = _C14ARD()

        # ARD 添付ペイン（ARD 選択時のみ表示）— 遅延 import で循環依存回避
        self._attachment_pane: Optional[QWidget] = None
        # Step 2 改定で追加されたコンポーネント
        self._app_id_checklist: Optional[QWidget] = None
        self._aas_notice: Optional[QWidget] = None
        self._groups_layout: Optional[QVBoxLayout] = None

        # 必須要件サマリーバナー（Task C 統合）
        # 単一インスタンスを保持し、選択ワークフローに応じて配置先を動的切替する。
        self._requirements_banner: WorkflowRequirementsBanner = WorkflowRequirementsBanner()
        self._banner_current_section: Optional[str] = None
        self._last_banner_selection: List[Tuple[str, List[str]]] = []

        self._setup_ui()
        self._refresh_specific_categories()
        # auto_qa の変更で C4 (Work IQ) の表示が変わるため購読
        self.c3.auto_qa.stateChanged.connect(
            lambda _s: self._refresh_specific_categories()
        )

        # 監視対象フィールドの textChanged をバナー更新にフック（接続漏れ防止のため
        # 一覧をテーブル化してまとめて接続する）
        self._wire_requirements_banner_listeners()

    # ----------------------------------------------------------
    # 公開 API
    # ----------------------------------------------------------

    def set_workflow(self, workflow_id: str, workflow_name: str = "") -> None:
        """選択ワークフローを設定し、固有カテゴリの表示を更新する。"""
        self.set_workflows([workflow_id], {workflow_id: workflow_name})

    def set_workflows(
        self,
        workflow_ids: List[str],
        workflow_name_map: Optional[Dict[str, str]] = None,
    ) -> None:
        """選択ワークフロー群を設定し、固有カテゴリの表示を更新する。"""
        self._workflow_ids = list(workflow_ids)
        self._workflow_id = self._workflow_ids[0] if self._workflow_ids else None
        self._workflow_name_map = dict(workflow_name_map or {})
        self._workflow_name = self._workflow_name_map.get(self._workflow_id or "", "")

        # 旧: `_title_label` 更新は廃止（画面内タイトルを削除）。

        self._refresh_specific_categories()
        self._update_attachment_pane_visibility()

    def build_args(self, repo_root: Optional["Path"] = None) -> OrchestrateArgs:  # type: ignore[name-defined] # noqa: F821
        """全カテゴリの入力値を `OrchestrateArgs` にまとめて返す。"""
        workflow_id = self._workflow_id or (self._workflow_ids[0] if self._workflow_ids else "")
        return self.build_args_for_workflow(workflow_id, repo_root=repo_root)

    def build_args_for_workflow(
        self,
        workflow_id: str,
        repo_root: Optional["Path"] = None,  # type: ignore[name-defined] # noqa: F821
    ) -> OrchestrateArgs:
        """指定 workflow_id 向けに全カテゴリ入力を `OrchestrateArgs` へ反映する。"""
        from pathlib import Path

        args = OrchestrateArgs(
            workflow=workflow_id or "",
            repo_root=repo_root or Path.cwd(),
        )
        for cat in (
            self.c1,
            self.c3,
            self.c4,
            self.c5,
            self.c6,
            self.c7,
            self.c_azure,
            self.c10,
            self.c11,
            self.c12,
            self.c13,
            self.c14,
        ):
            cat.to_args(args)

        # SSOT ブリッジ: mdq_watch / mdq_watch_debounce_ms は MDQ セクション
        # (skills/Markdown-Query) で編集されるため、settings_store から直接拾う。
        try:
            from . import settings_store
            _opts = settings_store.load().get("options", {})
            if "mdq_watch" in _opts:
                args.mdq_watch = _opts["mdq_watch"]
            if "mdq_watch_debounce_ms" in _opts:
                _v = _opts["mdq_watch_debounce_ms"]
                args.mdq_watch_debounce_ms = _v if isinstance(_v, int) and _v > 0 else None
        except Exception:
            pass

        # ARD: 添付ペインで生成された `--attached-docs` が C14 を上書きする
        if self._attachment_pane is not None and workflow_id == "ard":
            attach_str = getattr(self._attachment_pane, "attached_docs_string", None)
            if callable(attach_str):
                v = attach_str()
                if v:
                    args.attached_docs = v
            target_business = getattr(self._attachment_pane, "target_business_path", None)
            if callable(target_business):
                tb = target_business()
                if tb and not args.target_business:
                    args.target_business = tb

        # Step 2 セッション限定: `ard` / `akm` で「QA 回答ドラフト生成」 ON のとき
        # `workiq=true` をセッション内のみ強制有効化する（設定保存はしない）。
        if workflow_id in ("ard", "akm") and self.c4.workiq_draft.isChecked():
            args.workiq = True

        return args

    def build_args_list(self, repo_root: Optional["Path"] = None) -> List[OrchestrateArgs]:  # type: ignore[name-defined] # noqa: F821
        """選択 workflow 群の順序に従って `OrchestrateArgs` 配列を返す。"""
        workflow_ids = self._workflow_ids or ([self._workflow_id] if self._workflow_id else [])
        return [
            self.build_args_for_workflow(wf_id, repo_root=repo_root)
            for wf_id in workflow_ids
            if wf_id
        ]

    def validate(self) -> tuple[bool, str]:
        """入力検証。OK なら (True, "")、NG なら (False, エラー文)。"""
        if not self._workflow_ids and not self._workflow_id:
            return False, "ワークフローが選択されていません。"
        # ARD: company-name または target-business のいずれかは推奨だが、強制はしない
        # （CLI 仕様上は未指定でも動作可能なため）
        # 実行は許可するが警告ステータスを表示できる構造を維持
        return True, ""

    def attachment_pane(self) -> Optional[QWidget]:
        """ARD 添付ペインの参照を返す（test 用）。"""
        return self._attachment_pane

    # ----------------------------------------------------------
    # 必須要件サマリーバナー（Task C 統合）
    # ----------------------------------------------------------

    # 監視対象フィールド対応表（プラン Task C のキー → ウィジェット属性）
    # キーは workflow_step_requirements.INPUT_FIELD_KEYS と一致させる。
    def _banner_input_widgets(self) -> Dict[str, QWidget]:
        return {
            "company_name": self.c14.company_name,
            "target_business": self.c14.target_business,
            "resource_group": self.c_azure.resource_group,
            "target_dirs": self.c13.target_dirs,
        }

    def _wire_requirements_banner_listeners(self) -> None:
        """監視対象フィールドの textChanged にバナー更新を接続する。

        `_FilePickerWidget` は内部 QLineEdit `_edit` を持つため両対応する。
        """
        for w in self._banner_input_widgets().values():
            inner = getattr(w, "_edit", None)
            sig_owner = inner if inner is not None else w
            sig = getattr(sig_owner, "textChanged", None)
            if sig is not None:
                sig.connect(self._on_banner_input_changed)

    def _on_banner_input_changed(self, *_args) -> None:
        # 現在の選択状態を維持して再描画する。
        self._refresh_requirements_banner()

    def _collect_banner_input_values(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for k, w in self._banner_input_widgets().items():
            getter = getattr(w, "text", None)
            if callable(getter):
                try:
                    out[k] = (getter() or "").strip()
                except Exception:
                    out[k] = ""
            else:
                out[k] = ""
        return out

    def _banner_file_exists(self, path: str) -> bool:
        """要件テーブルのファイル/ディレクトリ存在判定。

        - 末尾が "/" のものはディレクトリ扱い（中身が 1 件以上で True）。
        - それ以外はファイル存在で判定。
        ベースは ``self._repo_root``。
        """
        base = self._repo_root
        try:
            target = base / path
            if path.endswith("/"):
                return target.is_dir() and any(target.iterdir())
            return target.is_file()
        except Exception:
            return False

    def _current_selection_for_banner(self) -> List[Tuple[str, List[str]]]:
        """現在の選択 (workflow_id, step_ids) リストを返す。
        ステップ ID は外部から提供される必要があるため、保持していない場合は
        全 workflow_id に空リストを返す（外部から ``update_requirements_banner``
        で明示更新されるまでは「対象なし」表示となる）。
        """
        return [(wf, []) for wf in self._workflow_ids]

    def update_requirements_banner(
        self,
        selected: List[Tuple[str, List[str]]],
    ) -> None:
        """外部（WorkflowSelectPage）から呼び出される公開 API。

        Args:
            selected: [(workflow_id, [step_id, ...]), ...]
        """
        self._last_banner_selection = selected
        self._refresh_requirements_banner()

    def _refresh_requirements_banner(self) -> None:
        """内部: バナー内容と配置先を更新する。"""
        selected = getattr(self, "_last_banner_selection", None)
        if not selected:
            # 選択未確定なら非表示
            self._move_banner_to_section(None)
            return

        target = pick_target_step(selected)
        if target is None:
            self._move_banner_to_section(None)
            return

        workflow_id, step_id = target

        # ARD 添付ペインの状態を取得
        attached_count = 0
        origin_chosen = False
        if self._attachment_pane is not None and workflow_id == "ard":
            ts = getattr(self._attachment_pane, "target_business_path", None)
            if callable(ts):
                origin_chosen = bool(ts())
            # 添付件数: _results 属性を参照（無ければ 0）
            results = getattr(self._attachment_pane, "_results", None)
            if results is not None:
                try:
                    attached_count = len(results)
                except Exception:
                    attached_count = 0

        summary = summarize_requirements(
            workflow_id, step_id,
            input_values=self._collect_banner_input_values(),
            file_exists=self._banner_file_exists,
            attached_count=attached_count,
            origin_chosen=origin_chosen,
        )
        if summary is None:
            self._move_banner_to_section(None)
            return

        section = summary.section
        self._move_banner_to_section(section)
        self._requirements_banner.set_summary(summary)
        self._requirements_banner.setVisible(True)

    def _move_banner_to_section(self, section: Optional[str]) -> None:
        """バナーを指定セクションのレイアウト先頭に移動する。

        section=None または不明セクション → 非表示。
        """
        banner = self._requirements_banner
        if section is None:
            banner.setVisible(False)
            self._banner_current_section = None
            return

        if section == self._banner_current_section:
            return  # 既に正しい配置

        # 既存の親レイアウトから取り除く
        parent_layout = banner.parentWidget().layout() if banner.parentWidget() else None
        if parent_layout is not None:
            for i in range(parent_layout.count()):
                if parent_layout.itemAt(i) is not None and parent_layout.itemAt(i).widget() is banner:
                    parent_layout.takeAt(i)
                    break
        banner.setParent(None)

        # 配置先決定
        if section == "OPTIONS_TOP":
            if self._groups_layout is not None:
                self._groups_layout.insertWidget(0, banner)
                self._banner_current_section = section
                return
        else:
            group = self._category_groups.get(section)
            if group is not None:
                inner = group.layout()
                if inner is not None:
                    inner.insertWidget(0, banner)
                    self._banner_current_section = section
                    return

        # 配置先が解決できない場合は非表示扱い
        banner.setVisible(False)
        self._banner_current_section = None

    # ----------------------------------------------------------
    # UI セットアップ
    # ----------------------------------------------------------

    def _setup_ui(self) -> None:
        # 画面内タイトル（旧: "Step 2: オプション選択"）は親ページ (WorkflowSelectPage)
        # 側のヘッダに統合したため、本ページからは削除。

        # 全カテゴリを QGroupBox として縦に並べる（GitHub Issue Template スタイル）。
        # QToolBox から置き換え: 一度に1セクションのみ表示・内部スクロール域不足で
        # 内容が切れる問題を解消する。
        self._page_indices: Dict[str, int] = {}
        self._category_groups: Dict[str, QGroupBox] = {}

        groups_container = QWidget()
        groups_layout = QVBoxLayout(groups_container)
        groups_layout.setContentsMargins(4, 4, 4, 4)
        groups_layout.setSpacing(12)
        self._groups_layout = groups_layout

        # 見出しスタイル: 太字・少し大きめ。説明文との視覚差を確保。
        group_style = (
            "QGroupBox { font-size: 11pt; font-weight: bold; "
            "border: 1px solid #d0d7de; border-radius: 6px; "
            "margin-top: 12px; padding: 12px 8px 8px 8px; background: #f6f8fa; }"
            " QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; "
            " color: #1f2328; }"
        )

        def _add(key: str, title: str, widget: QWidget) -> None:
            from .help_popup import HelpPopupButton

            group = QGroupBox(title)
            group.setStyleSheet(group_style)
            inner = QVBoxLayout(group)
            inner.setContentsMargins(8, 8, 8, 8)

            # カテゴリ見出しのヘルプボタン行
            help_btn = HelpPopupButton.from_key(f"category.{key}")
            if help_btn is not None:
                help_row = QHBoxLayout()
                help_row.setContentsMargins(0, 0, 0, 0)
                help_row.addStretch()
                help_row.addWidget(QLabel(self.tr("このセクションについて:")))
                help_row.addWidget(help_btn)
                inner.addLayout(help_row)

            inner.addWidget(widget)
            widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            groups_layout.addWidget(group)
            idx = len(self._page_indices)
            self._page_indices[key] = idx
            self._category_groups[key] = group

        _add("C1", "基本設定  *必須", self.c1)
        _add("C3", "自動プロンプト", self.c3)
        _add("C4", "Work IQ", self.c4)
        _add("C5", "Git", self.c5)
        _add("C6", "出力制御", self.c6)
        _add("C7", "MCP / CLI 接続", self.c7)
        _add("AZURE", "Azure", self.c_azure)
        _add("C10", "アプリケーションID", self.c10)
        _add("C11", "AKM 固有", self.c11)
        _add("C12", "AQOD 固有", self.c12)
        _add("C13", "ADOC 固有", self.c13)
        _add("C14", "要求定義書", self.c14)

        groups_layout.addStretch(1)

        # スクロール対応
        scroll = QScrollArea()
        scroll.setWidget(groups_container)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # コマンドプレビュー / 画面タイトル / StepIntroBanner は本ページ統合に伴い削除。

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll, stretch=1)

    def _refresh_specific_categories(self) -> None:
        """ワークフロー別の表示制御（フィールド粒度）。

        - `_STEP2_HIDDEN_CATEGORIES` のカテゴリは Step 2 では完全非表示（設定画面で編集）。
        - 残カテゴリ内の `_LabeledField` は全て一旦非表示。
        - 選択ワークフローの `_STEP2_FIELDS_BY_WORKFLOW` で指定されたフィールドのみ表示。
        - C15 の `追加プロンプト` は常に表示（共通・最下段）。
        - 表示フィールドが 1 つも無いカテゴリ枠は非表示。
        - `aas` のみ選択時は案内ラベルを表示。
        """
        selected_workflows = self._workflow_ids or (
            [self._workflow_id] if self._workflow_id else []
        )

        # 1) Step 2 非表示カテゴリは完全に隠す
        for cat_key in _STEP2_HIDDEN_CATEGORIES:
            g = self._category_groups.get(cat_key)
            if g is not None:
                g.setVisible(False)

        # 1.5) C3 内「追加プロンプト」のみは Step 1 右ペインで常時表示する例外。
        #     - カテゴリ枠 C3 を可視化し、枠タイトルを「追加プロンプト」に上書き
        #     - C3 内の他フィールド（QA 自動投入 等）は明示的に hide
        c3_group = self._category_groups.get("C3")
        if c3_group is not None:
            c3_group.setVisible(True)
            try:
                c3_group.setTitle(self.tr("追加プロンプト"))
            except Exception:
                pass
            for lf in self.c3.findChildren(_LabeledField):
                lbl = lf.findChild(QLabel)
                head = ""
                if lbl is not None:
                    head = lbl.text().split("  *")[0].strip()
                lf.setVisible(head not in _C3_NON_ADDITIONAL_PROMPT_TITLES)

        # 2) ワークフロー固有カテゴリ + C4 の全 _LabeledField を一旦非表示
        category_attr_map = {
            "C4": self.c4,
            "C10": self.c10,
            "C11": self.c11,
            "C12": self.c12,
            "C13": self.c13,
            "C14": self.c14,
        }
        for cw in category_attr_map.values():
            for lf in cw.findChildren(_LabeledField):
                lf.setVisible(False)

        # 3) 表示すべきフィールドの集合を構築（重複は自動的に統合）
        attr_to_category = {
            "c4": "C4",
            "c10": "C10",
            "c11": "C11",
            "c12": "C12",
            "c13": "C13",
            "c14": "C14",
        }
        wanted: List[tuple] = []
        seen: set = set()

        def _add_field(entry: tuple) -> None:
            if entry in seen:
                return
            seen.add(entry)
            wanted.append(entry)

        for wf_id in selected_workflows:
            for entry in _STEP2_FIELDS_BY_WORKFLOW.get(wf_id, []):
                _add_field(entry)
        # 共通: 追加プロンプトを最下段で表示
        for entry in _STEP2_COMMON_FIELDS:
            _add_field(entry)

        visible_categories: set = set()
        for cat_attr, title in wanted:
            cw = getattr(self, cat_attr, None)
            if cw is None:
                continue
            lf = self._find_labeled_field(cw, title)
            if lf is not None:
                lf.setVisible(True)
                cat_key = attr_to_category.get(cat_attr)
                if cat_key:
                    visible_categories.add(cat_key)

        # 4) 表示フィールドが 1 つも無いカテゴリ枠を非表示
        for cat_key, cw in category_attr_map.items():
            g = self._category_groups.get(cat_key)
            if g is None:
                continue
            g.setVisible(cat_key in visible_categories)

        # 5) APP-ID チェックリスト注入（aad-web のみ）
        self._refresh_app_id_checklist(selected_workflows)

        # 6) `aas` 案内ラベル
        self._refresh_aas_notice(selected_workflows, visible_categories)

        # 7) 表示カテゴリを Workflow Step 順 (ARD 先頭) に並べ替え
        self._reorder_visible_categories(selected_workflows, visible_categories)

        # 8) 「追加プロンプト」(C3) を最上部に固定する。
        #     - `_reorder_visible_categories` は ordered_keys が空のとき早期 return
        #       するため、ここで独立に C3 ピン留めを行う。
        #     - `_aas_notice` は index 0 に挿入されるが、ユーザー要件により
        #       「追加プロンプトを一番上」とするため C3 をさらに index 0 へ前置する。
        self._pin_additional_prompt_top()

    def _pin_additional_prompt_top(self) -> None:
        """C3 カテゴリ枠（追加プロンプト）を `_groups_layout` の index 0 に固定する。"""
        layout = getattr(self, "_groups_layout", None)
        if layout is None:
            return
        c3 = self._category_groups.get("C3")
        if c3 is None:
            return
        # 現在 index 0 でなければ移動。連続適用キャッシュは持たない（軽量操作）。
        if layout.indexOf(c3) == 0:
            return
        layout.removeWidget(c3)
        layout.insertWidget(0, c3)

    def _reorder_visible_categories(
        self,
        selected_workflows: List[str],
        visible_categories: set,
    ) -> None:
        """選択 Workflow に基づき表示カテゴリを正準順 (ARD 先頭) で並べ替える。

        - `visible_categories` は `_refresh_specific_categories` で算出済みの
          「表示意図」セット。`QWidget.isVisible()` は親階層未表示時に
          False を返すため初回描画で空振りする。ここでは意図集合を使う。
        - 共有カテゴリ C4 (Work IQ) は `_C4_OWNER_WORKFLOWS` の最初の所有
          Workflow 直後に 1 回だけ挿入。
        - 末尾の addStretch アイテム (QSpacerItem) は `removeWidget` の対象外
          のため末尾に残る。
        - 同じ並び順を連続で適用しないようキャッシュし (フローカス飛び/
          フリッカ回避)、同一なら no-op とする。
        """
        layout = getattr(self, "_groups_layout", None)
        if layout is None:
            return

        selected_set = set(selected_workflows)
        ordered_keys: List[str] = []
        c4_inserted = False
        c4_intended_visible = "C4" in visible_categories

        for wf_id in _WORKFLOW_CANONICAL_ORDER:
            if wf_id not in selected_set:
                continue
            cat_key = _WORKFLOW_TO_PRIMARY_CATEGORY.get(wf_id)
            if cat_key is None:
                continue
            if cat_key not in visible_categories:
                continue
            if cat_key not in ordered_keys:
                ordered_keys.append(cat_key)
            # C4 を最初の所有 Workflow (`_C4_OWNER_WORKFLOWS`) の直後に 1 回だけ挿入
            if (
                not c4_inserted
                and c4_intended_visible
                and wf_id in _C4_OWNER_WORKFLOWS
                and "C4" not in ordered_keys
            ):
                ordered_keys.append("C4")
                c4_inserted = True

        if not ordered_keys:
            return

        # 連続適用キャッシュ: 同じ並び順なら何もしない (フリッカ/フォーカス飛び回避)
        if getattr(self, "_last_ordered_keys", None) == ordered_keys:
            return
        self._last_ordered_keys = list(ordered_keys)

        # 並べ替え対象を一旦 layout から外し、正準順で再挿入する。
        # `removeWidget` は QSpacerItem (addStretch) に作用しないため stretch は末尾に残る。
        for cat_key in ordered_keys:
            g = self._category_groups.get(cat_key)
            if g is not None:
                layout.removeWidget(g)
        for i, cat_key in enumerate(ordered_keys):
            g = self._category_groups.get(cat_key)
            if g is not None:
                layout.insertWidget(i, g)

    @staticmethod
    def _find_labeled_field(parent_widget: QWidget, title: str) -> Optional["_LabeledField"]:
        """parent_widget 配下から指定タイトルの _LabeledField を返す。

        タイトル末尾の "*必須" マーカーは無視して比較する。
        """
        normalized = title.strip()
        for lf in parent_widget.findChildren(_LabeledField):
            lbl = lf.findChild(QLabel)
            if lbl is None:
                continue
            text = lbl.text()
            # "  *必須" を除去
            head = text.split("  *")[0].strip()
            if head == normalized:
                return lf
        return None

    def _refresh_app_id_checklist(self, selected_workflows: List[str]) -> None:
        """`aad-web` 選択時に APP-ID チェックリスト Widget を注入する。

        - 元の `app_ids` QLineEdit を含む _LabeledField の入力部分の下に追加する。
        - チェックリストの変更を `app_ids` QLineEdit テキストへ同期する。
        - aad-web 非選択時はチェックリストを隠す。
        - カタログが空（候補なし）の場合は元の QLineEdit を残し手入力可能とする。
        """
        is_aad_web = "aad-web" in selected_workflows

        # 既に注入済みなら可視性のみ切り替え + LineEdit からチェック状態を再同期
        if getattr(self, "_app_id_checklist", None) is not None:
            cl = self._app_id_checklist
            has_entries = bool(getattr(cl, "_entries", []))
            cl.setVisible(is_aad_web and has_entries)
            # カタログが空のときは LineEdit を残し、ある場合は隠す
            self.c10.app_ids.setVisible(not is_aad_web or not has_entries)
            # LineEdit テキストからチェックリストへ再同期（aad-web 表示時のみ）
            if is_aad_web and has_entries:
                cl.set_selected_csv(self.c10.app_ids.text().strip())
            return

        if not is_aad_web:
            return

        try:
            from .widgets.app_id_checklist import AppIdChecklist
        except ImportError:
            return

        self._app_id_checklist = AppIdChecklist(self._repo_root, parent=self.c10)

        # `app_ids` の _LabeledField を取得し、その入力ウィジェットの下にチェックリスト追加
        target_lf = self._find_labeled_field(self.c10, "対象アプリケーション (APP-ID)")
        if target_lf is None:
            return
        target_lf.layout().addWidget(self._app_id_checklist)

        has_entries = bool(self._app_id_checklist._entries)
        # カタログ空時は LineEdit を残す
        self.c10.app_ids.setVisible(not has_entries)
        self._app_id_checklist.setVisible(has_entries)

        # 変更同期: チェックリスト → LineEdit
        def _sync_to_line_edit(csv: str) -> None:
            self.c10.app_ids.setText(csv)
        self._app_id_checklist.selection_changed.connect(_sync_to_line_edit)
        # 初期値を反映
        if has_entries:
            initial = self.c10.app_ids.text().strip()
            if initial:
                self._app_id_checklist.set_selected_csv(initial)

    def _refresh_aas_notice(
        self, selected_workflows: List[str], visible_categories: set
    ) -> None:
        """`aas` のみ選択時に案内ラベルを表示する。"""
        only_aas = selected_workflows == ["aas"]
        if not hasattr(self, "_aas_notice") or self._aas_notice is None:
            # 初回構築
            from PySide6.QtWidgets import QPushButton

            container = QWidget()
            v = QVBoxLayout(container)
            v.setContentsMargins(8, 8, 8, 8)
            v.setSpacing(8)
            label = QLabel(self.tr("オプションは、[設定] メニューで行ってください。"))
            label.setStyleSheet("color: #1f2328; font-size: 11pt; padding: 8px;")
            label.setWordWrap(True)
            btn = QPushButton(self.tr("設定を開く"))
            btn.setMaximumWidth(160)
            btn.clicked.connect(self._open_settings_window_safely)
            v.addWidget(label)
            v.addWidget(btn)
            v.addStretch(1)
            self._aas_notice = container
            # スクロール内の groups_container 先頭に挿入
            if hasattr(self, "_groups_layout") and self._groups_layout is not None:
                self._groups_layout.insertWidget(0, container)
        self._aas_notice.setVisible(only_aas)

    def _open_settings_window_safely(self) -> None:
        """親 MainWindow があれば設定ウィンドウを開く。"""
        try:
            w = self.window()
            opener = getattr(w, "_open_settings_window", None)
            if callable(opener):
                opener()
        except Exception:
            pass

    @staticmethod
    def _hide_labeled_field(parent_widget: QWidget, attr_name: str) -> None:
        """parent_widget.<attr_name> ウィジェットを含む _LabeledField を非表示にする（後方互換）。"""
        target = getattr(parent_widget, attr_name, None)
        if target is None:
            return
        w: Optional[QWidget] = target
        for _ in range(6):
            if w is None:
                return
            if isinstance(w, _LabeledField):
                w.setVisible(False)
                return
            w = w.parentWidget()
        target.setVisible(False)

    def _update_attachment_pane_visibility(self) -> None:
        """ARD 選択時に C14 セクションに添付 D&D ペインを動的追加する。

        実装は `page_options_ard.AttachmentPane` を遅延 import。
        """
        selected_workflows = self._workflow_ids or ([self._workflow_id] if self._workflow_id else [])
        if "ard" not in selected_workflows:
            return
        # 既に追加済みならスキップ
        if self._attachment_pane is not None:
            return
        try:
            from .page_options_ard import AttachmentPane
        except ImportError:
            return

        self._attachment_pane = AttachmentPane()
        # C14 のレイアウト末尾に追加（QVBoxLayout / QFormLayout 両対応）
        c14_layout = self.c14.layout()
        if isinstance(c14_layout, QFormLayout):
            c14_layout.addRow(self._attachment_pane)
        elif isinstance(c14_layout, QVBoxLayout):
            c14_layout.addWidget(self._attachment_pane)

        # 要求定義書 生成完了時に target_business フィールドへ自動セット
        sig = getattr(self._attachment_pane, "business_requirement_generated", None)
        if sig is not None:
            sig.connect(self._on_business_requirement_generated)

        # 添付ファイル件数/起点選択が変わったら要件バナーを再描画（接続漏れ対策）
        files_sig = getattr(self._attachment_pane, "files_changed", None)
        if files_sig is not None:
            files_sig.connect(self._on_banner_input_changed)

    def _on_business_requirement_generated(self, rel_path: str) -> None:
        """AttachmentPane から要求定義書生成完了通知を受けて target_business を自動セット。"""
        if not rel_path:
            return
        target_widget = getattr(self.c14, "target_business", None)
        if target_widget is None:
            return
        # _FilePickerWidget は setText / set_text のどちらかを持つ想定
        setter = getattr(target_widget, "set_text", None) or getattr(
            target_widget, "setText", None
        )
        if callable(setter):
            setter(rel_path)

    # コマンドプレビュー API は本ページ統合に伴い削除済み。
