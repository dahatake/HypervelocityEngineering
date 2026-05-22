"""hve.gui.workflow_display の書式テスト。"""

from __future__ import annotations

from hve.gui.workflow_display import (
    format_workflow_label,
    format_workflow_label_activity,
    format_workflow_label_html,
)


def test_explicit_name_and_id():
    assert (
        format_workflow_label("ard", "Auto Requirement Definition")
        == "Auto Requirement Definition (ARD)"
    )


def test_hyphenated_id_uppercased():
    assert (
        format_workflow_label("aad-web", "Web App Design")
        == "Web App Design (AAD-WEB)"
    )


def test_resolve_from_registry_when_name_missing():
    # registry に存在する ID は name 省略時に解決される
    assert format_workflow_label("ard") == "Auto Requirement Definition (ARD)"
    assert format_workflow_label("ard", "") == "Auto Requirement Definition (ARD)"


def test_resolve_from_registry_when_name_equals_id():
    # name が ID と同一（旧データ）の場合も registry で人間可読名に置換される
    assert format_workflow_label("aas", "aas") == "Architecture Design (AAS)"


def test_unknown_id_falls_back_to_id_only():
    # registry にも template_engine にも存在しない ID は ID のみ大文字で返す
    assert format_workflow_label("__nonexistent_workflow_zzz__") == (
        "(__NONEXISTENT_WORKFLOW_ZZZ__)"
    )


def test_abdv_uses_template_engine_display_name():
    """workflow_registry.name と template_engine 表示名が乖離する `adfdv` で
    template_engine 側の表示名（CLI/Issue タイトルと同一）を優先することを保証する。"""
    label = format_workflow_label("adfdv")
    # template_engine._WORKFLOW_DISPLAY_NAMES["adfdv"] == "Dataflow Dev & Deploy"
    assert label == "Dataflow Dev & Deploy (ADFDV)"


def test_empty_id_returns_name_or_empty():
    assert format_workflow_label("", "Some Name") == "Some Name"
    assert format_workflow_label("", "") == ""


def test_html_escape():
    out = format_workflow_label_html("x", "<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "(X)" in out


def test_html_uppercase_id():
    out = format_workflow_label_html("ard", "Auto Requirement Definition")
    assert out == "Auto Requirement Definition (ARD)"


def test_activity_explicit_name_and_id():
    assert (
        format_workflow_label_activity("ard", "Auto Requirement Definition")
        == "ARD-Auto Requirement Definition"
    )


def test_activity_resolve_from_registry_when_name_missing():
    assert (
        format_workflow_label_activity("ard")
        == "ARD-Auto Requirement Definition"
    )


def test_activity_hyphenated_id_uppercased():
    assert (
        format_workflow_label_activity("aad-web", "Web App Design")
        == "AAD-WEB-Web App Design"
    )


def test_activity_unknown_id_falls_back_to_id_only():
    assert (
        format_workflow_label_activity("__nonexistent_workflow_zzz__")
        == "__NONEXISTENT_WORKFLOW_ZZZ__"
    )


def test_activity_empty_id_returns_name_or_empty():
    assert format_workflow_label_activity("", "Some Name") == "Some Name"
    assert format_workflow_label_activity("", "") == ""
