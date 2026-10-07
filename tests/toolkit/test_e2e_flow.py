"""End-to-end rehearsal of one conductor run with deterministic stand-ins for the LLM work (plan §7.3)."""
import json

from conftest import SAMPLE_CATALOG, SAMPLE_RD, Repo, git


def test_full_run_rehearsal(repo):
    p = repo.path
    # stage 0
    out = repo.py("run-state.py", "start", "--options", "max_hours: 24\nparallel_workers: 2", check=True).stdout
    rid = out.split()[1]
    integ = f"run/{rid}"
    assert git(p, "branch", "--show-current") == integ
    repo.py("run-state.py", "stage", "1", check=True)

    # stage 1: rd-author writes the requirements (gate allows it only while rd-author is active)
    repo.gate("subagent-start", {"agentName": "rd-author"})
    for kind in ("FR", "AC", "AC", "Q", "PARAM"):
        repo.py("next-id.py", kind, check=True)
    repo.write("docs/requirements-definition.md", SAMPLE_RD)
    repo.write("docs/catalog.md", SAMPLE_CATALOG)
    repo.py("next-id.py", "--sync", check=True)
    assert repo.gate("subagent-stop", {"agentName": "rd-author", "agentId": "rd1", "response": "RESULT: done"}) == {}
    repo.commit("[RD] 初版")
    repo.py("run-state.py", "stage", "1", "--done", check=True)
    repo.py("run-state.py", "stage", "2", "--done", check=True)

    # stage 3: plan
    repo.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-001", "--ac", "AC-001", "--boundary", "申請", check=True)
    repo.py("run-state.py", "stage", "3", "--done", check=True)

    # stage 4: test-designer creates the system test before the implementation
    repo.gate("subagent-start", {"agentName": "test-designer"})
    repo.write("tests/system/e2e/fr_001_test.py",
               "# FR-001 AC-001\nfrom pathlib import Path\nimport sys\nsys.path.insert(0, 'src')\nfrom drafts import resume\nassert resume('x') == 'x'\n")
    repo.py("ledger.py", "--by", "test-designer", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "再開", "--layer", "e2e",
            "--command", "python tests/system/e2e/fr_001_test.py", "--canary", check=True)
    assert repo.gate("subagent-stop", {"agentName": "test-designer", "agentId": "td1", "response": "RESULT: done"}) == {}
    repo.commit("[ST] AC-001")
    repo.py("run-state.py", "stage", "4", "--done", check=True)
    assert repo.py("verify.py", "--docs-only").returncode == 0  # ledger is strict now and fully mapped

    # stage 5: implementer in its own worktree
    repo.py("run-state.py", "stage", "5", check=True)
    assert "I-01" in repo.py("run-state.py", "queue", "ready", "--parallel", "2", check=True).stdout
    wt = p / "work" / "worktrees" / f"{rid}-I-01"
    branch = f"work/{rid}/I-01"
    git(p, "worktree", "add", "-q", str(wt), "-b", branch, integ)
    repo.py("run-state.py", "queue", "set", "I-01", "--status", "doing", "--branch", branch, "--attempts", "+1", check=True)
    repo.gate("subagent-start", {"agentName": "implementer"})
    worker = Repo(wt)
    assert repo.gate("pre-tool", {"toolName": "create", "toolArgs": {"path": str(wt / "src" / "drafts.py")}}) == {}
    worker.write("src/drafts.py", "# FR-001 AC-001\ndef resume(v):\n    return v\n")
    worker.write("tests/unit/test_drafts.py", "# FR-001 AC-001\n")
    worker.write("docs/catalog.md", SAMPLE_CATALOG.replace("| 未実装 | 未実装 |", "| src/drafts.py | tests/unit/test_drafts.py |"))
    run_out = worker.py("ledger.py", "run", "--cases", "E2E-001", "--no-record", check=True).stdout
    assert "E2E-001 FR-001 pass" in run_out
    worker.commit("[FR-001] 下書きの再開")
    assert worker.py("verify.py", "--quick").returncode == 0  # CHK-12 compares against the integration branch
    res = repo.gate("subagent-stop", {"agentName": "implementer", "agentId": "im1", "response": f"WORKTREE: {wt}\nGATE: pass"})
    assert res == {}

    # integration (serial) on the integration branch
    git(p, "merge", "--no-ff", "-q", "-m", "merge I-01", branch)
    led_out = repo.py("ledger.py", "--by", "conductor", "run", "--select", "changed", "--canary-first", "--stop-on-canary-fail", check=True).stdout
    assert "E2E-001 FR-001 pass" in led_out
    repo.commit("ledger status")
    git(p, "worktree", "remove", "--force", str(wt))
    git(p, "branch", "-d", branch)
    repo.py("run-state.py", "queue", "set", "I-01", "--status", "done", "--summary", "共通部品なし", check=True)
    assert repo.py("verify.py", "--run", "current").returncode == 0  # CHK-21: done item is in the catalog and passes

    # the conductor may not stop yet
    assert repo.gate("agent-stop", {"sessionId": "S"}).get("decision") == "block"

    # stage 6
    repo.py("run-state.py", "stage", "6", check=True)
    assert repo.py("verify.py", "--strict", "--run", "current").returncode == 0
    repo.write(f"work/runs/{rid}/run-report.md", "結果: 全件完了\n")
    repo.py("run-state.py", "stage", "6", "--done", check=True)
    assert repo.gate("agent-stop", {"sessionId": "S"}) == {}
    repo.py("run-state.py", "finish", "--result", "全件完了", check=True)
    repo.commit("[RUN] finish")
    hist = repo.read("docs/run-history.md")
    assert f"| {rid} |" in hist and "| 全件完了 | FR-001 | 0 | 1/1 |" in hist
    assert json.loads(repo.read("tests/system/ledger.json"))["cases"][0]["status"] == "pass"
    assert repo.py("verify.py", "--strict").returncode == 0
