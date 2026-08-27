"""FR-PROMPT-SRC-01 / FR-PROMPT-SRC-02 の恒久契約テスト。

Prompt 本文の正本が `.github/prompts/**` に限定されていることと、読込が
`hve.prompt_loader` の単一実装で fail-closed であることを静的に固定する。
導入時は RED 契約として作成し、移行完了後は再混入検出の回帰テストとして維持する。
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

import pytest

import hve.prompt_loader as prompt_loader
from hve.workflow_registry import list_workflows


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPTS_ROOT = _REPO_ROOT / ".github" / "prompts"
_REQUIREMENTS = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_MAPPING = _REPO_ROOT / "hve-dev" / "requirement-test-mapping.md"
_FEATURE_INVENTORY = _REPO_ROOT / "hve-dev" / "hve-feature-inventory.csv"
_LEGACY_STEP_TEMPLATES = _REPO_ROOT / ".github" / "scripts" / "templates"
_LEGACY_FANOUT_PROMPTS = _REPO_ROOT / "hve" / "prompt"
_CLOUD_WORKFLOWS = {
    "copilot-auto-feedback.yml": _REPO_ROOT / ".github" / "workflows" / "copilot-auto-feedback.yml",
    "auto-review-to-approve-transition.yml": _REPO_ROOT / ".github" / "workflows" / "auto-review-to-approve-transition.yml",
    "auto-qa-default-answer.yml": _REPO_ROOT / ".github" / "workflows" / "auto-qa-default-answer.yml",
}
_CLOUD_INLINE_PROMPT_MARKERS = {
    "copilot-auto-feedback.yml": (
        "あなたは、私の依頼を実行する前に",
        "あなたは今から **敵対的レビュアー**",
    ),
    "auto-review-to-approve-transition.yml": (
        "## 再レビュー実行指示",
        "The automated adversarial review returned **FAIL**.",
    ),
    "auto-qa-default-answer.yml": (
        "## QA 質問票への回答（全問デフォルト値採用）",
        "質問票の全質問に対して、各質問に記載された",
    ),
}

_PROMPTS_RUNTIME_SYMBOLS = (
    "PRE_EXECUTION_QA_PROMPT_V2",
    "QA_PROMPT_V2",
    "MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT",
    "ARD_WORKIQ_USECASE_PROMPT",
    "AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT",
    "AKM_WORKIQ_INGEST_PROMPT",
)
_WORKIQ_RUNTIME_SYMBOLS = (
    "_WORKIQ_ROLE_PROMPT",
    "_WORKIQ_OUTPUT_SCHEMA_PROMPT",
    "_WORKIQ_FEWSHOT_PROMPT",
    "DEFAULT_WORKIQ_QA_PROMPT",
    "DEFAULT_WORKIQ_KM_PROMPT",
    "DEFAULT_WORKIQ_REVIEW_PROMPT",
)

_PROMPT_PRODUCER_INVENTORY: dict[str, dict[str, tuple[str, ...]]] = {
    "hve/prompts.py": {
        "must_call": ("load_prompt_file",),
        "must_not_inline": _PROMPTS_RUNTIME_SYMBOLS,
    },
    "hve/workiq.py": {
        "must_call": ("load_prompt_file",),
        "must_not_inline": _WORKIQ_RUNTIME_SYMBOLS,
    },
    "hve/self_improve.py": {
        "must_call": ("load_prompt_file",),
        "must_not_inline": ("_LLM_GOAL_PROMPT_TEMPLATE",),
    },
    "hve/repository_query.py": {"must_call": ("load_prompt_file",)},
    "hve/template_engine.py": {"must_call": ("load_prompt_file",)},
    "hve/orchestrator.py": {
        "must_import_from_prompts": (
            "CODE_REVIEW_AGENT_FIX_PROMPT",
            "CODE_REVIEW_CLI_PROMPT",
            "AKM_WORKIQ_VERIFY_AND_UPDATE_PROMPT",
            "AKM_WORKIQ_INGEST_PROMPT",
            "ARD_WORKIQ_USECASE_PROMPT",
            "ARD_TARGET_BUSINESS_FROM_RECOMMENDATION_PROMPT",
        )
    },
    "hve/runner.py": {
        "must_import_from_prompts": (
            "REVIEW_PROMPT",
            "ADVERSARIAL_RECHECK_PROMPT",
            "QA_PROMPT_V2",
            "SELF_IMPROVE_SCAN_PROMPT",
            "SELF_IMPROVE_PLAN_PROMPT",
            "SELF_IMPROVE_VERIFY_PROMPT",
            "PRE_EXECUTION_QA_PROMPT_V2",
            "MAIN_ARTIFACT_IMPROVEMENT_APPLY_PROMPT",
        )
    },
    "hve/application_requirements.py": {"must_call": ("load_prompt_file",)},
    "hve/input_aliases.py": {"must_call": ("load_prompt_file",)},
    "hve/mdq_enforcement.py": {"must_call": ("load_prompt_file",)},
    "hve/split_fork.py": {"must_call": ("load_prompt_file",)},
    "hve/fleet_mode.py": {"must_call": ("load_prompt_file",)},
    "hve/github_title_generator.py": {"must_call": ("load_prompt_file",)},
    "hve/gui/br_prompt_builder.py": {"must_call": ("load_prompt_file",)},
    "hve/gui/copilot_job_context.py": {"must_call": ("load_prompt_file",)},
    "hve-dev/evaluate_repository_query.py": {"must_call": ("load_prompt_file",)},
    "tools/measure_startup_tokens.py": {
        "must_call": ("load_prompt_file",),
        "must_not_inline": ("LIGHTWEIGHT_PROMPT",),
    },
}

_LOAD_PROMPT_FILE = getattr(prompt_loader, "load_prompt_file", None)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_ast(path: Path) -> ast.AST:
    return ast.parse(_read_text(path), filename=str(path))


def _is_non_empty_utf8_markdown(path: Path) -> bool:
    if path.suffix != ".md" or not path.is_file():
        return False
    data = path.read_bytes()
    if not data.strip():
        return False
    data.decode("utf-8")
    return True


def _iter_active_non_container_steps() -> Iterable[tuple[str, Any]]:
    for workflow in list_workflows():
        for step in workflow.steps:
            if not step.is_container:
                yield workflow.id, step


def _collect_called_names(tree: ast.AST) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    return called


def _collect_imported_names_from_prompts(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("prompts"):
            for alias in node.names:
                names.add(alias.name)
    return names


def _collect_non_loader_assignment_names(tree: ast.AST) -> set[str]:
    """Return assigned names whose value is not a direct prompt-loader call.

    固定 Prompt の再混入は plain string だけでなく f-string や文字列連結でも
    起こり得るため、RHS の構文種別ではなく loader への委譲有無で判定する。
    """
    assigned: set[str] = set()

    def _record(target: ast.expr, value: ast.AST) -> None:
        if not isinstance(target, ast.Name):
            return
        if isinstance(value, ast.Call):
            func = value.func
            if isinstance(func, ast.Name) and func.id == "load_prompt_file":
                return
            if isinstance(func, ast.Attribute) and func.attr == "load_prompt_file":
                return
        assigned.add(target.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _record(target, node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            _record(node.target, node.value)
    return assigned


def _require_load_prompt_file() -> Callable[..., str]:
    assert _LOAD_PROMPT_FILE is not None, (
        "FR-PROMPT-SRC-02: hve.prompt_loader.load_prompt_file(relative_path, *, prompts_dir=None, required=True) "
        "must exist"
    )
    return _LOAD_PROMPT_FILE


def _skip_if_load_prompt_file_missing() -> Callable[..., str]:
    if _LOAD_PROMPT_FILE is None:
        pytest.skip(
            "FR-PROMPT-SRC-02 behavior checks are skipped until load_prompt_file is implemented"
        )
    return _LOAD_PROMPT_FILE


def _make_prompt_file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_fr_prompt_src_01_requirement_and_mapping_are_registered_once_and_active() -> None:
    requirement_text = _read_text(_REQUIREMENTS)
    mapping_text = _read_text(_MAPPING)
    feature_inventory = _read_text(_FEATURE_INVENTORY)

    assert len(re.findall(r"^\- \*\*FR-PROMPT-SRC-01\b", requirement_text, re.MULTILINE)) == 1
    assert len(re.findall(r"^\- \*\*FR-PROMPT-SRC-02\b", requirement_text, re.MULTILINE)) == 1

    assert len(re.findall(r"^### FR-PROMPT-SRC-01\b", mapping_text, re.MULTILINE)) == 1
    assert len(re.findall(r"^### FR-PROMPT-SRC-02\b", mapping_text, re.MULTILINE)) == 1
    assert "要追加" in mapping_text

    assert len(re.findall(r"^FR,FR-PROMPT-SRC-01,active-or-described,", feature_inventory, re.MULTILINE)) == 1
    assert len(re.findall(r"^FR,FR-PROMPT-SRC-02,active-or-described,", feature_inventory, re.MULTILINE)) == 1


def test_fr_prompt_src_01_active_steps_use_repo_relative_prompt_sources() -> None:
    errors: list[str] = []

    for workflow_id, step in _iter_active_non_container_steps():
        body_path = getattr(step, "body_template_path", None)
        if not body_path:
            errors.append(f"{workflow_id}:{step.id} body_template_path is missing")
        else:
            expected_prefix = f".github/prompts/steps/{workflow_id}/"
            if not str(body_path).startswith(expected_prefix):
                errors.append(
                    f"{workflow_id}:{step.id} body_template_path must be repo-relative under {expected_prefix}: {body_path}"
                )
            resolved = _REPO_ROOT / str(body_path)
            if not _is_non_empty_utf8_markdown(resolved):
                errors.append(
                    f"{workflow_id}:{step.id} body_template_path must point to an existing non-empty UTF-8 markdown file: {body_path}"
                )

        additional_path = getattr(step, "additional_prompt_template_path", None)
        if additional_path:
            expected_prefix = f".github/prompts/fanout/{workflow_id}/"
            if not str(additional_path).startswith(expected_prefix):
                errors.append(
                    f"{workflow_id}:{step.id} additional_prompt_template_path must be repo-relative under {expected_prefix}: {additional_path}"
                )
            resolved = _REPO_ROOT / str(additional_path)
            if not _is_non_empty_utf8_markdown(resolved):
                errors.append(
                    f"{workflow_id}:{step.id} additional_prompt_template_path must point to an existing non-empty UTF-8 markdown file: {additional_path}"
                )

    assert not errors, "\n".join(errors)


def test_fr_prompt_src_01_legacy_prompt_source_directories_are_empty() -> None:
    legacy_templates = sorted(
        str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
        for path in _LEGACY_STEP_TEMPLATES.rglob("*.md")
    )
    legacy_fanout = sorted(
        str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
        for path in _LEGACY_FANOUT_PROMPTS.rglob("*.md")
        if path.name.lower() != "readme.md"
    )

    assert legacy_templates == [], (
        "FR-PROMPT-SRC-01: legacy .github/scripts/templates/** prompt sources must be removed after centralization:\n"
        + "\n".join(legacy_templates)
    )
    assert legacy_fanout == [], (
        "FR-PROMPT-SRC-01: legacy hve/prompt/** fanout prompt sources must be removed after centralization:\n"
        + "\n".join(legacy_fanout)
    )


@pytest.mark.parametrize(
    ("surface", "rel_path", "base_pattern"),
    [
        (
            "bash",
            ".github/scripts/bash/orchestrate.sh",
            re.compile(r'^_TEMPLATES_BASE="\$\(cd "\$\{_SCRIPT_DIR\}/(?P<up>[./]+)" && pwd\)"', re.MULTILINE),
        ),
        (
            "powershell",
            ".github/scripts/powershell/orchestrate.ps1",
            re.compile(r"^\$TemplatesBase = \(Resolve-Path \(Join-Path \$ScriptDir '(?P<up>[./]+)'\)\)\.Path", re.MULTILINE),
        ),
    ],
)
def test_fr_prompt_src_01_cloud_surfaces_resolve_the_same_prompt_files(
    surface: str, rel_path: str, base_pattern: re.Pattern[str]
) -> None:
    """Bash / PowerShell の基点が registry のリポジトリ相対パスと結合して実在ファイルを指すこと。

    registry の path 文字列が 3 面で一致していても、基点がずれると CLI/Cloud だけ
    Step body を読めずに縮退 Issue を作る。文字列一致ではなく実効解決を検証する。
    """
    script = _REPO_ROOT / rel_path
    match = base_pattern.search(_read_text(script))
    assert match is not None, f"{rel_path}: template base assignment not found"

    script_dir = script.parent
    base = (script_dir / match.group("up")).resolve()

    missing: list[str] = []
    for workflow_id, step in _iter_active_non_container_steps():
        body_path = getattr(step, "body_template_path", None)
        if not body_path:
            continue
        if not (base / str(body_path)).is_file():
            missing.append(f"{workflow_id}:{step.id} -> {base / str(body_path)}")

    assert not missing, (
        f"FR-PROMPT-SRC-01: {surface} surface cannot resolve step bodies from its template base "
        f"({base}):\n" + "\n".join(missing[:10])
    )


def test_fr_prompt_src_01_runtime_prompt_producers_have_explicit_inventory_evidence() -> None:
    errors: list[str] = []

    for rel_path, contract in _PROMPT_PRODUCER_INVENTORY.items():
        path = _REPO_ROOT / rel_path
        assert path.is_file(), rel_path
        tree = _read_ast(path)
        called = _collect_called_names(tree)
        imported = _collect_imported_names_from_prompts(tree)
        inline_assignments = _collect_non_loader_assignment_names(tree)

        must_call = set(contract.get("must_call", ()))
        if must_call and not must_call.issubset(called):
            errors.append(
                f"{rel_path} must call prompt-loader API(s) {sorted(must_call)}; found calls={sorted(called)}"
            )

        must_import = set(contract.get("must_import_from_prompts", ()))
        if must_import and not must_import.issubset(imported):
            errors.append(
                f"{rel_path} must import known externalized prompt symbol(s) {sorted(must_import)}; found imports={sorted(imported)}"
            )

        forbidden_inline = set(contract.get("must_not_inline", ()))
        leaked = sorted(forbidden_inline & inline_assignments)
        if leaked:
            errors.append(
                f"{rel_path} still defines inline prompt literal assignment(s) that must be externalized: {leaked}"
            )

    assert not errors, "\n".join(errors)


def test_fr_prompt_src_01_cloud_workflows_load_external_prompt_files_without_inline_prompt_bodies() -> None:
    errors: list[str] = []
    prompt_ref_re = re.compile(r"\.github/prompts/cloud/[A-Za-z0-9._/-]+\.prompt\.md")

    for name, path in _CLOUD_WORKFLOWS.items():
        text = _read_text(path)
        executable_text = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        prompt_refs = sorted(set(prompt_ref_re.findall(text)))
        if not prompt_refs:
            errors.append(f"{name} must load at least one .github/prompts/cloud/*.prompt.md file")
        for rel_path in prompt_refs:
            resolved = _REPO_ROOT / rel_path
            if not _is_non_empty_utf8_markdown(resolved):
                errors.append(f"{name} references missing or empty cloud prompt file: {rel_path}")
        for marker in _CLOUD_INLINE_PROMPT_MARKERS[name]:
            if marker in executable_text:
                errors.append(
                    f"{name} still contains known inline model-facing cloud instructions: {marker!r}"
                )

    assert not errors, "\n".join(errors)


def test_fr_prompt_src_02_load_prompt_file_api_contract_exists() -> None:
    func = _require_load_prompt_file()
    signature = inspect.signature(func)
    params = list(signature.parameters.values())

    assert [param.name for param in params] == ["relative_path", "prompts_dir", "required"]
    assert params[0].kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    assert params[1].kind is inspect.Parameter.KEYWORD_ONLY
    assert params[1].default is None
    assert params[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert params[2].default is True


def test_fr_prompt_src_02_load_prompt_file_reads_flat_and_nested_prompt_files(tmp_path: Path) -> None:
    load_prompt_file = _skip_if_load_prompt_file_missing()
    prompts_dir = tmp_path / "prompts"
    _make_prompt_file(prompts_dir / "flat.prompt.md", "flat ok".encode("utf-8"))
    _make_prompt_file(prompts_dir / "runtime" / "nested.prompt.md", "nested ok".encode("utf-8"))

    assert load_prompt_file("flat.prompt.md", prompts_dir=prompts_dir) == "flat ok"
    assert load_prompt_file("runtime/nested.prompt.md", prompts_dir=prompts_dir) == "nested ok"


@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        "   ",
        "/absolute.prompt.md",
        # Repository Prompt path は OS にかかわらず POSIX `/` 区切りだけを許可する。
        r"C:\\absolute.prompt.md",
        r"runtime\\nested.prompt.md",
        "./flat.prompt.md",
        "../escape.prompt.md",
        "runtime/../flat.prompt.md",
        ".",
        "..",
    ],
)
def test_fr_prompt_src_02_load_prompt_file_rejects_unsafe_paths(
    tmp_path: Path, relative_path: str
) -> None:
    load_prompt_file = _skip_if_load_prompt_file_missing()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    with pytest.raises(ValueError):
        load_prompt_file(relative_path, prompts_dir=prompts_dir)


def test_fr_prompt_src_02_load_prompt_file_rejects_symlink_escape(tmp_path: Path) -> None:
    load_prompt_file = _skip_if_load_prompt_file_missing()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    outside = _make_prompt_file(tmp_path / "outside.prompt.md", b"outside")
    link = prompts_dir / "runtime" / "escape.prompt.md"
    link.parent.mkdir(parents=True, exist_ok=True)

    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation is unavailable in this environment: {exc}")

    with pytest.raises(ValueError):
        load_prompt_file("runtime/escape.prompt.md", prompts_dir=prompts_dir)


@pytest.mark.skipif(os.name != "nt", reason="NTFS junctions are Windows-specific")
def test_fr_prompt_src_02_load_prompt_file_rejects_junction_escape(tmp_path: Path) -> None:
    load_prompt_file = _skip_if_load_prompt_file_missing()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    outside_dir = tmp_path / "outside"
    _make_prompt_file(outside_dir / "escape.prompt.md", b"outside")
    junction = prompts_dir / "runtime"

    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(outside_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip(
            "NTFS junction creation is unavailable: "
            f"{(completed.stderr or completed.stdout).strip()}"
        )

    with pytest.raises(ValueError):
        load_prompt_file("runtime/escape.prompt.md", prompts_dir=prompts_dir)


def test_fr_prompt_src_02_load_prompt_file_missing_empty_and_invalid_utf8_fail_closed(
    tmp_path: Path,
) -> None:
    load_prompt_file = _skip_if_load_prompt_file_missing()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    _make_prompt_file(prompts_dir / "zero-byte.prompt.md", b"")
    _make_prompt_file(prompts_dir / "empty.prompt.md", b"   \n")
    _make_prompt_file(prompts_dir / "invalid.prompt.md", b"\xff\xfe\x00")

    with pytest.raises(FileNotFoundError):
        load_prompt_file("missing.prompt.md", prompts_dir=prompts_dir)
    with pytest.raises(ValueError):
        load_prompt_file("zero-byte.prompt.md", prompts_dir=prompts_dir)
    with pytest.raises(ValueError):
        load_prompt_file("empty.prompt.md", prompts_dir=prompts_dir)
    with pytest.raises((UnicodeDecodeError, ValueError)):
        load_prompt_file("invalid.prompt.md", prompts_dir=prompts_dir)


def test_fr_prompt_src_02_load_prompt_file_required_false_returns_empty_only_for_missing(
    tmp_path: Path,
) -> None:
    load_prompt_file = _skip_if_load_prompt_file_missing()
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    _make_prompt_file(prompts_dir / "empty.prompt.md", b"")
    _make_prompt_file(prompts_dir / "invalid.prompt.md", b"\xff")

    assert load_prompt_file("missing.prompt.md", prompts_dir=prompts_dir, required=False) == ""

    with pytest.raises(ValueError):
        load_prompt_file("empty.prompt.md", prompts_dir=prompts_dir, required=False)
    with pytest.raises((UnicodeDecodeError, ValueError)):
        load_prompt_file("invalid.prompt.md", prompts_dir=prompts_dir, required=False)


def test_fr_prompt_src_02_existing_load_prompt_flat_compatibility_is_preserved(
    tmp_path: Path,
) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    _make_prompt_file(prompts_dir / "Agent.prompt.md", "flat compatibility".encode("utf-8"))

    assert prompt_loader.load_prompt("Agent", prompts_dir=prompts_dir) == "flat compatibility"
    assert prompt_loader.load_prompt("Missing", prompts_dir=prompts_dir) == ""
    assert prompt_loader.load_prompt("", prompts_dir=prompts_dir) == ""