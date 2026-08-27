"""AAS Step.7 / Step.8 自然順採番の全実行面契約テスト（FR-WF-AAS-01）。

契約:
    Step 7 = ペルソナカタログ（`Arch-PersonaCatalog` / depends_on=["6"]）
    Step 8 = ペルソナ別共通画面カタログ（`Arch-UI-PersonaScreenList` / depends_on=["7"]）

`hve/workflow_registry.py` を正本とし、Bash / PowerShell registry・Cloud workflow・
Issue Form・Prompt・Template・I/O contract・ユーザーガイドが同じ意味と順序を
宣言することを固定する。Step ID の意味が入れ替わる変更のため、単一面だけの
更新漏れを検出できるよう全面を 1 ファイルで突き合わせる。

Step ID は AAS Step.1 起点化（旧 Step.2 → Step.1 昇格に伴う全 Step 番号の
1 つ繰り上がり）に追従し、ペルソナカタログ / ペルソナ別共通画面カタログの
意味と依存順序自体は変わらない。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from hve.dag_planner import build_dag_plan
from hve.gui.widgets.dag_layout import compute_layout
from hve.workflow_registry import AAS, get_step

_REPO_ROOT = Path(__file__).resolve().parents[2]

PERSONA_CATALOG_STEP = "7"
PERSONA_SCREEN_STEP = "8"
PERSONA_CATALOG_AGENT = "Arch-PersonaCatalog"
PERSONA_SCREEN_AGENT = "Arch-UI-PersonaScreenList"
PERSONA_CATALOG_OUTPUT = "docs/catalog/persona-catalog.md"
PERSONA_SCREEN_OUTPUT = "docs/catalog/persona-screen-catalog.md"

_BASH_REGISTRY = _REPO_ROOT / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"
_PS_REGISTRY = _REPO_ROOT / ".github" / "scripts" / "powershell" / "lib" / "workflow-registry.ps1"
_CLOUD_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "auto-app-selection-reusable.yml"
_ISSUE_FORM = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "app-architecture-design.yml"
_IO_CONTRACTS = _REPO_ROOT / ".github" / "io-contracts"
_PROMPTS = _REPO_ROOT / ".github" / "prompts"
_TEMPLATES = _REPO_ROOT / ".github" / "prompts" / "steps"
_USERS_GUIDE = _REPO_ROOT / "users-guide" / "02-app-architecture-design.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _bash_aas_steps() -> list[dict]:
    match = re.search(
        r"_WORKFLOW_REGISTRY\[aas\]=\$\(cat <<'JSONEOF'\n(?P<json>.*?)\nJSONEOF",
        _read(_BASH_REGISTRY),
        re.S,
    )
    assert match is not None, "bash registry に aas ブロックが見つかりません"
    return json.loads(match.group("json"))["steps"]


_PS_STEP_RE = re.compile(
    r"NewWorkflowStep\s+-Id\s+'(?P<id>[^']+)'\s+-Title\s+'(?P<title>[^']+)'"
    r"\s+-CustomAgent\s+'(?P<agent>[^']+)'"
    r"(?:\s+-DependsOn\s+@\((?P<deps>[^)]*)\))?"
)


def _powershell_aas_steps() -> list[dict]:
    text = _read(_PS_REGISTRY)
    start = text.index("$script:WorkflowRegistryData['aas']")
    end = text.index("$script:WorkflowRegistryData['adfd']")
    steps: list[dict] = []
    for match in _PS_STEP_RE.finditer(text[start:end]):
        raw_deps = match.group("deps") or ""
        steps.append(
            {
                "id": match.group("id"),
                "title": match.group("title"),
                "custom_agent": match.group("agent"),
                "depends_on": re.findall(r"'([^']+)'", raw_deps),
            }
        )
    return steps


class TestRegistryContract:
    """Python registry が Step 7/8 の意味と依存を自然順で宣言すること。"""

    def test_step_7_is_persona_catalog(self) -> None:
        step = get_step("aas", PERSONA_CATALOG_STEP)
        assert step is not None
        assert step.title == "ペルソナカタログ"
        assert step.custom_agent == PERSONA_CATALOG_AGENT
        assert step.depends_on == ["6"]
        assert step.skip_fallback_deps == ["6"]
        assert step.output_paths == [PERSONA_CATALOG_OUTPUT]
        assert step.body_template_path == ".github/prompts/steps/aas/step-7.prompt.md"
        assert "docs/catalog/use-case-catalog.md" in step.required_input_paths
        assert "use_case_catalog" in (step.consumed_artifacts or [])
        assert "persona_catalog" not in (step.consumed_artifacts or [])

    def test_step_8_is_persona_screen_catalog(self) -> None:
        step = get_step("aas", PERSONA_SCREEN_STEP)
        assert step is not None
        assert step.title == "ペルソナ別共通画面カタログ"
        assert step.custom_agent == PERSONA_SCREEN_AGENT
        assert step.depends_on == [PERSONA_CATALOG_STEP]
        assert step.skip_fallback_deps == [PERSONA_CATALOG_STEP]
        assert step.output_paths == [PERSONA_SCREEN_OUTPUT]
        assert step.body_template_path == ".github/prompts/steps/aas/step-8.prompt.md"
        assert PERSONA_CATALOG_OUTPUT in step.required_input_paths
        assert "persona_catalog" in (step.consumed_artifacts or [])

    def test_declaration_order_is_ascending(self) -> None:
        ids = [step.id for step in AAS.steps]
        assert ids.index("6") < ids.index(PERSONA_CATALOG_STEP) < ids.index(PERSONA_SCREEN_STEP)

    def test_dag_waves_end_with_six_seven_eight(self) -> None:
        active = {step.id for step in AAS.steps if not step.is_container}
        plan = build_dag_plan(AAS, active)
        tail = [wave.step_ids for wave in plan.waves][-3:]
        assert tail == [("6",), (PERSONA_CATALOG_STEP,), (PERSONA_SCREEN_STEP,)]

    def test_gui_layout_rank_is_ascending(self) -> None:
        nodes = [
            {"id": step.id, "title": step.title, "depends_on": list(step.depends_on)}
            for step in AAS.steps
            if not step.is_container
        ]
        rank, _ = compute_layout(nodes)
        assert rank["6"] < rank[PERSONA_CATALOG_STEP] < rank[PERSONA_SCREEN_STEP]


class TestIoContractFiles:
    """scoped I/O contract のファイル名と producer が新しい Step 番号を指すこと。"""

    def test_persona_catalog_contract_uses_step_7(self) -> None:
        path = _IO_CONTRACTS / f"{PERSONA_CATALOG_AGENT}--aas--{PERSONA_CATALOG_STEP}.yaml"
        assert path.is_file(), f"{path} が存在しません"
        contract = yaml.safe_load(_read(path))
        assert [entry["path"] for entry in contract["outputs"]] == [PERSONA_CATALOG_OUTPUT]

    def test_persona_screen_contract_uses_step_8(self) -> None:
        path = _IO_CONTRACTS / f"{PERSONA_SCREEN_AGENT}--aas--{PERSONA_SCREEN_STEP}.yaml"
        assert path.is_file(), f"{path} が存在しません"
        contract = yaml.safe_load(_read(path))
        assert [entry["path"] for entry in contract["outputs"]] == [PERSONA_SCREEN_OUTPUT]
        producers = {
            entry["path"]: entry.get("producer")
            for entry in contract["inputs"]
        }
        assert producers[PERSONA_CATALOG_OUTPUT] == (
            f"{PERSONA_CATALOG_AGENT}--aas--{PERSONA_CATALOG_STEP}"
        )

    def test_old_contract_filenames_are_gone(self) -> None:
        stale = [
            _IO_CONTRACTS / f"{PERSONA_CATALOG_AGENT}--aas--{PERSONA_SCREEN_STEP}.yaml",
            _IO_CONTRACTS / f"{PERSONA_SCREEN_AGENT}--aas--{PERSONA_CATALOG_STEP}.yaml",
        ]
        assert [path.name for path in stale if path.exists()] == []

    @pytest.mark.parametrize(
        "contract_name",
        ["Arch-UI-List--aad-web--1.yaml", "Arch-UI-Detail--aad-web--2.1.yaml"],
    )
    def test_aad_web_contracts_reference_new_producer(self, contract_name: str) -> None:
        contract = yaml.safe_load(_read(_IO_CONTRACTS / contract_name))
        producers = {
            entry["path"]: entry.get("producer")
            for entry in contract["inputs"]
        }
        assert producers[PERSONA_SCREEN_OUTPUT] == (
            f"{PERSONA_SCREEN_AGENT}--aas--{PERSONA_SCREEN_STEP}"
        )


class TestTemplatesAndPrompts:
    """Template / Prompt が新しい Step 番号で Agent の役割を宣言すること。"""

    _agent_pattern = re.compile(r"## Custom Agent\s*\n\s*`([^`]+)`")

    def test_step_7_template_is_persona_catalog(self) -> None:
        body = _read(_TEMPLATES / "aas" / "step-7.prompt.md")
        match = self._agent_pattern.search(body)
        assert match is not None
        assert match.group(1).strip() == PERSONA_CATALOG_AGENT
        assert PERSONA_CATALOG_OUTPUT in body

    def test_step_8_template_is_persona_screen(self) -> None:
        body = _read(_TEMPLATES / "aas" / "step-8.prompt.md")
        match = self._agent_pattern.search(body)
        assert match is not None
        assert match.group(1).strip() == PERSONA_SCREEN_AGENT
        assert PERSONA_SCREEN_OUTPUT in body
        assert "Step.7" in body, "Step.8 テンプレートは Step.7 への依存を宣言すること"

    def test_persona_catalog_prompt_declares_step_7(self) -> None:
        body = _read(_PROMPTS / f"{PERSONA_CATALOG_AGENT}.prompt.md")
        assert "AAS Step.7 として" in body
        assert "Step.8（ペルソナ別共通画面カタログ）" in body

    def test_persona_screen_prompt_declares_step_8(self) -> None:
        body = _read(_PROMPTS / f"{PERSONA_SCREEN_AGENT}.prompt.md")
        assert "AAS Step.8 として" in body
        assert "AAS Step.7 出力" in body

    @pytest.mark.parametrize(
        "relative_path",
        [
            "prompts/Arch-UI-List.prompt.md",
            "prompts/Arch-UI-Detail.prompt.md",
            "prompts/steps/aad-web/step-1.prompt.md",
            "prompts/steps/aad-web/step-2.1.prompt.md",
        ],
    )
    def test_downstream_consumers_point_to_step_8(self, relative_path: str) -> None:
        body = _read(_REPO_ROOT / ".github" / relative_path)
        assert "AAS Step.8 で生成" in body
        assert "AAS Step.7 で生成" not in body


class TestBashRegistryParity:
    """Bash registry が Python registry と同じ Step 7/8 契約を宣言すること。"""

    def test_bash_steps_match_python_registry(self) -> None:
        bash_steps = {step["id"]: step for step in _bash_aas_steps()}
        for step_id in (PERSONA_CATALOG_STEP, PERSONA_SCREEN_STEP):
            expected = get_step("aas", step_id)
            assert expected is not None
            actual = bash_steps[step_id]
            assert actual["title"] == expected.title
            assert actual["custom_agent"] == expected.custom_agent
            assert actual["depends_on"] == expected.depends_on
            assert actual["skip_fallback_deps"] == expected.skip_fallback_deps
            assert actual["body_template_path"] == expected.body_template_path

    def test_bash_declaration_order_is_ascending(self) -> None:
        ids = [step["id"] for step in _bash_aas_steps()]
        assert ids.index("6") < ids.index(PERSONA_CATALOG_STEP) < ids.index(PERSONA_SCREEN_STEP)


class TestPowerShellRegistryParity:
    """PowerShell registry が AAS 全 Step を Python registry と同期して宣言すること。"""

    def test_powershell_declares_every_python_step(self) -> None:
        expected = [step for step in AAS.steps if not step.is_container]
        actual = _powershell_aas_steps()
        assert [step["id"] for step in actual] == [step.id for step in expected]

    def test_powershell_step_7_and_8_match_python_registry(self) -> None:
        actual = {step["id"]: step for step in _powershell_aas_steps()}
        for step_id in (PERSONA_CATALOG_STEP, PERSONA_SCREEN_STEP):
            expected = get_step("aas", step_id)
            assert expected is not None
            assert step_id in actual, f"PowerShell registry に Step.{step_id} がありません"
            assert actual[step_id]["title"] == expected.title
            assert actual[step_id]["custom_agent"] == expected.custom_agent
            assert actual[step_id]["depends_on"] == expected.depends_on


class TestCloudWorkflow:
    """Cloud workflow の skip / 起動 / 完了遷移が 6 → 7 → 8 であること。"""

    def test_skip_propagates_from_step_7_to_step_8(self) -> None:
        body = _read(_CLOUD_WORKFLOW)
        pattern = re.compile(
            r'grep\s+-q\s+" 7 ".*?grep\s+-q\s+" 8 ".*?SKIP_STEPS="\$\{SKIP_STEPS\}\s+8"',
            re.S,
        )
        assert pattern.search(body) is not None, (
            "Step.7 スキップ時に Step.8 を強制スキップする分岐が見つかりません"
        )
        assert 'SKIP_STEPS="${SKIP_STEPS} 7"' not in body, (
            "Step.8 スキップを理由に Step.7 をスキップする旧方向が残っています"
        )

    def test_step_1_is_initial_root(self) -> None:
        body = _read(_CLOUD_WORKFLOW)
        assert '"[AAS] Step.1: ソフトウェアアーキテクチャの推薦"' in body
        assert 'render_aas_step_body "1"' in body
        assert 'add_label "${S1_NUM}" "aas:ready"' in body
        assert 'assign_copilot "${S1_NUM}"' in body

    def test_step_issue_titles_use_new_numbers(self) -> None:
        body = _read(_CLOUD_WORKFLOW)
        assert "[AAS] Step.7: ペルソナカタログ" in body
        assert "[AAS] Step.8: ペルソナ別共通画面カタログ" in body

    def test_step_7_activation_requires_use_case_catalog(self) -> None:
        body = _read(_CLOUD_WORKFLOW)
        pattern = re.compile(
            r'activate_with_prereq_check "\$\{S7_NUM\}" "7"(?P<args>(?:\s*\\\s*\n\s*"[^"]+")+)'
        )
        match = pattern.search(body)
        assert match is not None, "Step.7 の起動呼び出しが見つかりません"
        assert "docs/catalog/use-case-catalog.md" in match.group("args")
        assert PERSONA_CATALOG_OUTPUT not in match.group("args")

    def test_step_8_activation_requires_persona_catalog(self) -> None:
        body = _read(_CLOUD_WORKFLOW)
        pattern = re.compile(
            r'activate_with_prereq_check "\$\{S8_NUM\}" "8"(?P<args>(?:\s*\\\s*\n\s*"[^"]+")+)'
        )
        match = pattern.search(body)
        assert match is not None, "Step.8 の起動呼び出しが見つかりません"
        assert PERSONA_CATALOG_OUTPUT in match.group("args")


class TestIssueForm:
    """Issue Form の説明・依存・チェックボックスが自然順であること。"""

    def test_step_table_rows_use_new_meaning(self) -> None:
        body = _read(_ISSUE_FORM)
        assert "| **Step.7** | ペルソナカタログ |" in body
        assert "| **Step.8** | ペルソナ別共通画面カタログ |" in body

    def test_dependency_chain_is_ascending(self) -> None:
        body = _read(_ISSUE_FORM)
        assert "Step.6 → Step.7 → Step.8" in body
        assert "Step.8 → Step.7" not in body

    def test_checkbox_labels_declare_new_dependencies(self) -> None:
        body = _read(_ISSUE_FORM)
        assert '- label: "Step.7 — ペルソナカタログ ※ Step.6 が必須"' in body
        assert '- label: "Step.8 — ペルソナ別共通画面カタログ ※ Step.7 が必須"' in body


class TestUsersGuide:
    """ユーザーガイドが Step 8/9 を含む現行構成を説明すること。"""

    def test_guide_documents_persona_steps(self) -> None:
        body = _read(_USERS_GUIDE)
        for token in (
            PERSONA_CATALOG_AGENT,
            PERSONA_SCREEN_AGENT,
            PERSONA_CATALOG_OUTPUT,
            PERSONA_SCREEN_OUTPUT,
        ):
            assert token in body, f"ユーザーガイドに {token} の説明がありません"

    def test_guide_has_no_stale_step_count(self) -> None:
        body = _read(_USERS_GUIDE)
        assert "Step.1〜Step.7、8ステップ構成" not in body
        assert "Step.1〜Step.7 の8ステップ" not in body
