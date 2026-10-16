"""Integration tests of `rdfix.py --full` against broken input, other encodings / line endings, a directory that is not
a git repository, and the number of inspections (NFR-REL-004 AC-251〜253, NFR-PERF-005 AC-254・255).

Every test works on a copy of the disposable repository of test_rdfix_full.py (toolkit installed + SAMPLE data layer).
Faults are injected by the test; the implementation has no test hooks.
"""
import importlib.util
import json
import os
import re
import shutil
import statistics
import stat
import sys
import time
from pathlib import Path

import pytest

from conftest import SOURCE, Repo
from test_rdfix_full import (  # noqa: F401  (template is a fixture)
    APPLY, CATALOG, CHECK, LEDGER, REGISTRY, ROLES, data_files, fresh, lines, no_traceback, out, plant_automatic,
    planted, snapshot, template,
)

BOM = b"\xef\xbb\xbf"
PARAM_025 = 5.0  # PARAM-025（秒）
PARAM_026 = 3    # PARAM-026（回）


def rm_tree(path: Path) -> None:
    def onexc(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=onexc)


def manual_at(text: str, rel: str):
    """The MANUAL lines that name `rel` with a line number: (line number, whole line)."""
    got = []
    for l in lines(text, "MANUAL"):
        m = re.match(r"MANUAL (CHK-\d+) (\S+?):(\d+) ", l)
        if m and m.group(2) == rel:
            got.append((int(m.group(3)), l))
    return got


# ---------------------------------------------------------------------------------- AC-251

def _line_no(r: Repo, rel: str, needle: str) -> int:
    for i, l in enumerate(r.read(rel).split("\n"), 1):
        if needle in l:
            return i
    raise AssertionError((rel, needle))


def inject_marker(r: Repo):
    r.write(CATALOG, r.read(CATALOG) + "\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> branch\n")
    return CATALOG, _line_no(r, CATALOG, "<<<<<<< HEAD")


def inject_json(r: Repo):
    r.write(LEDGER, '{\n  "version": 1,\n  "cases": [ not json\n}\n')
    return LEDGER, 3


def inject_utf8(r: Repo):
    p = r.path / REGISTRY
    raw = p.read_bytes()
    n = raw.count(b"\n") + 2
    p.write_bytes(raw + b"\n\xff\xfe\x80 bad\n")
    return REGISTRY, n


def inject_columns(r: Repo):
    text = r.read(REGISTRY)
    row = next(l for l in text.split("\n") if l.startswith("| FR-001 |"))
    short = row.rstrip(" |").rsplit("|", 1)[0].rstrip() + " |"
    r.write(REGISTRY, text.replace(row, short, 1))
    return REGISTRY, _line_no(r, REGISTRY, short)


BROKEN = {"marker": inject_marker, "json": inject_json, "utf8": inject_utf8, "columns": inject_columns}


# NFR-REL-004 AC-251
@pytest.mark.parametrize("kind", sorted(BROKEN))
@pytest.mark.parametrize("mode", ["check", "apply"])
@pytest.mark.parametrize("with_fix", [False, True])
def test_broken_input_is_manual_and_untouched(template, tmp_path, kind, mode, with_fix):
    r = fresh(template, tmp_path)
    if with_fix:
        plant_automatic(r)
    rel, line = BROKEN[kind](r)
    before = snapshot(r)
    p = r.py("rdfix.py", *(CHECK if mode == "check" else APPLY))
    text = out(p)
    assert no_traceback(text), text
    assert p.returncode == 1, text
    hits = manual_at(text, rel)
    assert any(n == line for n, _ in hits), f"{rel}:{line} の MANUAL がありません\n{text}"
    for _, l in hits:
        assert "CHK-" in l and re.search(r"担当: (%s)" % "|".join(ROLES), l), l
    assert snapshot(r) == before, "壊れた入力のとき、データ層のファイルが書き換えられた"
    j = r.py("rdfix.py", *(CHECK if mode == "check" else APPLY), "--json")
    assert j.returncode == 1 and no_traceback(out(j))
    obj = json.loads(j.stdout)
    assert any(m["file"] == rel and m["line"] == line and m["owner"] in ROLES and m["chk"].startswith("CHK-")
               for m in obj["manual"]), obj["manual"]


# ---------------------------------------------------------------------------------- AC-252

def to_variant(raw: bytes, variant: str) -> bytes:
    body = raw.replace(b"\r\n", b"\n")
    if variant in ("crlf", "bom+crlf"):
        body = body.replace(b"\n", b"\r\n")
    elif variant == "mixed":
        parts = body.split(b"\n")
        body = b"".join(p + (b"\r\n" if i % 2 else b"\n") for i, p in enumerate(parts[:-1])) + parts[-1]
    if variant.startswith("bom"):
        body = BOM + body
    return body


def split_lines(raw: bytes):
    body = raw[len(BOM):] if raw.startswith(BOM) else raw
    out_, start = [], 0
    while True:
        i = body.find(b"\n", start)
        if i < 0:
            if start < len(body):
                out_.append(body[start:])
            return out_
        out_.append(body[start:i + 1])
        start = i + 1


def norm(line: bytes) -> bytes:
    return line.rstrip(b"\r\n")


# NFR-REL-004 AC-252
@pytest.mark.parametrize("variant", ["bom+lf", "crlf", "bom+crlf", "mixed"])
def test_bom_and_line_endings_are_kept(template, tmp_path, variant):
    r = planted(template, tmp_path, name="variant")
    ref = planted(template, tmp_path, name="reference")  # the same repair on plain LF files
    files = (CATALOG, REGISTRY, LEDGER)
    for rel in files:
        p = r.path / rel
        p.write_bytes(to_variant(p.read_bytes(), variant))
    before = {rel: (r.path / rel).read_bytes() for rel in files}
    c = r.py("rdfix.py", *CHECK)
    assert no_traceback(out(c)) and c.returncode == 1 and "result=plan" in c.stdout, out(c)
    assert not manual_at(c.stdout, CATALOG) and not lines(c.stdout, "MANUAL"), "BOM・改行の違いだけで不整合と判定された\n" + out(c)
    a = ref.py("rdfix.py", *APPLY)
    assert a.returncode == 0, out(a)
    a = r.py("rdfix.py", *APPLY)
    assert a.returncode == 0 and no_traceback(out(a)), out(a)
    v = r.py("verify.py", "--docs-only")
    assert v.returncode == 0, out(v)
    for rel in files:
        old, new = before[rel], (r.path / rel).read_bytes()
        assert new != old, f"{rel} が修復されていない"
        assert new.startswith(BOM) == old.startswith(BOM), f"{rel} の BOM の有無が変わった"
        expected = (ref.path / rel).read_bytes()
        assert [norm(l) for l in split_lines(new)] == [norm(l) for l in split_lines(expected)], f"{rel} の修復の内容が LF のときと違う"
        old_lines = split_lines(old)
        old_by_text = {}
        for l in old_lines:
            old_by_text.setdefault(norm(l), set()).add(l)
        changed = 0
        for l in split_lines(new):
            if norm(l) in old_by_text:
                assert l in old_by_text[norm(l)], f"{rel}: 修復しなかった行の改行が変わった: {l!r}"
            else:
                changed += 1
                if variant in ("crlf", "bom+crlf"):
                    assert l.endswith(b"\r\n") or not l.endswith(b"\n") or l.endswith(b"\r\n"), l
                    assert not (l.endswith(b"\n") and not l.endswith(b"\r\n")), f"{rel}: 修復した行の改行が CRLF でない: {l!r}"
        assert changed >= 1
        kept = [l for l in old_lines if norm(l) in {norm(x) for x in split_lines(new)}]
        assert len(kept) >= len(old_lines) - 4, f"{rel}: 修復しなかった行が多く変わっている"


# ---------------------------------------------------------------------------------- AC-253

def strip_git(path: Path) -> None:
    rm_tree(path / ".git")


def fix_lines(text: str):
    return sorted(l for l in text.splitlines() if l.startswith(("FIX ", "MANUAL ", "ERROR ")))


# NFR-REL-004 AC-253
def test_directory_that_is_not_a_git_repository(template, tmp_path):
    g = planted(template, tmp_path, name="with git")
    n = fresh(template, tmp_path, name="without git")
    plant_automatic(n)
    strip_git(n.path)
    assert not (n.path / ".git").exists()
    cg, cn = g.py("rdfix.py", *CHECK), n.py("rdfix.py", *CHECK)
    assert no_traceback(out(cn)) and cn.returncode == cg.returncode == 1, out(cn)
    assert "git の管理下にない" in out(cn) and "省" in out(cn), out(cn)
    assert "git の管理下にない" not in out(cg)
    assert fix_lines(cn.stdout) == fix_lines(cg.stdout)
    ag, an = g.py("rdfix.py", *APPLY), n.py("rdfix.py", *APPLY)
    assert no_traceback(out(an)) and an.returncode == ag.returncode == 0, out(an)
    assert "git の管理下にない" in out(an)
    assert fix_lines(an.stdout) == fix_lines(ag.stdout)
    for rel in (CATALOG, REGISTRY, LEDGER):
        assert (n.path / rel).read_bytes() == (g.path / rel).read_bytes(), rel
    again = n.py("rdfix.py", *CHECK)
    assert again.returncode == 0 and no_traceback(out(again)), out(again)


# NFR-REL-004 AC-253 (a directory that the installer was told to accept with --allow-non-git)
def test_non_git_install_target(tmp_path):
    target = tmp_path / "plain dir"
    target.mkdir()
    (target / "README.md").write_text("# app\n", encoding="utf-8")
    from conftest import run
    run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(target), "--allow-non-git", "--skip-verify"],
        target, check=True)
    assert not (target / ".git").exists()
    p = run([sys.executable, str(target / "scripts" / "rdfix.py"), *CHECK], target)
    text = out(p)
    assert no_traceback(text) and p.returncode in (0, 1), text
    assert "git の管理下にない" in text
    p = run([sys.executable, str(target / "scripts" / "rdfix.py"), *APPLY], target)
    assert no_traceback(out(p)) and p.returncode in (0, 1), out(p)


# ---------------------------------------------------------------------------------- AC-254 / AC-255

def load_rdfix():
    spec = importlib.util.spec_from_file_location("rdfix_under_test", SOURCE / "scripts" / "rdfix.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rdfix_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class Counter:
    def __init__(self, monkeypatch, mod):
        self.inspections = 0
        self.writes = 0
        rd = mod.h.load_script("rdcheck")
        orig_run_all = rd.Checker.run_all
        orig_atomic = mod.atomic_write_bytes
        orig_text = mod.h.write_text_atomic
        me = self

        def run_all(slf, *a, **k):
            me.inspections += 1
            return orig_run_all(slf, *a, **k)

        def atomic(path, data):
            me.writes += 1
            return orig_atomic(path, data)

        def text(path, t):
            me.writes += 1
            return orig_text(path, t)

        monkeypatch.setattr(rd.Checker, "run_all", run_all)
        monkeypatch.setattr(mod, "atomic_write_bytes", atomic)
        monkeypatch.setattr(mod.h, "write_text_atomic", text)


def call(mod, root: Path, *args):
    return mod.main(["--root", str(root), *args, "--json"])


# NFR-PERF-005 AC-254
@pytest.mark.parametrize("args", [CHECK, APPLY])
def test_clean_data_layer_one_inspection_zero_writes(template, tmp_path, monkeypatch, capsys, args):
    r = fresh(template, tmp_path)
    assert r.py("rdfix.py", *APPLY).returncode == 0  # the sample data layer still has one pending state fix
    assert r.py("rdfix.py", *CHECK).returncode == 0
    r.commit("clean")
    before = snapshot(r)
    mod = load_rdfix()
    c = Counter(monkeypatch, mod)
    rc = call(mod, r.path, *args)
    obj = json.loads(capsys.readouterr().out)
    assert rc == 0 and obj["result"] == "pass", (obj["fix"], obj["manual"], obj["errors"])
    assert c.inspections == 1, f"検査が {c.inspections} 回行われた"
    assert c.writes == 0
    assert snapshot(r) == before


# NFR-PERF-005 AC-254（EABK 本体の管理データでの 3 回の中央値）
def test_check_of_this_repository_median_within_limit():
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        p = __import__("subprocess").run([sys.executable, str(SOURCE / "scripts" / "rdfix.py"), "--full", "--root", str(SOURCE)],
                                         capture_output=True, text=True, encoding="utf-8", errors="replace")
        times.append(time.perf_counter() - t0)
        assert no_traceback(out(p)) and p.returncode in (0, 1), out(p)
    assert statistics.median(times) <= PARAM_025, times


# NFR-PERF-005 AC-255
def test_repair_inspection_count_within_rounds_plus_one(template, tmp_path, monkeypatch, capsys):
    r = planted(template, tmp_path)
    mod = load_rdfix()
    c = Counter(monkeypatch, mod)
    rc = call(mod, r.path, *APPLY)
    obj = json.loads(capsys.readouterr().out)
    assert rc == 0 and obj["result"] == "repaired", obj
    assert 1 <= obj["rounds"] <= PARAM_026
    assert c.inspections <= obj["rounds"] + 1 <= PARAM_026 + 1, (c.inspections, obj["rounds"])
    assert c.writes >= 1
