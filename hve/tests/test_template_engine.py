"""test_template_engine.py — hve/template_engine.py のテスト"""

import re
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from hve.template_engine import (
    _WORKFLOW_DISPLAY_NAMES,
    _WORKFLOW_PREFIX,
    _build_additional_section,
    _build_app_id_section,
    _build_completion_instruction,
    _build_job_section,
    _build_qa_review_context_section,
    _build_rg_section,
    _build_root_ref,
    _build_remote_mcp_server_design_section,
    _load_template,
    _normalize_bool,
    _TEMPLATES_BASE,
    build_root_issue_body,
    collect_params,
    render_template,
    resolve_selected_steps,
)
from hve.workflow_registry import get_workflow, StepDef, WorkflowDef


# ---------------------------------------------------------------------------
# _TEMPLATES_BASE パス検証
# ---------------------------------------------------------------------------


class TestTemplatesBase:
    def test_points_to_scripts(self):
        """_TEMPLATES_BASE が .github/scripts/ を指すこと。"""
        assert _TEMPLATES_BASE.name == "scripts"
        assert _TEMPLATES_BASE.parent.name == ".github"


# ---------------------------------------------------------------------------
# _load_template
# ---------------------------------------------------------------------------


class TestLoadTemplate:
    def test_load_existing(self):
        """実在するテンプレートが読み込めること。"""
        content = _load_template("templates/aas/step-1.md")
        assert "{root_ref}" in content

    def test_load_nonexistent(self, capsys):
        """存在しないテンプレートは空文字列を返し警告が出ること。"""
        result = _load_template("templates/nonexistent/step-999.md")
        assert result == ""
        captured = capsys.readouterr()
        assert "テンプレートが見つかりません" in captured.out


# ---------------------------------------------------------------------------
# _build_root_ref
# ---------------------------------------------------------------------------


class TestBuildRootRef:
    def test_minimal(self):
        ref = _build_root_ref(42)
        assert "<!-- root-issue: #42 -->" in ref
        assert "<!-- branch: main -->" in ref
        assert "<!-- auto-review: true -->" in ref
        assert "<!-- auto-context-review: true -->" in ref
        assert "<!-- auto-qa: true -->" in ref
        assert "<!-- auto-merge: false -->" in ref

    def test_with_params(self):
        ref = _build_root_ref(
            10,
            params={
                "branch": "develop",
                "skip_review": True,
                "skip_qa": True,
                "enable_auto_merge": True,
                "resource_group": "rg-test",
                "app_ids": ["APP-01", "APP-02"],
                "batch_job_id": "JOB-1,JOB-2",
            },
        )
        assert "<!-- branch: develop -->" in ref
        assert "<!-- auto-review: false -->" in ref
        assert "<!-- auto-qa: false -->" in ref
        assert "<!-- auto-merge: true -->" in ref
        assert "<!-- resource-group: rg-test -->" in ref
        assert "<!-- app-ids: APP-01, APP-02 -->" in ref
        assert "<!-- batch-job-ids: JOB-1,JOB-2 -->" in ref

    def test_with_app_id_legacy(self):
        """旧形式 app_id 単体でも app-ids として出力されること。"""
        ref = _build_root_ref(10, params={"app_id": "APP-01"})
        assert "<!-- app-ids: APP-01 -->" in ref
        assert "<!-- app-id:" not in ref

    def test_app_ids_list(self):
        """app_ids リストが app-ids コメントとして出力されること。"""
        ref = _build_root_ref(1, params={"app_ids": ["APP-01", "APP-02"]})
        assert "<!-- app-ids: APP-01, APP-02 -->" in ref

    def test_empty_optional_params_omitted(self):
        ref = _build_root_ref(1, params={"app_id": "", "resource_group": ""})
        assert "app-ids" not in ref
        assert "resource-group" not in ref


# ---------------------------------------------------------------------------
# _build_additional_section
# ---------------------------------------------------------------------------


class TestBuildAdditionalSection:
    def test_empty(self):
        assert _build_additional_section({}) == ""

    def test_with_comment(self):
        result = _build_additional_section({"additional_comment": "テスト用"})
        assert "## 追加コメント" in result
        assert "テスト用" in result


# ---------------------------------------------------------------------------
# _build_app_id_section
# ---------------------------------------------------------------------------


class TestBuildAppIdSection:
    def test_empty(self):
        assert _build_app_id_section("") == ""

    def test_empty_list(self):
        assert _build_app_id_section([]) == ""

    def test_with_id(self):
        result = _build_app_id_section("APP-05")
        assert "APP-05" in result
        assert "docs/catalog/app-catalog.md" in result

    def test_with_multiple_ids(self):
        result = _build_app_id_section(["APP-01", "APP-02", "APP-03"])
        assert "APP-01" in result
        assert "APP-02" in result
        assert "APP-03" in result
        assert "docs/catalog/app-catalog.md" in result

    def test_with_single_id_list(self):
        result = _build_app_id_section(["APP-05"])
        assert "APP-05" in result
        assert "docs/catalog/app-catalog.md" in result


# ---------------------------------------------------------------------------
# _build_rg_section / _build_job_section
# ---------------------------------------------------------------------------


class TestBuildRgJobSections:
    def test_rg_empty(self):
        assert _build_rg_section("") == ""

    def test_rg_with_value(self):
        result = _build_rg_section("my-rg")
        assert "`my-rg`" in result

    def test_job_empty(self):
        assert _build_job_section("") == ""

    def test_job_with_value(self):
        result = _build_job_section("BATCH-01")
        assert "`BATCH-01`" in result


class TestBuildCompletionInstruction:
    def test_github_mode(self):
        result = _build_completion_instruction("akm", "github")
        assert result == "- 完了時に自身に `akm:done` ラベルを付与すること"

    def test_local_mode(self):
        result = _build_completion_instruction("akm", "local")
        assert "出力ファイルが全て正常に生成" in result
        assert "`akm:done` ラベルの付与は不要" in result


# ---------------------------------------------------------------------------
# render_template
# ---------------------------------------------------------------------------


class TestRenderTemplate:
    def test_aas_step1(self):
        """AAS step-1 テンプレートが正しく展開されること。"""
        wf = get_workflow("aas")
        body = render_template(
            "templates/aas/step-1.md",
            root_issue_num=99,
            params={"branch": "main"},
            wf=wf,
        )
        assert "<!-- root-issue: #99 -->" in body
        assert "{root_ref}" not in body
        assert "{additional_section}" not in body

    def test_nonexistent_template(self):
        wf = get_workflow("aas")
        body = render_template(
            "templates/nope.md",
            root_issue_num=1,
            params={},
            wf=wf,
        )
        assert body == ""

    def test_asdw_placeholders(self):
        """ASDW テンプレートの固有プレースホルダが展開されること。"""
        wf = get_workflow("asdw")
        step = wf.get_step("1.1")
        if step and step.body_template_path:
            body = render_template(
                step.body_template_path,
                root_issue_num=50,
                params={"app_id": "APP-03", "resource_group": "rg-dev", "usecase_id": "UC-01"},
                wf=wf,
            )
            # app_id_section が展開されている
            if "{app_id_section}" in _load_template(step.body_template_path):
                assert "APP-03" in body
            # usecase_id プレースホルダが展開されている
            assert "{usecase_id}" not in body

    def test_adoc_placeholders(self):
        """ADOC テンプレートの固有プレースホルダが展開されること。"""
        wf = get_workflow("adoc")
        body = render_template(
            "templates/adoc/step-1.md",
            root_issue_num=60,
            params={
                "target_dirs": "src/,hve/",
                "exclude_patterns": "dist/,node_modules/",
                "doc_purpose": "all",
                "max_file_lines": 300,
            },
            wf=wf,
        )
        assert "{target_dirs}" not in body
        assert "{exclude_patterns}" not in body
        assert "{doc_purpose}" not in body
        assert "{max_file_lines}" not in body
        assert "`src/,hve/`" in body
        assert "`dist/,node_modules/`" in body
        assert "`all`" in body
        assert "`300` 行" in body

    def test_adoc_doc_purpose_default_all(self):
        """ADOC doc_purpose のデフォルトが all であること。"""
        wf = get_workflow("adoc")
        body = render_template(
            "templates/adoc/step-1.md",
            root_issue_num=61,
            params={},
            wf=wf,
        )
        assert "`all`" in body

    def test_aqod_placeholders(self):
        """AQOD テンプレートの固有プレースホルダが展開されること。"""
        wf = get_workflow("aqod")
        body = render_template(
            "templates/aqod/step-1.md",
            root_issue_num=70,
            params={
                "target_scope": "original-docs/",
                "depth": "lightweight",
                "focus_areas": "データ整合性",
            },
            wf=wf,
        )
        assert "{aqod_target_scope}" not in body
        assert "{aqod_depth}" not in body
        assert "{aqod_focus_areas}" not in body
        assert "`original-docs/`" in body
        assert "`lightweight`" in body
        assert "`データ整合性`" in body

    def test_ard_placeholders_with_missing_values(self):
        """ARD で company_name / target_business 未入力時も placeholder が残らないこと。"""
        wf = get_workflow("ard")
        body = render_template(
            "templates/ard/step-2.md",
            root_issue_num=71,
            params={
                "company_name": "",
                "target_business": "",
                "survey_period_years": 30,
                "target_region": "グローバル全体",
                "analysis_purpose": "中長期成長戦略の立案",
                "attached_docs": [],
            },
            wf=wf,
        )
        assert "{company_name}" not in body
        assert "{target_business}" not in body
        assert "`未指定`" in body

    def test_ard_step1_all_placeholders_expanded(self):
        """Phase B (Major No.15): ARD step-1 で全プレースホルダが展開されること。"""
        wf = get_workflow("ard")
        body = render_template(
            "templates/ard/step-1.md",
            root_issue_num=72,
            params={
                "company_name": "テスト株式会社",
                "survey_base_date": "2026-01-15",
                "survey_period_years": 20,
                "target_region": "日本国内",
                "analysis_purpose": "新規事業検討",
                "attached_docs": ["a.pdf", "b.xlsx"],
            },
            wf=wf,
        )
        for token in (
            "{company_name}",
            "{survey_base_date}",
            "{survey_period_years}",
            "{target_region}",
            "{analysis_purpose}",
            "{attached_docs}",
        ):
            assert token not in body, f"placeholder {token} not expanded"
        assert "テスト株式会社" in body
        assert "2026-01-15" in body
        assert "20" in body
        assert "日本国内" in body
        assert "a.pdf, b.xlsx" in body

    def test_ard_step1_defaults_when_params_missing(self):
        """Phase B: ARD step-1 で任意パラメータが空でも既定値で展開されること。"""
        wf = get_workflow("ard")
        body = render_template(
            "templates/ard/step-1.md",
            root_issue_num=73,
            params={"company_name": "X 社"},
            wf=wf,
        )
        for token in (
            "{survey_base_date}",
            "{survey_period_years}",
            "{target_region}",
            "{attached_docs}",
        ):
            assert token not in body
        assert "30" in body  # 既定 survey_period_years
        assert "グローバル全体" in body  # 既定 target_region
        assert "添付なし" in body  # 既定 attached_docs

    def test_completion_instruction_github_mode(self):
        wf = get_workflow("akm")
        body = render_template(
            "templates/akm/step-1.md",
            root_issue_num=70,
            params={"branch": "main"},
            wf=wf,
            execution_mode="github",
        )
        assert "- 完了時に自身に `akm:done` ラベルを付与すること" in body

    def test_completion_instruction_local_mode(self):
        wf = get_workflow("akm")
        body = render_template(
            "templates/akm/step-1.md",
            root_issue_num=70,
            params={"branch": "main"},
            wf=wf,
            execution_mode="local",
        )
        assert "ローカル実行のため `akm:done` ラベルの付与は不要です" in body
        assert "- 完了時に自身に `akm:done` ラベルを付与すること" not in body

    def test_completion_instruction_local_fallback_for_legacy_template(self):
        wf = get_workflow("akm")
        legacy = (
            "{root_ref}\n## 完了条件\n"
            "- 完了時に自身に `akm:done` ラベルを付与すること\n"
            "{additional_section}\n"
        )
        with patch("hve.template_engine._load_template", return_value=legacy):
            body = render_template(
                "templates/akm/step-1.md",
                root_issue_num=1,
                params={"branch": "main"},
                wf=wf,
                execution_mode="local",
            )
        assert "ローカル実行のため done ラベルの付与は不要です" in body
        assert "完了時に自身に `akm:done` ラベルを付与すること" not in body


class TestCollectParams:
    def test_aad_collect_params_with_multiple_app_ids(self):
        wf = get_workflow("aad")
        inputs = iter([
            "main",                  # branch
            "APP-01, APP-02",        # app_ids
            "",                      # create_remote_mcp_server (default=True)
            "",                      # selected_steps = all
            "n",                     # skip_review
            "n",                     # skip_qa
            "",                      # additional_comment
        ])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            params = collect_params(wf)
        assert params["branch"] == "main"
        assert params["app_ids"] == ["APP-01", "APP-02"]
        assert "app_id" not in params

    def test_adoc_collect_params(self):
        wf = get_workflow("adoc")
        inputs = iter([
            "main",                 # branch
            "src/,hve/",            # target_dirs
            "dist/,node_modules/",  # exclude_patterns
            "3",                    # doc_purpose -> refactoring
            "1000",                 # max_file_lines
            "",                     # selected_steps = all
            "n",                    # skip_review
            "n",                    # skip_qa
            "",                     # additional_comment
        ])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            params = collect_params(wf)
        assert params["branch"] == "main"
        assert params["target_dirs"] == "src/,hve/"
        assert params["exclude_patterns"] == "dist/,node_modules/"
        assert params["doc_purpose"] == "refactoring"
        assert params["max_file_lines"] == 1000

    def test_adoc_collect_params_retries_invalid_doc_purpose(self):
        wf = get_workflow("adoc")
        inputs = iter([
            "main",                # branch
            "",                    # target_dirs
            "",                    # exclude_patterns
            "5",                   # invalid doc_purpose
            "2",                   # valid doc_purpose -> onboarding
            "500",                 # max_file_lines
            "",                    # selected_steps = all
            "n",                   # skip_review
            "n",                   # skip_qa
            "",                    # additional_comment
        ])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            params = collect_params(wf)
        assert params["doc_purpose"] == "onboarding"

    def test_adoc_collect_params_retries_invalid_max_file_lines(self):
        wf = get_workflow("adoc")
        inputs = iter([
            "main",                # branch
            "",                    # target_dirs
            "",                    # exclude_patterns
            "1",                   # doc_purpose -> all
            "abc",                 # invalid max_file_lines
            "300",                 # valid max_file_lines
            "",                    # selected_steps = all
            "n",                   # skip_review
            "n",                   # skip_qa
            "",                    # additional_comment
        ])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            params = collect_params(wf)
        assert params["max_file_lines"] == 300

    def test_akm_collect_params_skips_auto_merge_prompt_when_no_pr(self):
        wf = get_workflow("akm")
        inputs = iter([
            "main",  # branch
            "1",     # sources -> qa
            "",      # target_files (default)
            "n",     # force_refresh
            "",      # custom_source_dir
            "",      # selected_steps = all
            "n",     # skip_review
            "n",     # skip_qa
            "",      # additional_comment
        ])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            params = collect_params(wf, will_create_pr=False)
        assert params["sources"] == "qa"
        assert params["enable_auto_merge"] is False

    def test_akm_collect_params_asks_auto_merge_prompt_when_pr(self):
        wf = get_workflow("akm")
        inputs = iter([
            "main",  # branch
            "1",     # sources -> qa
            "",      # target_files (default)
            "n",     # force_refresh
            "",      # custom_source_dir
            "y",     # enable_auto_merge
            "",      # selected_steps = all
            "n",     # skip_review
            "n",     # skip_qa
            "",      # additional_comment
        ])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            params = collect_params(wf, will_create_pr=True)
        assert params["sources"] == "qa"
        assert params["enable_auto_merge"] is True


# ---------------------------------------------------------------------------
# resolve_selected_steps
# ---------------------------------------------------------------------------


class TestResolveSelectedSteps:
    def test_empty_returns_all(self):
        # Sub-4 (B-1): AAS Step 4 が 4.1 / 4.2 に分割された
        wf = get_workflow("aas")
        result = resolve_selected_steps(wf, [])
        assert result == {"1", "2", "3.1", "3.2", "4.1", "4.2", "5", "6", "7"}

    def test_specific_steps(self):
        wf = get_workflow("aad-web")
        result = resolve_selected_steps(wf, ["2.1", "2.2"])
        assert "2.1" in result
        assert "2.2" in result

    def test_unknown_steps_excluded(self, capsys):
        # Sub-4 (B-1): AAS Step 4 が 4.1 / 4.2 に分割された
        wf = get_workflow("aas")
        result = resolve_selected_steps(wf, ["999"])
        captured = capsys.readouterr()
        assert "未知の Step ID" in captured.out
        # 有効な選択がないので全ステップにフォールバック
        assert result == {"1", "2", "3.1", "3.2", "4.1", "4.2", "5", "6", "7"}

    def test_mixed_valid_invalid(self, capsys):
        wf = get_workflow("aad-web")
        result = resolve_selected_steps(wf, ["2.1", "INVALID"])
        captured = capsys.readouterr()
        assert "未知の Step ID" in captured.out
        assert "2.1" in result
        assert "INVALID" not in result

    def test_container_not_added_without_children(self):
        wf = get_workflow("asdw-web")
        result = resolve_selected_steps(wf, ["2.3T"])
        assert "2.3T" in result
        # 親コンテナ "2" が追加される
        assert "2" in result
        # 無関係なコンテナ "1" は含まれない
        assert "1" not in result


# ---------------------------------------------------------------------------
# build_root_issue_body
# ---------------------------------------------------------------------------


class TestBuildRootIssueBody:
    def test_aas(self):
        wf = get_workflow("aas")
        body = build_root_issue_body(wf, {"branch": "main"})
        assert "# [AAS] Architecture Design" in body
        assert "<!-- branch: main -->" in body
        assert "ワークフロー: **Architecture Design**" in body

    def test_asdw_with_params(self):
        wf = get_workflow("asdw")
        body = build_root_issue_body(wf, {
            "branch": "feature/x",
            "app_ids": ["APP-05"],
            "app_id": "APP-05",
            "enable_auto_merge": True,
            "resource_group": "rg-prod",
            "usecase_id": "UC-42",
        })
        assert "# [ASDW-WEB]" in body
        assert "<!-- auto-merge: true -->" in body
        assert "<!-- app-ids: APP-05 -->" in body
        assert "<!-- resource-group: rg-prod -->" in body
        assert "APP-ID: `APP-05`" in body
        assert "リソースグループ: `rg-prod`" in body
        assert "ユースケースID: `UC-42`" in body

    def test_asdw_with_multiple_app_ids(self):
        wf = get_workflow("asdw")
        body = build_root_issue_body(wf, {
            "branch": "feature/x",
            "app_ids": ["APP-01", "APP-02"],
        })
        assert "<!-- app-ids: APP-01, APP-02 -->" in body
        assert "APP-ID: `APP-01`, `APP-02`" in body

    def test_additional_comment(self):
        wf = get_workflow("abd")
        body = build_root_issue_body(wf, {
            "branch": "main",
            "additional_comment": "初回テスト",
        })
        assert "## 追加コメント" in body
        assert "初回テスト" in body

    def test_abdv_batch_job_id(self):
        wf = get_workflow("abdv")
        body = build_root_issue_body(wf, {
            "branch": "main",
            "batch_job_id": "JOB-A,JOB-B",
        })
        assert "<!-- batch-job-ids: JOB-A,JOB-B -->" in body
        assert "バッチジョブ ID: `JOB-A,JOB-B`" in body

    def test_adoc_title_prefix(self):
        wf = get_workflow("adoc")
        body = build_root_issue_body(wf, {"branch": "main"})
        assert "# [ADOC] Source Codeからのドキュメント作成" in body


class TestWorkflowNameMappings:
    def test_display_names_include_new_workflows_and_aliases(self):
        assert _WORKFLOW_DISPLAY_NAMES["aas"] == "Architecture Design"
        assert _WORKFLOW_DISPLAY_NAMES["aad-web"] == "Web App Design"
        assert _WORKFLOW_DISPLAY_NAMES["asdw-web"] == "Web App Dev & Deploy"
        assert _WORKFLOW_DISPLAY_NAMES["aag"] == "AI Agent Design"
        assert _WORKFLOW_DISPLAY_NAMES["aagd"] == "AI Agent Dev & Deploy"
        assert _WORKFLOW_DISPLAY_NAMES["aad"] == "Web App Design"
        assert _WORKFLOW_DISPLAY_NAMES["asdw"] == "Web App Dev & Deploy"

    def test_prefixes_include_new_workflows_and_aliases(self):
        assert _WORKFLOW_PREFIX["aas"] == "AAS"
        assert _WORKFLOW_PREFIX["aad-web"] == "AAD-WEB"
        assert _WORKFLOW_PREFIX["asdw-web"] == "ASDW-WEB"
        assert _WORKFLOW_PREFIX["aag"] == "AAG"
        assert _WORKFLOW_PREFIX["aagd"] == "AAGD"
        assert _WORKFLOW_PREFIX["aad"] == "AAD-WEB"
        assert _WORKFLOW_PREFIX["asdw"] == "ASDW-WEB"


# ---------------------------------------------------------------------------
# 全テンプレートに {additional_section} が含まれること
# ---------------------------------------------------------------------------


class TestAllTemplatesHaveAdditionalSection:
    def test_all_templates_have_placeholder(self):
        """全テンプレートファイルに {additional_section} プレースホルダが含まれること。"""
        templates_dir = _TEMPLATES_BASE / "templates"
        missing = []
        for md_file in sorted(templates_dir.rglob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            if "{additional_section}" not in content:
                missing.append(str(md_file.relative_to(templates_dir)))
        assert not missing, f"以下のテンプレートに {{additional_section}} がありません: {missing}"

    def test_no_legacy_done_instruction_in_templates(self):
        templates_dir = _TEMPLATES_BASE / "templates"
        legacy_patterns = []
        for md_file in sorted(templates_dir.rglob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            if (
                "完了時に自身に `" in content and ":done` ラベルを付与すること" in content
            ) or ("完了時に `" in content and ":done` を付与すること" in content):
                legacy_patterns.append(str(md_file.relative_to(templates_dir)))
        assert not legacy_patterns, f"以下のテンプレートに旧 done 指示が残っています: {legacy_patterns}"


# ---------------------------------------------------------------------------
# render_template で追加コメントが展開されること
# ---------------------------------------------------------------------------


class TestRenderTemplateAdditionalComment:
    def test_additional_comment_rendered_in_body(self):
        """追加コメントが render_template で展開されること。"""
        wf = get_workflow("asdw")
        body = render_template(
            "templates/asdw/step-2.1.md",
            root_issue_num=99,
            params={"additional_comment": "Vue.jsで作成する", "branch": "main"},
            wf=wf,
        )
        assert "## 追加コメント" in body
        assert "Vue.jsで作成する" in body

    def test_no_additional_comment_leaves_no_placeholder(self):
        """追加コメントなしの場合 {additional_section} が残らないこと。"""
        wf = get_workflow("asdw")
        body = render_template(
            "templates/asdw/step-2.1.md",
            root_issue_num=99,
            params={"branch": "main"},
            wf=wf,
        )
        assert "{additional_section}" not in body
        assert "## 追加コメント" not in body


# ---------------------------------------------------------------------------
# Phase 3: QA / Review コンテキスト参照セクションの注入検証
# ---------------------------------------------------------------------------


class TestQaReviewContextSection:
    """Phase 3: _build_qa_review_context_section と render_template への注入を検証する。"""

    def test_section_is_non_empty_string(self):
        """`_build_qa_review_context_section()` が空でない文字列を返すこと。"""
        section = _build_qa_review_context_section()
        assert isinstance(section, str)
        assert len(section.strip()) > 0

    def test_section_contains_qa_reference(self):
        """`qa/` への参照が含まれること。"""
        assert "qa/" in _build_qa_review_context_section()

    def test_section_contains_review_reference(self):
        """レビュー指摘への参照が含まれること。"""
        assert "レビュー指摘" in _build_qa_review_context_section()

    def test_section_contains_reflect_instruction(self):
        """成果物反映指示が含まれること。"""
        assert "成果物へ反映" in _build_qa_review_context_section()

    def test_section_contains_no_fabrication(self):
        """存在しない情報を推測しない旨の記述が含まれること。"""
        assert "推測せず" in _build_qa_review_context_section()

    def test_section_contains_reason_recording(self):
        """未反映時の理由記録指示が含まれること。"""
        assert "理由を完了コメントまたは成果物内に記録" in _build_qa_review_context_section()

    def test_rendered_template_contains_qa_review_section(self):
        """render_template の出力に QA / Review コンテキスト参照セクションが含まれること。"""
        wf = get_workflow("aas")
        body = render_template(
            "templates/aas/step-1.md",
            root_issue_num=1,
            params={"branch": "main"},
            wf=wf,
        )
        assert "## 追加コンテキストの参照" in body
        assert "qa/" in body

    def test_rendered_template_qa_section_precedes_additional_comment(self):
        """QA / Review コンテキストセクションが追加コメントより前に現れること。"""
        wf = get_workflow("aas")
        body = render_template(
            "templates/aas/step-1.md",
            root_issue_num=1,
            params={"branch": "main", "additional_comment": "追加テスト"},
            wf=wf,
        )
        qa_pos = body.find("## 追加コンテキストの参照")
        comment_pos = body.find("追加テスト")
        assert qa_pos != -1
        assert comment_pos != -1
        assert qa_pos < comment_pos

    def test_all_templates_get_qa_review_section(self):
        """全テンプレートのレンダリング結果に QA/Review 参照セクションが含まれること。"""
        templates_dir = _TEMPLATES_BASE / "templates"
        missing = []
        for md_file in sorted(templates_dir.rglob("*.md")):
            rel = str(md_file.relative_to(_TEMPLATES_BASE))  # e.g. "templates/aas/step-1.md"
            wf_id = md_file.parts[-2]  # e.g. "aas"
            try:
                wf = get_workflow(wf_id)
            except Exception:
                continue
            body = render_template(rel, root_issue_num=1, params={"branch": "main"}, wf=wf)
            if body and "## 追加コンテキストの参照" not in body:
                missing.append(rel)
        assert not missing, f"以下のテンプレートに QA/Review 参照セクションがありません: {missing}"


# ---------------------------------------------------------------------------
# Phase 5: workflow_registry の body_template_path と custom_agent の整合性検証
# ---------------------------------------------------------------------------


class TestRegistryTemplateConsistencyPhase5:
    """Phase 5: workflow_registry.py の body_template_path 存在確認と custom_agent 整合性検証。

    外部 API に依存しない静的テストとして実装する。
    custom_agent が一致しない既知の例外は ALLOWLIST で管理する。
    """

    # 既知の不一致を許容する template_path のリスト。
    # 実際に不一致があり意図的に許容する場合のみここに追加する。
    _CUSTOM_AGENT_ALLOWLIST: list[str] = []

    def _collect_registry_steps(self) -> list[tuple[str, str | None]]:
        """workflow_registry の全ワークフローから (body_template_path, custom_agent) ペアを収集する。

        workflow_registry モジュールを直接 import して走査するため、
        StepDef 引数の順序や title 内の ')' に依存しない。
        """
        from hve.workflow_registry import list_workflows
        results = []
        for wf in list_workflows():
            for step in wf.steps:
                if step.body_template_path and step.custom_agent:
                    results.append((step.body_template_path, step.custom_agent))
        return results

    def test_all_body_template_paths_exist(self) -> None:
        """workflow_registry.py の全 body_template_path ファイルが .github/scripts/ 配下に存在すること。"""
        missing = []
        for tpl_path, _ in self._collect_registry_steps():
            full = _TEMPLATES_BASE / tpl_path
            if not full.exists():
                missing.append(tpl_path)
        assert not missing, (
            f"以下の body_template_path が .github/scripts/ 配下に存在しません: {missing}"
        )

    def test_template_custom_agent_matches_registry(self) -> None:
        """各テンプレートの '## Custom Agent' 行が workflow_registry.py の custom_agent と一致すること。

        不一致が許容される既知ケースは _CUSTOM_AGENT_ALLOWLIST で管理する。
        """
        mismatches = []
        for tpl_path, registry_agent in self._collect_registry_steps():
            if tpl_path in self._CUSTOM_AGENT_ALLOWLIST:
                continue
            full = _TEMPLATES_BASE / tpl_path
            if not full.exists():
                continue  # 存在確認は別テストで行う

            content = full.read_text(encoding="utf-8")
            match = re.search(r"## Custom Agent\n`([^`]+)`", content)
            if match:
                tpl_agent = match.group(1)
                if tpl_agent != registry_agent:
                    mismatches.append(
                        f"{tpl_path}: registry='{registry_agent}', template='{tpl_agent}'"
                    )
            # ## Custom Agent セクションがないテンプレートは比較対象外（コンテナ Step 等）

        assert not mismatches, (
            "以下のテンプレートで ## Custom Agent と workflow_registry.py の custom_agent が一致しません。\n"
            "意図的な不一致は _CUSTOM_AGENT_ALLOWLIST に追加してください:\n"
            + "\n".join(mismatches)
        )


# ---------------------------------------------------------------------------
# Remote MCP Server セクション展開テスト
# ---------------------------------------------------------------------------


class TestRemoteMcpServerSection:
    """``{remote_mcp_server_section}`` プレースホルダの展開を検証する。"""

    def test_placeholder_not_exposed_when_false(self):
        """create_remote_mcp_server=False のとき {remote_mcp_server_section} が残らないこと。"""
        wf = get_workflow("asdw-web")
        body = render_template(
            "templates/asdw-web/step-2.5.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": False},
            wf=wf,
        )
        assert "{remote_mcp_server_section}" not in body
        assert "## Remote MCP Server 実装" not in body

    def test_placeholder_not_exposed_when_true(self):
        """create_remote_mcp_server=True のとき {remote_mcp_server_section} が残らないこと。"""
        wf = get_workflow("asdw-web")
        body = render_template(
            "templates/asdw-web/step-2.5.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": True},
            wf=wf,
        )
        assert "{remote_mcp_server_section}" not in body
        assert "## Remote MCP Server 実装" in body

    def test_placeholder_not_exposed_default(self):
        """create_remote_mcp_server が未指定（後方互換）のとき {remote_mcp_server_section} が残らないこと。"""
        wf = get_workflow("asdw-web")
        body = render_template(
            "templates/asdw-web/step-2.5.md",
            root_issue_num=1,
            params={"branch": "main"},
            wf=wf,
        )
        assert "{remote_mcp_server_section}" not in body
        # デフォルト True なのでセクションが含まれる
        assert "## Remote MCP Server 実装" in body

    def test_mcp_section_content_when_true(self):
        """create_remote_mcp_server=True のとき MCP セクションの主要コンテンツが含まれること。"""
        wf = get_workflow("asdw-web")
        body = render_template(
            "templates/asdw-web/step-2.5.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": True},
            wf=wf,
        )
        assert "### 基本方針" in body
        assert "### 実装時の検討事項" in body
        assert "疎結合" in body

    def test_root_ref_includes_create_remote_mcp_server_true(self):
        """_build_root_ref に create-remote-mcp-server: true が含まれること。"""
        from hve.template_engine import _build_root_ref
        root_ref = _build_root_ref(5, {"branch": "main", "create_remote_mcp_server": True})
        assert "<!-- create-remote-mcp-server: true -->" in root_ref

    def test_root_ref_includes_create_remote_mcp_server_false(self):
        """_build_root_ref に create-remote-mcp-server: false が含まれること。"""
        from hve.template_engine import _build_root_ref
        root_ref = _build_root_ref(5, {"branch": "main", "create_remote_mcp_server": False})
        assert "<!-- create-remote-mcp-server: false -->" in root_ref

    def test_root_ref_default_true(self):
        """create_remote_mcp_server 未指定のとき _build_root_ref に true が含まれること（後方互換）。"""
        from hve.template_engine import _build_root_ref
        root_ref = _build_root_ref(5, {"branch": "main"})
        assert "<!-- create-remote-mcp-server: true -->" in root_ref

    def test_build_root_issue_body_asdw_includes_metadata(self):
        """asdw-web の build_root_issue_body に create-remote-mcp-server メタデータが含まれること。"""
        wf = get_workflow("asdw-web")
        body = build_root_issue_body(wf, {"branch": "main", "create_remote_mcp_server": False})
        assert "<!-- create-remote-mcp-server: false -->" in body

    def test_string_false_suppresses_mcp_section(self):
        """create_remote_mcp_server が文字列 "false" のとき Remote MCP Server セクションが出力されないこと。"""
        wf = get_workflow("asdw-web")
        body = render_template(
            "templates/asdw-web/step-2.5.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": "false"},
            wf=wf,
        )
        assert "{remote_mcp_server_section}" not in body
        assert "## Remote MCP Server 実装" not in body

    def test_string_true_includes_mcp_section(self):
        """create_remote_mcp_server が文字列 "true" のとき Remote MCP Server セクションが出力されること。"""
        wf = get_workflow("asdw-web")
        body = render_template(
            "templates/asdw-web/step-2.5.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": "true"},
            wf=wf,
        )
        assert "{remote_mcp_server_section}" not in body
        assert "## Remote MCP Server 実装" in body

    def test_string_no_suppresses_mcp_section(self):
        """create_remote_mcp_server が文字列 "no" のとき Remote MCP Server セクションが出力されないこと。"""
        wf = get_workflow("asdw-web")
        body = render_template(
            "templates/asdw-web/step-2.5.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": "no"},
            wf=wf,
        )
        assert "{remote_mcp_server_section}" not in body
        assert "## Remote MCP Server 実装" not in body

    def test_string_sakusei_shinai_suppresses_mcp_section(self):
        """create_remote_mcp_server が "作成しない" のとき Remote MCP Server セクションが出力されないこと。"""
        wf = get_workflow("asdw-web")
        body = render_template(
            "templates/asdw-web/step-2.5.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": "作成しない"},
            wf=wf,
        )
        assert "{remote_mcp_server_section}" not in body
        assert "## Remote MCP Server 実装" not in body

    # --- AAD-WEB 設計フェーズ向けテスト ---

    def test_aad_web_step22_includes_design_section_when_true(self):
        """create_remote_mcp_server=True のとき step-2.2.md に設計観点セクションが含まれること。"""
        wf = get_workflow("aad-web")
        body = render_template(
            "templates/aad-web/step-2.2.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": True},
            wf=wf,
        )
        assert "{remote_mcp_server_design_section}" not in body
        assert "## Remote MCP Server 設計観点" in body
        assert "adapter 層" in body
        assert "設計で固定しないこと" in body

    def test_aad_web_step22_suppresses_design_section_when_false(self):
        """create_remote_mcp_server=False のとき step-2.2.md に設計観点セクションが含まれないこと。"""
        wf = get_workflow("aad-web")
        body = render_template(
            "templates/aad-web/step-2.2.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": False},
            wf=wf,
        )
        assert "{remote_mcp_server_design_section}" not in body
        assert "## Remote MCP Server 設計観点" not in body

    def test_aad_web_step22_default_true_includes_design_section(self):
        """create_remote_mcp_server 未指定のとき step-2.2.md に設計観点セクションが含まれること（後方互換）。"""
        wf = get_workflow("aad-web")
        body = render_template(
            "templates/aad-web/step-2.2.md",
            root_issue_num=1,
            params={"branch": "main"},
            wf=wf,
        )
        assert "## Remote MCP Server 設計観点" in body

    def test_aad_web_step22_sakusei_shinai_suppresses_design_section(self):
        """create_remote_mcp_server が "作成しない" のとき step-2.2.md に設計観点セクションが含まれないこと。"""
        wf = get_workflow("aad-web")
        body = render_template(
            "templates/aad-web/step-2.2.md",
            root_issue_num=1,
            params={"branch": "main", "create_remote_mcp_server": "作成しない"},
            wf=wf,
        )
        assert "## Remote MCP Server 設計観点" not in body

    def test_build_root_issue_body_aad_includes_metadata(self):
        """aad-web の build_root_issue_body に create-remote-mcp-server メタデータが含まれること。"""
        wf = get_workflow("aad-web")
        body = build_root_issue_body(wf, {"branch": "main", "create_remote_mcp_server": True})
        assert "<!-- create-remote-mcp-server: true -->" in body

    def test_design_section_no_technology_specifics(self):
        """設計観点セクションに特定技術（Azure Functions / SDK）を固定する記述が含まれないこと。"""
        section = _build_remote_mcp_server_design_section(True)
        assert "Azure Functions" not in section
        assert "CI/CD" not in section


class TestNormalizeBool:
    """_normalize_bool() のテスト。"""

    @pytest.mark.parametrize("value", [True, "true", "1", "yes", "y", "on", "作成する"])
    def test_truthy_values(self, value):
        """truthy な値はすべて True に正規化されること。"""
        assert _normalize_bool(value) is True

    @pytest.mark.parametrize("value", [False, "false", "0", "no", "n", "off", "作成しない"])
    def test_falsy_values(self, value):
        """falsy な値はすべて False に正規化されること。"""
        assert _normalize_bool(value) is False

    def test_none_returns_default_true(self):
        """None は default=True を返すこと。"""
        assert _normalize_bool(None, default=True) is True

    def test_none_returns_default_false(self):
        """None は default=False を返すこと。"""
        assert _normalize_bool(None, default=False) is False

    def test_unknown_string_returns_default(self):
        """不明文字列は default を返すこと。"""
        assert _normalize_bool("unknown", default=True) is True
        assert _normalize_bool("unknown", default=False) is False

    def test_bool_param_str_string_false_normalizes_correctly(self):
        """_get_bool_param_str が文字列 "false" を正しく "false" に正規化すること。"""
        from hve.template_engine import _get_bool_param_str
        assert _get_bool_param_str({"key": "false"}, "key") == "false"

    def test_bool_param_str_string_true_normalizes_correctly(self):
        """_get_bool_param_str が文字列 "true" を正しく "true" に正規化すること。"""
        from hve.template_engine import _get_bool_param_str
        assert _get_bool_param_str({"key": "true"}, "key") == "true"

    def test_bool_param_str_missing_key_defaults_to_true(self):
        """_get_bool_param_str はキー未指定のとき default=True の "true" を返すこと。"""
        from hve.template_engine import _get_bool_param_str
        assert _get_bool_param_str({}, "missing_key") == "true"

    def test_bool_param_str_missing_key_defaults_to_false(self):
        """_get_bool_param_str はキー未指定のとき default=False の "false" を返すこと。"""
        from hve.template_engine import _get_bool_param_str
        assert _get_bool_param_str({}, "missing_key", default=False) == "false"


# ---------------------------------------------------------------------------
# Phase 2: Agentic Retrieval 質問項目 - 静的サニティチェック
# ---------------------------------------------------------------------------

class TestAgenticRetrievalConstants:
    """_AGENTIC_RETRIEVAL_QUESTIONS 定数と Issue Form YAML の整合性検証。

    Phase 7 で同期テストを追加するための土台として、
    最低限の構造チェックを行う。
    """

    _REPO_ROOT = Path(__file__).resolve().parents[2]
    _TEMPLATE_DIR = _REPO_ROOT / ".github" / "ISSUE_TEMPLATE"

    def test_questions_keys_are_snake_case(self):
        """全キーが snake_case であること（Issue Form id との整合）。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS
        import re
        for key in _AGENTIC_RETRIEVAL_QUESTIONS:
            assert re.match(r'^[a-z][a-z0-9_]*$', key), \
                f"キー '{key}' は snake_case でありません"

    def test_questions_required_fields(self):
        """各質問に必須フィールドが存在すること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS
        required = {"label", "description", "kind", "default", "applies_to"}
        for key, q in _AGENTIC_RETRIEVAL_QUESTIONS.items():
            missing = required - set(q.keys())
            assert not missing, f"質問 '{key}' に必須フィールドが不足: {missing}"

    def test_questions_applies_to_valid_workflow_ids(self):
        """applies_to に指定されるワークフロー ID が有効であること。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_QUESTIONS
        valid_ids = {"aad-web", "asdw-web"}
        for key, q in _AGENTIC_RETRIEVAL_QUESTIONS.items():
            for wf_id in q["applies_to"]:
                assert wf_id in valid_ids, \
                    f"質問 '{key}' の applies_to に無効なワークフロー ID: {wf_id}"

    def test_aad_web_has_q1_and_q3_only(self):
        """AAD-WEB 適用質問は Q1(enable_agentic_retrieval) と Q3(foundry_mcp_integration) のみ。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_KEYS_FOR
        aad_keys = _AGENTIC_RETRIEVAL_KEYS_FOR["aad-web"]
        assert "enable_agentic_retrieval" in aad_keys
        assert "foundry_mcp_integration" in aad_keys
        # ASDW-WEB 専用キーは AAD-WEB に含まれないこと
        asdw_only = {
            "agentic_data_source_modes",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        }
        for key in asdw_only:
            assert key not in aad_keys, f"AAD-WEB に ASDW-WEB 専用キー '{key}' が含まれています"

    def test_asdw_web_has_all_six_questions(self):
        """ASDW-WEB 適用質問は Q1〜Q6 の 6 つ全て。"""
        from hve.template_engine import _AGENTIC_RETRIEVAL_KEYS_FOR, _AGENTIC_RETRIEVAL_QUESTIONS
        asdw_keys = set(_AGENTIC_RETRIEVAL_KEYS_FOR["asdw-web"])
        expected = {
            "enable_agentic_retrieval",
            "agentic_data_source_modes",
            "foundry_mcp_integration",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        }
        assert asdw_keys == expected, \
            f"ASDW-WEB キー不一致: 期待={expected} 実際={asdw_keys}"

    def test_issue_form_yaml_contains_agentic_ids_aad_web(self):
        """AAD-WEB Issue Template が Q1・Q3 の id を持つこと。"""
        content = (self._TEMPLATE_DIR / "web-app-design.yml").read_text(encoding="utf-8")
        assert "id: enable_agentic_retrieval" in content
        assert "id: foundry_mcp_integration" in content

    def test_issue_form_yaml_contains_agentic_ids_asdw_web(self):
        """ASDW-WEB Issue Template が Q1〜Q6 の id を持つこと。"""
        content = (self._TEMPLATE_DIR / "web-app-dev.yml").read_text(encoding="utf-8")
        for field_id in [
            "enable_agentic_retrieval",
            "agentic_data_source_modes",
            "foundry_mcp_integration",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        ]:
            assert f"id: {field_id}" in content, \
                f"web-app-dev.yml に id: {field_id} が見つかりません"

    def test_normalize_no_disables_foundry_fields(self):
        """enable_agentic_retrieval=no（内部値）のとき Q3/Q6 が無効化されること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers
        answers = {
            "enable_agentic_retrieval": "no",
            "foundry_mcp_integration": "する",
            "foundry_sku_fallback_policy": "Global 必須（Standard 拒否）",
        }
        result = normalize_agentic_retrieval_answers(answers)
        assert result["foundry_mcp_integration"] is False
        assert result["foundry_sku_fallback_policy"] == "standard_allowed"

    def test_normalize_japanese_shinai_disables_foundry_fields(self):
        """enable_agentic_retrieval=「しない」（UI 表示値）のとき Q3/Q6 が無効化されること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers
        answers = {
            "enable_agentic_retrieval": "しない",
            "foundry_mcp_integration": "する",
            "foundry_sku_fallback_policy": "Global 必須（Standard 拒否）",
        }
        result = normalize_agentic_retrieval_answers(answers)
        assert result["foundry_mcp_integration"] is False
        assert result["foundry_sku_fallback_policy"] == "standard_allowed"

    def test_normalize_auto_preserves_values(self):
        """enable_agentic_retrieval=auto のとき Q3/Q6 はユーザー入力値を保持すること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers
        answers = {
            "enable_agentic_retrieval": "auto",
            "foundry_mcp_integration": "する",
            "foundry_sku_fallback_policy": "Global 必須（Standard 拒否）",
        }
        result = normalize_agentic_retrieval_answers(answers)
        assert result["foundry_mcp_integration"] == "する"
        assert result["foundry_sku_fallback_policy"] == "Global 必須（Standard 拒否）"

    def test_normalize_japanese_jidohantei_preserves_values(self):
        """enable_agentic_retrieval=「自動判定に従う」（UI 表示値）のとき Q3/Q6 はユーザー入力値を保持すること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers
        answers = {
            "enable_agentic_retrieval": "自動判定に従う",
            "foundry_mcp_integration": "する",
            "foundry_sku_fallback_policy": "Global 必須（Standard 拒否）",
        }
        result = normalize_agentic_retrieval_answers(answers)
        assert result["foundry_mcp_integration"] == "する"
        assert result["foundry_sku_fallback_policy"] == "Global 必須（Standard 拒否）"

    def test_normalize_yes_preserves_values(self):
        """enable_agentic_retrieval=yes のとき Q3/Q6 はユーザー入力値を保持すること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers
        answers = {
            "enable_agentic_retrieval": "yes",
            "foundry_mcp_integration": "しない",
            "foundry_sku_fallback_policy": "Standard 許容",
        }
        result = normalize_agentic_retrieval_answers(answers)
        assert result["foundry_mcp_integration"] == "しない"
        assert result["foundry_sku_fallback_policy"] == "Standard 許容"

    def test_normalize_japanese_suru_preserves_values(self):
        """enable_agentic_retrieval=「する」（UI 表示値）のとき Q3/Q6 はユーザー入力値を保持すること。"""
        from hve.template_engine import normalize_agentic_retrieval_answers
        answers = {
            "enable_agentic_retrieval": "する",
            "foundry_mcp_integration": "しない",
            "foundry_sku_fallback_policy": "Standard 許容",
        }
        result = normalize_agentic_retrieval_answers(answers)
        assert result["foundry_mcp_integration"] == "しない"
        assert result["foundry_sku_fallback_policy"] == "Standard 許容"

    def test_config_has_agentic_fields(self):
        """SDKConfig に 6 フィールドが存在し、デフォルト値が仕様通りであること。"""
        from hve.config import SDKConfig
        cfg = SDKConfig()
        assert cfg.enable_agentic_retrieval == "auto"
        assert cfg.agentic_data_source_modes == ["indexer"]
        assert cfg.foundry_mcp_integration is True
        assert cfg.agentic_data_sources_hint == ""
        assert cfg.agentic_existing_design_diff_only is False
        assert cfg.foundry_sku_fallback_policy == "standard_allowed"

    def test_run_state_safe_config_fields_include_agentic(self):
        """_SAFE_CONFIG_FIELDS に 6 フィールドが全て含まれること。"""
        from hve.run_state import _SAFE_CONFIG_FIELDS
        expected = {
            "enable_agentic_retrieval",
            "agentic_data_source_modes",
            "foundry_mcp_integration",
            "agentic_data_sources_hint",
            "agentic_existing_design_diff_only",
            "foundry_sku_fallback_policy",
        }
        for field in expected:
            assert field in _SAFE_CONFIG_FIELDS, \
                f"_SAFE_CONFIG_FIELDS に '{field}' が含まれていません"

    def test_to_safe_config_dict_includes_agentic_fields(self):
        """to_safe_config_dict が 6 フィールドを正しく snapshot に含めること。"""
        from hve.config import SDKConfig
        from hve.run_state import to_safe_config_dict
        cfg = SDKConfig()
        snapshot = to_safe_config_dict(cfg)
        assert snapshot["enable_agentic_retrieval"] == "auto"
        assert snapshot["agentic_data_source_modes"] == ["indexer"]
        assert snapshot["foundry_mcp_integration"] is True
        assert snapshot["agentic_data_sources_hint"] == ""
        assert snapshot["agentic_existing_design_diff_only"] is False
        assert snapshot["foundry_sku_fallback_policy"] == "standard_allowed"

    def test_backward_compat_load_state_without_agentic_fields(self):
        """既存 state.json（新フィールドなし）を読み込んでもクラッシュしないこと。"""
        import json
        import tempfile
        from pathlib import Path
        from hve.run_state import RunState
        # 新フィールドを含まない古い state.json を模倣
        old_state = {
            "schema_version": "1.0",
            "run_id": "20260101T000000-abc123",
            "session_name": "test session",
            "workflow_id": "aad-web",
            "status": "paused",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_updated_at": "2026-01-01T00:00:00+00:00",
            "pause_reason": None,
            "host": {},
            "config_snapshot": {
                "model": "claude-opus-4.7",
                # Agentic Retrieval フィールドは意図的に含めない
            },
            "params_snapshot": {},
            "selected_step_ids": [],
            "step_states": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "20260101T000000-abc123"
            run_dir.mkdir()
            (run_dir / "state.json").write_text(
                json.dumps(old_state), encoding="utf-8"
            )
            loaded = RunState.load("20260101T000000-abc123", work_dir=Path(tmpdir))
            # config_snapshot は dict なので新フィールドが無い場合は .get() でデフォルト取得可能
            snap = loaded.config_snapshot
            assert snap.get("enable_agentic_retrieval", "auto") == "auto"
            assert snap.get("agentic_data_source_modes", ["indexer"]) == ["indexer"]
            assert snap.get("foundry_mcp_integration", True) is True
