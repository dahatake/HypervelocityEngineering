import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("integrate_mod_perf", ROOT / "scripts" / "integrate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def trees(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    run(main, "init", "-q")
    run(main, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    commit = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=main, check=True,
                            capture_output=True, text=True).stdout.strip()
    wt = tmp_path / "wt"
    run(main, "worktree", "add", "-q", "--detach", str(wt))
    return main, wt, commit


def write(main, name_commit, env_commit, sidecar="ok"):
    d = main / "work" / "runs" / "r1" / "evidence"
    d.mkdir(parents=True)
    f = d / f"perf-baseline-{name_commit}.json"
    data = json.dumps({"env": {"commit": env_commit}, "samples": {}}).encode()
    f.write_bytes(data)
    if sidecar == "ok":
        (d / (f.name + ".sha256")).write_text(hashlib.sha256(data).hexdigest() + "  " + f.name)
    elif sidecar == "bad":
        (d / (f.name + ".sha256")).write_text("0" * 64)
    return f


def placed(wt):
    return list((wt / "work").glob("**/evidence/perf-baseline-*.json")) if (wt / "work").exists() else []


# NFR-PERF-003 AC-452 (commit と hash が一致 → 配置)
def test_match_places(trees):
    main, wt, c = trees
    write(main, c, c)
    out = load().sync_perf_baseline(main, wt)
    assert len(placed(wt)) == 1 and "配置しました" in "".join(out)


# NFR-PERF-003 AC-452 (hash 不一致 → 配置しない)
def test_hash_mismatch(trees):
    main, wt, c = trees
    write(main, c, c, sidecar="bad")
    out = load().sync_perf_baseline(main, wt)
    assert not placed(wt) and "hash 不一致" in "".join(out)


# NFR-PERF-003 AC-452 (hash 欠落 → 配置しない)
def test_hash_missing(trees):
    main, wt, c = trees
    write(main, c, c, sidecar=None)
    out = load().sync_perf_baseline(main, wt)
    assert not placed(wt) and "hash 欠落" in "".join(out)


# NFR-PERF-003 AC-452 (内容の commit がファイル名と別 → 配置しない)
def test_commit_mismatch(trees):
    main, wt, c = trees
    write(main, c, "deadbeef")
    out = load().sync_perf_baseline(main, wt)
    assert not placed(wt) and "commit 不一致" in "".join(out)


# NFR-PERF-003 AC-452 (リポジトリにない commit → 配置しない)
def test_unknown_commit(trees):
    main, wt, c = trees
    write(main, "deadbeef", "deadbeef")
    out = load().sync_perf_baseline(main, wt)
    assert not placed(wt) and "別 commit" in "".join(out)


# NFR-PERF-003 AC-452 (既にあれば上書きしない)
def test_existing_not_overwritten(trees):
    main, wt, c = trees
    write(main, c, c)
    d = wt / "work" / "runs" / "r2" / "evidence"
    d.mkdir(parents=True)
    (d / f"perf-baseline-{c}.json").write_text("mine")
    assert load().sync_perf_baseline(main, wt) == []
    assert (d / f"perf-baseline-{c}.json").read_text() == "mine"
