"""Harness verification guidance scope contract."""

from __future__ import annotations

import re
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SKILL = _ROOT / ".github" / "skills" / "harness-verification-loop" / "SKILL.md"
_REF = _SKILL.parent / "references" / "verification-commands.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing source document: {path}"
    return path.read_text(encoding="utf-8-sig")


def _section(text: str, heading_start: str) -> str:
    lines = text.splitlines()
    visible_lines: list[str] = []
    in_fence = False
    for line in lines:
        if re.match(r"^```", line.strip()):
            visible_lines.append("")
            in_fence = not in_fence
        else:
            visible_lines.append("" if in_fence else line)
    start = next(i for i, line in enumerate(visible_lines) if line.strip().startswith(heading_start))
    heading = visible_lines[start].strip()
    level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for i in range(start + 1, len(visible_lines)):
        if re.match(rf"^#{{1,{level}}}\s", visible_lines[i]):
            end = i
            break
    return "\n".join(lines[start:end])


def _report_template(ref: str) -> str:
    section = _section(ref, "## 検証レポート例")
    match = re.search(r"```markdown\n(?P<report>.*?)\n```", section, re.DOTALL)
    assert match, "missing fenced verification report template"
    return match.group("report")


def _table(section: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] == "言語" or set(cells[0]) <= {"-", ":"}:
            continue
        rows[cells[0]] = cells[1]
    return rows


def _has_target_placeholder(command: str) -> bool:
    targets = ("{ファイルパス}", "{ディレクトリ}", "{テストファイルパス}", "{対象パス}")
    return any(token in command for token in targets)


def test_section_helper_ignores_fenced_markdown_headings() -> None:
    sample = "## §2 検証レポートテンプレート\nbefore\n```markdown\n# fenced h1\n## fenced h2\n```\nafter\n## §3 Next\noutside"

    section = _section(sample, "## §2 検証レポート")

    assert "fenced h1" in section and "after" in section
    assert "## §3 Next" not in section


def test_reference_uses_dedicated_json_and_yaml_rows() -> None:
    rows = _table(_section(_read(_REF), "## 対象コマンドの選び方"))

    assert "JSON/YAML" not in rows
    assert "JSON" in rows
    assert "YAML" in rows
    assert "json.load" in rows["JSON"]
    assert "json.load" not in rows["YAML"]
    assert re.search(r"\b(yaml|yq)\b", rows["YAML"], re.IGNORECASE)


def test_python_commands_are_scoped_to_explicit_targets() -> None:
    ref = _read(_REF)
    rows = _table(_section(ref, "## 対象コマンドの選び方"))
    tests = rows["Python の対象テスト"]
    syntax = rows["Python の対象構文確認"]

    assert "pytest" in tests
    assert _has_target_placeholder(tests)
    assert _has_target_placeholder(syntax)


def test_core_completion_is_exit_code_based_and_report_schema_stays_visible() -> None:
    skill = _read(_SKILL)
    ref = _read(_REF)

    assert "要求定義から導いたコマンドの exit code" in skill
    assert "合否を文章だけで主張しない" in skill
    assert "対象テスト" in skill
    assert "PR の CI で 1 回" in skill
    report = _report_template(ref)
    assert all(label in report for label in ("## Acceptance Criteria", "## Commands", "Exit-Code", "Output-Summary"))
    assert "原因、再試行条件、停止条件" in _section(ref, "## 失敗時")
    assert "--remote" not in skill + ref
    for removed in ("Phase 1: Build", "Phase 2: Lint", "Phase 3: Test", "Phase 4: Security Scan", "Phase 5: Diff Review"):
        assert removed not in skill + ref


def test_missing_external_endpoint_blocks_instead_of_passing() -> None:
    section = _section(_read(_REF), "## 対象コマンドの選び方")
    endpoint_line = next(line for line in section.splitlines() if "外部サービス用" in line)

    assert "FAIL(環境ブロッカー)" in endpoint_line or "blocked" in endpoint_line
    assert "成功扱いしない" in endpoint_line