"""FR-KIT-05: 配布対象のコードは上流固有パッケージ（`hve`）へ依存しない。

根拠: hve-dev/requirement-definition.md §3.10 FR-KIT-05

RED（実装前）:
  - `mdq/usage_stats.py` が `from hve.gui import mdq_index_service` を実行する
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# 配布対象ツリー（上流の正本と、そこから生成される配布コピー）。
_DISTRIBUTED_ROOTS = (
    "mdq",
    "cq",
    "tools/skills/_kit",
    "tools/skills/markdown_query/vendor",
    "tools/skills/code_query/vendor",
    "tools/skills/markdown_query/kit",
    "tools/skills/code_query/kit",
)


def _python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).parts
        if "tests" in parts or "__pycache__" in parts:
            continue
        yield path


def _imports_upstream(path: Path) -> bool:
    # BOM 付きで保存されたファイルがあるため utf-8-sig で読む。
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "hve" or a.name.startswith("hve.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "hve" or module.startswith("hve."):
                return True
    return False


@pytest.mark.parametrize("root_rel", _DISTRIBUTED_ROOTS)
def test_distributed_tree_does_not_import_the_upstream_package(root_rel: str) -> None:
    root = _REPO_ROOT / root_rel
    if not root.is_dir():
        pytest.skip(f"{root_rel} does not exist")
    offenders = [
        str(p.relative_to(_REPO_ROOT))
        for p in _python_files(root)
        if _imports_upstream(p)
    ]
    assert offenders == [], (
        f"distributed code must not depend on the upstream `hve` package: {offenders}"
    )


def test_usage_statistics_run_without_the_upstream_package(tmp_path: Path) -> None:
    """実行時に `hve` が import されないことを別プロセスで確認する。"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# hi\n\nbody\n", encoding="utf-8")
    script = (
        "import sys, json\n"
        "from pathlib import Path\n"
        "from mdq import usage_stats\n"
        "usage_stats.aggregate_usage_stats(Path(sys.argv[1]), window_days=7)\n"
        "leaked = sorted(m for m in sys.modules if m == 'hve' or m.startswith('hve.'))\n"
        "print(json.dumps(leaked))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("[]"), result.stdout
