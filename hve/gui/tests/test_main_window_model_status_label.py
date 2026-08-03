"""hve.gui.tests.test_main_window_model_status_label

MainWindow のステータスバーにある「使用するモデル」/「Effort」UI の検証。

旧実装は読み取り専用の QLabel（`_model_status_label`）だったが、
`_page_options.c1.model` / `.effort`（HVE 設定 > 基本設定と共有する実行時データの
実ウィジェット）をステータスバーへ re-parent し、その場で選択可能な UI に変更した。

検証観点:
- ステータスバーのコンボが `_page_options.c1.model` / `.effort` と同一オブジェクトであること
  （独自データを持たず、選択内容が即座に実行時設定へ反映されることの担保）
- 選択可能（非編集ドロップダウン）であること
- キャプションラベルが存在すること
- モデル変更時に Effort 選択肢が動的更新される既存挙動（`_C1Basic._refresh_effort_row`）が
  re-parent 後も引き続き機能すること
- 旧読み取り専用ラベル関連の属性が撤去されていること（回帰防止）
- 選択変更が `settings_store` へ即時保存されること（Task2）
- 「HVE 設定」ダイアログが表示中の場合、同じ値がそちらにも反映されること（Task2）
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox, QLabel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def main_window(qapp, monkeypatch, tmp_path):
    from hve.gui import settings_store

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        settings_store, "settings_path", lambda: tmp_path / ".settings.txt"
    )
    from hve.gui.main_window import MainWindow
    win = MainWindow()
    yield win
    win.close()
    win.deleteLater()


def test_status_bar_model_combo_is_same_object_as_page_options_c1(main_window):
    """ステータスバーに表示されるモデルコンボが _page_options.c1.model と同一オブジェクトである
    こと（独自データを持たない = re-parent 方式であること）を確認する。"""
    sb = main_window.statusBar()
    combos = sb.findChildren(QComboBox)
    assert main_window._page_options.c1.model in combos
    assert main_window._page_options.c1.effort in combos


def test_model_and_effort_combos_are_selectable_dropdowns(main_window):
    c1 = main_window._page_options.c1
    assert isinstance(c1.model, QComboBox)
    assert c1.model.isEditable() is False
    assert c1.model.isEnabled() is True
    assert isinstance(c1.effort, QComboBox)
    assert c1.effort.isEditable() is False


def test_status_bar_has_model_and_effort_captions(main_window):
    sb = main_window.statusBar()
    labels = [lab.text() for lab in sb.findChildren(QLabel)]
    assert "使用するモデル" in labels
    assert "Effort" in labels


def test_old_read_only_label_attributes_removed(main_window):
    """旧実装の読み取り専用ラベルは撤去済み（選択可能 UI へ置換されたための回帰防止）。"""
    assert not hasattr(main_window, "_model_status_label")
    assert not hasattr(main_window, "_refresh_model_status_label")


def test_selecting_new_model_reflects_in_combo_display(main_window):
    c1 = main_window._page_options.c1
    c1.model.addItem("test-model-select", userData="test-model-select")
    idx = c1.model.findData("test-model-select")

    c1.model.setCurrentIndex(idx)

    assert c1.model.currentData() == "test-model-select"
    assert c1.model.currentText() == "test-model-select"


def test_effort_choices_still_update_dynamically_after_reparent(main_window, monkeypatch):
    """re-parent 後も `_C1Basic._refresh_effort_row`（モデル変更→Effort 動的更新）が
    引き続き機能すること（既存挙動の回帰確認）。"""
    c1 = main_window._page_options.c1

    class _FakeEntry:
        supports_reasoning_effort = True
        supported_reasoning_efforts = ["low", "high"]
        default_reasoning_effort = "high"
        max_context_window_tokens = None
        input_price_usd_per_1m = None
        output_price_usd_per_1m = None
        cache_price_usd_per_1m = None

    c1.model.addItem("test-model-effort", userData="test-model-effort")
    c1._entries_map["test-model-effort"] = _FakeEntry()
    idx = c1.model.findData("test-model-effort")

    c1.model.setCurrentIndex(idx)

    assert c1.effort.isEnabled() is True
    effort_values = [c1.effort.itemData(i) for i in range(c1.effort.count())]
    assert effort_values == ["low", "high"]
    assert c1.effort.currentData() == "high"


# ---------------------------------------------------------------------------
# Task2: settings_store への即時永続化
# ---------------------------------------------------------------------------
def test_changing_model_persists_to_settings_store(main_window):
    from hve.gui import settings_store

    c1 = main_window._page_options.c1
    c1.model.addItem("test-model-persist", userData="test-model-persist")
    idx = c1.model.findData("test-model-persist")

    c1.model.setCurrentIndex(idx)

    assert settings_store.get_option("model") == "test-model-persist"


def test_changing_effort_persists_to_settings_store(main_window):
    from hve.gui import settings_store

    c1 = main_window._page_options.c1

    class _FakeEntry:
        supports_reasoning_effort = True
        supported_reasoning_efforts = ["low", "high"]
        default_reasoning_effort = "low"
        max_context_window_tokens = None
        input_price_usd_per_1m = None
        output_price_usd_per_1m = None
        cache_price_usd_per_1m = None

    c1.model.addItem("test-model-effort-persist", userData="test-model-effort-persist")
    c1._entries_map["test-model-effort-persist"] = _FakeEntry()
    idx = c1.model.findData("test-model-effort-persist")
    c1.model.setCurrentIndex(idx)

    effort_idx = c1.effort.findData("high")
    c1.effort.setCurrentIndex(effort_idx)

    assert settings_store.get_option("reasoning_effort") == "high"


def test_selecting_auto_model_persists_empty_effort(main_window):
    from hve.gui import settings_store
    from hve.config import MODEL_AUTO_VALUE

    c1 = main_window._page_options.c1
    # 非 Auto へ一度切り替えてから Auto へ戻し、effort が空で保存されることを確認する。
    c1.model.addItem("test-model-back-to-auto", userData="test-model-back-to-auto")
    c1.model.setCurrentIndex(c1.model.findData("test-model-back-to-auto"))

    auto_idx = c1.model.findData(MODEL_AUTO_VALUE)
    c1.model.setCurrentIndex(auto_idx)

    assert settings_store.get_option("model") == MODEL_AUTO_VALUE
    assert settings_store.get_option("reasoning_effort") == ""


def test_changing_model_syncs_to_open_settings_dialog(main_window):
    main_window._open_settings_window()
    settings_c1 = main_window._settings_window._sections["C1"]

    c1 = main_window._page_options.c1
    # 実際の運用では両コンボが同一の models_cache から選択肢を投入されるため、
    # テスト用モデルも両方のコンボに追加してその状態を再現する。
    c1.model.addItem("test-model-sync", userData="test-model-sync")
    settings_c1.model.addItem("test-model-sync", userData="test-model-sync")
    c1.model.setCurrentIndex(c1.model.findData("test-model-sync"))

    assert settings_c1.model.currentData() == "test-model-sync"


def test_changing_effort_syncs_to_open_settings_dialog(main_window):
    main_window._open_settings_window()
    settings_c1 = main_window._settings_window._sections["C1"]

    c1 = main_window._page_options.c1

    class _FakeEntry:
        supports_reasoning_effort = True
        supported_reasoning_efforts = ["low", "high"]
        default_reasoning_effort = "low"
        max_context_window_tokens = None
        input_price_usd_per_1m = None
        output_price_usd_per_1m = None
        cache_price_usd_per_1m = None

    # 両コンボ及び両 _entries_map に同じテストモデルを追加し、
    # 設定ダイアログ側の Effort 動的切替（_refresh_effort_row）も
    # 同じ選択肢を持てるようにする。
    c1.model.addItem("test-model-effort-sync", userData="test-model-effort-sync")
    c1._entries_map["test-model-effort-sync"] = _FakeEntry()
    settings_c1.model.addItem("test-model-effort-sync", userData="test-model-effort-sync")
    settings_c1._entries_map["test-model-effort-sync"] = _FakeEntry()

    c1.model.setCurrentIndex(c1.model.findData("test-model-effort-sync"))
    c1.effort.setCurrentIndex(c1.effort.findData("high"))

    assert settings_c1.model.currentData() == "test-model-effort-sync"
    assert settings_c1.effort.currentData() == "high"


def test_changing_model_without_open_settings_dialog_does_not_error(main_window):
    """設定ダイアログが開いていない場合でも例外なく動作すること。"""
    assert main_window._settings_window is None
    c1 = main_window._page_options.c1
    c1.model.addItem("test-model-no-dialog", userData="test-model-no-dialog")

    c1.model.setCurrentIndex(c1.model.findData("test-model-no-dialog"))  # raise しないこと

    assert c1.model.currentData() == "test-model-no-dialog"

