"""hve.gui.github_comment_format のユニットテスト（FR-GUI-33）。"""

from __future__ import annotations

import pytest

from hve.gui.github_comment_format import (
    MAX_CONSOLE_LOG_LINES,
    format_console_log_comment,
    strip_ansi,
)


class TestHeader:
    def test_has_heading(self) -> None:
        out = format_console_log_comment("a\nb")
        assert out.startswith("### HVE コンソール出力")

    def test_reports_total_and_shown_lines(self) -> None:
        out = format_console_log_comment("\n".join(str(i) for i in range(5)))
        assert "| 総行数 | 5 |" in out
        assert "| 掲載行数 | 5 |" in out

    def test_includes_run_id_and_workflow_when_given(self) -> None:
        out = format_console_log_comment("x", run_id="20260825T000000-abcdef", workflow_id="asdw-web")
        assert "| run-id | `20260825T000000-abcdef` |" in out
        assert "| ワークフロー | `asdw-web` |" in out

    def test_omits_run_id_and_workflow_when_absent(self) -> None:
        out = format_console_log_comment("x")
        assert "run-id" not in out
        assert "ワークフロー" not in out

    def test_body_is_wrapped_in_details(self) -> None:
        out = format_console_log_comment("x")
        assert "<details>" in out and "</details>" in out


class TestTruncation:
    def test_default_limit_is_300(self) -> None:
        assert MAX_CONSOLE_LOG_LINES == 300

    def test_keeps_tail_when_over_limit(self) -> None:
        text = "\n".join(f"line{i}" for i in range(400))
        out = format_console_log_comment(text)
        assert "| 総行数 | 400 |" in out
        assert "| 掲載行数 | 300 |" in out
        assert "| 省略行数 | 先頭 100 行を省略 |" in out
        assert "line399" in out
        assert "line99" not in out
        assert "line100" in out

    def test_no_omission_notice_when_within_limit(self) -> None:
        out = format_console_log_comment("\n".join(f"l{i}" for i in range(10)))
        assert "省略行数" not in out
        assert "全 10 行" in out

    def test_custom_max_lines(self) -> None:
        out = format_console_log_comment("a\nb\nc\nd", max_lines=2)
        assert "| 掲載行数 | 2 |" in out
        assert "| 省略行数 | 先頭 2 行を省略 |" in out

    def test_max_lines_below_one_is_clamped(self) -> None:
        out = format_console_log_comment("a\nb\nc", max_lines=0)
        assert "| 掲載行数 | 1 |" in out

    def test_empty_text_produces_zero_totals(self) -> None:
        out = format_console_log_comment("")
        assert "| 総行数 | 0 |" in out
        assert "| 掲載行数 | 0 |" in out


class TestAnsiStripping:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("\x1b[31mred\x1b[0m", "red"),
            ("\x1b[1;32mbold green\x1b[0m", "bold green"),
            ("\x1b[2Kclear", "clear"),
            ("\x1b]0;title\x07after", "after"),
            ("plain", "plain"),
        ],
    )
    def test_strip_ansi(self, raw: str, expected: str) -> None:
        assert strip_ansi(raw) == expected

    def test_comment_body_has_no_escape_characters(self) -> None:
        out = format_console_log_comment("\x1b[31mERROR\x1b[0m failed")
        assert "\x1b" not in out
        assert "ERROR failed" in out


class TestFenceLength:
    def test_plain_body_uses_three_backticks(self) -> None:
        out = format_console_log_comment("hello")
        assert "```text" in out
        assert "````" not in out

    def test_body_with_triple_fence_uses_longer_fence(self) -> None:
        out = format_console_log_comment("before\n```\ncode\n```\nafter")
        assert "````text" in out

    def test_body_with_longer_fence_extends_further(self) -> None:
        out = format_console_log_comment("`````\nx\n`````")
        assert "``````text" in out

    def test_outer_fence_is_balanced(self) -> None:
        out = format_console_log_comment("a\n```\nb")
        opening = next(line for line in out.splitlines() if line.endswith("text") and line.startswith("`"))
        fence = opening[: -len("text")]
        # 開始フェンスと同じ長さの閉じフェンス行が存在する
        assert any(line == fence for line in out.splitlines())

    def test_inline_backticks_do_not_extend_fence(self) -> None:
        out = format_console_log_comment("use `git status` here")
        assert "```text" in out
        assert "````" not in out


class TestNoSideEffects:
    def test_input_is_not_mutated(self) -> None:
        text = "a\nb\nc"
        format_console_log_comment(text)
        assert text == "a\nb\nc"

    def test_module_does_not_import_pyside(self) -> None:
        import ast
        from pathlib import Path

        import hve.gui.github_comment_format as mod

        path = Path(mod.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".", 1)[0])
        assert "PySide6" not in roots
