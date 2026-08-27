"""FR-DAG-09: DAG の外側で回すフィードバックループ（差戻し）の決定層。

`FR-DAG-01` の依存パターン 4 種は非巡回であり、レビュー Step から実装 Step へ
戻るエッジを DAG 内に表現できない。本モジュールは DAG の外側で「どの Step へ
戻すか」を決めるだけを担い、DAG そのものを変更しない。

判定入力は `FR-WF-CONF-03` が定める `Judgement` 列の 4 値語彙で、表の解析は
[hve/artifact_validation.py](artifact_validation.py) の既存実装を再利用する
（FR-MAINT-07）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, List

#: 差戻しの引き金となる判定。`NOT_MEASURED` / `NO_TARGET` は「測れていない」
#: 「目標が無い」であり、実装の不備を意味しないため引き金にしない（FR-WF-CONF-03）。
REWORK_TRIGGER_JUDGEMENT = "FAIL"


def report_has_rework_trigger(text: str) -> bool:
    """要件適合実測レポートに `FAIL` 判定の行があるか。"""
    try:
        from .artifact_validation import (  # noqa: PLC0415 - 重い依存の遅延 import
            _CONFORMANCE_TABLE_HEADER,
            _find_ai_agent_table,
            _normalize_ai_agent_label,
        )
    except ImportError:  # pragma: no cover - script execution path
        from artifact_validation import (  # type: ignore[no-redef]
            _CONFORMANCE_TABLE_HEADER,
            _find_ai_agent_table,
            _normalize_ai_agent_label,
        )

    judgement_key = _normalize_ai_agent_label("Judgement")
    rows = _find_ai_agent_table(text, _CONFORMANCE_TABLE_HEADER) or []
    return any(
        row.get(judgement_key, "").strip().upper() == REWORK_TRIGGER_JUDGEMENT for row in rows
    )


def _step_reports_rework(step: Any, repo_root: Path) -> bool:
    for relative in getattr(step, "output_paths", None) or []:
        if not str(relative).endswith(".md"):
            continue
        path = repo_root / str(relative)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        if report_has_rework_trigger(text):
            return True
    return False


def resolve_rework_targets(
    steps: Iterable[Any],
    completed_step_ids: Iterable[str],
    repo_root: Path,
) -> List[str]:
    """差戻し先 Step ID を宣言順・重複なしで返す。

    `rework_targets` を宣言し、かつ成果物に `FAIL` を報告した Step だけが対象。
    戻り先は静的宣言に限り、レビュー本文から推測してはならない。
    """
    completed = set(completed_step_ids)
    targets: List[str] = []
    for step in steps:
        declared = list(getattr(step, "rework_targets", None) or [])
        if not declared or getattr(step, "id", None) not in completed:
            continue
        if not _step_reports_rework(step, repo_root):
            continue
        for target in declared:
            if target not in targets:
                targets.append(target)
    return targets


def format_rework_suggestion(workflow_id: str, targets: Iterable[str]) -> str:
    """差戻し先を再実行コマンドの提案として 1 行へ整形する。

    自動再実行は行わないため、返すのは提示用の文字列だけとする（FR-DAG-09）。
    対象が空のときは空文字を返し、呼び出し側は何も提示しない。
    """
    ordered = [str(target) for target in targets if str(target)]
    if not ordered:
        return ""
    joined = ",".join(ordered)
    return (
        f"要件適合実測が FAIL を報告しました。差戻し先: {joined} / "
        f"再実行: python -m hve orchestrate --workflow {workflow_id} --steps {joined}"
    )
