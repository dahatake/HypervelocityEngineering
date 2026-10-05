"""N5-3: 比較実測の集計スクリプト（hve-dev/measure_pipeline_runs.py）のテスト。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "hve-dev" / "measure_pipeline_runs.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_pipeline_runs", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_events(run_dir: Path, events: list[dict]) -> None:
    target = run_dir / "observability"
    target.mkdir(parents=True)
    with (target / "events-100.jsonl").open("w", encoding="utf-8") as fh:
        for seq, event in enumerate(events, start=1):
            fh.write(json.dumps({"pid": 100, "seq": seq, **event}) + "\n")


def test_every_metric_key_is_present_with_reason_when_no_events(tmp_path: Path) -> None:
    module = _load()
    result = module.measure(tmp_path)
    assert set(result["metrics"]) == set(module.METRIC_KEYS)
    for metric in result["metrics"].values():
        assert metric["value"] is None
        assert metric["reason"]


def test_metrics_are_folded_by_the_shared_reducer(tmp_path: Path) -> None:
    module = _load()
    _write_events(
        tmp_path,
        [
            {"ts": "2026-09-30T00:00:00+00:00", "kind": "step_status", "step": "1", "status": "running"},
            {"ts": "2026-09-30T00:00:10+00:00", "kind": "assistant_usage", "step": "1", "input": 100, "output": 20},
            {"ts": "2026-09-30T00:00:11+00:00", "kind": "usage_credit", "api_call_id": "a", "nano_aiu": 2_000_000_000},
            {"ts": "2026-09-30T00:01:00+00:00", "kind": "step_status", "step": "1", "status": "done"},
            {"ts": "2026-09-30T00:01:30+00:00", "kind": "step_status", "step": "2", "status": "failed"},
        ],
    )
    metrics = module.measure(tmp_path, {"human_inputs": 1, "deploy_e2e_passed": True})["metrics"]
    assert metrics["total_elapsed_seconds"]["value"] == 90.0
    assert metrics["ai_credits"]["value"] == 2.0
    assert metrics["input_tokens"]["value"] == 100
    assert metrics["sessions"]["value"] == 2
    assert metrics["steps_done"]["value"] == 1
    assert metrics["steps_failed"]["value"] == 1
    assert metrics["g_out_passed"]["value"] is False
    assert metrics["human_inputs"]["value"] == 1
    assert metrics["deploy_e2e_passed"]["value"] is True
    assert metrics["review_critical"]["value"] is None


def test_cli_prints_json_and_exits_zero(tmp_path: Path, capsys) -> None:
    module = _load()
    assert module.main(["--run-dir", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["metrics"]) == set(module.METRIC_KEYS)
