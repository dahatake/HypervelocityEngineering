"""Integration tests of the three entry points to the data-layer common entry (`rdfix.py --full [--apply]`):
the GitHub Actions workflow, the installer and the manual command.
FR-1044 (AC-235, AC-236), FR-1045 (AC-237, AC-238, AC-239), NFR-COMPAT-004 (AC-256), NFR-OPS-007 (AC-257).
One disposable repository is built once; each test works on a copy.
"""
import hashlib
import importlib.util
import json
import re
import shutil
import sys

import pytest

from conftest import SAMPLE_CATALOG, SAMPLE_ID_REGISTRY, SAMPLE_RD, SOURCE, Repo, git, init_git, run

RD = "docs/requirements-definition.md"
CATALOG = "docs/catalog.md"
LAYER = ("docs", "tests/system/ledger.json")
INSTALL = SOURCE / "tools" / "install.py"
WF = SOURCE / ".github" / "workflows" / "ebak-data-layer.yml"


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    path = tmp_path_factory.mktemp("entrypoints") / "base repo"
    init_git(path)
    (path / "README.md").write_text("# app\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "init")
    run([sys.executable, str(INSTALL), "--target", str(path), "--skip-verify"], path, check=True)
    r = Repo(path)
    r.commit("install toolkit")
    r.write(RD, SAMPLE_RD)
    r.write(CATALOG, SAMPLE_CATALOG)
    r.write("docs/id-registry.md", SAMPLE_ID_REGISTRY)
    r.write("tests/system/ledger.json", json.dumps({"version": 1, "ac_digests": {}, "cases": []}, indent=2) + "\n")
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
    assert r.py("rdfix.py", "--full", "--apply").returncode == 0  # normalise (e.g. registry states)
    r.commit("normalised")
    assert r.py("verify.py", "--docs-only").returncode == 0 and r.py("rdfix.py", "--full").returncode == 0
    return path


def fresh(template, tmp_path, name="repo with spaces") -> Repo:
    dst = tmp_path / name
    shutil.copytree(template, dst)
    return Repo(dst)


def plant_auto(r: Repo):
    r.write(CATALOG, r.read(CATALOG).replace("承認済み", "承認待ち", 1))  # CHK-07 (automatic)


def plant_manual(r: Repo):
    # two run-history rows with the same run-id and different contents -> manual (merge=union leftovers)
    row = "| 202610010000 | 2026-10-01 00:00 | 2026-10-01 01:00 | abc1234 | 完了 | FR-001 | なし | 100% | 60 分 | 100% | 0 | 0 | FR-001 |\n"
    other = row.replace("abc1234 | 完了", "def5678 | 中断")
    r.write("docs/run-history.md", r.read("docs/run-history.md").rstrip("\n") + "\n" + row + other)


def layer_bytes(r: Repo):
    out = {}
    for base in LAYER:
        p = r.path / base
        files = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file())
        for f in files:
            out[f.relative_to(r.path).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def install(r: Repo, *extra):
    return run([sys.executable, str(INSTALL), "--target", str(r.path), *extra], r.path)


def text(p):
    return (p.stdout or "") + (p.stderr or "")


# FR-1044 AC-236: the workflow and the installer repair only through the common entry
def test_ac236_workflow_and_installer_use_only_the_common_entry():
    wf = WF.read_text(encoding="utf-8")
    runs = re.findall(r"run:\s*(.+)", wf)
    assert "python scripts/rdfix.py --full --apply" in runs
    assert not any(re.search(r"rdfix\.py\s+--apply", r) for r in runs), "共通の入口を通さない rdfix.py --apply が残っている"
    assert not re.search(r"(ledger|next-id)\.py", wf), "ワークフローが独自の修復手順を持つ"
    src = INSTALL.read_text(encoding="utf-8")
    assert '"--full"' in src and "rdfix.py" in src
    assert "verify.py" not in src.split("def run_data_layer")[1].split("def main")[0]
    # exactly one call of the data layer from main (no extra verify after it)
    assert src.count("run_data_layer(") == 2  # definition + the single call
    assert "run_verify" not in src
    # the safety net of FR-1018 stays
    assert "git checkout -- docs/requirements-definition.md" in wf


# FR-1044 AC-236: the pass/fail of the common entry equals verify --docs-only
@pytest.mark.parametrize("plant", [None, "auto", "manual"])
def test_ac236_entry_result_matches_verify_docs_only(template, tmp_path, plant):
    r = fresh(template, tmp_path)
    if plant == "auto":
        plant_auto(r)
    elif plant == "manual":
        plant_manual(r)
    v = r.py("verify.py", "--docs-only").returncode
    f = r.py("rdfix.py", "--full").returncode
    assert (v == 0) == (f == 0)


# FR-1044 AC-235: workflow call, installer and the manual command give the same bytes and report
def test_ac235_three_entries_repair_identically(template, tmp_path):
    results = {}
    for name in ("manual", "workflow", "installer"):
        r = fresh(template, tmp_path, name)
        plant_auto(r)
        plant_manual(r)
        if name == "installer":
            p = install(r)
            assert p.returncode == 0, text(p)
        else:
            p = r.py("rdfix.py", "--full", "--apply")
            assert p.returncode == 1, text(p)
        results[name] = (layer_bytes(r), sorted(set(re.findall(r"(?:FIX|MANUAL) (CHK-\d+) (\S+)", text(p)))))
    assert results["manual"] == results["workflow"] == results["installer"]
    assert any(f == "docs/run-history.md:" or f.startswith("docs/run-history.md") for _, f in results["manual"][1])


# FR-1045 AC-237 / AC-239: repaired, reported, requirements definition untouched, exit 0 even with manual items left
def test_ac237_ac239_install_repairs_reports_and_keeps_exit_code(template, tmp_path):
    r = fresh(template, tmp_path)
    plant_auto(r)
    plant_manual(r)
    rd = (r.path / RD).read_bytes()
    p = install(r)
    t = text(p)
    assert p.returncode == 0, t
    assert "承認待ち" not in r.read(CATALOG).split("FR-001")[1].split("\n")[0]
    assert (r.path / RD).read_bytes() == rd
    assert re.search(r"MANUAL CHK-\d+ docs/run-history.md:\d+", t) and "conductor" in t
    assert re.search(r"合否: 不合格", t)
    assert "python scripts/rdfix.py --full --apply" in t and (r.path / "scripts" / "rdfix.py").exists()


# FR-1045 AC-238: --no-repair writes nothing and shows the plan; --skip-verify neither checks nor repairs
def test_ac238_no_repair_and_skip_verify(template, tmp_path):
    r = fresh(template, tmp_path)
    plant_auto(r)
    before = layer_bytes(r)
    p = install(r, "--no-repair")
    assert p.returncode == 0 and re.search(r"^FIX CHK-07", text(p), re.M), text(p)
    assert layer_bytes(r) == before
    p = install(r, "--skip-verify")
    assert p.returncode == 0 and "CHK-" not in text(p)
    assert layer_bytes(r) == before
    for mode in ("--dry-run", "--check"):
        p = install(r, mode)
        assert "FIX CHK" not in text(p)
        assert layer_bytes(r) == before


# FR-1045 AC-239 / NFR-COMPAT-004 AC-256: a cancelled repair (worker branch -> exit 2) leaves the toolkit and the data layer
def test_ac239_ac256_cancelled_repair_keeps_toolkit_and_exit_code(template, tmp_path):
    r = fresh(template, tmp_path)
    plant_auto(r)
    git(r.path, "checkout", "-q", "-b", "work/run1/item")
    before = layer_bytes(r)
    direct = r.py("rdfix.py", "--full", "--apply")
    assert direct.returncode == 2 and layer_bytes(r) == before
    p = install(r)
    assert p.returncode == 0, text(p)
    assert layer_bytes(r) == before
    assert "rdfix.py --full" in text(p) and (r.path / "scripts" / "rdfix.py").exists()


# NFR-COMPAT-004 AC-256: the existing invocations keep their meaning
def test_ac256_existing_invocations_unchanged(template, tmp_path):
    r = fresh(template, tmp_path)
    assert r.py("rdfix.py").returncode == 0
    plant_auto(r)
    assert r.py("rdfix.py").returncode == 1
    assert r.py("rdfix.py", "--apply").returncode == 0


# NFR-OPS-007 AC-257: distribution, version and user documents
def test_ac257_managed_version_and_documents():
    spec = importlib.util.spec_from_file_location("ebak_install", INSTALL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for rel in ("scripts/rdfix.py", "scripts/ebaklib.py", "scripts/rdcheck.py", "scripts/next-id.py", "scripts/ledger.py",
                ".github/workflows/ebak-data-layer.yml", "tools/install.py"):
        assert rel in mod.MANAGED, rel
    ver = re.search(r'TOOLKIT_VERSION = "(\d+)\.(\d+)\.(\d+)"', (SOURCE / "scripts" / "ebaklib.py").read_text(encoding="utf-8"))
    assert tuple(map(int, ver.groups())) > (0, 4, 0)
    docs = ["README.md", "CHANGELOG.md", "users-guide/04-customization.md", "users-guide/05-scripts-reference.md",
            "users-guide/06-quality-gates.md", "users-guide/07-troubleshooting.md", ".github/agents/conductor.agent.md"]
    for d in docs:
        t = (SOURCE / d).read_text(encoding="utf-8")
        assert "rdfix.py --full --apply" in t, d
        assert "--no-repair" in t or d.endswith("07-troubleshooting.md") or d.endswith("conductor.agent.md") or "--no-repair" in t, d
    for d in ("README.md", "users-guide/05-scripts-reference.md", "users-guide/07-troubleshooting.md"):
        t = (SOURCE / d).read_text(encoding="utf-8")
        assert "exit 2" in t or "2 =" in t, d
        assert "要求定義書" in t
    assert "--no-repair" in (SOURCE / "tools" / "install.py").read_text(encoding="utf-8")
