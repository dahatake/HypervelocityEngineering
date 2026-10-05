"""test_adi.py — ADI（Auto Design-doc Ingestion）ワークフローの基本テスト。"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
import sys
from pathlib import Path

_repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.abspath(_repo_root))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hve.orchestrator import _collect_params_non_interactive  # noqa: E402
from hve.template_engine import _WORKFLOW_DISPLAY_NAMES  # noqa: E402
from hve.workflow_registry import get_workflow  # noqa: E402

_HVE_DIR = Path(__file__).resolve().parents[1]
_REQUIREMENT_DEFINITION = (
    Path(__file__).resolve().parents[2] / "hve-dev" / "requirement-definition.md"
)

_main_path = os.path.join(os.path.dirname(__file__), "..", "__main__.py")
_spec = _ilu.spec_from_file_location("hve_main_for_adi", os.path.abspath(_main_path))
_main_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_main_mod)
_build_parser = _main_mod._build_parser
_build_params = _main_mod._build_params


def test_adi_workflow_registered() -> None:
    wf = get_workflow("adi")
    assert wf is not None
    assert wf.id == "adi"
    assert wf.name == "Auto Design-doc Ingestion"
    assert wf.label_prefix == "adi"


def test_adi_params_are_minimal() -> None:
    """統合後も用途が明確な4パラメータだけを公開する。"""
    wf = get_workflow("adi")
    assert wf.params == ["purpose", "target_scope", "depth", "focus_areas"]


def test_adi_max_parallel_matches_existing_convention() -> None:
    """D01〜D21 fan-out を同一waveで実行できる。"""
    assert get_workflow("adi").max_parallel == 21


def test_adi_has_expected_steps() -> None:
    wf = get_workflow("adi")
    assert [s.id for s in wf.steps] == [
        "1", "1.1", "1.2", "2", "3", "4", "5.1", "5.2", "5.3",
    ]


def test_adi_questionnaire_steps_contract() -> None:
    wf = get_workflow("adi")
    step_11 = wf.get_step("1.1")
    step_12 = wf.get_step("1.2")

    assert step_11 is not None
    assert step_11.custom_agent == "QA-DocConsistency"
    assert step_11.depends_on == ["1"]
    assert step_11.fanout_static_keys == [f"D{n:02d}" for n in range(1, 22)]
    assert step_11.output_paths_template == [
        "qa/{key}-original-docs-questionnaire.md",
    ]
    assert "docs/original-design-doc-ingest/index.json" in step_11.required_input_paths
    assert "docs/original-design-doc-ingest/*/content.md" in step_11.required_input_paths

    assert step_12 is not None
    assert step_12.custom_agent == "QA-DocConsistency"
    assert step_12.depends_on == ["1.1"]
    assert step_12.output_paths == ["qa/original-docs-cross-questionnaire.md"]
    assert step_12.required_input_paths == [
        "qa/{key}-original-docs-questionnaire.md",
    ]


_SEED_AGENT = "Doc-OriginalDownstreamSeed"

# Step 5.x が候補を反映する下流成果物。下流の最上流 Step の出力に対応させる
# （use-case-skeleton=ARD 3.1 / app-catalog=AAS 1 / domain-analytics=AAS 2.1 /
#  data-model=AAS 3.1 / dataflow-app-catalog=ADFD 0.2）。
_SEED_TARGETS = {
    "5.1": ["docs/catalog/use-case-skeleton.md"],
    "5.2": [
        "docs/catalog/app-catalog.md",
        "docs/catalog/domain-analytics.md",
        "docs/catalog/data-model.md",
    ],
    "5.3": ["docs/dataflow/dataflow-app-catalog.md"],
}


def test_adi_seed_steps_share_one_agent() -> None:
    """共通ルールを 1 箇所で管理するため、3 Step は同じ Agent を再利用する。"""
    wf = get_workflow("adi")
    assert {wf.get_step(sid).custom_agent for sid in _SEED_TARGETS} == {_SEED_AGENT}


def test_adi_seed_steps_run_in_parallel_after_step4() -> None:
    """書き込み先が重ならないため Step 4 の後に並列実行できる。"""
    wf = get_workflow("adi")
    for step_id in _SEED_TARGETS:
        assert wf.get_step(step_id).depends_on == ["4"], step_id


def test_adi_seed_step_output_paths() -> None:
    wf = get_workflow("adi")
    for step_id, expected in _SEED_TARGETS.items():
        assert wf.get_step(step_id).output_paths == expected, step_id


def test_adi_seed_steps_read_routing_and_cards() -> None:
    wf = get_workflow("adi")
    for step_id in _SEED_TARGETS:
        required = wf.get_step(step_id).required_input_paths
        assert "docs/catalog/design-doc-routing.md" in required, step_id
        assert "docs/original-design-doc-ingest/*/card.md" in required, step_id


def test_adi_seed_steps_have_body_templates() -> None:
    wf = get_workflow("adi")
    for step_id in _SEED_TARGETS:
        expected = f".github/prompts/steps/adi/step-{step_id}.prompt.md"
        assert wf.get_step(step_id).body_template_path == expected, step_id


def test_adi_seed_targets_do_not_overlap() -> None:
    """並列実行の前提。同一ファイルを 2 つの Step が書くと競合する。"""
    seen: set[str] = set()
    for paths in _SEED_TARGETS.values():
        assert not (seen & set(paths))
        seen |= set(paths)


def test_adi_is_not_registered_as_meta_dependency() -> None:
    """ADI は下流ワークフローを自動起動しない。"""
    from hve.workflow_registry import FULL_PIPELINE

    assert "adi" not in FULL_PIPELINE.workflows
    for deps in FULL_PIPELINE.dependencies.values():
        assert all(d.workflow_id != "adi" for d in deps)


def test_adi_fanout_uses_inventory_parser() -> None:
    step = get_workflow("adi").get_step("2")
    assert step.fanout_parser == "design_doc_inventory"
    assert step.additional_prompt_template_path == ".github/prompts/fanout/adi/_common.prompt.md"


def test_fr_dag_04_declares_adi_step_2_inventory_parser() -> None:
    """FR-DAG-04 が ADI Step 2 の実在 parser を列挙すること。"""
    step = get_workflow("adi").get_step("2")
    assert step is not None
    text = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8")
    block = text.split("- **FR-DAG-04**:", 1)[1].split("- **FR-DAG-05**:", 1)[0]

    declarations = [
        line
        for line in block.splitlines()
        if f"`{step.fanout_parser}`" in line and "ADI Step 2" in line
    ]
    assert len(declarations) == 1, (
        "design_doc_inventory と利用元 ADI Step 2 を同じ列挙行で宣言していない"
    )


def test_adi_step_dependencies_are_serial() -> None:
    wf = get_workflow("adi")
    step_11 = wf.get_step("1.1")
    step_12 = wf.get_step("1.2")
    assert step_11 is not None
    assert step_12 is not None
    assert step_11.depends_on == ["1"]
    assert step_12.depends_on == ["1.1"]
    assert wf.get_step("2").depends_on == ["1.2"]
    assert wf.get_step("3").depends_on == ["2"]
    assert wf.get_step("4").depends_on == ["3"]


def test_adi_step1_contract() -> None:
    step = get_workflow("adi").get_step("1")
    assert step is not None
    assert step.custom_agent == "Doc-OriginalInventory"
    assert step.depends_on == []
    assert step.consumed_artifacts == []
    assert step.body_template_path == ".github/prompts/steps/adi/step-1.prompt.md"
    assert step.output_paths == [
        "docs/catalog/design-doc-inventory.md",
        "docs/original-design-doc-ingest/index.json",
    ]
    assert step.output_paths_template == [
        "docs/original-design-doc-ingest/*/content.md",
    ]


def test_adi_registered_in_skill_manifest() -> None:
    manifest = json.loads((_HVE_DIR / "skill_manifest.json").read_text(encoding="utf-8"))
    assert manifest["workflow_defaults"]["adi"] == ["knowledge-lookup"]
    assert manifest["required_skills"]["adi"]["1"] == ["knowledge-lookup"]


def test_adi_display_name_registered() -> None:
    assert _WORKFLOW_DISPLAY_NAMES["adi"] == "Auto Design-doc Ingestion"


def test_adi_cli_purpose_defaults_to_empty() -> None:
    args = _build_parser().parse_args(["orchestrate", "--workflow", "adi"])
    params = _build_params(args)
    assert params["purpose"] == ""


def test_adi_cli_questionnaire_params_default() -> None:
    args = _build_parser().parse_args(["orchestrate", "--workflow", "adi"])
    params = _build_params(args)
    assert params["target_scope"] == "docs-original/"
    assert params["depth"] == "standard"
    assert params["focus_areas"] == ""


def test_adi_cli_purpose_is_passed_through() -> None:
    args = _build_parser().parse_args(
        ["orchestrate", "--workflow", "adi", "--purpose", "取り置き算出の再構築"]
    )
    params = _build_params(args)
    assert params["purpose"] == "取り置き算出の再構築"


def test_adi_non_interactive_defaults() -> None:
    params = _collect_params_non_interactive(get_workflow("adi"), {"branch": "main"})
    assert params["purpose"] == ""
    assert params["target_scope"] == "docs-original/"
    assert params["depth"] == "standard"
    assert params["focus_areas"] == ""


# --- FR-QA-03: ADI に例外を持たせない ------------------------------------


def _answered_qa_doc():
    from hve.qa_merger import QADocument, QAQuestion

    return QADocument(
        title="事前 QA",
        status="回答待ち",
        header_fields=[("状態", "回答待ち")],
        questions=[QAQuestion(no=1, question="対象範囲は？", default_answer="A")],
    )


def test_adi_is_not_excluded_from_pre_qa() -> None:
    """ADI は事前 QA の対象外としてはならない。"""
    from hve.runner import _should_run_pre_execution_qa

    for step_agent in ("QA-DocConsistency", "Doc-OriginalInventory"):
        assert _should_run_pre_execution_qa(
            auto_qa=True,
            workflow_id="adi",
            custom_agent=step_agent,
            prompt="dummy",
        ) is True
    assert _should_run_pre_execution_qa(
        auto_qa=False, workflow_id="adi", custom_agent=None, prompt="dummy",
    ) is False


def test_adi_answered_qa_is_dispatched_like_other_workflows(tmp_path: Path) -> None:
    """再帰防止の対象は `akm` だけで、ADI は除外されない。"""
    from hve.runner import _persist_answered_qa_and_dispatch

    submitted: list[Path] = []
    _persist_answered_qa_and_dispatch(
        doc=_answered_qa_doc(),
        user_answers_raw="",
        use_defaults=True,
        output_path=tmp_path / "adi-answered.md",
        workflow_id="adi",
        dispatcher=submitted.append,
    )
    assert [p.name for p in submitted] == ["adi-answered.md"]

    recursive: list[Path] = []
    _persist_answered_qa_and_dispatch(
        doc=_answered_qa_doc(),
        user_answers_raw="",
        use_defaults=True,
        output_path=tmp_path / "akm-answered.md",
        workflow_id="akm",
        dispatcher=recursive.append,
    )
    assert recursive == []


def test_adi_questionnaire_main_outputs_are_separate_from_pre_qa_file() -> None:
    """Step 1.1 / 1.2 の main 成果物は事前 QA の回答済み補助ファイルと別物。"""
    from hve.artifact_validation import is_original_docs_questionnaire_filename

    adi = get_workflow("adi")
    assert adi.get_step("1.1").output_paths_template == [
        "qa/{key}-original-docs-questionnaire.md"
    ]
    assert adi.get_step("1.2").output_paths == [
        "qa/original-docs-cross-questionnaire.md"
    ]
    assert is_original_docs_questionnaire_filename(
        Path("qa/D01-original-docs-questionnaire.md")
    )
    assert not is_original_docs_questionnaire_filename(
        Path("qa/Issue-1-questionnaire-answered-abc12345.md")
    )


def test_adi_questionnaire_steps_can_be_skipped() -> None:
    """N5-2 / FR-WF-ADI-18（v3.29）: Step 1.1 / 1.2 を選ばない実行でも Step 2 へ進める。"""
    adi = get_workflow("adi")
    step_2 = adi.get_step("2")
    assert step_2.depends_on == ["1.2"]
    assert step_2.skip_fallback_deps == ["1"]
    assert "qa/original-docs-cross-questionnaire.md" not in step_2.required_input_paths


def test_adi_questionnaire_steps_are_not_selected_by_default() -> None:
    """N5-2 / FR-WF-ADI-18（v3.33）: 既定の選択から 1.1 / 1.2 を外す。"""
    from hve.workflow_registry import default_step_ids

    defaults = default_step_ids("adi")
    assert "1.1" not in defaults and "1.2" not in defaults
    assert defaults[0] == "1" and "2" in defaults
    assert default_step_ids("aas") == []


def test_cli_without_steps_uses_the_registry_default_selection() -> None:
    from hve.__main__ import _build_parser, _build_params

    args = _build_parser().parse_args(["orchestrate", "--workflow", "adi", "--dry-run"])
    params = _build_params(args)
    assert "1.1" not in params["steps"] and "1" in params["steps"]
    explicit = _build_params(_build_parser().parse_args(["orchestrate", "-w", "adi", "--steps", "1,1.1,1.2", "--dry-run"]))
    assert explicit["steps"] == ["1", "1.1", "1.2"]
