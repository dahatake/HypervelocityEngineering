"""hve.gui.settings_apply — page_options ウィジェット ↔ settings_store の橋渡し。

各 `_C*` ウィジェットは元々 `to_args(OrchestrateArgs)` を持つが、
設定保存・復元では独自のフィールドアクセスが必要になる。
本モジュールはウィジェット固有のフィールド名を一箇所に集約する。
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QWidget,
)


# ---------------------------------------------------------------------------
# 値の読み書きヘルパー
# ---------------------------------------------------------------------------
def _get(widget: Any) -> Any:
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QComboBox):
        # TriStateCombo (page_options) 等
        if hasattr(widget, "get_tristate"):
            v = widget.get_tristate()
            return "" if v is None else ("on" if v else "off")
        data = widget.currentData()
        return data if data is not None else ""
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, QPlainTextEdit):
        return widget.toPlainText()
    # QLineEdit 互換 wrapper（例: _FilePickerWidget は QWidget サブクラスだが
    # text()/setText() を duck-type で公開する）。`isinstance(QLineEdit)` では
    # 捕捉できないため、明示的な text() 呼び出し可能性で判定する。
    text_attr = getattr(widget, "text", None)
    if callable(text_attr):
        try:
            value = text_attr()
        except TypeError:
            return None
        if isinstance(value, str):
            return value
    return None


def _set(widget: Any, value: Any) -> None:
    if isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
        return
    if isinstance(widget, QSpinBox):
        try:
            widget.setValue(int(value))
        except (TypeError, ValueError):
            pass
        return
    if isinstance(widget, QDoubleSpinBox):
        try:
            widget.setValue(float(value))
        except (TypeError, ValueError):
            pass
        return
    if isinstance(widget, QComboBox):
        if hasattr(widget, "set_tristate"):
            if value == "on":
                widget.set_tristate(True)
            elif value == "off":
                widget.set_tristate(False)
            else:
                widget.set_tristate(None)
            return
        # userData マッチを優先
        for i in range(widget.count()):
            if widget.itemData(i) == value:
                widget.setCurrentIndex(i)
                return
        # text フォールバック
        idx = widget.findText(str(value))
        if idx >= 0:
            widget.setCurrentIndex(idx)
        return
    if isinstance(widget, QLineEdit):
        widget.setText("" if value is None else str(value))
        return
    if isinstance(widget, QPlainTextEdit):
        widget.setPlainText("" if value is None else str(value))
        return
    # QLineEdit 互換 wrapper（例: _FilePickerWidget）への duck-type 経路。
    set_text_attr = getattr(widget, "setText", None)
    if callable(set_text_attr):
        try:
            set_text_attr("" if value is None else str(value))
        except TypeError:
            pass
        return


# ---------------------------------------------------------------------------
# セクションごとのフィールド対応
# ---------------------------------------------------------------------------
# 各 key = settings_store の options キー、value = ウィジェット属性名
_SECTION_FIELDS: Dict[str, Dict[str, str]] = {
    "C1": {
        "model": "model",
        "review_model": "review_model",
        "qa_model": "qa_model",
        "reasoning_effort": "effort",
        "review_reasoning_effort": "review_effort",
        "qa_reasoning_effort": "qa_effort",
        # 旧 C2 / C8 / C6 から移動
        "max_parallel": "max_parallel",
        "timeout": "timeout",
        "review_timeout": "review_timeout",
        "theme": "theme",
        "verbosity": "verbosity",
    },
    "C3": {
        "auto_qa": "auto_qa",
        "qa_answer_mode": "qa_answer_mode",
        "force_interactive": "force_interactive",
        "auto_contents_review": "auto_contents_review",
        "auto_coding_agent_review": "auto_coding_agent_review",
        "auto_coding_agent_review_auto_approval": "auto_coding_agent_review_auto_approval",
        # 旧 C16 / C15 から移動
        "self_improve": "self_improve",
        "no_self_improve": "no_self_improve",
        "additional_prompt": "additional_prompt",
        "context_max_chars": "context_max_chars",
    },
    "C5": {
        "create_issues": "create_issues",
        "create_pr": "create_pr",
        "ignore_paths": "ignore_paths",
        "repo": "repo",
        "issue_title": "issue_title",
        # 旧 C9 / C11 から移動
        "branch": "branch",
        "enable_auto_merge": "enable_auto_merge",
    },
    "C7": {"cli_path": "cli_path", "cli_url": "cli_url"},
    "AZURE": {
        "resource_group": "resource_group",
    },
    "C4": {
        "workiq": "workiq",
        "workiq_dxx": "workiq_dxx",
        "workiq_draft": "workiq_draft",
        "workiq_draft_output_dir": "workiq_draft_output_dir",
        "workiq_prompt_qa": "workiq_prompt_qa",
        "workiq_prompt_km": "workiq_prompt_km",
        "workiq_prompt_review": "workiq_prompt_review",
        "workiq_per_question_timeout": "workiq_per_question_timeout",
        "workiq_request_timeout": "workiq_request_timeout",
        # tri-state: workiq_akm_review / workiq_akm_ingest
        "workiq_akm_review": "workiq_akm_review",
        "workiq_akm_ingest": "workiq_akm_ingest",
    },
    "C10": {
        "app_id": "app_id",
        "app_ids": "app_ids",
        "usecase_id": "usecase_id",
    },
    "C11": {
        "target_files": "target_files",
        "force_refresh": "force_refresh",
        "custom_source_dir": "custom_source_dir",
        # sources_* は _C11AKM の QCheckBox 3 個。個別に autosave 経路へ乗せる
        # （`to_args()` 側は引き続き CSV `sources` として集約される）。
        "sources_qa": "sources_qa",
        "sources_original_docs": "sources_original_docs",
        "sources_workiq": "sources_workiq",
    },
    "C12": {
        "target_scope": "target_scope",
        "depth": "depth",
        "focus_areas": "focus_areas",
    },
    "C13": {
        "target_dirs": "target_dirs",
        "exclude_patterns": "exclude_patterns",
        "doc_purpose": "doc_purpose",
        "max_file_lines": "max_file_lines",
    },
    "C14": {
        "company_name": "company_name",
        "target_business": "target_business",
        "survey_base_date": "survey_base_date",
        "survey_period_years": "survey_period_years",
        "target_region": "target_region",
        "analysis_purpose": "analysis_purpose",
        "target_recommendation_id": "target_recommendation_id",
        "attached_docs": "attached_docs",
    },
    "MDQ": {
        "mdq_watch": "mdq_watch",
        "mdq_watch_debounce_ms": "mdq_watch_debounce_ms",
    },
    "LANG": {
        "language": "language",
    },
    "AUTOPILOT": {
        "autopilot_max_parallel": "autopilot_max_parallel",
        "step1_show_plan_review_always": "step1_show_plan_review_always",
    },
    "GUI_SESSION": {
        "gui_session_cleanup_policy": "gui_session_cleanup_policy",
    },
    # EXPLORER: 値は ";" 区切り文字列。QListWidget との同期は
    # ``_CExplorerSection`` 内部で完結し、settings_apply 経由では QLineEdit
    # ``explorer_roots`` の text だけを読み書きする。
    "EXPLORER": {
        "explorer_roots": "explorer_roots",
    },
}


def apply_to_widgets(
    sections: Dict[str, QWidget], settings: Dict[str, Dict[str, Any]]
) -> None:
    """settings dict をウィジェット群へ書き込む。"""
    options = settings.get("options", {})
    for sec_key, fields in _SECTION_FIELDS.items():
        widget = sections.get(sec_key)
        if widget is None:
            continue
        for opt_key, attr_name in fields.items():
            if opt_key not in options:
                continue
            sub = getattr(widget, attr_name, None)
            if sub is None:
                continue
            _set(sub, options[opt_key])


def collect_from_widgets(sections: Dict[str, QWidget]) -> Dict[str, Any]:
    """ウィジェット群から options dict を組み立てる。"""
    out: Dict[str, Any] = {}
    for sec_key, fields in _SECTION_FIELDS.items():
        widget = sections.get(sec_key)
        if widget is None:
            continue
        for opt_key, attr_name in fields.items():
            sub = getattr(widget, attr_name, None)
            if sub is None:
                continue
            out[opt_key] = _get(sub)
    return out


def wire_autosave(
    sections: Dict[str, QWidget],
    *,
    on_changed: Callable[[], None],
) -> None:
    """各ウィジェットの変更シグナルを on_changed に接続する。"""
    for sec_key, fields in _SECTION_FIELDS.items():
        widget = sections.get(sec_key)
        if widget is None:
            continue
        for attr_name in fields.values():
            sub = getattr(widget, attr_name, None)
            if sub is None:
                continue
            _connect_changed(sub, on_changed)


def _connect_changed(widget: Any, callback: Callable[[], None]) -> None:
    if isinstance(widget, QCheckBox):
        widget.stateChanged.connect(lambda *_: callback())
    elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        widget.valueChanged.connect(lambda *_: callback())
    elif isinstance(widget, QComboBox):
        widget.currentIndexChanged.connect(lambda *_: callback())
    elif isinstance(widget, QLineEdit):
        widget.editingFinished.connect(callback)
    elif isinstance(widget, QPlainTextEdit):
        widget.textChanged.connect(callback)
    else:
        # QLineEdit 互換 wrapper（_FilePickerWidget 等）。内部の QLineEdit
        # (`_edit`) があれば editingFinished を購読する。Browse ボタン経由の
        # setText でも editingFinished が emit されない仕様だが、closeEvent の
        # 強制保存により最終的に値は保持される。
        inner = getattr(widget, "_edit", None)
        if isinstance(inner, QLineEdit):
            inner.editingFinished.connect(callback)
