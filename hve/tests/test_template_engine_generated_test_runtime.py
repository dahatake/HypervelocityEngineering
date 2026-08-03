"""Tests for generated-test runtime contract injection in template_engine."""

from __future__ import annotations

from typing import cast

from hve.template_engine import _inject_generated_test_runtime_section, render_template
from hve.workflow_registry import WorkflowDef, get_workflow


def test_injects_runtime_section_for_tdd_report_template_without_existing_section() -> None:
    body = """# TDD Step

## TDD テスト結果レポート（必須）
- 出力先: `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`
"""

    out = _inject_generated_test_runtime_section(body)

    assert "## 生成テストの実行環境" in out
    assert "ローカル端末 / CI" in out
    assert "環境変数" in out
    assert "秘密情報" in out


def test_does_not_duplicate_runtime_section() -> None:
    body = """# TDD Step

## 生成テストの実行環境
- 既存セクション

## TDD テスト結果レポート（必須）
- 出力先: `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`
"""

    out = _inject_generated_test_runtime_section(body)

    assert out.count("## 生成テストの実行環境") == 1
    assert "既存セクション" in out


def test_does_not_inject_runtime_section_for_non_tdd_template() -> None:
    body = "# Documentation Step\n\n通常の設計ドキュメントを生成する。"

    out = _inject_generated_test_runtime_section(body)

    assert out == body


def test_render_template_keeps_single_runtime_section_for_existing_tdd_template() -> None:
    wf = cast(WorkflowDef, get_workflow("asdw-web"))

    body = render_template(
        "templates/asdw-web/step-3.2.md",
        root_issue_num=1,
        params={"branch": "main"},
        wf=wf,
    )

    assert body.count("## 生成テストの実行環境") == 1
    assert "ローカル端末" in body
    assert "秘密情報" in body
