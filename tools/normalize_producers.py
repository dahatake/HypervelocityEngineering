"""normalize_producers.py — Per-Step YAML 内の producer 参照を per-Step ファイル名形式に正規化する。

Q-A2.3=A: producer は `<Agent>--<workflow>--<stepId>` 形式を採用。

ロジック:
  1. 全 per-Step YAML を走査し、各 outputs path → producer_basename を逆引きインデックス化。
  2. 各 per-Step YAML の inputs[].producer を Agent 名から逆引き結果へ置換。
     - 1 path に複数 producer がある場合は、artifact key の整合性を優先するため
       最初に見つかった producer を採用（警告表示）。
     - input.kind != agent_artifact のものはスキップ。
     - input.path に対応する producer が見つからない場合は producer を変更しない（warning）。
  3. 自己参照（input.path が自身の outputs にもある）は producer = 自身のファイル basename にする。
"""
from __future__ import annotations
import sys
from pathlib import Path
from collections import defaultdict
import fnmatch
import yaml

REPO = Path(__file__).resolve().parents[1]
IOC = REPO / ".github" / "io-contracts"


def load_yaml(fp: Path) -> dict:
    with fp.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def emit_yaml(fp: Path, data: dict) -> None:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    fp.write_text(text, encoding="utf-8")


def main() -> int:
    files = sorted(p for p in IOC.glob("*.yaml") if "--" in p.stem)
    contracts: dict[str, dict] = {f.stem: load_yaml(f) for f in files}

    # path -> [producer_basename, ...]
    producers: dict[str, list[str]] = defaultdict(list)
    for basename, c in contracts.items():
        for o in (c.get("outputs") or []):
            if isinstance(o, dict):
                p = (o.get("path") or "").strip()
                if p:
                    producers[p].append(basename)

    def find_producer(path: str, self_basename: str) -> str | None:
        if path in producers:
            cand = producers[path]
            # 自己参照優先
            if self_basename in cand:
                return self_basename
            return cand[0]
        # wildcard fallback - both directions
        for pp, lst in producers.items():
            if "*" in path and (fnmatch.fnmatchcase(pp, path) or fnmatch.fnmatchcase(path.replace("*", "ANY"), pp.replace("*", "ANY"))):
                return lst[0]
        # ディレクトリ prefix fallback: input が "foo/" のとき outputs に "foo/..." があれば一致
        if path.endswith("/"):
            for pp, lst in producers.items():
                if pp.startswith(path):
                    return lst[0]
        # placeholder-aware fallback: `{...}` を `*` に正規化して比較
        def normalize_path(s: str) -> str:
            import re
            return re.sub(r"\{[^}]+\}", "*", s)
        norm_path = normalize_path(path)
        for pp, lst in producers.items():
            np = normalize_path(pp)
            if norm_path == np or fnmatch.fnmatchcase(np, norm_path) or fnmatch.fnmatchcase(norm_path, np):
                return lst[0]
        return None

    updated = 0
    warnings: list[str] = []
    for basename, c in contracts.items():
        changed = False
        for inp in (c.get("inputs") or []):
            if not isinstance(inp, dict):
                continue
            if inp.get("kind") != "agent_artifact":
                continue
            p = (inp.get("path") or "").strip()
            new_prod = find_producer(p, basename)
            if new_prod is None:
                if inp.get("required") is True:
                    warnings.append(f"{basename}: no producer for required input '{p}'")
                continue
            if inp.get("producer") != new_prod:
                inp["producer"] = new_prod
                changed = True
        if changed:
            emit_yaml(IOC / f"{basename}.yaml", c)
            updated += 1

    print(f"Updated: {updated}")
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings[:30]:
            print(f"  {w}")
        if len(warnings) > 30:
            print(f"  ... and {len(warnings)-30} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
