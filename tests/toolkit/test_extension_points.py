"""FR-1082 (AC-458, AC-460) and FR-1083 (AC-461, AC-462): extension points of the data-layer checks and the
installer's warning about wiring that an update would drop."""
import json
import sys

from conftest import SOURCE, run

FAIL_EXT = '''def project_integration_check(root, cfg):
    return [{"level": "ERROR", "chk": "PRJ-01", "loc": "docs/integrations.md:7", "msg": "連携先が未定義"}]
'''
WARN_EXT = '''def project_warn_check(root, cfg):
    return [("WARN", "PRJ-02", "docs/x.md:1", "注意")]
'''
PASS_EXT = '''def project_pass_check(*args, **kwargs):
    return []
'''


def _register(repo, *entries):
    p = repo.path / "scripts" / "ebak.config.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg.setdefault("extensions", {})["checks"] = list(entries)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _out(proc):
    return proc.stdout + proc.stderr


def _install(repo, *extra):
    return run([sys.executable, str(SOURCE / "tools" / "install.py"), "--target", str(repo.path), "--skip-verify", *extra], repo.path)


# FR-1082 AC-458: config-registered and scripts/ext checks run in rdcheck, same format, failure -> exit code
def test_ac458_rdcheck_calls_registered_extensions_and_reflects_failure(sample):
    base = sample.py("rdcheck.py", "check", "--base", "none")
    assert "EXT " not in _out(base) and base.returncode == 0
    sample.write("scripts/project_fail.py", FAIL_EXT)
    sample.write("scripts/project_warn.py", WARN_EXT)
    _register(sample, {"module": "project_fail", "function": "project_integration_check", "target": "rdcheck"},
              {"module": "project_warn", "function": "project_warn_check"})
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    out = _out(proc)
    assert proc.returncode == 1, out
    assert "ERROR PRJ-01 docs/integrations.md:7 [project_fail.project_integration_check] 連携先が未定義" in out
    assert "WARN PRJ-02 docs/x.md:1" in out
    assert "EXT project_fail.project_integration_check target=rdcheck result=fail" in out
    assert "EXT project_warn.project_warn_check target=rdcheck result=warn" in out
    # the same check registered both ways is called once; a warning alone keeps the exit code 0
    sample.write("scripts/ext/project_warn.py", WARN_EXT)
    _register(sample, {"module": "project_warn", "function": "project_warn_check"})
    proc = sample.py("rdcheck.py", "check", "--base", "none")
    assert proc.returncode == 0, _out(proc)
    assert _out(proc).count("EXT project_warn.project_warn_check") == 1


# FR-1082 AC-458: rdfix --full also calls the extensions (target rdfix / both); a failing one is not a pass
def test_ac458_rdfix_calls_extensions_and_failure_is_reflected(sample):
    sample.write("scripts/ext/project_checks.py", FAIL_EXT)  # no target -> both
    proc = sample.py("rdfix.py", "--full")
    out = _out(proc)
    assert "EXT project_checks.project_integration_check target=rdfix" in out, out
    assert "PRJ-01" in out and proc.returncode == 1, out
    plain = sample.py("rdfix.py")
    assert "PRJ-01" in _out(plain) and plain.returncode == 1


# FR-1082 AC-460: verify prints one line per registered extension
def test_ac460_verify_prints_one_line_per_extension_and_nothing_when_none(sample):
    none = sample.py("verify.py", "--docs-only", "--no-cache")
    assert "EXT " not in _out(none)
    sample.write("scripts/ext/project_pass.py", PASS_EXT)
    sample.write("scripts/project_warn.py", WARN_EXT)
    _register(sample, {"module": "project_warn", "function": "project_warn_check", "target": "rdcheck"})
    proc = sample.py("verify.py", "--docs-only", "--no-cache")
    out = _out(proc)
    lines = [l.strip() for l in out.splitlines() if l.strip().startswith("EXT ")]
    assert len(lines) == 2, out
    assert any("project_pass.project_pass_check" in l and "result=pass" in l for l in lines)
    assert any("project_warn.project_warn_check" in l and "target=rdcheck" in l for l in lines)


# FR-1082 AC-460: registered but not called -> a warning line; unreadable / raising -> failure naming the extension
def test_ac460_not_called_is_warned_and_broken_extensions_fail_with_their_name(sample):
    sample.write("scripts/project_pass.py", PASS_EXT)
    _register(sample, {"module": "project_pass", "function": "project_pass_check", "target": "rdfix"})
    proc = sample.py("verify.py", "--docs-only", "--no-cache")
    assert proc.returncode == 0, _out(proc)
    assert "EXT-WARN project_pass.project_pass_check" in _out(proc)

    sample.write("scripts/ext/project_broken.py", "raise RuntimeError('boom')\n")
    sample.write("scripts/ext/project_raises.py", "def project_raises_check(root, cfg):\n    raise ValueError('bad')\n")
    _register(sample, {"module": "no_such_module", "function": "f"})
    proc = sample.py("verify.py", "--docs-only", "--no-cache")
    out = _out(proc)
    assert proc.returncode != 0, out
    assert "project_broken" in out and "boom" in out
    assert "project_raises.project_raises_check" in out and "ValueError" in out
    assert "no_such_module.f" in out


WIRING = ("import project_extra\n")


def _wire(repo, rel="scripts/rdcheck.py"):
    repo.write("scripts/project_extra.py", "def run(root, cfg):\n    return []\n")
    p = repo.path / rel
    text = p.read_text(encoding="utf-8")
    p.write_text(text.replace("import ebaklib as h", "import ebaklib as h\nimport project_extra\nproject_extra.run(None, None)", 1), encoding="utf-8")


# FR-1083 AC-461: unregistered wiring -> file:line warning with migration advice; overwrite, backup, exit code unchanged
def test_ac461_warns_about_dropped_wiring_without_changing_the_update(sample):
    _wire(sample)
    proc = _install(sample, "--force")
    out = _out(proc)
    assert proc.returncode == 0, out
    assert "WARN-WIRING  scripts/rdcheck.py:" in out and "import project_extra" in out, out
    assert "extensions.checks" in out and "scripts/ext/" in out
    assert "project_extra" not in sample.read("scripts/rdcheck.py")
    assert list((sample.path / "scripts").glob("rdcheck.py.ebak-backup-*"))
    # the exit code is the same as without wiring
    plain = _install(sample, "--force")
    assert plain.returncode == proc.returncode


# FR-1083 AC-462: no wiring, or wiring already registered -> no warning; dry-run / check only display
def test_ac462_no_warning_when_nothing_or_everything_is_registered_and_dry_run_writes_nothing(sample):
    sample.py("rdcheck.py", "check", "--base", "none")
    p = sample.path / "scripts" / "rdcheck.py"
    p.write_text(p.read_text(encoding="utf-8") + "\n# local note\nLOCAL = 1\n", encoding="utf-8")
    proc = _install(sample, "--force")
    assert "WARN-WIRING" not in _out(proc) and proc.returncode == 0

    _wire(sample)
    _register(sample, {"module": "project_extra", "function": "run", "target": "rdcheck"})
    proc = _install(sample, "--force")
    assert "WARN-WIRING" not in _out(proc), _out(proc)

    # dry-run / check: judgement only, no file is changed
    _register(sample)
    _wire(sample)
    for b in (sample.path / "scripts").glob("*.ebak-backup-*"):
        b.unlink()
    before = {f.name: f.read_bytes() for f in (sample.path / "scripts").glob("*") if f.is_file()}
    for flag in ("--dry-run", "--check"):
        proc = _install(sample, "--force", flag)
        assert "WARN-WIRING  scripts/rdcheck.py:" in _out(proc), _out(proc)
        after = {f.name: f.read_bytes() for f in (sample.path / "scripts").glob("*") if f.is_file()}
        assert after == before
    assert not list((sample.path / "scripts").glob("*.ebak-backup-*"))
