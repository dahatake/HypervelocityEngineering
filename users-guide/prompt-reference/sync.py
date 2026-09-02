"""Synchronize and verify the non-canonical users-guide Prompt mirror.

The only Prompt source of truth is ``.github/prompts/**``. This helper catalogs
every source file, copies files referenced by an execution or module-load path
byte-for-byte with an added ``.txt`` suffix, emits three composed Work IQ
templates for manual testing, and regenerates the SHA-256 catalog. ``--check``
performs no writes.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from hashlib import sha256
from pathlib import Path, PurePosixPath
import sys
import tempfile
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / ".github" / "prompts"
REFERENCE_ROOT = Path(__file__).resolve().parent
COPY_ROOT = REFERENCE_ROOT / "copies"
COMPOSED_ROOT = REFERENCE_ROOT / "composed"
CATALOG_PATH = REFERENCE_ROOT / "catalog.md"

CATEGORY_LABELS = {
    "flat": "Agent 本文（flat）",
    "steps": "Step 本文",
    "fanout": "fan-out 追加本文",
    "runtime": "runtime Prompt",
    "cloud": "Cloud 実行指示",
}
CATEGORY_ORDER = ("flat", "steps", "fanout", "runtime", "cloud")
REFERENCE_ROOTS = (
    REPO_ROOT / "hve",
    REPO_ROOT / "hve-dev",
    REPO_ROOT / "tools",
    REPO_ROOT / ".github" / "scripts",
    REPO_ROOT / ".github" / "workflows",
)
REFERENCE_SUFFIXES = frozenset({".py", ".ps1", ".sh", ".yml", ".yaml"})
REFERENCE_EXCLUDED_PARTS = frozenset({"__pycache__", ".pytest_cache", "tests", "vendor"})

# These files are loaded into hve.prompts module constants, but no production
# code passes those constants to a model as of 2026-08-27. Keep this explicit
# because path-reference scanning alone can prove loading, not downstream use.
LOADED_ONLY_SYMBOLS = {
    "runtime/qa/merge-save.prompt.md": "QA_MERGE_SAVE_PROMPT",
    "runtime/qa/overengineering-ban.prompt.md": "OVERENGINEERING_BAN_TEXT_QA",
    "runtime/qa/questionnaire-depth-rules.prompt.md": "QUESTIONNAIRE_DEPTH_RULES_TEXT",
    "runtime/shared/overengineering-ban.prompt.md": "OVERENGINEERING_BAN_TEXT",
}
LOADED_ONLY = frozenset(LOADED_ONLY_SYMBOLS)

# Runtime wiring is intentionally owned by T24. Mirror this fixed recovery
# Prompt while it is unwired without misreporting it as a production consumer.
# Once wired, the normal consumer-based rule keeps the copy eligible.
MIRROR_WHILE_UNWIRED = frozenset(
    {
        "runtime/runner/resume-recovery.prompt.md",
    }
)

WORKIQ_COMPOSITIONS = {
    "workiq-qa.prompt.txt": (
        "runtime/workiq/qa-task.prompt.md",
        "質問一覧",
    ),
    "workiq-km.prompt.txt": (
        "runtime/workiq/km-task.prompt.md",
        "Knowledge 項目",
    ),
    "workiq-review.prompt.txt": (
        "runtime/workiq/review-task.prompt.md",
        "ドキュメント概要",
    ),
}
WORKIQ_SHARED_COMPONENTS = (
    "runtime/workiq/role.prompt.md",
    "runtime/workiq/output-schema.prompt.md",
    "runtime/workiq/fewshot.prompt.md",
)


def _copy_relative_path(source_relative: Path) -> Path:
    if not source_relative.name.endswith(".prompt.md"):
        raise ValueError(f"Unexpected Prompt filename: {source_relative}")
    return source_relative.with_name(source_relative.name + ".txt")


def _source_files() -> list[Path]:
    if not SOURCE_ROOT.is_dir():
        raise RuntimeError(f"Prompt source directory not found: {SOURCE_ROOT}")

    files = sorted(
        SOURCE_ROOT.rglob("*.prompt.md"),
        key=lambda path: path.relative_to(SOURCE_ROOT).as_posix(),
    )
    if not files:
        raise RuntimeError(f"No Prompt source files found under: {SOURCE_ROOT}")

    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(SOURCE_ROOT.resolve()):
            raise RuntimeError(f"Prompt source must not be a symlink or escape its root: {path}")
        data = path.read_bytes()
        if not data.strip():
            raise RuntimeError(f"Prompt source must not be empty: {path}")
        data.decode("utf-8")
    return files


def _prompt_relative_path(repository_path: str) -> str:
    path = PurePosixPath(repository_path)
    prefix = PurePosixPath(".github/prompts")
    try:
        return path.relative_to(prefix).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"Registry Prompt path is outside .github/prompts: {path}") from exc


def _registry_usage() -> tuple[dict[str, set[str]], dict[str, int]]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from hve.workflow_registry import list_workflows

    usage: dict[str, set[str]] = defaultdict(set)
    stats = {"agent_assignments": 0, "step_body_references": 0, "fanout_references": 0}

    for workflow in list_workflows():
        for step in workflow.steps:
            if step.is_container:
                continue
            consumer = f"workflow:{workflow.id}/step:{step.id}"
            if step.custom_agent:
                usage[f"{step.custom_agent}.prompt.md"].add(consumer)
                stats["agent_assignments"] += 1
            if step.body_template_path:
                usage[_prompt_relative_path(step.body_template_path)].add(consumer)
                stats["step_body_references"] += 1
            if step.additional_prompt_template_path:
                usage[_prompt_relative_path(step.additional_prompt_template_path)].add(consumer)
                stats["fanout_references"] += 1
    return usage, stats


def _reference_texts() -> dict[str, str]:
    texts: dict[str, str] = {}
    for root in REFERENCE_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in REFERENCE_SUFFIXES:
                continue
            relative = path.relative_to(REPO_ROOT)
            if REFERENCE_EXCLUDED_PARTS.intersection(relative.parts):
                continue
            texts[relative.as_posix()] = path.read_text(encoding="utf-8-sig")
    return texts


def _production_symbol_consumers(
    symbol: str, reference_texts: dict[str, str]
) -> tuple[str, ...]:
    consumers: list[str] = []
    for relative, text in reference_texts.items():
        if not relative.startswith("hve/") or not relative.endswith(".py"):
            continue
        if relative == "hve/prompts.py":
            continue
        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError as exc:
            raise RuntimeError(f"Cannot parse production Python source: {relative}") from exc

        imported_names = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and (node.module or "").endswith("prompts")
            for alias in node.names
            if alias.name == symbol
        }
        imported_use = any(
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in imported_names
            for node in ast.walk(tree)
        )
        attribute_use = any(
            isinstance(node, ast.Attribute) and node.attr == symbol
            for node in ast.walk(tree)
        )
        if imported_use or attribute_use:
            consumers.append(relative)
    return tuple(sorted(consumers))


def _usage_inventory(
    source_files: list[Path],
) -> tuple[dict[str, tuple[str, ...]], dict[str, int]]:
    usage, stats = _registry_usage()
    reference_texts = _reference_texts()

    for source in source_files:
        relative = source.relative_to(SOURCE_ROOT).as_posix()
        category = "flat" if "/" not in relative else relative.split("/", 1)[0]
        if category not in {"runtime", "cloud"}:
            continue

        dynamic_gui_name = ""
        if relative.startswith("runtime/gui/"):
            dynamic_gui_name = Path(relative).name.removesuffix(".prompt.md")

        for consumer, text in reference_texts.items():
            direct_reference = relative in text or f".github/prompts/{relative}" in text
            dynamic_reference = bool(dynamic_gui_name) and (
                f'"{dynamic_gui_name}"' in text or f"'{dynamic_gui_name}'" in text
            )
            if direct_reference or dynamic_reference:
                usage[relative].add(consumer)

    source_relpaths = {
        path.relative_to(SOURCE_ROOT).as_posix() for path in source_files
    }
    unknown_references = sorted(set(usage) - source_relpaths)
    if unknown_references:
        raise RuntimeError(f"Prompt references point to missing source files: {unknown_references}")

    missing_loaded_only = sorted(LOADED_ONLY - source_relpaths)
    if missing_loaded_only:
        raise RuntimeError(f"Known load-only Prompt file is missing: {missing_loaded_only}")
    missing_mirrored_unwired = sorted(MIRROR_WHILE_UNWIRED - source_relpaths)
    if missing_mirrored_unwired:
        raise RuntimeError(
            "Known unwired mirrored Prompt file is missing: "
            f"{missing_mirrored_unwired}"
        )
    for relative in LOADED_ONLY:
        if not usage.get(relative):
            raise RuntimeError(f"Load-only Prompt no longer has a loader reference: {relative}")
        symbol_consumers = _production_symbol_consumers(
            LOADED_ONLY_SYMBOLS[relative], reference_texts
        )
        if symbol_consumers:
            raise RuntimeError(
                f"Load-only Prompt is now consumed by production code: {relative} -> "
                + ", ".join(symbol_consumers)
            )

    return {
        relative: tuple(sorted(consumers))
        for relative, consumers in usage.items()
    }, stats


def _status(relative: str, consumers: tuple[str, ...]) -> str:
    if relative in LOADED_ONLY:
        return "ロードのみ（送信参照なし）"
    if consumers:
        return "結線済み"
    return "未結線"


def _should_copy(relative: str, consumers: tuple[str, ...]) -> bool:
    return _status(relative, consumers) != "未結線" or relative in MIRROR_WHILE_UNWIRED


def _expected_copies(
    source_files: list[Path], usage: dict[str, tuple[str, ...]]
) -> dict[Path, bytes]:
    return {
        _copy_relative_path(source.relative_to(SOURCE_ROOT)): source.read_bytes()
        for source in source_files
        if _should_copy(
            relative := source.relative_to(SOURCE_ROOT).as_posix(),
            usage.get(relative, ()),
        )
    }


def _read_prompt(relative: str) -> str:
    return (SOURCE_ROOT / PurePosixPath(relative)).read_text(encoding="utf-8")


def _expected_composed_workiq() -> dict[Path, bytes]:
    role, output_schema, fewshot = (
        _read_prompt(relative) for relative in WORKIQ_SHARED_COMPONENTS
    )
    composed: dict[Path, bytes] = {}
    for filename, (task_path, target_label) in WORKIQ_COMPOSITIONS.items():
        task_directive = _read_prompt(task_path)
        text = (
            role
            + output_schema
            + fewshot
            + "\n"
            + task_directive
            + f"\n\n### {target_label}\n"
            + "{target_content}\n"
        )
        composed[Path(filename)] = text.encode("utf-8")
    return composed


def _markdown_href(relative: str) -> str:
    return quote(relative, safe="/._-")


def _render_catalog(
    source_files: list[Path],
    usage: dict[str, tuple[str, ...]],
    registry_stats: dict[str, int],
    composed: dict[Path, bytes],
) -> str:
    source_relpaths = [path.relative_to(SOURCE_ROOT) for path in source_files]
    categories: dict[str, list[Path]] = defaultdict(list)
    for relative in source_relpaths:
        category = "flat" if len(relative.parts) == 1 else relative.parts[0]
        categories[category].append(relative)

    unexpected_categories = sorted(set(categories) - set(CATEGORY_ORDER))
    if unexpected_categories:
        raise RuntimeError(f"Unexpected Prompt categories: {unexpected_categories}")

    status_counts: dict[str, int] = defaultdict(int)
    for relative in source_relpaths:
        rel = relative.as_posix()
        status_counts[_status(rel, usage.get(rel, ()))] += 1
    copy_count = sum(
        _should_copy(relative.as_posix(), usage.get(relative.as_posix(), ()))
        for relative in source_relpaths
    )

    lines = [
        "# HVE Prompt 正本・コピー一覧",
        "",
        "← [HVE Prompt 全文リファレンス](./README.md)",
        "",
        "---",
        "",
        "> [!IMPORTANT]",
        "> この一覧と `copies/**` は `.github/prompts/**/*.prompt.md` から作成した非規範コピーです。編集先は正本だけです。",
        "> コピーは Markdown 検索への重複登録を避けるため、正本の相対パス末尾に `.txt` を付けています。本文 bytes は正本と同一です。",
        "",
        f"- Prompt 正本: **{len(source_files)} 件**",
        f"- 閲覧用コピー: **{copy_count} 件**",
        f"- model-facing / Cloud 実行経路に結線済み: **{status_counts['結線済み']} 件**",
        f"- module load のみ（送信参照なし）: **{status_counts['ロードのみ（送信参照なし）']} 件**",
        f"- 未結線: **{status_counts['未結線']} 件**",
        f"- Registry 参照: Agent 割当 **{registry_stats['agent_assignments']}** / Step 本文 **{registry_stats['step_body_references']}** / fan-out **{registry_stats['fanout_references']}**",
        "- SHA-256: 正本と byte-for-byte コピーに共通する、小文字 64 桁 hex",
        "- 参照元: Agent / Step / fan-out は Registry 割当、runtime / Cloud は固定本文を直接読む loader / Workflow。完全な downstream call graph ではありません",
        "- 再生成・検証: [`sync.py`](./sync.py)",
        "",
    ]

    for category in CATEGORY_ORDER:
        paths = categories[category]
        lines.extend(
            [
                f"## {CATEGORY_LABELS[category]}（{len(paths)} 件）",
                "",
                "| 状態（静的判定） | 正本 | 閲覧用コピー | 参照元（Registry / loader） | SHA-256 |",
                "|---|---|---|---|---|",
            ]
        )
        for relative in paths:
            rel = relative.as_posix()
            copy_rel = _copy_relative_path(relative).as_posix()
            consumers = usage.get(rel, ())
            status = _status(rel, consumers)
            usage_cell = "<br>".join(f"`{consumer}`" for consumer in consumers) or "—"
            digest = sha256((SOURCE_ROOT / relative).read_bytes()).hexdigest()
            copy_cell = (
                f"[`copies/{copy_rel}`](copies/{_markdown_href(copy_rel)})"
                if _should_copy(rel, consumers)
                else "—"
            )
            lines.append(
                f"| {status} | "
                f"[`{rel}`](../../.github/prompts/{_markdown_href(rel)}) | "
                f"{copy_cell} | "
                f"{usage_cell} | `{digest}` |"
            )
        lines.append("")

    lines.extend(
        [
            "## Work IQ 合成済みデバッグ用 Prompt（3 件）",
            "",
            "`hve/workiq.py::_compose_default_workiq_prompt()` と同じ順序・区切りで生成した既定テンプレートです。`config_override` を指定した実行には一致しません。",
            "",
            "| 用途 | 合成済みテンプレート | 構成元 | SHA-256 |",
            "|---|---|---|---|",
        ]
    )
    for filename, (task_path, _target_label) in WORKIQ_COMPOSITIONS.items():
        components = (*WORKIQ_SHARED_COMPONENTS, task_path)
        component_cell = "<br>".join(f"`{component}`" for component in components)
        data = composed[Path(filename)]
        lines.append(
            f"| `{filename.removesuffix('.prompt.txt')}` | "
            f"[`composed/{filename}`](composed/{_markdown_href(filename)}) | "
            f"{component_cell} | `{sha256(data).hexdigest()}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _tree_files(root: Path) -> tuple[dict[Path, bytes], list[str]]:
    errors: list[str] = []
    if not root.exists():
        return {}, errors
    if root.is_symlink():
        return {}, [f"generated root must not be a symlink: {root}"]

    files: dict[Path, bytes] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            errors.append(f"generated tree must not contain a symlink: {path}")
        elif path.is_file():
            files[path.relative_to(root)] = path.read_bytes()
    return files, errors


def _check_tree(root: Path, expected: dict[Path, bytes]) -> list[str]:
    actual, errors = _tree_files(root)
    expected_paths = set(expected)
    actual_paths = set(actual)
    for relative in sorted(expected_paths - actual_paths, key=lambda path: path.as_posix()):
        errors.append(f"missing generated file: {root.name}/{relative.as_posix()}")
    for relative in sorted(actual_paths - expected_paths, key=lambda path: path.as_posix()):
        errors.append(f"unexpected generated file: {root.name}/{relative.as_posix()}")
    for relative in sorted(expected_paths & actual_paths, key=lambda path: path.as_posix()):
        if actual[relative] != expected[relative]:
            errors.append(f"byte mismatch: {root.name}/{relative.as_posix()}")
    return errors


def _check(
    expected_copies: dict[Path, bytes],
    expected_composed: dict[Path, bytes],
    expected_catalog: str,
) -> list[str]:
    errors = _check_tree(COPY_ROOT, expected_copies)
    errors.extend(_check_tree(COMPOSED_ROOT, expected_composed))

    expected_catalog_bytes = expected_catalog.encode("utf-8")
    if not CATALOG_PATH.is_file():
        errors.append("missing catalog.md")
    elif CATALOG_PATH.read_bytes() != expected_catalog_bytes:
        errors.append("catalog.md is stale or has different line endings")
    return errors


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _sync_tree(
    root: Path,
    expected: dict[Path, bytes],
    *,
    generated_suffix: str,
) -> None:
    actual, errors = _tree_files(root)
    if errors:
        raise RuntimeError("\n".join(errors))

    stale = set(actual) - set(expected)
    unsafe_stale = sorted(
        (path for path in stale if not path.name.endswith(generated_suffix)),
        key=lambda path: path.as_posix(),
    )
    if unsafe_stale:
        rendered = ", ".join(path.as_posix() for path in unsafe_stale)
        raise RuntimeError(f"Refusing to delete non-generated files under {root}: {rendered}")

    root.mkdir(parents=True, exist_ok=True)
    for relative, content in expected.items():
        target = root / relative
        if target.is_symlink():
            raise RuntimeError(f"Generated target must not be a symlink: {target}")
        if not target.is_file() or target.read_bytes() != content:
            _atomic_write(target, content)

    for relative in stale:
        (root / relative).unlink()
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()), reverse=True
    ):
        if not any(directory.iterdir()):
            directory.rmdir()


def _build_expected() -> tuple[dict[Path, bytes], dict[Path, bytes], str]:
    source_files = _source_files()
    usage, registry_stats = _usage_inventory(source_files)
    copies = _expected_copies(source_files, usage)
    composed = _expected_composed_workiq()
    catalog = _render_catalog(source_files, usage, registry_stats, composed)
    return copies, composed, catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the mirror and catalog without modifying files.",
    )
    args = parser.parse_args()

    expected_copies, expected_composed, expected_catalog = _build_expected()
    if args.check:
        errors = _check(expected_copies, expected_composed, expected_catalog)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print(
            f"PASS: {len(expected_copies)} Prompt copies, "
            f"{len(expected_composed)} composed Work IQ templates, and catalog match"
        )
        return 0

    _sync_tree(COPY_ROOT, expected_copies, generated_suffix=".prompt.md.txt")
    _sync_tree(COMPOSED_ROOT, expected_composed, generated_suffix=".prompt.txt")
    if CATALOG_PATH.is_symlink():
        raise RuntimeError(f"Catalog must not be a symlink: {CATALOG_PATH}")
    _atomic_write(CATALOG_PATH, expected_catalog.encode("utf-8"))

    # Re-read the source after writing so a concurrent Prompt change cannot be
    # reported as a successful synchronized snapshot.
    fresh_copies, fresh_composed, fresh_catalog = _build_expected()
    errors = _check(fresh_copies, fresh_composed, fresh_catalog)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(
        f"COPIED={len(fresh_copies)} COMPOSED={len(fresh_composed)} "
        "STATUS=verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
