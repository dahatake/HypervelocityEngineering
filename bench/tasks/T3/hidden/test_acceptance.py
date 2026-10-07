import pytest

import docstore
from docstore import (
    DocstoreError,
    DocumentExistsError,
    DocumentNotFoundError,
    DocumentStore,
)


# 機能が未実装でも回帰テストを実行できるよう、遅延して参照する
class _Missing(Exception):
    pass


PermissionDeniedError = getattr(docstore, "PermissionDeniedError", _Missing)


@pytest.fixture
def s():
    st = DocumentStore()
    st.create("doc", "v1")
    st.set_role("vera", "viewer")
    st.set_role("ed", "editor")
    st.set_role("ada", "admin")
    return st


# --- 回帰: 利用者を指定しない従来の動作 ---

def test_legacy_create_read_update_delete():
    st = DocumentStore()
    st.create("a", "x")
    assert st.read("a") == "x"
    st.update("a", "y")
    assert st.read("a") == "y"
    st.delete("a")
    with pytest.raises(DocumentNotFoundError):
        st.read("a")


def test_legacy_errors_unchanged():
    st = DocumentStore()
    st.create("a", "x")
    with pytest.raises(DocumentExistsError):
        st.create("a", "y")
    with pytest.raises(DocumentNotFoundError):
        st.update("zz", "y")
    with pytest.raises(DocumentNotFoundError):
        st.delete("zz")


def test_legacy_list_ids_sorted():
    st = DocumentStore()
    st.create("b", "1")
    st.create("a", "2")
    assert st.list_ids() == ["a", "b"]


def test_permission_error_is_docstore_error():
    assert issubclass(PermissionDeniedError, DocstoreError)


# --- 新機能 ---

def test_set_and_get_role(s):
    assert s.get_role("vera") == "viewer"
    assert s.get_role("nobody") is None
    s.set_role("vera", "editor")
    assert s.get_role("vera") == "editor"


def test_invalid_role_rejected(s):
    with pytest.raises(ValueError):
        s.set_role("x", "owner")


def test_viewer_can_read_and_list_only(s):
    assert s.read("doc", user="vera") == "v1"
    assert s.list_ids(user="vera") == ["doc"]
    with pytest.raises(PermissionDeniedError):
        s.create("n", "x", user="vera")
    with pytest.raises(PermissionDeniedError):
        s.update("doc", "x", user="vera")
    with pytest.raises(PermissionDeniedError):
        s.delete("doc", user="vera")


def test_editor_can_create_update_not_delete(s):
    s.create("n", "x", user="ed")
    s.update("n", "y", user="ed")
    assert s.read("n", user="ed") == "y"
    with pytest.raises(PermissionDeniedError):
        s.delete("n", user="ed")


def test_admin_can_do_everything(s):
    s.create("n", "x", user="ada")
    s.update("n", "y", user="ada")
    s.delete("n", user="ada")
    assert s.list_ids(user="ada") == ["doc"]


def test_denied_operation_does_not_change_document(s):
    with pytest.raises(PermissionDeniedError):
        s.update("doc", "hacked", user="vera")
    with pytest.raises(PermissionDeniedError):
        s.delete("doc", user="ed")
    assert s.read("doc") == "v1"


def test_user_without_role_is_denied_everything(s):
    for call in (
        lambda: s.read("doc", user="ghost"),
        lambda: s.list_ids(user="ghost"),
        lambda: s.create("n", "x", user="ghost"),
        lambda: s.update("doc", "x", user="ghost"),
        lambda: s.delete("doc", user="ghost"),
    ):
        with pytest.raises(PermissionDeniedError):
            call()


def test_permission_checked_before_existence(s):
    with pytest.raises(PermissionDeniedError):
        s.read("missing", user="ghost")
    with pytest.raises(PermissionDeniedError):
        s.delete("missing", user="ed")


def test_set_role_requires_admin_when_actor_given(s):
    s.set_role("new", "viewer", actor="ada")
    assert s.get_role("new") == "viewer"
    with pytest.raises(PermissionDeniedError):
        s.set_role("new", "admin", actor="ed")
    with pytest.raises(PermissionDeniedError):
        s.set_role("new", "admin", actor="ghost")
    assert s.get_role("new") == "viewer"
