"""hve.gui.i18n 基盤のテスト。

- ``resolve_language()`` の優先順位
- ``install_translator()`` の正常系・異常系
- ``.qm`` ファイルが存在し、ロード可能であること
- 設定ファイルの ``language`` キーが既定値に含まれていること
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# QApplication が必要な可能性があるため pytest-qt を使わない簡易テスト構成
pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication

from hve.gui import i18n, settings_store


_I18N_DIR = Path(i18n.__file__).resolve().parent


# ---------------------------------------------------------------------------
# resolve_language
# ---------------------------------------------------------------------------
class TestResolveLanguage:
    def test_env_var_supersedes_stored(self) -> None:
        with mock.patch.dict(os.environ, {"HVE_GUI_LANG": "en_US"}, clear=False):
            assert i18n.resolve_language("ja_JP") == "en_US"

    def test_env_var_ja_jp(self) -> None:
        with mock.patch.dict(os.environ, {"HVE_GUI_LANG": "ja_JP"}, clear=False):
            assert i18n.resolve_language("en_US") == "ja_JP"

    def test_env_auto_falls_through(self) -> None:
        with mock.patch.dict(os.environ, {"HVE_GUI_LANG": "auto"}, clear=False):
            # auto なので stored 値を採用
            assert i18n.resolve_language("ja_JP") == "ja_JP"

    def test_invalid_env_falls_through_to_stored(self) -> None:
        with mock.patch.dict(os.environ, {"HVE_GUI_LANG": "xx_XX"}, clear=False):
            assert i18n.resolve_language("en_US") == "en_US"

    def test_stored_ja_jp(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert i18n.resolve_language("ja_JP") == "ja_JP"

    def test_stored_en_us(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert i18n.resolve_language("en_US") == "en_US"

    def test_none_falls_back_to_os_detection(self) -> None:
        # OS 検出結果は環境依存だが、サポート言語のいずれかが返ることを確認
        with mock.patch.dict(os.environ, {}, clear=True):
            result = i18n.resolve_language(None)
            assert result in i18n.SUPPORTED_LANGUAGES

    def test_empty_falls_back_to_os_detection(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            result = i18n.resolve_language("")
            assert result in i18n.SUPPORTED_LANGUAGES

    def test_auto_falls_back_to_os_detection(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            result = i18n.resolve_language("auto")
            assert result in i18n.SUPPORTED_LANGUAGES


# ---------------------------------------------------------------------------
# install_translator
# ---------------------------------------------------------------------------
class TestInstallTranslator:
    @pytest.fixture(autouse=True)
    def _ensure_app(self) -> None:
        # 翻訳 install には QCoreApplication で十分だが、同一 pytest プロセス内の
        # 後続 GUI テスト（QWidget ベース）は QApplication を要求する。ここで
        # 非 GUI の QCoreApplication を先に生成すると "Cannot create a QWidget
        # without QApplication" で後続がクラッシュ/ハングするため、GUI と共存
        # できる QApplication を生成する。
        from PySide6.QtWidgets import QApplication

        self._app = QApplication.instance() or QApplication(sys.argv[:1])

    def test_source_language_returns_true_without_load(self) -> None:
        # ja_JP はソース言語のため .qm ロード不要、True を返す
        assert i18n.install_translator(self._app, "ja_JP") is True

    def test_en_us_loads_qm_if_present(self) -> None:
        qm_path = _I18N_DIR / "hve_gui_en_US.qm"
        if not qm_path.exists():
            pytest.skip(".qm not built; run setup-hve to compile")
        try:
            assert i18n.install_translator(self._app, "en_US") is True
        finally:
            # 後続テスト（例: test_status_banner の "待機" 等 ja_JP 文言検証）への
            # 翻訳汚染を防ぐため、ソース言語 ja_JP へ戻して QTranslator を取り外す。
            # install_translator(app, "ja_JP") は既存 translator を removeTranslator する。
            i18n.install_translator(self._app, "ja_JP")


# ---------------------------------------------------------------------------
# 設定 / アセット
# ---------------------------------------------------------------------------
class TestSettings:
    def test_language_key_in_defaults(self) -> None:
        defaults = settings_store.defaults()
        assert "language" in defaults["options"]
        assert defaults["options"]["language"] == "auto"


class TestAssets:
    def test_translations_pro_exists(self) -> None:
        assert (_I18N_DIR / "translations.pro").exists()

    def test_ts_exists_with_messages(self) -> None:
        ts_path = _I18N_DIR / "hve_gui_en_US.ts"
        assert ts_path.exists()
        content = ts_path.read_text(encoding="utf-8")
        assert '<source>' in content
        assert 'sourcelanguage="ja_JP"' in content or 'language="en_US"' in content

    def test_cq_settings_section_is_translated(self) -> None:
        """FR-GUI-04: Code-Query セクションの文字列が翻訳カタログに載っていること。"""
        sources = (_I18N_DIR / "translations.pro").read_text(encoding="utf-8")
        assert "cq/gui/settings_section.py" in sources

        content = (_I18N_DIR / "hve_gui_en_US.ts").read_text(encoding="utf-8")
        assert '<context>\n    <name>CqIndexSection</name>' in content
        assert "<source>インデックス管理</source>" in content


class TestAvailableLanguages:
    def test_includes_auto_ja_en(self) -> None:
        langs = i18n.available_languages()
        codes = [code for code, _ in langs]
        assert "auto" in codes
        assert "ja_JP" in codes
        assert "en_US" in codes
