"""EABK Lite: the check profile applies the same way to every command (FR-1084)."""
import json

from conftest import SOURCE


def check(sample, *extra):
    return sample.py("rdcheck.py", "check", "--base", "none", *extra)


def chks(proc):
    return {l.split()[1] for l in proc.stdout.splitlines() if l.startswith(("ERROR ", "WARN "))}


def set_checks(sample, **kw):
    p = sample.path / "scripts" / "ebak.config.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg.setdefault("checks", {}).update(kw)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def plant_format_and_trace_findings(sample):
    """An ambiguous word (CHK-13, full only) and a hand-numbered requirement ID in code (CHK-19, lite)."""
    sample.write("docs/requirements-definition.md",
                 sample.read("docs/requirements-definition.md").replace("- 要求: ", "- 要求: 適切に ", 1))
    sample.write("src/app.py", "# FR-9999\n")


# FR-1084 AC-465: lite (default) reports only lite_checks; full reports every CHK
def test_lite_profile_reports_only_lite_checks(sample):
    set_checks(sample, profile="lite")
    plant_format_and_trace_findings(sample)
    lite = check(sample)
    assert "profile=lite" in lite.stdout and "CHK-19" in chks(lite), lite.stdout
    assert chks(lite) <= set(json.loads((SOURCE / "scripts/ebak.config.json").read_text(encoding="utf-8"))["checks"]["lite_checks"])
    full = check(sample, "--profile", "full")
    assert "profile=full" in full.stdout and "CHK-13" in chks(full) and "CHK-13" not in chks(lite), full.stdout
    # a warning outside the profile never changes the exit code
    sample.write("src/app.py", "print('ok')\n")
    assert check(sample).returncode == 0


# FR-1084 AC-466: --profile overrides checks.profile and verify passes it through; rdfix --full follows the same
# profile, so its pass/fail equals verify --docs-only (FR-1044 AC-236)
def test_profile_override_and_one_profile_everywhere(sample):
    plant_format_and_trace_findings(sample)
    set_checks(sample, profile="full")
    assert "CHK-13" in chks(check(sample))
    assert "CHK-13" not in chks(check(sample, "--profile", "lite"))
    out = sample.py("verify.py", "--docs-only", "--no-cache", "--show-warnings", "--profile", "lite").stdout
    assert "profile=lite" in out and "CHK-13" not in out, out
    for profile in ("lite", "full"):
        set_checks(sample, profile=profile)
        v = sample.py("verify.py", "--docs-only", "--no-cache").returncode
        f = sample.py("rdfix.py", "--full").returncode
        assert (v == 0) == (f == 0), profile

