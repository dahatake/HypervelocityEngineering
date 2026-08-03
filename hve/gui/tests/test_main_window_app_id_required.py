"""``MainWindow._validate_app_ids_for_downstream`` のテスト。

downstream workflow (aad-web/asdw-web/adfd/adfdv) 選択時に APP-ID が
1 件以上選択されているかを検証し、未選択時は QMessageBox.warning で
ダイアログ表示し False を返すこと、選択済み or downstream 以外の workflow
では True を返すことを確認する。

このバリデーションが無い場合、orchestrator 側の後方互換 fallback
(``resolve_app_arch_scope(requested_app_ids=None)`` が catalog の対象
アーキテクチャ全 APP-ID を返す）により、Step 2 で全 APP-ID が並列展開
されてしまうバグの引き金となる。

軽量モック方針: ``test_main_window_unified_precheck.py`` 等と同じく
``self`` を ``MagicMock`` に置換し、Qt ウィンドウを生成せずに unbound
メソッドとして呼び出す。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hve.gui.main_window import MainWindow  # noqa: E402


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app  # type: ignore[return-value]


def _make_self(app_ids_text: str = "") -> MagicMock:
    """``_validate_app_ids_for_downstream`` 実行に必要な属性のみ持つ軽量 self を作る。"""
    fake = MagicMock()
    fake.tr = lambda s: s
    fake._page_options.c10.app_ids.text.return_value = app_ids_text
    return fake


# ---------------------------------------------------------------------------
# Case 1: downstream workflow 未選択 → 常に True (バリデーション対象外)
# ---------------------------------------------------------------------------
def test_validate_returns_true_when_no_downstream_workflow() -> None:
    _ensure_app()
    fake_self = _make_self(app_ids_text="")

    with patch(
        "hve.gui.main_window.QMessageBox.warning"
    ) as mock_warning:
        # ard / aas / aag / aagd は downstream に含まれない
        for wf_id in ("ard", "aas", "aag", "aagd"):
            result = MainWindow._validate_app_ids_for_downstream(
                fake_self, [wf_id]
            )
            assert result is True

    mock_warning.assert_not_called()


# ---------------------------------------------------------------------------
# Case 2: downstream workflow 選択 + APP-ID 指定済み → True
# ---------------------------------------------------------------------------
def test_validate_returns_true_when_app_ids_specified() -> None:
    _ensure_app()
    fake_self = _make_self(app_ids_text="APP-02")

    with patch(
        "hve.gui.main_window.QMessageBox.warning"
    ) as mock_warning:
        for wf_id in ("aad-web", "asdw-web", "adfd", "adfdv"):
            result = MainWindow._validate_app_ids_for_downstream(
                fake_self, [wf_id]
            )
            assert result is True

    mock_warning.assert_not_called()


# ---------------------------------------------------------------------------
# Case 3: downstream workflow 選択 + APP-ID 空 → False + 警告ダイアログ
# ---------------------------------------------------------------------------
def test_validate_returns_false_when_downstream_and_empty_app_ids() -> None:
    _ensure_app()
    fake_self = _make_self(app_ids_text="")

    with patch(
        "hve.gui.main_window.QMessageBox.warning"
    ) as mock_warning:
        result = MainWindow._validate_app_ids_for_downstream(
            fake_self, ["aad-web"]
        )

    assert result is False
    mock_warning.assert_called_once()
    # 警告ダイアログのメッセージに対象 workflow 名 (大文字) と
    # 「APP-ID」キーワードが含まれていること
    _, args, _kwargs = mock_warning.mock_calls[0]
    body_text = args[2]  # (parent, title, body) の body
    assert "AAD-WEB" in body_text
    assert "APP-ID" in body_text


# ---------------------------------------------------------------------------
# Case 4: APP-ID が空白のみ (whitespace) でも未選択扱い
# ---------------------------------------------------------------------------
def test_validate_returns_false_when_app_ids_is_whitespace_only() -> None:
    _ensure_app()
    fake_self = _make_self(app_ids_text="   \t  ")

    with patch(
        "hve.gui.main_window.QMessageBox.warning"
    ) as mock_warning:
        result = MainWindow._validate_app_ids_for_downstream(
            fake_self, ["adfd"]
        )

    assert result is False
    mock_warning.assert_called_once()


# ---------------------------------------------------------------------------
# Case 5: 複数 workflow に downstream / 非 downstream が混在
#   → downstream のみリストアップして警告
# ---------------------------------------------------------------------------
def test_validate_lists_only_downstream_workflows_in_message() -> None:
    _ensure_app()
    fake_self = _make_self(app_ids_text="")

    with patch(
        "hve.gui.main_window.QMessageBox.warning"
    ) as mock_warning:
        result = MainWindow._validate_app_ids_for_downstream(
            fake_self, ["ard", "aad-web", "aas", "adfd"]
        )

    assert result is False
    mock_warning.assert_called_once()
    _, args, _kwargs = mock_warning.mock_calls[0]
    body_text = args[2]
    # downstream の AAD-WEB / ADFD は含まれる
    assert "AAD-WEB" in body_text
    assert "ADFD" in body_text
    # 非 downstream の ARD / AAS は含まれない
    assert "ARD" not in body_text
    assert "AAS" not in body_text


# ---------------------------------------------------------------------------
# Case 6: OptionsPage.c10.app_ids 属性アクセス例外時の防御
# ---------------------------------------------------------------------------
def test_validate_handles_attribute_error_defensively() -> None:
    _ensure_app()
    fake_self = MagicMock()
    fake_self.tr = lambda s: s
    # text() が呼ばれる前に AttributeError を発生させる
    fake_self._page_options.c10.app_ids.text.side_effect = AttributeError

    with patch(
        "hve.gui.main_window.QMessageBox.warning"
    ) as mock_warning:
        result = MainWindow._validate_app_ids_for_downstream(
            fake_self, ["aad-web"]
        )

    # 例外捕捉して空文字扱い → 警告表示して False
    assert result is False
    mock_warning.assert_called_once()
