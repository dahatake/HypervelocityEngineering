"""D1: precheck_collector の単体テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.autopilot.precheck_collector import collect_missing_files
from hve.autopilot.precheck_model import PrecheckCategory


def test_unknown_workflow_returns_empty(tmp_path: Path) -> None:
    items = collect_missing_files(["nonexistent-wf"], tmp_path)
    assert items == []


def test_existing_file_not_reported_as_missing(tmp_path: Path) -> None:
    # 既存 workflow 'ard' を対象に、依存ファイルを実体配置して確認
    # ARD 自体は required_input_paths を持たない可能性があるため、
    # 「存在するファイルを step.required_input_paths として扱った場合」を
    # 単体関数 _path_exists 経由で間接確認する。
    from hve.autopilot.precheck_collector import _path_exists

    (tmp_path / "exists.md").write_text("ok", encoding="utf-8")
    assert _path_exists(tmp_path, "exists.md") is True
    assert _path_exists(tmp_path, "missing.md") is False


def test_glob_pattern_resolution(tmp_path: Path) -> None:
    from hve.autopilot.precheck_collector import _path_exists

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("a", encoding="utf-8")
    assert _path_exists(tmp_path, "docs/*.md") is True
    assert _path_exists(tmp_path, "docs/*.json") is False


def test_collect_items_have_correct_category(tmp_path: Path) -> None:
    # 実 workflow を渡し、依存 missing があれば FILE カテゴリで返る
    items = collect_missing_files(["aad-web"], tmp_path)
    for it in items:
        assert it.category is PrecheckCategory.FILE
        assert it.workflow_id == "aad-web"
        assert it.field_name  # 不足パス文字列が入る


def test_steps_filter_limits_scope(tmp_path: Path) -> None:
    # steps_by_workflow で空 list を渡すと step-level 走査がスキップされる
    items_all = collect_missing_files(["aad-web"], tmp_path)
    items_filtered = collect_missing_files(
        ["aad-web"],
        tmp_path,
        steps_by_workflow={"aad-web": []},
    )
    # filtered は step-level missing が 0 になり、items_all 以下になる
    assert len(items_filtered) <= len(items_all)


# ---------------------------------------------------------------------------
# 新ロジック: planned_outputs / additional_prompts / extra_provided_paths
# (plan P2=(b), P3=(b), P4=(a) 採用)
# ---------------------------------------------------------------------------


def test_planned_outputs_satisfy_required_input(tmp_path: Path) -> None:
    """先行 step が `output_paths` で生成予定のファイルは missing とならない。

    aas Step 1 は docs/catalog/app-catalog.md を output、
    Step 2 は同ファイルを required_input としている。
    両方選択すれば Step 2 側の missing は出ない。
    """
    # Step 1 + Step 2 を選択。リポジトリには何も存在しない。
    items = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["1", "2"]},
    )
    # Step 2 の app-catalog.md missing は無いはず
    step2_app_catalog_missing = [
        it for it in items
        if it.step_id == "2" and it.field_name == "docs/catalog/app-catalog.md"
    ]
    assert step2_app_catalog_missing == []


def test_planned_outputs_excluded_when_step_not_selected(tmp_path: Path) -> None:
    """Step 1 が未選択なら、Step 2 の app-catalog.md missing は検出される。"""
    items = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
    )
    paths = {(it.step_id, it.field_name) for it in items}
    assert ("2", "docs/catalog/app-catalog.md") in paths


def test_additional_prompts_override(tmp_path: Path) -> None:
    """追加プロンプト本文に必須ファイルパスが含まれれば missing にならない。"""
    items_no_prompt = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
    )
    items_with_prompt = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
        additional_prompts={
            "aas": "事前に docs/catalog/app-catalog.md を作成済みです。"
        },
    )
    n_app_catalog_no = sum(
        1 for it in items_no_prompt
        if it.field_name == "docs/catalog/app-catalog.md"
    )
    n_app_catalog_yes = sum(
        1 for it in items_with_prompt
        if it.field_name == "docs/catalog/app-catalog.md"
    )
    assert n_app_catalog_no > 0
    assert n_app_catalog_yes == 0


def test_extra_provided_paths_override(tmp_path: Path) -> None:
    """GUI パラメータで明示指定されたファイルは missing にならない。"""
    items = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
        extra_provided_paths_by_workflow={
            "": ["docs/catalog/app-catalog.md"],
        },
    )
    found = [
        it for it in items
        if it.field_name == "docs/catalog/app-catalog.md"
    ]
    assert found == []


def test_truly_missing_files_still_detected(tmp_path: Path) -> None:
    """planned/prompt/extra いずれにも該当しない真の不足は引き続き検出される。"""
    items = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["1"]},  # Step 1 は use-case-catalog を要求
    )
    paths = {(it.step_id, it.field_name) for it in items}
    assert ("1", "docs/catalog/use-case-catalog.md") in paths


def test_existing_repo_file_not_missing(tmp_path: Path) -> None:
    """repo 配下に実存すれば missing にならない。"""
    (tmp_path / "docs" / "catalog").mkdir(parents=True)
    (tmp_path / "docs" / "catalog" / "use-case-catalog.md").write_text("uc", encoding="utf-8")
    items = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["1"]},
    )
    found = [
        it for it in items
        if it.field_name == "docs/catalog/use-case-catalog.md"
    ]
    assert found == []


def test_is_overridden_in_prompt_matches_description() -> None:
    """description（文書名）でも override 判定される。"""
    from hve.autopilot.precheck_collector import is_overridden_in_prompt

    assert is_overridden_in_prompt(
        "アプリケーションカタログを使います",
        "docs/catalog/app-catalog.md",
        "アプリケーションカタログ",
    )
    assert not is_overridden_in_prompt(
        "別の話題",
        "docs/catalog/app-catalog.md",
        "アプリケーションカタログ",
    )
    assert not is_overridden_in_prompt(
        None,
        "docs/catalog/app-catalog.md",
        "アプリケーションカタログ",
    )


# ---------------------------------------------------------------------------
# チェーン依存ロジック（Q3=A）: 依存先 workflow が選択集合内なら satisfy
# ---------------------------------------------------------------------------


def test_chain_dependency_satisfied_when_dep_workflow_selected(tmp_path: Path) -> None:
    """adfdv が依存する adfd が選択集合に含まれかつ全 step 選択時、
    `WorkflowDependency.required_artifacts`（fan-out glob 含む）は missing にならない。
    """
    items = collect_missing_files(
        ["adfd", "adfdv"],
        tmp_path,
        # 全 step 選択（既定動作）
    )
    # adfdv の依存先 adfd 由来の不足は 0 件のはず
    abdv_dep_missing = [
        it for it in items
        if it.workflow_id == "adfdv" and it.step_id is None
    ]
    assert abdv_dep_missing == [], (
        f"adfdv の依存ファイルが missing になっている: "
        f"{[it.field_name for it in abdv_dep_missing]}"
    )
    # 具体的な代表パスについても明示確認
    field_names = {it.field_name for it in items if it.workflow_id == "adfdv"}
    assert "docs/dataflow/dataflow-service-catalog.md" not in field_names
    assert "docs/dataflow/dataflow-app-catalog.md" not in field_names


def test_chain_dependency_missing_when_dep_step_excluded(tmp_path: Path) -> None:
    """依存先 workflow が選択中でも、必要 step が steps_by_workflow で除外されている
    場合は missing として検出される（過剰許容しない厳密化）。
    """
    # adfd を選択しているが、Step 4 (service-catalog) を steps_by_workflow から除外
    items = collect_missing_files(
        ["adfd", "adfdv"],
        tmp_path,
        steps_by_workflow={
            "adfd": ["1.1", "1.2", "2", "3"],  # Step 4 以降を除外
            # adfdv は全 step
        },
    )
    field_names = {it.field_name for it in items if it.workflow_id == "adfdv"}
    # service-catalog は adfd Step 4 で生成されるはずだったが除外されたので missing
    assert "docs/dataflow/dataflow-service-catalog.md" in field_names


def test_chain_dependency_missing_when_fanout_step_excluded(tmp_path: Path) -> None:
    """fan-out step (Step 6.1) を除外すると、adfdv が要求する jobs/*.md は missing。"""
    items = collect_missing_files(
        ["adfd", "adfdv"],
        tmp_path,
        steps_by_workflow={
            "adfd": ["1.1", "1.2", "2", "3", "4", "5", "6.2", "6.3"],  # 6.1 を除外
        },
    )
    field_names = {it.field_name for it in items if it.workflow_id == "adfdv"}
    assert "docs/dataflow/apps/*.md" in field_names


def test_chain_dependency_still_missing_when_dep_workflow_not_selected(
    tmp_path: Path,
) -> None:
    """adfd が選択集合に含まれない場合、adfdv の依存ファイルは missing として検出される。"""
    items = collect_missing_files(
        ["adfdv"],
        tmp_path,
    )
    abdv_dep_missing = [
        it for it in items
        if it.workflow_id == "adfdv" and it.step_id is None
    ]
    assert len(abdv_dep_missing) > 0


def test_fanout_template_satisfies_glob_required_input(tmp_path: Path) -> None:
    """fan-out テンプレート (`docs/dataflow/apps/{jobId}-{slug}-spec.md`) の出力は
    後続 workflow の glob 要求 (`docs/dataflow/apps/*.md`) を satisfy する。

    adfd Step 6.1 が fan-out output、adfdv が `docs/dataflow/apps/*.md` を依存に持つ。
    adfd + adfdv 両方選択かつ Step 6.1 を含めれば missing にならない。
    """
    items = collect_missing_files(
        ["adfd", "adfdv"],
        tmp_path,
    )
    jobs_glob_missing = [
        it for it in items
        if it.field_name == "docs/dataflow/apps/*.md"
    ]
    assert jobs_glob_missing == []


def test_abd_output_paths_are_declared() -> None:
    """T2 リグレッション: ADFD 各 step の output_paths が空でないこと。"""
    from hve.workflow_registry import get_workflow

    adfd = get_workflow("adfd")
    assert adfd is not None
    non_fanout_steps = {"1.1", "1.2", "2", "3", "4", "5", "6.2"}
    for step in adfd.steps:
        if step.id in non_fanout_steps:
            assert step.output_paths, (
                f"ADFD Step {step.id} の output_paths が空: 必ず宣言してください"
            )
    # fan-out 2 step
    step_6_1 = adfd.get_step("6.1")
    step_6_3 = adfd.get_step("6.3")
    assert step_6_1 and step_6_1.output_paths_template
    assert step_6_3 and step_6_3.output_paths_template


def test_template_to_glob_basic() -> None:
    """_template_to_glob のプレースホルダ→glob 変換確認。"""
    from hve.autopilot.precheck_collector import _template_to_glob

    assert _template_to_glob("docs/dataflow/apps/{jobId}-{slug}-spec.md") == \
        "docs/dataflow/apps/*-*-spec.md"
    assert _template_to_glob("docs/test-specs/{jobId}-test-spec.md") == \
        "docs/test-specs/*-test-spec.md"
    assert _template_to_glob("") == ""
    # プレースホルダ無し
    assert _template_to_glob("docs/plain.md") == "docs/plain.md"


# ---------------------------------------------------------------------------
# T6/T9: ARD グループ ID 展開（SSOT）と planned_outputs 連動
# ---------------------------------------------------------------------------


def test_expand_group_step_ids_ard_basic() -> None:
    """GUI/CLI のグループ ID が実 step ID に展開される。"""
    from hve.workflow_registry import expand_group_step_ids

    assert expand_group_step_ids("ard", ["1", "2", "4"]) == [
        "1", "1.1", "1.2", "2", "4.1", "4.2", "4.3"
    ]
    # 未登録 group ID "3"（KPI/OKR）は素通し
    assert expand_group_step_ids("ard", ["3"]) == ["3"]


def test_expand_group_step_ids_passthrough_for_non_ard() -> None:
    """ARD 以外、未登録 workflow は素通し。"""
    from hve.workflow_registry import expand_group_step_ids

    assert expand_group_step_ids("aas", ["1", "3.1"]) == ["1", "3.1"]
    assert expand_group_step_ids("nonexistent", ["x", "y"]) == ["x", "y"]


def test_group_id_for_step_reverse_lookup() -> None:
    """実 step ID から GUI グループ ID への逆引き。"""
    from hve.workflow_registry import group_id_for_step

    assert group_id_for_step("ard", "1.1") == "1"
    assert group_id_for_step("ard", "4.2") == "4"
    assert group_id_for_step("ard", "2") == "2"
    # 未登録（KPI/OKR）は None
    assert group_id_for_step("ard", "3") is None
    # ARD 以外 / 未登録 step は None
    assert group_id_for_step("aas", "1") is None


def test_ard_group_selection_satisfies_aas_use_case_catalog(tmp_path: Path) -> None:
    """画像症状の回帰: GUI 形式 `{"ard":["1","2","4"], "aas":[...]}` を渡して
    `docs/catalog/use-case-catalog.md` が AAS の required_input から missing にならない。
    """
    items = collect_missing_files(
        ["ard", "aas"],
        tmp_path,
        steps_by_workflow={
            "ard": ["1", "2", "4"],  # GUI グループ ID（"4" → 4.1/4.2/4.3 へ展開）
            "aas": ["1", "2", "3.1", "3.2"],
        },
    )
    use_case_missing = [
        it for it in items
        if it.workflow_id == "aas"
        and it.field_name == "docs/catalog/use-case-catalog.md"
    ]
    assert use_case_missing == [], (
        f"use-case-catalog.md が missing: {[it.step_id for it in use_case_missing]}"
    )


def test_aad_web_fanout_output_paths_template_declared() -> None:
    """T7 リグレッション: AAD-WEB Step 2.1/2.2/2.3 の output_paths_template 宣言。"""
    from hve.workflow_registry import get_workflow

    aad = get_workflow("aad-web")
    assert aad is not None
    for sid in ("2.1", "2.2", "2.3"):
        step = aad.get_step(sid)
        assert step is not None
        assert step.output_paths_template, (
            f"AAD-WEB Step {sid} の output_paths_template が空"
        )


def test_asdw_web_dependency_satisfied_via_aad_web_templates(tmp_path: Path) -> None:
    """T7 機能確認: AAD-WEB + ASDW-WEB 両方選択時、ASDW-WEB の glob 依存
    （docs/screen/*.md, docs/services/*.md, docs/test-specs/*-test-spec.md）が
    AAD-WEB の output_paths_template で satisfy される。
    """
    items = collect_missing_files(
        ["aad-web", "asdw-web"],
        tmp_path,
    )
    asdw_dep_missing = {
        it.field_name for it in items
        if it.workflow_id == "asdw-web" and it.step_id is None
    }
    for required in (
        "docs/screen/*.md",
        "docs/services/*.md",
        "docs/test-specs/*-test-spec.md",
    ):
        assert required not in asdw_dep_missing, (
            f"ASDW-WEB の glob 依存 {required} が missing: {asdw_dep_missing}"
        )


# ---------------------------------------------------------------------------
# T10: ON/OFF 同一アルゴリズム（implicit_required_paths / autopilot_required_artifacts）
# ---------------------------------------------------------------------------


def test_implicit_required_paths_detected(tmp_path: Path) -> None:
    """implicit_required_paths で渡したファイルが planned/実存とも無い場合 missing。"""
    items = collect_missing_files(
        ["aad-web"],
        tmp_path,
        implicit_required_paths={
            "aad-web": ["docs/catalog/app-arch-catalog.md"],
        },
    )
    matched = [
        it for it in items
        if it.workflow_id == "aad-web"
        and it.field_name == "docs/catalog/app-arch-catalog.md"
        and "暗黙必須" in it.description
    ]
    assert len(matched) == 1


def test_implicit_required_paths_satisfied_by_aas_chain(tmp_path: Path) -> None:
    """AAS が選択され Step 2（catalog 生成）を含む場合、aad-web の implicit
    要求 docs/catalog/app-arch-catalog.md は planned で satisfy。"""
    items = collect_missing_files(
        ["aas", "aad-web"],
        tmp_path,
        steps_by_workflow={
            "aas": ["1", "2"],  # Step 2 = app-arch-catalog 生成
            "aad-web": ["1", "2.1", "2.2", "2.3", "3"],
        },
        implicit_required_paths={
            "aad-web": ["docs/catalog/app-arch-catalog.md"],
        },
    )
    aad_implicit_missing = [
        it for it in items
        if it.workflow_id == "aad-web"
        and it.field_name == "docs/catalog/app-arch-catalog.md"
    ]
    assert aad_implicit_missing == []


def test_autopilot_required_artifacts_detected(tmp_path: Path) -> None:
    """autopilot_required_artifacts は workflow_id='' で PrecheckItem として返る。"""
    items = collect_missing_files(
        ["aad-web"],
        tmp_path,
        autopilot_required_artifacts=["docs/catalog/app-arch-catalog.md"],
    )
    global_missing = [
        it for it in items
        if it.workflow_id == ""
        and it.field_name == "docs/catalog/app-arch-catalog.md"
    ]
    assert len(global_missing) == 1


def test_autopilot_required_artifacts_satisfied_by_aas_step_2(tmp_path: Path) -> None:
    """AAS Step 2 が選択集合に含まれる場合、planned_outputs 経由で satisfy。"""
    items = collect_missing_files(
        ["aas", "aad-web"],
        tmp_path,
        steps_by_workflow={"aas": ["1", "2"], "aad-web": ["1"]},
        autopilot_required_artifacts=["docs/catalog/app-arch-catalog.md"],
    )
    global_missing = [
        it for it in items
        if it.workflow_id == "" and it.field_name == "docs/catalog/app-arch-catalog.md"
    ]
    assert global_missing == []


def test_off_mode_omits_autopilot_specific_checks(tmp_path: Path) -> None:
    """OFF 経路相当: implicit_required_paths と autopilot_required_artifacts を
    渡さない場合は当該カテゴリの不足が発火しない（ON/OFF 差異の境界確認）。"""
    items_off = collect_missing_files(
        ["aad-web"],
        tmp_path,
    )
    items_on = collect_missing_files(
        ["aad-web"],
        tmp_path,
        implicit_required_paths={"aad-web": ["docs/catalog/app-arch-catalog.md"]},
        autopilot_required_artifacts=["docs/catalog/app-arch-catalog.md"],
    )
    assert len(items_on) > len(items_off)


def test_t8_target_steps_have_output_paths() -> None:
    """T8 で確定した対象 step が output_paths / output_paths_template を持つ。"""
    from hve.workflow_registry import get_workflow

    # ASDW-WEB
    asdw = get_workflow("asdw-web")
    assert asdw is not None
    assert asdw.get_step("2.3T").output_paths_template == [
        "docs/test-specs/{serviceId}-test-spec.md"
    ]
    assert asdw.get_step("3.0T").output_paths_template == [
        "docs/test-specs/{screenId}-test-spec.md"
    ]
    # AAG
    aag = get_workflow("aag")
    assert aag is not None
    assert aag.get_step("1").output_paths == ["docs/agent/agent-application-definition.md"]
    assert aag.get_step("2").output_paths == ["docs/agent/agent-architecture.md"]
    assert aag.get_step("3").output_paths == ["docs/ai-agent-catalog.md"]
    assert aag.get_step("3").output_paths_template == [
        "docs/agent/agent-detail-{agentId}-{agentName}.md"
    ]
    # AAGD
    aagd = get_workflow("aagd")
    assert aagd is not None
    assert aagd.get_step("1").output_paths == ["docs/agent/agent-application-definition.md"]
    assert aagd.get_step("2.1").output_paths_template == [
        "docs/test-specs/{agentId}-test-spec.md"
    ]

# --- T4: LLM 判定統合テスト (use_llm_judge=True) ---

def test_llm_judge_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    """use_llm_judge を渡さない場合は LLM ヘルパが呼ばれない（後方互換）。"""
    called = {"n": 0}

    def fake_judge(*args, **kwargs):  # noqa: ANN001
        called["n"] += 1
        return {}

    monkeypatch.setattr(
        "hve.autopilot.precheck_llm_judge.judge_overrides_with_llm",
        fake_judge,
    )
    collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
        additional_prompts={"aas": "別ファイル名で指定します"},
    )
    assert called["n"] == 0


def test_llm_judge_removes_satisfied_items(tmp_path: Path, monkeypatch) -> None:
    """LLM が satisfied と判定した項目は missing から除外される。"""
    from hve.autopilot.precheck_llm_judge import JudgeResult

    def fake_judge(prompt, items, **kwargs):  # noqa: ANN001
        # すべての候補を satisfied として返す
        return {
            it["pattern"]: JudgeResult(is_satisfied=True, reason="LLM ok")
            for it in items
        }

    monkeypatch.setattr(
        "hve.autopilot.precheck_llm_judge.judge_overrides_with_llm",
        fake_judge,
    )
    items_off = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
        additional_prompts={"aas": "自然言語で代替指定"},
        use_llm_judge=False,
    )
    items_on = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
        additional_prompts={"aas": "自然言語で代替指定"},
        use_llm_judge=True,
    )
    aas_missing_off = [it for it in items_off if it.workflow_id == "aas"]
    aas_missing_on = [it for it in items_on if it.workflow_id == "aas"]
    assert len(aas_missing_off) > 0
    assert len(aas_missing_on) == 0


def test_llm_judge_keeps_unsatisfied_items(tmp_path: Path, monkeypatch) -> None:
    """LLM が satisfied=False を返した項目は missing として残る。"""
    from hve.autopilot.precheck_llm_judge import JudgeResult

    def fake_judge(prompt, items, **kwargs):  # noqa: ANN001
        return {
            it["pattern"]: JudgeResult(is_satisfied=False, reason="言及なし")
            for it in items
        }

    monkeypatch.setattr(
        "hve.autopilot.precheck_llm_judge.judge_overrides_with_llm",
        fake_judge,
    )
    items_on = collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
        additional_prompts={"aas": "関係ない指示"},
        use_llm_judge=True,
    )
    aas_missing = [it for it in items_on if it.workflow_id == "aas"]
    assert len(aas_missing) > 0


def test_llm_judge_skipped_when_prompt_empty(tmp_path: Path, monkeypatch) -> None:
    """追加プロンプトが空の workflow に対しては LLM を呼ばない。"""
    called = {"n": 0}

    def fake_judge(prompt, items, **kwargs):  # noqa: ANN001
        called["n"] += 1
        return {}

    monkeypatch.setattr(
        "hve.autopilot.precheck_llm_judge.judge_overrides_with_llm",
        fake_judge,
    )
    collect_missing_files(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
        additional_prompts={"aas": ""},
        use_llm_judge=True,
    )
    assert called["n"] == 0
