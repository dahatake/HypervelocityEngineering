import json

from test_run_state import start_run

OLD_HISTORY = """# 実行履歴

説明

| run-id | 開始 | 終了 | HEAD | 結果 | 実装した要求 ID | BLOCKED | AC pass 率 | 経過時間 | 1 回目のゲート通過率 | AI クレジット |
|---|---|---|---|---|---|---|---|---|---|---|
| 202601010000 | 2026-01-01T00:00 | 2026-01-01T04:00 | abc | 全件完了 | FR-001, FR-002 | 0 | 2/2 | 4.0h | 1/2 | 10 |
"""


def finish_run(repo, rid):
    repo.py("run-state.py", "stage", "6", "--done", check=True)
    repo.write(f"work/runs/{rid}/run-report.md", "結果\n")
    return repo.py("run-state.py", "finish", "--credits", "3", check=True).stdout


def unblock_and_pass(repo):
    rd = repo.read("docs/requirements-definition.md").replace("  - BLOCKED: Q-001\n", "")
    repo.write("docs/requirements-definition.md", rd)
    cid = repo.py("ledger.py", "--by", "test-designer", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "再開",
                  "--layer", "e2e", "--command", "python -c pass", check=True).stdout.strip()
    repo.write("work/evidence.log", "ok\n")
    repo.py("ledger.py", "set", cid, "pass", "--evidence", "work/evidence.log", check=True)


def test_human_and_kpi_run(sample):
    rid = start_run(sample)
    sample.py("run-state.py", "human", "answers", "--note", "Q-001: B", check=True)
    assert sample.py("run-state.py", "human", "bogus").returncode != 0
    sample.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-001", "--ac", "AC-001", check=True)
    sample.py("run-state.py", "queue", "set", "I-01", "--status", "done", "--attempts", "+1", check=True)

    k = json.loads(sample.py("kpi.py", "run", "--format", "json", check=True).stdout)
    assert k["human_interventions"] == 2 and k["human_breakdown"] == {"request": 1, "answers": 1}
    assert k["implemented"] == ["FR-001"] and k["verified"] == []
    assert "BLOCKED" in k["not_verified"]["FR-001"]
    assert k["first_gate"]["rate"] == 1.0 and k["nsm"] == 0.0

    unblock_and_pass(sample)
    k = json.loads(sample.py("kpi.py", "run", "--format", "json", check=True).stdout)
    assert k["verified"] == ["FR-001"] and k["nsm"] == 0.5
    assert k["traceability"] == {"traced": 1, "total": 1, "rate": 1.0}
    assert k["ac_pass"]["rate"] == 1.0

    md = sample.py("kpi.py", "run", check=True).stdout
    assert "| North Star: 人の介入 1 回あたりの検証済み要求 | 0.50 |" in md
    sample.py("kpi.py", "run", "--format", "html", "--out", f"work/runs/{rid}/kpi.html", check=True)
    html = sample.read(f"work/runs/{rid}/kpi.html")
    assert html.startswith("<!doctype html>") and 'class="ok"' in html

    out = finish_run(sample, rid)
    assert "| 2 | 1/1 |" in out
    hist = json.loads(sample.py("kpi.py", "history", "--format", "json", check=True).stdout)
    assert hist["runs"] == 1 and hist["nsm"] == 0.5 and hist["human"]["mean"] == 2.0
    assert hist["unattended_completion"]["rate"] == 1.0
    # finished runs stay readable
    k = json.loads(sample.py("kpi.py", "run", "--run", rid, "--format", "json", check=True).stdout)
    assert k["status"] == "finished"


def test_history_upgrade_from_older_version(sample):
    sample.write("docs/run-history.md", OLD_HISTORY)
    rid = start_run(sample)
    sample.py("run-state.py", "stage", "3", "--done", check=True)
    finish_run(sample, rid)
    text = sample.read("docs/run-history.md")
    assert "| AI クレジット | 人の介入 | 検証済み要求 |" in text
    assert "|---|---|---|---|---|---|---|---|---|---|---|---|---|" in text
    assert "| 10 | - | - |" in text
    assert f"| {rid} |" in text and "| 1 | 0/0 |" in text
    hist = json.loads(sample.py("kpi.py", "history", "--format", "json", check=True).stdout)
    assert hist["runs"] == 2
    assert hist["human"]["runs_measured"] == 1  # the old row has no intervention count
    assert hist["first_gate"] == {"pass": 1, "total": 2, "rate": 0.5}
    assert hist["hours_per_requirement"] == 2.0
    assert sample.py("rdcheck.py", "check", "--base", "none").returncode == 0


def test_kpi_without_runs(repo):
    proc = repo.py("kpi.py", "run")
    assert proc.returncode != 0 and "run がありません" in (proc.stdout + proc.stderr)
    hist = json.loads(repo.py("kpi.py", "history", "--format", "json", check=True).stdout)
    assert hist["runs"] == 0 and hist["nsm"] is None
