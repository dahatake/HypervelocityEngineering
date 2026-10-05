"""FR-MODEL-09: 既定モデル更新時のハーネス再評価チェックリストが部品を列挙する。"""

from __future__ import annotations

from pathlib import Path

_CHECKLIST = Path(__file__).resolve().parents[2] / "hve-dev" / "model-upgrade-checklist.md"


def test_checklist_lists_harness_components() -> None:
    text = _CHECKLIST.read_text(encoding="utf-8")
    for component in ("事前 QA", "Phase 3 敵対的レビュー", "言語指示", "大型 Prompt", "計画の分割閾値"):
        assert component in text, component
    assert "NOT_MEASURED" in text
    assert "FR-MODEL-09" in text
