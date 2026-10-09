"""FR-006 AC-006, FR-007 AC-007, FR-010 AC-010, FR-011 AC-011, FR-012 AC-012."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "EABK-Studio"))
import studio
def test_model_parses_catalog_and_requirements():
    model=studio._repo_data(ROOT)
    assert any(x["id"]=="FR-006" for x in model["requirements"])
    assert any(x["id"]=="FR-006" for x in model["catalog"])
    assert model["files"]
def test_fingerprint_changes_when_management_data_changes(tmp_path):
    (tmp_path/"docs").mkdir()
    (tmp_path/"docs/requirements-definition.md").write_text("#### FR-1 X\n",encoding="utf-8")
    (tmp_path/"docs/catalog.md").write_text("# Catalog\n",encoding="utf-8")
    before=studio.fingerprint(tmp_path)
    (tmp_path/"docs/catalog.md").write_text("# Catalog\nchanged",encoding="utf-8")
    assert before != studio.fingerprint(tmp_path)
def test_repository_switch_rejects_missing_data():
    try: studio._repo_data(ROOT/"missing")
    except ValueError as e: assert "not found" in str(e)
    else: assert False
