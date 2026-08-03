"""Azure external Skill のJIT routing共通規約を固定する契約テスト。"""

from __future__ import annotations

import json
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PREAMBLE = _REPO_ROOT / ".github" / "skills" / "agent-common-preamble" / "SKILL.md"
_ROUTING = _REPO_ROOT / ".github" / "skills" / "_routing" / "README.md"
_MANIFEST = _REPO_ROOT / "hve" / "skill_manifest.json"


def test_common_preamble_declares_jit_exact_directory_and_missing_policy() -> None:
    """共通規約は全外部rootの公開と未導入時writeを禁止する。"""
    text = _PREAMBLE.read_text(encoding="utf-8")

    for required_text in (
        "Azure External Skill の JIT ルーティング（必須）",
        "`hve/skill_manifest.json` の `required_skills` / `optional_skills` を正本",
        "`~/.agents/skills` 全体またはカテゴリ directory を渡して探索させてはならない",
        "選定済み Azure サービスと実行操作に一致する candidate だけを読込み・利用",
        "未導入 Skill の Azure write 許可や resource 操作の根拠にはしない",
    ):
        assert required_text in text

    assert "設計・read-only 調査・review は、Microsoft Learn MCP を使い" in text
    assert "Azure write を実行せず block する" in text
    assert "generic な `azure-prepare` / `azure-deploy`" in text
    assert "read-only readiness review 候補として明示されていない `azure-validate`" in text


def test_routing_table_distinguishes_catalog_from_active_jit_session_routing() -> None:
    """routing表はカタログとactive Stepのexact routingを混同しない。"""
    text = _ROUTING.read_text(encoding="utf-8")

    for required_text in (
        "Active HVE の JIT ルーティング方針（規範）",
        "Skill カタログであり、session に全 Azure Skill を無条件にロードする一覧ではない",
        "`hve/skill_manifest.json` の `required_skills` / `optional_skills` を正本",
        "`~/.agents/skills` 全体は渡さない",
        "選定サービス・操作に一致しない candidate は読まない",
        "Azure write は block",
        "`azure-prepare` と `azure-deploy` は",
        "`azure-validate` はread-only readiness reviewに限り",
        "`asdw-web:5.2` / `adfdv:4.2`",
    ):
        assert required_text in text


def test_aagd_foundry_jit_policy_agrees_with_required_skill_manifest() -> None:
    """AAGD固定Foundry Stepはmeta skillとpinned MCP境界を共有する。"""
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    combined_policy = (
        _PREAMBLE.read_text(encoding="utf-8")
        + "\n"
        + _ROUTING.read_text(encoding="utf-8")
    )

    assert manifest["required_skills"]["aagd"] == {
        "2.3": ["microsoft-foundry"],
        "3": ["microsoft-foundry"],
    }
    assert manifest["optional_skills"]["aagd"] == {
        "2.3": ["azure-ai", "entra-agent-id"],
        "3": ["azure-diagnostics"],
    }
    assert "AAGD `2.3` / `3`" in combined_policy
    assert "`microsoft-foundry` meta skill" in combined_policy
    assert "repository-pinned `azure` と `microsoft-learn` MCP" in combined_policy