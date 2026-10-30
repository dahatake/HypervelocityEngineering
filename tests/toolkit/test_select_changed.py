"""NFR-PERF-003: `ledger.py run --select changed` picks cases from the IDs on the changed lines (AC-450, AC-451)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _ledger():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("ledger_sel_mod", SCRIPTS / "ledger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(p, *a):
    subprocess.run(["git", *a], cwd=p, check=True, capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "req.md").write_text("AC-001 a\nAC-002 b\nAC-003 c\nAC-004 d\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("plain\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "runner.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")


def _data():
    def case(i, ac, st="pass", cmd="python -m pytest tests/system/x.py"):
        return {"id": i, "status": st, "command": cmd, "requirement_ids": [], "ac_ids": [ac]}
    return {"cases": [case(f"IT-{n}", f"AC-00{n}") for n in (1, 2, 3, 4)]}


def _select(tmp_path, data=None):
    mod = _ledger()
    why = {}
    sel = mod.select_cases(tmp_path, {}, data or _data(), "changed", "HEAD", reasons=why)
    return {c["id"] for c in sel}, why


# NFR-PERF-003 / AC-450: only the IDs on changed lines select cases; reasons are reported
def test_ac450_changed_lines_select_only_their_cases(tmp_path):
    _repo(tmp_path)
    (tmp_path / "docs" / "req.md").write_text("AC-001 a changed\nAC-002 b\nAC-003 c\nAC-004 d changed AC-004\n", encoding="utf-8")
    ids, why = _select(tmp_path)
    assert ids == {"IT-1", "IT-4"}
    assert all("変更行の ID" in why[i] for i in ids)
    # legacy (whole-file) selection would have picked everything
    mod = _ledger()
    assert len(mod._select_legacy(tmp_path, {}, _data(), "changed", "HEAD")) == 4


# NFR-PERF-003 / AC-450: an untracked new file counts fully
def test_ac450_untracked_file_ids_are_not_missed(tmp_path):
    _repo(tmp_path)
    (tmp_path / "docs" / "new.md").write_text("see AC-003\n", encoding="utf-8")
    ids, _ = _select(tmp_path)
    assert ids == {"IT-3"}


# NFR-PERF-003 / AC-451: shared code widens to the legacy selection and says so
def test_ac451_shared_code_widens(tmp_path):
    _repo(tmp_path)
    (tmp_path / "docs" / "req.md").write_text("AC-001 a changed\nAC-002 b\nAC-003 c\nAC-004 d\n", encoding="utf-8")
    (tmp_path / "scripts" / "runner.py").write_text("x = 2  # AC-002\n", encoding="utf-8")
    mod = _ledger()
    why = {}
    sel = mod.select_cases(tmp_path, {}, _data(), "changed", "HEAD", reasons=why)
    legacy = mod._select_legacy(tmp_path, {}, _data(), "changed", "HEAD")
    assert {c["id"] for c in legacy} <= {c["id"] for c in sel}
    assert why["IT-3"].startswith("広げた") and "共通コード" in why["IT-3"]
    assert why["IT-1"].startswith("変更行の ID")


# NFR-PERF-003 / AC-451: a changed file without IDs widens; a command-matched file does not
def test_ac451_no_id_in_changed_lines_widens_but_command_file_does_not(tmp_path):
    _repo(tmp_path)
    (tmp_path / "docs" / "req.md").write_text("AC-001 a changed\nAC-002 b\nAC-003 c\nAC-004 d\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("plain edited\n", encoding="utf-8")
    ids, why = _select(tmp_path)
    assert "IT-4" in ids and "変更行に ID がない" in why["IT-4"]
    data = _data()
    data["cases"][1]["command"] = "python notes.txt"
    ids, why = _select(tmp_path, data)
    assert ids == {"IT-1", "IT-2"} and "command" in why["IT-2"]


# NFR-PERF-003 / AC-451: unparsable diff (bad base) widens
def test_ac451_unparsable_diff_widens(tmp_path, monkeypatch):
    _repo(tmp_path)
    (tmp_path / "docs" / "new.md").write_text("AC-003\n", encoding="utf-8")
    mod = _ledger()
    monkeypatch.setattr(mod, "changed_files", lambda root, base: ["docs/new.md"])
    # h (ebaklib) is shared across modules: restore it after the test
    monkeypatch.setattr(mod.h, "git", lambda args, root: (1, "") if args and args[0] == "diff" else (0, ""))
    why = {}
    sel = mod.select_cases(tmp_path, {}, _data(), "changed", "nope", reasons=why)
    legacy = {c["id"] for c in mod._select_legacy(tmp_path, {}, _data(), "changed", "nope")}
    assert legacy and legacy <= {c["id"] for c in sel}
    assert any(r.startswith("広げた") and "解析できない" in r for r in why.values())
