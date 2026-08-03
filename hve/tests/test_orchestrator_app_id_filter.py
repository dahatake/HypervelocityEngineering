"""APP-ID フィルタの伝播テスト。

Step 1 の設定画面で APP-ID を 1 つ選択した場合に、Step 2 の fan-out 子展開が
その APP-ID に紐付くキーのみへ絞り込まれることを保証する。

検証範囲:
- ``orchestrator._expand_workflow_for_dag`` に ``app_ids`` を渡すと、
  ``hve.fanout_expander.expand_workflow_fanout`` 経由でフィルタが適用される。
- ``DAGExecutor`` に ``app_ids`` を渡すと、deferred fan-out のランタイム再展開
  （``expand_single_step_fanout``）にも同じ app_ids が伝播する。

E2E（GUI → orchestrator）の確認は T08 の手動再現で行う。本ファイルは
orchestrator と DAGExecutor の interface 接続点のみを検証する。
"""
from __future__ import annotations

from pathlib import Path

from hve import workflow_registry as wr
from hve.dag_executor import DAGExecutor
from hve.orchestrator import _expand_workflow_for_dag


def _write_aad_web_min_catalogs(tmp_path: Path) -> None:
    """aad-web fan-out 用の最小カタログ 3 種を tmp_path に書き出す。

    - app-catalog.md (APP-07, APP-09)
    - screen-catalog-APP-07.md / -APP-09.md
    - service-catalog.md (SVC-09→APP-07, SVC-11→APP-09)
    """
    catalog_dir = tmp_path / "docs" / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    (catalog_dir / "app-catalog.md").write_text(
        "# App Catalog\n\n## A. サマリ\n\n"
        "| APP-ID | 名称 |\n"
        "|---|---|\n"
        "| APP-07 | seven |\n"
        "| APP-09 | nine |\n",
        encoding="utf-8",
    )
    (catalog_dir / "screen-catalog-APP-07.md").write_text(
        "# Screen APP-07\n\n"
        "| 画面ID | 名称 |\n"
        "|---|---|\n"
        "| APP-07-S001 | s1 |\n"
        "| APP-07-S002 | s2 |\n",
        encoding="utf-8",
    )
    (catalog_dir / "screen-catalog-APP-09.md").write_text(
        "# Screen APP-09\n\n"
        "| 画面ID | 名称 |\n"
        "|---|---|\n"
        "| APP-09-S001 | s1 |\n",
        encoding="utf-8",
    )
    (catalog_dir / "service-catalog.md").write_text(
        "# Service Catalog\n\n## A. サマリ\n\n"
        "| SVC-ID | 名称 | 種別 | カテゴリ | 説明 | 利用APP |\n"
        "|---|---|---|---|---|---|\n"
        "| SVC-09 | nine-svc | API | A | desc | APP-07 |\n"
        "| SVC-11 | eleven-svc | API | A | desc | APP-09 |\n"
        "\n## B. 詳細\n",
        encoding="utf-8",
    )


def test_expand_workflow_for_dag_filters_aad_web_by_app_07(tmp_path):
    """AAD-WEB × APP-07: Step 1=APP-07 のみ、Step 2.1=APP-07 配下のみ、Step 2.2=SVC-09 のみ。"""
    _write_aad_web_min_catalogs(tmp_path)
    aad_web = wr.get_workflow("aad-web")
    active = {"1", "2.1", "2.2", "2.3"}
    expanded_wf, expanded_active, info = _expand_workflow_for_dag(
        aad_web, active, tmp_path, app_ids=["APP-07"],
    )
    assert info is not None
    assert info.fanout_map.get("1") == ["1/APP-07"]
    assert info.fanout_map.get("2.1") == ["2.1/APP-07-S001", "2.1/APP-07-S002"]
    assert info.fanout_map.get("2.2") == ["2.2/SVC-09"]
    assert info.fanout_map.get("2.3") == ["2.3/SVC-09"]
    # active も子 ID が追加されている
    assert "1/APP-07" in expanded_active
    assert "2.1/APP-07-S001" in expanded_active
    assert "2.2/SVC-09" in expanded_active


def test_expand_workflow_for_dag_app_ids_none_returns_full_fanout(tmp_path):
    """app_ids=None は全 fan-out キーを展開（後方互換）。"""
    _write_aad_web_min_catalogs(tmp_path)
    aad_web = wr.get_workflow("aad-web")
    active = {"1", "2.1", "2.2", "2.3"}
    _, _, info_none = _expand_workflow_for_dag(aad_web, active, tmp_path, app_ids=None)
    _, _, info_default = _expand_workflow_for_dag(aad_web, active, tmp_path)
    assert info_none is not None and info_default is not None
    # app_ids=None と未指定で同一結果
    assert info_none.fanout_map.get("1") == info_default.fanout_map.get("1")
    # min catalog 全件 = APP-07 + APP-09 の 2 件
    assert sorted(info_none.fanout_map.get("1", [])) == ["1/APP-07", "1/APP-09"]


def test_expand_workflow_for_dag_app_ids_empty_returns_full_fanout(tmp_path):
    """app_ids=[] も全件展開（後方互換）。"""
    _write_aad_web_min_catalogs(tmp_path)
    aad_web = wr.get_workflow("aad-web")
    active = {"1", "2.1", "2.2", "2.3"}
    _, _, info_empty = _expand_workflow_for_dag(aad_web, active, tmp_path, app_ids=[])
    assert info_empty is not None
    assert sorted(info_empty.fanout_map.get("1", [])) == ["1/APP-07", "1/APP-09"]


def test_dag_executor_passes_app_ids_to_expand_single_step_fanout(tmp_path, monkeypatch):
    """DAGExecutor に渡された app_ids が expand_single_step_fanout 呼び出しに伝播する。

    deferred fan-out 経路で再展開が起きる際、ランタイムでも app_ids でフィルタ
    される。spy で関数呼び出しの kwargs を検証する。

    実装メモ: DAGExecutor._expand_dynamic_fanouts 内で
    ``from .fanout_expander import expand_single_step_fanout`` とローカル import
    しているため、spy は ``hve.fanout_expander`` モジュール属性を差し替える。
    """
    captured: dict = {}

    import hve.fanout_expander as fe_mod

    real_fn = fe_mod.expand_single_step_fanout

    def _spy(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(fe_mod, "expand_single_step_fanout", _spy)

    async def _dummy_run(**_kw):
        return True

    # 単一 fan-out base のみを持つ最小 workflow
    step = wr.StepDef(
        id="1", title="t", custom_agent=None,
        consumed_artifacts=[], fanout_static_keys=["k1", "k2"],
    )
    wf = wr.WorkflowDef(
        id="t", name="t", label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[], steps=[step],
    )

    executor = DAGExecutor(
        workflow=wf,
        run_step_fn=_dummy_run,
        active_step_ids={"1"},
        repo_root=tmp_path,
        enable_fanout=False,  # __init__ の自動 expand_workflow_fanout を抑止し、
                              # deferred 経路の _try_dynamic_expand を発火させる
        deferred_fanout_ids={"1"},
        app_ids=["APP-07"],
    )
    # _try_dynamic_expand を直接呼んで expand_single_step_fanout の kwargs を捕捉
    # (private API 直叩きだが、interface 接続点の確認のため最小範囲で使用)
    executor._try_dynamic_expand(completed_step_id="dummy")

    assert "kwargs" in captured
    assert captured["kwargs"].get("app_ids") == ["APP-07"]


def test_dag_executor_with_none_app_ids_passes_none(tmp_path, monkeypatch):
    """DAGExecutor(app_ids=None) は expand_single_step_fanout に app_ids=None を渡す。"""
    captured: dict = {}
    import hve.fanout_expander as fe_mod
    real_fn = fe_mod.expand_single_step_fanout

    def _spy(*args, **kwargs):
        captured["kwargs"] = kwargs
        return real_fn(*args, **kwargs)

    monkeypatch.setattr(fe_mod, "expand_single_step_fanout", _spy)

    async def _dummy_run(**_kw):
        return True

    step = wr.StepDef(
        id="1", title="t", custom_agent=None,
        consumed_artifacts=[], fanout_static_keys=["k1"],
    )
    wf = wr.WorkflowDef(
        id="t", name="t", label_prefix="t",
        state_labels=wr._make_state_labels("t"),
        params=[], steps=[step],
    )

    executor = DAGExecutor(
        workflow=wf,
        run_step_fn=_dummy_run,
        active_step_ids={"1"},
        repo_root=tmp_path,
        enable_fanout=False,
        deferred_fanout_ids={"1"},
        app_ids=None,
    )
    executor._try_dynamic_expand(completed_step_id="dummy")
    assert captured["kwargs"].get("app_ids") is None
