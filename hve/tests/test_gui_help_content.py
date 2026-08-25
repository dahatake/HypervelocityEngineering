"""test_gui_help_content.py — help_content モジュールの純粋ユニットテスト。

GUI（Qt）に依存せず、辞書の構造と argparse 抽出を検証する。
"""

from __future__ import annotations


def test_step_intro_returns_entry_for_each_step():
    from hve.gui.help_content import step_intro

    for i in range(3):
        e = step_intro(i)
        assert e.short, f"step {i} の説明文が空"


def test_workflow_help_known_id():
    from hve.gui.help_content import workflow_help

    e = workflow_help("ard")
    assert "事業" in e.short or "要件" in e.short
    assert e.guide_path.endswith(".md")


def test_workflow_help_unknown_id():
    from hve.gui.help_content import workflow_help

    e = workflow_help("__nonexistent__")
    assert e.short == ""


def test_option_help_dynamic_extraction():
    """`hve.__main__._build_parser` から argparse help が抽出できることを確認。"""
    from hve.gui.help_content import option_help

    e = option_help("workflow")
    # 動的抽出が成功していれば必ず短文が入る
    assert e.short, "argparse からの動的抽出が失敗している可能性"


def test_option_help_fallback():
    """argparse に存在しないキーでもフォールバック辞書を引く。"""
    from hve.gui.help_content import option_help

    e = option_help("model")
    assert e.short  # フォールバック辞書もしくは argparse のどちらかから取得


def test_option_help_unknown():
    from hve.gui.help_content import option_help

    e = option_help("__nonexistent_option__")
    assert e.short == ""


def test_workbench_help_known():
    from hve.gui.help_content import workbench_help

    e = workbench_help("log_pane")
    assert "ログ" in e.short


def test_category_help_covers_only_live_categories():
    """実在するカテゴリ枠だけに説明文を持つことを確認。

    キー一覧の出所は `hve/gui/page_options.py` `OptionsPage._setup_ui` の `_add(...)`。
    """
    from hve.gui.help_content import _CATEGORY_HELP, category_help

    live_keys = {
        "C1", "C3", "C4", "C5", "C6", "C7",
        "AZURE", "AGENTIC",
        "C10", "C11", "C13", "C14", "C17",
    }
    dead = set(_CATEGORY_HELP) - live_keys
    assert not dead, f"実在しないカテゴリの説明文が残っています: {sorted(dead)}"
    for key in sorted(_CATEGORY_HELP):
        e = category_help(key)
        assert e.short, f"{key} の説明文が空"
        assert e.guide_path.endswith(".md"), f"{key} のガイドパスが不正"


def test_category_help_unknown():
    from hve.gui.help_content import category_help

    assert category_help("CXX").short == ""


def test_guide_url_returns_file_uri_when_exists():
    from hve.gui.help_content import guide_url, users_guide_dir

    if not (users_guide_dir() / "hve-gui-getting-started.md").exists():
        return  # users-guide が無い環境ではスキップ
    url = guide_url("hve-gui-getting-started.md")
    assert url is not None
    assert url.startswith("file:")


def test_guide_url_returns_none_when_missing():
    from hve.gui.help_content import guide_url

    assert guide_url("__not_exist__.md") is None
    assert guide_url("") is None


def test_options_fallback_keys_match_orchestrate_args():
    """フォールバック辞書のキーが OrchestrateArgs のフィールド名と整合することを検証。

    捏造防止のため、知らないキーが辞書に紛れていないかチェックする。
    """
    from dataclasses import fields

    from hve.gui.help_content import _OPTIONS_FALLBACK
    from hve.gui.orchestrate_args import OrchestrateArgs

    arg_field_names = {f.name for f in fields(OrchestrateArgs)}
    unknown = [k for k in _OPTIONS_FALLBACK if k not in arg_field_names]
    assert not unknown, f"OrchestrateArgs に存在しないキーが辞書にある: {unknown}"


def test_original_document_options_link_to_adi_guide() -> None:
    from hve.gui.help_content import _OPTIONS_GUIDE_HINT, WORKFLOW_GUIDE_MAP

    assert WORKFLOW_GUIDE_MAP["adi"] == "00-design-doc-ingestion.md"
    for key in ("target_scope", "depth", "focus_areas"):
        assert _OPTIONS_GUIDE_HINT[key] == "00-design-doc-ingestion.md"


def test_ai_agent_workflows_have_help_entries() -> None:
    """FR-GUI-21: AAG / AAGD / AAR にも説明文と実在するガイドがあること。"""
    from hve.gui.help_content import guide_url, workflow_help

    for wf_id in ("aag", "aagd", "aar"):
        entry = workflow_help(wf_id)
        assert entry.short, wf_id
        assert entry.guide_path.endswith(".md"), wf_id
        assert guide_url(entry.guide_path) is not None, entry.guide_path


def test_every_registered_workflow_has_help_entry() -> None:
    """FR-GUI-21: 登録済み全ワークフローが説明文とガイドパスを持つこと。"""
    from hve.gui.help_content import guide_url, workflow_help
    from hve.workflow_registry import list_workflows

    missing = []
    for wf in list_workflows():
        entry = workflow_help(wf.id)
        if not entry.short or guide_url(entry.guide_path) is None:
            missing.append(wf.id)
    assert missing == []

