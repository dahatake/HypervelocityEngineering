"""System Test: ledger.py run が、異なるテストファイルの互換な UI ケースを 1 つの pytest プロセスと
1 回のブラウザー起動にまとめる（NFR-PERF-003 拡張）。

期待値は要求定義書の受入基準だけから決めた。使い捨てリポジトリに、session fixture が「起動回数」を
ファイルへ記録する fake browser を持つ 2 つの UI テストファイルを置き、ledger.py run の
pytest プロセス数・fixture 起動回数・選択・台帳記録・context 分離・オプトアウトを数える。
実 Playwright には依存しない。実装（ledger.py の plan_batches など）は読んでいない。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import run

CONFTEST = '''\
import os
import uuid

import pytest

LOG = os.environ["FAKE_BROWSER_LOG"]


def _log(line):
    with open("%s.%d" % (LOG, os.getpid()), "a", encoding="utf-8") as f:
        f.write(line + "\\n")


def pytest_sessionstart(session):
    _log("proc %d" % os.getpid())


class FakeContext:
    def __init__(self):
        self.id = uuid.uuid4().hex
        self.storage = {}


@pytest.fixture(scope="session")
def browser():
    _log("launch %d" % os.getpid())
    yield object()
    _log("close %d" % os.getpid())


@pytest.fixture
def context(browser, request):
    ctx = FakeContext()
    _log("ctx %s %s" % (request.node.nodeid, ctx.id))
    assert ctx.storage == {}, "context state leaked from another test"
    yield ctx


@pytest.fixture(autouse=True)
def _record_test(request):
    _log("test " + request.node.nodeid)
    yield
'''

TEST_A = '''\
def test_one(context):
    context.storage["cookie"] = "a"


def test_ctx_a(context):
    assert context.storage == {}
    context.storage["cookie"] = "a2"


def test_unselected_a(context):
    pass
'''

TEST_B = '''\
def test_two(context):
    context.storage["cookie"] = "b"


def test_ctx_b(context):
    assert context.storage == {}
    context.storage["cookie"] = "b2"


def test_unselected_b(context):
    pass
'''

TEST_C_FAIL = '''\
def test_broken(context):
    assert False, "intentional failure"
'''

A = "tests/ui_batch/test_a_ui.py"
B = "tests/ui_batch/test_b_ui.py"
C = "tests/ui_batch/test_c_ui.py"
COMMANDS = [
    f"python -m pytest {A} -k test_one -q",
    f"python -m pytest {A}::test_ctx_a -q",
    f"python -m pytest {B}::test_two -q",
    f"python -m pytest {B} -k test_ctx_b -q",
]


def _ledger_run(repo: Path, log: Path, *extra: str):
    env = dict(os.environ, PYTHONUTF8="1", EABK_ALLOW_PRIMARY="1", FAKE_BROWSER_LOG=str(log))
    for old in [log, *log.parent.glob(log.name + ".*")]:
        if old.exists():
            old.unlink()
    res = subprocess.run(
        [sys.executable, "scripts/ledger.py", "--by", "test-designer", "run", "--select", "all", "--jobs", "1", *extra],
        cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=300,
    )
    # each process writes its own per-PID file (no concurrent appends); aggregate here
    parts = sorted(log.parent.glob(log.name + ".*"))
    if parts:
        log.write_text("".join(p.read_text(encoding="utf-8") for p in parts), encoding="utf-8")
        for p in parts:
            p.unlink()
    return res


def _events(log: Path, kind: str):
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return [ln.split(" ", 1)[1] for ln in lines if ln.split(" ", 1)[0] == kind]


def _write_ledger(repo: Path, commands):
    cases = [
        {"id": f"E2E-9{i:02d}", "requirement_ids": ["FR-001"], "ac_ids": ["AC-001"], "title": f"fake ui {i}",
         "layer": "e2e", "command": cmd, "canary": False, "status": "not_run", "history": []}
        for i, cmd in enumerate(commands, 1)
    ]
    ledger = repo / "tests" / "system" / "ledger.json"
    ledger.write_text(json.dumps({"version": 1, "ac_digests": {}, "cases": cases}, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return [c["id"] for c in cases]


def _statuses(repo: Path):
    data = json.loads((repo / "tests" / "system" / "ledger.json").read_text(encoding="utf-8"))
    return {c["id"]: (c["status"], c.get("evidence")) for c in data["cases"]}


def test_ac433_cross_file_ui_cases_share_one_pytest_process_and_one_browser_launch(installed_repo: Path, tmp_path: Path):
    # NFR-PERF-003 AC-433
    repo = installed_repo
    ui = repo / "tests" / "ui_batch"
    ui.mkdir(parents=True)
    (ui / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    (ui / "test_a_ui.py").write_text(TEST_A, encoding="utf-8")
    (ui / "test_b_ui.py").write_text(TEST_B, encoding="utf-8")
    ids = _write_ledger(repo, COMMANDS)
    log = tmp_path / "fake_browser.log"

    # --- まとめて実行（既定）: pytest プロセス 1 回・ブラウザー起動 1 回 ---
    batched = _ledger_run(repo, log)
    assert batched.returncode == 0, batched.stdout + batched.stderr
    assert "ledger run: pass=4 fail=0" in batched.stdout, batched.stdout
    assert len(_events(log, "proc")) == 1, "pytest process must be started once in total\n" + log.read_text()
    assert len(_events(log, "launch")) == 1, "browser must be launched once in total\n" + log.read_text()
    # 選択の維持: 各ケースの選択だけが実行され、選択外のテストは動かない
    ran = sorted(n.split("[", 1)[0] for n in _events(log, "test"))
    assert ran == sorted([f"{A}::test_one", f"{A}::test_ctx_a", f"{B}::test_two", f"{B}::test_ctx_b"]), ran
    # テストごとの context 分離: 各テストが別の context を受け取り、状態が漏れない
    ctxs = [ln.rsplit(" ", 1)[1] for ln in (log.read_text().splitlines()) if ln.startswith("ctx ")]
    assert len(ctxs) == 4 and len(set(ctxs)) == 4, ctxs
    # ケースごとの台帳記録: 4 件すべてが個別に pass と証跡を持つ
    st = _statuses(repo)
    assert all(st[i][0] == "pass" and st[i][1] for i in ids), st
    assert len({st[i][1] for i in ids}) == 4, "evidence (log) must be recorded per case"

    # --- 並列度 2（4 ケース）: 最大 2 プロセスに分割し各プロセスの起動 1 回、従来(--no-batch --jobs 2)より起動が少ない ---
    # AC-433（N>1 は均等分割で 2 プロセス）。実装が jobs>1 でも 1 プロセスのうちは fail でよい。
    _write_ledger(repo, COMMANDS)
    par = _ledger_run(repo, log, "--jobs", "2")
    assert par.returncode == 0 and "ledger run: pass=4 fail=0" in par.stdout, par.stdout + par.stderr
    procs = _events(log, "proc")
    launches = _events(log, "launch")
    assert len(procs) == 2, "jobs=2 must split into 2 pytest processes\n" + log.read_text()
    assert sorted(launches) == sorted(procs) and len(set(launches)) == len(launches), "each process launches the browser once\n" + log.read_text()
    par_ran = sorted(n.split("[", 1)[0] for n in _events(log, "test"))
    assert par_ran == ran, par_ran
    par_ctxs = [ln.rsplit(" ", 1)[1] for ln in log.read_text().splitlines() if ln.startswith("ctx ")]
    assert len(par_ctxs) == 4 and len(set(par_ctxs)) == 4, par_ctxs
    st = _statuses(repo)
    assert all(st[i][0] == "pass" and st[i][1] for i in ids), st
    assert len({st[i][1] for i in ids}) == 4
    par_launch_count = len(launches)
    _write_ledger(repo, COMMANDS)
    legacy2 = _ledger_run(repo, log, "--no-batch", "--jobs", "2")
    assert legacy2.returncode == 0 and "ledger run: pass=4 fail=0" in legacy2.stdout, legacy2.stdout
    assert par_launch_count < len(_events(log, "launch")) == 4

    # --- オプトアウト（--no-batch）: 従来実行（ケースごとに 1 プロセス）で合否が同じ ---
    _write_ledger(repo, COMMANDS)
    legacy = _ledger_run(repo, log, "--no-batch")
    assert legacy.returncode == 0 and "ledger run: pass=4 fail=0" in legacy.stdout, legacy.stdout
    assert "batched_commands=0" in legacy.stdout
    assert len(_events(log, "proc")) == 4 and len(_events(log, "launch")) == 4

    # --- オプトアウト（system_test.batch_pytest: false）も同じ ---
    cfg_path = repo / "scripts" / "ebak.config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    cfg.setdefault("system_test", {})["batch_pytest"] = False
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_ledger(repo, COMMANDS)
    by_cfg = _ledger_run(repo, log)
    assert by_cfg.returncode == 0 and "ledger run: pass=4 fail=0" in by_cfg.stdout, by_cfg.stdout
    assert len(_events(log, "proc")) == 4 and len(_events(log, "launch")) == 4
    cfg["system_test"]["batch_pytest"] = True
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 異常系: 1 件が fail するときも、まとめた実行と従来実行で合否が一致（失敗ケースだけ fail） ---
    (ui / "test_c_ui.py").write_text(TEST_C_FAIL, encoding="utf-8")
    mixed = COMMANDS + [f"python -m pytest {C}::test_broken -q"]
    ids = _write_ledger(repo, mixed)
    on = _ledger_run(repo, log)
    on_status = {k: v[0] for k, v in _statuses(repo).items()}
    _write_ledger(repo, mixed)
    off = _ledger_run(repo, log, "--no-batch")
    off_status = {k: v[0] for k, v in _statuses(repo).items()}
    assert on.returncode == 1 and off.returncode == 1
    assert "pass=4 fail=1" in on.stdout and "pass=4 fail=1" in off.stdout, on.stdout + off.stdout
    assert on_status == off_status and on_status[ids[-1]] == "fail" and all(on_status[i] == "pass" for i in ids[:-1])
