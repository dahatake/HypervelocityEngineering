"""Cloud 再利用 YAML が SSoT（`workflow-registry.sh`）と同じ Step を生成すること。

再利用 YAML は SSoT を読まずハードコードしているため、
定義と実行がずれていても実行するまで気づけない。
生成される Issue タイトルから Step ID を取り出して突き合わせる。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

from hve.dag_parity import extract_bash_workflow_steps
from hve.workflow_registry import get_workflow

_REPO = Path(__file__).resolve().parents[2]
_BASH_REGISTRY = _REPO / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"
_REQUIREMENTS = _REPO / "hve-dev" / "requirement-definition.md"
_DISPATCHER = _REPO / ".github" / "workflows" / "auto-orchestrator-dispatcher.yml"

# 再利用 YAML と workflow_id の対応。未統一のものは _PENDING に置く。
_UNIFIED = {
    "auto-ai-agent-design-reusable.yml": ("aag", "AAG"),
    "auto-ai-agent-dev-reusable.yml": ("aagd", "AAGD"),
    "auto-agentic-retrieval-reusable.yml": ("aar", "AAR"),
    "auto-agent-data-architecture-reusable.yml": ("ada", "ADA"),
    "auto-app-dev-microservice-web-reusable.yml": ("asdw-web", "ASDW-WEB"),
    "auto-dataflow-dev-reusable.yml": ("adfdv", "ADFDV"),
}
_PENDING: dict[str, tuple[str, str]] = {}

_FR_CLOUD_20_MAPPING = {
    "ARD": "auto-requirement-definition-reusable.yml",
    "AAS": "auto-app-selection-reusable.yml",
    "AAD-WEB": "auto-app-detail-design-web-reusable.yml",
    "ASDW-WEB": "auto-app-dev-microservice-web-reusable.yml",
    "ADFD": "auto-dataflow-design-reusable.yml",
    "ADFDV": "auto-dataflow-dev-reusable.yml",
    "ADA": "auto-agent-data-architecture-reusable.yml",
    "AAG": "auto-ai-agent-design-reusable.yml",
    "AAGD": "auto-ai-agent-dev-reusable.yml",
    "AAR": "auto-agentic-retrieval-reusable.yml",
    "ADOC": "auto-app-documentation-reusable.yml",
    "AKM": "auto-knowledge-management-reusable.yml",
}


def test_fr_cloud_20_matches_dispatcher_reusable_jobs() -> None:
    requirement_text = _REQUIREMENTS.read_text(encoding="utf-8")
    section = requirement_text.split("- **FR-CLOUD-20**:", 1)[1].split(
        "- **FR-CLOUD-21**:", 1
    )[0]
    declared = dict(re.findall(r"^  - `([^`]+)` → `([^`]+)`$", section, re.MULTILINE))
    assert declared == _FR_CLOUD_20_MAPPING

    dispatcher = yaml.safe_load(_DISPATCHER.read_text(encoding="utf-8"))
    actual: dict[str, str] = {}
    for job in dispatcher["jobs"].values():
        uses = str(job.get("uses", ""))
        if not re.fullmatch(r"\./\.github/workflows/auto-.*-reusable\.yml", uses):
            continue
        targets = re.findall(
            r"needs\.detect\.outputs\.target == '([^']+)'", str(job.get("if", ""))
        )
        assert len(targets) == 1, f"dispatch targetを一意に抽出できません: {uses}"
        actual[targets[0]] = Path(uses).name
    assert actual == _FR_CLOUD_20_MAPPING


def _workflow(workflow_id: str):
    workflow = get_workflow(workflow_id)
    assert workflow is not None, f"workflow が未登録: {workflow_id}"
    return workflow


def _created_step_ids(workflow_file: str, prefix: str) -> set[str]:
    """YAML が作る Step ID。コンテナ Issue は SSoT に存在しないため除く。"""
    text = (_REPO / ".github" / "workflows" / workflow_file).read_text(encoding="utf-8")
    pattern = rf'"\[{re.escape(prefix)}\] Step\.([0-9A-Z.]+): ([^"$]*)'
    return {
        step_id
        for step_id, title in re.findall(pattern, text)
        if "（コンテナ）" not in title
    }


def _created_container_ids(workflow_file: str, prefix: str) -> set[str]:
    text = (_REPO / ".github" / "workflows" / workflow_file).read_text(encoding="utf-8")
    pattern = rf'"\[{re.escape(prefix)}\] Step\.([0-9A-Z.]+): ([^"$]*)'
    return {
        step_id
        for step_id, title in re.findall(pattern, text)
        if "（コンテナ）" in title
    }


@pytest.mark.parametrize(
    "workflow_file,workflow_id,prefix",
    [(f, w, p) for f, (w, p) in _UNIFIED.items()],
)
class TestUnifiedWorkflows:
    def test_yaml_creates_exactly_the_registry_steps(
        self, workflow_file: str, workflow_id: str, prefix: str
    ):
        created = _created_step_ids(workflow_file, prefix)
        declared = set(extract_bash_workflow_steps(_BASH_REGISTRY, workflow_id))
        assert created == declared, (
            f"{workflow_file}: yaml_only={sorted(created - declared)} "
            f"registry_only={sorted(declared - created)}"
        )

    def test_yaml_matches_hve_registry_too(
        self, workflow_file: str, workflow_id: str, prefix: str
    ):
        """CLI/GUI 側の registry とも一致すること。"""
        created = _created_step_ids(workflow_file, prefix)
        hve = {
            s.id for s in _workflow(workflow_id).steps if not s.is_container
        }
        assert created == hve

    def test_custom_agents_match_registry(
        self, workflow_file: str, workflow_id: str, prefix: str
    ):
        """番号が合っていても実行 Agent が違えば意味がない。"""
        text = (_REPO / ".github" / "workflows" / workflow_file).read_text(
            encoding="utf-8"
        )
        expected = {
            s.custom_agent
            for s in _workflow(workflow_id).steps
            if not s.is_container and s.custom_agent
        }
        for agent in expected:
            assert agent in text, f"{workflow_file} に {agent} が無い"

    def test_no_stale_agents_from_the_copied_pipeline(
        self, workflow_file: str, workflow_id: str, prefix: str
    ):
        """複製元（AAD-WEB / ASDW-WEB）固有の Agent が残っていないこと。

        printf 書式内では改行が literal `\\n` なので、その形で拾う。
        抽出 0 件だと検査が自明に通るため、件数も確認する。
        """
        text = (_REPO / ".github" / "workflows" / workflow_file).read_text(
            encoding="utf-8"
        )
        allowed = {
            s.custom_agent
            for s in _workflow(workflow_id).steps
            if not s.is_container and s.custom_agent
        }
        used = set(re.findall(r"## Custom Agent\\n`([A-Za-z0-9\-]+)`", text))
        if not used:
            template_dir = _REPO / ".github" / "prompts" / "steps" / workflow_id
            for template in template_dir.glob("step-*.md"):
                used.update(
                    re.findall(
                        r"## Custom Agent\s*\n`([A-Za-z0-9\-]+)`",
                        template.read_text(encoding="utf-8"),
                    )
                )
        assert used, "Custom Agent を 1 件も抽出できていない（検査が無効）"
        assert used <= allowed, f"複製元の Agent が残存: {sorted(used - allowed)}"

    def test_container_ids_do_not_collide_with_step_ids(
        self, workflow_file: str, workflow_id: str, prefix: str
    ):
        """コンテナ Issue の番号が実 Step と衝突しないこと。

        衝突すると `STEP_MATCH` が同じ ID を返し、遷移が誤発火する。
        """
        containers = _created_container_ids(workflow_file, prefix)
        steps = _created_step_ids(workflow_file, prefix)
        assert containers.isdisjoint(steps), (
            f"{workflow_file}: コンテナと Step の ID が衝突 {sorted(containers & steps)}"
        )



def test_asdw_web_state_transition_dependencies_match_registry() -> None:
    """Cloud 状態遷移の依存表を registry の非コンテナ Step と一致させる。"""
    text = (_REPO / ".github" / "workflows" / "auto-app-dev-microservice-web-reusable.yml").read_text(
        encoding="utf-8"
    )
    match = re.search(r"^\s*DEPS = (\{.*?^\s*\})", text, re.MULTILINE | re.DOTALL)
    assert match, "ASDW-WEB の状態遷移 DEPS が見つかりません"
    cloud_deps = ast.literal_eval(match.group(1))
    registry_deps = {
        step.id: list(step.depends_on)
        for step in _workflow("asdw-web").steps
        if not step.is_container
    }
    assert cloud_deps == registry_deps


def test_asdw_web_inline_bodies_have_no_legacy_step_ids() -> None:
    text = (_REPO / ".github" / "workflows" / "auto-app-dev-microservice-web-reusable.yml").read_text(
        encoding="utf-8"
    )
    legacy_ids = ["Step.2.3TC", "Step.2.7T", "Step.2.7TC", "Step.2.8", "Step.2.9", "Step.2.10", "Step.3.0TC"]
    assert [step_id for step_id in legacy_ids if step_id in text] == []


def test_aar_root_done_event_does_not_reenter_step_transition() -> None:
    text = (_REPO / ".github" / "workflows" / "auto-agentic-retrieval-reusable.yml").read_text(
        encoding="utf-8"
    )
    assert '"${ISSUE_TITLE}" =~ ^\\[AAR\\]\\ Step\\.[1-7]:' in text
    assert 'echo "mode=skip" >> "${GITHUB_OUTPUT}"' in text


def test_aar_no_policy_skips_step_creation_and_uses_run_scoped_work() -> None:
    text = (_REPO / ".github" / "workflows" / "auto-agentic-retrieval-reusable.yml").read_text(
        encoding="utf-8"
    )
    assert 'if [[ "${ENABLE_AGENTIC_RETRIEVAL}" == "no" ]]; then' in text
    assert 'add_label "${ROOT_ISSUE}" "aar:done"' in text
    assert "work/run/cloud-aar-" in text
    assert "/artifacts/" in text

class TestAkmCloudParity:
    """AKM の Cloud 経路が `hve/workflow_registry.py` と同じ Step を作ること。

    AKM は Bash registry (`workflow-registry.sh`) に未登録で Cloud YAML が
    ハードコードしているため、`TestUnifiedWorkflows` ではなく hve registry
    のみと突き合わせる。
    """

    _WORKFLOW_FILE = "auto-knowledge-management-reusable.yml"
    _PREFIX = "AKM"

    @staticmethod
    def _text() -> str:
        return (
            _REPO / ".github" / "workflows" / TestAkmCloudParity._WORKFLOW_FILE
        ).read_text(encoding="utf-8")

    def test_yaml_creates_exactly_the_hve_registry_steps(self) -> None:
        created = _created_step_ids(self._WORKFLOW_FILE, self._PREFIX)
        declared = {s.id for s in _workflow("akm").steps if not s.is_container}
        assert created == declared, (
            f"yaml_only={sorted(created - declared)} "
            f"registry_only={sorted(declared - created)}"
        )

    def test_custom_agents_match_registry(self) -> None:
        text = self._text()
        expected = {
            s.custom_agent
            for s in _workflow("akm").steps
            if not s.is_container and s.custom_agent
        }
        for agent in expected:
            assert agent in text, f"{self._WORKFLOW_FILE} に {agent} が無い"

    def test_step1_completion_starts_step2(self) -> None:
        """Step.1 完了で Root を done にせず Step.2 を起動すること。"""
        text = self._text()
        assert "AKM はステップが 1 つのみ" not in text
        assert "[AKM] Step.2" in text
        assert 'if [[ "${STEP_MATCH}" == "1" ]]; then' in text

    def test_only_last_step_marks_root_done(self) -> None:
        """Root の akm:done は最終 Step（Step.2）完了時のみ付与すること。"""
        text = self._text()
        transition = text.split("# ---- 依存関係マップに基づき処理 ----", 1)
        assert len(transition) == 2, "状態遷移セクションが見つかりません"
        body = transition[1]
        root_done_index = body.index('add_label "${ROOT_ISSUE}" "akm:done"')
        step2_index = body.index('"${STEP_MATCH}" == "2"')
        assert step2_index < root_done_index, (
            "Root への akm:done 付与が Step.2 判定より前にある"
        )


class TestPendingWorkflows:
    """未統一のものは「未統一である」ことを記録として固定する。

    黙って放置すると、統一済みと誤認される。
    """

    def test_all_reusable_workflows_are_unified(self):
        """全て統一されたことを固定する。未統一を戻したら落ちる。"""
        assert not _PENDING, f"未統一が残っている: {sorted(_PENDING)}"


class TestAagStepContents:
    """AAG の各 Step が意図した Agent と依存を持つこと。"""

    @pytest.fixture(scope="class")
    @classmethod
    def text(cls) -> str:
        return (
            _REPO / ".github" / "workflows" / "auto-ai-agent-design-reusable.yml"
        ).read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "step_id,title,agent",
        [
            ("1", "AI Agent アプリケーション定義", "Arch-AIAgentDesign-Step1"),
            ("2", "AI Agent 粒度設計", "Arch-AIAgentDesign-Step2"),
            ("3", "AI Agent 詳細設計", "Arch-AIAgentDesign-Step3"),
        ],
    )
    def test_step_title_and_agent(self, text, step_id, title, agent):
        assert f"[AAG] Step.{step_id}: {title}" in text
        assert agent in text

    def test_transition_chain_is_1_to_2_to_3(self, text):
        assert '"1")' in text and '"2")' in text and '"3")' in text
        assert r"\[AAG\] Step\.2:" in text
        assert r"\[AAG\] Step\.3:" in text

    def test_step_3_ends_the_workflow(self, text):
        """最終 Step が Self-Improve へ渡らないと Root が閉じない。"""
        body = text.split('            "3")', 1)[1].split("\n              ;;", 1)[0]
        assert "mark_root_self_improve_ready" in body

    def test_step_1_is_the_entry_point(self, text):
        """起動対象が Step.1 であること。"""
        assert 'CA=$(extract_custom_agent "${BODY_S1}")' in text

    def test_no_orphan_variables(self, text):
        """削除した Step の変数が残ると `set -u` で落ちる。"""
        for var in ("S11_NUM", "S71_NUM", "S81_NUM", "BODY_S8", "APP_ID_SECTION_S11"):
            assert var not in text, f"{var} が残存している"
