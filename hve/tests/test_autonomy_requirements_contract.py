"""要求定義の、自律実行の追加（不明点の梯子・較正）に関する記述の契約。"""

import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENTS = _REPO_ROOT / "hve-dev" / "requirement-definition.md"


def _requirement_line(req_id: str) -> str:
    prefix = f"- **{req_id}**:"
    lines = [line for line in _REQUIREMENTS.read_text(encoding="utf-8").splitlines() if line.startswith(prefix)]
    assert len(lines) == 1, f"{req_id} の行が 1 件ではない: {len(lines)}"
    return lines[0]


def _assert_contains(text: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    assert not missing, f"記述が無い: {missing}"


def test_requirement_defines_unknown_resolution_ladder_and_gate() -> None:
    line = _requirement_line("FR-QA-09")
    _assert_contains(line, "L0", "L1", "L2", "L3", "L4", "出典", "`assumed`", "1 往復")
    assert re.search(r"3 条件", line)


def test_requirement_defines_default_calibration_log() -> None:
    line = _requirement_line("FR-QA-10")
    _assert_contains(
        line,
        "work/learning/qa-calibration.jsonl",
        "20 件",
        "`security`",
        "`irreversible`",
        "Work IQ の応答本文",
    )
