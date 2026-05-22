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
    discover_subissues_md_verbose,
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

    def test_table_format_raises_with_actionable_message(self, tmp_path: Path):
        """P-A: テーブル形式の subissues.md は専用メッセージで早期失敗する。"""
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- parent_issue: 1 -->\n\n"
            "# Sub-tasks\n\n"
            "| id | depends_on | input | output |\n"
            "|---|---|---|---|\n"
            "| W1-SVC-01 | - | a.md | b.md |\n"
            "| W1-SVC-02 | - | c.md | d.md |\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError) as exc_info:
            parse_subissues_md(p)
        msg = str(exc_info.value)
        assert "ブロックが 0 件" in msg
        assert "Markdown テーブル形式" in msg
        assert "<!-- subissue -->" in msg
        assert "<!-- title:" in msg
        assert "subissues-template.md" in msg

    def test_short_table_not_detected_as_table_format(self, tmp_path: Path):
        """テーブル行が `_TABLE_MIN_CONSECUTIVE_ROWS` 未満なら判定しない。"""
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- parent_issue: 1 -->\n\n"
            "| a | b |\n"
            "|---|---|\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError) as exc_info:
            parse_subissues_md(p)
        msg = str(exc_info.value)
        assert "ブロックが 0 件" in msg
        assert "Markdown テーブル形式" not in msg

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

    def test_preflight_reports_all_missing_blocks(self, tmp_path: Path):
        """全ブロックで title 欠落 → 一括で全ブロック番号と H2 候補が報告される。"""
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- parent_issue: 1 -->\n\n"
            "<!-- subissue -->\n## Sub 01: ACT-01 会員ポータル系\n\n"
            "<!-- subissue -->\n## Sub 02: ACT-01 残高・リワード系\n\n"
            "<!-- subissue -->\n## Sub 03: ACT-01 通知系\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError) as exc_info:
            parse_subissues_md(p)
        msg = str(exc_info.value)
        assert "欠落ブロック: [1,2,3]" in msg
        assert "Sub 01: ACT-01 会員ポータル系" in msg
        assert "Sub 02: ACT-01 残高・リワード系" in msg
        assert "Sub 03: ACT-01 通知系" in msg
        assert "task-dag-planning" in msg
        assert "validate-subissues.sh" in msg

    def test_preflight_reports_partial_missing(self, tmp_path: Path):
        """一部ブロックのみ title 欠落 → 該当ブロックのみ報告される。"""
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- parent_issue: 1 -->\n\n"
            "<!-- subissue -->\n<!-- title: First -->\n## Sub-1\n\n"
            "<!-- subissue -->\n## Sub 02: 二番目\n\n"
            "<!-- subissue -->\n<!-- title: Third -->\n## Sub-3\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError) as exc_info:
            parse_subissues_md(p)
        msg = str(exc_info.value)
        assert "欠落ブロック: [2]" in msg
        assert "Sub 02: 二番目" in msg
        # 既存ブロック (1, 3) は欠落リストに含まれない
        assert "ブロック 1:" not in msg
        assert "ブロック 3:" not in msg

    def test_preflight_reports_no_h2(self, tmp_path: Path):
        """title も H2 も無いブロック → 'H2 見出しも未検出' と明示される。"""
        p = tmp_path / "subissues.md"
        p.write_text(
            "<!-- parent_issue: 1 -->\n\n"
            "<!-- subissue -->\nplain text only, no heading\n",
            encoding="utf-8",
        )
        with pytest.raises(SubIssuesParseError) as exc_info:
            parse_subissues_md(p)
        msg = str(exc_info.value)
        assert "欠落ブロック: [1]" in msg
        assert "H2 見出しも未検出" in msg


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

    def test_agent_scoped_preferred_over_fallback_glob(self, tmp_path: Path):
        """custom_agent 指定時、他 Agent の後発書き込みに mtime で負けないこと。

        再発防止: AAD-WEB 実行時に Step.2.1 (Arch-UI-Detail) の subissues.md 探索が
        並列実行中の Step.2.2 (Arch-Microservice-ServiceDetail) のファイルを
        mtime 勝ちで採用していたバグの回帰テスト。
        """
        import time

        # 自 Agent の subissues.md（先に書く＝古い mtime）
        own_dir = tmp_path / "Arch-UI-Detail" / "Issue-step-2-1"
        own_dir.mkdir(parents=True)
        own = own_dir / "subissues.md"
        own.write_text(_VALID_SUBISSUES, encoding="utf-8")

        time.sleep(0.05)

        # 他 Agent の subissues.md（後に書く＝新しい mtime、fallback-glob で拾われる）
        other_dir = tmp_path / "Arch-Microservice-ServiceDetail" / "Issue-step-2-2"
        other_dir.mkdir(parents=True)
        other = other_dir / "subissues.md"
        other.write_text(_VALID_SUBISSUES, encoding="utf-8")

        # custom_agent 指定時は agent-scoped 候補を優先し、自 Agent のファイルが返る
        found = discover_subissues_md(tmp_path, "Arch-UI-Detail", "2.1")
        assert found == own, (
            f"agent-scoped 候補があるのに fallback-glob が選ばれた: {found}"
        )

    def test_run_id_filter_excludes_stale_subissues(self, tmp_path: Path):
        """Issue-gui-session-workdir-isolation T1/T2 回帰テスト。

        過去 run の `Issue-<old_run>-...` 配下の subissues.md が、
        現在 run の探索結果に紛れ込まないことを確認する。
        """
        current_run = "20260521T074921-f707d7"
        old_run = "20260101T000000-aaaaaa"

        # 過去 run の subissues.md（mtime は新しい = フィルタ無しなら勝ってしまう）
        stale_dir = tmp_path / f"Issue-{old_run}-step-2"
        stale_dir.mkdir(parents=True)
        stale = stale_dir / "subissues.md"
        stale.write_text(_VALID_SUBISSUES, encoding="utf-8")

        # 現在 run の subissues.md
        current_dir = tmp_path / f"Issue-{current_run}-step-2"
        current_dir.mkdir(parents=True)
        current = current_dir / "subissues.md"
        current.write_text(_VALID_SUBISSUES, encoding="utf-8")

        # run_id フィルタなし: 順序は mtime 次第なのでアサートしない
        # run_id フィルタあり: 現在 run のみが返る
        result = discover_subissues_md_verbose(
            work_root=tmp_path,
            custom_agent=None,
            parent_step_id="2",
            run_id=current_run,
        )
        assert result.path == current, (
            f"run_id={current_run} で過去 run の subissues.md が選ばれた: {result.path}"
        )

    def test_run_id_none_keeps_backward_compatibility(self, tmp_path: Path):
        """run_id=None なら従来通り全候補が探索対象になる (Q9: 後方互換)。"""
        issue_dir = tmp_path / "Issue-some-identifier"
        issue_dir.mkdir(parents=True)
        target = issue_dir / "subissues.md"
        target.write_text(_VALID_SUBISSUES, encoding="utf-8")

        result = discover_subissues_md_verbose(
            work_root=tmp_path,
            custom_agent=None,
            parent_step_id="1",
            run_id=None,
        )
        assert result.path == target


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

    def test_includes_absolute_output_path(self, tmp_path: Path):
        sub = SubIssueDef(index=2, title="T", body="b")
        prompt = build_subtask_prompt(
            sub, "1", None, "Issue-x/sub-002", repo_root=tmp_path,
        )
        expected_abs = (tmp_path / "work" / "Issue-x" / "sub-002").as_posix() + "/"
        assert expected_abs in prompt
        # 正例/誤例の対比が含まれる
        assert "work/Issue-x/sub-002/completion-report.md" in prompt
        assert "hve/work/Issue-x/sub-002/completion-report.md" in prompt


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

    def test_detects_misplaced_hve_work(self, tmp_path: Path):
        """LLM が hve/work/ 側に completion-report.md を誤書き込みしたケースの検出。"""
        repo_root = tmp_path
        work_root = repo_root / "work"  # work_root.name == "work" でないと検出ロジックは作動しない
        work_root.mkdir()
        # 正規パスには報告ファイルなし
        # 誤書き込み先に作成
        misplaced = repo_root / "hve" / "work" / "Issue-x" / "sub-002"
        misplaced.mkdir(parents=True)
        (misplaced / "completion-report.md").write_text(
            "<!-- validation-confirmed -->\n", encoding="utf-8",
        )
        ok, reason = check_subtask_completion(work_root, "Issue-x/sub-002")
        assert ok is False
        assert "[MISPLACED]" in reason
        assert "hve/work" in reason.replace("\\", "/")
