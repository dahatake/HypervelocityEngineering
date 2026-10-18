import importlib.util
from pathlib import Path

from conftest import git  # noqa: F401
from test_speed import commit_in, start_run, worktree_of

ROOT = Path(__file__).resolve().parents[2]


# FR-1065 AC-361
def test_merge_reaps_released_worktree(sample):
    start_run(sample)
    sample.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-001", check=True)
    wt = worktree_of(sample.py("integrate.py", "prepare", "I-01", check=True).stdout)
    commit_in(wt, "src/app.py", "print('ok')\n")
    proc = sample.py("integrate.py", "merge", "I-01", "--summary", "x")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "INTEGRATE: pass I-01" in proc.stdout
    assert "終了したプロセス" in proc.stdout  # the reap ran


# FR-1065 AC-362
def test_abandon_reaps_released_worktree(sample):
    start_run(sample)
    sample.py("run-state.py", "queue", "add", "--id", "I-01", "--req", "FR-001", check=True)
    sample.py("integrate.py", "prepare", "I-01", check=True)
    proc = sample.py("integrate.py", "abandon", "I-01", "--reason", "t")
    assert proc.returncode == 0
    assert "終了したプロセス" in proc.stdout


# FR-1065 AC-361 AC-362 (a failing reap only warns and never raises)
def test_reap_failure_only_warns():
    spec = importlib.util.spec_from_file_location("integrate_mod", ROOT / "scripts" / "integrate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    lines = mod.reap_under(Path(Path.cwd().anchor))  # filesystem root: reap refuses (exit 2)
    assert any(l.startswith("WARN integrate") for l in lines)
