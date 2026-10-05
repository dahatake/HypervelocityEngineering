"""FR-INPUT-03 — docs-original 候補提示の決定性・縮退契約。"""

from __future__ import annotations

from pathlib import Path

from hve.step_inputs import find_docs_original_candidates


def _write(root: Path, relative: str, text: str = "x") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_mdq_results_are_confined_filename_first_and_limited(tmp_path: Path) -> None:
    for index in range(12):
        _write(tmp_path, f"docs-original/{index:02d}-orders.md")

    def searcher(query: str, paths: tuple[str, ...], limit: int):
        assert query == "00-orders"
        assert paths == ("docs-original/**",)
        assert limit == 10
        return [
            {"path": "docs/escape.md", "score": 999},
            {"path": "docs-original/11-orders.md", "score": 1},
            {"path": "docs-original/00-orders.md", "score": 1},
        ]

    result = find_docs_original_candidates(
        tmp_path, "00-orders", limit=10, searcher=searcher
    )

    assert result.source == "mdq"
    assert [item.path for item in result.candidates] == [
        "docs-original/00-orders.md",
        "docs-original/11-orders.md",
    ]
    assert all(item.path.startswith("docs-original/") for item in result.candidates)


def test_search_failure_falls_back_to_posix_path_order(tmp_path: Path) -> None:
    _write(tmp_path, "docs-original/zeta.md")
    _write(tmp_path, "docs-original/alpha.md")
    _write(tmp_path, "docs-original/sub/beta.md")

    def broken(*_args):
        raise RuntimeError("stale index")

    result = find_docs_original_candidates(
        tmp_path, "anything", limit=10, searcher=broken
    )

    assert result.source == "filesystem-fallback"
    assert "stale index" in result.warning
    assert "filesystem" in result.warning
    assert [item.path for item in result.candidates] == [
        "docs-original/alpha.md",
        "docs-original/sub/beta.md",
        "docs-original/zeta.md",
    ]


def test_zero_candidates_is_a_normal_result(tmp_path: Path) -> None:
    result = find_docs_original_candidates(tmp_path, "nothing", searcher=lambda *_: [])

    assert result.candidates == ()
    assert result.source == "mdq"
