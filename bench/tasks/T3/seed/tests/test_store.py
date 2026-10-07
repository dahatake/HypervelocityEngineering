import pytest

from docstore import DocumentExistsError, DocumentNotFoundError, DocumentStore


def test_create_and_read():
    s = DocumentStore()
    s.create("a", "hello")
    assert s.read("a") == "hello"


def test_create_duplicate():
    s = DocumentStore()
    s.create("a", "x")
    with pytest.raises(DocumentExistsError):
        s.create("a", "y")


def test_update_and_delete():
    s = DocumentStore()
    s.create("a", "x")
    s.update("a", "y")
    assert s.read("a") == "y"
    s.delete("a")
    with pytest.raises(DocumentNotFoundError):
        s.read("a")


def test_list_ids_sorted():
    s = DocumentStore()
    s.create("b", "1")
    s.create("a", "2")
    assert s.list_ids() == ["a", "b"]
