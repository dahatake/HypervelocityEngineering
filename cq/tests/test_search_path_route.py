"""FR-CQ-06: 全経路が 0 件のときにファイルパスの部分一致で引く検索層（RED）。

`chunks_fts` の索引列は本文・名称・シグネチャ・識別子語のみで、リポジトリ相対パスを
含まない。そのためテストモジュール名やスタックトレースのパス断片からは到達できない。
全層が 0 件のときに限り、最後にパスの部分一致で引く。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cq import config, indexer, search

_DB = Path(".cq") / "index-test.sqlite"


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "nested").mkdir(parents=True)
    # パスにだけ現れる語。本文には一切出さない。定義 2 つでチャンクが 2 つになる。
    (tmp_path / "pkg" / "zeta_marker_module.py").write_text(
        "def first_helper():\n"
        "    return 1\n"
        "\n"
        "\n"
        "def second_helper():\n"
        "    return 2\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "nested" / "zeta_marker_other.py").write_text(
        "def third_helper():\n    return 3\n", encoding="utf-8"
    )
    # 本文にもパスにも現れる語。既存層が先に引けることの対照。
    (tmp_path / "pkg" / "ledger_service.py").write_text(
        "def ledger_service_entry():\n    return 0\n", encoding="utf-8"
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / _DB)
    return tmp_path


def _search(repo: Path, **kwargs):
    return search.search(repo, "test", db_path=repo / _DB, **kwargs)


def test_token_that_appears_only_in_a_path_is_reachable(repo: Path) -> None:
    hits = _search(repo, query="zeta_marker_module")
    assert hits, "パスにしか現れない語へ到達できない"
    assert hits[0].path == "pkg/zeta_marker_module.py"
    assert hits[0].route == "path"


def test_path_hit_carries_the_documented_response_fields(repo: Path) -> None:
    hits = _search(repo, query="zeta_marker_module")
    assert hits
    payload = hits[0].to_dict()
    assert payload["path"] == "pkg/zeta_marker_module.py"
    assert isinstance(payload["lines"], list) and len(payload["lines"]) == 2
    assert payload["lines"][0] <= payload["lines"][1]
    assert payload["snippet"], "抜粋が空"
    assert payload["parser"], "パーサフィデリティが空"
    assert payload["route"] == "path"


def test_path_hit_returns_the_first_chunk_of_the_file(repo: Path) -> None:
    """ファイル先頭のチャンクを返す（どのチャンクでもよいわけではない）。"""
    hits = _search(repo, query="zeta_marker_module")
    assert hits
    assert hits[0].lines[0] == 1, f"先頭チャンクではない: {hits[0].lines}"
    assert hits[0].snippet.startswith("def first_helper():")


def test_path_layer_returns_one_hit_per_file(repo: Path) -> None:
    """2 チャンクあるファイルでも 1 件へ畳む。順序はパス長の昇順で決定的。"""
    hits = _search(repo, query="zeta_marker")
    assert [h.path for h in hits] == [
        "pkg/zeta_marker_module.py",
        "pkg/nested/zeta_marker_other.py",
    ], f"ファイルごとに 1 件へ畳めていないか順序が不定: {[(h.path, h.lines) for h in hits]}"


def test_other_layers_win_over_the_path_layer(repo: Path) -> None:
    """本文で引ける語ではパス層へ落ちない。"""
    hits = _search(repo, query="ledger_service_entry")
    assert hits
    assert hits[0].route == "symbol"


def test_short_query_does_not_reach_the_path_layer(repo: Path) -> None:
    """最小長未満では試行せず、エラーにもしない。"""
    assert _search(repo, query="ze") == []


def test_paths_filter_applies_to_the_path_layer(repo: Path) -> None:
    hits = _search(repo, query="zeta_marker", paths="pkg/nested/*")
    assert [h.path for h in hits] == ["pkg/nested/zeta_marker_other.py"]


def test_path_layer_is_last_in_the_fallback_chain(repo: Path) -> None:
    """パスにも本文にも無い語は 0 件のまま。"""
    assert _search(repo, query="zzabsenteverywhere") == []


def test_path_layer_is_not_selectable_as_an_explicit_mode(repo: Path) -> None:
    """fallback 連鎖専用の層であり、`--mode path` は存在しない。"""
    assert "path" not in search.ROUTES
    with pytest.raises(search.SearchError):
        _search(repo, query="zeta_marker", mode="path")
