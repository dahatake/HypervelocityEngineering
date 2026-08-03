"""APP 推薦名から downstream workflow への二分類契約テスト。"""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = _REPO_ROOT / ".github" / "prompts" / "Arch-ArchitectureCandidateAnalyzer.prompt.md"
_OUTPUT_FORMAT = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "architecture-questionnaire"
    / "assets"
    / "output-format.md"
)
_SCOPE_SKILL = _REPO_ROOT / ".github" / "skills" / "app-scope-resolution" / "SKILL.md"
_SCOPE_EVAL = (
    _REPO_ROOT
    / ".github"
    / "skills"
    / "_evals"
    / "app-scope-resolution.eval.yaml"
)

_BATCH_TERMS = (
    "バッチ",
    "ETL",
    "集計",
    "データ処理",
    "データパイプライン",
    "DWH",
    "BI",
    "Analytics",
    "分析",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_routing_contract(text: str) -> None:
    assert "`batch`" in text
    assert "`web-cloud`" in text
    assert "それ以外の非空" in text
    assert "空の推薦は分類しない" in text
    assert "大文字小文字を区別せず" in text
    assert "`BI` は独立した英数字語" in text
    assert "固定候補外の推薦名を許可するものではない" in text
    for term in _BATCH_TERMS:
        assert term in text


def test_architecture_candidate_prompt_declares_routing_contract() -> None:
    _assert_routing_contract(_read(_PROMPT))


def test_architecture_output_format_declares_routing_contract() -> None:
    _assert_routing_contract(_read(_OUTPUT_FORMAT))


def test_app_scope_skill_declares_routing_contract() -> None:
    _assert_routing_contract(_read(_SCOPE_SKILL))


def test_app_scope_eval_covers_fallback_and_boundaries() -> None:
    eval_text = _read(_SCOPE_EVAL)
    expected_terms = {
        "aad-web-bff-falls-back-to-web-cloud": ("BFF", "web-cloud"),
        "adfd-dwh-analytics-falls-back-to-batch": ("DWH", "BI", "Analytics", "batch"),
        "adfd-lowercase-dwh-analytics-falls-back-to-batch": ("大文字小文字", "batch"),
        "aad-web-bi-substring-does-not-trigger-batch": ("BIBLE", "独立", "web-cloud"),
    }
    for case_id, terms in expected_terms.items():
        marker = f"  - id: {case_id}\n"
        start = eval_text.index(marker)
        end = eval_text.find("\n  - id: ", start + len(marker))
        case_text = eval_text[start:] if end < 0 else eval_text[start:end]
        for term in terms:
            assert term in case_text
