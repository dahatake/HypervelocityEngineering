"""FR-PROMPT-02 / 03 / 04 — request v1 統合 Prompt の恒久契約。

`tests/prompt-version/01-request-contract.md` の手動テストオラクルが、
registry / OrchestrateArgs / Prompt CLI の実装と逆方向へ drift しないことを検査する。
子 `orchestrate` 非起動は OS process 総数ではなく `_default_runner` の呼び出しで判定する。
"""

from __future__ import annotations

from dataclasses import dataclass, fields
import json
from pathlib import Path
import subprocess
from typing import Any
from unittest.mock import Mock

import pytest

from hve import __main__ as hve_main
from hve import prompt_execution
from hve.gui import settings_store
from hve.gui.orchestrate_args import OrchestrateArgs
from hve.workflow_registry import get_workflow, list_workflows

_REQUEST_CONTRACT = Path("tests/prompt-version/01-request-contract.md")
_C1_START = "<!-- request-contract-c1:start -->"
_C1_END = "<!-- request-contract-c1:end -->"
_STALE_C1_CLAIM = "OrchestrateArgs` に対応フィールドが無いパラメータ"
_FIXED_HEAD = "a" * 40
_UNKNOWN_STEP = "__not_registered_step__"
_UNKNOWN_PARAM = "__not_declared_param__"


def _minimal(workflows: Any, **overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "schema_version": 1,
        "goal": "request v1 integration contract",
        "workflows": workflows,
    }
    request.update(overrides)
    return request


def _workflow(workflow_id: str, **overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {"workflow_id": workflow_id}
    request.update(overrides)
    return request


def _read_contract() -> str:
    return _REQUEST_CONTRACT.read_text(encoding="utf-8")


def _c1_contract() -> str:
    text = _read_contract()
    assert text.count(_C1_START) == 1
    assert text.count(_C1_END) == 1
    return text.split(_C1_START, 1)[1].split(_C1_END, 1)[0]


def _safe_asdw_root_step_id() -> str:
    workflow = get_workflow("asdw-web")
    assert workflow is not None
    observed = [
        {
            "id": step.id,
            "is_container": step.is_container,
            "depends_on": list(step.depends_on),
            "requires_remote_cicd": step.requires_remote_cicd,
        }
        for step in workflow.steps
        if not step.depends_on
    ]
    candidates = [
        step.id
        for step in workflow.steps
        if not step.is_container
        and not step.depends_on
        and not step.requires_remote_cicd
    ]
    assert len(candidates) == 1, (
        "asdw-web の非コンテナ・依存なし root・non-remote Step は "
        f"1 件でなければなりません: candidates={candidates}, roots={observed}"
    )
    return candidates[0]


class TestRequestContractDocument:
    def test_c1_is_bounded_and_matches_the_current_acceptance_contract(self) -> None:
        text = _read_contract()
        section = _c1_contract()

        assert _STALE_C1_CLAIM not in text
        for token in (
            "include_kpi_okr=true",
            "--include-kpi-okr",
            "tdd_max_retries=3",
            "--tdd-max-retries 3",
            "create_remote_mcp_server=true",
            "--create-remote-mcp-server",
            "create_remote_mcp_server=false",
            "--no-create-remote-mcp-server",
            "not s.is_container",
            "not s.depends_on",
            "not s.requires_remote_cicd",
            "assert len(c) == 1",
        ):
            assert token in section, token

    def test_child_process_contract_names_the_orchestrate_runner_seam(self) -> None:
        text = _read_contract()

        assert "子 `orchestrate`" in text
        assert "prompt_execution._default_runner" in text
        assert "OS process 総数" in text
        assert "TestInvalidRequestCliMatrix" in text

    def test_copyable_outer_fence_and_required_sections_are_preserved(self) -> None:
        text = _read_contract()

        assert text.count("````markdown") == 1
        assert text.rstrip().endswith("````")
        for heading in (
            "## 目的",
            "## 前提",
            "## 実施項目",
            "### A. 正常系（受理されること）",
            "### B. 異常系（実行前に拒否されること）",
            "### C. 境界の確認（**捏造しないこと**）",
            "## 記録すること",
            "## 重要",
        ):
            assert heading in text, heading


@dataclass(frozen=True)
class InvalidRequestCase:
    case_id: str
    request: Any | None = None
    raw: bytes | None = None
    missing: bool = False
    tokens: tuple[str, ...] = ()


_INVALID_CASES: tuple[InvalidRequestCase, ...] = (
    InvalidRequestCase(
        "B1-schema-2",
        _minimal([_workflow("aas")], schema_version=2),
        tokens=("未知の schema_version", "対応は 1 のみ"),
    ),
    InvalidRequestCase(
        "B1-schema-string",
        _minimal([_workflow("aas")], schema_version="1"),
        tokens=("schema_version", "整数"),
    ),
    InvalidRequestCase(
        "B1-schema-bool",
        _minimal([_workflow("aas")], schema_version=True),
        tokens=("schema_version", "整数"),
    ),
    InvalidRequestCase(
        "B1-schema-missing",
        {"goal": "test", "workflows": [_workflow("aas")]},
        tokens=("schema_version", "整数"),
    ),
    InvalidRequestCase(
        "B2-unknown-top-level",
        _minimal([_workflow("aas")], extra=1),
        tokens=("未知のフィールド", "extra"),
    ),
    InvalidRequestCase(
        "B3-workflows-empty",
        _minimal([]),
        tokens=("workflows", "1 件以上", "配列"),
    ),
    InvalidRequestCase(
        "B3-workflows-not-array",
        _minimal({"workflow_id": "aas"}),
        tokens=("workflows", "1 件以上", "配列"),
    ),
    InvalidRequestCase(
        "B4-duplicate-workflow",
        _minimal([_workflow("aas"), _workflow("aas")]),
        tokens=("同じ Workflow", "重複", "aas"),
    ),
    InvalidRequestCase(
        "B5-duplicate-json-key",
        raw=b'{"schema_version":1,"schema_version":1,"goal":"test","workflows":[{"workflow_id":"aas"}]}',
        tokens=("JSON に重複キー", "schema_version"),
    ),
    InvalidRequestCase(
        "B6-unknown-workflow",
        _minimal([_workflow("nope")]),
        tokens=("registry に存在しません", "nope"),
    ),
    InvalidRequestCase(
        "B7-unknown-step",
        _minimal([_workflow("aas", steps=[_UNKNOWN_STEP])]),
        tokens=("存在しない Step", _UNKNOWN_STEP),
    ),
    InvalidRequestCase(
        "B8-undeclared-param",
        _minimal([_workflow("akm", params={_UNKNOWN_PARAM: "x"})]),
        tokens=("宣言していないパラメータ", _UNKNOWN_PARAM),
    ),
    InvalidRequestCase(
        "B9-param-number",
        _minimal([_workflow("akm", params={"sources": 1})]),
        tokens=("workflows[0].params.sources", "文字列"),
    ),
    InvalidRequestCase(
        "B9-param-bool",
        _minimal([_workflow("akm", params={"sources": True})]),
        tokens=("workflows[0].params.sources", "文字列"),
    ),
    InvalidRequestCase(
        "B9-param-null",
        _minimal([_workflow("akm", params={"sources": None})]),
        tokens=("workflows[0].params.sources", "文字列"),
    ),
    *(
        InvalidRequestCase(
            f"B10-setting-{key}",
            _minimal([_workflow("aas")], settings_overrides={key: "x"}),
            tokens=("許可されていないキー", key),
        )
        for key in ("token", "cli_path", "mcp_config", "repo_root")
    ),
    *(
        InvalidRequestCase(
            f"B11-cli-owned-{key}",
            _minimal([_workflow("aas")], settings_overrides={key: "x"}),
            tokens=("許可されていないキー", key),
        )
        for key in ("dry_run", "workbench", "workflow", "steps")
    ),
    InvalidRequestCase(
        "B12-alias-missing-canonical",
        _minimal([_workflow("aas", input_aliases=[{"actual": "README.md"}])]),
        tokens=("input_aliases[0]", "canonical", "ありません"),
    ),
    InvalidRequestCase(
        "B12-alias-missing-actual",
        _minimal([_workflow("aas", input_aliases=[{"canonical": "README.md"}])]),
        tokens=("input_aliases[0]", "actual", "ありません"),
    ),
    InvalidRequestCase(
        "B12-alias-empty-canonical",
        _minimal(
            [
                _workflow(
                    "aas",
                    input_aliases=[{"canonical": "", "actual": "README.md"}],
                )
            ]
        ),
        tokens=("input_aliases[0].canonical", "空でない文字列"),
    ),
    InvalidRequestCase(
        "B12-alias-empty-actual",
        _minimal(
            [
                _workflow(
                    "aas",
                    input_aliases=[{"canonical": "README.md", "actual": ""}],
                )
            ]
        ),
        tokens=("input_aliases[0].actual", "空でない文字列"),
    ),
    InvalidRequestCase(
        "B13-request-missing",
        missing=True,
        tokens=("request ファイルを読み込めません",),
    ),
    InvalidRequestCase(
        "B13-request-non-utf8",
        raw=b'{"schema_version":1,"goal":"\xff","workflows":[{"workflow_id":"aas"}]}',
        tokens=("utf-8", "decode"),
    ),
    InvalidRequestCase(
        "B13-request-invalid-json",
        raw=b"{",
        tokens=("JSON が不正",),
    ),
)


class TestInvalidRequestCliMatrix:
    def test_matrix_covers_all_documented_variants(self) -> None:
        assert len(_INVALID_CASES) == 30
        assert {case.case_id.split("-", 1)[0] for case in _INVALID_CASES} == {
            f"B{number}" for number in range(1, 14)
        }

    @pytest.mark.parametrize("case", _INVALID_CASES, ids=lambda case: case.case_id)
    def test_invalid_request_is_actionable_and_starts_no_orchestrate(
        self,
        case: InvalidRequestCase,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        request_path = tmp_path / f"{case.case_id}.json"
        if case.raw is not None:
            request_path.write_bytes(case.raw)
        elif not case.missing:
            request_path.write_text(
                json.dumps(case.request, ensure_ascii=False),
                encoding="utf-8",
            )

        runner = Mock(name="orchestrate_runner_must_not_start")
        monkeypatch.setattr(prompt_execution, "_default_runner", runner)

        code = hve_main.main(
            ["prompt", "plan", "--request", str(request_path)]
        )
        captured = capsys.readouterr()

        assert code != 0
        runner.assert_not_called()
        assert "plan SHA-256:" not in captured.out
        assert captured.err.strip()
        for token in case.tokens:
            assert token in captured.err, (case.case_id, token, captured.err)


@dataclass(frozen=True)
class AcceptedParamCase:
    case_id: str
    workflow_id: str
    params: dict[str, str]
    expected_flag: str
    expected_value: str | None = None
    use_safe_asdw_root: bool = False


_ACCEPTED_PARAM_CASES: tuple[AcceptedParamCase, ...] = (
    AcceptedParamCase(
        "C1-include-kpi-okr",
        "ard",
        {"include_kpi_okr": "true"},
        "--include-kpi-okr",
    ),
    AcceptedParamCase(
        "C1-tdd-max-retries",
        "asdw-web",
        {"tdd_max_retries": "3"},
        "--tdd-max-retries",
        expected_value="3",
        use_safe_asdw_root=True,
    ),
    AcceptedParamCase(
        "C1-create-remote-mcp-server-true",
        "aad-web",
        {"create_remote_mcp_server": "true"},
        "--create-remote-mcp-server",
    ),
    AcceptedParamCase(
        "C1-create-remote-mcp-server-false",
        "aad-web",
        {"create_remote_mcp_server": "false"},
        "--no-create-remote-mcp-server",
    ),
)


class TestDeclaredWorkflowParamCliMatrix:
    @pytest.mark.parametrize(
        "case", _ACCEPTED_PARAM_CASES, ids=lambda case: case.case_id
    )
    def test_declared_param_reaches_the_expected_orchestrate_argv(
        self,
        case: AcceptedParamCase,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        workflow_request = _workflow(case.workflow_id, params=case.params)
        safe_step_id: str | None = None
        if case.use_safe_asdw_root:
            safe_step_id = _safe_asdw_root_step_id()
            workflow_request["steps"] = [safe_step_id]

        request_path = tmp_path / f"{case.case_id}.json"
        request_path.write_text(
            json.dumps(
                _minimal([workflow_request]),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(settings_store, "load", settings_store.defaults)
        monkeypatch.setattr(
            prompt_execution,
            "resolve_head_commit",
            lambda _repo_root: _FIXED_HEAD,
        )
        runner = Mock(
            name="successful_orchestrate_dry_run",
            return_value=subprocess.CompletedProcess([], 0),
        )
        monkeypatch.setattr(prompt_execution, "_default_runner", runner)

        code = hve_main.main(
            ["prompt", "plan", "--request", str(request_path)]
        )
        captured = capsys.readouterr()

        assert code == 0
        runner.assert_called_once()
        child_argv = list(runner.call_args.args[0])
        assert child_argv[:3] == [
            str(Path(prompt_execution.sys.executable)),
            "-m",
            "hve",
        ]
        assert child_argv[3:6] == [
            "orchestrate",
            "--workflow",
            case.workflow_id,
        ]
        assert "--dry-run" in child_argv
        assert child_argv.count(case.expected_flag) == 1
        opposite_flag = {
            "--create-remote-mcp-server": "--no-create-remote-mcp-server",
            "--no-create-remote-mcp-server": "--create-remote-mcp-server",
        }.get(case.expected_flag)
        if opposite_flag is not None:
            assert opposite_flag not in child_argv
        if case.expected_value is not None:
            index = child_argv.index(case.expected_flag)
            assert child_argv[index + 1] == case.expected_value
        if safe_step_id is not None:
            index = child_argv.index("--steps")
            assert child_argv[index + 1] == safe_step_id
        assert "plan SHA-256:" in captured.out
        assert "Prompt request を受理できません" not in captured.err


class TestRegistryParamCompleteness:
    def test_every_declared_workflow_param_has_an_orchestrate_args_field(self) -> None:
        args_fields = {field.name for field in fields(OrchestrateArgs)}
        missing_by_workflow = {
            workflow.id: sorted(set(workflow.params) - args_fields)
            for workflow in list_workflows()
            if set(workflow.params) - args_fields
        }

        assert not missing_by_workflow, (
            "WorkflowDef.params に宣言済みだが OrchestrateArgs に対応 field がないため、"
            f"Prompt plan へ投影できません: {missing_by_workflow}"
        )

    def test_asdw_safe_root_predicate_is_unambiguous(self) -> None:
        assert _safe_asdw_root_step_id()
