"""FR-E2E-01: 依頼 1 回での無人の一気通貫実行（規範目標）の契約テスト。

AC-003 の実測（課金を伴う比較実測 N5-4）は時間枠で打ち切り、HVE の full-pipeline
実行としての合格 run はまだ無いため、ここでは
規範目標の停止境界が要求定義と無人実行の指示で一致していることだけを固定する。
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
REQ_DEF = ROOT / "hve-dev" / "requirement-definition.md"
UNATTENDED_PROMPT = (
    ROOT / ".github" / "prompts" / "runtime" / "runner" / "unattended-guidance-suffix.prompt.md"
)

_STOP_TERMS = ("資格情報", "宣言範囲外", "破壊的", "不可逆", "課金", "外部公開")


def _definition_line(identifier: str) -> str:
    text = REQ_DEF.read_text(encoding="utf-8")
    matches = [
        line for line in text.splitlines() if line.startswith(f"- **{identifier}**:")
    ]
    assert len(matches) == 1, f"{identifier} must be defined exactly once"
    return matches[0]


def test_fr_e2e_01_is_must_and_limits_stops_to_two_conditions() -> None:
    line = _definition_line("FR-E2E-01")
    assert "優先度 MUST" in line
    assert "依頼 1 回" in line
    assert "full-pipeline" in line
    assert "resource_group" in line
    for term in ("資格情報", "破壊的", "不可逆", "課金", "外部公開"):
        assert term in line, term
    assert "FR-PROMPT-06" in line, "未選択 Workflow を暗黙に足さない制約を維持すること"


def test_ac_003_traces_fr_e2e_01() -> None:
    text = REQ_DEF.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| AC-003 |")]
    assert len(rows) == 1
    assert "| FR-E2E-01 |" in rows[0]
    assert "exit 0" in rows[0]


def test_unattended_guidance_uses_the_same_stop_boundary() -> None:
    body = UNATTENDED_PROMPT.read_text(encoding="utf-8")
    stop_sentences = [s for s in re.split(r"(?<=。)", body) if "停止" in s]
    assert stop_sentences, "無人実行の指示に停止境界の文が必要"
    joined = "".join(stop_sentences)
    for term in _STOP_TERMS:
        assert term in joined, term
