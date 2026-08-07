"""FR-CQ-09: 俯瞰出力の予算判定を「実際に出力する文字列全体」で行うこと（RED）。

`build()` は掲載する定義行だけを数えているが、`render()` はファイル見出し・折り畳み
記号・区切りの空行・除外件数の通知を付加する。定義行だけで予算を判定すると、
実際の出力は予算を超える。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cq import config, indexer, repomap, tokens

_DB = Path(".cq") / "index-test.sqlite"
_DEFINITIONS = 60


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "cq.toml").write_text(
        "[profiles.test]\nroots = ['pkg']\n", encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "api.py").write_text(
        "\n\n".join(
            f"def operation_{index}(payload):\n    return payload + {index}"
            for index in range(_DEFINITIONS)
        )
        + "\n",
        encoding="utf-8",
    )
    # 被参照数を付けて順位付けを成立させる（自ファイル内参照は数えられない）。
    calls = " + ".join(f"operation_{index}(0)" for index in range(_DEFINITIONS))
    (tmp_path / "pkg" / "client.py").write_text(
        f"def use_everything():\n    return {calls}\n", encoding="utf-8"
    )
    profile = config.resolve_profile(tmp_path, "test")
    indexer.build_index(tmp_path, profile, db_path=tmp_path / _DB)
    return tmp_path


def _build(repo: Path, budget: int):
    return repomap.build(repo / _DB, max_tokens=budget)


@pytest.mark.parametrize("budget", [200, 400, 1200])
def test_rendered_output_fits_the_budget(repo: Path, budget: int) -> None:
    built = _build(repo, budget)
    rendered = repomap.render(built)
    assert tokens.count_tokens(rendered) <= budget, (
        f"実際の出力が予算を超えている: "
        f"{tokens.count_tokens(rendered)} > {budget}（掲載 {len(built.entries)} 件）"
    )


def test_budget_is_not_satisfied_by_dropping_everything(repo: Path) -> None:
    built = _build(repo, 400)
    assert built.entries, "予算内に収めるために掲載 0 件にしている"


def test_dropped_notice_is_inside_the_budget(repo: Path) -> None:
    """除外件数の通知行も予算に含める。"""
    budget = 200
    built = _build(repo, budget)
    rendered = repomap.render(built)
    assert built.dropped > 0, "この予算では除外が発生するはず（fixture の前提）"
    assert "# dropped" in rendered
    assert tokens.count_tokens(rendered) <= budget


def test_self_reported_tokens_do_not_exceed_the_budget(repo: Path) -> None:
    built = _build(repo, 400)
    assert built.tokens <= 400


def test_a_larger_budget_never_shows_fewer_entries(repo: Path) -> None:
    assert len(_build(repo, 1200).entries) >= len(_build(repo, 200).entries)


def test_body_is_never_included(repo: Path) -> None:
    rendered = repomap.render(_build(repo, 1200))
    assert "return payload" not in rendered
