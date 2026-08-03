"""RED contracts for the HVE protected artifact guard (local checkpoint retention).

local generation checkpoint 後に `src/api` / `src/app` / `src/test` が全消失したり、
成功済み local 出力が欠落した状態で stage / commit / push されることを防ぐ。
"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, List

import pytest

import hve.orchestrator as orchestrator


class _RecordingConsole:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.events: List[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def event(self, message: str) -> None:
        self.events.append(message)


def _write(root: Path, relative: str, content: str = "x") -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_protected_artifact_roots_cover_api_app_and_test() -> None:
    """保護対象は生成物の 3 ルートに固定する。"""
    assert orchestrator.PROTECTED_ARTIFACT_ROOTS == ("src/api", "src/app", "src/test")


def test_manifest_records_relative_posix_paths_per_root(tmp_path) -> None:
    """manifest はルート毎に POSIX 相対パス集合を保持する。"""
    _write(tmp_path, "src/api/svc/handler.py")
    _write(tmp_path, "src/app/index.tsx")
    _write(tmp_path, "src/test/ui/home.spec.ts")

    manifest = orchestrator.capture_protected_artifact_manifest(tmp_path)

    assert manifest["src/api"] == frozenset({"src/api/svc/handler.py"})
    assert manifest["src/app"] == frozenset({"src/app/index.tsx"})
    assert manifest["src/test"] == frozenset({"src/test/ui/home.spec.ts"})


def test_manifest_omits_roots_that_do_not_exist(tmp_path) -> None:
    """未生成のルートは manifest に含めない（保護対象にしない）。"""
    _write(tmp_path, "src/api/svc/handler.py")

    manifest = orchestrator.capture_protected_artifact_manifest(tmp_path)

    assert set(manifest) == {"src/api"}


def test_manifest_is_deterministic(tmp_path) -> None:
    """同一ツリーからは同一 manifest が得られる。"""
    _write(tmp_path, "src/api/a.py")
    _write(tmp_path, "src/api/b.py")

    first = orchestrator.capture_protected_artifact_manifest(tmp_path)
    second = orchestrator.capture_protected_artifact_manifest(tmp_path)

    assert first == second


def test_guard_accepts_unchanged_tree(tmp_path) -> None:
    """変化なしは違反にしない。"""
    _write(tmp_path, "src/api/a.py")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)

    assert orchestrator.check_protected_artifact_regression(baseline, tmp_path) == []


def test_guard_accepts_added_files(tmp_path) -> None:
    """追加生成は違反にしない。"""
    _write(tmp_path, "src/api/a.py")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)
    _write(tmp_path, "src/api/b.py")

    assert orchestrator.check_protected_artifact_regression(baseline, tmp_path) == []


def test_guard_rejects_full_loss_of_a_protected_root(tmp_path) -> None:
    """保護ルートの全消失を拒否する。"""
    _write(tmp_path, "src/app/index.tsx")
    _write(tmp_path, "src/api/a.py")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)
    (tmp_path / "src" / "app" / "index.tsx").unlink()

    errors = orchestrator.check_protected_artifact_regression(baseline, tmp_path)

    assert errors
    assert any("src/app" in error for error in errors)


def test_guard_rejects_missing_previously_successful_output(tmp_path) -> None:
    """成功済み local 出力の欠落を拒否する。"""
    _write(tmp_path, "src/api/a.py")
    _write(tmp_path, "src/api/b.py")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)
    (tmp_path / "src" / "api" / "b.py").unlink()

    errors = orchestrator.check_protected_artifact_regression(baseline, tmp_path)

    assert errors
    assert any("src/api/b.py" in error for error in errors)


def test_guard_reports_every_violated_root(tmp_path) -> None:
    """複数ルートの違反を 1 回の判定で全件報告する。"""
    _write(tmp_path, "src/api/a.py")
    _write(tmp_path, "src/app/index.tsx")
    _write(tmp_path, "src/test/ui/home.spec.ts")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)
    (tmp_path / "src" / "api" / "a.py").unlink()
    (tmp_path / "src" / "app" / "index.tsx").unlink()

    errors = orchestrator.check_protected_artifact_regression(baseline, tmp_path)

    assert any("src/api" in error for error in errors)
    assert any("src/app" in error for error in errors)
    assert not any("src/test" in error for error in errors)


def test_guard_ignores_roots_absent_from_baseline(tmp_path) -> None:
    """baseline に無かったルートは欠落扱いしない。"""
    _write(tmp_path, "src/api/a.py")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)
    assert set(baseline) == {"src/api"}

    # baseline 取得後に生成されたルートは、その後消えても違反にしない。
    _write(tmp_path, "src/app/index.tsx")
    (tmp_path / "src" / "app" / "index.tsx").unlink()

    assert orchestrator.check_protected_artifact_regression(baseline, tmp_path) == []


def test_commit_push_refuses_to_stage_when_guard_fails(tmp_path, monkeypatch) -> None:
    """guard 違反時は git add / commit / push を一切実行しない。"""
    _write(tmp_path, "src/app/index.tsx")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)
    (tmp_path / "src" / "app" / "index.tsx").unlink()

    invoked: List[List[str]] = []

    def fake_run(args: Any, **_kwargs: Any):
        invoked.append(list(args))
        raise AssertionError(f"guard 違反時に git を実行した: {args}")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    console = _RecordingConsole()

    result = orchestrator._git_add_commit_push(
        "feature/x",
        "msg",
        console,
        protected_baseline=baseline,
        repo_root=tmp_path,
    )

    assert result is False
    assert invoked == []
    assert any("src/app" in error for error in console.errors)


def test_commit_push_proceeds_when_guard_passes(tmp_path, monkeypatch) -> None:
    """guard を通過した場合は従来どおり add → commit → push を実行する。"""
    _write(tmp_path, "src/app/index.tsx")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)

    calls: List[List[str]] = []

    class _Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(args: Any, **_kwargs: Any):
        argv = list(args)
        calls.append(argv)
        if argv[:3] == ["git", "status", "--porcelain"]:
            return _Result(0, stdout=" M src/app/index.tsx\n")
        if argv == ["git", "diff", "--cached", "--quiet"]:
            # --quiet は差分ありで exit 1
            return _Result(1)
        return _Result(0)

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    console = _RecordingConsole()

    result = orchestrator._git_add_commit_push(
        "feature/x",
        "msg",
        console,
        protected_baseline=baseline,
        repo_root=tmp_path,
    )

    assert result is True
    assert ["git", "add", "."] in calls
    assert any(argv[:2] == ["git", "commit"] for argv in calls)
    assert any(argv[:2] == ["git", "push"] for argv in calls)


def test_commit_push_without_baseline_keeps_existing_behaviour(tmp_path, monkeypatch) -> None:
    """baseline 未取得時は guard を適用せず既存挙動を維持する。"""

    class _Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(args: Any, **_kwargs: Any):
        argv = list(args)
        if argv[:3] == ["git", "status", "--porcelain"]:
            return _Result(0, stdout="")
        return _Result(0)

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    console = _RecordingConsole()

    assert orchestrator._git_add_commit_push("feature/x", "msg", console) is False


def test_guard_error_message_names_the_checkpoint_contract(tmp_path) -> None:
    """エラー文が checkpoint 保持契約であることを示す。"""
    _write(tmp_path, "src/api/a.py")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)
    (tmp_path / "src" / "api" / "a.py").unlink()

    errors = orchestrator.check_protected_artifact_regression(baseline, tmp_path)

    assert errors
    assert any("local generation checkpoint" in error for error in errors)


@pytest.mark.parametrize("root", ["src/api", "src/app", "src/test"])
def test_guard_protects_each_root_independently(tmp_path, root) -> None:
    """3 ルートそれぞれが独立に保護される。"""
    _write(tmp_path, f"{root}/keep.txt")
    baseline = orchestrator.capture_protected_artifact_manifest(tmp_path)
    (tmp_path / root / "keep.txt").unlink()

    errors = orchestrator.check_protected_artifact_regression(baseline, tmp_path)

    assert any(root in error for error in errors)


def test_guard_is_wired_into_every_commit_push_call_site() -> None:
    """guard がデッドコードにならないこと。

    `_git_add_commit_push` の全呼び出しが `protected_baseline` を渡し、
    local generation checkpoint で baseline を取得するコードが存在することを固定する。
    """
    source = Path(orchestrator.__file__).read_text(encoding="utf-8")
    body = source.split("def _git_add_commit_push(", 1)[1]
    call_sites = body.count("_git_add_commit_push(")
    assert call_sites > 0
    assert body.count("protected_baseline=protected_baseline") == call_sites
    assert "protected_baseline = capture_protected_artifact_manifest()" in body


def test_guard_runs_before_git_add_in_commit_push() -> None:
    """guard は `git add` より前に実行し、index を事故状態にしない。"""
    source = inspect.getsource(orchestrator._git_add_commit_push)

    assert source.index("check_protected_artifact_regression(") < source.index('"git", "add", "."')
