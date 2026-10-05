"""FR-MAINT-14: Coding Agent のモデル・context・subagent・承認契約。"""

from __future__ import annotations

import json
from pathlib import Path

import yaml  # type: ignore

_ROOT = Path(__file__).resolve().parents[2]
_INSTRUCTIONS = _ROOT / ".github" / "copilot-instructions.md"
_SETTINGS = _ROOT / ".vscode" / "settings.json"
_SKILLS = _ROOT / ".github" / "skills"
_FORKED_SKILLS = (
    "adversarial-review",
    "repo-onboarding-fast",
    "requirements-conformance-measurement",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(path: Path) -> dict[str, object]:
    parts = _read(path).split("---", 2)
    assert len(parts) == 3 and not parts[0].strip()
    value = yaml.safe_load(parts[1])
    assert isinstance(value, dict)
    return value


def test_model_routing_is_tiered_and_does_not_claim_automatic_switching() -> None:
    text = _read(_INSTRUCTIONS)
    for phrase in (
        "routine implementation",
        "lightweight investigation",
        "deep reasoning",
        "model picker",
        "自動変更できない",
        "利用可能なモデル名を推測しない",
    ):
        assert phrase in text


def test_model_suggestion_is_limited_to_request_or_deep_reasoning() -> None:
    """FR-MAINT-14（2026-09-25 改訂）: 毎タスクのモデル提案を出さない。"""
    text = _read(_INSTRUCTIONS)
    line = next(l for l in text.splitlines() if "**モデル選択**" in l)
    assert "利用者がモデル選択を尋ねたとき" in line
    assert "deep reasoning` と判断したときだけ" in line
    assert "それ以外では提案しない" in line
    assert "をユーザーへ提案する。" not in line


def test_context_is_not_split_by_request_budget() -> None:
    """FR-MAINT-14（v3.14）: token 数・request 数で session を分割・停止しない。"""
    text = _read(_INSTRUCTIONS)
    settings = json.loads(_read(_SETTINGS))
    assert settings["chat.agent.maxRequests"] >= 200
    assert settings["github.copilot.chat.skillTool.enabled"] is True
    for phrase in (
        "100,000 tokens未満",
        "30 model request",
        "代理ゲート",
    ):
        assert phrase not in text, phrase


def test_heavy_skills_use_forked_context() -> None:
    for name in _FORKED_SKILLS:
        frontmatter = _frontmatter(_SKILLS / name / "SKILL.md")
        assert frontmatter.get("context") == "fork", name


def test_subagent_policy_keeps_parent_context_small() -> None:
    text = _read(_INSTRUCTIONS)
    for phrase in (
        "Explore",
        "execution_subagent",
        "親セッションへは要約だけ",
        "密結合な実装",
    ):
        assert phrase in text


def test_terminal_auto_approval_is_read_only_and_fail_closed() -> None:
    settings = json.loads(_read(_SETTINGS))
    rules = settings["chat.tools.terminal.autoApprove"]
    assert settings["chat.tools.terminal.ignoreDefaultAutoApproveRules"] is False
    assert settings["chat.tools.terminal.blockDetectedFileWrites"] == "outsideWorkspace"

    true_rules = {key for key, value in rules.items() if value is True}
    false_rules = {key for key, value in rules.items() if value is False}
    assert any("git (status|diff" in key for key in true_rules)
    assert any("Get-(ChildItem|Item|Location)" in key for key in true_rules)
    assert all("Get-Content" not in key and "Select-String" not in key for key in true_rules)
    assert any("Remove-Item" in key and "Set-Content" in key for key in false_rules)
    assert any("git (push|reset|clean|restore|checkout" in key for key in false_rules)
    assert any("az|azd|terraform|kubectl" in key for key in false_rules)
    assert any("pytest" in key for key in false_rules)
