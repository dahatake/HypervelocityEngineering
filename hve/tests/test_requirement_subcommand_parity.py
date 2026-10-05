"""§5.1 のサブコマンド表と `hve/__main__.py` の実装 parity を検査する。

§13 の Step 表に対する `test_requirement_section13_parity.py` と同じ趣旨で、
要求定義書の説明的基線が実装から drift することを機械的に検出する。

drift の実例: §5.1 の説明的基線が `_build_parser()` の登録内容へ追随せず、
実装にだけ複数のサブコマンドが存在した。
`FR-CLI-77` は本文で `login` / `pricing` / `toolsearch` / `ingest-docs` / `gui` を
列挙しており、同一文書内で §5.1 と矛盾していた。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from hve.__main__ import _build_parser

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"

_SECTION = "5.1"
_DELIMITER_RE = re.compile(r"^:?-+:?$")
_NAME_RE = re.compile(r"^`([a-z][a-z0-9-]*)`$")
_LONG_OPTION_RE = re.compile(
    r"--[a-z0-9][a-z0-9-]*(?:\{[a-z0-9]+(?:,[a-z0-9]+)+\})?"
)
_BRACE_SHORTHAND_EXPANSIONS = {
    "--workiq-prompt-{qa,km}": {
        "--workiq-prompt-qa",
        "--workiq-prompt-km",
    },
}


def _section_lines() -> list[str]:
    lines = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines()
    heading = f"### {_SECTION} "
    starts = [i for i, line in enumerate(lines) if line.startswith(heading)]
    assert len(starts) == 1, f"§{_SECTION} の見出しが {len(starts)} 件見つかった"
    start = starts[0]
    for offset, line in enumerate(lines[start + 1 :], start + 1):
        if line.startswith("### "):
            return lines[start:offset]
    return lines[start:]


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _documented_subcommands() -> list[str]:
    """§5.1 の表の第 1 列に現れるサブコマンド名を出現順で返す。"""
    lines = _section_lines()
    headers = [
        i
        for i, line in enumerate(lines)
        if line.startswith("|") and _split_row(line)[:1] == ["サブコマンド"]
    ]
    assert len(headers) == 1, f"§{_SECTION} のサブコマンド表が {len(headers)} 件見つかった"
    start = headers[0]
    assert all(_DELIMITER_RE.fullmatch(cell) for cell in _split_row(lines[start + 1]))

    names: list[str] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        cell = _split_row(line)[0]
        match = _NAME_RE.fullmatch(cell)
        assert match is not None, f"§{_SECTION} の第 1 列が `name` 形式ではない: {cell!r}"
        names.append(match.group(1))
    assert names, f"§{_SECTION} のサブコマンド表に本文行が無い"
    return names


def _implemented_subcommands() -> list[str]:
    """`_build_parser()` が登録したトップレベルサブコマンド名を返す。"""
    for action in _build_parser()._actions:
        name_parser_map = getattr(action, "_name_parser_map", None)
        if name_parser_map is not None:
            return list(name_parser_map)
    raise AssertionError("_build_parser() にサブパーサが見つからない")


def _requirement_block(requirement_id: str) -> str:
    lines = _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines()
    marker = f"- **{requirement_id}**"
    starts = [i for i, line in enumerate(lines) if line.startswith(marker)]
    assert len(starts) == 1, f"{requirement_id} が {len(starts)} 件見つかった"
    start = starts[0]
    end = next(
        (
            i
            for i, line in enumerate(lines[start + 1 :], start + 1)
            if line.startswith("- **FR-")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _documented_orchestrate_long_options() -> set[str]:
    raw_options = set(_LONG_OPTION_RE.findall(_requirement_block("FR-CLI-02")))
    brace_shorthands = {option for option in raw_options if "{" in option}
    unsupported = brace_shorthands - _BRACE_SHORTHAND_EXPANSIONS.keys()
    assert not unsupported, (
        "FR-CLI-02 に未対応の brace shorthand がある: "
        f"{sorted(unsupported)}"
    )

    options = raw_options - brace_shorthands
    for shorthand in brace_shorthands:
        options.update(_BRACE_SHORTHAND_EXPANSIONS[shorthand])
    assert options, "FR-CLI-02 に長形式 option が見つからない"
    return options


def _public_orchestrate_long_options() -> set[str]:
    parser = _build_parser()
    subparsers = parser._subparsers._group_actions[0]
    return {
        option
        for action in subparsers.choices["orchestrate"]._actions
        if action.help != argparse.SUPPRESS
        for option in action.option_strings
        if option.startswith("--")
    }


class TestSubcommandParity:
    def test_documented_set_matches_the_implementation(self) -> None:
        documented = set(_documented_subcommands())
        implemented = set(_implemented_subcommands())
        assert documented == implemented, (
            f"§{_SECTION} にのみ存在: {sorted(documented - implemented)} / "
            f"実装にのみ存在: {sorted(implemented - documented)}"
        )


class TestOrchestrateOptionParity:
    def test_documented_long_options_are_a_subset_of_public_parser_options(self) -> None:
        documented = _documented_orchestrate_long_options()
        public = _public_orchestrate_long_options()
        assert documented <= public, (
            "FR-CLI-02 にのみ存在する非公開または未実装 option: "
            f"{sorted(documented - public)}"
        )
