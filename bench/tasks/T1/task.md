# 在庫管理ライブラリ（予約と在庫アラート付き）

## 目的

小さな倉庫の担当者が、在庫数と予約を間違えずに管理したい。
在庫が少なくなった商品を、すぐ見つけられるようにしたい。

## 要求

- 商品（SKU・名前・在庫数・発注点）を登録できる。
- 入庫で在庫数を増やせる。
- 商品を予約できる。予約した分は「引当可能数」から引く。在庫数（実在庫）は予約では減らない。
- 引当可能数より多い数は予約できない。
- 予約を取り消すと、引当可能数が戻る。
- 予約を確定すると、実在庫がその数だけ減り、予約は消える。
- 引当可能数が発注点以下の商品を、一覧で取得できる。
- 内容を JSON ファイルに保存でき、次回起動時に読み込める。
- 同じ操作を CLI からも実行できる。

## 公開インターフェース（固定）

Python 3.11、pytest。第三者のランタイム依存は使わない。パッケージ名は `inventory`。リポジトリ直下に置く。

### 例外（`inventory` から import できる）

- `InventoryError(Exception)`：基底。
- `UnknownItemError(InventoryError)`：存在しない SKU や予約 ID。
- `DuplicateItemError(InventoryError)`：登録済みの SKU の再登録。
- `InsufficientStockError(InventoryError)`：引当可能数の不足。
- `InvalidQuantityError(InventoryError)`：数量が 1 未満（`add_item` の初期在庫と発注点は 0 以上）。

### クラス `inventory.Inventory`

| 呼び出し | 動作 |
|---|---|
| `Inventory(path=None)` | `path` が既存ファイルなら読み込む。`None` ならメモリのみ。 |
| `add_item(sku, name, quantity=0, reorder_level=0)` | 商品を登録する。重複は `DuplicateItemError`。 |
| `receive(sku, qty)` | 実在庫を `qty` 増やす。 |
| `on_hand(sku) -> int` | 実在庫。 |
| `available(sku) -> int` | 実在庫 − 予約中の合計。 |
| `reserve(sku, qty) -> str` | 予約し、予約 ID（文字列）を返す。不足は `InsufficientStockError`。 |
| `release(res_id)` | 予約を取り消す。 |
| `commit(res_id)` | 予約を確定する（実在庫を減らし、予約を消す）。 |
| `low_stock() -> list[str]` | `available(sku) <= reorder_level` の SKU を昇順で返す。 |
| `save()` | `path` に JSON で保存する。`path` が `None` なら `InventoryError`。 |

### CLI

`python -m inventory --file <path> <command> ...`。成功は終了コード 0、エラーは 1 で、標準エラーにメッセージを出す。各コマンドの後に自動で保存する。

| コマンド | 出力（標準出力） |
|---|---|
| `add <sku> <name> <qty> [--reorder N]` | なし |
| `receive <sku> <qty>` | なし |
| `reserve <sku> <qty>` | 予約 ID だけを 1 行で出す |
| `release <res_id>` / `commit <res_id>` | なし |
| `stock <sku>` | 引当可能数だけを 1 行で出す |
| `low` | 該当 SKU を 1 行に 1 つ、昇順で出す |
