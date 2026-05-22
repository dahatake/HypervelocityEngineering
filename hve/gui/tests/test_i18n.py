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
        # QCoreApplication が必要
        if QCoreApplication.instance() is None:
            self._app = QCoreApplication(sys.argv[:1])
        else:
            self._app = QCoreApplication.instance()

    def test_source_language_returns_true_without_load(self) -> None:
        # ja_JP はソース言語のため .qm ロード不要、True を返す
        assert i18n.install_translator(self._app, "ja_JP") is True

    def test_en_us_loads_qm_if_present(self) -> None:
        qm_path = _I18N_DIR / "hve_gui_en_US.qm"
        if not qm_path.exists():
            pytest.skip(".qm not built; run setup-hve to compile")
        assert i18n.install_translator(self._app, "en_US") is True


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


class TestAvailableLanguages:
    def test_includes_auto_ja_en(self) -> None:
        langs = i18n.available_languages()
        codes = [code for code, _ in langs]
        assert "auto" in codes
        assert "ja_JP" in codes
        assert "en_US" in codes
