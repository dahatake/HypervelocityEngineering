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


def test_category_help_all_16_present():
    """C1〜C16 のすべてに説明文があることを確認。"""
    from hve.gui.help_content import category_help

    for i in range(1, 17):
        key = f"C{i}"
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
