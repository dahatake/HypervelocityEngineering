"""D14: copilot-instructions に存在しない番号付きの節（§0 など）を参照しない（N4-1）。"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
# `copilot-instructions.md` に番号付きの節は §12 だけがある。それ以外の §N 参照は参照切れ。
_PATTERN = re.compile(r"copilot-instructions(\.md)?`?\s*(の\s*)?§\s?(?!12)\d")
_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".ts", ".json", ".txt"}


def test_no_reference_to_missing_copilot_instructions_section_zero() -> None:
    offenders: list[str] = []
    for base in (_ROOT / ".github", _ROOT / "hve"):
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in _SUFFIXES:
                continue
            if path == Path(__file__).resolve():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if _PATTERN.search(line):
                    offenders.append(f"{path.relative_to(_ROOT).as_posix()}:{number}")
    assert not offenders, "\n".join(offenders)


def test_copilot_instructions_has_no_section_zero() -> None:
    text = (_ROOT / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
    assert not re.search(r"^#+\s*§?0[\s.]", text, re.MULTILINE)
