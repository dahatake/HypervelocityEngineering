"""FR-CLOUD-06: OUT-OF-SYNC な Cloud ASDW reusable workflow の dispatch 停止契約テスト。

FR-CLOUD-06 は「registry と同期していない Cloud reusable workflow を dispatcher から
起動してはならない」と定める。`auto-app-dev-microservice-web-reusable.yml` は
`hve/workflow_registry.py` の ASDW-WEB Step 体系と非同期（ファイル冒頭で OUT-OF-SYNC
NOTICE を自己申告）であるため、`.github/workflows/auto-orchestrator-dispatcher.yml` から
ASDW-WEB の Cloud 起動を停止し、CLI / GUI 経路が supported であることを明示する。
他の Cloud workflow（AAS / AAD-WEB / ADFD / ADFDV / AAG / AAGD / AKM / AQOD / ADOC）の
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


class TestAsdwWebCloudDispatchStopped:
    """FR-CLOUD-06: ASDW-WEB の Cloud 起動経路がすべて停止していること。"""

    @pytest.mark.parametrize(
        "kwargs",
        [
            # opened: 正規トリガーラベル
            {"action": "opened", "labels": ["auto-app-dev-microservice-web"]},
            # opened: 後方互換トリガーラベル
            {"action": "opened", "labels": ["auto-app-dev-microservice"]},
            # labeled: 正規トリガーラベル
            {"action": "labeled", "label_name": "auto-app-dev-microservice-web"},
            # labeled: 後方互換トリガーラベル
            {"action": "labeled", "label_name": "auto-app-dev-microservice"},
            # labeled: done ラベル（state_transition 経路）
            {"action": "labeled", "label_name": "asdw-web:done"},
            # labeled: 後方互換 done ラベル
            {"action": "labeled", "label_name": "asdw:done"},
            # closed: タイトルプレフィックス
            {"action": "closed", "title": "[ASDW-WEB] Step.1.1 データストア選定"},
            # closed: 後方互換タイトルプレフィックス
            {"action": "closed", "title": "[ASDW] Step.1.1 データストア選定"},
            # closed: ラベル経由
            {"action": "closed", "labels": ["auto-app-dev-microservice-web"]},
        ],
    )
    def test_asdw_web_never_resolves_as_dispatch_target(self, tmp_path, kwargs):
        """FR-CLOUD-06: ASDW-WEB のどの起動経路でも target が ASDW-WEB にならないこと。"""
        outputs = _run_detect(tmp_path, **kwargs)
        assert outputs["target"] == "none", f"ASDW-WEB が dispatch されました: {kwargs}"
        assert outputs["mode"] == "skip", f"ASDW-WEB が skip されていません: {kwargs}"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"action": "opened", "labels": ["auto-app-dev-microservice-web"]},
            {"action": "labeled", "label_name": "auto-app-dev-microservice-web"},
            {"action": "labeled", "label_name": "asdw-web:done"},
        ],
    )
    def test_asdw_web_marks_cloud_dispatch_disabled(self, tmp_path, kwargs):
        """FR-CLOUD-06: 停止した旨を通知するための出力が ASDW-WEB を示すこと。"""
        outputs = _run_detect(tmp_path, **kwargs)
        assert outputs.get("cloud_dispatch_disabled") == "ASDW-WEB"

    def test_closed_event_does_not_notify(self, tmp_path):
        """FR-CLOUD-06: closed イベントでは停止通知を出さないこと（ノイズ抑制）。"""
        outputs = _run_detect(
            tmp_path, action="closed", title="[ASDW-WEB] Step.1.1 データストア選定"
        )
        assert outputs.get("cloud_dispatch_disabled") == ""

    def test_dispatcher_has_no_job_calling_out_of_sync_asdw_reusable(self):
        """FR-CLOUD-06: dispatcher が OUT-OF-SYNC な ASDW reusable workflow を uses しないこと。"""
        jobs = _dispatcher_yaml()["jobs"]
        offenders = [
            name for name, job in jobs.items()
            if _ASDW_WEB_REUSABLE in str(job.get("uses", ""))
        ]
        assert offenders == [], f"ASDW reusable workflow を呼ぶジョブが残っています: {offenders}"
        assert f"uses: ./.github/workflows/{_ASDW_WEB_REUSABLE}" not in _dispatcher_text()

    def test_dispatcher_notifies_cli_gui_supported_path(self):
        """FR-CLOUD-06: CLI / GUI 経路が supported であることを Issue コメントで明示すること。"""
        steps = _dispatcher_yaml()["jobs"]["detect"]["steps"]
        notify = [
            step for step in steps
            if "cloud_dispatch_disabled" in str(step.get("if", ""))
        ]
        assert notify, "Cloud 起動停止を通知するステップが見つかりません"
        script = str(notify[0].get("run", ""))
        assert "gh" in script and "issue" in script and "comment" in script
        assert "CLI" in script and "GUI" in script


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
        ("auto-app-documentation", "ADOC"),
        ("knowledge-management", "AKM"),
    ]

    @pytest.mark.parametrize("label,expected", _OTHER_TRIGGERS)
    def test_other_triggers_still_initialize_on_opened(self, tmp_path, label, expected):
        outputs = _run_detect(tmp_path, action="opened", labels=[label])
        assert outputs["target"] == expected
        assert outputs["mode"] == "initialize"
        assert outputs.get("cloud_dispatch_disabled") == ""

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

    def test_setup_labels_and_aqod_paths_unchanged(self, tmp_path):
        setup = _run_detect(tmp_path, action="opened", labels=["setup-labels"])
        assert (setup["target"], setup["mode"]) == ("SETUP_LABELS", "initialize")
        aqod = _run_detect(tmp_path, action="labeled", label_name="original-docs-review")
        assert (aqod["target"], aqod["mode"]) == ("AQOD", "initialize")

    def test_other_reusable_workflow_jobs_remain(self):
        """FR-CLOUD-06: ASDW-WEB 以外の reusable workflow 呼び出しジョブを維持すること。"""
        jobs = _dispatcher_yaml()["jobs"]
        expected = {
            "aad-web": "auto-app-detail-design-web-reusable.yml",
            "aag": "auto-ai-agent-design-reusable.yml",
            "aagd": "auto-ai-agent-dev-reusable.yml",
            "adoc": "auto-app-documentation-reusable.yml",
            "aas": "auto-app-selection-reusable.yml",
            "adfd": "auto-dataflow-design-reusable.yml",
            "adfdv": "auto-dataflow-dev-reusable.yml",
            "akm": "auto-knowledge-management-reusable.yml",
            "setup_labels": "setup-labels.yml",
            "aqod": "auto-aqod.yml",
        }
        for job_name, workflow in expected.items():
            assert job_name in jobs, f"ジョブ {job_name} が dispatcher から消えています"
            assert jobs[job_name]["uses"].endswith(workflow)
