import subprocess
import sys

import pytest

import inventory
from inventory import (
    DuplicateItemError,
    InsufficientStockError,
    Inventory,
    InvalidQuantityError,
    UnknownItemError,
)


@pytest.fixture
def inv():
    i = Inventory()
    i.add_item("A", "apple", 10, 3)
    i.add_item("B", "banana", 5)
    return i


def test_add_and_on_hand(inv):
    assert inv.on_hand("A") == 10
    assert inv.available("A") == 10


def test_duplicate_sku_rejected(inv):
    with pytest.raises(DuplicateItemError):
        inv.add_item("A", "again")


def test_unknown_sku(inv):
    with pytest.raises(UnknownItemError):
        inv.on_hand("ZZZ")


def test_receive_increases_stock(inv):
    inv.receive("B", 7)
    assert inv.on_hand("B") == 12


def test_invalid_quantity(inv):
    with pytest.raises(InvalidQuantityError):
        inv.receive("A", 0)
    with pytest.raises(InvalidQuantityError):
        inv.reserve("A", -1)


def test_reserve_reduces_available_not_on_hand(inv):
    rid = inv.reserve("A", 4)
    assert isinstance(rid, str)
    assert inv.available("A") == 6
    assert inv.on_hand("A") == 10


def test_cannot_reserve_more_than_available(inv):
    inv.reserve("A", 8)
    with pytest.raises(InsufficientStockError):
        inv.reserve("A", 3)
    assert inv.available("A") == 2


def test_release_restores_available(inv):
    rid = inv.reserve("A", 4)
    inv.release(rid)
    assert inv.available("A") == 10
    with pytest.raises(UnknownItemError):
        inv.release(rid)


def test_commit_reduces_on_hand(inv):
    rid = inv.reserve("A", 4)
    inv.commit(rid)
    assert inv.on_hand("A") == 6
    assert inv.available("A") == 6
    with pytest.raises(UnknownItemError):
        inv.commit(rid)


def test_low_stock_uses_available_and_is_sorted(inv):
    assert inv.low_stock() == []
    inv.add_item("C", "cherry", 2, 2)
    inv.reserve("A", 7)
    assert inv.low_stock() == ["A", "C"]


def test_low_stock_includes_equal_to_reorder_level(inv):
    inv.reserve("A", 7)
    assert inv.available("A") == 3
    assert "A" in inv.low_stock()


def test_save_and_reload(tmp_path):
    path = str(tmp_path / "inv.json")
    i = Inventory(path)
    i.add_item("A", "apple", 10, 3)
    rid = i.reserve("A", 4)
    i.save()
    j = Inventory(path)
    assert j.on_hand("A") == 10
    assert j.available("A") == 6
    j.commit(rid)
    assert j.on_hand("A") == 6


def test_save_without_path_fails(inv):
    with pytest.raises(inventory.InventoryError):
        inv.save()


def _cli(path, *args):
    return subprocess.run(
        [sys.executable, "-m", "inventory", "--file", str(path), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def test_cli_flow(tmp_path):
    f = tmp_path / "cli.json"
    assert _cli(f, "add", "A", "apple", "10", "--reorder", "3").returncode == 0
    r = _cli(f, "reserve", "A", "8")
    assert r.returncode == 0
    rid = r.stdout.strip()
    assert rid and "\n" not in rid
    assert _cli(f, "stock", "A").stdout.strip() == "2"
    assert _cli(f, "low").stdout.split() == ["A"]
    assert _cli(f, "commit", rid).returncode == 0
    assert _cli(f, "stock", "A").stdout.strip() == "2"


def test_cli_error_exit_code(tmp_path):
    f = tmp_path / "cli.json"
    r = _cli(f, "stock", "NOPE")
    assert r.returncode == 1
    assert r.stderr.strip()
