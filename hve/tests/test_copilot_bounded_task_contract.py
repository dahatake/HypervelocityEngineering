"""FR-MAINT-13: Coding Agent の長時間タスクを有界に実行する契約。"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore

_ROOT = Path(__file__).resolve().parents[2]
_SKILLS = _ROOT / ".github" / "skills"
_INSTRUCTIONS = _ROOT / ".github" / "copilot-instructions.md"
_LARGE_OUTPUT = _SKILLS / "large-output-chunking" / "SKILL.md"

_MOVED_SKILLS = {
    "adversarial-review": "harness",
    "harness-error-recovery": "harness",
    "harness-safety-guard": "harness",
    "harness-verification-loop": "harness",
    "tdd-red-green-reality": "testing",
    "tdd-green-retry-strategy": "testing",
    "requirements-conformance-measurement": "testing",
    "docs-output-format": "output",
    "large-output-chunking": "output",
    "azure-region-policy": "azure-skills",
    "azure-cli-deploy-scripts": "azure-skills",
    "azure-ac-verification": "azure-skills",
    "github-actions-cicd": "cicd",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_required_skills_are_directly_discoverable_without_duplicates() -> None:
    for name, old_category in _MOVED_SKILLS.items():
        skill = _SKILLS / name / "SKILL.md"
        assert skill.is_file(), f"missing direct Skill: {skill}"
        parts = _read(skill).split("---", 2)
        assert len(parts) == 3 and not parts[0].strip()
        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter["name"] == name
        assert not (_SKILLS / old_category / name / "SKILL.md").exists()


def test_long_terminal_output_stays_out_of_conversation_context() -> None:
    text = _read(_LARGE_OUTPUT)
    for phrase in (
        "terminal output",
        "会話へ全文注入しない",
        "限定抽出",
        "execution_subagent",
        "秘密値",
        "正常な空出力",
    ):
        assert phrase in text


def test_repository_instructions_do_not_stop_on_session_limits() -> None:
    """FR-MAINT-13（v3.14）: 時間・成果物数・質問回数・tool 実行回数で停止しない。"""
    text = _read(_INSTRUCTIONS)
    for phrase in (
        "1セッション = 1成果物",
        "最大90分",
        "同じ質問の2回目",
        "200回超",
        "着手前の3行提示",
        "60分・タスク3件",
        "新しいセッションで行う",
    ):
        assert phrase not in text, phrase


def test_stop_boundary_is_limited_to_approval_and_credentials() -> None:
    """FR-MAINT-13（v3.14）: 承認済みの計画は要求定義。停止は承認境界と資格情報だけ。"""
    text = _read(_INSTRUCTIONS)
    for phrase in (
        "承認済みの計画は利用者の要求定義",
        "判断と理由を記録して続行",
        "停止してよいのは",
        "資格情報",
        "破壊的・不可逆・外部公開",
        "依存しない作業を先に終える",
    ):
        assert phrase in text, phrase


def test_completion_gate_is_evidence_based() -> None:
    text = _read(_INSTRUCTIONS)
    for phrase in (
        "完了条件",
        "要求定義から導",
        "実出力と exit code",
        "偽 PASS 禁止",
    ):
        assert phrase in text, phrase
    assert "受入基準と停止規則の確定はユーザー" not in text


def test_declared_scope_and_turn_ending_rules_are_in_instructions() -> None:
    """FR-MAINT-13（v3.25）: 宣言範囲は承認済み。4 つの早期終了の形を避ける。"""
    text = _read(_INSTRUCTIONS)
    for phrase in (
        "依頼で宣言された範囲",
        "承認済みとして扱う",
        "ターンの終え方",
        "希望が無ければ続けます",
        "次のツール呼び出しと同じメッセージ",
        "危険な操作・破壊的な操作の確認の必要性は変わらない",
        "FR-PROMPT-13",
    ):
        assert phrase in text, phrase


def test_ambiguous_hve_requests_confirm_only_undeclared_scope() -> None:
    """FR-MAINT-13（v3.25）: 一意に決まる値は選び、確認は資格情報と未宣言の範囲だけ。"""
    text = _read(_INSTRUCTIONS)
    assert "一意に決まる値は、選んだ理由を記録して使う" in text
    assert "資格情報と、依頼で宣言されていないデプロイ先・課金・外部公開" in text
