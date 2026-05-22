"""T9.3: hve.gui.skill_sections レジストリの単体テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.gui import skill_sections


@pytest.fixture(autouse=True)
def _isolate_registry():
    """各テストで registry を保存/復元し、他テストへの副作用を防ぐ。

    settings_window モジュールを先に import して組み込み Skill (MDQ) が
    登録された状態をスナップショットの基準にする。これにより、本ファイル
    実行後でも他テストファイルが期待する組み込み登録が保たれる。
    """
    # 組み込み Skill 登録を保証する
    from hve.gui import settings_window  # noqa: F401
    reg = skill_sections.get_registry()
    saved = list(reg.entries())
    yield
    reg.clear()
    for e in saved:
        reg.register(e)


def _dummy_factory(repo_root, parent):
    # widget を作らずダミー値を返す（Qt 非依存テストのため）
    return ("dummy_widget", str(repo_root), parent)


def test_register_and_get() -> None:
    reg = skill_sections.get_registry()
    reg.clear()
    skill_sections.register_skill_section(
        key="X", label="x-skill", section_factory=_dummy_factory
    )
    entry = reg.get("X")
    assert entry is not None
    assert entry.label == "x-skill"
    assert entry.key == "X"


def test_register_preserves_order() -> None:
    reg = skill_sections.get_registry()
    reg.clear()
    for k in ("A", "B", "C"):
        skill_sections.register_skill_section(
            key=k, label=f"label-{k}", section_factory=_dummy_factory
        )
    keys = [e.key for e in reg.entries()]
    assert keys == ["A", "B", "C"]


def test_register_overwrites_existing_key() -> None:
    reg = skill_sections.get_registry()
    reg.clear()
    skill_sections.register_skill_section(
        key="X", label="old", section_factory=_dummy_factory
    )
    skill_sections.register_skill_section(
        key="X", label="new", section_factory=_dummy_factory
    )
    assert len(reg.entries()) == 1
    assert reg.get("X").label == "new"


def test_unregister() -> None:
    reg = skill_sections.get_registry()
    reg.clear()
    skill_sections.register_skill_section(
        key="X", label="x", section_factory=_dummy_factory
    )
    reg.unregister("X")
    assert reg.get("X") is None
    # 存在しない key の unregister は無例外
    reg.unregister("NONEXISTENT")


def test_factory_invoked_with_repo_root_and_parent(tmp_path: Path) -> None:
    reg = skill_sections.get_registry()
    reg.clear()
    skill_sections.register_skill_section(
        key="X", label="x", section_factory=_dummy_factory
    )
    entry = reg.get("X")
    result = entry.section_factory(tmp_path, None)
    assert result == ("dummy_widget", str(tmp_path), None)


def test_builtin_markdown_query_registered_after_settings_window_import() -> None:
    """settings_window が import されると Markdown-Query が登録されること。"""
    # 既に test_settings_window_skills.py で import 済の可能性があるが、
    # 明示的に import してレジストリ状態を確認する。
    from hve.gui import settings_window  # noqa: F401
    reg = skill_sections.get_registry()
    entry = reg.get("MDQ")
    assert entry is not None
    assert entry.label == "Markdown-Query"
