"""FR-CLI-92 / FR-CLI-94: 利用者ガイドが Phase 3 の評価分離と評価者の責務を説明する。"""

from __future__ import annotations

from pathlib import Path

_GUIDES = Path(__file__).resolve().parents[2] / "users-guide"


def _read(name: str) -> str:
    return (_GUIDES / name).read_text(encoding="utf-8")


def test_guides_describe_review_session_isolation() -> None:
    for name in ("workflow-reference.md", "hve-cli-orchestrator-guide.md"):
        text = _read(name)
        assert "`review_model` の値に依らず" in text, name
        assert "評価者は判定と指摘だけを行い、成果物を修正しない" in text, name


def test_cli_guide_session_count_note_matches_review_isolation() -> None:
    text = _read("hve-cli-orchestrator-guide.md")
    assert "`--review-model` / `--qa-model` を使って別モデルを指定すると" not in text
