"""hve.gui.skill_sections — 設定画面の skills カテゴリ配下のセクションレジストリ。

将来 markdown-query 以外の Skill が GUI 表示を必要とした場合に、
このレジストリへ ``register_skill_section`` 呼び出し 1 行で追加できる。

== 使い方 ==

::

    from hve.gui.skill_sections import register_skill_section, get_registry

    register_skill_section(
        key="MY_SKILL",
        label="my-skill",
        section_factory=lambda repo_root, parent: MySkillSection(
            repo_root=repo_root, parent=parent),
    )

    # settings_window 構築時:
    for entry in get_registry().entries():
        ...

組み込みのデフォルト Skill (Markdown-Query) は ``settings_window`` モジュール
読み込み時に登録される（循環 import 回避のため遅延登録）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - 型ヒント専用
    from PySide6.QtWidgets import QWidget


SectionFactory = Callable[[Path, Optional["QWidget"]], "QWidget"]
"""``(repo_root, parent) -> QWidget`` 形式のファクトリ。"""


@dataclass(frozen=True)
class SkillSectionEntry:
    """設定画面 ``skills`` 配下に表示される 1 セクションの登録情報。

    Attributes:
        key: ``_CATEGORY_TREE`` で使うユニーク識別子（例: ``"MDQ"``）。
            ``QStackedWidget`` のインデックス対応辞書のキーになる。
        label: 左ペインのツリーノード表示名（例: ``"Markdown-Query"``）。
        section_factory: ``(repo_root, parent) -> QWidget`` でセクション本体を返す関数。
    """

    key: str
    label: str
    section_factory: SectionFactory


class SkillSectionRegistry:
    """skill_sections の登録/参照を司るレジストリ。

    登録順を保持する（``dict`` で OK だが意図を明示するため独立クラス化）。
    """

    def __init__(self) -> None:
        self._entries: Dict[str, SkillSectionEntry] = {}

    def register(self, entry: SkillSectionEntry) -> None:
        """エントリを登録する。同一 key は **上書き** する。

        上書きを許す理由: テスト・拡張機能からの差し替えを容易にするため。
        Production コード重複登録は呼び出し側で防ぐこと。
        """
        self._entries[entry.key] = entry

    def unregister(self, key: str) -> None:
        """指定 key を削除する。存在しない場合は無視。"""
        self._entries.pop(key, None)

    def entries(self) -> List[SkillSectionEntry]:
        """登録順のエントリ一覧を返す。"""
        return list(self._entries.values())

    def get(self, key: str) -> Optional[SkillSectionEntry]:
        """key に対応するエントリを返す（無ければ None）。"""
        return self._entries.get(key)

    def clear(self) -> None:
        """全エントリを削除する（テスト用）。"""
        self._entries.clear()


# モジュールレベル singleton
_REGISTRY: SkillSectionRegistry = SkillSectionRegistry()


def get_registry() -> SkillSectionRegistry:
    """モジュール singleton の Registry を返す。"""
    return _REGISTRY


def register_skill_section(
    *,
    key: str,
    label: str,
    section_factory: SectionFactory,
) -> None:
    """便利関数: ``SkillSectionEntry`` を生成して登録する。"""
    _REGISTRY.register(SkillSectionEntry(
        key=key, label=label, section_factory=section_factory,
    ))


__all__ = [
    "SectionFactory",
    "SkillSectionEntry",
    "SkillSectionRegistry",
    "get_registry",
    "register_skill_section",
]
