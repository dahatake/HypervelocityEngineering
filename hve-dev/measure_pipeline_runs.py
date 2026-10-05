"""比較実測（DAG review plan N5-3）の run 指標を集計する開発者用スクリプト。

HVE の実行時の挙動は変えない。run ディレクトリの観測イベント
（`<run-dir>/observability/events-*.jsonl`、FR-RTO-03）を既存の reducer
`hve.runtime_observability.RuntimeMetrics` で集計し、AI クレジットやトークンの
計算を再実装しない（FR-MAINT-07）。イベントから取れない指標（人の入力回数、
デプロイ後 E2E の合否、盲検レビューの件数）は `--manual-json` で与える。
値を取れない指標は `null` と理由を出力し、推測で埋めない。

usage:
    python hve-dev/measure_pipeline_runs.py --run-dir work/run/<run-id> --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hve.runtime_observability import RuntimeMetrics, read_events  # noqa: E402

METRIC_KEYS = (
    "human_inputs",
    "total_elapsed_seconds",
    "ai_credits",
    "premium_requests",
    "input_tokens",
    "output_tokens",
    "sessions",
    "steps_done",
    "steps_failed",
    "g_out_passed",
    "deploy_e2e_passed",
    "review_critical",
    "review_major",
)
_MANUAL_KEYS = ("human_inputs", "deploy_e2e_passed", "review_critical", "review_major")


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _metric(value: Any, reason: str = "") -> Dict[str, Any]:
    return {"value": value, "reason": "" if value is not None else reason}


def measure(run_dir: Path, manual: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """1 run の指標を返す。全キーを必ず含め、取れない値は None と理由にする。"""
    events = read_events(run_dir)
    metrics = RuntimeMetrics()
    for event in events:
        metrics.apply(event)

    no_events = "観測イベント（observability/events-*.jsonl）が無い"
    result: Dict[str, Any] = {}

    stamps = [ts for ts in (_parse_ts(e.get("ts")) for e in events) if ts is not None]
    elapsed = (max(stamps) - min(stamps)).total_seconds() if len(stamps) >= 2 else None
    result["total_elapsed_seconds"] = _metric(elapsed, no_events if not events else "時刻付きイベントが 2 件未満")

    if metrics.aiu_nano_total > 0:
        result["ai_credits"] = _metric(metrics.aiu_total)
    else:
        reason = metrics.credit_unavailable_reason or (no_events if not events else "usage_credit イベントが無い")
        result["ai_credits"] = _metric(None, reason)

    has_usage = metrics.assistant_usage_count > 0
    result["premium_requests"] = _metric(metrics.display_reqs if has_usage or metrics.premium_requests_total else None, no_events if not events else "使用量イベントが無い")
    result["input_tokens"] = _metric(metrics.input_tokens_total if has_usage else None, "assistant_usage イベントが無い")
    result["output_tokens"] = _metric(metrics.output_tokens_total if has_usage else None, "assistant_usage イベントが無い")

    statuses = metrics.step_status
    if statuses:
        done = sum(1 for s in statuses.values() if s == "done")
        failed = sum(1 for s in statuses.values() if s == "failed")
        # 1 Step は 1 つの main session を持つ（FR-WF-OUT-12 の継続も同じ session）。
        result["sessions"] = _metric(len(statuses))
        result["steps_done"] = _metric(done)
        result["steps_failed"] = _metric(failed)
        # G-OUT（FR-WF-OUT-01）に落ちた Step は failed になるため、failed 0 件を合格とする。
        result["g_out_passed"] = _metric(failed == 0)
    else:
        for key in ("sessions", "steps_done", "steps_failed", "g_out_passed"):
            result[key] = _metric(None, no_events if not events else "step_status イベントが無い")

    manual = manual or {}
    for key in _MANUAL_KEYS:
        if key in manual and manual[key] is not None:
            result[key] = _metric(manual[key])
        else:
            result[key] = _metric(None, "観測イベントに記録が無い。手順書どおり --manual-json で与える")

    missing = [key for key in METRIC_KEYS if key not in result]
    assert not missing, missing
    return {
        "run_dir": run_dir.as_posix(),
        "event_count": len(events),
        "metrics": {key: result[key] for key in METRIC_KEYS},
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--manual-json", type=Path, default=None)
    parser.add_argument("--format", choices=("json",), default="json")
    args = parser.parse_args(argv)

    if not args.run_dir.is_dir():
        print(f"run ディレクトリがありません: {args.run_dir}", file=sys.stderr)
        return 2
    manual = None
    if args.manual_json is not None:
        try:
            manual = json.loads(args.manual_json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"--manual-json を読めません: {exc}", file=sys.stderr)
            return 2
        if not isinstance(manual, dict):
            print("--manual-json は JSON object でなければなりません", file=sys.stderr)
            return 2
    print(json.dumps(measure(args.run_dir, manual), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
