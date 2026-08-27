"""hve.gui.github_comment_editor のユニットテスト（FR-GUI-30）。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.github_comment_editor import (  # noqa: E402
    FORMAT_ACTIONS,
    GitHubCommentEditor,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def editor(qapp):
    widget = GitHubCommentEditor()
    yield widget
    widget.deleteLater()


def _select(widget: GitHubCommentEditor, start: int, end: int) -> None:
    cursor = widget.editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    widget.editor.setTextCursor(cursor)


def _place(widget: GitHubCommentEditor, position: int) -> None:
    cursor = widget.editor.textCursor()
    cursor.setPosition(position)
    widget.editor.setTextCursor(cursor)


class TestPlainTextRoundTrip:
    def test_set_and_get_preserve_markdown_source(self, editor) -> None:
        source = "# 見出し\n\n- [ ] task\n\n```python\nprint(1)\n```\n"
        editor.set_text(source)
        assert editor.text() == source

    def test_fenced_code_language_is_preserved(self, editor) -> None:
        editor.set_text("```ts\nconst a = 1;\n```")
        assert "```ts" in editor.text()

    def test_clear_empties_text(self, editor) -> None:
        editor.set_text("x")
        editor.clear()
        assert editor.text() == ""

    def test_text_changed_signal_is_emitted(self, editor, qapp) -> None:
        seen = []
        editor.textChanged.connect(lambda: seen.append(1))
        editor.set_text("abc")
        assert seen


class TestToolbarActions:
    def test_nine_format_actions_exist(self, editor) -> None:
        assert len(FORMAT_ACTIONS) == 9
        assert set(editor.format_buttons) == set(FORMAT_ACTIONS)

    def test_buttons_have_accessible_names(self, editor) -> None:
        for key in FORMAT_ACTIONS:
            assert editor.format_buttons[key].accessibleName()

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("bold", "**word**"),
            ("italic", "*word*"),
            ("code", "`word`"),
        ],
    )
    def test_wrap_actions_on_selection(self, editor, key, expected) -> None:
        editor.set_text("word")
        _select(editor, 0, 4)
        editor.apply_format(key)
        assert editor.text() == expected

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("bold", "****"),
            ("italic", "**"),
            ("code", "``"),
        ],
    )
    def test_wrap_actions_without_selection(self, editor, key, expected) -> None:
        editor.set_text("")
        editor.apply_format(key)
        assert editor.text() == expected

    def test_wrap_without_selection_places_caret_inside(self, editor) -> None:
        editor.set_text("")
        editor.apply_format("bold")
        assert editor.editor.textCursor().position() == 2

    @pytest.mark.parametrize(
        "key,prefix",
        [
            ("heading", "### "),
            ("quote", "> "),
            ("bullet", "- "),
            ("number", "1. "),
            ("task", "- [ ] "),
        ],
    )
    def test_line_prefix_on_current_line(self, editor, key, prefix) -> None:
        editor.set_text("hello")
        _place(editor, 2)
        editor.apply_format(key)
        assert editor.text() == f"{prefix}hello"

    def test_line_prefix_applies_to_every_selected_line(self, editor) -> None:
        editor.set_text("a\nb\nc")
        _select(editor, 0, 5)
        editor.apply_format("bullet")
        assert editor.text() == "- a\n- b\n- c"

    def test_line_prefix_does_not_touch_unselected_lines(self, editor) -> None:
        editor.set_text("a\nb\nc")
        _select(editor, 0, 1)
        editor.apply_format("quote")
        assert editor.text() == "> a\nb\nc"

    def test_link_wraps_selection_and_selects_url(self, editor) -> None:
        editor.set_text("GitHub")
        _select(editor, 0, 6)
        editor.apply_format("link")
        assert editor.text() == "[GitHub](url)"
        assert editor.editor.textCursor().selectedText() == "url"

    def test_link_without_selection(self, editor) -> None:
        editor.set_text("")
        editor.apply_format("link")
        assert editor.text() == "[](url)"

    def test_unknown_action_is_ignored(self, editor) -> None:
        editor.set_text("x")
        editor.apply_format("no-such-action")
        assert editor.text() == "x"

    def test_read_only_blocks_format_insertion(self, editor) -> None:
        editor.set_text("x")
        editor.set_read_only(True)
        editor.apply_format("bold")
        assert editor.text() == "x"
        assert not editor.format_buttons["bold"].isEnabled()

    def test_button_click_applies_format(self, editor) -> None:
        editor.set_text("word")
        _select(editor, 0, 4)
        editor.format_buttons["bold"].click()
        assert editor.text() == "**word**"


class TestPreview:
    def test_has_write_and_preview_tabs(self, editor) -> None:
        assert editor.tabs.count() == 2

    def test_preview_renders_markdown(self, editor) -> None:
        editor.set_text("# Title")
        editor.show_preview()
        html = editor.preview_html()
        assert "Title" in html
        assert "# Title" not in html

    def test_switching_back_to_write_keeps_source(self, editor) -> None:
        editor.set_text("**bold**")
        editor.show_preview()
        editor.show_write()
        assert editor.text() == "**bold**"

    def test_preview_updates_after_text_change(self, editor) -> None:
        editor.set_text("first")
        editor.show_preview()
        editor.show_write()
        editor.set_text("second")
        editor.show_preview()
        assert "second" in editor.preview_html()

    def test_uses_shared_markdown_renderer(self) -> None:
        import ast
        from pathlib import Path

        import hve.gui.github_comment_editor as mod

        path = Path(mod.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert any("markdown_html_renderer" in name for name in modules)
        assert not any(name.split(".")[0] == "markdown_it" for name in modules)

    def test_preview_html_has_no_external_asset_requirement(self, editor) -> None:
        editor.set_text("```python\nprint(1)\n```")
        editor.show_preview()
        html = editor.preview_html()
        assert "mermaid.min.js" not in html
        assert "katex" not in html.lower()
