"""``settings_apply.apply_to_widgets`` の ``skip_keys`` パラメータ動作テスト。

Settings dialog 経由の autosave で OptionsPage の C10.app_ids が空文字で
上書きされる経路 (downstream workflow バグの引き金) を遮断する
``skip_keys={("C10", "app_ids")}`` の動作を検証する。

検証ポイント:
    1. ``skip_keys`` 未指定 (従来動作) → C10.app_ids も上書きされる。
    2. ``skip_keys={("C10", "app_ids")}`` → C10.app_ids は上書きされない。
    3. 他フィールド (usecase_id) は ``skip_keys`` の影響を受けず通常通り反映。
    4. 既存の C11 等他セクションは ``skip_keys`` の影響を受けない。

このテストは下記バグの回帰防止:
    - Step 1 で APP-ID を 1 件選択した後、Settings dialog 経由の
      autosave により OptionsPage の app_ids が空文字で上書きされ、
      Step 2 で全 APP-ID が並列実行される。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui import settings_apply  # noqa: E402
from hve.gui.page_options import _C10AppId, _C11AKM, _C3AutoPrompt  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestSettingsChangedSkipKeysCoverC3Qa:
    """設定画面の close 時 autosave が右ペインの必須 QA 選択を巻き戻さないこと。

    `SettingsWindow` は独立した `_CQaPrompt` 等を持ち、閉じるだけでも
    `collect_from_widgets` → save → `settings_changed` が走る。右ペインで
    選択した `auto_qa` がその stale 値で上書きされると、必須選択が未選択へ
    戻って実行不能になる（または意図しない on/off に化ける）。
    """

    def test_main_window_skip_keys_protect_c3_qa_fields(self) -> None:
        from hve.gui.main_window import _SETTINGS_APPLY_SKIP_KEYS

        assert ("QA", "auto_qa") in _SETTINGS_APPLY_SKIP_KEYS
        assert ("C10", "app_ids") in _SETTINGS_APPLY_SKIP_KEYS
        # 必須ではない qa_answer_mode は起動時に保存値を復元させる。
        assert ("QA", "qa_answer_mode") not in _SETTINGS_APPLY_SKIP_KEYS

    def test_auto_qa_selection_survives_settings_apply(self, qapp) -> None:
        from hve.gui.main_window import _SETTINGS_APPLY_SKIP_KEYS

        widget = _C3AutoPrompt()
        widget.auto_qa.set_tristate(True)

        settings_apply.apply_to_widgets(
            {"QA": widget},
            {"options": {"auto_qa": "", "qa_answer_mode": "autopilot"}},
            skip_keys=_SETTINGS_APPLY_SKIP_KEYS,
        )

        assert widget.auto_qa.get_tristate() is True

    def test_qa_answer_mode_is_restored_from_settings(self, qapp) -> None:
        from hve.gui.main_window import _SETTINGS_APPLY_SKIP_KEYS

        widget = _C3AutoPrompt()

        settings_apply.apply_to_widgets(
            {"QA": widget},
            {"options": {"auto_qa": "", "qa_answer_mode": "user"}},
            skip_keys=_SETTINGS_APPLY_SKIP_KEYS,
        )

        assert widget.qa_answer_mode.currentData() == "user"

    def test_other_c3_fields_are_still_applied(self, qapp) -> None:
        from hve.gui.main_window import _SETTINGS_APPLY_SKIP_KEYS

        widget = _C3AutoPrompt()

        settings_apply.apply_to_widgets(
            {"REVIEW": widget},
            {"options": {"auto_qa": "", "auto_contents_review": True}},
            skip_keys=_SETTINGS_APPLY_SKIP_KEYS,
        )

        assert widget.auto_contents_review.isChecked() is True


class TestApplyToWidgetsSkipKeys:
    """``apply_to_widgets`` の ``skip_keys`` パラメータ動作検証。"""

    def test_without_skip_keys_app_ids_is_overwritten(self, qapp) -> None:
        """skip_keys 未指定 (従来動作) → C10.app_ids も上書きされる。"""
        widget = _C10AppId()
        widget.app_ids.setText("APP-02")  # 事前にセット

        settings_apply.apply_to_widgets(
            {"C10": widget},
            {"options": {"app_ids": ""}},  # 空文字で上書き
        )

        # skip_keys 未指定なので空文字で上書きされる (バグの引き金)
        assert widget.app_ids.text() == ""

    def test_with_skip_keys_app_ids_is_protected(self, qapp) -> None:
        """skip_keys={("C10", "app_ids")} → C10.app_ids は保護される。"""
        widget = _C10AppId()
        widget.app_ids.setText("APP-02")

        settings_apply.apply_to_widgets(
            {"C10": widget},
            {"options": {"app_ids": ""}},
            skip_keys={("C10", "app_ids")},
        )

        # 上書きされず、Step 1 で選択した値が保持される
        assert widget.app_ids.text() == "APP-02"

    def test_with_skip_keys_usecase_id_is_still_applied(self, qapp) -> None:
        """skip_keys が app_ids のみ → usecase_id は通常通り上書きされる。"""
        widget = _C10AppId()
        widget.app_ids.setText("APP-02")
        widget.usecase_id.setText("OLD-UC")

        settings_apply.apply_to_widgets(
            {"C10": widget},
            {"options": {"app_ids": "", "usecase_id": "NEW-UC"}},
            skip_keys={("C10", "app_ids")},
        )

        # app_ids は保護、usecase_id は更新
        assert widget.app_ids.text() == "APP-02"
        assert widget.usecase_id.text() == "NEW-UC"

    def test_with_skip_keys_other_section_not_affected(self, qapp) -> None:
        """skip_keys が C10 のみ → 他セクション (C11) は影響を受けない。"""
        c10 = _C10AppId()
        c10.app_ids.setText("APP-02")
        c11 = _C11AKM()
        c11.sources_qa.setChecked(False)

        settings_apply.apply_to_widgets(
            {"C10": c10, "C11": c11},
            {
                "options": {
                    "app_ids": "",
                    "sources_qa": True,
                }
            },
            skip_keys={("C10", "app_ids")},
        )

        # C10.app_ids は保護
        assert c10.app_ids.text() == "APP-02"
        # C11.sources_qa は通常通り反映
        assert c11.sources_qa.isChecked() is True

    def test_skip_keys_with_iterable_input(self, qapp) -> None:
        """skip_keys は set 以外の iterable (list/tuple) も受け付ける。"""
        widget = _C10AppId()
        widget.app_ids.setText("APP-02")

        # list で渡す
        settings_apply.apply_to_widgets(
            {"C10": widget},
            {"options": {"app_ids": ""}},
            skip_keys=[("C10", "app_ids")],
        )
        assert widget.app_ids.text() == "APP-02"

        # tuple で渡す
        settings_apply.apply_to_widgets(
            {"C10": widget},
            {"options": {"app_ids": "OVERWRITE-ME"}},
            skip_keys=(("C10", "app_ids"),),
        )
        assert widget.app_ids.text() == "APP-02"
