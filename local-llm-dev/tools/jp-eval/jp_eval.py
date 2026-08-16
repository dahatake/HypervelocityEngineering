#!/usr/bin/env python3
"""日本語ローカル LLM 評価ツール（Ollama ネイティブ API 専用）。

測定するのは **客観的に自動判定できる項目だけ** である。
意味的な正確さ・日本語としての自然さは自動測定できないため、本ツールの対象外。
詳細と限界は README.md を参照。

使い方:
    python jp_eval.py run   --models qwen3:8b phi4-mini:latest
    python jp_eval.py score
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"

HIRA_KATA = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")
CJK = re.compile(r"[\u4E00-\u9FFF]")
LATIN = re.compile(r"[A-Za-z]")
CODE_FENCE = re.compile(r"```([A-Za-z0-9_+-]*)\s*\n(.*?)```", re.S)
HEADING = re.compile(r"^#{1,6}\s", re.M)

# 中国語簡体字のうち、日本語の漢字表記としては使われない字だけを列挙する。
# 「点・会・来」などは日本語でも使うため含めてはならない（誤検出の原因になる）。
SIMPLIFIED_ONLY = frozenset(
    "这说时间关发请给对个们为级样经现题实进种还认识语义员务开"
    "东车马鸟鱼长门问闻阳阴电话习练"
)

# ひらがな出現数による日本語判定が構造的に成立しない設問。
JP_METRIC_NA = frozenset({"U1-05"})


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def chat(endpoint: str, model: str, messages: list[dict], *,
         num_ctx: int = 8192, timeout: int = 1800, retries: int = 5) -> dict:
    """1 回のチャット補完。推論サーバは散発的に 500 や切断を返すため再試行する。"""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0, "seed": 42, "num_ctx": num_ctx},
    }
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{endpoint}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8"))
            body["_wall_sec"] = round(time.perf_counter() - t0, 2)
            body["_attempts"] = attempt + 1
            return body
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"    retry {attempt + 1}/{retries}: {type(e).__name__}: {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    assert last is not None
    raise last


def final_answer(body: dict) -> str:
    """推論トレース（thinking / <think> / harmony analysis）を除いた最終回答。"""
    text = (body.get("message") or {}).get("content") or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    # 出力が打ち切られて </think> が欠けた場合、以降すべてを推論トレースとみなす。
    text = re.sub(r"<think>.*\Z", "", text, flags=re.S)
    text = re.sub(r"<\|channel\|>analysis.*?<\|(?:end|message)\|>", "", text, flags=re.S)
    return text.strip()


def strip_code_blocks(text: str) -> str:
    """コードブロックを除去する。

    Markdown 見出しの判定で Python の `# コメント` を見出しと誤検出しないために使う。
    """
    text = CODE_FENCE.sub("", text)
    # 閉じられていないフェンスは、開始位置以降をコードとみなす。
    return re.sub(r"```.*\Z", "", text, flags=re.S)


# --------------------------------------------------------------------------- #
# 指標
# --------------------------------------------------------------------------- #
def jp_metrics(text: str) -> dict:
    hira = len(HIRA_KATA.findall(text))
    cjk = len(CJK.findall(text))
    latin = len(LATIN.findall(text))
    total = hira + cjk + latin
    zh = sorted(set(text) & SIMPLIFIED_ONLY)
    return {
        "hira_kata_count": hira,
        "cjk_count": cjk,
        "latin_count": latin,
        "jp_char_ratio": round((hira + cjk) / total, 3) if total else 0.0,
        # ひらがな/カタカナが一定数あれば日本語で書かれたと判断する。
        "is_japanese": hira >= 5,
        "simplified_chinese_chars": zh,
        "has_simplified_chinese": bool(zh),
    }


def fences(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in CODE_FENCE.finditer(text)]


def check_u1(task: dict, out: str) -> dict:
    c = task.get("checks", {})
    fl = fences(out)
    res: dict = {}
    if c.get("must_have_code_fence"):
        res["code_fence"] = bool(fl)
        if c.get("fence_lang"):
            res["fence_lang_ok"] = any(lang.lower() == c["fence_lang"] for lang, _ in fl)
    if c.get("must_not_have_code_fence"):
        res["no_code_fence"] = not fl
    if c.get("must_contain"):
        res["contains_all"] = all(s in out for s in c["must_contain"])
    if c.get("must_contain_any"):
        res["contains_any"] = any(s in out for s in c["must_contain_any"])
    if c.get("must_not_contain_tokens"):
        res["no_forbidden_tokens"] = not any(s in out for s in c["must_not_contain_tokens"])
    if c.get("must_be_json"):
        body = fl[0][1] if fl else out
        try:
            parsed = json.loads(body.strip())
            res["json_valid"] = True
            if c.get("json_must_have_key"):
                res["json_key_ok"] = c["json_must_have_key"] in parsed
        except Exception:  # noqa: BLE001
            res["json_valid"] = False
            if c.get("json_must_have_key"):
                res["json_key_ok"] = False
    if c.get("require_japanese"):
        res["japanese"] = jp_metrics(out)["is_japanese"]
    return res


def check_instruction(task: dict, out: str) -> dict:
    """指示追従の 4 ルールを判定する。適用外は None（集計から除外される）。"""
    fl = fences(out)
    return {
        "r1_japanese": jp_metrics(out)["is_japanese"],
        # コード内の `# コメント` を見出しと誤判定しないようコードブロックを除いてから見る。
        "r2_no_heading": not HEADING.search(strip_code_blocks(out)),
        "r3_unknown": ("不明" in out) if task.get("unknowable") else None,
        "r4_python_fence": (
            any(lang.lower() == "python" for lang, _ in fl) if task.get("expects_code") else None
        ),
    }


# --------------------------------------------------------------------------- #
# バリアント間の比較可能性
# --------------------------------------------------------------------------- #
# 判定が「この語が出力に含まれるか」を見ているルールと、その語。
# どちらかのバリアントがこの語を指示していないと、そのバリアントは
# モデルがどんなに忠実に従っても合格できず、比較が無効になる。
JUDGED_LITERALS = {
    "r3_unknown": ["不明"],
    "r4_python_fence": ["python"],
}


def variant_comparability_errors(spec: dict) -> list[str]:
    """バリアント間で判定条件が非対称になっていないか検査する。"""
    errors = []
    for rule, literals in JUDGED_LITERALS.items():
        for name, text in spec["instruction_variants"].items():
            for lit in literals:
                if lit not in text:
                    errors.append(
                        f"{rule}: バリアント '{name}' が判定語 '{lit}' を指示していない。"
                        "このバリアントは構造的に合格できず、比較が無効になる。"
                    )
    return errors


def variant_sha(text: str) -> str:
    """指示文の指紋。文面を変えたら古い結果を使い回さないようにするために使う。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# 実行
# --------------------------------------------------------------------------- #
def _row_key(r: dict) -> tuple[str, str, str]:
    return (r.get("suite", ""), r.get("variant", ""), r.get("id", ""))


def cmd_run(args: argparse.Namespace) -> int:
    spec = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))

    # 無効なデータを 1 時間かけて作らないよう、実行前に比較可能性を検査する。
    if "INSTR" in args.suites:
        problems = variant_comparability_errors(spec)
        if problems:
            print("バリアントの比較可能性の検査に失敗しました:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    variants = args.variants or list(spec["instruction_variants"])
    shas = {v: variant_sha(spec["instruction_variants"][v]) for v in spec["instruction_variants"]}
    planned: list[tuple[str, str, dict]] = []
    if "U1" in args.suites:
        planned += [("U1", "", t) for t in spec["u1_tasks"]]
    if "INSTR" in args.suites:
        for v in variants:
            planned += [("INSTR", v, t) for t in spec["instruction_tasks"]]

    for model in args.models:
        path = out_dir / (model.replace(":", "_").replace("/", "_") + ".json")
        rows: list[dict] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

        # 指示文が変わった INSTR の結果は、現在の設定の測定値ではないので捨てる。
        fresh, stale = [], 0
        for r in rows:
            if r.get("suite") == "INSTR" and r.get("variant_sha") != shas.get(r.get("variant")):
                stale += 1
                continue
            fresh.append(r)
        if stale:
            print(f"  {model}: 指示文が変わったため {stale} 件の古い結果を破棄して再取得します。",
                  flush=True)
        rows = fresh

        have = {_row_key(r) for r in rows}
        todo = [(s, v, t) for s, v, t in planned if (s, v, t["id"]) not in have]

        print(f"\n########## {model} ({len(todo)} / {len(planned)} 件を実行) ##########", flush=True)
        if not todo:
            print("  すべて取得済み。スキップします。", flush=True)
            continue

        failures = []
        for suite, variant, task in todo:
            if suite == "U1":
                messages = [{"role": "user", "content": task["prompt"]}]
            else:
                messages = [
                    {"role": "system", "content": spec["instruction_variants"][variant]},
                    {"role": "user", "content": task["prompt"]},
                ]
            try:
                body = chat(args.endpoint, model, messages,
                            num_ctx=args.num_ctx, retries=args.retries)
            except Exception as e:  # noqa: BLE001
                failures.append({"suite": suite, "variant": variant,
                                 "id": task["id"], "error": repr(e)})
                print(f"  {task['id']} 断念 {type(e).__name__}", flush=True)
                continue

            out = final_answer(body)
            row = {
                "suite": suite,
                "variant": variant,
                "id": task["id"],
                "model": model,
                "wall_sec": body["_wall_sec"],
                "attempts": body.get("_attempts"),
                "eval_count": body.get("eval_count"),
                "eval_duration_ns": body.get("eval_duration"),
                "prompt_eval_count": body.get("prompt_eval_count"),
                "jp": jp_metrics(out),
                "final_answer": out,
            }
            if suite == "U1":
                row["category"] = task["category"]
                row["checks"] = check_u1(task, out)
                shown = row["checks"]
            else:
                row["rules"] = check_instruction(task, out)
                row["variant_sha"] = shas[variant]
                shown = row["rules"]
            rows.append(row)
            # 途中終了しても再開できるよう 1 件ごとに保存する。
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  [{suite}{'/' + variant if variant else ''}] {task['id']}: "
                  f"{shown} {row['wall_sec']}s", flush=True)

        if failures:
            print(f"  未取得 {len(failures)} 件: "
                  f"{[f['id'] for f in failures]}（再実行すると自動で補完されます）", flush=True)
        print(f"  -> {path}", flush=True)
    return 0


# --------------------------------------------------------------------------- #
# 集計
# --------------------------------------------------------------------------- #
def _tps(row: dict) -> float | None:
    n, d = row.get("eval_count"), row.get("eval_duration_ns")
    return round(n / (d / 1e9), 1) if n and d else None


def _rate(vals: list[bool]) -> str:
    return f"{sum(vals)}/{len(vals)}" if vals else "-"


def cmd_score(args: argparse.Namespace) -> int:
    files = sorted(Path(args.results).glob("*.json"))
    if not files:
        raise SystemExit(f"結果ファイルがありません: {args.results}")

    spec = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
    u1_by_id = {t["id"]: t for t in spec["u1_tasks"]}
    instr_by_id = {t["id"]: t for t in spec["instruction_tasks"]}

    data: dict[str, list[dict]] = {}
    for f in files:
        rows = json.loads(f.read_text(encoding="utf-8"))
        if not rows:
            continue
        # 保存された生出力を正本とし、判定は常に現行ロジックで再計算する。
        # こうしておくと、判定の欠陥を修正したときにモデルを再実行せずに済む。
        for r in rows:
            answer = r.get("final_answer", "")
            r["jp"] = jp_metrics(answer)
            if r["suite"] == "U1" and r["id"] in u1_by_id:
                r["checks"] = check_u1(u1_by_id[r["id"]], answer)
            elif r["suite"] == "INSTR" and r["id"] in instr_by_id:
                r["rules"] = check_instruction(instr_by_id[r["id"]], answer)
        data[rows[0]["model"]] = rows

    models = sorted(data)
    out: list[str] = ["# 日本語ローカル LLM 評価結果", ""]
    out.append(f"- 対象モデル: {len(models)} 件")
    out.append("- 判定対象は形式遵守・出力言語・速度のみ。意味的な正確さは測定していない。")
    out.append("- 判定は保存された生出力から集計時に再計算されている。")
    out.append("")

    # 指示文が変わった結果を混ぜて集計すると、比較の意味が失われる。
    shas = {v: variant_sha(t) for v, t in spec["instruction_variants"].items()}
    stale = sorted({
        f"{m} / {r['variant']}"
        for m in models for r in data[m]
        if r["suite"] == "INSTR" and r.get("variant_sha") != shas.get(r["variant"])
    })
    if stale:
        warn = (
            "**警告: 現在の prompts.json とは異なる指示文で取得された結果が含まれている。**"
            " 下の指示追従率は指示文の異なるデータを混ぜているため、"
            "否定形と肯定形の比較には使えない。`run` を再実行して取り直すこと。"
        )
        print(f"警告: 指示文が変わった結果が {len(stale)} 組ある -> {stale}", file=sys.stderr)
        out.append(f"> {warn}")
        out.append(">")
        out.append(f"> 該当: {', '.join(stale)}")
        out.append("")

    # ---- U1 ----
    out.append("## 1. 日本語タスク（U1）")
    out.append("")
    out.append("※ U1-05 は期待出力がひらがなを含まないため、日本語判定を合格率から除外している。")
    out.append("")
    out.append("| モデル | 合格率 | 日本語で回答 | 簡体字混入 | 平均 tok/s |")
    out.append("|---|---|---|---|---|")
    for m in models:
        u1 = [r for r in data[m] if r["suite"] == "U1"]
        if not u1:
            continue
        checks = [v for r in u1 for k, v in r["checks"].items()
                  if isinstance(v, bool) and not (k == "japanese" and r["id"] in JP_METRIC_NA)]
        jp_scope = [r for r in u1 if r["id"] not in JP_METRIC_NA and "japanese" in r["checks"]]
        zh = sum(1 for r in u1 if r["jp"]["has_simplified_chinese"])
        speeds = [t for t in (_tps(r) for r in u1) if t]
        out.append(
            f"| {m} | {sum(checks)}/{len(checks)} "
            f"({round(100 * sum(checks) / len(checks)) if checks else 0}%) | "
            f"{_rate([r['jp']['is_japanese'] for r in jp_scope])} | {zh}/{len(u1)} | "
            f"{round(sum(speeds) / len(speeds), 1) if speeds else '-'} |"
        )

    # ---- 指示追従（否定形 vs 肯定形） ----
    variants = sorted({r["variant"] for m in models for r in data[m]
                       if r["suite"] == "INSTR" and r.get("variant")})
    if variants:
        out.append("")
        out.append("## 2. 指示追従率（システムプロンプトの書き方による比較）")
        out.append("")
        out.append("ルール: r1=日本語で回答 / r2=見出しを使わない / "
                   "r3=答えられない設問で「不明」と書く / r4=```python フェンス")
        out.append("")
        header = "| モデル | 書き方 | r1 | r2 | r3 | r4 | 総合追従率 |"
        out.append(header)
        out.append("|---|---|---|---|---|---|---|")
        summary: dict[str, dict[str, float]] = {}
        for m in models:
            for v in variants:
                rows = [r for r in data[m] if r["suite"] == "INSTR" and r["variant"] == v]
                if not rows:
                    continue
                agg: dict[str, list[bool]] = {}
                for r in rows:
                    for k, val in r["rules"].items():
                        if isinstance(val, bool):
                            agg.setdefault(k, []).append(val)
                allv = [x for vals in agg.values() for x in vals]
                rate = 100 * sum(allv) / len(allv) if allv else 0.0
                summary.setdefault(m, {})[v] = rate
                cells = [_rate(agg.get(k, [])) for k in
                         ("r1_japanese", "r2_no_heading", "r3_unknown", "r4_python_fence")]
                out.append(f"| {m} | {v} | " + " | ".join(cells) + f" | {rate:.0f}% |")

        if len(variants) == 2:
            a, b = variants
            out.append("")
            out.append(f"### {a} と {b} の差")
            out.append("")
            out.append(f"| モデル | {a} | {b} | 差分 |")
            out.append("|---|---|---|---|")
            deltas = []
            for m, s in summary.items():
                if a in s and b in s:
                    d = s[b] - s[a]
                    deltas.append(d)
                    out.append(f"| {m} | {s[a]:.0f}% | {s[b]:.0f}% | {d:+.0f} pt |")
            if deltas:
                out.append(f"| **平均** | | | **{sum(deltas) / len(deltas):+.1f} pt** |")

    # ---- 速度 ----
    out.append("")
    out.append("## 3. 速度")
    out.append("")
    out.append("| モデル | 実施設問数 | 生成トークン合計 | 平均 tok/s | 総所要秒 |")
    out.append("|---|---|---|---|---|")
    for m in models:
        rows = data[m]
        speeds = [t for t in (_tps(r) for r in rows) if t]
        out.append(
            f"| {m} | {len(rows)} | {sum(r.get('eval_count') or 0 for r in rows)} | "
            f"{round(sum(speeds) / len(speeds), 1) if speeds else '-'} | "
            f"{round(sum(r['wall_sec'] for r in rows), 1)} |"
        )

    # ---- 簡体字 ----
    out.append("")
    out.append("## 4. 簡体字混入の検出")
    out.append("")
    hits = [f"- {m} {r['suite']} {r['id']}: {r['jp']['simplified_chinese_chars']}"
            for m in models for r in data[m] if r["jp"]["has_simplified_chinese"]]
    out.extend(hits or ["- 検出なし"])

    text = "\n".join(out) + "\n"
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    # モデル出力には日本語以外の文字が混ざりうる。Windows 既定の cp932 コンソールでは
    # それらが encode できず集計が落ちるため、標準出力を UTF-8 に切り替える。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description="日本語ローカル LLM 評価ツール")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="評価を実行する（既取得分はスキップし未取得分だけ補完する）")
    r.add_argument("--models", nargs="+", required=True, help="評価するモデル名")
    r.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=f"既定 {DEFAULT_ENDPOINT}")
    r.add_argument("--out", default=str(HERE / "results"), help="結果 JSON の出力先")
    r.add_argument("--variants", nargs="*", help="指示追従の書き方（既定は全て）")
    r.add_argument("--suites", nargs="+", default=["U1", "INSTR"],
                   choices=["U1", "INSTR"], help="実行するスイート（既定は両方）")
    r.add_argument("--num-ctx", type=int, default=8192, dest="num_ctx")
    r.add_argument("--retries", type=int, default=5)
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("score", help="結果を集計して Markdown を出力する")
    s.add_argument("--results", default=str(HERE / "results"))
    s.add_argument("--out", default=str(HERE / "summary.md"))
    s.set_defaults(func=cmd_score)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
