"""FR-MAINT-12: self-test evidence routing, Git selection and safe cleanup.

Offline contracts only: no real GUI, Copilot, network or repository run cleanup.
README checks cover concepts, not exact prose. Git checks use only a copied
.gitignore in tmp_path; cleanup exercises the real conftest generator there.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_PROMPT_DIR = _ROOT / "tests/prompt-version"
_PROMPTS = (
    "01-request-contract.md",
    "02-plan-and-approval-gate.md",
    "03-multi-workflow-order.md",
    "04-input-alias.md",
    "05-gui-settings-reuse.md",
    "06-agent-skill-behavior.md",
    "07-docs-coverage.md",
    "08-e2e-smoke.md",
    "09-full-system-test.md",
)
_FULL = ("[cli]SystemTest - Full.txt", "[gui]SystemTest - Full.txt")
# Matching the closing fence length avoids treating nested text/JSON examples
# (notably 06 and 09) as separate controller instructions.
_PASTE_BLOCK = re.compile(
    r"^(?P<fence>`{3,}|~{3,})(?:markdown|md)[ \t]*\n"
    r"(?P<body>.*?)^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_EVIDENCE_ROOT = re.compile(r"(?<![\w/])tests/run/[^/\s`]+/[^/\s`]+/")
# Reject the old controller destinations, not legitimate lane-local work/.
_OLD_CONTROLLER_ROOT = re.compile(
    r"(?<![\w/])/?work/run/[^/\s`]+/Issue-[^/\s`]+/"
)


@pytest.fixture(autouse=True)
def _remove_leaked_run_artifacts():
    """Override repo cleanup here: every mutable fixture is under tmp_path.

    Otherwise the inherited autouse fixture could remove a concurrent real run
    while these read-only document/Git contracts are being executed.
    """


def _read(path: Path) -> str:
    assert path.is_file(), f"FR-MAINT-12: missing document: {path}"
    return path.read_text(encoding="utf-8-sig")


def _assert_route(text: str, source: Path, target: Path) -> None:
    """Accept repository-relative code paths or document-relative Markdown links."""
    references = [(_ROOT, value) for value in re.findall(r"`([^`\n]+)`", text)]
    references += [
        (source.parent, value)
        for value in re.findall(r"\[[^\]\n]*\]\(([^)\s]+)\)", text)
    ]
    for base, reference in references:
        reference = reference.split("#", 1)[0]
        # Do not resolve arbitrary CLI examples/URLs as Windows filesystem paths.
        if not reference.endswith(".md") or any(c in reference for c in ':"<>|?*'):
            continue
        if (base / reference).resolve() == target.resolve():
            return
    pytest.fail(f"{source.name}: missing route to {target.relative_to(_ROOT)}")


def _assert_evidence_root(text: str, source: Path) -> None:
    assert _EVIDENCE_ROOT.search(text), (
        f"{source.name}: declare tests/run/<run-id>/<task>/ inside the instructions"
    )
    assert not _OLD_CONTROLLER_ROOT.search(text), (
        f"{source.name}: legacy work/run/.../Issue-... controller destination"
    )


@pytest.mark.parametrize("name", _PROMPTS)
def test_each_copyable_prompt_routes_all_evidence_to_tests(name: str):
    path = _PROMPT_DIR / name
    blocks = [match["body"] for match in _PASTE_BLOCK.finditer(_read(path))]
    assert blocks, f"{name}: no copyable Markdown prompt found"
    for block in blocks:
        _assert_evidence_root(block, path)
        _assert_route(block, path, _PROMPT_DIR / "README.md")
        _assert_route(block, path, _ROOT / "tests/README.md")


@pytest.mark.parametrize("name", _FULL)
def test_cli_and_gui_full_route_to_common_evidence_contract(name: str):
    path = _ROOT / "tests" / name
    text = _read(path)
    _assert_evidence_root(text, path)
    _assert_route(text, path, _ROOT / "tests/README.md")


def test_prompt_index_routes_to_common_evidence_contract():
    path = _PROMPT_DIR / "README.md"
    _assert_route(_read(path), path, _ROOT / "tests/README.md")


# Exact identifiers are path/API vocabulary already required by FR-MAINT-12.
# Japanese/English alternatives deliberately avoid prescribing whole sentences.
_README_CONCEPTS = (
    ("request", r"\brequests?\b"),
    ("plan", r"\bplans?\b"),
    ("stdout", r"\bstdout\b"),
    ("stderr", r"\bstderr\b"),
    ("checkpoint", r"\bcheckpoints?\b"),
    ("review", r"\breviews?\b"),
    ("manifest", r"\bmanifests?\b"),
    ("lanes", r"\blanes/"),
    ("parent run", r"親|\bparent\b"),
    ("before launch", r"(?:起動|開始|実行)(?:する)?前|\bbefore\b"),
    ("allocate parent", r"確保|作成|\b(?:creat\w*|allocat\w*)\b"),
    ("cleanup", r"\bcleanup\b|クリーンアップ"),
    ("secrets", r"秘密|機微|\bsecrets?\b"),
    ("new run / attempt", r"新(?:しい|規)?\s*(?:run|ラン)|\bnew\s+(?:run|attempt)\b"),
    ("retention", r"保持|保存|\b(?:retain\w*|preserv\w*|keep)\b"),
    ("private directory", r"\bprivate/"),
    ("scratch fixtures", r"\bfixtures/"),
    ("temporary directories", r"\*-temp"),
)


@pytest.mark.parametrize(("concept", "pattern"), _README_CONCEPTS)
def test_common_readme_covers_evidence_lifecycle(concept: str, pattern: str):
    text = _read(_ROOT / "tests/README.md")
    # ASCII word boundaries also accept Japanese prose such as "stdoutを保存".
    assert re.search(pattern, text, re.IGNORECASE | re.ASCII), (
        f"tests/README.md: missing concept {concept!r} (accepted pattern: {pattern})"
    )


def test_common_readme_declares_run_root_and_safe_settings_snapshot():
    path = _ROOT / "tests/README.md"
    text = _read(path)
    _assert_evidence_root(text, path)
    assert "redacted.settings.json" in text


def _assert_cleanup_gate(text: str) -> None:
    section = re.search(r"^## cleanup\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert section is not None, "cleanup section required"
    body = section[1]
    assert re.search(r"退避.*検証.*後.*(?:削除|cleanup)", body, re.S)
    assert re.search(r"(?:欠損|検証不能).*停止", body, re.S)


def test_common_readme_requires_evidence_verification_before_cleanup():
    _assert_cleanup_gate(_read(_ROOT / "tests/README.md"))


def test_common_readme_requires_reference_validation_before_completion():
    text = _read(_ROOT / "tests/README.md")
    assert re.search(r"cleanup の有無.*完了報告前", text)
    assert re.search(r"参照先.*存在.*相対リンク.*hash", text)


def test_full_system_prompt_requires_approved_host_measurement_method():
    text = _read(_PROMPT_DIR / "09-full-system-test.md")
    for term in ("測定窓", "サンプル数", "測定間隔", "集約規則", "測定時点"):
        assert term in text
    assert re.search(r"上限.*明示承認", text, re.S)


@pytest.mark.parametrize("missing", ("退避", "検証", "後", "欠損", "停止"))
def test_cleanup_gate_rejects_missing_obligations(missing: str):
    text = "## cleanup\n証跡を退避して検証した後に削除。欠損なら停止。\n"
    _assert_cleanup_gate(text)
    with pytest.raises(AssertionError):
        _assert_cleanup_gate(text.replace(missing, ""))


def test_markdown_route_does_not_fall_back_to_repository_root():
    source = _PROMPT_DIR / _PROMPTS[0]
    with pytest.raises(pytest.fail.Exception):
        _assert_route("[共通](tests/README.md)", source, _ROOT / "tests/README.md")
    _assert_route("[共通](../README.md)", source, _ROOT / "tests/README.md")


def test_git_selects_safe_evidence_without_unignoring_secrets(tmp_path: Path):
    """Test Git semantics, not merely the presence/order of .gitignore strings."""
    git = shutil.which("git")
    assert git is not None, "Git is required to validate the ignore contract"
    repo = tmp_path / "git-contract"
    repo.mkdir()
    template = tmp_path / "empty-git-template"
    template.mkdir()
    shutil.copyfile(_ROOT / ".gitignore", repo / ".gitignore")
    # No inherited worktree/index or user/global ignore configuration.
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    env.update(
        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
    )
    command = [git, "-c", f"core.excludesFile={os.devnull}"]
    subprocess.run(
        [*command, "init", "--quiet", f"--template={template}"],
        cwd=repo, env=env, check=True, capture_output=True, timeout=15,
    )

    task = "tests/run/id/task"
    safe = {
        f"{task}/artifacts/report.{ext}"
        for ext in ("md", "json", "log", "xml", "png")
    }
    safe.update({
        f"{task}/pytest-result.xml",  # task root, not the repository root
        f"{task}/artifacts/settings/redacted.settings.json",
        f"{task}/artifacts/screenshots/CASE-001/manifest.json",
        f"{task}/artifacts/evidence/CASE-001/stdout.log",
        f"{task}/artifacts/evidence/CASE-001/stderr.log",
    })
    # Prompt 01 already requires these filenames; do not rename its evidence.
    prompt = _read(_PROMPT_DIR / "01-request-contract.md")
    for name in ("c1-asdw-safe-step.txt", "c1-asdw-token-blocker.txt"):
        assert f"artifacts/{name}" in prompt
        safe.add(f"{task}/artifacts/{name}")
    safe.add(f"{task}/artifacts/evidence/CASE-001/result.txt")
    for ext in ("py", "ps1", "sh"):
        safe.update({
            f"{task}/artifacts/scripts/driver.{ext}",
            f"{task}/artifacts/scripts/CASE-001/helper.{ext}",
        })
    ignored = {"hve/.settings.txt", "tests/unrelated.log", "tests/unrelated.tmp"}
    # Outside the run/task allowlist, retain the original .txt selection rules.
    safe.update({"tests/unrelated.txt", "tests/run/id/result.txt"})
    # No new extension exceptions at task root or arbitrary helper locations.
    ignored.update({
        f"{task}/result.txt", f"{task}/evidence/result.txt",
    })
    for ext in ("py", "ps1", "sh"):
        ignored.update(f"{task}/{relative}.{ext}" for relative in (
            "driver", "scripts/driver", "artifacts/driver",
            "artifacts/helpers/driver", "artifacts/nested/scripts/driver",
        ))
    # These had real ignore rules before the evidence directory reopening.
    # Allowed suffixes must not rescue environment/package/build cache contents.
    excluded_dirs = (
        "env", "venv", "ENV", "env.bak", "venv.bak", ".venv",
        ".eggs", "eggs", "develop-eggs", "package.egg-info", "build", "dist",
        "downloads", "parts", "sdist", "var", "wheels", "share/python-wheels",
        "target", "bin", "Bin", "obj", "Obj", "bld", "debug", "Debug",
        "DebugPublic", "release", "Release", "Releases", "DebugPS", "ReleasePS",
        "x64", "x86", "Win32", "ARM", "ARM64", "ipch", ".artifacts",
        "BenchmarkDotNet.Artifacts", "packages", "Packages",
        ".pyre", ".pytype", ".ipynb_checkpoints", ".sass-cache",
        ".webassets-cache", ".scrapy", ".pybuilder", ".pdm-build", ".pixi",
        "__pypackages__", ".vs", "__pycache__", "node_modules",
    )
    for base in (
        task, f"{task}/artifacts", f"{task}/artifacts/nested",
        f"{task}/artifacts/scripts",
    ):
        ignored.update(
            f"{base}/{directory}/{name}"
            for directory in excluded_dirs
            for name in ("report.json", "README.md", "result.txt", "driver.py")
        )
        for directory in ("private", "fixtures", "lanes", "pytest-temp"):
            ignored.update(
                f"{base}/{directory}/{name}"
                for name in (
                    "settings-original.txt", "c1-asdw-token-blocker.txt",
                    "driver.py", "driver.ps1", "driver.sh",
                    "scripts/helper.py", "scripts/helper.ps1", "scripts/helper.sh",
                )
            )
        ignored.update(f"{base}/{name}" for name in (
            ".env", ".env.local", ".env.production",
            "secret.key", "secret.pem", "secret.pfx",
            "hve/.settings.txt", "local.settings.json", "private/settings-original.txt",
            "private/restore.json", "private/report.md", "private/redacted.settings.json",
            "lanes/CASE-001/README.md", "lanes/CASE-001/artifacts/report.log",
            "fixtures/input.json", "fixtures/artifacts/report.md", "pytest-temp/report.md",
            "node_modules/pkg/package.json", ".venv/pyvenv.cfg", "__pycache__/module.pyc",
            ".mypy_cache/3.12/module.data.json", ".pytest_cache/report.json",
            ".ruff_cache/report.json", ".cache/report.json", ".tox/report.json",
            ".nox/report.json", ".hypothesis/report.json", ".mdq/report.json",
            ".cq/report.json", ".hve/report.json", ".toolsearch/report.log",
        ))
    for relative in safe | ignored:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("offline synthetic fixture\n", encoding="utf-8")

    result = subprocess.run(
        [*command, "check-ignore", "--no-index", "--stdin", "-z"],
        input="\0".join(sorted(safe | ignored)) + "\0",
        cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode in (0, 1), result.stderr
    actual = set(filter(None, result.stdout.split("\0")))
    assert actual == ignored, (
        f"safe evidence incorrectly ignored: {sorted(actual & safe)}; "
        f"sensitive/scratch files not ignored: {sorted(ignored - actual)}"
    )


def test_gitignore_has_no_unbounded_tests_exception():
    rules = {
        line.strip().removeprefix("!").lstrip("/")
        for line in _read(_ROOT / ".gitignore").splitlines()
        if line.strip().startswith("!")
    }
    assert not rules.intersection({"tests/**", "tests/**/*", "tests/*"}), (
        "Scope evidence exceptions to tests/run/, not all tests/**"
    )


@pytest.mark.parametrize("interrupted", (False, True), ids=("normal", "interrupted"))
def test_real_cleanup_preserves_existing_quality_run_only_removing_new_fixture_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted: bool,
):
    # Load an isolated copy: never mutate the conftest module used by pytest.
    spec = importlib.util.spec_from_file_location(
        "selftest_cleanup_contract", _ROOT / "hve/tests/conftest.py",
    )
    assert spec is not None and spec.loader is not None
    conftest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conftest)
    fake_repo = tmp_path / "repo"
    fake_file = fake_repo / "hve/tests/conftest.py"
    fake_file.parent.mkdir(parents=True)
    fake_file.touch()
    monkeypatch.setattr(conftest, "__file__", str(fake_file))
    assert isinstance(conftest.__file__, str)
    assert Path(conftest.__file__).resolve().parents[2] == fake_repo.resolve()
    assert fake_repo.resolve().is_relative_to(tmp_path.resolve())

    assert conftest._run_artifact_snapshot(fake_repo) == {
        "work/run": set(), "tests/run": set(),
    }
    shared = fake_repo / "shared.txt"
    shared.write_text("not a run artifact", encoding="utf-8")
    roots = ("work/run", "tests/run")
    for relative in roots:
        report = fake_repo / relative / "quality/task/artifacts/report.md"
        report.parent.mkdir(parents=True)
        report.write_text("preexisting quality evidence", encoding="utf-8")
    assert conftest._run_artifact_snapshot(fake_repo) == {
        relative: {"quality"} for relative in roots
    }

    cleanup = conftest._remove_leaked_run_artifacts.__wrapped__()
    next(cleanup)
    try:
        for relative in roots:
            fixture_run = fake_repo / relative / "fixture-created"
            fixture_run.mkdir()
            (fixture_run / "scratch.json").write_text("{}", encoding="utf-8")
            (fake_repo / relative / "quality/task/artifacts/new.log").write_text(
                "evidence added while pytest is running", encoding="utf-8",
            )
        if interrupted:
            cleanup.close()  # Exercise the generator's finally on interruption.
        else:
            with pytest.raises(StopIteration):
                next(cleanup)
    finally:
        cleanup.close()
    assert shared.read_text(encoding="utf-8") == "not a run artifact"
    for relative in roots:
        assert not (fake_repo / relative / "fixture-created").exists()
        evidence = fake_repo / relative / "quality/task/artifacts"
        assert (evidence / "report.md").read_text(encoding="utf-8") == (
            "preexisting quality evidence"
        )
        assert (evidence / "new.log").read_text(encoding="utf-8") == (
            "evidence added while pytest is running"
        )


def test_documented_case_evidence_paths_resolve_inside_run_outside_lanes(tmp_path: Path):
    """Materialize existing 09 case examples, not a new checkpoint/manifest schema."""
    text = _read(_PROMPT_DIR / "09-full-system-test.md")
    samples = [
        json.loads(body) for body in re.findall(
            r"^```json[ \t]*\n(.*?)^```[ \t]*$", text, re.M | re.S,
        )
    ]
    cases = []
    for sample in samples:
        if "case" in sample:
            cases.append(sample["case"])
        cases.extend(sample.get("cases", []))
    assert cases, "09: no documented case/shard/aggregate examples"
    root = tmp_path / "tests/run/id/task"
    for case in cases:
        paths = [case["request_path"], *case["evidence_paths"]]
        assert any(PurePosixPath(path).name == "manifest.json" for path in paths)
        for relative in paths:
            posix, windows = PurePosixPath(relative), PureWindowsPath(relative)
            assert not posix.is_absolute() and not windows.drive and not windows.root
            assert "\\" not in relative and ":" not in relative
            assert ".." not in posix.parts and posix.parts[0] == "artifacts"
            destination = (root / relative).resolve()
            assert destination.is_relative_to((root / "artifacts").resolve())
            assert not destination.is_relative_to((root / "lanes").resolve())
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("offline path fixture", encoding="utf-8")
            assert destination.is_file()