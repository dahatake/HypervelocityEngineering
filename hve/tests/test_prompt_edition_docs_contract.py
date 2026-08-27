"""FR-PROMPT-10 — Prompt 版 Agent Skill と利用者文書 coverage の契約テスト。

Workflow の全件は [hve/workflow_registry.py] を正本とし、本テストへ件数を
固定記述しない（FR-PROMPT-10 の「変動値を固定記述しない」に従う）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from hve.workflow_registry import list_workflows

_SKILL = Path(".github/skills/hve-prompt-edition/SKILL.md")
_COPILOT_INSTRUCTIONS = Path(".github/copilot-instructions.md")
_TASK_DAG_SKILL = Path(".github/skills/task-dag-planning/SKILL.md")
_TASK_DAG_DETAIL = Path(".github/skills/task-dag-planning/references/detail.md")
_TASK_DAG_RULES = Path(
    ".github/skills/task-dag-planning/references/dag-rules-detail.md"
)
_SKILL_EVAL = Path(".github/skills/_evals/hve-prompt-edition.eval.yaml")
_QUICK_START = Path("users-guide/hve-prompt-getting-started.md")
_PROMPTS_DIR = Path("users-guide/prompts")
_INDEX = _PROMPTS_DIR / "README.md"
_CROSS = _PROMPTS_DIR / "cross-workflow.md"
_CUSTOM_INPUTS = _PROMPTS_DIR / "custom-inputs.md"
_INTEGRATION_INDEX = Path("tests/prompt-version/README.md")
_PLAN_GATE = Path("tests/prompt-version/02-plan-and-approval-gate.md")
_SKILL_BEHAVIOR = Path("tests/prompt-version/06-agent-skill-behavior.md")
_E2E_SMOKE = Path("tests/prompt-version/08-e2e-smoke.md")
_REQUIREMENT_DEFINITION = Path("hve-dev/requirement-definition.md")
_REQUIREMENT_MAPPING = Path("hve-dev/requirement-test-mapping.md")

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


def _h2_body(path: Path, heading: str) -> str:
    text = _read(path)
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"{path} に見出し {heading!r} が無い"
    body = match.group("body").strip()
    assert body, f"{path} の見出し {heading!r} が空"
    return body


def _between(path: Path, start: str, end: str) -> str:
    text = _read(path)
    assert start in text, f"{path} に開始マーカー {start!r} が無い"
    assert end in text, f"{path} に終了マーカー {end!r} が無い"
    return text.split(start, 1)[1].split(end, 1)[0]


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


class TestApprovedFullExecutionContract:
    """FR-PROMPT-10 — 承認済み Prompt 版は既存 Orchestrator へ完全委譲する。"""

    def test_repository_instructions_define_a_narrow_delegation_exception(self):
        body = _between(
            _COPILOT_INSTRUCTIONS,
            "  - **Prompt 版承認後の委譲（限定例外）**:",
            "  - **Cloud Agent Orchestrator 配下モード**",
        )
        for token in (
            "明示承認",
            "`hve prompt run`",
            "`task_scope=multi`",
            "`context_size=large`",
            "対象成果物を直接実装・編集してはならない",
            "再plan・再提示・再承認",
            "`output_paths` gate",
        ):
            assert token in body
        assert re.search(r"HVE が.*SHA-256.*一致を確認", body)

    def test_task_dag_skill_routes_to_the_controller_exception(self):
        body = _h2_body(_TASK_DAG_SKILL, "Prompt Edition controller 例外")
        for token in (
            "明示承認",
            "SHA-256",
            "`hve prompt run`",
            "`task_scope=multi`",
            "`context_size=large`",
            "直接実装",
            "`output_paths`",
            "再plan",
        ):
            assert token in body

    def test_task_dag_detail_explains_why_delegation_can_continue(self):
        body = _h2_body(_TASK_DAG_DETAIL, "Prompt Edition controller 例外")
        for token in (
            "`task_scope=multi`",
            "`context_size=large`",
            "明示承認",
            "`hve prompt run`",
            "直接実装",
            "`output_paths`",
            "再plan",
        ):
            assert token in body
        assert re.search(r"HVE が.*SHA-256.*一致を確認", body)

    def test_task_dag_rules_limit_the_exception_to_approved_delegation(self):
        body = _h2_body(_TASK_DAG_RULES, "Prompt Edition controller 例外")
        for token in (
            "明示承認",
            "SHA-256",
            "`hve prompt run`",
            "`task_scope=multi`",
            "`context_size=large`",
            "直接実装",
            "`output_paths`",
            "再plan",
        ):
            assert token in body
        assert "この 3 条件をすべて満たす" not in body

    def test_skill_continues_after_approval_even_for_multi_or_large_work(self):
        body = _h2_body(_SKILL, "承認後の完全実行")
        for token in (
            "明示承認",
            "`task_scope=multi`",
            "`context_size=large`",
            "`hve prompt run`",
            "`output_paths`",
            "選択済み Workflow / Step",
            "最初の失敗",
            "未選択 Workflow",
            "既存の認証・権限・Azure・QA・デプロイ承認",
        ):
            assert token in body
        assert re.search(r"HVE が.*SHA-256.*一致を確認", body)
        assert "Prompt Edition controller" in body
        assert re.search(r"controller.*成果物.*直接実装・編集しない", body)
        assert re.search(r"(?:再承認|承認を取り直す)", body)

    def test_quick_start_explains_full_execution_and_gate_boundaries(self):
        body = _h2_body(_QUICK_START, "承認後の完全実行範囲")
        assert re.search(r"`plan\.md`.*`subissues\.md`.{0,80}(?:終わ|終了|停止)", body)
        assert "`output_paths`" in body
        assert "実行完了時点で存在" in body
        assert re.search(r"(?:選択済み|あなたが選んだ) Workflow / Step", body)
        assert "最初の失敗" in body
        assert "自動 rollback" in body
        assert "controller" in body and "直接編集" in body
        assert "実行時に再計算" in body
        assert "SHA-256 と現在の HEAD が一致" not in body
        assert "既存の認証・権限・Azure・QA・デプロイ承認ゲート" in body

    def test_requirement_and_mapping_name_orchestrate_children_precisely(self):
        requirement = _between(
            _REQUIREMENT_DEFINITION,
            "### 5.20 Prompt 版（自然言語 Prompt からの計画と実行）",
            "### 5.21 ローカル 3 面の設定パリティ",
        )
        mapping = _between(
            _REQUIREMENT_MAPPING,
            "### FR-PROMPT-04",
            "### FR-PROMPT-05",
        )
        skill_intro = _between(_SKILL, "`hve prompt run` は", "## 利用者との対話")
        assert "`orchestrate` 子プロセスを 1 つも起動してはならない" in requirement
        assert "`orchestrate` 子プロセス 0 件" in mapping
        assert "`orchestrate` 子プロセスを 1 つも起動せずに停止" in skill_intro

    def test_runtime_contracts_are_traced_from_the_v277_mapping(self):
        body = _between(
            _REQUIREMENT_MAPPING,
            "### FR-PROMPT-10",
            "### FR-LOCAL-SURFACE-01",
        )
        for path in (
            "hve/tests/test_prompt_cli.py",
            "hve/tests/test_prompt_execution.py",
            "hve/tests/test_runner_split_required_guard.py",
        ):
            assert path in body


class TestAdversarialReviewCorrections:
    def test_mutating_integration_cases_require_an_isolated_worktree(self):
        text = _read(_INTEGRATION_INDEX)
        assert "書き込みを伴うケース" in text
        assert "専用の隔離 worktree" in text
        assert "未コミット差分を把握済み" not in text

    def test_plan_gate_uses_orchestrate_specific_evidence(self):
        text = _read(_PLAN_GATE)
        assert "子 `orchestrate`" in text
        assert "代用できる" not in text
        assert "新しい commit を作って" not in text
        assert "TestPromptRunApprovalGate" in text
        assert "TestRunPlan::test_fail_fast_stops_subsequent_workflows" in text

    def test_plan_gate_contains_a_fixed_safe_request(self):
        text = _read(_PLAN_GATE)
        assert '"workflow_id": "ard"' in text
        assert '"steps": ["1"]' in text
        assert '"company_name": "Prompt Gate Test"' in text
        assert "request の `goal` だけ" in text
        assert "保存設定 `strict` を `false` から `true`" in text

    def test_skill_behavior_preserves_approval_context_and_bounds_scope(self):
        text = _read(_SKILL_BEHAVIOR)
        assert "A2 は A と同じセッション" in text
        assert "曖昧な同意" in text and "計画を提示した同じセッション" in text
        assert "Workflow / Step 数を増やして" not in text
        assert "ard=1 / aas=1" in text
        assert "終了コード 0" in text
        assert "canonical `output_paths`" in text

    def test_skill_behavior_does_not_repeat_mutating_runs(self):
        text = _read(_SKILL_BEHAVIOR)
        assert "A2 / A3 の mutating run は各 1 回" in text
        assert "B / C / D" in text and "最低 2 回" in text

    def test_e2e_uses_a_fixed_safe_fixture_and_safe_cleanup(self):
        text = _read(_E2E_SMOKE)
        assert "専用の隔離 worktree" in text
        assert "Workflow `ard` の Step `1`" in text
        assert "docs/company-business-recommendation.md" in text
        assert "git -C <元リポジトリ> worktree remove" in text
        assert "生成されたファイルを個別に削除" not in text
        assert "argv だけ" in text

    def test_approved_eval_requires_a_plan_in_the_same_context(self):
        data = yaml.safe_load(_read(_SKILL_EVAL))
        case = next(
            item
            for item in data["test_cases"]
            if item["id"] == "approved-multi-large-delegates-full-run"
        )
        assert "同じセッション" in case["input"]
        assert "plan SHA-256" in case["input"]

    def test_resolved_macos_conflict_is_not_listed_as_open(self):
        text = _read(_INTEGRATION_INDEX)
        assert "test_macos_cocoa_smoke.py" not in text


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
