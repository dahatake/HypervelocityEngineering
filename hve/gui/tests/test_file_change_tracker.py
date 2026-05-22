"""hve.gui.file_explorer.file_change_tracker のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from hve.gui.file_explorer.file_change_tracker import (
    ChangeState,
    FileChangeTracker,
)


@pytest.fixture
def tracker() -> FileChangeTracker:
    return FileChangeTracker(fade_seconds=5.0)


def test_initial_state_is_normal(tracker: FileChangeTracker) -> None:
    assert tracker.state_of(Path("a.md")) == ChangeState.NORMAL
    assert len(tracker) == 0


def test_mark_created_sets_new(tracker: FileChangeTracker) -> None:
    tracker.mark_created(Path("a.md"), now=10.0)
    assert tracker.state_of(Path("a.md")) == ChangeState.NEW
    assert len(tracker) == 1


def test_mark_modified_sets_modified(tracker: FileChangeTracker) -> None:
    tracker.mark_modified(Path("a.md"), now=10.0)
    assert tracker.state_of(Path("a.md")) == ChangeState.MODIFIED


def test_new_stays_new_on_subsequent_modify(tracker: FileChangeTracker) -> None:
    """NEW + modify は NEW のまま fade_at リセット（敵対的レビュー #11）。"""
    tracker.mark_created(Path("a.md"), now=10.0)
    tracker.mark_modified(Path("a.md"), now=12.0)
    assert tracker.state_of(Path("a.md")) == ChangeState.NEW

    # fade_at が 12.0 + 5.0 = 17.0 にリセットされていることを tick で間接検証
    list(tracker.tick(now=16.99))
    assert tracker.state_of(Path("a.md")) == ChangeState.NEW
    list(tracker.tick(now=17.0))
    assert tracker.state_of(Path("a.md")) == ChangeState.NORMAL


def test_modified_upgrades_to_new_on_create(tracker: FileChangeTracker) -> None:
    """MODIFIED + create で NEW に昇格（再作成扱い）。"""
    tracker.mark_modified(Path("a.md"), now=10.0)
    tracker.mark_created(Path("a.md"), now=11.0)
    assert tracker.state_of(Path("a.md")) == ChangeState.NEW


def test_mark_deleted_removes_entry(tracker: FileChangeTracker) -> None:
    tracker.mark_created(Path("a.md"), now=10.0)
    tracker.mark_deleted(Path("a.md"))
    assert tracker.state_of(Path("a.md")) == ChangeState.NORMAL
    assert len(tracker) == 0


def test_mark_deleted_on_unknown_path_is_noop(tracker: FileChangeTracker) -> None:
    tracker.mark_deleted(Path("never_existed.md"))  # 例外を出さない
    assert len(tracker) == 0


def test_tick_fades_expired_entries(tracker: FileChangeTracker) -> None:
    tracker.mark_created(Path("a.md"), now=10.0)
    tracker.mark_modified(Path("b.md"), now=10.0)

    faded = list(tracker.tick(now=14.99))
    assert faded == []
    assert tracker.state_of(Path("a.md")) == ChangeState.NEW
    assert tracker.state_of(Path("b.md")) == ChangeState.MODIFIED

    faded = list(tracker.tick(now=15.0))
    assert set(faded) == {Path("a.md"), Path("b.md")}
    assert tracker.state_of(Path("a.md")) == ChangeState.NORMAL
    assert tracker.state_of(Path("b.md")) == ChangeState.NORMAL


def test_tracked_paths_returns_current_entries(tracker: FileChangeTracker) -> None:
    tracker.mark_created(Path("a.md"), now=10.0)
    tracker.mark_modified(Path("b.md"), now=10.0)
    paths = set(tracker.tracked_paths())
    assert paths == {Path("a.md"), Path("b.md")}


def test_invalid_fade_seconds_raises() -> None:
    with pytest.raises(ValueError):
        FileChangeTracker(fade_seconds=0)
    with pytest.raises(ValueError):
        FileChangeTracker(fade_seconds=-1)
