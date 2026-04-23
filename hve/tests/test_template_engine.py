"""test_template_engine.py — hve/template_engine.py のテスト"""

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from hve.template_engine import (
    _build_additional_section,
    _build_app_id_section,
    _build_job_section,
    _build_rg_section,
    _build_root_ref,
    _load_template,
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


class TestCollectParams:
    def test_aad_collect_params_with_multiple_app_ids(self):
        wf = get_workflow("aad")
        inputs = iter([
            "main",                  # branch
            "APP-01, APP-02",        # app_ids
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
        wf = get_workflow("aas")
        result = resolve_selected_steps(wf, [])
        assert result == {"1", "2"}

    def test_specific_steps(self):
        wf = get_workflow("aad")
        result = resolve_selected_steps(wf, ["1.1", "1.2"])
        assert "1.1" in result
        assert "1.2" in result
        # 親コンテナ "1" も含まれる
        assert "1" in result

    def test_unknown_steps_excluded(self, capsys):
        wf = get_workflow("aas")
        result = resolve_selected_steps(wf, ["999"])
        captured = capsys.readouterr()
        assert "未知の Step ID" in captured.out
        # 有効な選択がないので全ステップにフォールバック
        assert result == {"1", "2"}

    def test_mixed_valid_invalid(self, capsys):
        wf = get_workflow("aad")
        result = resolve_selected_steps(wf, ["1.1", "INVALID"])
        captured = capsys.readouterr()
        assert "未知の Step ID" in captured.out
        assert "1.1" in result
        assert "INVALID" not in result
        # コンテナ "1" は "1.1" の親なので含まれる
        assert "1" in result

    def test_container_not_added_without_children(self):
        wf = get_workflow("aad")
        # "2" は非コンテナの実ステップなので、コンテナとして追加されない
        result = resolve_selected_steps(wf, ["2"])
        assert "2" in result
        # コンテナ "1" は子が選択されていないので含まれない
        assert "1" not in result


# ---------------------------------------------------------------------------
# build_root_issue_body
# ---------------------------------------------------------------------------


class TestBuildRootIssueBody:
    def test_aas(self):
        wf = get_workflow("aas")
        body = build_root_issue_body(wf, {"branch": "main"})
        assert "# [AAS] App Architecture Design" in body
        assert "<!-- branch: main -->" in body
        assert "ワークフロー: **App Architecture Design**" in body

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
        assert "# [ASDW]" in body
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
