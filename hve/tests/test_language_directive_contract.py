"""FR-CLI-98: 全 Step 先頭へ注入する言語指示は出力言語だけを指定する。"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DIRECTIVE = _ROOT / ".github" / "prompts" / "runtime" / "orchestrator" / "language-directive-ja.prompt.md"
_PREAMBLE = _ROOT / ".github" / "skills" / "agent-common-preamble" / "SKILL.md"
_INTERNAL_REASONING_WORDS = ("思考プロセス", "chain-of-thought", "内部独白", "推論の途中経過", "計画の自問自答")


def test_directive_limits_to_output_language() -> None:
    directive = _DIRECTIVE.read_text(encoding="utf-8")
    for word in _INTERNAL_REASONING_WORDS:
        assert word not in directive, word
    assert "最終出力・成果物・計画・ツール委譲の説明は日本語で記述" in directive
    assert "固有名詞・コマンド名・ファイルパス・コード識別子・引用文は英語のままで構わない" in directive


def test_preamble_does_not_direct_internal_reasoning_language() -> None:
    preamble = _PREAMBLE.read_text(encoding="utf-8")
    for word in ("推論の途中経過", "計画の自問自答"):
        assert word not in preamble, word
    assert "最終出力、成果物、計画、ツール委譲の説明は日本語で記述する" in preamble
