"""FR-APPREQ-03/04: 選択参照・fail-closed・trace block契約RED。"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _api():
    return importlib.import_module("hve.application_requirements")


def _write_fixture(
    root: Path, *, blocker: str = "no", status: str = "source-backed"
) -> None:
    catalog = root / "docs" / "catalog" / "app-catalog.md"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(
        "# App Catalog\n\n| APP-ID | APP名 |\n|---|---|\n| APP-001 | 会員管理 |\n| APP-002 | 分析 |\n",
        encoding="utf-8",
    )
    for app_id, app_name in (("APP-001", "会員管理"), ("APP-002", "分析")):
        suffix = app_id.removeprefix("APP-")
        path = root / "docs" / f"architectural-requirements-app-{suffix}.md"
        path.write_text(
            f"""# {app_id} 要求定義書

- Schema-Version: 1
- APP-ID: {app_id}
- APP名: {app_name}
- Document-Status: active

## Requirements

| Requirement ID | Status | Requirement | Source | Acceptance Criteria | Blocker |
|---|---|---|---|---|---|
| {app_id}-FR-001 | {status if app_id == 'APP-001' else 'source-backed'} | 登録できる | docs/catalog/use-case-catalog.md | 結果を確認できる | {blocker if app_id == 'APP-001' else 'no'} |
""",
            encoding="utf-8",
        )


def test_app_fanout_context_contains_only_the_target_path(tmp_path: Path) -> None:
    api = _api()
    _write_fixture(tmp_path)
    context = api.build_application_requirement_context(
        workflow_id="aas",
        workflow_params={},
        fanout_meta={"fanout_key": "APP-001", "base_step_id": "2"},
        repo_root=tmp_path,
    )
    assert "APP-001" in context
    assert "docs/architectural-requirements-app-001.md" in context
    assert "APP-002" not in context
    assert "登録できる" not in context
    assert "markdown-query" in context


def test_screen_fanout_resolves_its_own_app(tmp_path: Path) -> None:
    api = _api()
    _write_fixture(tmp_path)
    assert api.resolve_application_requirement_app_ids(
        workflow_id="aad-web",
        workflow_params={"app_ids": ["APP-001", "APP-002"]},
        fanout_meta={"fanout_key": "APP-002-S001", "base_step_id": "2.1"},
        repo_root=tmp_path,
    ) == ("APP-002",)


def test_non_fanout_scope_uses_effective_app_ids(tmp_path: Path) -> None:
    api = _api()
    _write_fixture(tmp_path)
    assert api.resolve_application_requirement_app_ids(
        workflow_id="asdw-web",
        workflow_params={"app_ids": ["APP-002"]},
        fanout_meta=None,
        repo_root=tmp_path,
    ) == ("APP-002",)


def test_cross_cutting_step_without_app_ids_uses_workflow_classification(
    tmp_path: Path,
) -> None:
    """実効 app_ids が空の横断 Step は当該 Workflow の対象分類の全 APP を参照する。

    Cloud の AAS / ADFD は app-catalog の生成側なので Step Issue へ app-ids を
    埋めない。その経路は fanout_meta=None かつ app_ids 空で解決される。
    """
    api = _api()
    _write_fixture(tmp_path)
    arch_catalog = tmp_path / "docs" / "catalog" / "app-arch-catalog.md"
    arch_catalog.write_text(
        "# arch\n\n## A) サマリ表（全APP横断）\n\n"
        "| APP-ID | APP名 | 推薦アーキテクチャ |\n|---|---|---|\n"
        "| APP-001 | 会員管理 | Webフロントエンド + クラウド |\n"
        "| APP-002 | 分析 | データフロー処理 |\n",
        encoding="utf-8",
    )

    def resolve(workflow_id: str) -> list[str]:
        return sorted(
            api.resolve_application_requirement_app_ids(
                workflow_id=workflow_id,
                workflow_params={},
                fanout_meta=None,
                repo_root=tmp_path,
            )
        )

    assert resolve("aas") == ["APP-001", "APP-002"]
    assert resolve("adfd") == ["APP-002"]
    assert resolve("aad-web") == ["APP-001"]


def test_missing_or_blocking_requirement_fails_before_session(tmp_path: Path) -> None:
    api = _api()
    _write_fixture(tmp_path)
    (tmp_path / "docs" / "architectural-requirements-app-001.md").unlink()
    with pytest.raises(api.ApplicationRequirementError):
        api.build_application_requirement_context(
            workflow_id="aas",
            workflow_params={"app_ids": ["APP-001"]},
            fanout_meta=None,
            repo_root=tmp_path,
        )

    _write_fixture(tmp_path, blocker="yes", status="TBD")
    with pytest.raises(api.ApplicationRequirementError):
        api.build_application_requirement_context(
            workflow_id="aas",
            workflow_params={"app_ids": ["APP-001"]},
            fanout_meta=None,
            repo_root=tmp_path,
        )


@pytest.mark.parametrize(
    "old,new",
    [
        ("- APP-ID: APP-001", "- APP-ID: APP-002"),
        (
            "| Requirement ID | Status | Requirement | Source | Acceptance Criteria | Blocker |",
            "| Requirement ID | Status | Requirement | Source | Blocker |",
        ),
    ],
)
def test_mismatched_or_structurally_invalid_requirement_fails_before_session(
    tmp_path: Path, old: str, new: str
) -> None:
    api = _api()
    _write_fixture(tmp_path)
    path = tmp_path / "docs" / "architectural-requirements-app-001.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(old, new, 1),
        encoding="utf-8",
    )
    with pytest.raises(api.ApplicationRequirementError):
        api.build_application_requirement_context(
            workflow_id="aas",
            workflow_params={"app_ids": ["APP-001"]},
            fanout_meta=None,
            repo_root=tmp_path,
        )


def test_non_tbd_blocker_is_not_an_unresolved_tbd_gate(tmp_path: Path) -> None:
    api = _api()
    _write_fixture(tmp_path, blocker="yes", status="source-backed")
    context = api.build_application_requirement_context(
        workflow_id="aas",
        workflow_params={"app_ids": ["APP-001"]},
        fanout_meta=None,
        repo_root=tmp_path,
    )
    assert "APP-001" in context


def test_trace_block_accepts_real_non_tbd_ids(tmp_path: Path) -> None:
    api = _api()
    _write_fixture(tmp_path)
    block = """<!-- app-requirements:start -->
- APP-IDs: APP-001
- Requirement-IDs: APP-001-FR-001
- Requirement-Documents: docs/architectural-requirements-app-001.md
- Unresolved-Blockers: none
<!-- app-requirements:end -->"""
    assert api.validate_application_requirement_trace_block(
        block, repo_root=tmp_path, expected_app_ids=("APP-001",)
    ) == []


def test_trace_block_rejects_unknown_or_tbd_ids(tmp_path: Path) -> None:
    api = _api()
    _write_fixture(tmp_path)
    base = """<!-- app-requirements:start -->
- APP-IDs: APP-001
- Requirement-IDs: {requirement_id}
- Requirement-Documents: docs/architectural-requirements-app-001.md
- Unresolved-Blockers: none
<!-- app-requirements:end -->"""
    unknown = api.validate_application_requirement_trace_block(
        base.format(requirement_id="APP-001-FR-999"),
        repo_root=tmp_path,
        expected_app_ids=("APP-001",),
    )
    assert unknown

    path = tmp_path / "docs" / "architectural-requirements-app-001.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("source-backed", "TBD"),
        encoding="utf-8",
    )
    tbd = api.validate_application_requirement_trace_block(
        base.format(requirement_id="APP-001-FR-001"),
        repo_root=tmp_path,
        expected_app_ids=("APP-001",),
    )
    assert tbd

    path.write_text(
        path.read_text(encoding="utf-8").replace("TBD", "guessed"),
        encoding="utf-8",
    )
    invalid_status = api.validate_application_requirement_trace_block(
        base.format(requirement_id="APP-001-FR-001"),
        repo_root=tmp_path,
        expected_app_ids=("APP-001",),
    )
    assert invalid_status


def test_trace_block_rejects_unresolved_blocker_introduced_after_preflight(
    tmp_path: Path,
) -> None:
    api = _api()
    _write_fixture(tmp_path, blocker="yes", status="TBD")
    block = """<!-- app-requirements:start -->
- APP-IDs: APP-001
- Requirement-IDs: none
- Requirement-Documents: docs/architectural-requirements-app-001.md
- Unresolved-Blockers: APP-001-FR-001
<!-- app-requirements:end -->"""
    errors = api.validate_application_requirement_trace_block(
        block,
        repo_root=tmp_path,
        expected_app_ids=("APP-001",),
    )
    assert any("未解決の TBD Blocker" in error for error in errors)


def test_runner_wires_preflight_before_client_and_completion_gate() -> None:
    import hve.runner as runner

    source = inspect.getsource(runner.StepRunner.run_step)
    preflight = source.index("build_application_requirement_context")
    client = source.index("create_copilot_client")
    coverage = source.index("validate_requirement_coverage")
    completion = source.index("validate_application_requirement_trace_block")
    final_message = source.index("self.console.final_message")
    assert preflight < client < coverage < completion < final_message


def test_runner_missing_requirement_stops_before_work_dir_and_sdk(
    tmp_path: Path, monkeypatch
) -> None:
    import hve.runner as runner_module
    from hve.config import SDKConfig
    from hve.console import Console

    monkeypatch.chdir(tmp_path)
    work_dir_probe = MagicMock()
    monkeypatch.setattr(runner_module, "_ensure_step_work_dir", work_dir_probe)
    console = Console(verbose=False, quiet=True)
    console.error = MagicMock()
    runner = runner_module.StepRunner(
        config=SDKConfig(dry_run=False),
        console=console,
        workflow_params={},
    )

    result = asyncio.run(
        runner.run_step(
            "2",
            "Architecture recommendation",
            "analyze",
            custom_agent="Arch-ArchitectureCandidateAnalyzer",
            workflow_id="aas",
        )
    )

    assert result is False
    work_dir_probe.assert_not_called()
    assert any(
        "APP要求preflight failed" in str(call.args[0])
        for call in console.error.call_args_list
    )
