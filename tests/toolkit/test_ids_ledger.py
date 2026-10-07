import json

from conftest import git


def test_next_id_allocates_and_registers(sample):
    out = sample.py("next-id.py", "FR", "--note", "test", check=True).stdout.split()
    assert out == ["FR-002"]
    out = sample.py("next-id.py", "AC", "--count", "2", check=True).stdout.split()
    assert out == ["AC-003", "AC-004"]
    assert sample.py("next-id.py", "NFR-SEC", check=True).stdout.strip() == "NFR-SEC-001"
    reg = sample.read("docs/id-registry.md")
    assert "| FR-002 | FR | 採番済み |" in reg and "| AC-004 | AC | 採番済み |" in reg
    assert sample.py("next-id.py", "--peek", "FR", check=True).stdout.strip() == "FR-003"


def test_next_id_is_shared_across_worktrees(sample):
    wt = sample.path / "work" / "worktrees" / "r-1"
    git(sample.path, "worktree", "add", "-q", str(wt), "-b", "work/r/1")
    from conftest import Repo
    other = Repo(wt)
    a = sample.py("next-id.py", "FR", check=True).stdout.strip()
    b = other.py("next-id.py", "FR", check=True).stdout.strip()
    assert a == "FR-002" and b == "FR-003"


def test_sync_marks_deleted_and_unused(sample):
    sample.py("next-id.py", "Q", check=True)
    rd = sample.read("docs/requirements-definition.md").replace(
        "| Q-001 | 高 | 保持期間の起点はいつか | A: 作成時 / B: 最終更新時 | B | 未回答 | |\n", "")
    rd = rd.replace("  - BLOCKED: Q-001\n", "")
    sample.write("docs/requirements-definition.md", rd)
    out = sample.py("next-id.py", "--sync", "--finalize", check=True).stdout
    assert "Q-001: 使用中 -> 削除済み" in out and "Q-002: 採番済み -> 欠番" in out


def test_ledger_lifecycle_and_digest(sample):
    cid = sample.py("ledger.py", "--by", "test-designer", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "再開",
                    "--layer", "e2e", "--command", "python -c \"raise SystemExit(0)\"", "--canary", check=True).stdout.strip()
    assert cid == "E2E-001"
    led = json.loads(sample.read("tests/system/ledger.json"))
    assert led["cases"][0]["status"] == "not_run" and led["ac_digests"]["AC-001"].startswith("sha256:")
    assert sample.py("rdcheck.py", "check", "--base", "none", "--strict-ledger").returncode == 0

    assert sample.py("ledger.py", "update", "E2E-001", "--command", "x").returncode != 0  # reason required
    assert sample.py("ledger.py", "set", "E2E-001", "pass").returncode != 0  # pass only from a run

    out = sample.py("ledger.py", "run", "--cases", "E2E-001", check=True).stdout
    assert "E2E-001 FR-001 pass" in out
    led = json.loads(sample.read("tests/system/ledger.json"))
    assert led["cases"][0]["status"] == "pass" and led["cases"][0]["evidence"].startswith("work/")

    rd = sample.read("docs/requirements-definition.md").replace("入力済みの値が失われない", "入力済みの値と添付が失われない")
    sample.write("docs/requirements-definition.md", rd)
    proc = sample.py("rdcheck.py", "check", "--base", "none", "--strict-ledger")
    assert proc.returncode == 1 and "CHK-11" in proc.stdout
    assert sample.py("ledger.py", "digests").returncode == 1
    sample.py("ledger.py", "digests", "--update", check=True)
    assert sample.py("rdcheck.py", "check", "--base", "none", "--strict-ledger").returncode == 0


def test_ledger_run_no_record_and_failure(sample):
    sample.py("ledger.py", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "t", "--layer", "api",
              "--command", "python -c \"raise SystemExit(3)\"", check=True)
    proc = sample.py("ledger.py", "run", "--cases", "IT-001", "--no-record")
    assert proc.returncode == 1 and "IT-001 FR-001 fail" in proc.stdout
    led = json.loads(sample.read("tests/system/ledger.json"))
    assert led["cases"][0]["status"] == "not_run"


def test_select_tests(sample):
    sample.write("tests/unit/test_resume.py", "# FR-001 AC-001\n")
    sample.commit("unit test")
    sample.write("src/resume.py", "# FR-001\n")
    out = sample.py("select-tests.py", "--base", "HEAD", check=True).stdout
    assert "REQ   AC-001 AC-002 FR-001" in out and "TEST  tests/unit/test_resume.py" in out


def test_summarize():
    import subprocess
    import sys
    from conftest import SOURCE
    log = "\n".join(["ok"] * 200 + ["FAILED tests/test_x.py::test_a - AssertionError: 1 != 2", "==== 1 failed, 10 passed in 1.2s ===="])
    out = subprocess.run([sys.executable, str(SOURCE / "scripts" / "summarize.py"), "-"], input=log, capture_output=True,
                         text=True, encoding="utf-8").stdout
    assert "1 failed, 10 passed" in out and "AssertionError" in out and len(out.splitlines()) <= 15
