"""FR-QA-10: 事前 QA 既定値較正ログのテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from hve.qa_merger import Choice, QADocument, QAMerger, QAQuestion
from hve.runner import _persist_answered_qa_and_dispatch


def _doc() -> QADocument:
    return QADocument(
        title="事前 QA",
        status="回答待ち",
        header_fields=[("状態", "回答待ち")],
        questions=[
            QAQuestion(
                no=1,
                question="通信方式は？",
                choices=[Choice("A", "REST"), Choice("B", "gRPC")],
                default_answer="REST",
                priority="高",
                category="architecture",
                research_answer="Research answer text must not be logged",
                research_status="Confirmed",
                research_sources="S1",
            ),
            QAQuestion(
                no=2,
                question="DB は？",
                choices=[Choice("A", "SQL"), Choice("B", "NoSQL")],
                default_answer="A) SQL",
                priority="中",
                category="data",
            ),
            QAQuestion(
                no=3,
                question="監視は？",
                choices=[Choice("A", "App Insights"), Choice("B", "なし")],
                default_answer="A) App Insights",
                priority="低",
                category="operations",
            ),
        ],
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_append_calibration_log_records_only_explicit_answers(tmp_path: Path) -> None:
    log_path = tmp_path / "work" / "learning" / "qa-calibration.jsonl"

    QAMerger.append_calibration_log(_doc(), {1: "A", 2: "B"}, log_path)

    records = _read_jsonl(log_path)
    assert [list(record.keys()) for record in records] == [
        ["category", "priority", "default", "final", "matched"],
        ["category", "priority", "default", "final", "matched"],
    ]
    assert records == [
        {
            "category": "architecture",
            "priority": "高",
            "default": "REST",
            "final": "A) REST",
            "matched": True,
        },
        {
            "category": "data",
            "priority": "中",
            "default": "A) SQL",
            "final": "B) NoSQL",
            "matched": False,
        },
    ]
    raw = log_path.read_text(encoding="utf-8")
    assert "operations" not in raw
    assert "Research answer" not in raw


def test_append_calibration_log_masks_secret_like_free_text(tmp_path: Path) -> None:
    log_path = tmp_path / "work" / "learning" / "qa-calibration.jsonl"

    QAMerger.append_calibration_log(
        _doc(), {1: "password=hunter2 を使う"}, log_path
    )

    raw = log_path.read_text(encoding="utf-8")
    assert "hunter2" not in raw
    assert "[REDACTED]" in raw


def test_append_calibration_log_with_defaults_records_nothing(tmp_path: Path) -> None:
    log_path = tmp_path / "work" / "learning" / "qa-calibration.jsonl"

    QAMerger.append_calibration_log(_doc(), {}, log_path)

    assert not log_path.exists()


def test_runner_persists_calibration_log_relative_to_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    _persist_answered_qa_and_dispatch(
        doc=_doc(),
        user_answers_raw="1: A\n2: B\n",
        use_defaults=False,
        output_path=Path("qa") / "answered.md",
        workflow_id="aas",
        dispatcher=None,
    )

    log_path = tmp_path / "work" / "learning" / "qa-calibration.jsonl"
    assert log_path.exists()
    records = _read_jsonl(log_path)
    assert [record["final"] for record in records] == ["A) REST", "B) NoSQL"]


def test_runner_use_defaults_records_no_calibration_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    _persist_answered_qa_and_dispatch(
        doc=_doc(),
        user_answers_raw="",
        use_defaults=True,
        output_path=Path("qa") / "answered.md",
        workflow_id="aas",
        dispatcher=None,
    )

    assert not (tmp_path / "work" / "learning" / "qa-calibration.jsonl").exists()
