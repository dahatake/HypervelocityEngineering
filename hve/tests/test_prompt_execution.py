"""FR-PROMPT-01 / FR-PROMPT-05 — Prompt 版 実行計画と SHA-256 の契約テスト。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hve import prompt_execution
from hve.gui import settings_store
from hve.gui.orchestrate_args import OrchestrateArgs
from hve.prompt_execution import (
    ExecutionPlan,
    build_execution_plan,
    canonical_plan_json,
    run_plan,
)
from hve.prompt_request import parse_request


def _settings(**options) -> dict:
    base = settings_store.defaults()
    base["options"].update(options)
    return base


def _request(**overrides) -> "object":
    data = {
        "schema_version": 1,
        "goal": "設計を進めたい",
        "workflows": [{"workflow_id": "aad-web"}, {"workflow_id": "aas"}],
    }
    data.update(overrides)
    return parse_request(data)


def _plan(tmp_path: Path, request=None, settings=None, head="abc123") -> ExecutionPlan:
    return build_execution_plan(
        request or _request(),
        settings=settings or _settings(),
        repo_root=tmp_path,
        head_commit=head,
    )


class TestOrdering:
    def test_workflows_are_sorted_by_dependency(self, tmp_path: Path):
        plan = _plan(tmp_path)
        assert [w.workflow_id for w in plan.workflows] == ["aas", "aad-web"]

    def test_does_not_add_unselected_dependencies(self, tmp_path: Path):
        plan = _plan(tmp_path, request=_request(workflows=[{"workflow_id": "aad-web"}]))
        assert [w.workflow_id for w in plan.workflows] == ["aad-web"]


class TestArgv:
    def test_each_workflow_has_its_own_argv(self, tmp_path: Path):
        plan = _plan(tmp_path)
        for wp in plan.workflows:
            assert wp.argv[:3] == ("orchestrate", "--workflow", wp.workflow_id)

    def test_goal_is_passed_as_additional_prompt(self, tmp_path: Path):
        plan = _plan(tmp_path)
        argv = list(plan.workflows[0].argv)
        assert "--additional-prompt" in argv
        assert argv[argv.index("--additional-prompt") + 1] == "設計を進めたい"

    def test_argv_is_a_tuple_of_strings_not_a_shell_string(self, tmp_path: Path):
        plan = _plan(tmp_path)
        for wp in plan.workflows:
            assert isinstance(wp.argv, tuple)
            assert all(isinstance(a, str) for a in wp.argv)

    def test_plan_never_contains_dry_run(self, tmp_path: Path):
        plan = _plan(tmp_path)
        for wp in plan.workflows:
            assert "--dry-run" not in wp.argv


class TestCanonicalJson:
    def test_is_sorted_compact_utf8(self, tmp_path: Path):
        raw = canonical_plan_json(_plan(tmp_path))
        assert ", " not in raw and '": ' not in raw
        data = json.loads(raw)
        assert list(data) == sorted(data)
        assert data["schema_version"] == 1
        assert data["head_commit"] == "abc123"

    def test_contains_argv_arrays(self, tmp_path: Path):
        data = json.loads(canonical_plan_json(_plan(tmp_path)))
        assert isinstance(data["workflows"][0]["argv"], list)


class TestSha256:
    def test_is_64_hex_chars(self, tmp_path: Path):
        assert len(_plan(tmp_path).sha256) == 64
        assert all(c in "0123456789abcdef" for c in _plan(tmp_path).sha256)

    def test_same_input_same_hash(self, tmp_path: Path):
        assert _plan(tmp_path).sha256 == _plan(tmp_path).sha256

    def test_head_change_changes_hash(self, tmp_path: Path):
        assert _plan(tmp_path, head="a").sha256 != _plan(tmp_path, head="b").sha256

    def test_settings_change_changes_hash(self, tmp_path: Path):
        a = _plan(tmp_path)
        b = _plan(tmp_path, settings=_settings(model="gpt-5.5"))
        assert a.sha256 != b.sha256

    def test_request_change_changes_hash(self, tmp_path: Path):
        a = _plan(tmp_path)
        b = _plan(tmp_path, request=_request(goal="別の目的"))
        assert a.sha256 != b.sha256

    def test_workflow_selection_change_changes_hash(self, tmp_path: Path):
        a = _plan(tmp_path)
        b = _plan(tmp_path, request=_request(workflows=[{"workflow_id": "aas"}]))
        assert a.sha256 != b.sha256


class TestInputAliases:
    def test_validated_aliases_appear_in_argv_and_plan(self, tmp_path: Path):
        (tmp_path / "inputs").mkdir()
        (tmp_path / "inputs" / "my-catalog.md").write_text("# c", encoding="utf-8")
        request = _request(
            workflows=[
                {
                    "workflow_id": "aas",
                    "steps": ["1"],
                    "input_aliases": [
                        {
                            "canonical": "docs/catalog/app-catalog.md",
                            "actual": "inputs/my-catalog.md",
                        }
                    ],
                }
            ]
        )
        plan = _plan(tmp_path, request=request)
        argv = list(plan.workflows[0].argv)
        assert argv.count("--input-alias") == 1
        assert plan.workflows[0].input_aliases[0].actual == "inputs/my-catalog.md"

    def test_invalid_alias_fails_closed(self, tmp_path: Path):
        from hve.input_aliases import InputAliasError

        request = _request(
            workflows=[
                {
                    "workflow_id": "aas",
                    "steps": ["1"],
                    "input_aliases": [
                        {"canonical": "docs/catalog/app-catalog.md", "actual": "inputs/absent.md"}
                    ],
                }
            ]
        )
        with pytest.raises(InputAliasError):
            _plan(tmp_path, request=request)


class _FakeRunner:
    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(
            argv, self.codes.pop(0) if self.codes else 0
        )


class TestRunPlan:
    def test_runs_each_workflow_in_order_with_shell_false(self, tmp_path: Path):
        runner = _FakeRunner([0, 0])
        assert run_plan(_plan(tmp_path), dry_run=False, runner=runner) == 0
        assert len(runner.calls) == 2
        assert runner.calls[0][0][:2] == [sys.executable, "-m"]
        assert "--workflow" in runner.calls[0][0]
        assert runner.calls[0][1].get("shell", False) is False

    def test_dry_run_appends_the_flag(self, tmp_path: Path):
        runner = _FakeRunner([0, 0])
        run_plan(_plan(tmp_path), dry_run=True, runner=runner)
        for argv, _ in runner.calls:
            assert "--dry-run" in argv

    def test_fail_fast_stops_subsequent_workflows(self, tmp_path: Path):
        runner = _FakeRunner([3, 0])
        assert run_plan(_plan(tmp_path), dry_run=False, runner=runner) == 3
        assert len(runner.calls) == 1

    def test_module_invocation_uses_hve_package(self, tmp_path: Path):
        runner = _FakeRunner([0, 0])
        run_plan(_plan(tmp_path), dry_run=True, runner=runner)
        assert runner.calls[0][0][:3] == [sys.executable, "-m", "hve"]

    def test_default_runner_does_not_duplicate_the_shell_keyword(self, tmp_path: Path):
        """`run_plan` が渡す `shell=False` と既定 runner の指定が衝突しないこと。"""
        seen: list = []

        def fake_subprocess_run(argv, **kwargs):
            seen.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(prompt_execution.subprocess, "run", fake_subprocess_run)
            assert run_plan(_plan(tmp_path), dry_run=True) == 0
        assert len(seen) == 2
        assert seen[0][1]["shell"] is False


class TestNoReimplementationOfTheExecutionCore:
    def test_module_does_not_import_the_dag_engine(self):
        source = Path("hve/prompt_execution.py").read_text(encoding="utf-8")
        for forbidden in ("dag_executor", "run_workflow", "StepRunner"):
            assert forbidden not in source, forbidden

    def test_module_never_uses_shell_true(self):
        source = Path("hve/prompt_execution.py").read_text(encoding="utf-8")
        assert "shell=True" not in source


class TestWorkflowParamCoercion:
    """request の params は文字列。`OrchestrateArgs` のフィールド型へ変換して argv を作る。"""

    def _argv(self, tmp_path: Path, workflow_id: str, params: dict) -> list:
        plan = _plan(
            tmp_path,
            request=_request(
                workflows=[{"workflow_id": workflow_id, "params": params}]
            ),
        )
        return list(plan.workflows[0].argv)

    def test_list_param_is_not_split_into_characters(self, tmp_path: Path):
        argv = self._argv(tmp_path, "akm", {"target_files": "qa/*.md"})
        assert "--target-files" in argv
        assert argv[argv.index("--target-files") + 1] == "qa/*.md"
        assert "q" not in argv

    def test_list_param_accepts_multiple_values(self, tmp_path: Path):
        argv = self._argv(tmp_path, "akm", {"target_files": "qa/a.md,qa/b.md"})
        start = argv.index("--target-files") + 1
        assert argv[start : start + 2] == ["qa/a.md", "qa/b.md"]

    def test_tristate_param_is_not_silently_dropped(self, tmp_path: Path):
        argv = self._argv(tmp_path, "akm", {"force_refresh": "true"})
        assert "--force-refresh" in argv

    def test_tristate_param_false_uses_the_negative_flag(self, tmp_path: Path):
        argv = self._argv(tmp_path, "akm", {"force_refresh": "false"})
        assert "--no-force-refresh" in argv

    def test_int_param_is_coerced(self, tmp_path: Path):
        argv = self._argv(tmp_path, "adoc", {"max_file_lines": "500"})
        assert argv[argv.index("--max-file-lines") + 1] == "500"

    def test_invalid_value_is_rejected_instead_of_guessed(self, tmp_path: Path):
        with pytest.raises(ValueError):
            self._argv(tmp_path, "adoc", {"max_file_lines": "たくさん"})

    def test_include_kpi_okr_reaches_the_existing_cli_shortcut(self, tmp_path: Path):
        # FR-PARAM-10 の後方互換ショートカットへ届くこと（FR-LOCAL-SURFACE-01）。
        argv = self._argv(tmp_path, "ard", {"include_kpi_okr": "true"})
        assert "--include-kpi-okr" in argv

    def test_unsupported_param_is_rejected_instead_of_dropped(self):
        # `OrchestrateArgs` に対応フィールドが無いパラメータは fail-closed で拒否する。
        # 黙って捨てると利用者は無効化に気づけない。
        args = OrchestrateArgs(workflow="ard")
        with pytest.raises(ValueError) as exc:
            prompt_execution._apply_workflow_params(args, {"not_a_real_param": "x"})
        assert "not_a_real_param" in str(exc.value)


class TestFormatPlan:
    def test_shows_order_argv_and_hash(self, tmp_path: Path):
        plan = _plan(tmp_path)
        text = prompt_execution.format_plan(plan)
        assert plan.sha256 in text
        assert "aas" in text and "aad-web" in text
        assert "--workflow" in text

    def test_does_not_ask_the_user_to_run_a_command(self, tmp_path: Path):
        # FR-PROMPT-03: 提示文は利用者へコマンド・request path・SHA-256 の入力を求めてはならない。
        text = prompt_execution.format_plan(_plan(tmp_path))
        assert "hve prompt run" not in text
        assert "利用者へコマンドの入力を求めてはならない" in text
        assert "--expected-sha256" in text


class TestRequirementIsDeclared:
    def test_fr_prompt_01_and_05_are_declared(self):
        text = Path("hve-dev/requirement-definition.md").read_text(encoding="utf-8")
        assert "**FR-PROMPT-01**" in text
        assert "**FR-PROMPT-05**" in text
