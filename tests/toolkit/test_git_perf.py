import importlib
import subprocess
import sys
import threading
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
h = importlib.import_module("ebaklib")


# NFR-PERF-003 AC-088: git ls-files 2 回が並行に走り、一覧は直列実行時と同一
def test_tracked_files_runs_two_ls_files_concurrently_with_same_result(sample, monkeypatch):
    sample.write("untracked-new.txt", "x\n")
    serial = h.tracked_files(sample.path)
    real = h.git
    lock = threading.Lock()
    state = {"cur": 0, "max": 0, "calls": []}

    def slow_git(args, cwd):
        with lock:
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
            state["calls"].append(list(args))
        time.sleep(0.3)
        try:
            return real(args, cwd)
        finally:
            with lock:
                state["cur"] -= 1

    monkeypatch.setattr(h, "git", slow_git)
    parallel = h.tracked_files(sample.path)
    assert parallel == serial and "untracked-new.txt" in parallel
    assert len(state["calls"]) == 2 and state["max"] == 2
    assert h.tracked_files(sample.path, include_untracked=False) == [
        f for f in serial if f != "untracked-new.txt"]


# NFR-PERF-003 AC-089: rdcheck / rdfix 1 回の実行で同一引数の git ls-files は 1 回以下
def test_rdcheck_and_rdfix_do_not_repeat_ls_files(sample, monkeypatch):
    import rdcheck
    import rdfix
    real = h.git
    for mod, cls, args in ((rdcheck, "Checker", None), (rdfix, None, None)):
        calls = []
        monkeypatch.setattr(h, "git", lambda a, c, calls=calls: (calls.append(tuple(a)), real(a, c))[1])
        script = "rdcheck.py" if mod is rdcheck else "rdfix.py"
        # in-process: 同一 Checker/Fixer で CHK-23 周りを 2 回呼んでも 1 回
        obj = _make(mod, sample.path)
        obj.git_ls_files()
        obj.git_ls_files()
        assert calls.count(("ls-files",)) <= 1, script


def _make(mod, root):
    cls = mod.Checker if mod.__name__ == "rdcheck" else mod.Fixer
    obj = cls.__new__(cls)
    obj.root = root
    return obj


# NFR-COMPAT-002 AC-090: rdcheck の出力・終了コードは tracked_files の並行化に依存しない
def test_rdcheck_output_stable_with_serial_ls_files(sample, monkeypatch):
    first = subprocess.run([sys.executable, "scripts/rdcheck.py"], cwd=sample.path, capture_output=True, text=True)
    second = subprocess.run([sys.executable, "scripts/rdcheck.py"], cwd=sample.path, capture_output=True, text=True)
    assert (first.returncode, first.stdout, first.stderr) == (second.returncode, second.stdout, second.stderr)
