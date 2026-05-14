"""hve/split_fork.py のユニットテスト。

SPLIT_REQUIRED サブタスク fork 機構の純粋ロジック部分を検証する。
SDK 依存なし、tmp_path のみ使用。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hve.split_fork import (
    SubIssueDef,
    SubIssuesParseError,
    build_subtask_prompt,
    check_subtask_completion,
    discover_subissues_md,
    make_subtask_work_subdir,
    parse_subissues_md,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

_VALID_SUBISSUES = """\
<!-- parent_issue: 42 -->

> 説明文

<!-- subissue -->
<!-- title: First Sub Task -->
<!-- labels: hve, split-fork -->
<!-- custom_agent: Arch-UI-Detail -->
## Sub-001
- Title: 画面定義書 S001
- AC: docs/screen/S001-*.md を生成
- 根拠: docs/catalog/screen-catalog.md
- context_size: small
- 依存: なし

---

<!-- subissue -->
<!-- title: Second Sub Task -->
<!-- labels: hve -->
<!-- custom_agent: Arch-UI-Detail -->
<!-- depends_on: 1 -->
## Sub-002
- Title: 画面定義書 S002
- AC: docs/screen/S002-*.md を生成
- context_size: small

<!-- subissue -->
<!-- title: Third Sub Task -->
<!-- depends_on: 1,2 -->
## Sub-003
- Title: 第3サブタスク
"""


# ---------------------------------------------------------------------------
# parse_subissues_md
# ---------------------------------------------------------------------------

class TestParseSubissues:
    def test_valid_3_blocks(self, tmp_path: Path):
        p = tmp_path / "subissues.md"
        p.write_text(_VALID_SUBISSUES, encoding="utf-8")
        result = parse_subissues_md(p)
        assert len(result) == 3
        assert result[0].index == 1
        assert result[0].title == "First Sub Task"
        assert result[0].labels == ["hve", "split-fork"]
        assert result[0].custom_agent == "Arch-UI-Detail"
        assert result[0].depends_on == []
        assert result[1].depends_on == [1]
        assert result[2].depends_on == [1, 2]
        assert result[2].custom_agent is None

    def test_body_contains_h2_section(self, tmp_path: Path):
        p = tmp_path / "subissues.md"
        p.write_text(_VALID_SUBISSUES, encoding="utf-8")
        result = parse_subissues_md(p)
        assert "## Sub-001" in result[0].body
        assert "AC: docs/screen/S001-*.md を生成" in result[0].body
        # メタコメント行は body に含まれないこと
        assert "<!-- title:" not in result[0].body

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(SubIssuesParseError, match="見つかりません"):
            parse_subissues_md(tmp_path / "nonexistent.md")

    def test_no_subissue_marker_raises(self, tmp_path: Path):
        p = tmp_path / "subissues.md"
        p.write_text("<!-- parent_issue: 42 -->\n\nno blocks here\n", encoding="utf-8")
        with pytest.raises(SubIssuesParseError, match="ブロックが 0 件"):
            parse_subissues_md(p)

    def test_missing_title_raises(self, tmp_path: Path):
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- subissue -->\n<!-- labels: x -->\n## Sub-001\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError, match="title.*見つかりません"):
            parse_subissues_md(p)

    def test_empty_title_raises(self, tmp_path: Path):
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- subissue -->\n<!-- title:  -->\n## Sub-001\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError, match="title が空"):
            parse_subissues_md(p)

    def test_placeholder_title_raises(self, tmp_path: Path):
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- subissue -->\n<!-- title: {REPLACE_ME_TITLE} -->\n## Sub-001\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError, match="プレースホルダ"):
            parse_subissues_md(p)

    def test_invalid_depends_on_raises(self, tmp_path: Path):
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- subissue -->\n<!-- title: A -->\n<!-- depends_on: abc -->\n## Sub-001\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError, match="depends_on"):
            parse_subissues_md(p)

    def test_forward_reference_raises(self, tmp_path: Path):
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- subissue -->\n<!-- title: A -->\n<!-- depends_on: 2 -->\n## Sub-001\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError, match="前方参照"):
            parse_subissues_md(p)

    def test_crlf_handling(self, tmp_path: Path):
        p = tmp_path / "subissues.md"
        crlf_content = _VALID_SUBISSUES.replace("\n", "\r\n")
        p.write_bytes(crlf_content.encode("utf-8"))
        result = parse_subissues_md(p)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# discover_subissues_md
# ---------------------------------------------------------------------------

class TestDiscoverSubissues:
    def test_custom_agent_mode(self, tmp_path: Path):
        agent_issue = tmp_path / "Arch-UI-Detail" / "Issue-screen-detail"
        agent_issue.mkdir(parents=True)
        target = agent_issue / "subissues.md"
        target.write_text(_VALID_SUBISSUES, encoding="utf-8")

        found = discover_subissues_md(tmp_path, "Arch-UI-Detail", "2.1")
        assert found == target

    def test_non_agent_mode(self, tmp_path: Path):
        issue_dir = tmp_path / "Issue-42"
        issue_dir.mkdir(parents=True)
        target = issue_dir / "subissues.md"
        target.write_text(_VALID_SUBISSUES, encoding="utf-8")

        found = discover_subissues_md(tmp_path, None, "2.1")
        assert found == target

    def test_not_found(self, tmp_path: Path):
        assert discover_subissues_md(tmp_path, "Arch-UI-Detail", "2.1") is None

    def test_multiple_picks_latest(self, tmp_path: Path):
        import time

        d1 = tmp_path / "Arch-UI-Detail" / "Issue-old"
        d2 = tmp_path / "Arch-UI-Detail" / "Issue-new"
        d1.mkdir(parents=True)
        d2.mkdir(parents=True)
        old = d1 / "subissues.md"
        new = d2 / "subissues.md"
        old.write_text(_VALID_SUBISSUES, encoding="utf-8")
        time.sleep(0.05)  # mtime 差を確保
        new.write_text(_VALID_SUBISSUES, encoding="utf-8")

        found = discover_subissues_md(tmp_path, "Arch-UI-Detail", "2.1")
        assert found == new


# ---------------------------------------------------------------------------
# build_subtask_prompt
# ---------------------------------------------------------------------------

class TestBuildSubtaskPrompt:
    def test_contains_all_metadata(self):
        sub = SubIssueDef(
            index=5,
            title="Test Title",
            labels=["hve", "test"],
            custom_agent="Arch-UI-Detail",
            depends_on=[1, 2],
            body="## Sub-005\n- AC: ...",
        )
        prompt = build_subtask_prompt(
            subissue=sub,
            parent_step_id="2.1",
            parent_custom_agent="Arch-UI-Detail",
            work_subdir="Arch-UI-Detail/Issue-screen-detail/sub-005",
        )
        assert "Sub-005" in prompt
        assert "2.1" in prompt
        assert "Test Title" in prompt
        assert "Sub-001" in prompt and "Sub-002" in prompt  # depends_on 表示
        assert "validation-confirmed" in prompt
        assert "SPLIT_REQUIRED を再発させてはなりません" in prompt

    def test_no_depends_on(self):
        sub = SubIssueDef(index=1, title="Root", body="content")
        prompt = build_subtask_prompt(sub, "1", None, "Issue-x/sub-001")
        assert "なし" in prompt  # depends_on 表示
        assert "(none)" in prompt  # parent_custom_agent


# ---------------------------------------------------------------------------
# make_subtask_work_subdir
# ---------------------------------------------------------------------------

class TestMakeSubtaskWorkSubdir:
    def test_with_custom_agent(self):
        result = make_subtask_work_subdir("Arch-UI-Detail", "screen-detail", 7)
        assert result == "Arch-UI-Detail/Issue-screen-detail/sub-007"

    def test_without_custom_agent(self):
        result = make_subtask_work_subdir(None, "42", 3)
        assert result == "Issue-42/sub-003"

    def test_zero_padding(self):
        result = make_subtask_work_subdir("X", "y", 123)
        assert "sub-123" in result


# ---------------------------------------------------------------------------
# check_subtask_completion
# ---------------------------------------------------------------------------

class TestCheckSubtaskCompletion:
    def test_missing_report(self, tmp_path: Path):
        ok, reason = check_subtask_completion(tmp_path, "Issue-x/sub-001")
        assert ok is False
        assert "存在しない" in reason

    def test_with_html_marker(self, tmp_path: Path):
        sub_dir = tmp_path / "Issue-x" / "sub-001"
        sub_dir.mkdir(parents=True)
        (sub_dir / "completion-report.md").write_text(
            "# Result\n\n<!-- validation-confirmed -->\n", encoding="utf-8",
        )
        ok, reason = check_subtask_completion(tmp_path, "Issue-x/sub-001")
        assert ok is True
        assert reason == "OK"

    def test_with_japanese_heading(self, tmp_path: Path):
        sub_dir = tmp_path / "Issue-x" / "sub-001"
        sub_dir.mkdir(parents=True)
        (sub_dir / "completion-report.md").write_text(
            "# Result\n\n## 検証結果\n\n- OK\n", encoding="utf-8",
        )
        ok, _ = check_subtask_completion(tmp_path, "Issue-x/sub-001")
        assert ok is True

    def test_with_bullet_marker(self, tmp_path: Path):
        sub_dir = tmp_path / "Issue-x" / "sub-001"
        sub_dir.mkdir(parents=True)
        (sub_dir / "completion-report.md").write_text(
            "# Result\n\n- 検証: pytest PASS\n", encoding="utf-8",
        )
        ok, _ = check_subtask_completion(tmp_path, "Issue-x/sub-001")
        assert ok is True

    def test_no_marker_fails(self, tmp_path: Path):
        sub_dir = tmp_path / "Issue-x" / "sub-001"
        sub_dir.mkdir(parents=True)
        (sub_dir / "completion-report.md").write_text(
            "# Result\n\n- done\n", encoding="utf-8",
        )
        ok, reason = check_subtask_completion(tmp_path, "Issue-x/sub-001")
        assert ok is False
        assert "マーカー" in reason
