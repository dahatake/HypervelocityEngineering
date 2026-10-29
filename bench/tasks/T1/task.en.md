[日本語](task.md) | **English**

# Inventory management library (with reservations and stock alerts)

## Purpose

Staff at a small warehouse want to manage stock quantities and reservations without mistakes.
They also want to quickly find items whose stock is running low.

## Requirements

- Items (SKU, name, stock quantity, reorder level) can be registered.
- Receiving goods increases the stock quantity.
- Items can be reserved. The reserved quantity is subtracted from the "available quantity". The stock quantity (physical stock) does not decrease on reservation.
- A quantity greater than the available quantity cannot be reserved.
- Cancelling a reservation restores the available quantity.
- Committing a reservation decreases the physical stock by that quantity, and the reservation disappears.
- Items whose available quantity is at or below the reorder level can be retrieved as a list.
- The contents can be saved to a JSON file and loaded on the next startup.
- The same operations can also be run from a CLI.

## Public interface (fixed)

Python 3.11, pytest. No third-party runtime dependencies. The package name is `inventory`. Place it at the repository root.

### Exceptions (importable from `inventory`)

- `InventoryError(Exception)`: base class.
- `UnknownItemError(InventoryError)`: a nonexistent SKU or reservation ID.
- `DuplicateItemError(InventoryError)`: re-registering an already registered SKU.
- `InsufficientStockError(InventoryError)`: insufficient available quantity.
- `InvalidQuantityError(InventoryError)`: the quantity is less than 1 (for `add_item`, the initial stock and reorder level must be 0 or more).

### Class `inventory.Inventory`

| Call | Behavior |
|---|---|
| `Inventory(path=None)` | If `path` is an existing file, load it. If `None`, in-memory only. |
| `add_item(sku, name, quantity=0, reorder_level=0)` | Register an item. A duplicate raises `DuplicateItemError`. |
| `receive(sku, qty)` | Increase the physical stock by `qty`. |
| `on_hand(sku) -> int` | Physical stock. |
| `available(sku) -> int` | Physical stock − total of active reservations. |
| `reserve(sku, qty) -> str` | Reserve and return the reservation ID (a string). Insufficient quantity raises `InsufficientStockError`. |
| `release(res_id)` | Cancel a reservation. |
| `commit(res_id)` | Commit a reservation (decrease the physical stock and remove the reservation). |
| `low_stock() -> list[str]` | Return, in ascending order, the SKUs for which `available(sku) <= reorder_level`. |
| `save()` | Save to `path` as JSON. If `path` is `None`, raise `InventoryError`. |

### CLI

`python -m inventory --file <path> <command> ...`. Success exits with code 0; an error exits with 1 and writes a message to standard error. It saves automatically after each command.

| Command | Output (standard output) |
|---|---|
| `add <sku> <name> <qty> [--reorder N]` | None |
| `receive <sku> <qty>` | None |
| `reserve <sku> <qty>` | Only the reservation ID, on one line |
| `release <res_id>` / `commit <res_id>` | None |
| `stock <sku>` | Only the available quantity, on one line |
| `low` | The matching SKUs, one per line, in ascending order |
