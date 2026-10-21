import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import ebaklib as h  # noqa: E402


def load_run_state():
    spec = importlib.util.spec_from_file_location("run_state_mod", SCRIPTS / "run-state.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_effective_max_hours_defaults_and_cap():
    assert h.effective_max_hours({}) == 2.5
    assert h.effective_max_hours({"max_hours": "24"}) == 3.0
    assert h.effective_max_hours({"max_hours": "1.5"}) == 1.5
    assert h.effective_max_hours({"max_hours": "abc"}) == 2.5


def test_cap_is_configurable_for_overnight_runs():
    cfg = {"limits": {"max_hours_default": 6, "max_hours_cap": 8, "reserve_minutes": 45}}
    assert h.effective_max_hours({}, cfg) == 6
    assert h.effective_max_hours({"max_hours": "24"}, cfg) == 8
    assert h.time_limits(cfg)[2] == 0.75


def test_share_dirs_links_when_lock_matches(tmp_path):
    src, wt = tmp_path / "primary", tmp_path / "wt"
    for r in (src, wt):
        r.mkdir()
        (r / "package-lock.json").write_text("{}")
    (src / "node_modules").mkdir()
    (src / "node_modules" / "a.txt").write_text("x")
    cfg = {"worktree_share": {"enabled": True, "dirs": ["node_modules"]}}
    notes = h.share_dirs(src, wt, cfg)
    assert any(n.startswith("SHARED") for n in notes), notes
    assert (wt / "node_modules" / "a.txt").read_text() == "x"
    assert h.unshare_dirs(wt, cfg) == 1
    assert not (wt / "node_modules").exists()
    assert (src / "node_modules" / "a.txt").exists()  # the target survives


def test_share_dirs_skips_when_lock_differs_or_disabled(tmp_path):
    src, wt = tmp_path / "primary", tmp_path / "wt"
    src.mkdir()
    wt.mkdir()
    (src / "package-lock.json").write_text("{}")
    (wt / "package-lock.json").write_text('{"a":1}')
    (src / "node_modules").mkdir()
    cfg = {"worktree_share": {"enabled": True, "dirs": ["node_modules"]}}
    assert h.share_dirs(src, wt, cfg)[0].startswith("NOTE")
    assert not (wt / "node_modules").exists()
    assert h.share_dirs(src, wt, {"worktree_share": {"enabled": False, "dirs": ["node_modules"]}}) == []


def test_credit_estimate(tmp_path):
    rs = load_run_state()
    cfg = {"work": {"dir": "work"}, "credits": {"default_multiplier": 1, "model_multipliers": {"big": 3}}}
    rdir = h.run_dir(tmp_path, cfg, "r1")
    rdir.mkdir(parents=True)
    lines = [{"model": "big"}, {"model": "big"}, {"model": "small"}]
    (rdir / "models.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    out = rs.credit_estimate(tmp_path, cfg, "r1")
    assert out.startswith("推定 7") and "big×2" in out
    assert rs.credit_estimate(tmp_path, cfg, "none") == ""
