"""FR-QA-10 と改善プラン §9 の学習ログ昇格契約を検査する。"""

from __future__ import annotations

from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
_README = _REPO / "work" / "learning" / "README.md"


def _read_learning_readme() -> str:
    assert _README.exists(), f"missing file: {_README}"
    return _README.read_text(encoding="utf-8")


def test_learning_readme_documents_cross_run_exception_and_safety_rules() -> None:
    text = _read_learning_readme()

    for token in (
        "work/run/<run-id>/",
        "外",
        "例外",
        "qa-calibration.jsonl",
        "追記",
        "最新",
        "秘密値",
        "Work IQ",
        "応答本文",
    ):
        assert token in text


def test_learning_readme_documents_promotion_checklist() -> None:
    text = _read_learning_readme()

    for token in (
        "契約テスト",
        "exit 0",
        "過去の実行の受入コマンド",
        "退行",
        "_evals",
        "Skill の発動条件",
        "ルーティング",
        "LLM の自己採点",
        "合否を決めない",
        "PR",
    ):
        assert token in text
