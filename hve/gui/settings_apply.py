"""hve.gui.settings_apply — page_options ウィジェット ↔ settings_store の橋渡し。

各 `_C*` ウィジェットは元々 `to_args(OrchestrateArgs)` を持つが、
設定保存・復元では独自のフィールドアクセスが必要になる。
本モジュールはウィジェット固有のフィールド名を一箇所に集約する。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional, Set, Tuple

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
            if value is True or value == "on":
                widget.set_tristate(True)
            elif value is False or value == "off":
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
        "context_tier": "context_tier",
        "run_id_timezone": "run_id_timezone",
        # 旧 C2 / C8 / C6 から移動
        "max_parallel": "max_parallel",
        "timeout": "timeout",
        "review_timeout": "review_timeout",
        "theme": "theme",
        "verbosity": "verbosity",
        # 旧 GUI_SESSION セクションから移動
        "gui_session_cleanup_policy": "gui_session_cleanup_policy",
        # 旧「自動プロンプト」ノードから移設
        "additional_prompt": "additional_prompt",
        "context_max_chars": "context_max_chars",
        # FR-LOCAL-SURFACE-01 (a): SDK tool search の 3 状態選択。
        "enable_tool_search": "enable_tool_search",
        # FR-LOCAL-SURFACE-01 (a): CLI `--strict` と共通の pre-check 中断制御。
        "strict": "strict",
    },
    "QA": {
        "auto_qa": "auto_qa",
        "qa_answer_mode": "qa_answer_mode",
    },
    "REVIEW": {
        "auto_contents_review": "auto_contents_review",
        "auto_coding_agent_review": "auto_coding_agent_review",
        "auto_coding_agent_review_auto_approval": "auto_coding_agent_review_auto_approval",
    },
    "KM": {
        "qa_akm_background_merge": "qa_akm_background_merge",
        "akm_model": "akm_model",
        "akm_reasoning_effort": "akm_effort",
        "akm_context_tier": "akm_context_tier",
    },
    "SELFIMPROVE": {
        "self_improve": "self_improve",
        "self_improve_max_iterations": "self_improve_max_iterations",
        "self_improve_target_scope": "self_improve_target_scope",
        "self_improve_goal": "self_improve_goal",
    },
    "C5": {
        "create_issues": "create_issues",
        "create_pr": "create_pr",
        "create_working_branch": "create_working_branch",
        "ignore_paths": "ignore_paths",
        "repo": "repo",
        "issue_title": "issue_title",
        "issue_mode": "issue_mode",
        "issue_number": "issue_number",
        # FR-GUI-32: GUI セッション内だけで使う PR 番号（OrchestrateArgs へは出さない）
        "linked_pr_number": "linked_pr_number",
        # 旧 C9 / C11 から移動
        "branch": "branch",
        # FR-GUI-38: 進捗を引き継ぐ再実行の run-id
        "resume_run": "resume_run",
        "enable_auto_merge": "enable_auto_merge",
        "delete_local_merged_branch": "delete_local_merged_branch",
        # FR-GUI-36: GUI セッション内だけで使う自動進捗 Post の送信先
        "github_auto_post_target": "github_auto_post_target",
        # 旧 C1 から移動: Fleet mode / Cloud Sessions
        "fleet_mode_enabled": "fleet_mode_enabled",
        "cloud_session_enabled": "cloud_session_enabled",
        "cloud_session_repository_branch": "cloud_session_repository_branch",
        "cloud_session_max_concurrency": "cloud_session_max_concurrency",
        "cloud_session_integration_id": "cloud_session_integration_id",
        "cloud_session_mc_base_url": "cloud_session_mc_base_url",
        "cloud_session_step_overrides": "cloud_session_step_overrides",
        "cloud_session_subtask_overrides": "cloud_session_subtask_overrides",
    },
    "C7": {"cli_path": "cli_path", "cli_url": "cli_url"},
    # FR-GUI-03: 永続化するのは `default_params` を持たない必須パラメータだけ。
    # 既定値を持つ ASDW-WEB Step 1.3 の `data_*` は入力欄を持たない（FR-WF-ASDW-02）。
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
    "C17": {
        "purpose": "purpose",
        "target_scope": "target_scope",
        "depth": "analysis_depth",
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
    # CQ: profile / build_profiles は `[cq]` セクションへ CqIndexSection が直接
    # 書き込む。ここへ載せるのは `[options]` 側の watch 2 キーだけ（FR-GUI-04）。
    "CQ": {
        "cq_watch": "cq_watch",
        "cq_watch_debounce_ms": "cq_watch_debounce_ms",
    },
    "LANG": {
        "language": "language",
    },
    "AUTOPILOT": {
        "autopilot_max_parallel": "autopilot_max_parallel",
        "step1_show_plan_review_always": "step1_show_plan_review_always",
        "autopilot_show_app_id_picker": "autopilot_show_app_id_picker",
        "autopilot_app_id_picker_timeout_sec": "autopilot_app_id_picker_timeout_sec",
        "auto_compaction": "auto_compaction",
    },
    # TOOLSEARCH: FR-GUI-07。この 2 キーの入力欄は本セクションが単独で所有する
    # （Step 1 右ペインと二重に持たない。FR-MAINT-07）。
    "TOOLSEARCH": {
        "tool_search": "tool_search",
        "tool_search_ranking": "tool_search_ranking",
    },
    # AGENTIC: FR-LOCAL-SURFACE-01 (a)。`_CAgenticRetrieval` の 6 項目を
    # 永続化する。QComboBox の userData はすべて往復可能な文字列で、
    # CLI の型への復元は `_CAgenticRetrieval.to_args()` が行う。
    "AGENTIC": {
        "enable_agentic_retrieval": "enable_agentic_retrieval",
        "agentic_data_source_modes": "agentic_data_source_modes",
        "foundry_mcp_integration": "foundry_mcp_integration",
        "agentic_data_sources_hint": "agentic_data_sources_hint",
        "agentic_existing_design_diff_only": "agentic_existing_design_diff_only",
        "foundry_sku_fallback_policy": "foundry_sku_fallback_policy",
    },
    # EXPLORER: 値は ";" 区切り文字列。QListWidget との同期は
    # ``_CExplorerSection`` 内部で完結し、settings_apply 経由では QLineEdit
    # ``explorer_roots`` の text だけを読み書きする。
    "EXPLORER": {
        "explorer_roots": "explorer_roots",
    },
}


def apply_to_widgets(
    sections: Dict[str, QWidget],
    settings: Dict[str, Dict[str, Any]],
    *,
    skip_keys: Optional[Iterable[Tuple[str, str]]] = None,
) -> None:
    """settings dict をウィジェット群へ書き込む。

    Args:
        sections: セクションキー (例: ``"C10"``) → 対象 widget のマッピング。
        settings: ``settings_store.load()`` の戻り値。
        skip_keys: 上書きを抑止する ``(section_key, option_key)`` の集合。
            例: ``{("C10", "app_ids")}`` を渡すと、Settings dialog 経由の
            空文字 autosave で OptionsPage の APP-ID 欄が上書きされる経路を
            遮断できる（Step 1 の AppIdChecklist を SSOT として保護する）。
    """
    options = settings.get("options", {})
    skip_set: Set[Tuple[str, str]] = set(skip_keys) if skip_keys else set()
    for sec_key, fields in _SECTION_FIELDS.items():
        widget = sections.get(sec_key)
        if widget is None:
            continue
        for opt_key, attr_name in fields.items():
            if (sec_key, opt_key) in skip_set:
                continue
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
