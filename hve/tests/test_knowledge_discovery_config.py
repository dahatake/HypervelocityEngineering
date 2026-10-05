"""FR-KD-01 / FR-KD-10: 知識源の設定と Work IQ 専用設定の削除。"""

from __future__ import annotations

import dataclasses

import pytest

from hve.__main__ import _build_config, _build_parser
from hve.config import SDKConfig

_REMOVED_OPTIONS = [
    ["--workiq-akm-review"],
    ["--no-workiq-akm-review"],
    ["--workiq-akm-ingest"],
    ["--no-workiq-akm-ingest"],
    ["--workiq-dxx", "D01"],
    ["--workiq-draft"],
    ["--workiq-draft-output-dir", "qa"],
    ["--workiq-prompt-qa", "x"],
    ["--workiq-prompt-km", "x"],
    ["--workiq-per-question-timeout", "10"],
]
_REMOVED_FIELDS = (
    "workiq_qa_enabled", "workiq_akm_review_enabled", "workiq_akm_ingest_enabled", "workiq_akm_ingest_dxx",
    "workiq_prompt_qa", "workiq_prompt_km", "workiq_draft_mode", "workiq_draft_output_dir",
    "workiq_per_question_timeout", "workiq_max_draft_questions", "workiq_priority_filter",
)
_REMOVED_ENV = (
    "WORKIQ_QA_ENABLED", "WORKIQ_AKM_REVIEW_ENABLED", "WORKIQ_AKM_INGEST_ENABLED", "WORKIQ_AKM_INGEST_DXX",
    "WORKIQ_PROMPT_QA", "WORKIQ_PROMPT_KM", "WORKIQ_DRAFT_MODE", "WORKIQ_DRAFT_OUTPUT_DIR",
    "WORKIQ_PER_QUESTION_TIMEOUT", "WORKIQ_MAX_DRAFT_QUESTIONS", "WORKIQ_PRIORITY_FILTER",
)


def _config(argv: list, monkeypatch: pytest.MonkeyPatch) -> SDKConfig:
    monkeypatch.delenv("HVE_KNOWLEDGE_SOURCES", raising=False)
    monkeypatch.delenv("WORKIQ_ENABLED", raising=False)
    return _build_config(_build_parser().parse_args(["orchestrate", "--workflow", "aas", *argv]))


def test_cli_effective_sources_order_and_dedupe(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config(["--workiq", "--knowledge-source", "confluence,workiq", "--knowledge-source", "jira"], monkeypatch)
    assert cfg.effective_knowledge_sources() == ["workiq", "confluence", "jira"]


def test_cli_without_sources_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    # FR-KD-11（v3.42）: 既定は Work IQ 有効のため、知識源を 0 件にするには --no-workiq が要る。
    assert _config([], monkeypatch).effective_knowledge_sources() == ["workiq"]
    assert _config(["--no-workiq"], monkeypatch).effective_knowledge_sources() == []


@pytest.mark.parametrize("bad", ["bad name", "-x", "a/b", "x" * 65])
def test_cli_invalid_source_name_exits_2(bad: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as err:
        _build_parser().parse_args(["orchestrate", "--workflow", "aas", f"--knowledge-source={bad}"])
    assert err.value.code == 2
    assert bad.strip() in capsys.readouterr().err


def test_env_sources_ignore_invalid_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HVE_KNOWLEDGE_SOURCES", " jira , ,bad name")
    monkeypatch.setenv("WORKIQ_ENABLED", "yes")
    cfg = SDKConfig.from_env()
    assert cfg.knowledge_sources == ["jira"]
    assert cfg.effective_knowledge_sources() == ["workiq", "jira"]


def test_effective_sources_extra_and_invalid() -> None:
    cfg = SDKConfig(knowledge_sources=["a", "bad name", "a"])
    assert cfg.effective_knowledge_sources("workiq", "a") == ["a", "workiq"]


@pytest.mark.parametrize("argv", _REMOVED_OPTIONS)
def test_removed_options_exit_2(argv: list) -> None:
    with pytest.raises(SystemExit) as err:
        _build_parser().parse_args(["orchestrate", "--workflow", "aas", *argv])
    assert err.value.code == 2


def test_removed_config_fields_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    names = {f.name for f in dataclasses.fields(SDKConfig)}
    assert not names & set(_REMOVED_FIELDS)
    for env in _REMOVED_ENV:
        monkeypatch.setenv(env, "1")
    cfg = SDKConfig.from_env()
    assert not any(hasattr(cfg, f) for f in _REMOVED_FIELDS)
    for method in ("is_workiq_qa_enabled", "is_workiq_akm_review_enabled", "is_workiq_akm_ingest_enabled"):
        assert not hasattr(cfg, method)
