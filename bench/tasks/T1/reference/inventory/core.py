import json
import os
import uuid


class InventoryError(Exception):
    pass


class UnknownItemError(InventoryError):
    pass


class DuplicateItemError(InventoryError):
    pass


class InsufficientStockError(InventoryError):
    pass


class InvalidQuantityError(InventoryError):
    pass


def _positive(qty):
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
        raise InvalidQuantityError(f"数量は 1 以上の整数: {qty!r}")


def _non_negative(qty):
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
        raise InvalidQuantityError(f"数量は 0 以上の整数: {qty!r}")


class Inventory:
    def __init__(self, path=None):
        self._path = path
        self._items = {}
        self._reservations = {}
        if path is not None and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._items = data["items"]
            self._reservations = data["reservations"]

    def _item(self, sku):
        try:
            return self._items[sku]
        except KeyError:
            raise UnknownItemError(sku) from None

    def add_item(self, sku, name, quantity=0, reorder_level=0):
        _non_negative(quantity)
        _non_negative(reorder_level)
        if sku in self._items:
            raise DuplicateItemError(sku)
        self._items[sku] = {"name": name, "on_hand": quantity, "reorder_level": reorder_level}

    def receive(self, sku, qty):
        _positive(qty)
        self._item(sku)["on_hand"] += qty

    def on_hand(self, sku):
        return self._item(sku)["on_hand"]

    def _reserved(self, sku):
        return sum(r["qty"] for r in self._reservations.values() if r["sku"] == sku)

    def available(self, sku):
        return self._item(sku)["on_hand"] - self._reserved(sku)

    def reserve(self, sku, qty):
        _positive(qty)
        if qty > self.available(sku):
            raise InsufficientStockError(sku)
        res_id = uuid.uuid4().hex
        self._reservations[res_id] = {"sku": sku, "qty": qty}
        return res_id

    def _res(self, res_id):
        try:
            return self._reservations[res_id]
        except KeyError:
            raise UnknownItemError(res_id) from None

    def release(self, res_id):
        self._res(res_id)
        del self._reservations[res_id]

    def commit(self, res_id):
        r = self._res(res_id)
        self._items[r["sku"]]["on_hand"] -= r["qty"]
        del self._reservations[res_id]

    def low_stock(self):
        return sorted(s for s, i in self._items.items() if self.available(s) <= i["reorder_level"])

    def save(self):
        if self._path is None:
            raise InventoryError("path が指定されていません")
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({"items": self._items, "reservations": self._reservations}, f, ensure_ascii=False)
