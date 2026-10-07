from datetime import datetime, timedelta

import pytest

from drafts import DraftNotFoundError, DraftStore, DraftTooLargeError

T0 = datetime(2026, 1, 1, 9, 0, 0)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def env(tmp_path):
    clock = Clock()
    path = str(tmp_path / "drafts.json")
    return clock, path, DraftStore(path, clock=clock)


def test_save_and_resume(env):
    _, _, s = env
    s.save("u1", "form-a", {"name": "太郎", "step": 2})
    assert s.resume("u1", "form-a") == {"name": "太郎", "step": 2}


def test_resume_missing_raises(env):
    _, _, s = env
    with pytest.raises(DraftNotFoundError):
        s.resume("u1", "nope")


def test_users_and_forms_are_isolated(env):
    _, _, s = env
    s.save("u1", "a", {"v": 1})
    s.save("u2", "a", {"v": 2})
    s.save("u1", "b", {"v": 3})
    assert s.resume("u2", "a") == {"v": 2}
    assert s.list_drafts("u1") == ["a", "b"]
    assert s.list_drafts("u2") == ["a"]


def test_default_overwrite_keeps_single_draft(env):
    _, _, s = env
    s.save("u1", "a", {"v": 1})
    s.save("u1", "a", {"v": 2})
    assert s.resume("u1", "a") == {"v": 2}
    assert s.list_drafts("u1") == ["a"]


def test_default_retention_29_days_still_alive(env):
    clock, _, s = env
    s.save("u1", "a", {"v": 1})
    clock.advance(days=29, hours=23)
    assert s.resume("u1", "a") == {"v": 1}


def test_default_retention_exactly_30_days_is_expired(env):
    clock, _, s = env
    s.save("u1", "a", {"v": 1})
    clock.advance(days=30)
    with pytest.raises(DraftNotFoundError):
        s.resume("u1", "a")
    assert s.list_drafts("u1") == []


def test_custom_retention_days(tmp_path):
    clock = Clock()
    s = DraftStore(str(tmp_path / "d.json"), retention_days=7, clock=clock)
    s.save("u", "a", {})
    clock.advance(days=7)
    with pytest.raises(DraftNotFoundError):
        s.resume("u", "a")


def test_resume_does_not_extend_expiry(env):
    clock, _, s = env
    s.save("u1", "a", {"v": 1})
    clock.advance(days=20)
    s.resume("u1", "a")
    clock.advance(days=10)
    with pytest.raises(DraftNotFoundError):
        s.resume("u1", "a")


def test_resave_restarts_expiry(env):
    clock, _, s = env
    s.save("u1", "a", {"v": 1})
    clock.advance(days=20)
    s.save("u1", "a", {"v": 2})
    clock.advance(days=20)
    assert s.resume("u1", "a") == {"v": 2}


def test_submit_returns_and_deletes(env):
    _, _, s = env
    s.save("u1", "a", {"v": 1})
    assert s.submit("u1", "a") == {"v": 1}
    with pytest.raises(DraftNotFoundError):
        s.resume("u1", "a")
    with pytest.raises(DraftNotFoundError):
        s.submit("u1", "a")


def test_submit_expired_raises(env):
    clock, _, s = env
    s.save("u1", "a", {"v": 1})
    clock.advance(days=31)
    with pytest.raises(DraftNotFoundError):
        s.submit("u1", "a")


def test_purge_expired_returns_count(env):
    clock, _, s = env
    s.save("u1", "old1", {})
    s.save("u2", "old2", {})
    clock.advance(days=25)
    s.save("u1", "fresh", {})
    clock.advance(days=6)
    assert s.purge_expired() == 2
    assert s.list_drafts("u1") == ["fresh"]
    assert s.purge_expired() == 0


def test_persists_across_instances(env):
    clock, path, s = env
    s.save("u1", "a", {"v": "永続"})
    s2 = DraftStore(path, clock=clock)
    assert s2.resume("u1", "a") == {"v": "永続"}


def test_size_limit_default_65536_bytes(env):
    _, _, s = env
    with pytest.raises(DraftTooLargeError):
        s.save("u1", "a", {"text": "x" * 70000})
    s.save("u1", "a", {"text": "x" * 1000})
    assert s.resume("u1", "a")["text"] == "x" * 1000
