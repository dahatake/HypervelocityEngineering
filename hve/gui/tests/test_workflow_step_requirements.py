"""hve.gui.tests.test_workflow_step_requirements

Task A-3: Task A-1（要件テーブル）/ A-2（純関数）の単体テスト。
Qt 非依存（pytest-qt 不要）。

テストマトリクス:
  - REQUIREMENT_TABLE の整合性（全 11 ワークフロー定義済み）
  - pick_target_step: 単独 / 複数 / 優先順序 / 未定義スキップ
  - summarize_requirements: 各ワークフロー × 入力状態の主要パターン
  - ARD Step 2 起点ロジック（添付 0 件 / 1 件 + 起点未選択 / 起点選択済み）
  - _natural_step_key: 自然順ソート
"""

from __future__ import annotations

import pytest

from hve.gui.workflow_step_requirements import (
    FILE_KIND_TO_SPEC,
    INPUT_FIELD_KEYS,
    REQUIREMENT_TABLE,
    WORKFLOW_PRIORITY,
    WORKFLOW_TO_SECTION,
    RequirementItem,
    RequirementsSummary,
    StepRequirement,
    _natural_step_key,
    get_file_kind_spec,
    get_requirement,
    pick_target_step,
    summarize_requirements,
)


# --------------------------------------------------------------------------
# Table integrity
# --------------------------------------------------------------------------


class TestTableIntegrity:
    def test_all_workflows_have_at_least_one_entry(self):
        defined_wfs = {wf for wf, _ in REQUIREMENT_TABLE.keys()}
        expected_wfs = set(WORKFLOW_PRIORITY)
        assert defined_wfs == expected_wfs

    def test_priority_matches_section_keys(self):
        # すべての優先順位ワークフローが配置先セクションを持つ
        for wf in WORKFLOW_PRIORITY:
            assert wf in WORKFLOW_TO_SECTION

    def test_required_info_keys_are_known(self):
        # 必須情報キーはすべて INPUT_FIELD_KEYS 内
        for req in REQUIREMENT_TABLE.values():
            for k in req.required_info_keys:
                assert k in INPUT_FIELD_KEYS, f"unknown key: {k}"

    def test_required_file_kinds_are_known(self):
        # 必須ファイル種別はすべて FILE_KIND_TO_SPEC 内
        for req in REQUIREMENT_TABLE.values():
            if req.required_file_kind is not None:
                assert req.required_file_kind in FILE_KIND_TO_SPEC

    def test_logic_values_are_valid(self):
        for req in REQUIREMENT_TABLE.values():
            assert req.required_info_logic in ("all", "any", "none")

    def test_app_id_not_in_required_keys(self):
        # 改訂で app_id は全削除
        for req in REQUIREMENT_TABLE.values():
            assert "app_id" not in req.required_info_keys
            assert "usecase_id" not in req.required_info_keys


# --------------------------------------------------------------------------
# get_requirement
# --------------------------------------------------------------------------


class TestGetRequirement:
    def test_existing(self):
        r = get_requirement("ard", "1")
        assert r is not None
        assert r.workflow_id == "ard"
        assert r.required_info_keys == ("company_name",)

    def test_missing(self):
        assert get_requirement("ard", "999") is None
        assert get_requirement("nonexistent", "1") is None


# --------------------------------------------------------------------------
# _natural_step_key
# --------------------------------------------------------------------------


class TestNaturalStepKey:
    def test_basic_ordering(self):
        keys = ["2", "1", "1.1", "10", "2.1", "1.2"]
        sorted_keys = sorted(keys, key=_natural_step_key)
        assert sorted_keys == ["1", "1.1", "1.2", "2", "2.1", "10"]

    def test_non_numeric_part_goes_last(self):
        # "2.3T" は (2, 9999) として末尾扱い（非数値部は決定論的に大きい値）
        assert _natural_step_key("2.3") < _natural_step_key("2.3T")
        # 数値ステップは非数値ステップより手前に並ぶ
        assert _natural_step_key("2.4") < _natural_step_key("2.3T")


# --------------------------------------------------------------------------
# pick_target_step
# --------------------------------------------------------------------------


class TestPickTargetStep:
    def test_single_workflow(self):
        assert pick_target_step([("ard", ["1"])]) == ("ard", "1")

    def test_min_step_id_within_workflow(self):
        assert pick_target_step([("ard", ["2", "1", "4"])]) == ("ard", "1")

    def test_priority_first_workflow_wins(self):
        # ARD と aad-web 同時選択 → ARD が先頭
        result = pick_target_step([
            ("aad-web", ["1"]),
            ("ard", ["1"]),
        ])
        assert result == ("ard", "1")

    def test_skip_workflow_without_table_entry(self):
        # aas は step "1" のみ登録。"999" は未登録 → スキップして次の登録済みへ
        result = pick_target_step([
            ("aas", ["999"]),
            ("aad-web", ["1"]),
        ])
        assert result == ("aad-web", "1")

    def test_empty_returns_none(self):
        assert pick_target_step([]) is None
        assert pick_target_step([("ard", [])]) is None

    def test_natural_order_within_workflow(self):
        # adfd は "1.1" と "2" → "1.1" が選ばれる
        result = pick_target_step([("adfd", ["2", "1.1"])])
        assert result == ("adfd", "1.1")


# --------------------------------------------------------------------------
# summarize_requirements — basic
# --------------------------------------------------------------------------


class TestSummarizeBasic:
    def test_unknown_returns_none(self):
        assert summarize_requirements("nonexistent", "1") is None

    def test_returns_summary_object(self):
        s = summarize_requirements("ard", "1")
        assert isinstance(s, RequirementsSummary)
        assert s.workflow_id == "ard"
        assert s.step_id == "1"
        assert s.section == "C14"


# --------------------------------------------------------------------------
# summarize_requirements — ARD
# --------------------------------------------------------------------------


class TestSummarizeArd:
    def test_step1_missing_company_name(self):
        s = summarize_requirements("ard", "1", input_values={"company_name": ""})
        assert s.overall_status == "warn"
        assert any(i.label == "company_name" and i.status == "warn" for i in s.items)

    def test_step1_with_company_name(self):
        s = summarize_requirements("ard", "1", input_values={"company_name": "Acme"})
        assert s.overall_status == "ok"

    def test_step2_missing_target_business(self):
        s = summarize_requirements("ard", "2")
        assert s.overall_status == "warn"

    def test_step2_with_target_business_no_attachments(self):
        s = summarize_requirements(
            "ard", "2",
            input_values={"target_business": "EC事業"},
            attached_count=0,
        )
        assert s.overall_status == "ok"

    def test_step2_attachments_without_origin(self):
        s = summarize_requirements(
            "ard", "2",
            input_values={"target_business": "EC事業"},
            attached_count=3,
            origin_chosen=False,
        )
        assert s.overall_status == "warn"
        assert any("起点" in i.label for i in s.items)

    def test_step2_attachments_with_origin(self):
        s = summarize_requirements(
            "ard", "2",
            input_values={"target_business": "EC事業"},
            attached_count=3,
            origin_chosen=True,
        )
        assert s.overall_status == "ok"

    def test_step3_requires_business_requirement_md(self):
        s = summarize_requirements("ard", "3", file_exists=lambda _p: False)
        assert s.overall_status == "warn"
        s2 = summarize_requirements("ard", "3", file_exists=lambda _p: True)
        assert s2.overall_status == "ok"

    def test_step4_requires_business_requirement_md(self):
        s = summarize_requirements("ard", "4", file_exists=lambda _p: False)
        assert s.overall_status == "warn"


# --------------------------------------------------------------------------
# summarize_requirements — other workflows
# --------------------------------------------------------------------------


class TestSummarizeOthers:
    def test_aas_requires_use_case_catalog(self):
        s = summarize_requirements("aas", "1", file_exists=lambda _p: False)
        assert s.overall_status == "warn"
        s2 = summarize_requirements("aas", "1", file_exists=lambda _p: True)
        assert s2.overall_status == "ok"

    def test_aad_web_no_required_info(self):
        # app_id は必須から除外されているため、ファイルさえあれば ok
        s = summarize_requirements("aad-web", "1", file_exists=lambda _p: True)
        assert s.overall_status == "ok"

    def test_asdw_web_requires_resource_group(self):
        s = summarize_requirements(
            "asdw-web", "1.1",
            input_values={"resource_group": ""},
            file_exists=lambda _p: True,
        )
        assert s.overall_status == "warn"
        s2 = summarize_requirements(
            "asdw-web", "1.1",
            input_values={"resource_group": "rg-prod"},
            file_exists=lambda _p: True,
        )
        assert s2.overall_status == "ok"

    def test_aagd_requires_resource_group(self):
        s = summarize_requirements(
            "aagd", "1",
            input_values={"resource_group": "rg-prod"},
            file_exists=lambda _p: True,
        )
        assert s.overall_status == "ok"

    def test_akm_or_logic_qa_only(self):
        # original-docs/ なし、qa/ あり → "any" で ok
        def fe(p: str) -> bool:
            return p == "qa/"
        s = summarize_requirements("akm", "1", file_exists=fe)
        assert s.overall_status == "ok"

    def test_akm_or_logic_both_missing(self):
        s = summarize_requirements("akm", "1", file_exists=lambda _p: False)
        assert s.overall_status == "warn"

    def test_aqod_requires_original_docs(self):
        # akm と異なり aqod は original-docs/ のみ
        def fe(p: str) -> bool:
            return p == "qa/"
        s = summarize_requirements("aqod", "1", file_exists=fe)
        assert s.overall_status == "warn"

    def test_adoc_requires_target_dirs(self):
        s = summarize_requirements("adoc", "1", input_values={"target_dirs": ""})
        assert s.overall_status == "warn"
        s2 = summarize_requirements("adoc", "1", input_values={"target_dirs": "src/"})
        assert s2.overall_status == "ok"

    def test_section_for_options_top_workflow(self):
        s = summarize_requirements("aas", "1", file_exists=lambda _p: True)
        assert s.section == "OPTIONS_TOP"
