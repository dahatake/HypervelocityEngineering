"""FR-GUI-18: 実行ジョブタブの入力ボックス（``ChatInputBox``）。

VS Code のチャット入力と同じく、複数行入力・Enter 送信 / Shift+Enter 改行・
コンテキスト添付チップ・送信方法セレクタを 1 つの枠にまとめる。添付は
パスだけを本文へ列挙し、ファイル本文を読み取らない。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from hve.job_interaction_ipc import ACTION_QUEUE, ACTION_STEER, ACTION_STOP_AND_SEND
from hve.gui.widgets.chat_input_box import ChatInputBox


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def box(qapp) -> ChatInputBox:
    return ChatInputBox()


def _key_event(key: int, modifiers: Qt.KeyboardModifier) -> QKeyEvent:
    return QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers)


def _press(box: ChatInputBox, key: int, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
    QApplication.sendEvent(box.text_edit(), _key_event(key, modifiers))


class TestMultilineSubmit:
    def test_enter_submits(self, box: ChatInputBox) -> None:
        seen: list[str] = []
        box.submitted.connect(lambda: seen.append(box.compose_text()))
        box.set_text("送ります")
        _press(box, Qt.Key.Key_Return)
        assert seen == ["送ります"]

    def test_shift_enter_inserts_a_newline_without_submitting(self, box: ChatInputBox) -> None:
        seen: list[str] = []
        box.submitted.connect(lambda: seen.append("x"))
        box.set_text("一行目")
        _press(box, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        assert seen == []
        assert box.text() == "一行目\n"

    def test_send_button_submits(self, box: ChatInputBox) -> None:
        seen: list[str] = []
        box.submitted.connect(lambda: seen.append("x"))
        box.set_text("hello")
        box.send_button().click()
        assert seen == ["x"]

    def test_empty_input_does_not_submit(self, box: ChatInputBox) -> None:
        seen: list[str] = []
        box.submitted.connect(lambda: seen.append("x"))
        box.set_text("   ")
        _press(box, Qt.Key.Key_Return)
        assert seen == []

    def test_input_is_multiline_capable(self, box: ChatInputBox) -> None:
        box.set_text("a\nb\nc")
        assert box.text() == "a\nb\nc"


class TestAttachments:
    def test_attachment_is_added_and_listed(self, box: ChatInputBox) -> None:
        assert box.add_attachment("docs/business-requirement.md") is True
        assert box.attachments() == ("docs/business-requirement.md",)

    def test_duplicate_attachment_is_rejected(self, box: ChatInputBox) -> None:
        box.add_attachment("a.md")
        assert box.add_attachment("a.md") is False
        assert box.attachments() == ("a.md",)

    def test_attachment_can_be_removed_individually(self, box: ChatInputBox) -> None:
        box.add_attachment("a.md")
        box.add_attachment("b.md")
        assert box.remove_attachment("a.md") is True
        assert box.attachments() == ("b.md",)

    def test_removing_an_unknown_attachment_is_reported(self, box: ChatInputBox) -> None:
        assert box.remove_attachment("ghost.md") is False

    def test_chip_close_removes_its_attachment(self, box: ChatInputBox) -> None:
        box.add_attachment("a.md")
        box.add_attachment("b.md")
        box.attachment_chips()[0].close_button().click()
        assert box.attachments() == ("b.md",)

    def test_attach_button_delegates_to_the_owner(self, box: ChatInputBox) -> None:
        """ファイル選択ダイアログはパネル側が開く（ウィジェットは要求だけ出す）。"""
        seen: list[int] = []
        box.attach_requested.connect(lambda: seen.append(1))
        box.attach_button().click()
        assert seen == [1]

    def test_clear_removes_text_and_attachments(self, box: ChatInputBox) -> None:
        box.set_text("hello")
        box.add_attachment("a.md")
        box.clear()
        assert box.text() == ""
        assert box.attachments() == ()


class TestComposeText:
    def test_without_attachments_the_body_is_sent_as_is(self, box: ChatInputBox) -> None:
        box.set_text("進捗を教えて")
        assert box.compose_text() == "進捗を教えて"

    def test_attachment_paths_are_appended_as_a_list(self, box: ChatInputBox) -> None:
        box.set_text("見てほしい")
        box.add_attachment("docs/a.md")
        box.add_attachment("src/b.py")
        composed = box.compose_text().splitlines()
        assert composed[0] == "見てほしい"
        assert "- docs/a.md" in composed
        assert "- src/b.py" in composed

    def test_file_contents_are_never_embedded(self, tmp_path, box: ChatInputBox) -> None:
        secret = tmp_path / "secret.md"
        secret.write_text("SHOULD-NOT-APPEAR", encoding="utf-8")
        box.set_text("読んで")
        box.add_attachment(str(secret))
        composed = box.compose_text()
        assert "SHOULD-NOT-APPEAR" not in composed
        assert str(secret) in composed

    def test_attachments_only_still_compose(self, box: ChatInputBox) -> None:
        box.add_attachment("docs/a.md")
        assert "- docs/a.md" in box.compose_text()


class TestActionSelector:
    def test_the_three_actions_are_offered(self, box: ChatInputBox) -> None:
        assert box.action_labels() == ["キューに追加", "いま割り込む", "中断して送信"]

    def test_selecting_a_label_changes_the_action(self, box: ChatInputBox) -> None:
        box.select_action("中断して送信")
        assert box.current_action() == ACTION_STOP_AND_SEND
        box.select_action("キューに追加")
        assert box.current_action() == ACTION_QUEUE

    def test_default_action_is_queue(self, box: ChatInputBox) -> None:
        assert box.current_action() == ACTION_QUEUE

    def test_action_label_lookup(self, box: ChatInputBox) -> None:
        assert box.action_label(ACTION_STEER) == "いま割り込む"

    def test_no_model_or_effort_selector_is_offered(self, box: ChatInputBox) -> None:
        """FR-GUI-18 / FR-GUI-10: 実行中ジョブのモデル選択 UI を持たない。"""
        from PySide6.QtWidgets import QComboBox

        combos = box.findChildren(QComboBox)
        assert [c.objectName() for c in combos] == ["ChatInputActionCombo"]


class TestSendableGating:
    def test_sendable_gating_disables_input_and_send(self, box: ChatInputBox) -> None:
        box.set_sendable(False)
        assert box.text_edit().isEnabled() is False
        assert box.send_button().isEnabled() is False
        box.set_sendable(True)
        assert box.text_edit().isEnabled() is True
        assert box.send_button().isEnabled() is True

    def test_disabled_box_does_not_submit(self, box: ChatInputBox) -> None:
        seen: list[str] = []
        box.submitted.connect(lambda: seen.append("x"))
        box.set_text("hello")
        box.set_sendable(False)
        box.send_button().click()
        assert seen == []


class TestHeightGrowth:
    def test_height_grows_with_the_line_count(self, box: ChatInputBox) -> None:
        one_line = box.text_edit().maximumHeight()
        box.set_text("a\nb\nc\nd")
        assert box.text_edit().maximumHeight() > one_line

    def test_growth_stops_at_the_configured_limit(self, box: ChatInputBox) -> None:
        box.set_text("\n".join("x" for _ in range(50)))
        capped = box.text_edit().maximumHeight()
        box.set_text("\n".join("x" for _ in range(200)))
        assert box.text_edit().maximumHeight() == capped

    def test_capped_input_scrolls_instead_of_growing(self, box: ChatInputBox) -> None:
        box.set_text("\n".join("x" for _ in range(200)))
        policy = box.text_edit().verticalScrollBarPolicy()
        assert policy == Qt.ScrollBarPolicy.ScrollBarAsNeeded
