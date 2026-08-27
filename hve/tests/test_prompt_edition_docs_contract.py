"""FR-PROMPT-10 — Prompt 版 Agent Skill と利用者文書 coverage の契約テスト。

Workflow の全件は [hve/workflow_registry.py] を正本とし、本テストへ件数を
固定記述しない（FR-PROMPT-10 の「変動値を固定記述しない」に従う）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hve.workflow_registry import list_workflows

_SKILL = Path(".github/skills/hve-prompt-edition/SKILL.md")
_QUICK_START = Path("users-guide/hve-prompt-getting-started.md")
_PROMPTS_DIR = Path("users-guide/prompts")
_INDEX = _PROMPTS_DIR / "README.md"
_CROSS = _PROMPTS_DIR / "cross-workflow.md"
_CUSTOM_INPUTS = _PROMPTS_DIR / "custom-inputs.md"

_SNIPPET_FILES = [
    _PROMPTS_DIR / "requirements-architecture.md",
    _PROMPTS_DIR / "web-application.md",
    _PROMPTS_DIR / "dataflow.md",
    _PROMPTS_DIR / "ai-agent.md",
    _PROMPTS_DIR / "knowledge-management.md",
    _PROMPTS_DIR / "design-doc-ingestion.md",
    _PROMPTS_DIR / "source-code-documentation.md",
]

_ALL_DOCS = [_QUICK_START, _INDEX, _CROSS, _CUSTOM_INPUTS, *_SNIPPET_FILES]


def _read(path: Path) -> str:
    assert path.exists(), f"未作成: {path}"
    return path.read_text(encoding="utf-8")


class TestSkill:
    def test_skill_exists(self):
        assert _SKILL.exists(), f"未作成: {_SKILL}"

    def test_skill_has_frontmatter_name_and_description(self):
        text = _read(_SKILL)
        assert text.startswith("---\n")
        head = text.split("---", 2)[1]
        assert "name: hve-prompt-edition" in head
        assert "description:" in head
        assert "USE FOR:" in head and "DO NOT USE FOR:" in head and "WHEN:" in head

    def test_skill_declares_plan_before_run(self):
        text = _read(_SKILL)
        assert "hve prompt plan" in text
        assert "hve prompt run" in text
        assert "--expected-sha256" in text

    def test_skill_forbids_guessing(self):
        text = _read(_SKILL)
        assert "推測" in text

    def test_skill_forbids_asking_the_user_to_type_commands(self):
        # FR-PROMPT-10: CLI 起動と hash 転記は Agent が代行する。
        text = _read(_SKILL)
        assert "利用者へコマンド" in text

    def test_skill_is_routed(self):
        routing = Path(".github/skills/_routing/README.md").read_text(encoding="utf-8")
        assert "hve-prompt-edition" in routing


class TestQuickStart:
    def test_exists_and_points_at_gui_settings(self):
        text = _read(_QUICK_START)
        assert "設定" in text
        assert "hve prompt plan" in text

    def test_does_not_promise_a_new_gui_tab(self):
        text = _read(_QUICK_START)
        assert "新しい GUI タブ" not in text

    def test_states_cloud_is_out_of_scope(self):
        text = _read(_QUICK_START)
        assert "Cloud" in text


class TestSnippetIndex:
    def test_index_links_every_snippet_file(self):
        text = _read(_INDEX)
        for path in [*_SNIPPET_FILES, _CROSS, _CUSTOM_INPUTS]:
            assert path.name in text, f"索引に {path.name} へのリンクが無い"


class TestWorkflowCoverage:
    def test_every_registry_workflow_has_a_copyable_prompt(self):
        corpus = "\n".join(_read(p) for p in _SNIPPET_FILES)
        missing = [w.id for w in list_workflows() if f"`{w.id}`" not in corpus]
        assert not missing, f"Prompt 例が無い Workflow: {missing}"

    def test_every_snippet_file_has_a_fenced_prompt_block(self):
        for path in _SNIPPET_FILES:
            assert "```" in _read(path), f"{path} に貼り付け用ブロックが無い"

    def test_cross_workflow_example_uses_dependency_order(self):
        text = _read(_CROSS)
        assert "`aas`" in text and "`aad-web`" in text

    def test_custom_inputs_example_declares_the_v1_limits(self):
        text = _read(_CUSTOM_INPUTS)
        assert "canonical" in text
        assert "glob" in text
        assert "コピー" in text


class TestPlanBeforeRun:
    @pytest.mark.parametrize("path", _ALL_DOCS, ids=lambda p: p.name)
    def test_each_document_requires_explicit_approval(self, path: Path):
        text = _read(path)
        assert "plan" in text, f"{path} に plan 提示の記載が無い"
        assert "承認" in text, f"{path} に明示承認の記載が無い"


class TestNoStaleCounts:
    _COUNT_PATTERN = re.compile(r"(?:全|計)\s*\d+\s*(?:件|個)の(?:Prompt|プロンプト|例)")

    @pytest.mark.parametrize("path", _ALL_DOCS, ids=lambda p: p.name)
    def test_no_fixed_prompt_counts(self, path: Path):
        text = _read(path)
        hits = self._COUNT_PATTERN.findall(text)
        assert not hits, f"{path} に固定件数の記述: {hits}"


class TestRelativeLinks:
    _LINK = re.compile(r"\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)")

    @pytest.mark.parametrize("path", _ALL_DOCS, ids=lambda p: p.name)
    def test_relative_links_resolve(self, path: Path):
        text = _read(path)
        broken = []
        for target in self._LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            candidate = (path.parent / target).resolve()
            if not candidate.exists() and not Path(target).exists():
                broken.append(target)
        assert not broken, f"{path} の未解決リンク: {broken}"


class TestExistingGuidesArePlumbed:
    def test_root_readme_lists_the_prompt_surface(self):
        text = Path("README.md").read_text(encoding="utf-8")
        assert "Prompt 版" in text
        assert _QUICK_START.name in text

    def test_prompt_examples_page_points_at_the_new_index(self):
        text = Path("users-guide/prompt-examples.md").read_text(encoding="utf-8")
        assert "prompts/README.md" in text


class TestRequirementIsDeclared:
    def test_fr_prompt_10_is_declared(self):
        text = Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
        assert "**FR-PROMPT-10**" in text


class TestNaturalLanguageOnly:
    """FR-PROMPT-10 — 利用者は自然言語だけで計画取得から実行までを完了できる。"""

    _PASTE_BLOCK = re.compile(r"```text\n(.*?)```", re.S)

    @pytest.mark.parametrize(
        "path", [_INDEX, _CROSS, _CUSTOM_INPUTS, *_SNIPPET_FILES], ids=lambda p: p.name
    )
    def test_paste_blocks_have_no_cli_subcommand(self, path: Path):
        leaked = [b for b in self._PASTE_BLOCK.findall(_read(path)) if "hve prompt" in b]
        assert not leaked, f"{path} の貼り付け用ブロックに CLI サブコマンド名がある: {leaked}"

    def test_quick_start_states_the_agent_runs_the_commands(self):
        text = _read(_QUICK_START)
        assert "コマンドを打つ必要はありません" in text
