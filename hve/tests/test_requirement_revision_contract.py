"""改善プラン（work/202609232130-LongtimeDevelopmentImprovementPlan.md）の要件改訂の契約。

要求定義に規範文が存在することだけを検査する。実装の振る舞いは各要件の対応テストが検査する。
"""

from __future__ import annotations

import re
from pathlib import Path

_REQUIREMENTS = Path(__file__).resolve().parents[2] / "hve-dev" / "requirement-definition.md"


def _definition(requirement_id: str) -> str:
    text = _REQUIREMENTS.read_text(encoding="utf-8")
    match = re.search(
        rf"^- \*\*{re.escape(requirement_id)}\*\*: (.+)$", text, flags=re.MULTILINE
    )
    assert match, f"{requirement_id} の定義行が requirement-definition.md に無い"
    return match.group(1)


def test_p2_review_separation_requirements() -> None:
    session = _definition("FR-CLI-92")
    assert "review_model" in session
    assert "新しいセッション" in session
    assert "ならない" in session or "なければならない" in session

    review_input = _definition("FR-CLI-93")
    assert "output_paths" in review_input
    assert "切り詰め" in review_input

    no_fix = _definition("FR-CLI-94")
    assert "修正を指示してはならない" in no_fix
    assert "軽微" in no_fix and "承認" in no_fix
    assert "スタブ" in no_fix

    recheck = _definition("FR-CLI-95")
    assert "未修正の Critical" in recheck
    assert "FAIL を維持" in recheck


def test_p4_reinforcement_requirements() -> None:
    ui = _definition("FR-CLI-96")
    assert "除外するスタイル" in ui
    assert "Arch-UI-Detail.prompt.md" in ui

    deny = _definition("NFR-SEC-04")
    assert "CRITICAL" in deny
    assert "拒否" in deny and "記録" in deny
    assert "CRITICAL 以外" in deny

    report = _definition("FR-CLI-97")
    assert "利用者の判断待ち" in report and "先頭" in report
    assert "マージを止める問題" in report
    assert "続行規則" in report


def test_p3_model_and_language_requirements() -> None:
    model = _definition("FR-MODEL-01")
    assert "`claude-opus-5.5`" in model
    text = _REQUIREMENTS.read_text(encoding="utf-8")
    assert "`MODEL_CHOICES` は 5 値: `claude-opus-5.5`" in text

    checklist = _definition("FR-MODEL-09")
    assert "hve-dev/model-upgrade-checklist.md" in checklist
    assert "既定モデル" in checklist and "なければならない" in checklist

    language = _definition("FR-CLI-98")
    assert "言語指示" in language
    assert "内部推論" in language and "指定してはならない" in language

