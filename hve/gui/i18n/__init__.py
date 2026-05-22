"""hve.gui.i18n — Qt QTranslator ベースの GUI 多言語化基盤。

設計:
  - ソース言語: 日本語（コード中の ``self.tr("...")`` 引数は日本語）。
  - 翻訳対象: en_US のみ。``hve_gui_en_US.ts`` / ``.qm`` を本ディレクトリに配置。
  - 言語決定優先順位:
      1. 環境変数 ``HVE_GUI_LANG``（``ja_JP`` / ``en_US`` / ``auto``）
      2. ``settings_store.py`` の ``[options].language``
      3. OS ロケール（``locale.getlocale()`` の先頭 2 文字）
      4. フォールバック = ``ja_JP``（ソース言語）
  - 言語切替はアプリ再起動で反映する方針（``QTranslator`` 入替時のライブ再描画は実装しない）。

公開 API:
  - :func:`resolve_language` — 起動時に確定言語コードを返す。
  - :func:`install_translator` — ``QApplication`` に ``QTranslator`` をインストールする。
  - :func:`available_languages` — UI に表示する選択肢一覧。
  - :data:`SUPPORTED_LANGUAGES` — 対応言語コード。
  - :data:`SOURCE_LANGUAGE` — ソース言語コード（翻訳不要）。
"""

from __future__ import annotations

import locale
import os
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QCoreApplication, QLocale, QTranslator

SOURCE_LANGUAGE = "ja_JP"
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("ja_JP", "en_US")
_AUTO = "auto"
_TRANSLATIONS_DIR = Path(__file__).resolve().parent

# QApplication に install した QTranslator を保持し、GC されないようにする。
_active_translator: Optional[QTranslator] = None


def available_languages() -> List[Tuple[str, str]]:
    """設定 UI 用の (コード, 表示名) 一覧を返す。

    ``"auto"`` を先頭に含め、OS ロケールに従う既定動作を選べるようにする。
    """
    return [
        (_AUTO, "自動 / Auto"),
        ("ja_JP", "日本語"),
        ("en_US", "English"),
    ]


def _detect_os_language() -> str:
    """OS ロケールから ``ja_JP`` / ``en_US`` を判定する。判定不能時は ``ja_JP``。"""
    try:
        # Qt 側のロケールを優先（プラットフォーム差異を吸収）。
        qloc = QLocale.system().name()  # 例: "ja_JP", "en_US"
    except Exception:
        qloc = ""
    if not qloc:
        try:
            sys_loc = locale.getlocale()[0] or ""
        except Exception:
            sys_loc = ""
        qloc = sys_loc.replace("-", "_")
    head = qloc.lower()
    if head.startswith("ja"):
        return "ja_JP"
    if head.startswith("en"):
        return "en_US"
    # 未対応ロケールは英語にフォールバック（en_US ユーザーの方が母数大）。
    return "en_US"


def resolve_language(stored_value: Optional[str] = None) -> str:
    """起動時に使用する言語コードを決定する。

    Args:
        stored_value: ``settings_store`` から渡される ``[options].language`` 値。
            ``None`` / ``""`` / ``"auto"`` のいずれかなら OS 判定を行う。

    Returns:
        ``"ja_JP"`` または ``"en_US"``。
    """
    env = (os.environ.get("HVE_GUI_LANG") or "").strip()
    if env in SUPPORTED_LANGUAGES:
        return env
    if env and env != _AUTO:
        # 不正値は無視して次の優先順位へフォールスルー
        pass

    val = (stored_value or "").strip()
    if val in SUPPORTED_LANGUAGES:
        return val

    return _detect_os_language()


def install_translator(app: QCoreApplication, language: str) -> bool:
    """``QApplication`` に ``QTranslator`` をインストールする。

    Args:
        app: 対象の ``QCoreApplication`` インスタンス。
        language: ``"ja_JP"`` / ``"en_US"``。

    Returns:
        ``.qm`` のロードに成功した場合 ``True``。ソース言語 ``ja_JP`` の場合は
        翻訳ファイル不要のため ``True`` を返す（QTranslator は install しない）。
        ロード失敗時は ``False``。
    """
    global _active_translator

    # 既存の Translator を取り外す（言語切替を将来サポートする場合に備える）。
    if _active_translator is not None:
        try:
            app.removeTranslator(_active_translator)
        except Exception:
            pass
        _active_translator = None

    if language == SOURCE_LANGUAGE:
        return True

    qm_path = _TRANSLATIONS_DIR / f"hve_gui_{language}.qm"
    if not qm_path.exists():
        return False

    translator = QTranslator(app)
    if not translator.load(str(qm_path)):
        return False
    if not app.installTranslator(translator):
        return False

    _active_translator = translator
    return True


__all__ = [
    "SOURCE_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "available_languages",
    "resolve_language",
    "install_translator",
]
