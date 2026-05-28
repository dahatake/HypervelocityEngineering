"""D4: precheck_runner の統合テスト（v2 統一版）。

`run_step1_precheck` が `summarize_requirements_for_selection` 経由で
バナーと同じ判定ロジックを使うことを検証する。
"""

from __future__ import annotations

from pathlib import Path

from hve.autopilot.precheck_model import AutopilotPrecheckResult, PrecheckCategory
from hve.autopilot.precheck_runner import run_step1_precheck


def test_runner_returns_result_object(tmp_path: Path) -> None:
    r = run_step1_precheck([], tmp_path)
    assert isinstance(r, AutopilotPrecheckResult)
    assert r.is_ok() is True
    assert r.count() == 0


def test_runner_aas_step1_requires_use_case_catalog(tmp_path: Path) -> None:
    r = run_step1_precheck(
        ["aas"], tmp_path,
        steps_by_workflow={"aas": ["1"]},
    )
    file_items = r.by_category(PrecheckCategory.FILE)
    assert any(
        it.field_name == "docs/catalog/use-case-catalog.md" for it in file_items
    )


def test_runner_aas_middle_steps_do_not_trigger_extra_checks(tmp_path: Path) -> None:
    """v2: 中間ステップの required_input_paths は検査対象外（バナー方針へ統一）。"""
    r = run_step1_precheck(
        ["aas"], tmp_path,
        steps_by_workflow={"aas": ["1", "6"]},
    )
    file_names = {it.field_name for it in r.by_category(PrecheckCategory.FILE)}
    assert "docs/catalog/screen-catalog.md" not in file_names


def test_runner_ard_aas_combined_only_checks_priority_workflow(tmp_path: Path) -> None:
    """ARD + AAS 同時選択時はバナーと同じく最優先 (ARD) のみ評価する。

    バナーで「ARD Step 3 OK」と表示されているのに precheck が AAS Step 1 の
    use-case-catalog.md 不足で NG を出す不整合（ユーザー報告）への回帰防止。
    ARD Step 4 がユースケースカタログを生成するため、AAS 側の入力不足は
    実行時に上流ステップで解消される。
    """
    br = tmp_path / "docs" / "business-requirement.md"
    br.parent.mkdir(parents=True, exist_ok=True)
    br.write_text("# br", encoding="utf-8")

    r = run_step1_precheck(
        ["ard", "aas"], tmp_path,
        steps_by_workflow={"ard": ["3", "4"], "aas": ["1"]},
        input_values={},
    )
    file_names = {it.field_name for it in r.by_category(PrecheckCategory.FILE)}
    # AAS Step 1 の use-case-catalog.md は警告しない
    assert "docs/catalog/use-case-catalog.md" not in file_names
    # ARD Step 3 の business-requirement.md は存在するので警告なし
    assert "docs/business-requirement.md" not in file_names
    assert r.is_ok() is True


def test_runner_ard_step1_requires_company_name(tmp_path: Path) -> None:
    r = run_step1_precheck(
        ["ard"], tmp_path,
        steps_by_workflow={"ard": ["1"]},
        input_values={},
    )
    wi_items = r.by_category(PrecheckCategory.WIZARD_INPUT)
    assert any(it.field_name == "company_name" for it in wi_items)


def test_runner_ard_step1_satisfied_when_company_name_filled(tmp_path: Path) -> None:
    r = run_step1_precheck(
        ["ard"], tmp_path,
        steps_by_workflow={"ard": ["1"]},
        input_values={"company_name": "Contoso"},
    )
    wi_names = {it.field_name for it in r.by_category(PrecheckCategory.WIZARD_INPUT)}
    assert "company_name" not in wi_names


def test_runner_autopilot_mode_requires_catalog(tmp_path: Path) -> None:
    r = run_step1_precheck(
        ["aas", "aad-web"],
        tmp_path,
        steps_by_workflow={"aas": ["1"], "aad-web": ["1"]},
        autopilot_mode=True,
    )
    file_items = r.by_category(PrecheckCategory.FILE)
    assert any(
        it.field_name == "docs/catalog/app-arch-catalog.md" for it in file_items
    )
    assert not any(
        it.field_name == "docs/catalog/use-case-catalog.md" for it in file_items
    )


def test_runner_autopilot_mode_satisfied_when_catalog_exists(tmp_path: Path) -> None:
    """Autopilot ON + SE 系 WF（aad-web）選択 + app-arch-catalog.md 配置 → OK。"""
    catalog = tmp_path / "docs" / "catalog" / "app-arch-catalog.md"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text("# catalog", encoding="utf-8")

    r = run_step1_precheck(
        ["aas", "aad-web"], tmp_path,
        steps_by_workflow={"aas": ["1"], "aad-web": ["1"]},
        autopilot_mode=True,
    )
    assert r.is_ok() is True


def test_runner_autopilot_custom_catalog_path(tmp_path: Path) -> None:
    """Autopilot ON + SE 系 WF 選択 + カスタムカタログパス配置 → OK。"""
    custom = tmp_path / "custom" / "my-catalog.md"
    custom.parent.mkdir(parents=True, exist_ok=True)
    custom.write_text("# custom", encoding="utf-8")

    r = run_step1_precheck(
        ["aas", "aad-web"], tmp_path,
        steps_by_workflow={"aas": ["1"], "aad-web": ["1"]},
        autopilot_mode=True,
        autopilot_catalog_path="custom/my-catalog.md",
    )
    assert r.is_ok() is True


def test_runner_autopilot_mode_no_se_workflow_skips_catalog_check(tmp_path: Path) -> None:
    """Autopilot ON + ARD/AAS のみ選択（SE 系未選択） → app-arch-catalog.md は要求されない。

    バナーと Precheck の挙動を Autopilot ON/OFF で揃えるための回帰テスト。
    """
    r = run_step1_precheck(
        ["ard"], tmp_path,
        steps_by_workflow={"ard": ["1"]},
        input_values={"company_name": "Contoso"},
        autopilot_mode=True,
    )
    file_names = {it.field_name for it in r.by_category(PrecheckCategory.FILE)}
    assert "docs/catalog/app-arch-catalog.md" not in file_names


def test_runner_no_legacy_setting_category(tmp_path: Path) -> None:
    """v2: SETTING / AUTH カテゴリは生成されない（enum 値自体は互換性のため温存）。

    生成され得るのは FILE / WIZARD_INPUT のみ。
    """
    r = run_step1_precheck(
        ["ard"], tmp_path,
        steps_by_workflow={"ard": ["1"]},
        input_values={},
    )
    for it in r.items:
        assert it.category in {
            PrecheckCategory.FILE,
            PrecheckCategory.WIZARD_INPUT,
        }
