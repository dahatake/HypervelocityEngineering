"""hve.gui.copilot_job_context — 完了ジョブを Copilot と相談するための初期コンテキスト。

FR-GUI-14。選択したジョブの実在パスだけを列挙し、ファイル本文は埋め込まない。
選択した run のルート外は自動探索しない。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .job_interaction_model import JobTarget

__all__ = ["JobResultContext", "build_job_result_context"]

# run ルート配下から自動収集する完了報告の上限（列挙が肥大化しないための実務上の上限）。
_MAX_COMPLETION_REPORTS = 20


@dataclass(frozen=True)
class JobResultContext:
    """新しい Copilot CLI チャットへ渡す初期コンテキスト。"""

    run_id: str
    target: JobTarget
    paths: Tuple[Path, ...]
    prompt: str


def _existing(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _collect_paths(work_root: Path, artifacts: Iterable[Path]) -> Tuple[List[Path], bool]:
    collected: List[Path] = []
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
    returncode: Optional[int] = None,
    artifacts: Sequence[Path] = (),
) -> JobResultContext:
    """ジョブ結果を相談するための初期プロンプトと参照パスを構成する。"""
    work_root = Path(work_root)
    paths, truncated = _collect_paths(work_root, artifacts)

    lines = [
        "直前に実行した HVE ジョブの結果を確認したい。",
        f"- Run ID: {work_root.name}",
        f"- Workflow: {target.workflow_id} (instance: {target.instance_id})",
    ]
    if target.step_id:
        step_label = f"{target.step_id} {target.step_title}".strip()
        lines.append(f"- Step: {step_label}")
    lines.append(f"- 状態: {target.status}")
    if returncode is not None:
        lines.append(f"- 終了コード: {returncode}")

    if paths:
        lines.append("")
        lines.append("次のファイルを読んで、失敗原因・残作業・次の一手を教えてほしい。")
        lines.extend(f"- {path}" for path in paths)
        if truncated:
            lines.append(
                f"- （完了報告は先頭 {_MAX_COMPLETION_REPORTS} 件のみ列挙。他は run ディレクトリを直接探索してほしい）"
            )
    else:
        lines.append("")
        lines.append("参照可能なログ・成果物は残っていない。会話で状況を確認したい。")

    return JobResultContext(
        run_id=work_root.name,
        target=target,
        paths=tuple(paths),
        prompt="\n".join(lines),
    )
