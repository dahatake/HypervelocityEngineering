"""FR-1095 AC-517 AC-518 AC-519 / FR-1099 AC-538: the release judgment (HVE-Studio/release.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release  # noqa: E402


def _model(cases, goals=("G-001",), questions=(), acs=None, status="承認済み（依頼）", ledger="tests/system/ledger.json"):
    acs = acs if acs is not None else [{"id": "AC-001", "text": "x", "level": "system", "blocked": ""}]
    return {
        "meta": {"files": {"ledger": ledger}, "generatedAt": "2026-11-20T10:00:00+09:00"},
        "goals": [{"id": g, "title": g} for g in goals],
        "reqs": [{"id": "FR-001", "status": status, "statusKind": "approved" if status.startswith("承認済み") else "unknown",
                  "goal": "G-001", "body": "- 上位: G-001", "acs": acs}],
        "cases": [{"id": f"E2E-{i:03d}", "ac_ids": ["AC-001"], "status": s, "last_run_at": f"2026-11-1{i}T00:00:00+09:00"}
                  for i, s in enumerate(cases, 1)],
        "questions": list(questions),
    }


# FR-1095 AC-517: all pass -> met; any fail/blocked -> unmet (wins); otherwise not_run -> undetermined; none -> nothing to judge
def test_ac517_goal_verdict_rules():
    assert release.judge(_model(["pass", "pass"]))["goals"][0]["verdict"] == "met"
    assert release.judge(_model(["pass", "not_run", "fail"]))["goals"][0]["verdict"] == "unmet"
    assert release.judge(_model(["pass", "blocked"]))["goals"][0]["verdict"] == "unmet"
    assert release.judge(_model(["pass", "not_run"]))["goals"][0]["verdict"] == "undetermined"
    r = release.judge(_model([]))
    assert r["goals"][0]["verdict"] == "none" and r["ledgerRunAt"] is None and r["modelAt"]


# FR-1095 AC-518: "ok" only when judged with nothing to act on; "unknown" never shows as "ok"
def test_ac518_overall_state():
    assert release.judge(_model(["pass"]))["state"] == "ok"
    assert release.judge(_model(["fail"]))["state"] == "action"
    unknown = [_model(["pass"], ledger=None), _model([], goals=()), _model([])]
    for m in unknown:
        assert release.judge(m)["state"] == "unknown"
    reasons = {r["code"] for r in release.judge(_model([]))["reasons"]}
    assert "goal-without-cases" in reasons
    m = _model(["pass"])
    m["meta"]["error"] = "broken"
    assert release.judge(m)["state"] == "unknown"


# FR-1095 AC-518: cases of retired / pending requirements and retired criteria are not counted; approvals are reference only
def test_ac518_pending_and_retired_are_not_counted():
    assert release.judge(_model(["fail"], status="承認待ち"))["items"] == []
    assert release.judge(_model(["fail"], status="承認待ち"))["approvalRequests"] == 1
    retired = [{"id": "AC-001", "text": "（廃止 2026-11-20）x", "level": "system", "blocked": ""}]
    assert release.judge(_model(["fail"], acs=retired))["items"] == []


# FR-1095 AC-519: fail -> blocked -> stalled -> open questions (severity) -> not_run, IDs ascending within a kind
def test_ac519_order_of_action_items():
    acs = [{"id": "AC-001", "text": "x", "level": "system", "blocked": ""},
           {"id": "AC-002", "text": "y", "level": "system", "blocked": "Q-001 未回答"}]
    qs = [{"id": "Q-010", "severity": "高", "state": "未回答", "question": "a"},
          {"id": "Q-002", "severity": "重大", "state": "未回答", "question": "b"},
          {"id": "Q-003", "severity": "中", "state": "未回答", "question": "c"},
          {"id": "Q-004", "severity": "重大", "state": "回答済み", "question": "d"}]
    m = _model(["not_run", "blocked", "fail", "fail"], acs=acs, questions=qs)
    order = [(i["kind"], i["id"]) for i in release.judge(m)["items"]]
    assert order == [("fail", "E2E-003"), ("fail", "E2E-004"), ("blocked", "E2E-002"), ("stalled", "AC-002"),
                     ("question", "Q-002"), ("question", "Q-010"), ("not_run", "E2E-001")]


# FR-1099 AC-538: any "action" -> action; else any "unknown" -> unknown; all "ok" -> ok
def test_ac538_group_state():
    per = lambda *states: [{"name": f"r{i}", "path": f"/r{i}", "release": {"state": s, "reasons": [], "items": []}}
                           for i, s in enumerate(states)]
    assert release.combine(per("ok", "unknown", "action"))["state"] == "action"
    assert release.combine(per("ok", "unknown"))["state"] == "unknown"
    assert release.combine(per("ok", "ok"))["state"] == "ok"
    assert [r["state"] for r in release.combine(per("ok", "unknown", "action"))["repos"]] == ["ok", "unknown", "action"]
