"""FR-CLOUD-06: Cloud ASDW-WEB reusable workflow の dispatch 契約テスト。

FR-CLOUD-06 は「registry と同期していない Cloud reusable workflow を dispatcher から
起動してはならない。同期が確認できた reusable は dispatch 対象としてよい」と定める。
`auto-app-dev-microservice-web-reusable.yml` は `hve/workflow_registry.py` の ASDW-WEB
Step 体系と同期済み（`test_cloud_reusable_workflow_parity.py` が固定）のため、
`.github/workflows/auto-orchestrator-dispatcher.yml` から ASDW-WEB を起動する。
他の Cloud workflow（AAS / AAD-WEB / ADFD / ADFDV / AAG / AAGD / AKM / ADOC）の
挙動は変更しない。

本テストは dispatcher の `detect` ステップに埋め込まれた Python スクリプトを抽出して
実行し、`target` / `mode` を振る舞いレベルで検証する（文字列一致だけに依存しない）。
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from pathlib import Path
from unittest import mock

import pytest
import yaml

_WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
_DISPATCHER = "auto-orchestrator-dispatcher.yml"
_ASDW_WEB_REUSABLE = "auto-app-dev-microservice-web-reusable.yml"


def _dispatcher_text() -> str:
    return (_WORKFLOWS_DIR / _DISPATCHER).read_text(encoding="utf-8")


def _dispatcher_yaml() -> dict:
    # PyYAML (YAML 1.1) では 'on' キーが boolean True になるため jobs のみ利用する。
    return yaml.safe_load(_dispatcher_text())


def _detect_step() -> dict:
    steps = _dispatcher_yaml()["jobs"]["detect"]["steps"]
    return next(step for step in steps if step.get("id") == "detect")


def _detect_script() -> str:
    """detect ステップの `python3 <<'PY' ... PY` ヒアドキュメント本文を返す。"""
    run = _detect_step()["run"]
    match = re.search(r"python3 <<'PY'\n(.*?)\nPY\s*$", run, re.DOTALL)
    assert match, "detect ステップから python ヒアドキュメントを抽出できません"
    return textwrap.dedent(match.group(1))


def _run_detect(
    tmp_path: Path,
    *,
    labels: list[str] | None = None,
    title: str = "",
    action: str = "opened",
    label_name: str = "",
    author_association: str = "OWNER",
    body: str = "",
    issue_number: str = "1234",
) -> dict[str, str]:
    """detect スクリプトを実行し、GITHUB_OUTPUT の内容を dict で返す。"""
    out_file = tmp_path / "github_output.txt"
    out_file.write_text("", encoding="utf-8")
    env = {
        "ISSUE_LABELS": json.dumps(labels or []),
        "ISSUE_TITLE": title,
        "EVENT_ACTION": action,
        "LABEL_NAME": label_name,
        "ISSUE_NUMBER": issue_number,
        "AUTHOR_ASSOCIATION": author_association,
        "ISSUE_BODY": body,
        "GITHUB_OUTPUT": str(out_file),
    }
    with mock.patch.dict(os.environ, env, clear=False):
        exec(compile(_detect_script(), "<dispatcher-detect>", "exec"), {})

    outputs: dict[str, str] = {}
    for line in out_file.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            outputs[key] = value
    return outputs


class TestAsdwWebCloudDispatchEnabled:
    """FR-CLOUD-06: ASDW-WEB の Cloud 起動経路が有効であること。"""

    @pytest.mark.parametrize(
        "kwargs,expected_mode",
        [
            # opened: 正規トリガーラベル
            ({"action": "opened", "labels": ["auto-app-dev-microservice-web"]}, "initialize"),
            # opened: 後方互換トリガーラベル
            ({"action": "opened", "labels": ["auto-app-dev-microservice"]}, "initialize"),
            # labeled: 正規トリガーラベル
            ({"action": "labeled", "label_name": "auto-app-dev-microservice-web"}, "initialize"),
            # labeled: 後方互換トリガーラベル
            ({"action": "labeled", "label_name": "auto-app-dev-microservice"}, "initialize"),
            # labeled: done ラベル（state_transition 経路）
            ({"action": "labeled", "label_name": "asdw-web:done"}, "state_transition"),
            # labeled: 後方互換 done ラベル
            ({"action": "labeled", "label_name": "asdw:done"}, "state_transition"),
            # closed: タイトルプレフィックス
            ({"action": "closed", "title": "[ASDW-WEB] Step.1.1 データストア選定"}, "closed"),
            # closed: 後方互換タイトルプレフィックス
            ({"action": "closed", "title": "[ASDW] Step.1.1 データストア選定"}, "closed"),
        ],
    )
    def test_asdw_web_resolves_as_dispatch_target(self, tmp_path, kwargs, expected_mode):
        outputs = _run_detect(tmp_path, **kwargs)
        assert outputs["target"] == "ASDW-WEB", f"ASDW-WEB が dispatch されません: {kwargs}"
        assert outputs["mode"] == expected_mode, f"mode が一致しません: {kwargs}"

    def test_dispatcher_has_a_job_calling_asdw_reusable(self):
        """dispatcher が ASDW reusable workflow を uses するジョブを持つこと。"""
        jobs = _dispatcher_yaml()["jobs"]
        callers = [
            name for name, job in jobs.items()
            if _ASDW_WEB_REUSABLE in str(job.get("uses", ""))
        ]
        assert callers, "ASDW reusable workflow を呼ぶジョブがありません"
        job = jobs[callers[0]]
        assert "ASDW-WEB" in str(job.get("if", ""))

    def test_dispatcher_has_no_cloud_dispatch_stop_notice(self):
        """停止通知ステップが残っていないこと。"""
        assert "cloud_dispatch_disabled" not in _dispatcher_text()


class TestOtherCloudWorkflowsUnchanged:
    """FR-CLOUD-06: 他の Cloud workflow の挙動を変更しないこと。"""

    _OTHER_TRIGGERS = [
        ("auto-app-selection", "AAS"),
        ("auto-app-detail-design-web", "AAD-WEB"),
        ("auto-app-detail-design", "AAD-WEB"),
        ("auto-dataflow-design", "ADFD"),
        ("auto-dataflow-dev", "ADFDV"),
        ("auto-ai-agent-design", "AAG"),
        ("auto-ai-agent-dev", "AAGD"),
        ("auto-agentic-retrieval", "AAR"),
        ("auto-app-documentation", "ADOC"),
        ("knowledge-management", "AKM"),
    ]

    @pytest.mark.parametrize("label,expected", _OTHER_TRIGGERS)
    def test_other_triggers_still_initialize_on_opened(self, tmp_path, label, expected):
        outputs = _run_detect(tmp_path, action="opened", labels=[label])
        assert outputs["target"] == expected
        assert outputs["mode"] == "initialize"

    @pytest.mark.parametrize("label,expected", _OTHER_TRIGGERS)
    def test_other_triggers_still_initialize_on_labeled(self, tmp_path, label, expected):
        outputs = _run_detect(tmp_path, action="labeled", label_name=label)
        assert outputs["target"] == expected
        assert outputs["mode"] == "initialize"

    @pytest.mark.parametrize(
        "label,expected",
        [
            ("aas:done", "AAS"),
            ("aad-web:done", "AAD-WEB"),
            ("adfd:done", "ADFD"),
            ("adfdv:done", "ADFDV"),
            ("aag:done", "AAG"),
            ("aagd:done", "AAGD"),
            ("aar:done", "AAR"),
            ("adoc:done", "ADOC"),
            ("akm:done", "AKM"),
        ],
    )
    def test_other_done_labels_still_state_transition(self, tmp_path, label, expected):
        outputs = _run_detect(tmp_path, action="labeled", label_name=label)
        assert outputs["target"] == expected
        assert outputs["mode"] == "state_transition"

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("[AAD-WEB] Step.1", "AAD-WEB"),
            ("[AAG] Step.1", "AAG"),
            ("[AAGD] Step.1", "AAGD"),
            ("[AAR] Step.1", "AAR"),
            ("[ADOC] Step.1", "ADOC"),
            ("[AAS] Step.1", "AAS"),
            ("[ADFD] Step.1", "ADFD"),
            ("[ADFDV] Step.1", "ADFDV"),
            ("[AKM] Step.1", "AKM"),
        ],
    )
    def test_other_closed_prefixes_still_resolve(self, tmp_path, title, expected):
        outputs = _run_detect(tmp_path, action="closed", title=title)
        assert outputs["target"] == expected
        assert outputs["mode"] == "closed"

    def test_setup_labels_path_unchanged(self, tmp_path):
        setup = _run_detect(tmp_path, action="opened", labels=["setup-labels"])
        assert (setup["target"], setup["mode"]) == ("SETUP_LABELS", "initialize")

    def test_other_reusable_workflow_jobs_remain(self):
        """FR-CLOUD-06: reusable workflow 呼び出しジョブの集合を固定すること。"""
        jobs = _dispatcher_yaml()["jobs"]
        expected = {
            "ard": "auto-requirement-definition-reusable.yml",
            "check_app_requirements": "check-app-requirements-reusable.yml",
            "aad-web": "auto-app-detail-design-web-reusable.yml",
            "aag": "auto-ai-agent-design-reusable.yml",
            "aagd": "auto-ai-agent-dev-reusable.yml",
            "aar": "auto-agentic-retrieval-reusable.yml",
            "ada": "auto-agent-data-architecture-reusable.yml",
            "adoc": "auto-app-documentation-reusable.yml",
            "aas": "auto-app-selection-reusable.yml",
            "adfd": "auto-dataflow-design-reusable.yml",
            "adfdv": "auto-dataflow-dev-reusable.yml",
            "akm": "auto-knowledge-management-reusable.yml",
            "asdw-web": "auto-app-dev-microservice-web-reusable.yml",
            "setup_labels": "setup-labels.yml",
        }
        for job_name, workflow in expected.items():
            assert job_name in jobs, f"ジョブ {job_name} が dispatcher から消えています"
            assert jobs[job_name]["uses"].endswith(workflow)

        reusable_jobs = {
            name for name, job in jobs.items() if isinstance(job, dict) and job.get("uses")
        }
        assert reusable_jobs == set(expected)
