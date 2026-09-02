# pyright: reportMissingTypeStubs=false
"""FR-CLOUD-41: blocked → human-required の SLA エスカレーション契約。

`.github/workflows/auto-blocked-to-human-required.yml` と
`.github/workflows/auto-human-resolved-to-ready.yml` は本番 Cloud 経路で稼働している
一方、要求定義書に対応する要件 ID が無く `FR-MAINT-01` / `FR-MAINT-04` の
トレーサビリティ対象外だった。本テストは要件宣言と実装の一致を固定する。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

_ESCALATE_WORKFLOW = "auto-blocked-to-human-required.yml"
_RESOLVE_WORKFLOW = "auto-human-resolved-to-ready.yml"
_SLA_VAR = "HITL_BLOCKED_SLA_HOURS"


def _requirement_line(requirement_id: str) -> str:
    for line in _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines():
        if line.lstrip("- ").startswith(f"**{requirement_id}**"):
            return line
    raise AssertionError(f"{requirement_id} が要求定義書に見つからない")


def _enclosing_section(requirement_id: str) -> str:
    lines = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines()
    target = _requirement_line(requirement_id)
    index = lines.index(target)
    for line in reversed(lines[:index]):
        if line.startswith("## "):
            return line
    raise AssertionError(f"{requirement_id} を含む `## ` 見出しが見つからない")


def _shell_list(text: str, variable: str) -> set[str]:
    match = re.search(rf'^\s*{variable}="([a-z0-9 \-]+)"', text, re.MULTILINE)
    assert match is not None, f"{variable} の定義行が見つからない"
    return set(match.group(1).split())


class TestEscalationRequirementIsDeclared:
    def test_requirement_lives_in_the_cloud_section(self) -> None:
        assert _enclosing_section("FR-CLOUD-41").startswith("## 4.")

    def test_requirement_names_both_workflows(self) -> None:
        line = _requirement_line("FR-CLOUD-41")
        assert _ESCALATE_WORKFLOW in line
        assert _RESOLVE_WORKFLOW in line

    def test_requirement_declares_the_sla_default(self) -> None:
        line = _requirement_line("FR-CLOUD-41")
        assert _SLA_VAR in line
        assert "24" in line

    def test_requirement_declares_updated_at_as_the_sla_clock(self) -> None:
        section = _enclosing_section("FR-CLOUD-41")
        text = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig")
        body = text.split(section, 1)[1].split("\n## ", 1)[0]
        assert "updatedAt" in body
        assert "付与時刻ではない" in body

    def test_requirement_declares_manual_only_escalation(self) -> None:
        section = _enclosing_section("FR-CLOUD-41")
        text = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig")
        body = text.split(section, 1)[1].split("\n## ", 1)[0]
        assert "`workflow_dispatch` だけで起動" in body
        assert "自動トリガーを持ってはならない" in body


class TestEscalationImplementationMatches:
    def test_escalation_workflow_uses_the_declared_sla_default(self) -> None:
        text = (_WORKFLOWS / _ESCALATE_WORKFLOW).read_text(encoding="utf-8")
        assert f"vars.{_SLA_VAR}" in text
        assert "|| '24'" in text

    def test_manual_sla_input_has_priority_over_repository_variable(self) -> None:
        text = (_WORKFLOWS / _ESCALATE_WORKFLOW).read_text(encoding="utf-8")
        expression = f"inputs.sla_hours || vars.{_SLA_VAR} || '24'"
        assert expression in text

    def test_escalation_triggers_match_the_requirement(self) -> None:
        data = yaml.safe_load(
            (_WORKFLOWS / _ESCALATE_WORKFLOW).read_text(encoding="utf-8")
        )
        on_section = data.get(True, {}) or data.get("on", {})
        assert set(on_section) == {"workflow_dispatch"}
        assert "sla_hours" in on_section["workflow_dispatch"]["inputs"]

    def test_resolve_workflow_exists(self) -> None:
        assert (_WORKFLOWS / _RESOLVE_WORKFLOW).is_file()

    def test_resolve_workflow_only_runs_on_labeled_issues(self) -> None:
        data = yaml.safe_load(
            (_WORKFLOWS / _RESOLVE_WORKFLOW).read_text(encoding="utf-8")
        )
        on_section = data.get(True, {}) or data.get("on", {})
        assert set(on_section) == {"issues"}
        assert on_section["issues"]["types"] == ["labeled"]

    def test_both_workflows_target_the_same_prefixes(self) -> None:
        escalate = (_WORKFLOWS / _ESCALATE_WORKFLOW).read_text(encoding="utf-8")
        resolve = (_WORKFLOWS / _RESOLVE_WORKFLOW).read_text(encoding="utf-8")
        assert _shell_list(escalate, "PREFIXES") == _shell_list(resolve, "VALID_PREFIXES")
