"""Integration tests of `rdfix.py --full` / `--full --apply` (FR-1046, NFR-REL-002, NFR-REL-003).

Every test works on a copy of one disposable repository (toolkit installed + SAMPLE data layer, verified clean).
Faults are injected from the test (monkeypatch in-process, or a child process that patches the standard library);
the implementation has no test hooks.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from conftest import SAMPLE_CATALOG, SAMPLE_ID_REGISTRY, SAMPLE_RD, SOURCE, Repo, git, init_git, run
from test_gate import denied, shell, start

CHECK = ("--full",)
APPLY = ("--full", "--apply")
CATALOG = "docs/catalog.md"
REGISTRY = "docs/id-registry.md"
LEDGER = "tests/system/ledger.json"
HISTORY = "docs/run-history.md"
RD = "docs/requirements-definition.md"
INTEGRATIONS = "docs/integrations.md"
ROLES = ("rd-author", "test-designer", "implementer", "conductor")


# ------------------------------------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def template(tmp_path_factory):
    path = tmp_path_factory.mktemp("rdfixfull") / "base repo"
    init_git(path)
    (path / "README.md").write_text("# app\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(path), "--skip-verify"], path, check=True)
    r = Repo(path)
    r.commit("install toolkit")
    r.write(RD, SAMPLE_RD)
    r.write(CATALOG, SAMPLE_CATALOG)
    r.write(REGISTRY, SAMPLE_ID_REGISTRY)
    r.write(LEDGER, json.dumps({"version": 1, "ac_digests": {}, "cases": []}, ensure_ascii=False, indent=2) + "\n")
    for rel in ("tests/system/e2e/test_studio_system.py", "tests/system/e2e/test_judge_capabilities.py"):
        if (path / rel).exists():
            (path / rel).unlink()
    if (path / "EABK-Studio").exists():
        shutil.rmtree(path / "EABK-Studio")
    r.py("next-id.py", "--sync", "--adopt", check=True)
    r.py("ledger.py", "--by", "test-designer", "add", "--req", "FR-001", "--ac", "AC-001", "--title", "t",
         "--layer", "e2e", "--command", "python -c pass", check=True)
    r.py("ledger.py", "--by", "test-designer", "digests", "--update", check=True)
    r.commit("sample data layer")
    v = r.py("verify.py", "--docs-only")
    assert v.returncode == 0, f"前提: 合成したデータ層が verify --docs-only に合格しない\n{v.stdout}"
    return path


def fresh(template, tmp_path, name="repo with spaces") -> Repo:
    dst = tmp_path / name
    shutil.copytree(template, dst)
    return Repo(dst)


@pytest.fixture
def repo(template, tmp_path):
    return fresh(template, tmp_path)


def sub_line(r: Repo, rel: str, pattern: str, repl: str) -> None:
    text = r.read(rel)
    new, n = re.subn(pattern, repl, text, count=1, flags=re.M)
    assert n == 1, (rel, pattern)
    r.write(rel, new)


def plant_automatic(r: Repo) -> None:
    sub_line(r, CATALOG, r"^(\| FR-001 \| 入力の中断と再開 \| )承認済み( \|)", r"\1保留\2")
    sub_line(r, REGISTRY, r"^(\| FR-001 \|[^|\n]*\| )使用中( \|)", r"\1廃止\2")
    led = json.loads(r.read(LEDGER))
    del led["cases"][0]["evidence"]
    r.write(LEDGER, json.dumps(led, ensure_ascii=False, indent=2) + "\n")


def plant_manual(r: Repo) -> None:
    row = "| 202610010000 | 2026-10-01 00:00 | 2026-10-01 01:00 | abc1234 | 完了 | FR-001 | なし | 100% | 60 分 | 100% | 0 | 0 | FR-001 |\n"
    other = row.replace("abc1234 | 完了", "def5678 | 中断")
    r.write(HISTORY, r.read(HISTORY).rstrip("\n") + "\n" + row + other)


def repaired(r: Repo) -> dict:
    led = json.loads(r.read(LEDGER))
    return {
        "catalog": "| FR-001 | 入力の中断と再開 | 承認済み |" in r.read(CATALOG),
        "registry": bool(re.search(r"^\| FR-001 \|[^|\n]*\| 使用中 \|", r.read(REGISTRY), re.M)),
        "ledger": "evidence" in led["cases"][0],
    }


def planted(template, tmp_path, manual=False, name="repo with spaces") -> Repo:
    r = fresh(template, tmp_path, name)
    plant_automatic(r)
    if manual:
        plant_manual(r)
    r.commit("plant")
    return r


def data_files(r: Repo):
    root = r.path
    out = [p for p in (root / "docs").rglob("*") if p.is_file()]
    out += [root / LEDGER, root / ".gitignore"]
    return sorted(out)


def snapshot(r: Repo, mtime=True):
    return {p.relative_to(r.path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns if mtime else 0) for p in data_files(r)}


def temp_files(r: Repo):
    return [p for p in r.path.rglob("*") if p.is_file() and ".git" not in p.relative_to(r.path).parts
            and (p.name.startswith(".rdfix-tmp-") or p.name.startswith(".tmp-"))]


def out(proc) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


def lines(text: str, kind: str):
    return [l for l in text.splitlines() if l.startswith(kind + " ")]


def no_traceback(text: str) -> bool:
    return "Traceback (most recent call last)" not in text


def rdfix_inproc():
    """The rdfix module of this checkout (the same code that install.py copies), for in-process fault injection."""
    sys.path.insert(0, str(SOURCE / "scripts"))
    import rdfix  # noqa: E402
    return rdfix


def main_inproc(r: Repo, capsys, *args):
    rdfix = rdfix_inproc()
    rc = rdfix.main([*args, "--root", str(r.path)])
    cap = capsys.readouterr()
    return rc, cap.out + cap.err


def child(code: str, cwd: Path, **kw):
    env = dict(os.environ, PYTHONUTF8="1", EABK_ALLOW_PRIMARY="1")
    return subprocess.Popen([sys.executable, "-c", code], cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", env=env, **kw)


HOLDER = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, {scripts!r})
    import rdfix
    from pathlib import Path
    root = Path({root!r})
    lk = rdfix.RepairLock(rdfix.lock_path(root, rdfix.h.load_config(root)))
    ok, _ = lk.acquire(0, lambda m: None)
    print("locked" if ok else "busy", flush=True)
    time.sleep({hold})
    {after}
    lk.release()
""")


def hold_lock(r: Repo, hold: float, after: str = "pass"):
    p = child(HOLDER.format(scripts=str(r.path / "scripts"), root=str(r.path), hold=hold, after=after), r.path)
    assert p.stdout.readline().strip() == "locked", p.stderr.read()
    return p


# ------------------------------------------------------------------------------------------- FR-1046

# FR-1046 AC-242: every MANUAL line has CHK-ID, file:line, the role in charge and the next action; --json has fields
def test_ac242_manual_items_have_chk_location_role_and_next_action(template, tmp_path):
    r = planted(template, tmp_path, manual=True)
    led = json.loads(r.read(LEDGER))
    led["ac_digests"]["AC-001"] = "sha256:stale"  # MANUAL CHK-11 (test-designer), location without a line in rdfix
    r.write(LEDGER, json.dumps(led, ensure_ascii=False, indent=2) + "\n")
    r.write(RD, r.read(RD).replace("- 受入基準 AC-002:", "- 受入基準 AC-077:"))  # hand-numbered ID: MANUAL CHK-01
    r.commit("manual items")
    proc = r.py("rdfix.py", *CHECK)
    text = out(proc)
    assert no_traceback(text) and proc.returncode == 1, text
    man = lines(text, "MANUAL")
    assert len(man) >= 3, text
    for l in man:
        assert re.match(r"^MANUAL CHK-\d{2} \S+:\d+ ", l), l
        assert any(f"担当: {role}" in l for role in ROLES), l
        assert "次の行動: " in l and l.split("次の行動: ", 1)[1].strip(), l
    assert any(l.startswith("MANUAL CHK-23 docs/run-history.md:") and "conductor" in l for l in man), text
    assert any(l.startswith("MANUAL CHK-11 tests/system/ledger.json:") and "test-designer" in l for l in man), text
    assert any(l.startswith("MANUAL CHK-01 ") and "AC-077" in l and "rd-author" in l for l in man), text

    js = json.loads(r.py("rdfix.py", *CHECK, "--json").stdout)
    assert js["exit"] == 1 and js["mode"] == "check"
    assert len(js["manual"]) == len(man)
    for item in js["manual"]:
        assert re.fullmatch(r"CHK-\d{2}", item["chk"]) and item["file"] and item["line"] >= 1, item
        assert item["loc"] == f"{item['file']}:{item['line']}"
        assert item["owner"] in ROLES and item["action"], item
    # the located line really holds the item
    ledger_item = next(i for i in js["manual"] if i["chk"] == "CHK-11")
    assert "AC-001" in r.read(LEDGER).splitlines()[ledger_item["line"] - 1]
    id_item = next(i for i in js["manual"] if i["chk"] == "CHK-01")
    assert "AC-077" in r.read(id_item["file"]).splitlines()[id_item["line"] - 1]


# FR-1046 AC-243: verify --docs-only names both commands; the same operations give the same output and exit code
# in a path with spaces and in a plain path (path separators aside)
def test_ac243_verify_hint_and_identical_results_regardless_of_path(template, tmp_path):
    a = planted(template, tmp_path, manual=True, name="path with spaces")
    b = planted(template, tmp_path, manual=True, name="plainpath")
    v = a.py("verify.py", "--docs-only")
    assert v.returncode == 1
    assert "python scripts/rdfix.py --full`" in v.stdout and "python scripts/rdfix.py --full --apply`" in v.stdout, v.stdout

    def norm(p):
        return out(p).replace("\\", "/")
    for args in (CHECK, CHECK + ("--json",), APPLY, APPLY):
        pa, pb = a.py("rdfix.py", *args), b.py("rdfix.py", *args)
        assert pa.returncode == pb.returncode, (args, norm(pa), norm(pb))
        assert norm(pa) == norm(pb), args
        assert no_traceback(norm(pa))
    assert snapshot(a, mtime=False) == snapshot(b, mtime=False)


# NFR-COMPAT-004 (FR-1046 の制限): the new apply command is limited by hook G-2 / G-5 like --apply
def test_full_apply_is_limited_by_gates_like_apply(template, tmp_path):
    r = fresh(template, tmp_path)
    git(r.path, "switch", "-q", "-c", "work/r/I-01")
    plant_automatic(r)
    before = snapshot(r)
    proc = r.py("rdfix.py", *APPLY)
    assert proc.returncode == 2 and "work/<run-id>/<item>" in out(proc)
    assert snapshot(r) == before
    git(r.path, "checkout", "-q", "--", ".")
    git(r.path, "switch", "-q", "main")
    start(r)
    assert shell(r, "python scripts/rdfix.py --full") == {}
    r.gate("subagent-start", {"agentName": "implementer"})
    assert denied(shell(r, "python scripts/rdfix.py --full --apply"), "G-2")
    r.gate("subagent-stop", {"agentName": "implementer", "agentId": "i1", "response": "RESULT: done"})
    r.gate("subagent-start", {"agentName": "rd-author"})
    assert denied(shell(r, "python scripts/rdfix.py --full --apply"), "G-5")


# ------------------------------------------------------------------------------------------- NFR-REL-002

# NFR-REL-002 AC-244: a repair that rewrites the requirements definition / integration catalog is detected and undone
@pytest.mark.parametrize("victim", [RD, INTEGRATIONS])
def test_ac244_repair_touching_protected_files_is_undone(template, tmp_path, capsys, monkeypatch, victim):
    r = planted(template, tmp_path)
    if not (r.path / victim).exists():
        r.write(victim, "# 外部連携カタログ\n")
        r.commit("integrations")
    before = snapshot(r)
    rdfix = rdfix_inproc()
    real_apply = rdfix.Fixer.apply

    def tampering_apply(self):
        real_apply(self)
        p = self.root / victim
        p.write_bytes(p.read_bytes() + "\n改ざん\n".encode("utf-8"))  # injected fault: not through the writers
    monkeypatch.setattr(rdfix.Fixer, "apply", tampering_apply)
    rc, text = main_inproc(r, capsys, *APPLY)
    assert rc == 2, text
    assert no_traceback(text)
    assert victim in text and "取り消し" in text, text
    assert {k: v[0] for k, v in snapshot(r).items()} == {k: v[0] for k, v in before.items()}
    assert not temp_files(r)


# NFR-REL-002 AC-245: a write that fails in the middle of several files restores every file, no temp file is left
def test_ac245_write_failure_midway_restores_everything(template, tmp_path, capsys, monkeypatch):
    r = planted(template, tmp_path)
    before = snapshot(r)
    real_replace = os.replace
    seen = []

    def failing_replace(src, dst):
        seen.append(Path(dst).name)
        if Path(dst).name == "ledger.json" and Path(src).name.startswith(".rdfix-tmp-"):
            raise PermissionError(13, "injected write failure", str(dst))
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", failing_replace)
    rc, text = main_inproc(r, capsys, *APPLY)
    monkeypatch.setattr(os, "replace", real_replace)
    assert rc == 2, text
    assert no_traceback(text) and "取り消し" in text, text
    assert "id-registry.md" in seen and "catalog.md" in seen, f"他のファイルを書いた後で失敗させていない: {seen}"
    after = snapshot(r)
    assert {k: v[0] for k, v in after.items()} == {k: v[0] for k, v in before.items()}
    assert not temp_files(r), temp_files(r)


# NFR-REL-002 AC-245: a repair killed while writing leaves every file complete (before or after), and the next
# apply cleans the temp file, takes over the lock of the dead process and converges
def test_ac245_killed_while_writing_leaves_complete_files(template, tmp_path):
    r = planted(template, tmp_path, name="killed")
    ref = planted(template, tmp_path, name="reference")
    assert ref.py("rdfix.py", *APPLY).returncode == 0
    before = snapshot(r, mtime=False)
    after = snapshot(ref, mtime=False)
    code = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(r.path / 'scripts')!r})
        import rdfix
        real = os.replace
        def replace(src, dst):
            if str(dst).endswith("catalog.md"):
                os._exit(9)   # killed between writing the temp file and replacing the target
            return real(src, dst)
        os.replace = replace
        sys.exit(rdfix.main(["--full", "--apply", "--root", {str(r.path)!r}]))
    """)
    p = child(code, r.path)
    p.communicate(timeout=120)
    assert p.returncode == 9
    now = snapshot(r, mtime=False)
    for rel in before:
        assert now[rel][0] in (before[rel][0], after[rel][0]), f"{rel} が途中までの内容になった"
    assert set(now) - set(before) == {p.relative_to(r.path).as_posix() for p in temp_files(r)}
    assert now[REGISTRY][0] == after[REGISTRY][0] and now[CATALOG][0] == before[CATALOG][0]
    assert temp_files(r), "強制終了の時点で一時ファイルがない（故障を注入できていない）"
    proc = r.py("rdfix.py", *APPLY)
    assert proc.returncode == 0, out(proc)
    assert "引き継ぎ" in out(proc), out(proc)
    assert not temp_files(r)
    assert all(repaired(r).values())
    assert snapshot(r, mtime=False) == after


# NFR-REL-002 AC-246: an error that the repair itself introduced cancels everything
def test_ac246_new_error_after_repair_is_undone(template, tmp_path, capsys, monkeypatch):
    r = planted(template, tmp_path)
    before = snapshot(r)
    rdfix = rdfix_inproc()
    real_apply = rdfix.Fixer.apply

    def apply_with_bad_row(self):
        real_apply(self)
        p = self.root / CATALOG
        rdfix.h.write_text_atomic(p, rdfix.h.read_text(p) + "| FR-404 | 幻の要求 | 承認済み | src/ghost.py | 未実装 | なし |\n")
    monkeypatch.setattr(rdfix.Fixer, "apply", apply_with_bad_row)
    rc, text = main_inproc(r, capsys, *APPLY)
    assert rc == 2, text
    assert no_traceback(text) and "取り消し" in text, text
    new = lines(text, "NEW-ERROR")
    assert new and all(re.match(r"^NEW-ERROR CHK-\d{2} docs/catalog\.md:\d+ ", l) for l in new), text
    assert any("FR-404" in l for l in new), text
    assert {k: v[0] for k, v in snapshot(r).items()} == {k: v[0] for k, v in before.items()}
    assert not temp_files(r)


# NFR-REL-002 AC-247: an unexpected internal error shows a summary (no traceback), undoes everything, exit 2
def test_ac247_internal_error_is_summarised_and_undone(template, tmp_path, capsys, monkeypatch):
    r = planted(template, tmp_path)
    before = snapshot(r)
    rdfix = rdfix_inproc()
    ledger = rdfix.h.load_script("ledger")
    real_repair = ledger.repair

    def broken_repair(root, cfg, doc, apply, by="rdfix"):
        if apply:
            raise RuntimeError("injected internal error")
        return real_repair(root, cfg, doc, apply, by)
    monkeypatch.setattr(ledger, "repair", broken_repair)
    rc, text = main_inproc(r, capsys, *APPLY)
    assert rc == 2, text
    assert no_traceback(text), text
    assert "RuntimeError" in text and "injected internal error" in text and "取り消し" in text, text
    assert {k: v[0] for k, v in snapshot(r).items()} == {k: v[0] for k, v in before.items()}
    assert not temp_files(r)


# ------------------------------------------------------------------------------------------- NFR-REL-003

# NFR-REL-003 AC-248: the second apply changes nothing (content and mtime) and gives the same verdict
@pytest.mark.parametrize("manual", [False, True])
def test_ac248_second_apply_is_a_no_op(template, tmp_path, manual):
    r = planted(template, tmp_path, manual=manual)
    first = r.py("rdfix.py", *APPLY)
    assert first.returncode == (1 if manual else 0), out(first)
    snap = snapshot(r)
    time.sleep(0.05)
    second = r.py("rdfix.py", *APPLY)
    assert second.returncode == first.returncode, out(second)
    assert not lines(out(second), "FIX"), out(second)
    assert "fix=0" in out(second)
    assert snapshot(r) == snap, "2 回目の適用がデータ層のファイル（内容または更新時刻）を変えた"
    assert lines(out(second), "MANUAL") == lines(out(first), "MANUAL")


# NFR-REL-003 AC-249: a repair that makes another repair necessary is repeated until it converges
def test_ac249_chained_repairs_converge(template, tmp_path, capsys, monkeypatch):
    r = planted(template, tmp_path)
    rdfix = rdfix_inproc()
    real_plan = rdfix.Fixer.plan
    calls = []

    def staged_plan(self):
        calls.append(1)
        if len(calls) == 1:  # the first round only sees the registry; catalog and ledger need the next round
            self.only = {"registry"}
        return real_plan(self)
    monkeypatch.setattr(rdfix.Fixer, "plan", staged_plan)
    rc, text = main_inproc(r, capsys, *APPLY)
    assert rc == 0, text
    assert "rounds=2" in text, text
    assert all(repaired(r).values())
    assert r.py("verify.py", "--docs-only").returncode == 0


# NFR-REL-003 AC-249: not converged within PARAM-026 rounds -> stop, show the items, exit 1, keep the repairs
def test_ac249_not_converged_stops_after_param_rounds_and_keeps_repairs(template, tmp_path, capsys, monkeypatch):
    r = planted(template, tmp_path)
    rdfix = rdfix_inproc()
    real_plan = rdfix.Fixer.plan

    def endless_plan(self):
        acts = real_plan(self)
        self.act("FIX", "CHK-07", CATALOG, "いつまでも残る修復", "", "catalog")
        p = self.root / CATALOG
        self.writers.append(lambda: rdfix.h.write_text_atomic(p, rdfix.h.read_text(p) + "<!-- round -->\n"))
        return self.actions
    monkeypatch.setattr(rdfix.Fixer, "plan", endless_plan)
    rc, text = main_inproc(r, capsys, *APPLY)
    assert rc == 1, text
    assert f"rounds={rdfix.MAX_ROUNDS}" in text and "result=not-converged" in text, text
    assert any("いつまでも残る修復" in l for l in lines(text, "UNCONVERGED")), text
    assert r.read(CATALOG).count("<!-- round -->") == rdfix.MAX_ROUNDS == 3
    assert all(repaired(r).values()), "収束しなかったときも、それまでの修復は残す"


# NFR-REL-003 AC-250: two applies started together - one writes, the other re-checks the result and has nothing to do
def test_ac250_two_concurrent_applies_do_not_mix(template, tmp_path):
    r = planted(template, tmp_path)
    env = dict(os.environ, PYTHONUTF8="1", EABK_ALLOW_PRIMARY="1")
    cmd = [sys.executable, str(r.path / "scripts" / "rdfix.py"), *APPLY]
    ps = [subprocess.Popen(cmd, cwd=str(r.path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                           encoding="utf-8", errors="replace", env=env) for _ in range(2)]
    results = [(p.communicate(timeout=120), p.returncode) for p in ps]
    texts = [o + e for (o, e), _ in results]
    assert [rc for _, rc in results] == [0, 0], texts
    assert sorted(bool(lines(t, "FIX")) for t in texts) == [False, True], texts
    assert all(repaired(r).values())
    assert not temp_files(r)


# NFR-REL-003 AC-250: a later apply waits, then checks the state the earlier one left
def test_ac250_waiting_apply_rechecks_the_latest_state(template, tmp_path):
    r = planted(template, tmp_path)
    fix_catalog = (f"p = root / {CATALOG!r}; "
                   "p.write_text(p.read_text(encoding='utf-8').replace('| 保留 |', '| 承認済み |'), encoding='utf-8', newline='\\n')")
    holder = hold_lock(r, 2, after=fix_catalog)
    t0 = time.monotonic()
    proc = r.py("rdfix.py", *APPLY)
    waited = time.monotonic() - t0
    holder.communicate(timeout=60)
    text = out(proc)
    assert proc.returncode == 0, text
    assert waited >= 1.5, f"排他を待っていない（{waited:.2f} 秒）"
    assert "待ちます" in text
    fixes = lines(text, "FIX")
    assert not any(CATALOG in l for l in fixes), f"先の修復が直した後の状態から検査していない\n{text}"
    assert any(REGISTRY in l for l in fixes) and any(LEDGER in l for l in fixes), text
    assert all(repaired(r).values())


# NFR-REL-003 AC-250: past PARAM-027 (here --lock-wait) the apply writes nothing and exits 2; the check never waits
def test_ac250_lock_timeout_and_check_does_not_wait(template, tmp_path):
    r = planted(template, tmp_path)
    before = snapshot(r)
    holder = hold_lock(r, 15)
    try:
        t0 = time.monotonic()
        chk = r.py("rdfix.py", *CHECK)
        t_check = time.monotonic() - t0
        assert chk.returncode == 1 and lines(out(chk), "FIX"), out(chk)
        assert t_check < 10, f"確認だけのコマンドが排他を待った（{t_check:.1f} 秒）"
        t0 = time.monotonic()
        proc = r.py("rdfix.py", *APPLY, "--lock-wait", "1")
        t_apply = time.monotonic() - t0
    finally:
        holder.kill()
        holder.communicate()
    text = out(proc)
    assert proc.returncode == 2, text
    assert no_traceback(text) and "書き込まずに終了" in text, text
    assert 1 <= t_apply < 12, t_apply
    assert snapshot(r) == before


# NFR-REL-003 AC-250: a lock left by a process that no longer exists is taken over at once
def test_ac250_lock_of_a_dead_process_is_taken_over(template, tmp_path):
    r = planted(template, tmp_path)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock = r.path / "work" / ".ebak" / "rdfix.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": dead.pid, "host": __import__("socket").gethostname(), "started": "2026-10-16T00:00:00+09:00"}),
                    encoding="utf-8")
    t0 = time.monotonic()
    proc = r.py("rdfix.py", *APPLY)
    assert proc.returncode == 0, out(proc)
    assert time.monotonic() - t0 < 20
    assert f"PID {dead.pid}" in out(proc) and "引き継ぎ" in out(proc) and "存在しません" in out(proc), out(proc)
    assert all(repaired(r).values())
    assert lock.read_text(encoding="utf-8").strip() == "", "正常終了で排他の記録が消えていない"
