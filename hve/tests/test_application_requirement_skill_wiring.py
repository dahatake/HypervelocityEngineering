"""FR-APPREQ-05: APP要求トレーサビリティSkillと9 Workflow配線RED。"""

from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SKILL = _REPO / ".github" / "skills" / "application-requirement-traceability" / "SKILL.md"
_PREAMBLE = _REPO / ".github" / "skills" / "agent-common-preamble" / "SKILL.md"
_MANIFEST = _REPO / "hve" / "skill_manifest.json"
_TARGETS = {
    "aas", "ada", "aad-web", "asdw-web", "adfd", "adfdv", "aag", "aagd", "aar"
}


def test_skill_exists_and_reuses_existing_scope_and_search_skills() -> None:
    text = _SKILL.read_text(encoding="utf-8")
    assert "name: application-requirement-traceability" in text
    assert "app-scope-resolution" in text
    assert "markdown-query" in text
    assert "docs/architectural-requirements-app-NNN.md" in text
    assert "要求書全文" in text
    assert "常時" in text
    assert "fail-closed" in text


def test_agent_common_preamble_routes_generated_app_work_to_the_skill() -> None:
    text = _PREAMBLE.read_text(encoding="utf-8")
    assert text.count("## 生成アプリケーション要求トレーサビリティ") == 1
    section = text.split("## 生成アプリケーション要求トレーサビリティ", 1)[1]
    assert "application-requirement-traceability" in section
    assert "要求定義書全文を既定の入力にしない" in section


def test_all_nine_workflows_require_the_skill_by_default() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    defaults = manifest["workflow_defaults"]
    actual = {
        workflow
        for workflow, skills in defaults.items()
        if "application-requirement-traceability" in skills
    }
    assert actual == _TARGETS
