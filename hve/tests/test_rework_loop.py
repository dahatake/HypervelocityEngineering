"""FR-DAG-09: DAG 外フィードバックループ（差戻し）の決定層。"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hve import rework
from hve.workflow_registry import StepDef

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"

_HEADER = "| Req ID | Kind | Target | Threshold | Measured | Judgement | Headroom | Evidence |"
_DIVIDER = "|---|---|---|---|---|---|---|---|"


def _report(*judgements: str) -> str:
    rows = [
        f"| FR-{i:02d} | FR | t | th | m | {judgement} | h | e |"
        for i, judgement in enumerate(judgements, 1)
    ]
    return "\n".join([_HEADER, _DIVIDER, *rows])


def _requirement_block(requirement_id: str) -> str:
    lines = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(f"- **{requirement_id}**")]
    assert len(starts) == 1, f"{requirement_id} の定義行が {len(starts)} 件見つかった"
    block = [lines[starts[0]]]
    for line in lines[starts[0] + 1 :]:
        if not line.startswith("  "):
            break
        block.append(line)
    return "\n".join(block)


class TestTriggerDetection:
    def test_fail_triggers_rework(self) -> None:
        assert rework.report_has_rework_trigger(_report("PASS", "FAIL")) is True

    def test_pass_only_does_not_trigger(self) -> None:
        assert rework.report_has_rework_trigger(_report("PASS", "PASS")) is False

    def test_not_measured_and_no_target_do_not_trigger(self) -> None:
        assert rework.report_has_rework_trigger(_report("NOT_MEASURED", "NO_TARGET")) is False

    def test_missing_table_does_not_trigger(self) -> None:
        assert rework.report_has_rework_trigger("本文だけで表が無い") is False


class TestTargetResolution:
    def _write(self, tmp_path: Path, relative: str, text: str) -> None:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def test_failing_step_returns_its_declared_targets(self, tmp_path: Path) -> None:
        self._write(tmp_path, "docs/report.md", _report("FAIL"))
        step = SimpleNamespace(
            id="5.3", output_paths=["docs/report.md"], rework_targets=["3.3", "4.2"]
        )
        assert rework.resolve_rework_targets([step], {"5.3"}, tmp_path) == ["3.3", "4.2"]

    def test_passing_step_returns_nothing(self, tmp_path: Path) -> None:
        self._write(tmp_path, "docs/report.md", _report("PASS"))
        step = SimpleNamespace(id="5.3", output_paths=["docs/report.md"], rework_targets=["3.3"])
        assert rework.resolve_rework_targets([step], {"5.3"}, tmp_path) == []

    def test_step_without_declaration_is_ignored(self, tmp_path: Path) -> None:
        self._write(tmp_path, "docs/report.md", _report("FAIL"))
        step = SimpleNamespace(id="5.3", output_paths=["docs/report.md"], rework_targets=[])
        assert rework.resolve_rework_targets([step], {"5.3"}, tmp_path) == []

    def test_uncompleted_step_is_ignored(self, tmp_path: Path) -> None:
        self._write(tmp_path, "docs/report.md", _report("FAIL"))
        step = SimpleNamespace(id="5.3", output_paths=["docs/report.md"], rework_targets=["3.3"])
        assert rework.resolve_rework_targets([step], set(), tmp_path) == []

    def test_missing_report_is_ignored(self, tmp_path: Path) -> None:
        step = SimpleNamespace(id="5.3", output_paths=["docs/absent.md"], rework_targets=["3.3"])
        assert rework.resolve_rework_targets([step], {"5.3"}, tmp_path) == []

    def test_duplicate_targets_are_collapsed_in_declaration_order(self, tmp_path: Path) -> None:
        self._write(tmp_path, "a.md", _report("FAIL"))
        self._write(tmp_path, "b.md", _report("FAIL"))
        steps = [
            SimpleNamespace(id="5.3", output_paths=["a.md"], rework_targets=["3.3"]),
            SimpleNamespace(id="5.4", output_paths=["b.md"], rework_targets=["3.3", "4.2"]),
        ]
        assert rework.resolve_rework_targets(steps, {"5.3", "5.4"}, tmp_path) == ["3.3", "4.2"]


class TestStepDefField:
    def test_rework_targets_defaults_to_empty(self) -> None:
        assert StepDef(id="x", title="t", custom_agent="A").rework_targets == []

    def test_rework_targets_accepts_declaration(self) -> None:
        step = StepDef(id="x", title="t", custom_agent="A", rework_targets=["1.1"])
        assert step.rework_targets == ["1.1"]


class TestRequirementIsDeclared:
    def test_requirement_keeps_the_dag_acyclic(self) -> None:
        block = _requirement_block("FR-DAG-09")
        assert "FR-DAG-01" in block
        assert "非巡回" in block

    def test_requirement_names_the_trigger_vocabulary(self) -> None:
        block = _requirement_block("FR-DAG-09")
        assert "FR-WF-CONF-03" in block
        assert "NOT_MEASURED" in block

    def test_requirement_defers_re_execution_to_a_restart(self) -> None:
        block = _requirement_block("FR-DAG-09")
        assert "--resume-run" in block
        assert "再入可能へ作り替えてはならない" in block

    def test_requirement_declares_the_presentation_channel(self) -> None:
        block = _requirement_block("FR-DAG-09")
        assert "console.event" in block
        assert "自動で再実行を開始してはならない" in block


class TestDeclaredReworkTargets:
    """FR-DAG-09: 宣言するのは `asdw-web` Step 5.3 だけとする。"""

    def test_asdw_web_step_5_3_declares_implementation_steps(self) -> None:
        from hve.workflow_registry import get_workflow

        step = get_workflow("asdw-web").get_step("5.3")
        assert step is not None
        assert step.rework_targets == ["3.3", "4.2"]

    def test_no_other_step_declares_rework_targets(self) -> None:
        from hve.workflow_registry import list_workflows

        declared = [
            (workflow.id, step.id)
            for workflow in list_workflows()
            for step in getattr(workflow, "steps", [])
            if getattr(step, "rework_targets", [])
        ]
        assert declared == [("asdw-web", "5.3")]


class TestReworkPresentationWiring:
    """FR-DAG-09: DAG 実行後に決定結果を 1 回だけ提示する。"""

    def test_run_workflow_calls_the_resolver(self) -> None:
        """`run_workflow` 本体から決定層を呼ぶことを AST で固定する。

        部分一致だけでは import 行やコメントでも通ってしまう。
        """
        tree = ast.parse((_REPO_ROOT / "hve" / "orchestrator.py").read_text(encoding="utf-8"))
        run_workflow = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == "run_workflow"
        )
        called = {
            node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            for node in ast.walk(run_workflow)
            if isinstance(node, ast.Call)
        }
        assert "resolve_rework_targets" in called

    def test_presentation_suggests_steps_option(self) -> None:
        from hve import rework

        assert hasattr(rework, "format_rework_suggestion")
        text = rework.format_rework_suggestion("asdw-web", ["3.3", "4.2"])
        assert "--steps" in text
        assert "3.3" in text and "4.2" in text

    def test_empty_targets_produce_no_message(self) -> None:
        from hve import rework

        assert rework.format_rework_suggestion("asdw-web", []) == ""


class TestReworkPresentationIntegration:
    """FR-DAG-09: `run_workflow` を実際に呼び、提示が「1回だけ・非空時だけ」発火することを確認する。

    AST 検証は「resolve_rework_targets を呼ぶ行がある」ことしか保証できず、結果を
    console.event へ渡す配線・空リスト時に沈黙する分岐・例外を握りつぶす
    try/except の実行時挙動までは保証できないため、DAGExecutor を差し替えた
    統合実行で確認する。
    """

    class _NoopDAGExecutor:
        def __init__(self, *args, **kwargs) -> None:
            self.completed: set = set()
            self.failed: set = set()
            self.skipped: set = set()

        def compute_waves(self):
            return []

        async def execute(self):
            return {}

    def _run_with_resolver(self, resolver):
        from hve import orchestrator
        from hve.config import SDKConfig
        from hve.console import Console

        cfg = SDKConfig(dry_run=False, quiet=True)
        with patch(
            "hve.orchestrator.DAGExecutor",
            side_effect=lambda *a, **k: self._NoopDAGExecutor(),
        ), patch(
            "hve.orchestrator.rework.resolve_rework_targets", side_effect=resolver
        ), patch.object(Console, "event") as mock_event:
            result = asyncio.run(
                orchestrator.run_workflow(
                    workflow_id="aas",
                    params={"branch": "main", "selected_steps": ["1"]},
                    config=cfg,
                )
            )
        # patch.object(Console, "event") はインスタンスへの束縛を経ないため、
        # 呼び出し引数の末尾（メッセージ本体）だけを取り出せば self の有無に依存しない。
        messages = [call.args[-1] for call in mock_event.call_args_list]
        return result, messages

    def test_non_empty_targets_are_presented_exactly_once(self) -> None:
        _, messages = self._run_with_resolver(lambda *a, **k: ["3.3", "4.2"])
        rework_messages = [m for m in messages if "--steps" in m]
        assert len(rework_messages) == 1, f"提示は1回だけのはずが {len(rework_messages)} 回だった"
        assert "3.3" in rework_messages[0] and "4.2" in rework_messages[0]

    def test_empty_targets_present_nothing(self) -> None:
        _, messages = self._run_with_resolver(lambda *a, **k: [])
        assert not any("--steps" in m for m in messages)

    def test_resolver_failure_does_not_fail_the_run(self) -> None:
        result, messages = self._run_with_resolver(RuntimeError("boom"))
        assert not any("--steps" in m for m in messages)
        assert result.get("workflow_id") == "aas"
        assert not result.get("error")
