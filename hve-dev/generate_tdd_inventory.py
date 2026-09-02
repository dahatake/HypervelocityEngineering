"""Generate HVE TDD inventory artifacts.

This script intentionally derives inventory rows from tracked and non-ignored repository files.
It does not infer or fabricate tests/features beyond observable file contents.
"""

from __future__ import annotations

import ast
import csv
import os
import pathlib
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cq import surface_export  # noqa: E402  面横断索引の抽出アルゴリズムは単一実装
from cq.surface_export import SURFACE_FIELDNAMES  # noqa: E402
from cq.traces import FEATURE_ID_RE  # noqa: E402  規範 ID の抽出パターンは単一定義

OUT_DIR = ROOT / "hve-dev"
TEST_CSV = OUT_DIR / "hve-test-inventory.csv"
FEATURE_CSV = OUT_DIR / "hve-feature-inventory.csv"
CROSSWALK_MD = OUT_DIR / "hve-tdd-crosswalk-baseline.md"
POLICY_MD = OUT_DIR / "hve-tdd-change-policy.md"
SURFACE_CSV = OUT_DIR / "hve-surface-inventory.csv"
REQ_DEF = OUT_DIR / "requirement-definition.md"
REQ_MAP = OUT_DIR / "requirement-test-mapping.md"
GATE_ID_RE = r"G-[A-Z]+"

# copilot-instructions.md / Skill のルールを機械判定するために実装が直接参照する固定文字列。
# FR-MAINT-06 は推測での追加を禁じるため、実在を確認した語だけを列挙する。
NORMATIVE_LITERALS = (
    "validation-confirmed",
    "task_scope",
    "context_size",
    "split_decision",
    "implementation_files",
    "subissues_count",
    "hve-traceability",
)
CLI_SURFACE_FILES = frozenset({"hve/__main__.py", "hve/orchestrator.py", "hve/runner.py"})
_SCOPE_MODULE = None

TEST_FIELDNAMES = [
    "category",
    "subsystem",
    "file",
    "line",
    "kind",
    "class_or_scope",
    "function_or_case",
    "async",
    "decorators_or_context",
    "spec_source",
    "specification",
    "evidence",
    "markers",
    "parametrize",
    "nodeid_hint",
]

FEATURE_FIELDNAMES = [
    "feature_kind",
    "feature_id",
    "active_status",
    "section",
    "title_or_summary",
    "source",
    "line",
    "details",
]


SURFACE_FIELDNAMES = SURFACE_FIELDNAMES


def git_files() -> list[str]:
    candidates = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).splitlines()
    # `git ls-files --cached` は削除をcommitする前のパスも返す。存在しないパスを
    # parse-error行としてinventoryへ残すと、削除済みテストや旧識別子が現行契約に
    # 見えてしまうため、現在の作業ツリーで実在する通常ファイルだけを入力にする。
    return [path for path in candidates if (ROOT / path).is_file()]


def category_for_test_path(path: str) -> tuple[str, str] | None:
    if re.search(r"(^|/)hve/tests/.*\.py$", path):
        return "core-python", "hve-cli-orchestrator"
    if re.search(r"(^|/)hve/gui/tests/.*\.py$", path):
        return "gui-python", "hve-gui-orchestrator"
    if re.search(r"(^|/)\.github/scripts/python/tests/.*\.py$", path):
        return "github-script-python", "cloud-orchestrator-scripts"
    if re.search(r"(^|/)\.github/scripts/powershell/tests/.*\.ps1$", path):
        return "github-script-powershell", "cloud-orchestrator-scripts"
    if re.search(r"(^|/)\.github/scripts/tests/.*\.(sh|ps1|py)$", path):
        return "github-script-shell", "cloud-orchestrator-scripts"
    if re.search(r"(^|/)mdq/tests/.*\.py$", path):
        return "mdq-support-python", "hve-mdq-support"
    if re.search(r"(^|/)cq/tests/.*\.py$", path):
        return "cq-support-python", "hve-cq-support"
    if re.search(r"(^|/)mdq/gui/tests/.*\.py$", path):
        return "markdown-query-gui-support-python", "hve-mdq-support"
    return None


def compact(value: object, limit: int = 360) -> str:
    return surface_export.compact(value, limit)


def safe_unparse(node: ast.AST) -> str:
    return surface_export.safe_unparse(node)


def is_fixture_decorator(decorator: ast.AST) -> bool:
    text = safe_unparse(decorator)
    return (
        text == "pytest.fixture"
        or text.startswith("pytest.fixture(")
        or text.endswith(".fixture")
        or ".fixture(" in text
    )


def is_parametrize_decorator(decorator: ast.AST) -> bool:
    return "parametrize" in safe_unparse(decorator)


def is_pytest_mark(decorator: ast.AST) -> bool:
    text = safe_unparse(decorator)
    return text.startswith("pytest.mark.") or ".pytest.mark." in text


class EvidenceVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.asserts: list[str] = []
        self.raises: list[str] = []
        self.calls: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        return

    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        self.asserts.append(safe_unparse(node.test))
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:  # noqa: N802
        for item in node.items:
            expr = safe_unparse(item.context_expr)
            if "pytest.raises" in expr or re.search(r"\braises\(", expr):
                self.raises.append(expr)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:  # noqa: N802
        for item in node.items:
            expr = safe_unparse(item.context_expr)
            if "pytest.raises" in expr or re.search(r"\braises\(", expr):
                self.raises.append(expr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        fn = safe_unparse(node.func)
        ignored = {"print", "str", "int", "len", "list", "dict", "set", "tuple", "bool"}
        if fn not in ignored:
            self.calls.append(fn)
        self.generic_visit(node)


def collect_evidence(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    visitor = EvidenceVisitor()
    for stmt in fn_node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        visitor.visit(stmt)
    parts: list[str] = []
    if visitor.asserts:
        parts.append("assert=" + " ; ".join(compact(x, 120) for x in visitor.asserts[:5]))
    if visitor.raises:
        parts.append("raises=" + " ; ".join(compact(x, 120) for x in visitor.raises[:5]))
    if visitor.calls:
        unique_calls = list(dict.fromkeys(visitor.calls))
        parts.append("calls=" + " ; ".join(compact(x, 80) for x in unique_calls[:10]))
    return " | ".join(parts)


def classify_py_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    parent_stack: tuple[tuple[str, str], ...],
) -> tuple[str, str, list[str]]:
    class_names = [name for kind, name in parent_stack if kind == "class"]
    decorators = [safe_unparse(d) for d in fn.decorator_list]
    if fn.name.startswith("test_"):
        kind = "test"
    elif any(is_fixture_decorator(d) for d in fn.decorator_list):
        kind = "fixture"
    elif fn.name in {
        "setup_method",
        "teardown_method",
        "setup_class",
        "teardown_class",
        "setUp",
        "tearDown",
    }:
        kind = "setup-teardown"
    elif fn.name.startswith("pytest_"):
        kind = "pytest-hook"
    elif class_names and class_names[-1].startswith("Test") and fn.name.startswith("test"):
        kind = "test"
    else:
        kind = "helper"
    return kind, class_names[-1] if class_names else "module", decorators


def iter_py_defs(tree: ast.Module) -> Iterable[tuple[ast.FunctionDef | ast.AsyncFunctionDef, tuple[tuple[str, str], ...]]]:
    stack: list[tuple[str, str]] = []

    def rec(node: ast.AST) -> Iterable[tuple[ast.FunctionDef | ast.AsyncFunctionDef, tuple[tuple[str, str], ...]]]:
        for child in getattr(node, "body", []):
            if isinstance(child, ast.ClassDef):
                stack.append(("class", child.name))
                yield from rec(child)
                stack.pop()
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield child, tuple(stack)
                stack.append(("function", child.name))
                yield from rec(child)
                stack.pop()

    yield from rec(tree)


def parse_python_test(path_rel: str, category: str, subsystem: str) -> list[dict[str, object]]:
    path = ROOT / path_rel
    rows: list[dict[str, object]] = []
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=path_rel)
    except Exception as exc:  # pragma: no cover - recorded in output for transparency
        return [
            {
                "category": category,
                "subsystem": subsystem,
                "file": path_rel,
                "line": "",
                "kind": "parse-error",
                "class_or_scope": "",
                "function_or_case": "",
                "async": "",
                "decorators_or_context": "",
                "spec_source": "parse-error",
                "specification": f"parse failed: {exc}",
                "evidence": "",
                "markers": "",
                "parametrize": "",
                "nodeid_hint": path_rel,
            }
        ]

    for fn, parent_stack in iter_py_defs(tree):
        kind, scope, decorators = classify_py_function(fn, parent_stack)
        doc = ast.get_docstring(fn)
        evidence = collect_evidence(fn)
        decorator_text = " ; ".join(compact(d, 180) for d in decorators)
        markers = " ; ".join(
            compact(safe_unparse(d), 180) for d in fn.decorator_list if is_pytest_mark(d)
        )
        parametrizes = " ; ".join(
            compact(safe_unparse(d), 220) for d in fn.decorator_list if is_parametrize_decorator(d)
        )
        qualname = ".".join([name for _, name in parent_stack] + [fn.name])
        if doc:
            spec_source = "docstring"
            specification = compact(doc, 500)
        elif kind == "test":
            spec_source = "function-name-and-code-evidence"
            specification = compact(
                f"name={fn.name}; evidence={evidence or 'no assert/raises/call evidence extracted'}",
                500,
            )
        elif kind == "fixture":
            spec_source = "fixture-definition"
            specification = compact(
                f"pytest fixture/helper for tests: {fn.name}; decorators={decorator_text}",
                500,
            )
        else:
            spec_source = "helper-definition"
            specification = compact(
                f"test helper/hook/setup function: {fn.name}; evidence={evidence}",
                500,
            )
        rows.append(
            {
                "category": category,
                "subsystem": subsystem,
                "file": path_rel,
                "line": getattr(fn, "lineno", ""),
                "kind": kind,
                "class_or_scope": scope,
                "function_or_case": fn.name,
                "async": "yes" if isinstance(fn, ast.AsyncFunctionDef) else "no",
                "decorators_or_context": decorator_text,
                "spec_source": spec_source,
                "specification": specification,
                "evidence": compact(evidence, 800),
                "markers": markers,
                "parametrize": parametrizes,
                "nodeid_hint": f"{path_rel}::{qualname}",
            }
        )
    if not rows:
        rows.append(
            {
                "category": category,
                "subsystem": subsystem,
                "file": path_rel,
                "line": 1,
                "kind": "python-file",
                "class_or_scope": "module",
                "function_or_case": pathlib.Path(path_rel).name,
                "async": "no",
                "decorators_or_context": "",
                "spec_source": "file-without-functions",
                "specification": "Python test package/support file with no function definitions",
                "evidence": "",
                "markers": "",
                "parametrize": "",
                "nodeid_hint": path_rel,
            }
        )
    return rows


def parse_powershell_test(path_rel: str, category: str, subsystem: str) -> list[dict[str, object]]:
    path = ROOT / path_rel
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    rows: list[dict[str, object]] = []
    current_describe = ""
    current_context = ""
    for i, line in enumerate(lines, start=1):
        if m := re.match(r"\s*Describe\s+['\"]([^'\"]+)['\"]", line):
            current_describe = m.group(1)
            current_context = ""
        if m := re.match(r"\s*Context\s+['\"]([^'\"]+)['\"]", line):
            current_context = m.group(1)
        if m := re.match(r"\s*It\s+['\"]([^'\"]+)['\"]", line):
            spec = m.group(1)
            evidence_lines = []
            for look in lines[i : i + 40]:
                if re.match(r"\s*(It|Describe|Context)\s+['\"]", look):
                    break
                if "Should " in look or "Should-" in look:
                    evidence_lines.append(compact(look.strip(), 180))
            ctx = " > ".join(x for x in [current_describe, current_context] if x)
            rows.append(
                {
                    "category": category,
                    "subsystem": subsystem,
                    "file": path_rel,
                    "line": i,
                    "kind": "pester-it",
                    "class_or_scope": current_describe,
                    "function_or_case": spec,
                    "async": "no",
                    "decorators_or_context": ctx,
                    "spec_source": "pester-it-literal",
                    "specification": spec,
                    "evidence": " | ".join(evidence_lines),
                    "markers": "",
                    "parametrize": "",
                    "nodeid_hint": f"{path_rel}::{current_describe}::{spec}",
                }
            )
        if m := re.match(r"\s*function\s+([A-Za-z0-9_-]+)", line):
            name = m.group(1)
            rows.append(
                {
                    "category": category,
                    "subsystem": subsystem,
                    "file": path_rel,
                    "line": i,
                    "kind": "powershell-helper",
                    "class_or_scope": current_describe,
                    "function_or_case": name,
                    "async": "no",
                    "decorators_or_context": current_describe,
                    "spec_source": "function-definition",
                    "specification": f"PowerShell helper function in test file: {name}",
                    "evidence": "",
                    "markers": "",
                    "parametrize": "",
                    "nodeid_hint": f"{path_rel}::{name}",
                }
            )
    return rows


def parse_shell_test(path_rel: str, category: str, subsystem: str) -> list[dict[str, object]]:
    path = ROOT / path_rel
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[dict[str, object]] = []
    current_section = ""
    for i, line in enumerate(lines, start=1):
        if section := re.match(r"\s*echo\s+[\"']={3,}\s*([^\"']+)\s*={3,}[\"']", line):
            current_section = compact(section.group(1), 120)
        if fn := re.match(r"\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{", line):
            name = fn.group(1)
            rows.append(
                {
                    "category": category,
                    "subsystem": subsystem,
                    "file": path_rel,
                    "line": i,
                    "kind": "shell-helper",
                    "class_or_scope": current_section,
                    "function_or_case": name,
                    "async": "no",
                    "decorators_or_context": current_section,
                    "spec_source": "function-definition",
                    "specification": f"Shell helper function in test script: {name}",
                    "evidence": "",
                    "markers": "",
                    "parametrize": "",
                    "nodeid_hint": f"{path_rel}::{name}",
                }
            )
        if m := re.search(r"\bpass\s+[\"']([^\"']+)[\"']", line):
            spec = m.group(1)
            rows.append(
                {
                    "category": category,
                    "subsystem": subsystem,
                    "file": path_rel,
                    "line": i,
                    "kind": "shell-case",
                    "class_or_scope": current_section,
                    "function_or_case": spec,
                    "async": "no",
                    "decorators_or_context": current_section,
                    "spec_source": "pass-label-literal",
                    "specification": spec,
                    "evidence": compact(line.strip(), 240),
                    "markers": "",
                    "parametrize": "",
                    "nodeid_hint": f"{path_rel}::line-{i}",
                }
            )
    if not rows:
        rows.append(
            {
                "category": category,
                "subsystem": subsystem,
                "file": path_rel,
                "line": 1,
                "kind": "script",
                "class_or_scope": "",
                "function_or_case": pathlib.Path(path_rel).name,
                "async": "no",
                "decorators_or_context": "",
                "spec_source": "script-file",
                "specification": "Test script file; no pass-label/function pattern extracted",
                "evidence": "",
                "markers": "",
                "parametrize": "",
                "nodeid_hint": path_rel,
            }
        )
    return rows


def collect_tests(files: list[str]) -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    selected_files: list[str] = []
    for path in files:
        category = category_for_test_path(path)
        if not category:
            continue
        category_name, subsystem = category
        selected_files.append(path)
        if path.endswith(".py"):
            rows.extend(parse_python_test(path, category_name, subsystem))
        elif path.endswith(".ps1"):
            rows.extend(parse_powershell_test(path, category_name, subsystem))
        elif path.endswith(".sh"):
            rows.extend(parse_shell_test(path, category_name, subsystem))
    rows.sort(key=lambda r: (str(r["category"]), str(r["file"]), row_line_number(r), str(r["function_or_case"])))
    return rows, selected_files


def row_line_number(row: dict[str, object]) -> int:
    try:
        return int(str(row.get("line") or 0))
    except ValueError:
        return 0


def section_from_heading(line: str) -> str | None:
    if m := re.match(r"^(#{1,6})\s+(.+?)\s*$", line):
        return m.group(2).strip()
    return None


def active_status_for_text(text: str) -> str:
    if "~~" in text or "→ **廃止" in text or "→ 廃止" in text:
        return "deprecated-or-removed"
    if "未対応" in text or "✗" in text:
        return "partial-or-not-supported"
    return "active-or-described"


def unique_in_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def defined_feature_ids_in_line(line: str) -> list[str]:
    """Return feature IDs only when the line appears to define them.

    Plain prose references such as "...（NFR-COMP-01）" are intentionally ignored.
    """
    ids: list[str] = []
    ids.extend(re.findall(rf"\*\*({FEATURE_ID_RE})(?:（[^）]+）)?\*\*", line))
    if m := re.match(rf"\s*\|\s*(?:~~)?({FEATURE_ID_RE})(?:（[^）]+）)?(?:[^|]*?)(?:~~)?\s*\|", line):
        ids.append(m.group(1))
    if m := re.match(rf"\s*-\s*(?:~~)?({FEATURE_ID_RE})\s*:", line):
        ids.append(m.group(1))
    return unique_in_order(ids)


def defined_gate_ids_in_line(line: str) -> list[str]:
    ids: list[str] = []
    ids.extend(re.findall(rf"\*\*({GATE_ID_RE})\*\*", line))
    if m := re.match(rf"\s*\|\s*({GATE_ID_RE})(?:[^|]*?)\s*\|", line):
        ids.append(m.group(1))
    return unique_in_order(ids)


def collect_features_from_requirement_definition() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not REQ_DEF.exists():
        return rows
    current_section = ""
    for i, line in enumerate(REQ_DEF.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if heading := section_from_heading(line):
            current_section = heading
        if current_section.startswith(("11.", "12.", "14.")):
            continue

        for feature_id in defined_feature_ids_in_line(line):
            rows.append(
                {
                    "feature_kind": feature_id.split("-")[0],
                    "feature_id": feature_id,
                    "active_status": active_status_for_text(line),
                    "section": current_section,
                    "title_or_summary": compact(line, 600),
                    "source": "hve-dev/requirement-definition.md",
                    "line": i,
                    "details": compact(line, 1000),
                }
            )
        for gate_id in defined_gate_ids_in_line(line):
            rows.append(
                {
                    "feature_kind": "GATE",
                    "feature_id": gate_id,
                    "active_status": active_status_for_text(line),
                    "section": current_section,
                    "title_or_summary": compact(line, 600),
                    "source": "hve-dev/requirement-definition.md",
                    "line": i,
                    "details": compact(line, 1000),
                }
            )

    seen: set[tuple[object, object, object]] = set()
    deduped: list[dict[str, object]] = []
    for row in rows:
        key = (row["feature_id"], row["source"], row["line"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def collect_workflow_features_from_code() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        sys.path.insert(0, str(ROOT))
        from hve.workflow_registry import list_workflows

        for workflow in sorted(list_workflows(), key=lambda item: item.id):
            steps = getattr(workflow, "steps", [])
            rows.append(
                {
                    "feature_kind": "WORKFLOW",
                    "feature_id": f"WF-{workflow.id.upper()}",
                    "active_status": "active-code",
                    "section": "hve.workflow_registry",
                    "title_or_summary": getattr(workflow, "name", workflow.id),
                    "source": "hve/workflow_registry.py",
                    "line": "",
                    "details": compact(
                        f"id={workflow.id}; prefix={getattr(workflow, 'prefix', '')}; steps={len(steps)}; max_parallel={getattr(workflow, 'max_parallel', '')}",
                        1000,
                    ),
                }
            )
            for step in steps:
                step_id = getattr(step, "id", "")
                rows.append(
                    {
                        "feature_kind": "WORKFLOW_STEP",
                        "feature_id": f"WF-{workflow.id.upper()}-STEP-{step_id}",
                        "active_status": "active-code",
                        "section": f"Workflow {workflow.id}",
                        "title_or_summary": getattr(step, "title", ""),
                        "source": "hve/workflow_registry.py",
                        "line": "",
                        "details": compact(
                            f"custom_agent={getattr(step, 'custom_agent', '')}; depends_on={getattr(step, 'depends_on', [])}; fanout_static_keys={getattr(step, 'fanout_static_keys', None)}; fanout_parser={getattr(step, 'fanout_parser', None)}; output_paths={getattr(step, 'output_paths', None)}; output_paths_template={getattr(step, 'output_paths_template', None)}; required_input_paths={getattr(step, 'required_input_paths', None)}",
                            1600,
                        ),
                    }
                )
    except Exception as exc:
        rows.append(
            {
                "feature_kind": "WORKFLOW_IMPORT_ERROR",
                "feature_id": "WF-IMPORT-ERROR",
                "active_status": "unknown",
                "section": "hve.workflow_registry",
                "title_or_summary": f"workflow_registry import failed: {exc}",
                "source": "hve/workflow_registry.py",
                "line": "",
                "details": repr(exc),
            }
        )
    return rows


def collect_features() -> list[dict[str, object]]:
    rows = collect_features_from_requirement_definition()
    rows.extend(collect_workflow_features_from_code())
    rows.sort(key=lambda r: (str(r["feature_kind"]), str(r["feature_id"]), str(r["line"])))
    return rows


def parse_mapping_ids() -> dict[str, dict[str, object]]:
    if not REQ_MAP.exists():
        return {}
    mapping: dict[str, dict[str, object]] = {}
    current = ""
    for i, line in enumerate(REQ_MAP.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if heading := re.match(r"#{2,6}\s+(.+)", line):
            title = heading.group(1)
            ids = mapping_ids_from_text(title)
            if ids:
                current = ids[0]
                for mapping_id in ids:
                    mapping.setdefault(
                        mapping_id,
                        {"line": i, "title": compact(title, 300), "judgment": "", "tests": []},
                    )
                continue
        if row := re.match(rf"\s*\|\s*({GATE_ID_RE})(?:[^|]*?)\s*\|", line):
            current = row.group(1)
            mapping.setdefault(
                current,
                {"line": i, "title": compact(line, 300), "judgment": "", "tests": []},
            )
            continue
        if current:
            if m := re.match(r"\s*-\s*判定:\s*(.*)", line):
                mapping[current]["judgment"] = compact(m.group(1), 200)
            if "hve/tests/" in line or ".github/scripts/" in line or "hve/gui/tests/" in line:
                tests_value = mapping[current]["tests"]
                if isinstance(tests_value, list):
                    tests_value.append(compact(line, 500))
    return mapping


def mapping_ids_from_text(text: str) -> list[str]:
    ids = re.findall(rf"{FEATURE_ID_RE}|{GATE_ID_RE}|§[0-9.]+", text)
    for match in re.finditer(r"((?:FR|NFR)-[A-Z0-9-]+-)(\d+)((?:\s*/\s*\d+)+)", text):
        prefix, first_number, tail = match.groups()
        width = len(first_number)
        for number in re.findall(r"\d+", tail):
            ids.append(f"{prefix}{number.zfill(width)}")
    return unique_in_order(ids)


def canonical_feature_id(feature_id: str) -> str:
    return re.sub(r"-§[0-9.]+$", "", feature_id)


def write_csv(path: pathlib.Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def scope_module():
    """§3.7 対象境界の単一機械判定（FR-MAINT-05）。ここで境界を再定義しない。"""
    global _SCOPE_MODULE
    if _SCOPE_MODULE is None:
        scripts_dir = str(ROOT / ".github" / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import hve_scope  # type: ignore[import-not-found]

        _SCOPE_MODULE = hve_scope
    return _SCOPE_MODULE


def surface_for_path(path: str) -> str | None:
    if not scope_module().is_in_scope(path):
        return None
    if path.startswith(".github/"):
        return "cloud"
    if path.startswith("hve/gui/"):
        return "gui"
    if path in CLI_SURFACE_FILES:
        return "cli"
    return "core"


def literals_in(text: str) -> str:
    return surface_export.literals_in(text, NORMATIVE_LITERALS)


def summarize_definition(node: ast.AST, segment: str) -> str:
    return surface_export.summarize_definition(node, segment)


def collect_surface_symbols(files: list[str]) -> list[dict[str, object]]:
    """FR-CQ-10: 抽出アルゴリズムは cq.surface_export に単一実装する。"""
    policy = surface_export.SurfacePolicy(
        surface_for_path=surface_for_path,
        is_test_path=lambda path: category_for_test_path(path) is not None,
        normative_literals=NORMATIVE_LITERALS,
    )
    return surface_export.collect(ROOT, files, policy)


def write_policy() -> None:
    POLICY_MD.write_text(
        """# HVE アプリケーション開発 TDD 運用ルール

## 適用範囲

- 対象は **`hve` アプリケーション**（HVE CLI / GUI / Cloud Agent Orchestrator、および同梱の MDQ / markdown-query 支援ツール関連コード・スクリプト・ドキュメント）に限定する。
- HVE が開発対象として生成・支援する **他アプリケーション** には、このルールを絶対に適用しない。
- バグ修正は例外。ただし、バグ修正から新機能・仕様変更へスコープが広がる場合は、このルールに切り替える。

## バグ修正を除く機能変更の必須順序

1. **機能要件に追加**
   - `hve-dev/requirement-definition.md` または後続の正規要件文書に、機能要件 / 非機能要件 / ゲート条件を追加する。
   - 不明点は `TBD` として明示し、推測を事実として書かない。
2. **テスト仕様に追加**
   - `hve-dev/requirement-test-mapping.md` または後続の正規テスト仕様・突合表に、期待するテストを追加する。
   - 既存テストで満たす場合は該当テスト名を明記する。
   - 既存テストが無い場合は「要追加」と明記する。
3. **RED を確認する**
    - 同じ対象テストを作成し、実装前に失敗することを確認する。
4. **索引を再生成して照合する**
    - `hve-feature-inventory.csv` と `hve-test-inventory.csv` を再生成し、新規 ID の source / status とテストパスを照合する。
5. **実装して GREEN を確認する**
    - 実装後、同じ対象テストが成功することを確認する。
6. **マッピングへ実結果を反映する**
    - `requirement-test-mapping.md` に GREEN 結果を反映する。

## 捏造禁止

- テスト名、関数名、ファイルパス、要求 ID、検証結果を根拠なく作らない。
- 未確認の項目は `未確認` / `TBD` / `該当なし（理由: ...）` と書く。
- 「関数仕様」はコード・docstring・テスト名・assert/raises/Should 等の実在情報からのみ記録する。

## 完了条件

- 変更対象の要求 ID とテスト ID が突合できること。
- 少なくとも 1 つの検証（テスト / 静的解析 / 生成物検査）を実行し、結果を記録すること。
""",
        encoding="utf-8",
    )


def _generation_timestamp() -> str:
    """Return a reproducible UTC timestamp when SOURCE_DATE_EPOCH is set."""
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is None:
        generated_at = datetime.now(timezone.utc)
    else:
        try:
            epoch = int(source_date_epoch)
        except ValueError as exc:
            raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer") from exc
        if epoch < 0:
            raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer")
        generated_at = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_crosswalk(test_rows: list[dict[str, object]], feature_rows: list[dict[str, object]], mapping: dict[str, dict[str, object]]) -> None:
    test_by_cat = Counter(str(r["category"]) for r in test_rows)
    test_by_kind = Counter(str(r["kind"]) for r in test_rows)
    files_by_cat: dict[str, set[str]] = defaultdict(set)
    for row in test_rows:
        files_by_cat[str(row["category"])].add(str(row["file"]))

    feature_by_kind = Counter(str(r["feature_kind"]) for r in feature_rows)
    feature_ids = {
        str(r["feature_id"])
        for r in feature_rows
        if str(r["feature_kind"]) in {"FR", "NFR", "GATE", "C", "UC"}
    }
    mapping_ids = set(mapping.keys())
    feature_canonical_ids = {canonical_feature_id(feature_id) for feature_id in feature_ids}
    mapping_canonical_ids = {canonical_feature_id(mapping_id) for mapping_id in mapping_ids}
    missing_in_mapping = sorted(
        fid
        for fid in feature_ids
        if canonical_feature_id(fid) not in mapping_canonical_ids and not fid.startswith(("C-", "UC-"))
    )
    stale_in_mapping = sorted(
        mid
        for mid in mapping_ids
        if canonical_feature_id(mid) not in feature_canonical_ids and not mid.startswith("§")
    )
    deprecated_features = sorted(
        {str(r["feature_id"]) for r in feature_rows if r["active_status"] == "deprecated-or-removed"}
    )
    now = _generation_timestamp()

    lines = [
        "# HVE TDD ベースライン突合サマリー",
        "",
        f"- 生成日時 (UTC): `{now}`",
        "- 対象: `hve` アプリケーションのみ（HVE CLI / GUI / Cloud Agent Orchestrator 関連）。他アプリ開発には適用しない。",
        "- 捏造防止: テスト仕様欄は docstring / 関数名 / assert・raises・Pester `Should` / shell `pass` ラベル等、実在コードから機械抽出した。",
        "",
        "## 生成物",
        "",
        f"- `{TEST_CSV.relative_to(ROOT).as_posix()}` — 既存テストコードの全関数/ケース棚卸し。",
        f"- `{FEATURE_CSV.relative_to(ROOT).as_posix()}` — 要求定義 ID と実コード Workflow/Step の機能一覧。",
        f"- `{SURFACE_CSV.relative_to(ROOT).as_posix()}` — HVE 対象の実装シンボルと実行面の一覧。",
        f"- `{CROSSWALK_MD.relative_to(ROOT).as_posix()}` — 要求定義・テストマッピング・生成inventoryの突合サマリー。",
        f"- `{POLICY_MD.relative_to(ROOT).as_posix()}` — 今後の hve 限定 TDD 運用ルール。",
        "",
        "## 対象範囲",
        "",
        "- 含める: `hve/tests/`, `hve/gui/tests/`, `.github/scripts/*/tests/`, `.github/scripts/tests/test_validate_skill_routing.py`, `mdq/tests/`, `cq/tests/`, `mdq/gui/tests/`。",
        "- 含めない: テスト fixture (`.github/scripts/tests/fixtures/` 等) と、HVE/MDQ 支援ツールに該当しない生成物・仮想環境・キャッシュ。",
        "",
        "## テスト棚卸し件数",
        "",
        f"- 抽出行数: **{len(test_rows)}**",
        f"- 対象ファイル数: **{len({str(r['file']) for r in test_rows})}**",
        "",
        "| 分類 | ファイル数 | 行数 |",
        "|---|---:|---:|",
    ]
    for category in sorted(test_by_cat):
        lines.append(f"| {category} | {len(files_by_cat[category])} | {test_by_cat[category]} |")
    lines.extend(["", "| 種別 | 行数 |", "|---|---:|"])
    for kind, count in sorted(test_by_kind.items()):
        lines.append(f"| {kind} | {count} |")
    lines.extend(
        [
            "",
            "## 機能一覧件数",
            "",
            f"- 抽出行数: **{len(feature_rows)}**",
            "",
            "| 種別 | 行数 |",
            "|---|---:|",
        ]
    )
    for kind, count in sorted(feature_by_kind.items()):
        lines.append(f"| {kind} | {count} |")
    lines.extend(
        [
            "",
            "## 要求定義 ↔ 既存マッピング文書の突合",
            "",
            f"- `hve-dev/requirement-definition.md` 側 ID 数（FR/NFR/GATE/C/UC）: **{len(feature_ids)}**",
            f"- `hve-dev/requirement-test-mapping.md` 側 ID 数: **{len(mapping_ids)}**",
            f"- 要求定義にあるがマッピング見出しが未確認の ID: **{len(missing_in_mapping)}**",
            f"- マッピングにあるが要求定義の抽出対象に無い ID: **{len(stale_in_mapping)}**",
            f"- 要求定義上で廃止/削除表記を含む ID: **{len(deprecated_features)}**",
            "",
            "### 要求定義にあるがマッピング見出しが未確認",
            "",
        ]
    )
    lines.extend([f"- `{fid}`" for fid in missing_in_mapping] or ["- なし"])
    lines.extend(["", "### マッピングにあるが要求定義の抽出対象に無い ID", ""])
    lines.extend([f"- `{fid}`" for fid in stale_in_mapping] or ["- なし"])
    lines.extend(["", "### 廃止/削除表記を含む ID", ""])
    lines.extend([f"- `{fid}`" for fid in deprecated_features] or ["- なし"])
    lines.extend(
        [
            "",
            "## 注意",
            "",
            "- 本ファイルは突合作業のベースラインであり、最終判断は `hve-test-inventory.csv` と `hve-feature-inventory.csv` の行単位確認で行う。",
            "- `spec_source=function-name-and-code-evidence` は、人手で自然文仕様へ清書する前の機械抽出表現である。",
            "- pytest の実 collection は optional dependency / importorskip の状態により、ソース上の test 関数一覧より少なくなる場合がある。CSV は実行可否ではなくソース棚卸しを正とする。",
        ]
    )
    CROSSWALK_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    files = git_files()
    test_rows, selected_test_files = collect_tests(files)
    feature_rows = collect_features()
    surface_rows = collect_surface_symbols(files)
    mapping = parse_mapping_ids()
    write_csv(TEST_CSV, test_rows, TEST_FIELDNAMES)
    write_csv(FEATURE_CSV, feature_rows, FEATURE_FIELDNAMES)
    write_csv(SURFACE_CSV, surface_rows, SURFACE_FIELDNAMES)
    write_policy()
    write_crosswalk(test_rows, feature_rows, mapping)
    print(f"wrote {TEST_CSV.relative_to(ROOT)} rows={len(test_rows)} files={len(set(r['file'] for r in test_rows))}")
    print(f"wrote {FEATURE_CSV.relative_to(ROOT)} rows={len(feature_rows)}")
    print(f"wrote {SURFACE_CSV.relative_to(ROOT)} rows={len(surface_rows)}")
    print(f"wrote {CROSSWALK_MD.relative_to(ROOT)}")
    print(f"wrote {POLICY_MD.relative_to(ROOT)}")
    print(f"selected_test_files={len(selected_test_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
