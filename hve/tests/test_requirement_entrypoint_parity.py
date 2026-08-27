"""FR-CLI-10: 引数なし起動の既定と、要求定義書の記述の parity を検査する。

`FR-CLI-10` は長らく「引数なしは対話 wizard を起動する」と記述していたが、
実装は GUI を既定として起動し、PySide6 未導入時にだけ対話へフォールバックする。
同一文書内の `FR-CLI-77` は「引数なし起動（GUI が既定）」と正しく記述しており、
`FR-CLI-10` と §5.1 の `run` 行だけが実装へ追随していなかった。
本テストは両者の一致を固定する。
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_DEFINITION = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_MAIN_SOURCE = _REPO_ROOT / "hve" / "__main__.py"


def _requirement_line(requirement_id: str) -> str:
    for line in _REQUIREMENT_DEFINITION.read_text(encoding="utf-8-sig").splitlines():
        if line.lstrip("- ").startswith(f"**{requirement_id}**"):
            return line
    raise AssertionError(f"{requirement_id} が要求定義書に見つからない")


def _no_args_branch_source() -> str:
    """`main()` の `args.command is None` 分岐を文字列として返す。"""
    tree = ast.parse(_MAIN_SOURCE.read_text(encoding="utf-8"))
    main_fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    for node in ast.walk(main_fn):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.ops[0], ast.Is)
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
            and ast.unparse(test.left) == "args.command"
        ):
            return ast.unparse(node)
    raise AssertionError("main() に `args.command is None` の分岐が見つからない")


class TestEntrypointParity:
    def test_requirement_declares_gui_as_the_no_args_default(self) -> None:
        line = _requirement_line("FR-CLI-10")
        assert "GUI" in line, "FR-CLI-10 が引数なし起動の既定を GUI と宣言していない"

    def test_requirement_declares_the_pyside6_fallback(self) -> None:
        line = _requirement_line("FR-CLI-10")
        assert "PySide6" in line
        assert "フォールバック" in line

    def test_implementation_starts_the_gui_and_falls_back_to_the_wizard(self) -> None:
        branch = _no_args_branch_source()
        assert "run_gui" in branch
        assert "_cmd_run_interactive" in branch
        assert "ImportError" in branch
