"""NFR-CQ-01: 応答トークン予算を返却ペイロード全体で見積もること（RED）。

予算の消費量は「抜粋の長さ」ではなく「実際に返す 1 ヒット分の機械可読表現の全体」
で見積もる。メタデータ（path / lines / route / score / parser / chunk_id / signature）
は 1 ヒットあたり無視できない量を占めるため、抜粋だけで数えると予算が空洞化する。

見積りは `users-guide/skills-code-query.md` が明記する「文字数 ÷ 4 の概算」を用いる。
検索経路へ任意依存のトークナイザを持ち込まない、という NFR-CQ-01 の制約を守るため。
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest

from cq import config, indexer, search

_DB = Path(".cq") / "index-test.sqlite"
_MARKER = "budgetmarker"
_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    for index in range(6):
        (tmp_path / "pkg" / f"module_{index}.py").write_text(
            f"def handler_{index}(payload):\n"
            f'    return "{_MARKER}"\n',
            encoding="utf-8",
        )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / _DB)
    return tmp_path


def _search(repo: Path, **kwargs):
    return search.search(repo, "test", db_path=repo / _DB, **kwargs)


def _payload_tokens(hits) -> int:
    """返却ペイロードの概算トークン数（文字数 ÷ 4）。"""
    return sum(
        max(1, len(json.dumps(hit.to_dict(), ensure_ascii=True)) // 4) for hit in hits
    )


def test_budget_accounts_for_the_whole_payload(repo: Path) -> None:
    """2 件以上返すなら、返却ペイロード全体が予算内に収まる。"""
    budget = 100
    hits = _search(repo, query=_MARKER, max_tokens=budget)
    assert hits
    if len(hits) > 1:
        assert _payload_tokens(hits) <= budget, (
            f"抜粋だけで見積もっているため予算を超えている: "
            f"{_payload_tokens(hits)} > {budget}（{len(hits)} 件）"
        )


def test_budget_accounts_for_the_whole_payload_in_chunk_unit(repo: Path) -> None:
    budget = 200
    hits = _search(repo, query=_MARKER, max_tokens=budget, return_unit="chunk")
    assert hits
    if len(hits) > 1:
        assert _payload_tokens(hits) <= budget


def test_first_hit_survives_a_tiny_budget(repo: Path) -> None:
    """先頭 1 件は上限を超えても返す（既存仕様の維持）。"""
    hits = _search(repo, query=_MARKER, max_tokens=1)
    assert len(hits) == 1


def test_a_larger_budget_never_returns_fewer_hits(repo: Path) -> None:
    small = _search(repo, query=_MARKER, max_tokens=100)
    large = _search(repo, query=_MARKER, max_tokens=100000)
    assert len(large) >= len(small)


def test_search_module_does_not_import_a_tokenizer() -> None:
    """見積りのために任意依存のトークナイザを検索経路へ導入しない。"""
    tree = ast.parse((_REPO_ROOT / "cq" / "search.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
            imported.update(alias.name for alias in node.names)
    assert "tiktoken" not in imported
    assert "tokens" not in imported, "cq.tokens を検索経路へ持ち込んでいる"
