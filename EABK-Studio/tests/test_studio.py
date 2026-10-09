"""FR-002 AC-002, FR-003 AC-003, FR-004 AC-004, FR-005 AC-005, FR-008 AC-008."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
from studio import model

def test_model_has_requirement_views():
    data=model(Path(__file__).parents[2])
    assert {"FR-002","FR-003","FR-004","FR-005","FR-008"} <= {x["id"] for x in data["requirements"]}
