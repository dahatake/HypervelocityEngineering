"""D4: precheck_runner の統合テスト。"""

from __future__ import annotations

from pathlib import Path

from hve.autopilot.precheck_model import AutopilotPrecheckResult, PrecheckCategory
from hve.autopilot.precheck_runner import run_step1_precheck


def test_runner_returns_result_object(tmp_path: Path) -> None:
    r = run_step1_precheck([], tmp_path)
    assert isinstance(r, AutopilotPrecheckResult)
    assert r.is_ok() is True
    assert r.count() == 0


def test_runner_collects_file_category(tmp_path: Path) -> None:
    r = run_step1_precheck(["aad-web"], tmp_path)
    # 不足があれば FILE のみに分類されている
    cats = {it.category for it in r.items}
    assert cats.issubset({PrecheckCategory.FILE})


def test_runner_skips_optional_categories_when_none(tmp_path: Path) -> None:
    # wizard/settings/auth を渡さない → これらは検査スキップで FILE のみ
    r = run_step1_precheck(
        ["aad-web"],
        tmp_path,
        wizard_inputs_by_workflow=None,
        settings_by_workflow=None,
        providers=None,
        auth_settings=None,
        auth_states=None,
    )
    for it in r.items:
        assert it.category is PrecheckCategory.FILE


def test_runner_auth_category_evaluated(tmp_path: Path) -> None:
    class _P:
        id = "p1"
        display_name = "P1"

        def is_required(self, _s):  # noqa: ANN001
            return True

    marker = object()
    r = run_step1_precheck(
        [],
        tmp_path,
        providers=[_P()],
        auth_settings={},
        auth_states={"p1": object()},  # not the marker → unauth
        authenticated_marker=marker,
    )
    auth_items = r.by_category(PrecheckCategory.AUTH)
    assert len(auth_items) == 1
    assert auth_items[0].field_name == "p1"


def test_runner_forwards_additional_prompts(tmp_path: Path) -> None:
    """`additional_prompts` が collector に渡り override が機能する。"""
    r_no = run_step1_precheck(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
    )
    r_yes = run_step1_precheck(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
        additional_prompts={
            "aas": "事前に docs/catalog/app-catalog.md を作成済み"
        },
    )
    assert any(it.field_name == "docs/catalog/app-catalog.md" for it in r_no.items)
    assert not any(it.field_name == "docs/catalog/app-catalog.md" for it in r_yes.items)


def test_runner_forwards_extra_provided_paths(tmp_path: Path) -> None:
    """`extra_provided_paths_by_workflow` が collector に渡り override が機能する。"""
    r = run_step1_precheck(
        ["aas"],
        tmp_path,
        steps_by_workflow={"aas": ["2"]},
        extra_provided_paths_by_workflow={
            "": ["docs/catalog/app-catalog.md"],
        },
    )
    assert not any(it.field_name == "docs/catalog/app-catalog.md" for it in r.items)

def test_runner_forwards_use_llm_judge(tmp_path: Path, monkeypatch) -> None:
    """run_step1_precheck の use_llm_judge が collect_missing_files に中継される。"""
    captured = {"use_llm_judge": None}

    from hve.autopilot import precheck_runner as runner_mod

    def fake_collect(*args, **kwargs):  # noqa: ANN001
        captured["use_llm_judge"] = kwargs.get("use_llm_judge")
        return []

    monkeypatch.setattr(runner_mod, "collect_missing_files", fake_collect)

    run_step1_precheck(["aad-web"], tmp_path, use_llm_judge=True)
    assert captured["use_llm_judge"] is True

    captured["use_llm_judge"] = None
    run_step1_precheck(["aad-web"], tmp_path)
    assert captured["use_llm_judge"] is False
