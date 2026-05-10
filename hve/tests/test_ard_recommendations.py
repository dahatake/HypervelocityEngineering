from __future__ import annotations

import textwrap
from pathlib import Path

from hve.ard_recommendations import Recommendation, annotate_with_ids, parse_recommendations


def _write_markdown(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "company-business-requirement.md"
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return path


def test_parse_table_format(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        # Title

        ## 6. Strategic Recommendations

        ### 6.1 推奨戦略
        | No. | 推奨戦略 | 根拠 |
        | --- | --- | --- |
        | 1 | 戦略A | 根拠A |
        | 2 | 戦略B | 根拠B |
        """,
    )

    recommendations = parse_recommendations(path)

    assert recommendations == [
        Recommendation(id="SR-1", title="戦略A", rationale="根拠A", source_line=8),
        Recommendation(id="SR-2", title="戦略B", rationale="根拠B", source_line=9),
    ]


def test_parse_heading_format(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        ## 6. Strategic Recommendations

        ### 推奨戦略A
        説明A

        ### 推奨戦略B
        説明B
        """,
    )

    recommendations = parse_recommendations(path)

    assert [item.id for item in recommendations] == ["SR-1", "SR-2"]
    assert [item.title for item in recommendations] == ["推奨戦略A", "推奨戦略B"]
    assert all(item.rationale == "" for item in recommendations)


def test_parse_paragraph_format(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        ## 6. Strategic Recommendations

        ### 推奨戦略と根拠

        **(1) タイトルA**
        説明A

        **(2) タイトルB**
        説明B

        ### 実行ステップ
        後続情報
        """,
    )

    recommendations = parse_recommendations(path)

    assert [item.id for item in recommendations] == ["SR-1", "SR-2"]
    assert [item.title for item in recommendations] == ["タイトルA", "タイトルB"]


def test_parse_section_with_japanese_label(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        ## 6. Strategic Recommendations（戦略提言）

        ### 推奨戦略A
        内容
        """,
    )

    recommendations = parse_recommendations(path)

    assert len(recommendations) == 1
    assert recommendations[0].title == "推奨戦略A"


def test_parse_no_section_returns_empty(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        ## 5. Gap Analysis
        内容
        """,
    )

    assert parse_recommendations(path) == []


def test_parse_nonexistent_file_returns_empty(tmp_path: Path) -> None:
    assert parse_recommendations(tmp_path / "missing.md") == []


def test_idempotent_existing_ids(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        ## 6. Strategic Recommendations

        ### [SR-1] 推奨戦略A
        説明A

        ### [SR-2] 推奨戦略B
        説明B
        """,
    )

    recommendations = parse_recommendations(path)

    assert [item.id for item in recommendations] == ["SR-1", "SR-2"]
    assert [item.title for item in recommendations] == ["推奨戦略A", "推奨戦略B"]


def test_annotate_writes_ids_to_table(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        ## 6. Strategic Recommendations

        ### 6.1 推奨戦略
        | No. | 推奨戦略 | 根拠 |
        | --- | --- | --- |
        | 1 | 戦略A | 根拠A |
        | 2 | 戦略B | 根拠B |
        """,
    )

    recommendations = annotate_with_ids(path)
    content = path.read_text(encoding="utf-8")

    assert [item.id for item in recommendations] == ["SR-1", "SR-2"]
    assert "[SR-1] 戦略A" in content
    assert "[SR-2] 戦略B" in content


def test_assign_ids_avoids_collision_with_later_existing_ids(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        ## 6. Strategic Recommendations

        ### 推奨戦略A
        説明A

        ### [SR-1] 推奨戦略B
        説明B

        ### [SR-3] 推奨戦略C
        説明C
        """,
    )

    recommendations = parse_recommendations(path)

    assert [item.id for item in recommendations] == ["SR-2", "SR-1", "SR-3"]
    assert len({item.id for item in recommendations}) == 3


def test_annotate_idempotent(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        ## 6. Strategic Recommendations

        ### 推奨戦略A
        説明A
        """,
    )

    first = annotate_with_ids(path)
    first_content = path.read_text(encoding="utf-8")
    second = annotate_with_ids(path)
    second_content = path.read_text(encoding="utf-8")

    assert first == second
    assert first_content == second_content
    assert second_content.count("[SR-1]") == 1


def test_annotate_returns_recommendations(tmp_path: Path) -> None:
    path = _write_markdown(
        tmp_path,
        """
        ## 6. Strategic Recommendations

        **(1) タイトルA**
        説明A
        """,
    )

    annotated = annotate_with_ids(path)

    assert annotated == parse_recommendations(path)
