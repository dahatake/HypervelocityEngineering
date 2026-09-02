"""FR-CLI-87: Wave 境界の承認ゲート。"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hve import approval
from hve.__main__ import _build_parser
from hve.workflow_registry import StepDef

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_DAG_EXECUTOR = _REPO_ROOT / "hve" / "dag_executor.py"


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


class TestWaveDetection:
    def test_wave_without_gate_needs_no_approval(self) -> None:
        steps = [SimpleNamespace(id="1.1"), SimpleNamespace(id="1.2")]
        assert approval.wave_requires_approval(steps) is False

    def test_wave_with_gate_needs_approval(self) -> None:
        steps = [SimpleNamespace(id="1.1"), SimpleNamespace(id="1.2", approval_gate=True)]
        assert approval.wave_requires_approval(steps) is True

    def test_step_def_declares_the_gate_flag(self) -> None:
        base = {"id": "x", "title": "t", "custom_agent": "A"}
        assert StepDef(**base).approval_gate is False
        assert StepDef(**base, approval_gate=True).approval_gate is True


class TestApprovalPrompt:
    def test_yes_passes(self) -> None:
        approval.request_wave_approval(
            [SimpleNamespace(id="1.1")], 1, interactive=True, input_fn=lambda _: "y"
        )

    @pytest.mark.parametrize("answer", ["", "n", "no", "  ", "yeah"])
    def test_anything_but_yes_declines(self, answer: str) -> None:
        with pytest.raises(approval.ApprovalDeclined):
            approval.request_wave_approval(
                [SimpleNamespace(id="1.1")], 1, interactive=True, input_fn=lambda _: answer
            )

    def test_non_interactive_declines_without_prompting(self) -> None:
        def _must_not_be_called(_prompt: str) -> str:  # pragma: no cover - 呼ばれないこと自体が期待
            raise AssertionError("非対話では入力を求めてはならない")

        with pytest.raises(approval.ApprovalDeclined):
            approval.request_wave_approval(
                [SimpleNamespace(id="1.1")], 1, interactive=False, input_fn=_must_not_be_called
            )

    def test_interrupted_input_declines(self) -> None:
        def _raise(_prompt: str) -> str:
            raise EOFError

        with pytest.raises(approval.ApprovalDeclined):
            approval.request_wave_approval(
                [SimpleNamespace(id="1.1")], 1, interactive=True, input_fn=_raise
            )

    def test_message_names_the_blocking_steps(self) -> None:
        with pytest.raises(approval.ApprovalDeclined) as excinfo:
            approval.request_wave_approval(
                [SimpleNamespace(id="3.2"), SimpleNamespace(id="3.3")],
                2,
                interactive=False,
            )
        assert "3.2" in str(excinfo.value)
        assert "3.3" in str(excinfo.value)


class TestExecutorPropagatesDecline:
    def test_on_wave_start_does_not_swallow_approval_declined(self) -> None:
        source = _DAG_EXECUTOR.read_text(encoding="utf-8")
        marker = "self._on_wave_start(executable, self._wave_counter)"
        assert marker in source
        tail = source.split(marker, 1)[1]
        # 汎用 except より前に ApprovalDeclined の再送出が置かれていること。
        declined = tail.find("ApprovalDeclined")
        generic = tail.find("except Exception")
        assert declined != -1, "ApprovalDeclined の再送出が無い"
        assert declined < generic, "汎用 except が ApprovalDeclined を先に捕捉している"

    def test_run_workflow_catches_decline_before_the_generic_handler(self) -> None:
        """`except BaseException` の continue_on_error 縮退へ落とさないこと。

        先に汎用ハンドラへ入ると fatal 分類→残ステップ skip→exit 0 となり、
        承認拒否が成功として扱われる。
        """
        source = (_REPO_ROOT / "hve" / "orchestrator.py").read_text(encoding="utf-8")
        marker = "results = await executor.execute()"
        assert marker in source
        tail = source.split(marker, 1)[1]
        declined = tail.find("except approval.ApprovalDeclined")
        generic = tail.find("except BaseException")
        assert declined != -1, "ApprovalDeclined の捕捉が無い"
        assert declined < generic, "except BaseException が先に承認拒否を捕捉している"


class TestDeclaredGates:
    def test_at_least_one_step_declares_the_gate(self) -> None:
        from hve.workflow_registry import list_workflows

        declared = [
            (workflow.id, step.id)
            for workflow in list_workflows()
            for step in getattr(workflow, "steps", [])
            if getattr(step, "approval_gate", False)
        ]
        assert declared, "approval_gate を宣言した Step が 1 件も無く、機能が不活性である"


class TestCliWiring:
    def test_approval_gates_option_is_registered(self) -> None:
        args = _build_parser().parse_args(["orchestrate", "-w", "aas", "--approval-gates"])
        assert args.approval_gates is True

    def test_approval_gates_defaults_to_false(self) -> None:
        args = _build_parser().parse_args(["orchestrate", "-w", "aas"])
        assert args.approval_gates is False


class TestRequirementIsDeclared:
    def test_requirement_declares_the_defaults_and_gui_scope(self) -> None:
        block = _requirement_block("FR-CLI-87")
        assert "--approval-gates" in block
        assert "既定は無効" in block
        assert "FR-GUI-23" in block


class TestDeclineRecordsWaveIndex:
    """FR-CLI-87: 承認・拒否の記録は `approval:<wave_index>` とする。

    拒否経路だけが wave 番号を捨てると、どの Wave で停止したかを
    FR-STATE-04 の進捗ストアから復元できない。
    """

    def test_declined_exception_carries_the_wave_index(self) -> None:
        with pytest.raises(approval.ApprovalDeclined) as excinfo:
            approval.request_wave_approval(
                [SimpleNamespace(id="1.3")], 7, interactive=False
            )
        assert excinfo.value.wave_index == 7

    def test_no_literal_declined_step_id_remains(self) -> None:
        """`approval:declined` を step_id として渡すリテラルが残っていないこと。

        単純な部分一致ではコメント文も拾うため、文字列リテラルだけを AST で集める。
        """
        tree = ast.parse((_REPO_ROOT / "hve" / "orchestrator.py").read_text(encoding="utf-8"))
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert "approval:declined" not in literals

    def test_requirement_declares_the_record_key(self) -> None:
        block = _requirement_block("FR-CLI-87")
        assert "approval:<wave_index>" in block


class TestDeclineIntegration:
    """FR-CLI-87: `run_workflow` が承認拒否を blocked として返すことを確認する。

    Durable contextを持つ公開経路のapproval pseudo-rowは
    ``test_orchestrator_durable_resume.py::TestApprovalRecords`` が固定する。
    contextを持たない内部直接呼出しはLegacy JSONLへdual-writeせず、拒否結果だけを返す。
    """

    class _DeclineDAGExecutor:
        def __init__(self, *args, **kwargs) -> None:
            self.completed: set = set()
            self.failed: set = set()
            self.skipped: set = set()

        def compute_waves(self):
            return []

        async def execute(self):
            raise approval.ApprovalDeclined("承認が得られませんでした。", wave_index=3)

    def test_run_workflow_blocks_without_legacy_jsonl_write(self) -> None:
        from hve import orchestrator, run_progress
        from hve.config import SDKConfig

        cfg = SDKConfig(dry_run=False, quiet=True)
        with patch(
            "hve.orchestrator.DAGExecutor",
            side_effect=lambda *a, **k: self._DeclineDAGExecutor(),
        ), patch("hve.run_progress.record_step") as mock_record:
            result = asyncio.run(
                orchestrator.run_workflow(
                    workflow_id="aas",
                    params={"branch": "main", "selected_steps": ["1"]},
                    config=cfg,
                )
            )

        mock_record.assert_not_called()
        assert result["error"] == "承認が得られませんでした。"
        assert result["blocked"] == ["1"]
