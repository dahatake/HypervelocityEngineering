import argparse
import sys

from .core import Inventory, InventoryError


def main(argv=None):
    p = argparse.ArgumentParser(prog="inventory")
    p.add_argument("--file", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("sku")
    a.add_argument("name")
    a.add_argument("qty", type=int)
    a.add_argument("--reorder", type=int, default=0)
    for name in ("receive", "reserve"):
        s = sub.add_parser(name)
        s.add_argument("sku")
        s.add_argument("qty", type=int)
    for name in ("release", "commit"):
        sub.add_parser(name).add_argument("res_id")
    sub.add_parser("stock").add_argument("sku")
    sub.add_parser("low")
    args = p.parse_args(argv)
    try:
        inv = Inventory(args.file)
        if args.cmd == "add":
            inv.add_item(args.sku, args.name, args.qty, args.reorder)
        elif args.cmd == "receive":
            inv.receive(args.sku, args.qty)
        elif args.cmd == "reserve":
            print(inv.reserve(args.sku, args.qty))
        elif args.cmd == "release":
            inv.release(args.res_id)
        elif args.cmd == "commit":
            inv.commit(args.res_id)
        elif args.cmd == "stock":
            print(inv.available(args.sku))
        elif args.cmd == "low":
            for sku in inv.low_stock():
                print(sku)
        inv.save()
    except InventoryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
