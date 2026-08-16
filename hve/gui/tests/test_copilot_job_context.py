"""hve.gui.tests.test_copilot_job_context

FR-GUI-14 の受入テスト。

完了ジョブを新しい Copilot CLI チャットへ渡すときの初期コンテキストが、
実在するパスだけを列挙し、ファイル本文を埋め込まず、選択した run の
ルート外を自動探索しないことを固定する。
"""

from __future__ import annotations

from pathlib import Path

from hve.gui.copilot_job_context import build_job_result_context
from hve.gui.job_interaction_model import JobTarget


def _target(**overrides) -> JobTarget:
    base = dict(
        instance_id="asdw-web",
        workflow_id="asdw-web",
        label="ASDW-WEB",
        step_id=None,
        step_title="",
        status="done",
        channel_dir=None,
    )
    base.update(overrides)
    return JobTarget(**base)


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "work" / "run" / "20260813T100153-594abe"
    (run_dir / "gui-logs").mkdir(parents=True)
    (run_dir / "console-log.txt").write_text("console", encoding="utf-8")
    (run_dir / "gui-logs" / "log-0001.log").write_text("log", encoding="utf-8")
    return run_dir


def test_includes_existing_run_paths(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    context = build_job_result_context(_target(), work_root=run_dir, returncode=0)
    names = {p.name for p in context.paths}
    assert "console-log.txt" in names
    assert "gui-logs" in names


def test_omits_paths_that_do_not_exist(tmp_path: Path) -> None:
    run_dir = tmp_path / "empty-run"
    run_dir.mkdir()
    context = build_job_result_context(_target(), work_root=run_dir, returncode=0)
    assert context.paths == ()
    assert "console-log.txt" not in context.prompt


def test_includes_completion_reports_under_the_run_root(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    report = run_dir / "Dev-Agent" / "Issue-step-1-1" / "completion-report.md"
    report.parent.mkdir(parents=True)
    report.write_text("done", encoding="utf-8")
    context = build_job_result_context(_target(), work_root=run_dir, returncode=0)
    assert report in context.paths


def test_does_not_search_outside_the_selected_run_root(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    sibling = tmp_path / "work" / "run" / "other-run"
    sibling.mkdir(parents=True)
    stray = sibling / "completion-report.md"
    stray.write_text("other", encoding="utf-8")
    context = build_job_result_context(_target(), work_root=run_dir, returncode=0)
    assert stray not in context.paths
    assert str(sibling) not in context.prompt


def test_does_not_embed_file_contents(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    (run_dir / "console-log.txt").write_text("SECRET-LOG-BODY", encoding="utf-8")
    context = build_job_result_context(_target(), work_root=run_dir, returncode=0)
    assert "SECRET-LOG-BODY" not in context.prompt


def test_includes_existing_session_artifacts_only(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    real = tmp_path / "docs" / "generated.md"
    real.parent.mkdir(parents=True)
    real.write_text("x", encoding="utf-8")
    missing = tmp_path / "docs" / "deleted.md"
    context = build_job_result_context(
        _target(), work_root=run_dir, returncode=0, artifacts=[real, missing]
    )
    assert real in context.paths
    assert missing not in context.paths


def test_prompt_identifies_the_job_and_outcome(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    context = build_job_result_context(
        _target(step_id="1.2", step_title="RED", status="failed"),
        work_root=run_dir,
        returncode=1,
    )
    assert "asdw-web" in context.prompt
    assert "1.2" in context.prompt
    assert "終了コード: 1" in context.prompt
    assert context.run_id == run_dir.name


def test_prompt_omits_the_return_code_when_unknown(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    context = build_job_result_context(_target(), work_root=run_dir, returncode=None)
    assert "終了コード" not in context.prompt


def test_paths_are_deduplicated_and_ordered(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    artifact = run_dir / "console-log.txt"
    context = build_job_result_context(
        _target(), work_root=run_dir, returncode=0, artifacts=[artifact, artifact]
    )
    assert len(context.paths) == len(set(context.paths))
    assert list(context.paths) == sorted(context.paths, key=lambda p: str(p))


def test_missing_work_root_yields_empty_paths(tmp_path: Path) -> None:
    context = build_job_result_context(
        _target(), work_root=tmp_path / "absent", returncode=None
    )
    assert context.paths == ()
    assert context.prompt.strip() != ""


def test_prompt_lists_every_selected_path(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    context = build_job_result_context(_target(), work_root=run_dir, returncode=0)
    for path in context.paths:
        assert str(path) in context.prompt
