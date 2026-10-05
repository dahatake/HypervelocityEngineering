"""FR-PROMPT-SRC-03 の Prompt デバッグ用リファレンス契約。"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

from hve.prompt_loader import load_prompt_file


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SYNC_PATH = _REPO_ROOT / "users-guide" / "prompt-reference" / "sync.py"
_REFERENCE_ROOT = _SYNC_PATH.parent
_COPY_ROOT = _REFERENCE_ROOT / "copies"
_REQUIREMENTS = _REPO_ROOT / "hve-dev" / "requirement-definition.md"
_MAPPING = _REPO_ROOT / "hve-dev" / "requirement-test-mapping.md"
_FEATURE_INVENTORY = _REPO_ROOT / "hve-dev" / "hve-feature-inventory.csv"

_REMOVED_WORKIQ_SOURCE_PATHS = (
    "runtime/workiq/context-injection.prompt.md",
    "runtime/workiq/review-task.prompt.md",
    "runtime/workiq/qa-task.prompt.md",
    "runtime/workiq/km-task.prompt.md",
    "runtime/workiq/role.prompt.md",
    "runtime/workiq/output-schema.prompt.md",
    "runtime/workiq/fewshot.prompt.md",
    "runtime/workiq/akm-ingest.prompt.md",
    "runtime/workiq/akm-verify-update.prompt.md",
    "runtime/workiq/ard-usecase.prompt.md",
)


def _load_sync_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_prompt_reference_sync_contract", _SYNC_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, heading: str, next_heading_prefix: str) -> str:
    assert heading in text, f"missing heading: {heading}"
    tail = text.split(heading, 1)[1]
    return tail.split(next_heading_prefix, 1)[0]


def test_fr_prompt_src_03_is_registered_in_requirement_mapping_and_inventory() -> None:
    requirement_text = _read(_REQUIREMENTS)
    mapping_text = _read(_MAPPING)
    feature_inventory = _read(_FEATURE_INVENTORY)

    assert len(re.findall(r"^- \*\*FR-PROMPT-SRC-03\*\*:", requirement_text, re.MULTILINE)) == 1
    assert len(re.findall(r"^### FR-PROMPT-SRC-03\b", mapping_text, re.MULTILINE)) == 1
    assert len(
        re.findall(
            r"^FR,FR-PROMPT-SRC-03,active-or-described,",
            feature_inventory,
            re.MULTILINE,
        )
    ) == 1


def test_checked_in_reference_tree_matches_sync_contract() -> None:
    sync = _load_sync_module()
    expected_copies, expected_composed, expected_catalog = sync._build_expected()

    errors = sync._check(expected_copies, expected_composed, expected_catalog)

    assert not errors, "\n".join(errors)


def test_every_mirror_matches_runtime_loader_text() -> None:
    sync = _load_sync_module()
    source_files = sync._source_files()
    usage, _registry_stats = sync._usage_inventory(source_files)
    expected_relatives = {
        source.relative_to(sync.SOURCE_ROOT).as_posix()
        for source in source_files
        if sync._should_copy(
            relative := source.relative_to(sync.SOURCE_ROOT).as_posix(),
            usage.get(relative, ()),
        )
    }
    actual_relatives = {
        path.relative_to(_COPY_ROOT).as_posix().removesuffix(".txt")
        for path in _COPY_ROOT.rglob("*.prompt.md.txt")
    }
    assert actual_relatives == expected_relatives

    mismatches = []
    for relative in sorted(expected_relatives):
        mirror = _COPY_ROOT / f"{relative}.txt"
        if _read(mirror) != load_prompt_file(relative):
            mismatches.append(relative)
    assert not mismatches, f"mirrors differ from runtime text: {mismatches}"


def test_crlf_source_is_normalized_like_runtime_loader(tmp_path: Path, monkeypatch) -> None:
    sync = _load_sync_module()
    prompts_dir = tmp_path / "prompts"
    prompt_path = prompts_dir / "runtime" / "crlf.prompt.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_bytes(b"first\r\nsecond\r\n")
    monkeypatch.setattr(sync, "SOURCE_ROOT", prompts_dir)

    expected = load_prompt_file(
        "runtime/crlf.prompt.md",
        prompts_dir=prompts_dir,
    ).encode("utf-8")
    copies = sync._expected_copies(
        [prompt_path],
        {"runtime/crlf.prompt.md": ("hve/example.py",)},
    )
    assert copies[Path("runtime/crlf.prompt.md.txt")] == expected == b"first\nsecond\n"


def test_unwired_mirror_exceptions_remain_labeled_unwired(monkeypatch) -> None:
    sync = _load_sync_module()
    source_files = sync._source_files()
    usage, registry_stats = sync._usage_inventory(source_files)
    composed = sync._expected_composed_workiq()

    wired_exceptions = {
        relative: usage[relative]
        for relative in sync.MIRROR_WHILE_UNWIRED
        if usage.get(relative)
    }
    assert not wired_exceptions, (
        f"wired Prompts must be removed from MIRROR_WHILE_UNWIRED: {wired_exceptions}"
    )

    relative = next(
        source.relative_to(sync.SOURCE_ROOT).as_posix()
        for source in source_files
        if source.relative_to(sync.SOURCE_ROOT).as_posix() not in sync.LOADED_ONLY
    )
    monkeypatch.setattr(sync, "MIRROR_WHILE_UNWIRED", frozenset({relative}))

    for relative in sync.MIRROR_WHILE_UNWIRED:
        consumers: tuple[str, ...] = ()
        assert sync._status(relative, consumers) == "未結線"
        assert sync._should_copy(relative, consumers)
        unwired_usage = {**usage, relative: consumers}
        catalog = sync._render_catalog(
            source_files,
            unwired_usage,
            registry_stats,
            composed,
        )
        copy_relative = sync._copy_relative_path(Path(relative)).as_posix()
        assert re.search(
            rf"^\| 未結線 \| .*{re.escape(relative)}.*copies/{re.escape(copy_relative)}.*\|",
            catalog,
            re.MULTILINE,
        )


def test_fr_kd_10_workiq_composed_references_are_removed() -> None:
    assert not list((_REFERENCE_ROOT / "composed").glob("*.prompt.txt"))
    for relative in _REMOVED_WORKIQ_SOURCE_PATHS:
        assert not (_COPY_ROOT / f"{relative}.txt").exists()
    for name in ("common", "qa", "knowledge", "research", "repair"):
        relative = f"runtime/knowledge-discovery/{name}.prompt.md"
        assert _read(_COPY_ROOT / f"{relative}.txt") == load_prompt_file(relative)


def test_root_readme_prompt_section_links_to_debug_reference() -> None:
    root_readme = _read(_REPO_ROOT / "README.md")
    prompt_section = _section(root_readme, "### Prompt の見方", "\n## 技術アーキテクチャ")

    assert "users-guide/prompt-reference/README.md" in prompt_section
    for required_text in ("正本", "非規範", "手動デバッグ"):
        assert required_text in prompt_section
    assert (_REFERENCE_ROOT / "README.md").is_file()


def test_prompt_reference_explains_manual_debug_surfaces_and_boundary() -> None:
    guide = _read(_REFERENCE_ROOT / "README.md")
    manual_section = _section(
        guide,
        "## 手動デバッグでの使い分け",
        "\n## メインタスク Prompt の合成順",
    )

    for required_text in (
        "GitHub Copilot",
        "Microsoft 365 Copilot Chat",
        "知識探索",
        "placeholder",
        "Tool",
        "出典",
        "Autopilot",
    ):
        assert required_text in manual_section
    assert "最終 payload" in guide
    for required_text in ("実データ", "個人情報", "秘密情報"):
        assert required_text in guide


def test_prompt_reference_links_resolve() -> None:
    assert (_REFERENCE_ROOT / "catalog.md").is_file()
    assert (_REPO_ROOT / "users-guide" / "prompts" / "README.md").is_file()