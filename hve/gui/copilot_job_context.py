"""hve.gui.copilot_job_context — 完了ジョブを Copilot と相談するための初期コンテキスト。

FR-GUI-14。選択したジョブの実在パスだけを列挙し、ファイル本文は埋め込まない。
選択した run のルート外は自動探索しない。
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from ..prompt_loader import load_prompt_file
except ImportError:  # pragma: no cover - top-level import compatibility
    load_prompt_file = importlib.import_module("hve.prompt_loader").load_prompt_file

if TYPE_CHECKING:
    from hve.gui.job_interaction_model import JobTarget
else:
    JobTarget = Any

__all__ = ["JobResultContext", "build_job_result_context"]


_JOB_RESULT_CONTEXT_TEMPLATE = load_prompt_file(
    "runtime/gui/copilot-job-result-context.prompt.md"
)


def _fragment(name: str) -> str:
    """1 行の固定フラグメントを、末尾改行を除いた形で返す。"""
    return load_prompt_file(f"runtime/gui/{name}.prompt.md").rstrip("\n")


_STEP_LINE = _fragment("copilot-job-result-step-line")
_RETURNCODE_LINE = _fragment("copilot-job-result-returncode-line")
_DETAILS_INTRO = _fragment("copilot-job-result-details-intro")
_TRUNCATED_NOTICE = _fragment("copilot-job-result-truncated-notice")
_NO_DETAILS = _fragment("copilot-job-result-no-details")

# run ルート配下から自動収集する完了報告の上限（列挙が肥大化しないための実務上の上限）。
_MAX_COMPLETION_REPORTS = 20


@dataclass(frozen=True)
class JobResultContext:
    """新しい Copilot CLI チャットへ渡す初期コンテキスト。"""

    run_id: str
    target: JobTarget
    paths: tuple[Path, ...]
    prompt: str


def _existing(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _collect_paths(work_root: Path, artifacts: Iterable[Path]) -> tuple[list[Path], bool]:
    collected: list[Path] = []
    truncated = False
    if _existing(work_root):
        console_log = work_root / "console-log.txt"
        if _existing(console_log):
            collected.append(console_log)
        gui_logs = work_root / "gui-logs"
        if _existing(gui_logs):
            collected.append(gui_logs)
        reports = sorted(work_root.glob("**/completion-report.md"))
        truncated = len(reports) > _MAX_COMPLETION_REPORTS
        collected.extend(reports[:_MAX_COMPLETION_REPORTS])

    for artifact in artifacts:
        candidate = Path(artifact)
        if _existing(candidate):
            collected.append(candidate)

    unique = {str(p): p for p in collected}
    return [unique[key] for key in sorted(unique)], truncated


def build_job_result_context(
    target: JobTarget,
    *,
    work_root: Path,
    returncode: int | None = None,
    artifacts: Sequence[Path] = (),
) -> JobResultContext:
    """ジョブ結果を相談するための初期プロンプトと参照パスを構成する。"""
    work_root = Path(work_root)
    paths, truncated = _collect_paths(work_root, artifacts)

    step_block = ""
    if target.step_id:
        step_label = f"{target.step_id} {target.step_title}".strip()
        step_block = _STEP_LINE.format(step_label=step_label) + "\n"

    returncode_block = ""
    if returncode is not None:
        returncode_block = _RETURNCODE_LINE.format(returncode=returncode) + "\n"

    if paths:
        detail_lines = [_DETAILS_INTRO]
        detail_lines.extend(f"- {path}" for path in paths)
        if truncated:
            detail_lines.append(
                _TRUNCATED_NOTICE.format(limit=_MAX_COMPLETION_REPORTS)
            )
        details_block = "\n".join(detail_lines)
    else:
        details_block = _NO_DETAILS

    return JobResultContext(
        run_id=work_root.name,
        target=target,
        paths=tuple(paths),
        prompt=_JOB_RESULT_CONTEXT_TEMPLATE.format(
            run_id=work_root.name,
            workflow_id=target.workflow_id,
            instance_id=target.instance_id,
            step_block=step_block,
            status=target.status,
            returncode_block=returncode_block,
            details_block=details_block,
        ),
    )
