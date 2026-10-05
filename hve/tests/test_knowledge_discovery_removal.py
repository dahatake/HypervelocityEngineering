"""FR-KD-10: Work IQ 専用処理の削除と、旧列名・旧 GUI 設定の互換読込。"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import pytest

from hve.qa_merger import QAMerger

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HVE = _REPO_ROOT / "hve"

_REMOVED_SYMBOLS = (
    "query_workiq", "query_workiq_detailed", "get_workiq_prompt_template", "save_workiq_result",
    "build_workiq_session_options", "inspect_workiq_session", "validate_workiq_content_contract",
    "is_workiq_result_mergeable", "extract_workiq_status", "format_workiq_tool_not_invoked_warning",
    "format_workiq_content_contract_warning", "build_akm_workiq_query_targets", "render_akm_workiq_query_target",
    "merge_workiq_results", "_filter_workiq_questions", "DEFAULT_WORKIQ_QA_PROMPT", "DEFAULT_WORKIQ_KM_PROMPT",
    "AKM_WORKIQ_INGEST_PROMPT", "AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT", "ARD_WORKIQ_USECASE_PROMPT",
    "workiq_prompt(", "workiq_response(", "_copy_workiq_prompt_btn",
)
_REMOVED_CLI = (
    "--workiq-akm-review", "--workiq-akm-ingest", "--workiq-dxx", "--workiq-draft",
    "--workiq-prompt-qa", "--workiq-prompt-km", "--workiq-per-question-timeout",
)
_REMOVED_FIELDS = (
    "workiq_qa_enabled", "workiq_akm_review_enabled", "workiq_akm_ingest_enabled", "workiq_akm_ingest_dxx",
    "workiq_prompt_qa", "workiq_prompt_km", "workiq_draft_mode", "workiq_draft_output_dir",
    "workiq_per_question_timeout", "workiq_max_draft_questions", "workiq_priority_filter",
)
_REMOVED_ENV = (
    "WORKIQ_QA_ENABLED", "WORKIQ_AKM_REVIEW_ENABLED", "WORKIQ_AKM_INGEST_ENABLED", "WORKIQ_AKM_INGEST_DXX",
    "WORKIQ_PROMPT_QA", "WORKIQ_PROMPT_KM", "WORKIQ_DRAFT_MODE", "WORKIQ_DRAFT_OUTPUT_DIR",
    "WORKIQ_PER_QUESTION_TIMEOUT", "WORKIQ_MAX_DRAFT_QUESTIONS", "WORKIQ_PRIORITY_FILTER",
)
# 廃止キーを読込時に除去するための一覧だけは、削除済みの名前を保持してよい。
_ALLOWED_RESIDUE = {Path("gui") / "settings_store.py"}


def _production_sources() -> list[Path]:
    return [
        p for p in _HVE.rglob("*.py")
        if "tests" not in p.relative_to(_HVE).parts and "__pycache__" not in p.parts
    ]


def test_workiq_runtime_prompts_are_removed() -> None:
    assert not (_REPO_ROOT / ".github" / "prompts" / "runtime" / "workiq").exists()
    for name in ("common", "qa", "knowledge", "research", "repair"):
        assert (_REPO_ROOT / ".github" / "prompts" / "runtime" / "knowledge-discovery" / f"{name}.prompt.md").is_file()


@pytest.mark.parametrize("token", _REMOVED_SYMBOLS + _REMOVED_CLI + _REMOVED_FIELDS + _REMOVED_ENV)
def test_removed_names_have_no_production_reference(token: str) -> None:
    pattern = re.compile(re.escape(token) + (r"\b" if token[-1].isalnum() else ""))
    offenders = [
        str(p.relative_to(_HVE))
        for p in _production_sources()
        if p.relative_to(_HVE) not in _ALLOWED_RESIDUE and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"{token}: {offenders}"


def test_gui_settings_ignore_removed_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hve.gui import settings_store

    removed = (
        "workiq_draft", "workiq_akm_review", "workiq_akm_ingest", "workiq_dxx",
        "workiq_draft_output_dir", "workiq_prompt_qa", "workiq_prompt_km", "workiq_per_question_timeout",
    )
    path = tmp_path / ".settings.txt"
    cp = configparser.ConfigParser()
    cp["options"] = {**{k: "x" for k in removed}, "workiq": "true", "knowledge_sources": "jira"}
    with path.open("w", encoding="utf-8") as f:
        cp.write(f)
    monkeypatch.setattr(settings_store, "_SETTINGS_PATH", path)
    loaded = settings_store.load()
    assert not set(removed) & set(loaded.get("options", {}))
    assert loaded["options"]["knowledge_sources"] == "jira"
    settings_store.save(loaded)
    saved = path.read_text(encoding="utf-8")
    assert not any(f"{k} =" in saved for k in removed)


def test_legacy_workiq_columns_are_read_as_research_columns() -> None:
    legacy = (
        "# QA\n\n## 質問項目\n\n"
        "| No. | 質問 | 選択肢 | 既定値候補 | 既定値候補の理由 | Work IQ 回答案 | Work IQ 理由 | ユーザー回答 |\n"
        "|-----|------|--------|-----------|----------------|----------------|--------------|------------|\n"
        "| 1 | Q | A) x | A | r | 旧回答 | 旧理由 | A |\n"
    )
    q = QAMerger.parse_qa_content(legacy).questions[0]
    assert (q.research_answer, q.research_sources) == ("旧回答", "旧理由")
    rendered = QAMerger.render_merged(QAMerger.parse_qa_content(legacy))
    assert "| 調査回答 | 調査状態 | 調査出典 |" in rendered and "Work IQ 回答案" not in rendered
