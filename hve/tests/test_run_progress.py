"""FR-STATE-04 / FR-CLI-86: Workflow 進捗の保存と `--resume-run` による再実行。

§5.6 が全廃した SDK セッションの復元とは異なり、本機能が保存するのは
「どの Step が成功したか」という HVE 自身が所有する進捗だけである。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from hve import run_progress
from hve.__main__ import _build_parser

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_GITIGNORE = _REPO_ROOT / ".gitignore"


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


@pytest.fixture()
def progress_path(tmp_path: Path) -> Path:
    return tmp_path / ".run-progress.jsonl"


class TestProgressStore:
    def test_completed_steps_returns_only_succeeded_ids(self, progress_path: Path) -> None:
        run_progress.record_step("r1", "aas", "1.1", "succeeded", path=progress_path)
        run_progress.record_step("r1", "aas", "1.2", "failed", path=progress_path)
        run_progress.record_step("r1", "aas", "1.3", "succeeded", path=progress_path)
        assert run_progress.completed_steps("r1", path=progress_path) == frozenset({"1.1", "1.3"})

    def test_unknown_run_returns_none(self, progress_path: Path) -> None:
        run_progress.record_step("r1", "aas", "1.1", "succeeded", path=progress_path)
        assert run_progress.completed_steps("r2", path=progress_path) is None

    def test_missing_file_returns_none(self, progress_path: Path) -> None:
        assert run_progress.completed_steps("r1", path=progress_path) is None

    def test_records_are_isolated_per_run(self, progress_path: Path) -> None:
        run_progress.record_step("r1", "aas", "1.1", "succeeded", path=progress_path)
        run_progress.record_step("r2", "aas", "2.1", "succeeded", path=progress_path)
        assert run_progress.completed_steps("r1", path=progress_path) == frozenset({"1.1"})
        assert run_progress.completed_steps("r2", path=progress_path) == frozenset({"2.1"})

    def test_record_holds_only_the_declared_fields(self, progress_path: Path) -> None:
        run_progress.record_step("r1", "aas", "1.1", "succeeded", path=progress_path)
        record = json.loads(progress_path.read_text(encoding="utf-8").splitlines()[0])
        assert set(record) == {
            "schema_version",
            "ts",
            "run_id",
            "workflow_id",
            "step_id",
            "status",
        }

    def test_file_uses_lf_without_bom(self, progress_path: Path) -> None:
        run_progress.record_step("r1", "aas", "1.1", "succeeded", path=progress_path)
        raw = progress_path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r\n" not in raw

    def test_write_failure_does_not_raise(self, tmp_path: Path) -> None:
        # 親がファイルであるパスは書き込めないが、run を失敗させてはならない。
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        run_progress.record_step("r1", "aas", "1.1", "succeeded", path=blocker / "p.jsonl")

    def test_unreadable_line_is_ignored(self, progress_path: Path) -> None:
        progress_path.write_text("not-json\n", encoding="utf-8")
        run_progress.record_step("r1", "aas", "1.1", "succeeded", path=progress_path)
        assert run_progress.completed_steps("r1", path=progress_path) == frozenset({"1.1"})


class TestRequirementIsDeclared:
    def test_fr_state_04_declares_the_store(self) -> None:
        block = _requirement_block("FR-STATE-04")
        assert "hve/.run-progress.jsonl" in block
        assert "復元しない" in block

    def test_fr_cli_86_declares_fail_closed_for_unknown_run(self) -> None:
        block = _requirement_block("FR-CLI-86")
        assert "--resume-run" in block
        assert "fail-closed" in block

    def test_default_path_matches_the_requirement(self) -> None:
        assert run_progress.DEFAULT_PROGRESS_PATH.name == ".run-progress.jsonl"
        assert run_progress.DEFAULT_PROGRESS_PATH.parent.name == "hve"

    def test_progress_file_is_gitignored(self) -> None:
        assert "hve/.run-progress.jsonl" in _GITIGNORE.read_text(encoding="utf-8")


class TestCliWiring:
    def test_resume_run_option_is_registered(self) -> None:
        args = _build_parser().parse_args(["orchestrate", "-w", "aas", "--resume-run", "abc123"])
        assert args.resume_run == "abc123"

    def test_resume_run_defaults_to_none(self) -> None:
        args = _build_parser().parse_args(["orchestrate", "-w", "aas"])
        assert args.resume_run is None


class TestRunWorkflowResultShape:
    """`run_workflow` の全 dict 戻り値が呼び出し側の判定キーを持つこと。

    [hve/__main__.py](hve/__main__.py) の終了コード判定は `blocked` / `error` /
    `failed` を参照する。独自のキー集合で早期 return すると、停止させたい経路が
    成功（exit 0）として扱われる。FR-CLI-86 の fail-closed が fail-open へ
    転じた実例があるため、既存 17 箇所が共通して持つキーを不変条件として固定する。
    """

    REQUIRED_KEYS = {"workflow_id", "completed", "failed", "skipped", "elapsed_total"}

    def test_every_dict_return_carries_the_required_keys(self) -> None:
        source = (_REPO_ROOT / "hve" / "orchestrator.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        run_workflow = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == "run_workflow"
        )
        nested = {
            id(inner)
            for outer in ast.walk(run_workflow)
            if isinstance(outer, (ast.FunctionDef, ast.AsyncFunctionDef))
            and outer is not run_workflow
            for inner in ast.walk(outer)
        }

        violations = []
        for node in ast.walk(run_workflow):
            if not isinstance(node, ast.Return) or id(node) in nested:
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            keys = {
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if not self.REQUIRED_KEYS <= keys:
                violations.append((node.lineno, sorted(self.REQUIRED_KEYS - keys)))

        assert not violations, f"必須キーを欠く dict 戻り値: {violations}"
