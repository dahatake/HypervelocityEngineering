"""Static integration checks of the data-layer common entry points (no repository is built; fast).
FR-1044 AC-236, FR-1045 AC-238, NFR-COMPAT-004 AC-256, NFR-OPS-007 AC-257.
The behavioural tests of the three entries are in tests/toolkit/test_repair_entrypoints.py.
"""
import importlib.util
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
INSTALL = SOURCE / "tools" / "install.py"
WF = SOURCE / ".github" / "workflows" / "ebak-data-layer.yml"


def _read(rel):
    return (SOURCE / rel).read_text(encoding="utf-8")


# FR-1044 AC-236: the workflow and the installer repair only through `rdfix.py --full --apply`
def test_fr1044_ac236_workflow_and_installer_call_only_the_common_entry():
    runs = re.findall(r"run:\s*(.+)", WF.read_text(encoding="utf-8"))
    assert "python scripts/rdfix.py --full --apply" in runs
    assert not any(re.search(r"rdfix\.py\s+--apply", r) for r in runs)
    src = INSTALL.read_text(encoding="utf-8")
    body = src.split("def run_data_layer")[1].split("def main")[0]
    assert '"--full"' in body and "rdfix.py" in body and "verify.py" not in body
    assert src.count("run_data_layer(") == 2 and "run_verify" not in src


# FR-1045 AC-238: the installer options exist
def test_fr1045_ac238_installer_has_no_repair_and_skip_verify():
    src = INSTALL.read_text(encoding="utf-8")
    assert '"--no-repair"' in src and '"--skip-verify"' in src
    assert "apply = not args.no_repair" in src and "if not args.skip_verify:" in src


# NFR-COMPAT-004 AC-256: the existing rdfix invocations are kept
def test_nfr_compat_004_ac256_existing_options_kept():
    src = _read("scripts/rdfix.py")
    for opt in ('"--apply"', '"--only"', '"--adopt"', '"--json"', '"--full"'):
        assert f"add_argument({opt}" in src
    assert "is_work_branch(root)" in src


# NFR-OPS-007 AC-257: MANAGED, version and user documents
def test_nfr_ops_007_ac257_managed_version_and_documents():
    spec = importlib.util.spec_from_file_location("ebak_install", INSTALL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for rel in ("scripts/rdfix.py", "scripts/ebaklib.py", "scripts/rdcheck.py", "scripts/next-id.py", "scripts/ledger.py",
                ".github/workflows/ebak-data-layer.yml", "tools/install.py"):
        assert rel in mod.MANAGED, rel
    ver = re.search(r'TOOLKIT_VERSION = "(\d+)\.(\d+)\.(\d+)"', _read("scripts/ebaklib.py"))
    assert tuple(map(int, ver.groups())) > (0, 4, 0)
    for d in ("README.md", "CHANGELOG.md", "users-guide/04-customization.md", "users-guide/05-scripts-reference.md",
              "users-guide/06-quality-gates.md", "users-guide/07-troubleshooting.md", ".github/agents/conductor.agent.md"):
        assert "rdfix.py --full --apply" in _read(d), d
    for d in ("README.md", "users-guide/05-scripts-reference.md", "users-guide/06-quality-gates.md"):
        t = _read(d)
        assert "要求定義書" in t and "--no-repair" in t, d
