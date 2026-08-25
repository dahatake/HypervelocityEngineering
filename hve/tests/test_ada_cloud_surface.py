"""ADA Cloud 面（Issue Template / reusable workflow / dispatcher / labels）の契約テスト。

Cloud 経路は SSoT を読まずハードコードしているため、定義と実行のずれを
実行前に検出する。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO / ".github" / "workflows" / "auto-agent-data-architecture-reusable.yml"
_DISPATCHER = _REPO / ".github" / "workflows" / "auto-orchestrator-dispatcher.yml"
_ISSUE_TEMPLATE = _REPO / ".github" / "ISSUE_TEMPLATE" / "agent-data-architecture.yml"
_LABELS = _REPO / ".github" / "labels.json"
_BASH_REGISTRY = _REPO / ".github" / "scripts" / "bash" / "lib" / "workflow-registry.sh"

_TRIGGER_LABEL = "auto-agent-data-architecture"
_STATE_LABELS = (
    "ada:initialized",
    "ada:ready",
    "ada:running",
    "ada:done",
    "ada:blocked",
)
_EXPECTED_STEP_IDS = ["2", "3", "4.1", "4.2", "5", "6", "7", "8", "9"]


def _workflow_doc() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _run_blocks() -> list[tuple[str, str]]:
    steps = _workflow_doc()["jobs"]["orchestrate"]["steps"]
    return [(s.get("name", "<unnamed>"), s["run"]) for s in steps if s.get("run")]


def test_workflow_file_exists_and_parses() -> None:
    assert _WORKFLOW.is_file()
    doc = _workflow_doc()
    assert "orchestrate" in doc["jobs"]


def _git_bash() -> str | None:
    """Windows パスを解決できる bash（Git for Windows）だけを返す。

    PATH 上の `bash` は WSL bash のことがあり、Windows パスの一時ファイルを
    解決できずテストが環境依存で落ちる。確実に Windows パスを扱える
    Git for Windows の bash が見つかった場合だけ構文検査を行う。
    """
    override = os.environ.get("HVE_GIT_BASH")
    if override and Path(override).is_file():
        return override
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


@pytest.mark.parametrize("index", range(4))
def test_all_run_blocks_are_valid_bash(index: int) -> None:
    """YAML が通っても shell が壊れていることがあるため個別に構文検査する。"""
    blocks = _run_blocks()
    if index >= len(blocks):
        pytest.skip(f"run ブロックは {len(blocks)} 件")
    bash = _git_bash()
    if bash is None:  # pragma: no cover - Git for Windows 非搭載環境
        pytest.skip("Git for Windows の bash が見つかりません")
    name, script = blocks[index]
    with tempfile.NamedTemporaryFile(
        "w", suffix=".sh", delete=False, encoding="utf-8", newline="\n"
    ) as handle:
        handle.write(script)
        path = handle.name
    try:
        result = subprocess.run(
            [bash, "-n", path], capture_output=True, text=True, timeout=60
        )
    finally:
        Path(path).unlink(missing_ok=True)
    assert result.returncode == 0, f"{name}: {result.stderr}"


def test_workflow_creates_every_registry_step() -> None:
    """reusable YAML の Step 一覧が registry の Step ID と一致すること。"""
    text = _WORKFLOW.read_text(encoding="utf-8")
    found = re.findall(r'\("([0-9.]+)", "\[ADA\] Step\.[0-9.]+: ', text)
    assert found == _EXPECTED_STEP_IDS


def test_workflow_step_titles_match_registry_titles() -> None:
    from hve.workflow_registry import get_workflow

    text = _WORKFLOW.read_text(encoding="utf-8")
    titles = dict(
        re.findall(r'\("([0-9.]+)", "\[ADA\] Step\.[0-9.]+: ([^"]+)", "', text)
    )
    for step in get_workflow("ada").steps:
        assert titles[step.id] == step.title, step.id


def test_workflow_step_agents_match_registry_agents() -> None:
    from hve.workflow_registry import get_workflow

    text = _WORKFLOW.read_text(encoding="utf-8")
    agents = dict(
        re.findall(r'\("([0-9.]+)", "\[ADA\] Step\.[0-9.]+: [^"]+", "([^"]+)"\)', text)
    )
    for step in get_workflow("ada").steps:
        assert agents[step.id] == step.custom_agent, step.id


def test_state_transition_handles_decimal_step_ids() -> None:
    """Step.4.1 / 4.2 を含むため、次 Step 解決は順序リストで行うこと。"""
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "order = ['2','3','4.1','4.2','5','6','7','8','9']" in text
    # 算術インクリメント（$((STEP + 1))）は小数 ID を壊すため使わない。
    assert "$((STEP + 1))" not in text


def test_dispatcher_wires_ada() -> None:
    doc = yaml.safe_load(_DISPATCHER.read_text(encoding="utf-8"))
    job = doc["jobs"]["ada"]
    assert job["uses"].endswith("auto-agent-data-architecture-reusable.yml")
    assert "ADA" in job["if"]

    text = _DISPATCHER.read_text(encoding="utf-8")
    assert f"('{_TRIGGER_LABEL}',      'ADA')" in text
    assert "'ada:done':      'ADA'," in text
    assert "('[ADA]', 'ADA')," in text


def test_labels_json_declares_ada_labels() -> None:
    labels = {item["name"] for item in json.loads(_LABELS.read_text(encoding="utf-8"))}
    assert _TRIGGER_LABEL in labels
    for name in _STATE_LABELS:
        assert name in labels


def test_issue_template_uses_trigger_label() -> None:
    doc = yaml.safe_load(_ISSUE_TEMPLATE.read_text(encoding="utf-8"))
    assert doc["labels"] == [_TRIGGER_LABEL]
    ids = {
        item["id"]
        for item in doc["body"]
        if isinstance(item, dict) and "id" in item
    }
    # reusable workflow の本文パーサが参照する入力。
    assert {"branch", "runner_type", "app_ids", "additional_comment"} <= ids


def test_bash_registry_declares_ada() -> None:
    text = _BASH_REGISTRY.read_text(encoding="utf-8")
    assert "_WORKFLOW_REGISTRY[ada]=" in text
    for step_id in _EXPECTED_STEP_IDS:
        assert f'{{"id":"{step_id}"' in text.replace(" ", "") or f'"id":"{step_id}"' in text
