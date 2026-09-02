"""FR-PROMPT-07 — 保存済み GUI 設定から Qt 非依存で `OrchestrateArgs` を構築する契約テスト。

`orchestrate_args` は PySide6 に依存しない。本テストも Qt を import せず、
`settings_store.defaults()` 由来の dict だけを入力にする。
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from hve.gui import settings_store
from hve.gui.orchestrate_args import OrchestrateArgs, args_from_settings


def _settings(**options) -> dict:
    base = settings_store.defaults()
    base["options"].update(options)
    return base


class TestQtIndependence:
    def test_module_does_not_import_pyside6(self):
        source = Path("hve/gui/orchestrate_args.py").read_text(encoding="utf-8")
        assert "PySide6" not in source

    def test_importable_without_qt(self):
        mod = importlib.import_module("hve.gui.orchestrate_args")
        assert hasattr(mod, "args_from_settings")


class TestBasicMapping:
    def test_workflow_is_required_and_set(self):
        args = args_from_settings(_settings(), workflow="ard")
        assert isinstance(args, OrchestrateArgs)
        assert args.workflow == "ard"

    def test_rejects_empty_workflow(self):
        with pytest.raises(ValueError):
            args_from_settings(_settings(), workflow="")

    def test_scalar_settings_are_copied(self):
        args = args_from_settings(
            _settings(model="claude-opus-4.7", branch="develop", max_parallel=7),
            workflow="ard",
        )
        assert args.model == "claude-opus-4.7"
        assert args.branch == "develop"
        assert args.max_parallel == 7

    def test_empty_string_becomes_none_for_optional_fields(self):
        args = args_from_settings(_settings(review_model="", reasoning_effort=""), workflow="ard")
        assert args.review_model is None
        assert args.reasoning_effort is None


class TestTriState:
    @pytest.mark.parametrize(
        ("raw", "expected"), [("", None), ("on", True), ("off", False)]
    )
    def test_mdq_watch_tristate(self, raw, expected):
        args = args_from_settings(_settings(mdq_watch=raw), workflow="ard")
        assert args.mdq_watch is expected

    @pytest.mark.parametrize(
        ("raw", "expected"), [("", None), ("on", True), ("off", False)]
    )
    def test_cq_watch_tristate(self, raw, expected):
        args = args_from_settings(_settings(cq_watch=raw), workflow="ard")
        assert args.cq_watch is expected

    @pytest.mark.parametrize(("raw", "expected"), [("", False), ("on", True), ("off", False)])
    def test_auto_qa_is_a_plain_bool_on_args(self, raw, expected):
        args = args_from_settings(_settings(auto_qa=raw), workflow="ard")
        assert args.auto_qa is expected

    @pytest.mark.parametrize(
        ("raw", "self_improve", "no_self_improve"),
        [("", False, False), ("on", True, False), ("off", False, True)],
    )
    def test_self_improve_tristate_maps_to_two_flags(self, raw, self_improve, no_self_improve):
        args = args_from_settings(_settings(self_improve=raw), workflow="ard")
        assert args.self_improve is self_improve
        assert args.no_self_improve is no_self_improve


class TestAkmSources:
    def test_source_checkboxes_become_a_comma_list(self):
        args = args_from_settings(
            _settings(sources_qa=True, sources_original_docs=True, sources_workiq=False),
            workflow="akm",
        )
        assert args.sources == "qa,original-docs"

    def test_all_sources_off_yields_none(self):
        args = args_from_settings(
            _settings(sources_qa=False, sources_original_docs=False, sources_workiq=False),
            workflow="akm",
        )
        assert args.sources is None

    def test_sources_are_only_applied_to_akm(self):
        args = args_from_settings(_settings(sources_qa=True), workflow="ard")
        assert args.sources is None

    def test_all_akm_settings_are_only_applied_to_akm(self):
        saved = _settings(
            sources_qa=True,
            sources_original_docs=False,
            sources_workiq=True,
            target_files="qa/member.md",
            force_refresh="on",
            custom_source_dir="docs/custom",
        )

        other = args_from_settings(saved, workflow="asdw-web")
        akm = args_from_settings(saved, workflow="akm")
        assert {
            "other": {
                "sources": other.sources,
                "target_files": other.target_files,
                "force_refresh": other.force_refresh,
                "custom_source_dir": other.custom_source_dir,
            },
            "akm": {
                "sources": akm.sources,
                "target_files": akm.target_files,
                "force_refresh": akm.force_refresh,
                "custom_source_dir": akm.custom_source_dir,
            },
        } == {
            "other": {
                "sources": None,
                "target_files": [],
                "force_refresh": None,
                "custom_source_dir": [],
            },
            "akm": {
                "sources": "workiq,qa",
                "target_files": ["qa/member.md"],
                "force_refresh": True,
                "custom_source_dir": ["docs/custom"],
            },
        }


class TestConditionalSettings:
    def test_auto_qa_off_omits_qa_answer_mode(self):
        args = args_from_settings(
            _settings(auto_qa="off", qa_answer_mode="autopilot"), workflow="ard"
        )

        assert {
            "auto_qa": args.auto_qa,
            "qa_answer_mode": args.qa_answer_mode,
            "has_flag": "--qa-answer-mode" in args.to_argv(),
        } == {"auto_qa": False, "qa_answer_mode": None, "has_flag": False}

    def test_auto_qa_on_keeps_qa_answer_mode(self):
        args = args_from_settings(
            _settings(auto_qa="on", qa_answer_mode="autopilot"), workflow="ard"
        )

        assert args.auto_qa is True
        assert args.qa_answer_mode == "autopilot"
        assert "--qa-answer-mode" in args.to_argv()

    @pytest.mark.parametrize(
        ("saved", "override", "expected_mode"),
        [("off", True, "autopilot"), ("on", False, None)],
    )
    def test_auto_qa_override_controls_qa_answer_mode(
        self, saved, override, expected_mode
    ):
        args = args_from_settings(
            _settings(auto_qa=saved, qa_answer_mode="autopilot"),
            workflow="ard",
            overrides={"auto_qa": override},
        )

        assert {
            "auto_qa": args.auto_qa,
            "qa_answer_mode": args.qa_answer_mode,
            "has_flag": "--qa-answer-mode" in args.to_argv(),
        } == {
            "auto_qa": override,
            "qa_answer_mode": expected_mode,
            "has_flag": expected_mode is not None,
        }

    @pytest.mark.parametrize("state", ["", "off"])
    def test_self_improve_inactive_omits_dependent_settings(self, state):
        args = args_from_settings(
            _settings(
                self_improve=state,
                self_improve_max_iterations=7,
                self_improve_target_scope="hve",
                self_improve_goal="設定面を改善する",
            ),
            workflow="aag",
        )

        argv = args.to_argv()
        assert {
            "self_improve": args.self_improve,
            "max_iterations": args.self_improve_max_iterations,
            "target_scope": args.self_improve_target_scope,
            "goal": args.self_improve_goal,
            "has_max_iterations_flag": "--self-improve-max-iterations" in argv,
            "has_target_scope_flag": "--self-improve-target-scope" in argv,
            "has_goal_flag": "--self-improve-goal" in argv,
        } == {
            "self_improve": False,
            "max_iterations": None,
            "target_scope": None,
            "goal": None,
            "has_max_iterations_flag": False,
            "has_target_scope_flag": False,
            "has_goal_flag": False,
        }

    def test_self_improve_on_keeps_dependent_settings(self):
        args = args_from_settings(
            _settings(
                self_improve="on",
                self_improve_max_iterations=7,
                self_improve_target_scope="hve",
                self_improve_goal="設定面を改善する",
            ),
            workflow="aag",
        )

        assert args.self_improve is True
        assert args.self_improve_max_iterations == 7
        assert args.self_improve_target_scope == "hve"
        assert args.self_improve_goal == "設定面を改善する"

    def test_sdk_tool_search_ranking_omits_the_default_flag(self):
        args = args_from_settings(
            _settings(tool_search_ranking="sdk"), workflow="asdw-web"
        )

        assert {
            "ranking": args.tool_search_ranking,
            "has_flag": "--tool-search-ranking" in args.to_argv(),
        } == {"ranking": None, "has_flag": False}

    def test_hve_tool_search_ranking_keeps_the_non_default_flag(self):
        args = args_from_settings(
            _settings(tool_search_ranking="hve"), workflow="asdw-web"
        )

        assert args.tool_search_ranking == "hve"
        assert "--tool-search-ranking" in args.to_argv()


class TestNumericAndListCoercion:
    def test_zero_timeout_means_unspecified(self):
        args = args_from_settings(_settings(workiq_per_question_timeout=0.0), workflow="ard")
        assert args.workiq_per_question_timeout is None

    def test_issue_number_blank_is_none(self):
        args = args_from_settings(_settings(issue_number=""), workflow="ard")
        assert args.issue_number is None

    def test_issue_number_is_parsed_as_int(self):
        args = args_from_settings(_settings(issue_number="42"), workflow="ard")
        assert args.issue_number == 42

    def test_whitespace_path_list_becomes_multiple_argv_tokens(self):
        args = args_from_settings(_settings(ignore_paths="a b"), workflow="ard")
        argv = args.to_argv()

        assert args.ignore_paths == ["a", "b"]
        start = argv.index("--ignore-paths")
        assert argv[start : start + 3] == ["--ignore-paths", "a", "b"]

    @pytest.mark.parametrize(
        ("key", "flag", "raw", "expected"),
        [
            (
                "target_files",
                "--target-files",
                "qa/a.md qa/b.md",
                ["qa/a.md", "qa/b.md"],
            ),
            (
                "custom_source_dir",
                "--custom-source-dir",
                "docs/a docs/b",
                ["docs/a", "docs/b"],
            ),
        ],
    )
    def test_akm_whitespace_path_lists_become_multiple_argv_tokens(
        self, key, flag, raw, expected
    ):
        args = args_from_settings(_settings(**{key: raw}), workflow="akm")
        argv = args.to_argv()

        assert getattr(args, key) == expected
        start = argv.index(flag)
        assert argv[start : start + 3] == [flag, *expected]

    def test_zero_context_max_chars_is_unspecified(self):
        args = args_from_settings(_settings(context_max_chars=0), workflow="ard")
        assert args.context_max_chars is None


class TestPromptEditionOverrides:
    def test_allowlisted_override_wins_over_settings(self):
        args = args_from_settings(
            _settings(model="Auto"), workflow="ard", overrides={"model": "gpt-5.5"}
        )
        assert args.model == "gpt-5.5"

    def test_rejects_non_allowlisted_override(self):
        with pytest.raises(ValueError):
            args_from_settings(_settings(), workflow="ard", overrides={"cli_path": "/x"})

    def test_steps_and_goal_are_explicit_parameters(self):
        args = args_from_settings(
            _settings(), workflow="ard", steps=["1", "2"], goal="やりたいこと"
        )
        assert args.steps == "1,2"
        assert args.additional_prompt == "やりたいこと"

    def test_input_aliases_are_carried(self):
        args = args_from_settings(
            _settings(),
            workflow="aas",
            input_aliases=[("docs/catalog/app-catalog.md", "inputs/my-catalog.md")],
        )
        assert args.input_aliases == [("docs/catalog/app-catalog.md", "inputs/my-catalog.md")]

    def test_dry_run_is_not_taken_from_settings(self):
        args = args_from_settings(_settings(dry_run=True), workflow="ard")
        assert args.dry_run is False


class TestArgvContract:
    def test_argv_starts_with_orchestrate_and_workflow(self):
        argv = args_from_settings(_settings(), workflow="ard").to_argv()
        assert argv[:3] == ["orchestrate", "--workflow", "ard"]

    def test_argv_always_disables_workbench(self):
        argv = args_from_settings(_settings(), workflow="ard").to_argv()
        assert argv[-2:] == ["--workbench", "off"]

    def test_input_aliases_are_emitted_as_repeated_pairs(self):
        argv = args_from_settings(
            _settings(),
            workflow="aas",
            input_aliases=[
                ("docs/catalog/app-catalog.md", "inputs/a.md"),
                ("docs/catalog/use-case-catalog.md", "inputs/b.md"),
            ],
        ).to_argv()
        assert argv.count("--input-alias") == 2
        i = argv.index("--input-alias")
        assert argv[i : i + 3] == ["--input-alias", "docs/catalog/app-catalog.md", "inputs/a.md"]

    def test_no_aliases_emits_no_flag(self):
        argv = args_from_settings(_settings(), workflow="ard").to_argv()
        assert "--input-alias" not in argv


class TestSharedLocalSurfaceSettings:
    """FR-LOCAL-SURFACE-01 (a): shared setting が保存値から漏れなく反映される。"""

    SHARED = {
        "enable_agentic_retrieval": "no",
        "agentic_data_source_modes": "indexer;push",
        "foundry_mcp_integration": "off",
        "agentic_data_sources_hint": "Blob と Azure SQL",
        "agentic_existing_design_diff_only": "on",
        "foundry_sku_fallback_policy": "global_required",
        "enable_tool_search": "yes",
        "cloud_session_repository_branch": "feature/x",
        "strict": True,
    }

    def test_agentic_settings_reach_args(self):
        args = args_from_settings(_settings(**self.SHARED), workflow="asdw-web")
        assert args.enable_agentic_retrieval == "no"
        assert args.agentic_data_source_modes == ["indexer", "push"]
        assert args.foundry_mcp_integration is False
        assert args.agentic_data_sources_hint == "Blob と Azure SQL"
        assert args.agentic_existing_design_diff_only is True
        assert args.foundry_sku_fallback_policy == "global_required"
        assert args.enable_tool_search == "yes"
        assert args.strict is True

    def test_cloud_session_branch_is_bridged_from_its_settings_key(self):
        """保存 key は `cloud_session_repository_branch`、args は `cloud_session_branch`。

        名前が一致しないため、明示対応が無いと無言で捨てられる。
        """
        args = args_from_settings(
            _settings(cloud_session_repository_branch="feature/x"), workflow="ard"
        )
        assert args.cloud_session_branch == "feature/x"
        assert "--cloud-session-branch" in args.to_argv()

    @pytest.mark.parametrize(
        "key", ["enable_agentic_retrieval", "enable_tool_search"]
    )
    def test_auto_is_normalized_to_unset(self, key):
        """"auto" は GUI の to_args() と同じく CLI 未指定へ落とす。"""
        args = args_from_settings(_settings(**{key: "auto"}), workflow="asdw-web")
        assert getattr(args, key) is None

    def test_shared_settings_are_emitted_to_argv(self):
        argv = args_from_settings(_settings(**self.SHARED), workflow="asdw-web").to_argv()
        for flag in (
            "--enable-agentic-retrieval",
            "--agentic-data-source-modes",
            "--no-foundry-mcp-integration",
            "--agentic-data-sources-hint",
            "--agentic-existing-design-diff-only",
            "--foundry-sku-fallback-policy",
            "--enable-tool-search",
            "--cloud-session-branch",
            "--strict",
        ):
            assert flag in argv, f"{flag} が argv へ出ていない"
        start = argv.index("--agentic-data-source-modes")
        assert argv[start : start + 3] == [
            "--agentic-data-source-modes",
            "indexer",
            "push",
        ]

    def test_defaults_emit_no_shared_flags(self):
        """既定値のままなら追加のフラグを一切出さない（既存挙動の維持）。"""
        argv = args_from_settings(_settings(), workflow="asdw-web").to_argv()
        for flag in (
            "--enable-agentic-retrieval",
            "--agentic-data-source-modes",
            "--foundry-mcp-integration",
            "--no-foundry-mcp-integration",
            "--agentic-data-sources-hint",
            "--foundry-sku-fallback-policy",
            "--enable-tool-search",
            "--cloud-session-branch",
            "--strict",
        ):
            assert flag not in argv, f"既定状態で {flag} が argv へ出た"

    def test_shared_settings_are_overridable_from_prompt_requests(self):
        args = args_from_settings(
            _settings(),
            workflow="asdw-web",
            overrides={"strict": True, "enable_tool_search": "no"},
        )
        assert args.strict is True
        assert args.enable_tool_search == "no"


class TestRequirementIsDeclared:
    def test_fr_prompt_07_is_declared(self):
        text = Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
        assert "**FR-PROMPT-07**" in text

    def test_fr_local_surface_01_is_declared(self):
        text = Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
        assert "**FR-LOCAL-SURFACE-01**" in text
