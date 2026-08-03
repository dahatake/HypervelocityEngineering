"""RED contracts for the A/C/D Repository Query evaluator (FR-RQ-04)."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import closing
from functools import wraps
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATOR_PATH = REPO_ROOT / "hve-dev" / "evaluate_repository_query.py"
GOLDEN_PATH = REPO_ROOT / "hve-dev" / "repository-query-golden.json"
INDEX_PATHS = {
    "mdq": ".mdq/index.sqlite",
    "cq": {"hve": ".cq/index-hve.sqlite", "app": ".cq/index-app.sqlite"},
}

_spec = importlib.util.spec_from_file_location(
    "hve_dev_evaluate_repository_query", EVALUATOR_PATH
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"cannot load evaluator: {EVALUATOR_PATH}")
_evaluator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_evaluator)

EvaluationConfigError = _evaluator.EvaluationConfigError
GoldenSetError = _evaluator.GoldenSetError
build_default_runners = _evaluator.build_default_runners
evaluate = _evaluator.evaluate
load_golden = _evaluator.load_golden
main = _evaluator.main
MIN_AI_CREDITS = _evaluator.MIN_AI_CREDITS
EvaluationRunContractError = _evaluator.EvaluationRunContractError
require_one_shot_contract = _evaluator._require_one_shot_contract
score_result = _evaluator.score_result
REAL_QUERIES_BY_ID = {
    query["id"]: query for query in load_golden(GOLDEN_PATH, REPO_ROOT)
}

Runner = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]


def async_test(
    function: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Any]:
    """Run one async test with stdlib only; pytest-asyncio is not a dependency."""

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(function(*args, **kwargs))

    return wrapper


def _write_golden(tmp_path: Path, queries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "golden.json"
    path.write_text(
        json.dumps({"schema_version": 1, "queries": queries}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _query(
    *,
    query_id: str = "RQ-T-01",
    category: str = "cross_source",
    answerable: bool = True,
    evidence: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    required = evidence if evidence is not None else [
        {"source": "code", "path": "pkg/service.py", "anchor": "def run"}
    ]
    return {
        "id": query_id,
        "category": category,
        "scenario": "development",
        "question": f"question {query_id}",
        "profile": "hve",
        "answerable": answerable,
        "expected_status": "answered" if answerable else "insufficient_evidence",
        "required_evidence": required if answerable else [],
    }


def _result_for(query: dict[str, Any], *, arm: str) -> dict[str, Any]:
    query = REAL_QUERIES_BY_ID.get(str(query.get("id")), query)
    required = query["required_evidence"]
    if not query["answerable"]:
        return {
            "schema_version": 1,
            "status": "insufficient_evidence",
            "grounding": "No repository evidence answers this question.",
            "evidence_ids": [],
            "unresolved": ["repository evidence unavailable"],
            "evidence": [],
            "usage": {
                "llm_calls": 0 if arm == "A" else 1,
                "tool_calls": 1 if arm == "D" else 0,
                "internal_searches": 1,
                "input_tokens": 0 if arm == "A" else 10,
                "output_tokens": 0 if arm == "A" else 3,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "duration_ms": 2,
            },
        }
    evidence = [
        {
            "ref_id": f"E{index}",
            "source": item["source"],
            "path": item["path"],
            "lines": [1, 2],
            "chunk_id": f"chunk-{index}",
            "snippet": item["anchor"],
        }
        for index, item in enumerate(required, 1)
    ]
    ids = [item["ref_id"] for item in evidence]
    return {
        "schema_version": 1,
        "status": "answered",
        "grounding": " ".join(f"supported [{ref}]" for ref in ids),
        "evidence_ids": ids,
        "unresolved": [],
        "evidence": evidence,
        "usage": {
            "llm_calls": 0 if arm == "A" else 1,
            "tool_calls": 1 if arm == "D" else 0,
            "internal_searches": 1,
            "input_tokens": 0 if arm == "A" else 10,
            "output_tokens": 0 if arm == "A" else 3,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "duration_ms": 2,
        },
    }


def test_loads_the_real_composite_golden() -> None:
    queries = load_golden(GOLDEN_PATH, REPO_ROOT)

    assert len(queries) == 12
    assert {query["category"] for query in queries} == {
        "cross_source",
        "multi_document",
        "unanswerable",
    }
    assert sum(not query["answerable"] for query in queries) == 4


@pytest.mark.parametrize(
    "mutate",
    [
        lambda q: q.update(id=""),
        lambda q: q.update(category="other"),
        lambda q: q.update(profile="other"),
        lambda q: q.update(expected_status="partial"),
        # An answerable golden item must name at least one required evidence.
        lambda q: q.update(required_evidence=[]),
        lambda q: q.update(
            answerable=False,
            expected_status="insufficient_evidence",
            required_evidence=[
                {"source": "code", "path": "pkg/service.py", "anchor": "def run"}
            ],
        ),
        lambda q: q["required_evidence"][0].update(source="web"),
        lambda q: q["required_evidence"][0].update(path="../outside.py"),
        lambda q: q["required_evidence"][0].update(path="missing.py"),
        lambda q: q["required_evidence"][0].update(anchor="missing anchor"),
    ],
)
def test_golden_validation_is_fail_closed(
    tmp_path: Path, mutate: Callable[[dict[str, Any]], None]
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "def run():\n    return 1\n", encoding="utf-8"
    )
    query = _query()
    mutate(query)

    with pytest.raises(GoldenSetError):
        load_golden(_write_golden(tmp_path, [query]), tmp_path)


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "def run():\n    pass\n", encoding="utf-8"
    )
    first = _query()
    second = _query()

    with pytest.raises(GoldenSetError):
        load_golden(_write_golden(tmp_path, [first, second]), tmp_path)


def test_rejects_duplicate_questions(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "def run():\n    pass\n", encoding="utf-8"
    )
    first = _query(query_id="RQ-T-01")
    second = _query(query_id="RQ-T-02")
    second["question"] = first["question"]

    with pytest.raises(GoldenSetError):
        load_golden(_write_golden(tmp_path, [first, second]), tmp_path)


def test_rejects_an_ambiguous_anchor(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "def run():\n    pass\ndef run():\n    pass\n", encoding="utf-8"
    )

    with pytest.raises(GoldenSetError):
        load_golden(_write_golden(tmp_path, [_query()]), tmp_path)


def test_rejects_a_real_path_outside_the_repository(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("outside = True\n", encoding="utf-8")
    query = _query()
    query["required_evidence"][0]["path"] = f"../{outside.name}"

    with pytest.raises(GoldenSetError):
        load_golden(_write_golden(tmp_path, [query]), tmp_path)


def test_allows_two_queries_to_reuse_the_same_evidence(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "def run():\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "spec.md").write_text(
        "# Spec\ncontract\n", encoding="utf-8"
    )
    shared = [
        {"source": "markdown", "path": "docs/spec.md", "anchor": "contract"},
        {"source": "code", "path": "pkg/service.py", "anchor": "def run"},
    ]
    first = _query(query_id="RQ-T-01", evidence=shared)
    second = _query(query_id="RQ-T-02", evidence=shared)

    loaded = load_golden(_write_golden(tmp_path, [first, second]), tmp_path)

    assert len(loaded) == 2
    assert loaded[0]["required_evidence"] == loaded[1]["required_evidence"]


def test_scores_recall_citations_and_abstention() -> None:
    answerable = _query(
        evidence=[
            {"source": "markdown", "path": "docs/spec.md", "anchor": "contract"},
            {"source": "code", "path": "pkg/service.py", "anchor": "def run"},
        ]
    )
    partial_result = _result_for(answerable, arm="D")
    partial_result["evidence"] = partial_result["evidence"][:1]
    partial_result["evidence_ids"] = ["E1"]
    partial_result["grounding"] = "supported [E1]"

    score = score_result(answerable, partial_result)

    assert score == {
        "required_evidence": 2,
        "matched_evidence": 1,
        "required_evidence_recall": 0.5,
        "citation_validity": 1.0,
        "abstention_correct": None,
    }

    unanswerable = _query(
        query_id="RQ-UA-T",
        category="unanswerable",
        answerable=False,
    )
    abstention = score_result(unanswerable, _result_for(unanswerable, arm="D"))
    assert abstention["required_evidence_recall"] is None
    assert abstention["abstention_correct"] is True

    wrong_evidence = _result_for(answerable, arm="D")
    wrong_evidence["evidence"][1]["source"] = "code"
    wrong_evidence["evidence"][1]["path"] = "pkg/other.py"
    wrong_evidence["evidence"][1]["snippet"] = "not the required anchor"
    mismatch = score_result(answerable, wrong_evidence)
    assert mismatch["matched_evidence"] == 1
    assert mismatch["required_evidence_recall"] == 0.5

    invalid_citation = _result_for(answerable, arm="D")
    invalid_citation["evidence_ids"] = ["E1", "E99"]
    invalid_citation["grounding"] = "known [E1], unknown [E99]"
    citation_score = score_result(answerable, invalid_citation)
    assert citation_score["citation_validity"] == 0.5

    no_matches = _result_for(answerable, arm="D")
    for item in no_matches["evidence"]:
        item["source"] = "code"
        item["path"] = "pkg/wrong.py"
        item["snippet"] = "wrong"
    no_matches["evidence_ids"] = ["E99"]
    no_matches["grounding"] = "unknown [E99]"
    zero_score = score_result(answerable, no_matches)
    assert zero_score["matched_evidence"] == 0
    assert zero_score["required_evidence_recall"] == 0.0
    assert zero_score["citation_validity"] == 0.0

    false_answer = _result_for(unanswerable, arm="D")
    false_answer.update(
        status="answered",
        grounding="invented [E1]",
        evidence_ids=["E1"],
        unresolved=[],
        evidence=[
            {
                "ref_id": "E1",
                "source": "code",
                "path": "pkg/service.py",
                "lines": [1, 2],
                "chunk_id": "cq-1",
                "snippet": "def run",
            }
        ],
    )
    assert score_result(unanswerable, false_answer)["abstention_correct"] is False


def test_default_arm_a_uses_only_local_mdq_and_cq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cq import store as cq_store
    from mdq import store as mdq_store
    import hve.repository_query as runtime

    network_bundles: list[str] = []

    async def fake_repository_query(**kwargs: Any) -> dict[str, Any]:
        tools = kwargs["tools"]
        network_bundles.append(type(tools).__name__)
        rows = tools.ledger.evidence()
        evidence_ids = [str(row["ref_id"]) for row in rows]
        activity = tools.activity()
        if rows:
            status = "answered"
            grounding = "fixed " + " ".join(f"[{ref_id}]" for ref_id in evidence_ids)
            unresolved: list[str] = []
        else:
            status = "insufficient_evidence"
            grounding = "No fixed evidence."
            unresolved = ["no evidence"]
        return {
            "schema_version": 1,
            "status": status,
            "grounding": grounding,
            "evidence_ids": evidence_ids,
            "unresolved": unresolved,
            "evidence": rows,
            "usage": {
                "llm_calls": 1,
                "tool_calls": int(activity["tool_calls"]),
                "internal_searches": int(activity["internal_searches"]),
                "input_tokens": 10,
                "output_tokens": 3,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "duration_ms": 2,
            },
        }

    monkeypatch.setattr(runtime, "run_repository_query", fake_repository_query)

    (tmp_path / "docs").mkdir()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "def run_contract():\n    return 1\n", encoding="utf-8"
    )
    mdq_db = tmp_path / ".mdq" / "index.sqlite"
    with closing(mdq_store.open_store(mdq_db)) as conn:
        for index, text in enumerate(
            [
                "contract run_contract boundary",
                "unrelated alpha",
                "unrelated beta",
                "unrelated gamma",
            ],
            1,
        ):
            relative = f"docs/spec{index}.md"
            (tmp_path / relative).write_text(f"# Spec {index}\n{text}\n", encoding="utf-8")
            conn.execute(
                "INSERT INTO files(path,sha1,mtime,size_bytes,frontmatter) VALUES(?,?,?,?,?)",
                (relative, f"m{index}", 1.0, len(text), None),
            )
            conn.execute(
                "INSERT INTO chunks(chunk_id,path,heading_path,level,start_line,end_line,token_est,text) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (f"md{index}", relative, f"Spec {index}", 1, 1, 2, 4, f"# Spec {index}\n{text}"),
            )
        conn.commit()
    cq_db = tmp_path / ".cq" / "index-hve.sqlite"
    with closing(cq_store.open_store(cq_db)) as conn:
        conn.execute(
            "INSERT INTO files(path,lang,sha1,mtime,size_bytes,parser) VALUES(?,?,?,?,?,?)",
            ("pkg/service.py", "python", "c", 1.0, 32, "ast"),
        )
        conn.execute(
            "INSERT INTO chunks(chunk_id,path,start_line,end_line,text) VALUES(?,?,?,?,?)",
            ("cq1", "pkg/service.py", 1, 2, "def run_contract():\n    return 1"),
        )
        conn.commit()
    cq_app_db = tmp_path / ".cq" / "index-app.sqlite"
    (tmp_path / "src" / "app.py").write_text(
        "def app_contract():\n    return 2\n", encoding="utf-8"
    )
    with closing(cq_store.open_store(cq_app_db)) as conn:
        conn.execute(
            "INSERT INTO files(path,lang,sha1,mtime,size_bytes,parser) VALUES(?,?,?,?,?,?)",
            ("src/app.py", "python", "a", 1.0, 32, "ast"),
        )
        conn.execute(
            "INSERT INTO chunks(chunk_id,path,start_line,end_line,text) VALUES(?,?,?,?,?)",
            ("cq-app", "src/app.py", 1, 2, "def app_contract():\n    return 2"),
        )
        conn.commit()
    runners = build_default_runners(
        repo_root=tmp_path,
        mdq_db_path=mdq_db,
        cq_db_paths={"hve": cq_db, "app": cq_app_db},
    )
    query = {
        "id": "RQ-LOCAL",
        "category": "cross_source",
        "scenario": "development",
        "question": "run_contract()",
        "profile": "hve",
        "answerable": True,
        "expected_status": "answered",
        "required_evidence": [],
    }

    result = asyncio.run(
        runners["A"](
            query,
            {
                "arm": "A",
                "model": None,
                "reasoning_effort": None,
                "timeout": 30.0,
                "max_ai_credits": None,
            },
        )
    )

    assert result["usage"]["llm_calls"] == 0
    assert result["usage"]["tool_calls"] == 0
    assert {row["source"] for row in result["evidence"]} == {"markdown", "code"}

    app_query = dict(query)
    app_query.update(id="RQ-LOCAL-APP", question="app_contract()", profile="app")
    app_result = asyncio.run(
        runners["A"](
            app_query,
            {
                "arm": "A",
                "repeat": 0,
                "model": None,
                "reasoning_effort": None,
                "timeout": 30.0,
                "max_ai_credits": None,
            },
        )
    )
    code_paths = {
        row["path"] for row in app_result["evidence"] if row["source"] == "code"
    }
    assert code_paths == {"src/app.py"}

    unanswerable = dict(query)
    unanswerable.update(
        id="RQ-LOCAL-UA",
        category="unanswerable",
        answerable=False,
        expected_status="insufficient_evidence",
        required_evidence=[],
    )
    unanswerable_result = asyncio.run(
        runners["A"](
            unanswerable,
            {
                "arm": "A",
                "repeat": 1,
                "model": None,
                "reasoning_effort": None,
                "timeout": 30.0,
                "max_ai_credits": None,
            },
        )
    )
    assert unanswerable_result["usage"]["internal_searches"] == 2
    assert unanswerable_result["status"] == "answered"

    integration_query = {
        "id": "RQ-LOCAL-INTEGRATION",
        "category": "cross_source",
        "scenario": "development",
        "question": "run_contract()",
        "profile": "hve",
        "answerable": True,
        "expected_status": "answered",
        "required_evidence": [
            {
                "source": "markdown",
                "path": "docs/spec1.md",
                "anchor": "contract run_contract boundary",
            },
            {
                "source": "code",
                "path": "pkg/service.py",
                "anchor": "def run_contract",
            },
        ],
    }
    golden_path = _write_golden(tmp_path, [integration_query])

    def source_hashes_stub(root: Path) -> dict[str, str]:
        del root
        return {"test-source": "0" * 64}

    def workspace_dirty_stub(root: Path) -> bool:
        del root
        return True

    monkeypatch.setattr(
        _evaluator,
        "_source_hashes",
        source_hashes_stub,
    )
    monkeypatch.setattr(_evaluator, "_workspace_dirty", workspace_dirty_stub)
    evaluate_args = {
        "golden_path": golden_path,
        "repo_root": tmp_path,
        "runners": runners,
        "model": "gpt-5.6-sol",
        "reasoning_effort": "high",
        "repeat": 1,
        "timeout": 30.0,
        "max_ai_credits": MIN_AI_CREDITS,
        "network_enabled": True,
        "commit_sha": "abc123",
        "sdk_version": "1.0.6",
        "cli_version": "1.0.77",
        "index_paths": {
            "mdq": str(mdq_db),
            "cq": {"hve": str(cq_db), "app": str(cq_app_db)},
        },
    }
    integrated = asyncio.run(evaluate(**evaluate_args))
    a_run = integrated["queries"][0]["arms"]["A"]["runs"][0]
    c_run = integrated["queries"][0]["arms"]["C"]["runs"][0]
    assert a_run["result"]["evidence"] == c_run["result"]["evidence"]
    assert c_run["usage"]["llm_calls"] == 1
    assert c_run["usage"]["tool_calls"] == 0
    assert network_bundles == ["_OneShotBundle", "RepositoryQueryTools"]

    async def fail_frozen_preparation(
        _query: dict[str, Any], _config: dict[str, Any]
    ) -> None:
        del _query, _config
        raise RuntimeError("sensitive preparation detail")

    setattr(runners["C"], "_prepare_frozen_evidence", fail_frozen_preparation)
    network_bundles.clear()
    preparation_failure = asyncio.run(evaluate(**evaluate_args))
    failed_c = preparation_failure["queries"][0]["arms"]["C"]["runs"][0]
    assert preparation_failure["overall"]["A"]["runs"] == 1
    assert preparation_failure["overall"]["C"]["runs"] == 1
    assert preparation_failure["overall"]["D"]["runs"] == 1
    assert preparation_failure["overall"]["A"]["errors"] == 0
    assert preparation_failure["overall"]["C"]["errors"] == 1
    assert preparation_failure["overall"]["D"]["errors"] == 0
    assert failed_c["error"] == {"type": "RuntimeError"}
    assert "sensitive preparation detail" not in json.dumps(preparation_failure)
    assert network_bundles == ["RepositoryQueryTools"]

    with closing(mdq_store.open_store(mdq_db)) as conn:
        conn.execute("DELETE FROM chunks")
        conn.commit()
    with closing(cq_store.open_store(cq_db)) as conn:
        conn.execute("DELETE FROM chunks")
        conn.commit()
    refreshed = asyncio.run(
        runners["A"](
            query,
            {
                "arm": "A",
                "repeat": 0,
                "model": None,
                "reasoning_effort": None,
                "timeout": 30.0,
                "max_ai_credits": None,
            },
        )
    )
    assert refreshed["evidence"] == []
    assert refreshed["status"] == "insufficient_evidence"


def test_arm_c_requires_exactly_one_llm_call_and_no_tools() -> None:
    valid = _result_for(REAL_QUERIES_BY_ID["RQ-CS-01"], arm="C")
    require_one_shot_contract(valid)

    for field, value in (("llm_calls", 2), ("tool_calls", 1)):
        invalid = _result_for(REAL_QUERIES_BY_ID["RQ-CS-01"], arm="C")
        invalid["usage"][field] = value
        with pytest.raises(EvaluationRunContractError, match="Arm C") as excinfo:
            require_one_shot_contract(invalid)
        assert excinfo.value.usage == invalid["usage"]


def test_default_runners_reject_a_shared_cq_database(tmp_path: Path) -> None:
    shared = tmp_path / ".cq" / "index-shared.sqlite"

    with pytest.raises(EvaluationConfigError, match="distinct"):
        build_default_runners(
            repo_root=tmp_path,
            mdq_db_path=tmp_path / ".mdq" / "index.sqlite",
            cq_db_paths={"hve": shared, "app": shared},
        )


def test_cli_rejects_missing_network_opt_in_before_writing_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_json = tmp_path / "result.json"
    output_markdown = tmp_path / "result.md"

    code = main(
        [
            "--golden",
            str(GOLDEN_PATH),
            "--repo-root",
            str(REPO_ROOT),
            "--mdq-db",
            str(tmp_path / "missing-mdq.sqlite"),
            "--cq-db-hve",
            str(tmp_path / "missing-cq-hve.sqlite"),
            "--cq-db-app",
            str(tmp_path / "missing-cq-app.sqlite"),
            "--model",
            "gpt-5.6-sol",
            "--reasoning-effort",
            "high",
            "--timeout",
            "30",
            "--max-ai-credits",
            "30",
            "--commit-sha",
            "abc123",
            "--cli-version",
            "1.0.77",
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_markdown),
        ]
    )

    assert code == 2
    assert "network" in capsys.readouterr().err
    assert not output_json.exists()
    assert not output_markdown.exists()


@async_test
async def test_network_flag_is_required_before_any_runner_call() -> None:
    calls: list[str] = []

    async def runner(query: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        calls.append(query["id"])
        return _result_for(query, arm=config["arm"])

    with pytest.raises(EvaluationConfigError, match="network"):
        await evaluate(
            golden_path=GOLDEN_PATH,
            repo_root=REPO_ROOT,
            runners={"A": runner, "C": runner, "D": runner},
            model="gpt-5.6-sol",
            reasoning_effort="high",
            repeat=1,
            timeout=30.0,
            max_ai_credits=MIN_AI_CREDITS,
            network_enabled=False,
            commit_sha="abc123",
            sdk_version="1.0.6",
            cli_version="1.0.77",
            index_paths=INDEX_PATHS,
        )

    assert calls == []


@async_test
@pytest.mark.parametrize(
    "override",
    [
        {"model": ""},
        {"model": " Auto "},
        {"reasoning_effort": ""},
        {"reasoning_effort": " AUTO "},
        {"repeat": 0},
        {"timeout": 0.0},
        {"max_ai_credits": 0.0},
        {"max_ai_credits": MIN_AI_CREDITS - 0.1},
        {"commit_sha": ""},
        {"sdk_version": ""},
        {"cli_version": ""},
        {"index_paths": {}},
        {"index_paths": {"mdq": ".mdq/index.sqlite", "cq": ".cq/index.sqlite"}},
        {
            "index_paths": {
                "mdq": ".mdq/index.sqlite",
                "cq": {"hve": ".cq/index-hve.sqlite"},
            }
        },
        {
            "index_paths": {
                "mdq": ".mdq/index.sqlite",
                "cq": {
                    "hve": ".cq/index-shared.sqlite",
                    "app": ".cq/index-shared.sqlite",
                },
            }
        },
    ],
)
async def test_invalid_network_config_fails_before_any_runner_call(
    override: dict[str, object]
) -> None:
    calls: list[str] = []

    async def runner(query: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        calls.append(query["id"])
        return _result_for(query, arm=config["arm"])

    params: dict[str, Any] = {
        "golden_path": GOLDEN_PATH,
        "repo_root": REPO_ROOT,
        "runners": {"A": runner, "C": runner, "D": runner},
        "model": "gpt-5.6-sol",
        "reasoning_effort": "high",
        "repeat": 1,
        "timeout": 30.0,
        "max_ai_credits": MIN_AI_CREDITS,
        "network_enabled": True,
        "commit_sha": "abc123",
        "sdk_version": "1.0.6",
        "cli_version": "1.0.77",
        "index_paths": INDEX_PATHS,
    }
    params.update(override)

    with pytest.raises(EvaluationConfigError):
        await evaluate(**params)

    assert calls == []


@async_test
async def test_all_three_runners_are_required_before_execution() -> None:
    calls: list[str] = []

    async def runner(query: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        calls.append(query["id"])
        return _result_for(query, arm=config["arm"])

    with pytest.raises(EvaluationConfigError, match="runner"):
        await evaluate(
            golden_path=GOLDEN_PATH,
            repo_root=REPO_ROOT,
            runners={"A": runner, "C": runner},
            model="gpt-5.6-sol",
            reasoning_effort="high",
            repeat=1,
            timeout=30.0,
            max_ai_credits=MIN_AI_CREDITS,
            network_enabled=True,
            commit_sha="abc123",
            sdk_version="1.0.6",
            cli_version="1.0.77",
            index_paths=INDEX_PATHS,
        )

    assert calls == []


@async_test
async def test_runs_arms_in_rotated_order_with_comparable_conditions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []
    clock_calls = 0

    def clock() -> float:
        nonlocal clock_calls
        pair, offset = divmod(clock_calls, 2)
        clock_calls += 1
        return float(pair) + (0.007 if offset else 0.0)

    monkeypatch.setattr(_evaluator, "_clock", clock, raising=False)

    def make_runner(arm: str) -> Runner:
        async def runner(
            query: dict[str, Any], _config: dict[str, Any]
        ) -> dict[str, Any]:
            assert set(query) == {"id", "question", "scenario", "profile"}
            calls.append((query["id"], arm, dict(_config)))
            return _result_for(query, arm=arm)

        return runner

    report = await evaluate(
        golden_path=GOLDEN_PATH,
        repo_root=REPO_ROOT,
        runners={"A": make_runner("A"), "C": make_runner("C"), "D": make_runner("D")},
        model="gpt-5.6-sol",
        reasoning_effort="high",
        repeat=1,
        timeout=30.0,
        max_ai_credits=MIN_AI_CREDITS,
        network_enabled=True,
        commit_sha="abc123",
        sdk_version="1.0.6",
        cli_version="1.0.77",
        index_paths=INDEX_PATHS,
    )

    assert [(query_id, arm) for query_id, arm, _ in calls[:9]] == [
        ("RQ-CS-01", "A"),
        ("RQ-CS-01", "C"),
        ("RQ-CS-01", "D"),
        ("RQ-CS-02", "C"),
        ("RQ-CS-02", "D"),
        ("RQ-CS-02", "A"),
        ("RQ-CS-03", "D"),
        ("RQ-CS-03", "A"),
        ("RQ-CS-03", "C"),
    ]
    assert len(calls) == 12 * 3
    for _, arm, config in calls:
        assert config["arm"] == arm
        assert config["timeout"] == 30.0
        if arm == "A":
            assert config["model"] is None
            assert config["reasoning_effort"] is None
            assert config["max_ai_credits"] is None
        else:
            assert config["model"] == "gpt-5.6-sol"
            assert config["reasoning_effort"] == "high"
            assert config["max_ai_credits"] == MIN_AI_CREDITS

    assert report["schema_version"] == 1
    assert len(report["queries"]) == 12
    assert set(report["categories"]) == {
        "cross_source",
        "multi_document",
        "unanswerable",
    }
    assert set(report["overall"]) == {"A", "C", "D"}
    for arm in ("A", "C", "D"):
        overall = report["overall"][arm]
        assert overall["runs"] == 12
        assert overall["errors"] == 0
        assert overall["error_rate"] == 0.0
        assert overall["cap_aborts"] == 0
        assert overall["cap_rate"] == 0.0
        assert overall["required_evidence_recall"] == 1.0
        assert overall["citation_validity"] == 1.0
        assert overall["abstention_accuracy"] == 1.0
        assert overall["usage"]["outer_interactions"] == 12
        assert overall["usage"]["internal_searches"] == 12
        assert overall["usage"]["duration_ms"] == 84
    assert report["overall"]["A"]["usage"]["llm_calls"] == 0
    assert report["overall"]["A"]["usage"]["tool_calls"] == 0
    assert report["overall"]["C"]["usage"]["llm_calls"] == 12
    assert report["overall"]["C"]["usage"]["tool_calls"] == 0
    assert report["overall"]["D"]["usage"]["llm_calls"] == 12
    assert report["overall"]["D"]["usage"]["tool_calls"] == 12
    assert report["overall"]["C"]["usage"]["input_tokens"] == 120
    assert report["overall"]["D"]["usage"]["output_tokens"] == 36
    for category in ("cross_source", "multi_document", "unanswerable"):
        assert set(report["categories"][category]) == {"A", "C", "D"}
        for arm in ("A", "C", "D"):
            assert report["categories"][category][arm]["runs"] == 4
    for query_report in report["queries"]:
        assert set(query_report["arms"]) == {"A", "C", "D"}
        assert len(query_report["arms"]["A"]["runs"]) == 1
        assert len(query_report["arms"]["C"]["runs"]) == 1
        assert len(query_report["arms"]["D"]["runs"]) == 1
        for arm in ("A", "C", "D"):
            summary = query_report["arms"][arm]["summary"]
            assert summary["runs"] == 1
            assert summary["errors"] == 0
            assert summary["error_rate"] == 0.0
            assert summary["cap_rate"] == 0.0
        a_run = query_report["arms"]["A"]["runs"][0]
        c_run = query_report["arms"]["C"]["runs"][0]
        assert a_run["result"]["evidence"] == c_run["result"]["evidence"]
        assert a_run["usage"]["duration_ms"] == 7
        assert c_run["usage"]["duration_ms"] == 7
        assert a_run["result"]["usage"]["duration_ms"] == 2
        assert a_run["result"]["usage"]["llm_calls"] == 0
        assert c_run["result"]["usage"]["llm_calls"] == 1
        assert c_run["result"]["usage"]["tool_calls"] == 0
    assert "go" not in report and "judge" not in report
    provenance = report["provenance"]
    assert provenance["model"] == "gpt-5.6-sol"
    assert provenance["reasoning_effort"] == "high"
    assert provenance["sdk_version"] == "1.0.6"
    assert provenance["cli_version"] == "1.0.77"
    assert provenance["commit_sha"] == "abc123"
    assert provenance["golden_sha256"] == hashlib.sha256(GOLDEN_PATH.read_bytes()).hexdigest()
    assert provenance["index_paths"] == INDEX_PATHS
    assert provenance["arms"] == {
        "A": {"model": None, "reasoning_effort": None},
        "C": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
        "D": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    }
    assert provenance["duration_basis"] == "host_wall_clock_ms"
    assert "prepared before timing" in provenance["measurement_boundaries"]["C"]
    assert isinstance(provenance["workspace_dirty"], bool)
    assert set(provenance["source_sha256"]) == {
        "hve/repository_query.py",
        "hve/repository_query_tools.py",
        "hve-dev/evaluate_repository_query.py",
        "hve/tests/test_repository_query.py",
        "hve/tests/test_repository_query_tools.py",
        "hve/tests/test_repository_query_evaluation.py",
    }
    assert all(
        len(value) == 64 for value in provenance["source_sha256"].values()
    )


@async_test
async def test_repeat_two_keeps_every_run_and_rotates_the_starting_arm() -> None:
    calls: list[tuple[str, str]] = []

    def make_runner(arm: str) -> Runner:
        async def runner(
            query: dict[str, Any], _config: dict[str, Any]
        ) -> dict[str, Any]:
            del _config
            calls.append((query["id"], arm))
            return _result_for(query, arm=arm)

        return runner

    report = await evaluate(
        golden_path=GOLDEN_PATH,
        repo_root=REPO_ROOT,
        runners={"A": make_runner("A"), "C": make_runner("C"), "D": make_runner("D")},
        model="gpt-5.6-sol",
        reasoning_effort="high",
        repeat=2,
        timeout=30.0,
        max_ai_credits=MIN_AI_CREDITS,
        network_enabled=True,
        commit_sha="abc123",
        sdk_version="1.0.6",
        cli_version="1.0.77",
        index_paths=INDEX_PATHS,
    )

    assert len(calls) == 12 * 3 * 2
    arm_order = ("A", "C", "D")
    expected_calls: list[tuple[str, str]] = []
    query_ids = [query["id"] for query in load_golden(GOLDEN_PATH, REPO_ROOT)]
    for query_index, query_id in enumerate(query_ids):
        for repeat_index in range(2):
            start = (query_index + repeat_index) % len(arm_order)
            expected_calls.extend(
                (query_id, arm_order[(start + offset) % len(arm_order)])
                for offset in range(len(arm_order))
            )
    assert calls == expected_calls
    assert report["overall"]["A"]["runs"] == 24
    assert report["overall"]["C"]["runs"] == 24
    assert report["overall"]["D"]["runs"] == 24


@async_test
async def test_runner_failures_are_measured_not_dropped() -> None:
    calls = 0
    failure_usage = {
        "llm_calls": 2,
        "tool_calls": 1,
        "internal_searches": 3,
        "input_tokens": 40,
        "output_tokens": 8,
        "cache_read_tokens": 10,
        "cache_write_tokens": 0,
        "duration_ms": 9,
    }

    class MeasuredFailure(RuntimeError):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.usage = dict(failure_usage)

    async def failing(query: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if config["arm"] == "D" and query["id"] == "RQ-CS-01":
            raise MeasuredFailure("synthetic failure")
        return _result_for(query, arm=config["arm"])

    report = await evaluate(
        golden_path=GOLDEN_PATH,
        repo_root=REPO_ROOT,
        runners={"A": failing, "C": failing, "D": failing},
        model="gpt-5.6-sol",
        reasoning_effort="high",
        repeat=1,
        timeout=30.0,
        max_ai_credits=MIN_AI_CREDITS,
        network_enabled=True,
        commit_sha="abc123",
        sdk_version="1.0.6",
        cli_version="1.0.77",
        index_paths=INDEX_PATHS,
    )

    assert calls == 36
    assert report["overall"]["D"]["runs"] == 12
    assert report["overall"]["D"]["errors"] == 1
    assert report["overall"]["D"]["error_rate"] == pytest.approx(1 / 12)
    total_required = sum(
        len(query["required_evidence"])
        for query in load_golden(GOLDEN_PATH, REPO_ROOT)
    )
    failed_required = len(
        load_golden(GOLDEN_PATH, REPO_ROOT)[0]["required_evidence"]
    )
    assert report["overall"]["D"]["required_evidence_recall"] == pytest.approx(
        (total_required - failed_required) / total_required
    )
    assert report["overall"]["D"]["citation_validity"] == pytest.approx(7 / 8)
    assert report["overall"]["D"]["abstention_accuracy"] == 1.0
    failed = report["queries"][0]["arms"]["D"]["runs"][0]
    failed_summary = report["queries"][0]["arms"]["D"]["summary"]
    assert failed_summary["runs"] == 1
    assert failed_summary["errors"] == 1
    assert failed_summary["error_rate"] == 1.0
    assert failed_summary["required_evidence_recall"] == 0.0
    assert failed["error"]["type"] == "MeasuredFailure"
    assert {
        key: value for key, value in failed["usage"].items() if key != "duration_ms"
    } == {
        key: value for key, value in failure_usage.items() if key != "duration_ms"
    }
    assert failed["usage"]["duration_ms"] >= 0
    assert report["overall"]["D"]["usage"]["llm_calls"] == 13
    assert report["overall"]["D"]["usage"]["input_tokens"] == 150
    assert "message" not in failed["error"]
    assert "synthetic failure" not in json.dumps(report)


@async_test
async def test_abstention_accuracy_is_calculated_across_all_unanswerable_queries() -> None:
    async def runner(query: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        result = _result_for(query, arm=config["arm"])
        if config["arm"] == "D" and query["id"] == "RQ-UA-01":
            result.update(
                status="answered",
                grounding="invented [E1]",
                evidence_ids=["E1"],
                unresolved=[],
                evidence=[
                    {
                        "ref_id": "E1",
                        "source": "code",
                        "path": "pkg/service.py",
                        "lines": [1, 2],
                        "chunk_id": "cq-1",
                        "snippet": "invented",
                    }
                ],
            )
        return result

    report = await evaluate(
        golden_path=GOLDEN_PATH,
        repo_root=REPO_ROOT,
        runners={"A": runner, "C": runner, "D": runner},
        model="gpt-5.6-sol",
        reasoning_effort="high",
        repeat=1,
        timeout=30.0,
        max_ai_credits=MIN_AI_CREDITS,
        network_enabled=True,
        commit_sha="abc123",
        sdk_version="1.0.6",
        cli_version="1.0.77",
        index_paths=INDEX_PATHS,
    )

    assert report["overall"]["A"]["abstention_accuracy"] == 1.0
    assert report["overall"]["C"]["abstention_accuracy"] == 1.0
    assert report["overall"]["D"]["abstention_accuracy"] == 0.75
    assert report["categories"]["unanswerable"]["D"]["abstention_accuracy"] == 0.75


@async_test
async def test_cap_abort_is_counted_and_sanitized() -> None:
    cap_usage = {
        "llm_calls": 11,
        "tool_calls": 6,
        "internal_searches": 9,
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_tokens": 50,
        "cache_write_tokens": 0,
        "duration_ms": 30,
    }

    class SyntheticCapError(RuntimeError):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.cap_name = "llm_calls"
            self.limit = 10
            self.actual = 11
            self.usage = dict(cap_usage)

    async def runner(query: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        if config["arm"] == "D" and query["id"] == "RQ-CS-01":
            raise SyntheticCapError("sensitive cap detail")
        return _result_for(query, arm=config["arm"])

    report = await evaluate(
        golden_path=GOLDEN_PATH,
        repo_root=REPO_ROOT,
        runners={"A": runner, "C": runner, "D": runner},
        model="gpt-5.6-sol",
        reasoning_effort="high",
        repeat=1,
        timeout=30.0,
        max_ai_credits=MIN_AI_CREDITS,
        network_enabled=True,
        commit_sha="abc123",
        sdk_version="1.0.6",
        cli_version="1.0.77",
        index_paths=INDEX_PATHS,
    )

    assert report["overall"]["D"]["runs"] == 12
    assert report["overall"]["D"]["errors"] == 1
    assert report["overall"]["D"]["cap_aborts"] == 1
    assert report["overall"]["D"]["cap_rate"] == pytest.approx(1 / 12)
    assert report["categories"]["cross_source"]["D"]["runs"] == 4
    assert report["categories"]["cross_source"]["D"]["cap_aborts"] == 1
    assert report["categories"]["cross_source"]["D"]["cap_rate"] == 0.25
    failed = report["queries"][0]["arms"]["D"]["runs"][0]
    failed_summary = report["queries"][0]["arms"]["D"]["summary"]
    assert failed_summary["cap_aborts"] == 1
    assert failed_summary["cap_rate"] == 1.0
    assert failed["error"] == {
        "type": "cap_exceeded",
        "cap_name": "llm_calls",
        "limit": 10,
        "actual": 11,
    }
    assert {
        key: value for key, value in failed["usage"].items() if key != "duration_ms"
    } == {key: value for key, value in cap_usage.items() if key != "duration_ms"}
    assert failed["usage"]["duration_ms"] >= 0
    assert report["overall"]["D"]["usage"]["llm_calls"] == 22
    assert "sensitive cap detail" not in json.dumps(report)
