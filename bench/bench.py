#!/usr/bin/env python3
"""conductor と Spec Kit の比較ベンチマークの補助ツール（標準ライブラリのみ）。"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parent
TASKS = BENCH / "tasks"
RESULTS = BENCH / "results"
TOOLS = ("conductor", "speckit")
TOOL_LABEL = {"conductor": "conductor", "speckit": "Spec Kit"}
GREENFIELD = ("T1", "T2")
BROWNFIELD = ("T3",)
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


def task_ids():
    return sorted(p.name for p in TASKS.iterdir() if (p / "task.md").exists())


def task_dir(task):
    d = TASKS / task
    if not (d / "task.md").exists():
        raise SystemExit(f"error: 不明なタスク: {task}")
    return d


def toolkit_version():
    text = (ROOT / "scripts" / "hvelib.py").read_text(encoding="utf-8")
    m = re.search(r'^TOOLKIT_VERSION\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else None


def _inside(child, parent):
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def cmd_prepare(args):
    d = task_dir(args.task)
    dest = Path(args.dest).resolve()
    if _inside(dest, ROOT):
        raise SystemExit("error: dest はこのリポジトリの外に置いてください")
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit("error: dest が空ではありません")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(d / "task.md", dest / "TASK.md")
    seed = d / "seed"
    if seed.is_dir():
        shutil.copytree(seed, dest, dirs_exist_ok=True, ignore=IGNORE)
    git = ["git", "-c", "user.name=bench", "-c", "user.email=bench@example.invalid"]
    for c in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "initial state"]):
        subprocess.run(git + c, cwd=dest, check=True, capture_output=True)
    print(f"準備できました: {dest}")
    return 0


def run_score(task, repo):
    d = task_dir(task)
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise SystemExit(f"error: repo がありません: {repo}")
    reqs = json.loads((d / "hidden" / "requirements.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="hve-bench-") as tmp:
        hidden = Path(tmp) / "hidden"
        shutil.copytree(d / "hidden", hidden, ignore=IGNORE)
        xml_path = Path(tmp) / "result.xml"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(hidden / "test_acceptance.py"),
             "--rootdir", str(hidden), "-p", "no:cacheprovider", "-q",
             f"--junitxml={xml_path}"],
            cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        outcomes = {}
        if xml_path.exists():
            for tc in ET.parse(xml_path).getroot().iter("testcase"):
                bad = any(tc.find(t) is not None for t in ("failure", "error", "skipped"))
                outcomes[tc.get("name")] = not bad
    per_req = {}
    for rid, info in reqs.items():
        tests = info["tests"]
        per_req[rid] = {
            "title": info.get("title", ""),
            "passed": bool(tests) and all(outcomes.get(t, False) for t in tests),
        }
    return {
        "hidden_pass": sum(1 for ok in outcomes.values() if ok),
        "hidden_total": len(outcomes),
        "verified_requirements": sum(1 for r in per_req.values() if r["passed"]),
        "total_requirements": len(reqs),
        "requirements": per_req,
        "tests": outcomes,
        "pytest_returncode": proc.returncode,
        "pytest_output_tail": proc.stdout[-1500:] if not outcomes else "",
    }


def cmd_score(args):
    s = run_score(args.task, args.repo)
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        print(f"hidden: {s['hidden_pass']}/{s['hidden_total']}")
        print(f"要求の検証済み: {s['verified_requirements']}/{s['total_requirements']}")
        for rid, r in s["requirements"].items():
            print(f"  {rid} {'OK' if r['passed'] else 'NG'}  {r['title']}")
        if s["pytest_output_tail"]:
            print(s["pytest_output_tail"])
    return 0


def nsm(verified, interventions):
    return verified / interventions if interventions and interventions > 0 else None


def cmd_record(args):
    if args.interventions < 1:
        raise SystemExit("error: interventions は 1 以上（最初の依頼を 1 と数える）")
    s = run_score(args.task, args.repo)
    cwc = None if args.completed_without_correction is None else args.completed_without_correction == "yes"
    rec = {
        "tool": args.tool,
        "task": args.task,
        "run": args.run,
        "date": datetime.date.today().isoformat(),
        "toolkit_version": toolkit_version() if args.tool == "conductor" else None,
        "tool_version": args.tool_version,
        "model": args.model,
        "interventions": args.interventions,
        "hidden_pass": s["hidden_pass"],
        "hidden_total": s["hidden_total"],
        "verified_requirements": s["verified_requirements"],
        "total_requirements": s["total_requirements"],
        "nsm": nsm(s["verified_requirements"], args.interventions),
        "lead_time_min": args.lead_time_min,
        "human_minutes": args.human_minutes,
        "credits": args.credits,
        "completed_without_correction": cwc,
        "notes": args.notes,
        "requirements": {k: v["passed"] for k, v in s["requirements"].items()},
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{args.tool}-{args.task}-r{args.run}.json"
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"記録しました: {out}  hidden {rec['hidden_pass']}/{rec['hidden_total']}  "
          f"検証済み {rec['verified_requirements']}  NSM {rec['nsm']}")
    return 0


# ---- 集計 ----

def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def fmt(x, nd=2, pct=False):
    if x is None:
        return "-"
    return f"{x * 100:.0f}%" if pct else f"{x:.{nd}f}"


def pass_rate(r):
    return r["hidden_pass"] / r["hidden_total"] if r.get("hidden_total") else None


def credits_per_verified(rs):
    rs = [r for r in rs if r.get("credits") is not None]
    v = sum(r["verified_requirements"] for r in rs)
    return sum(r["credits"] for r in rs) / v if rs and v > 0 else None


def load_results(results_dir=None):
    d = Path(results_dir) if results_dir else RESULTS
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            print(f"warning: 読めない記録を飛ばします: {p.name}", file=sys.stderr)
    return out


def _by(results, tool, tasks=None):
    return [r for r in results if r["tool"] == tool and (tasks is None or r["task"] in tasks)]


def _nsm_mean(rs):
    return mean([r.get("nsm") for r in rs])


def hypotheses(results):
    """各仮説の (id, 内容, 判定, 根拠) を返す。判定は 未検証 / 支持 / 不支持。"""
    c, s = _by(results, "conductor"), _by(results, "speckit")
    both = bool(c and s)
    out = []

    # H1
    v, why = "未検証", "両ツールの記録が必要"
    if both:
        ci, si = mean([r["interventions"] for r in c]), mean([r["interventions"] for r in s])
        cm, sm = mean([r.get("human_minutes") for r in c]), mean([r.get("human_minutes") for r in s])
        ok = ci < si and (cm is None or sm is None or cm < sm)
        v = "支持" if ok else "不支持"
        why = f"介入 {fmt(ci)} 対 {fmt(si)}、人手分 {fmt(cm, 1)} 対 {fmt(sm, 1)}"
    out.append(("H1", "conductor は介入回数と人手の時間が少ない", v, why))

    # H2
    v, why = "未検証", "両ツールの記録が必要"
    if both:
        cp, sp = mean([pass_rate(r) for r in c]), mean([pass_rate(r) for r in s])
        v = "支持" if cp is not None and sp is not None and cp >= sp else "不支持"
        why = f"合格率 {fmt(cp, pct=True)} 対 {fmt(sp, pct=True)}"
    out.append(("H2", "conductor の隠しテスト合格率は Spec Kit 以上", v, why))

    # H3
    v, why = "未検証", "両ツールのクレジット記録が必要"
    cc, sc = credits_per_verified(c), credits_per_verified(s)
    if cc is not None and sc is not None:
        v = "支持" if cc <= sc * 1.2 else "不支持"
        why = f"検証済み要求あたり {fmt(cc)} 対 {fmt(sc)}（上限 +20% = {fmt(sc * 1.2)}）"
    out.append(("H3", "conductor はクレジットが多くても、検証済み要求あたり +20% 以内", v, why))

    # H4
    v, why = "未検証", "T3 と T1/T2 の両方に、両ツールの記録が必要"
    parts = {}
    for name, tasks in (("T3", BROWNFIELD), ("T1/T2", GREENFIELD)):
        a, b = _nsm_mean(_by(results, "conductor", tasks)), _nsm_mean(_by(results, "speckit", tasks))
        parts[name] = None if a is None or b is None else a - b
    if parts["T3"] is not None and parts["T1/T2"] is not None:
        v = "支持" if parts["T3"] > parts["T1/T2"] else "不支持"
        why = f"NSM の差（conductor − Spec Kit）T3 {fmt(parts['T3'])}、T1/T2 {fmt(parts['T1/T2'])}"
    out.append(("H4", "差は既存コードのある T3 で広がる", v, why))
    return out


def render(results, tasks=None):
    tasks = tasks or task_ids()
    L = ["# 比較結果（conductor と Spec Kit）", ""]
    L.append("このページは `python bench/bench.py aggregate` で作ります。手で直さないでください。")
    L.append("手順と条件は [README.md](README.md) にあります。")
    L.append("")
    if not results:
        L += ["> **未計測**です。記録（`bench/results/*.json`）がまだありません。",
              "> 下の表は予定の組み合わせで、値はすべて `-` です。", ""]
    else:
        L += [f"記録 {len(results)} 件から集計しました。未計測の組み合わせは `-` です。", ""]

    L += ["## ツール別の要約", "",
          "| ツール | 実行数 | NSM 平均 | 隠しテスト合格率 | 介入回数 平均 | リードタイム(分) 平均 | 人手(分) 平均 | クレジット/検証済み要求 | 修正なしで完了 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for t in TOOLS:
        rs = _by(results, t)
        cw = [r["completed_without_correction"] for r in rs if r.get("completed_without_correction") is not None]
        L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            TOOL_LABEL[t], len(rs), fmt(_nsm_mean(rs)),
            fmt(mean([pass_rate(r) for r in rs]), pct=True),
            fmt(mean([r["interventions"] for r in rs])),
            fmt(mean([r.get("lead_time_min") for r in rs]), 1),
            fmt(mean([r.get("human_minutes") for r in rs]), 1),
            fmt(credits_per_verified(rs)),
            fmt(sum(cw) / len(cw), pct=True) if cw else "-"))

    L += ["", "## タスク別", "",
          "| タスク | ツール | 実行数 | NSM 平均 | 検証済み要求 平均 | 隠しテスト合格率 | 介入回数 平均 | リードタイム(分) | 人手(分) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k in tasks:
        for t in TOOLS:
            rs = [r for r in _by(results, t) if r["task"] == k]
            L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                k, TOOL_LABEL[t], len(rs), fmt(_nsm_mean(rs)),
                fmt(mean([r["verified_requirements"] for r in rs]), 1),
                fmt(mean([pass_rate(r) for r in rs]), pct=True),
                fmt(mean([r["interventions"] for r in rs])),
                fmt(mean([r.get("lead_time_min") for r in rs]), 1),
                fmt(mean([r.get("human_minutes") for r in rs]), 1)))

    L += ["", "## 仮説", "",
          "両ツールの記録がそろった仮説だけ、自動で判定します。実行数が少ないうちは参考値です。", "",
          "| ID | 仮説 | 判定 | 根拠 |", "|---|---|---|---|"]
    for hid, text, verdict, why in hypotheses(results):
        L.append(f"| {hid} | {text} | {verdict} | {why} |")

    L += ["", "## 指標の定義", "",
          "| 指標 | 意味 |", "|---|---|",
          "| interventions | 人がエージェントに送った依頼の回数。最初の依頼を 1 とし、追加の指示・回答・修正・「続けて」を 1 回ずつ数える。Spec Kit は `/speckit-*` の呼び出しと手動の指示を 1 回ずつ数える。 |",
          "| hidden_pass / hidden_total | 隠し受入テストを、成果物のリポジトリに対して実行した結果。 |",
          "| verified_requirements | 隠しテストがすべて通った要求（R1..Rn）の数。 |",
          "| NSM | verified_requirements ÷ interventions。人の介入 1 回あたりの検証済み要求数。 |",
          "| lead_time_min | 最初の依頼から最終状態までの実時間（分）。 |",
          "| human_minutes | 人が実際に手を動かした時間（自己申告、分）。 |",
          "| credits | AI クレジットまたはプレミアムリクエスト数（任意）。 |",
          "| completed_without_correction | 人が修正の指示を出さずに、ツールが完了を報告したか。 |", ""]
    return "\n".join(L)


def cmd_aggregate(args):
    out = Path(args.out) if args.out else BENCH / "RESULTS.md"
    out.write_text(render(load_results(args.results_dir)), encoding="utf-8", newline="\n")
    print(f"書き出しました: {out}")
    return 0


def cmd_selfcheck(args):
    bad = 0
    for k in task_ids():
        ref = TASKS / k / "reference"
        if not ref.is_dir():
            print(f"{k}: reference がありません")
            bad += 1
            continue
        s = run_score(k, ref)
        ok = (s["hidden_total"] > 0 and s["hidden_pass"] == s["hidden_total"]
              and s["verified_requirements"] == s["total_requirements"])
        print(f"{k}: {s['hidden_pass']}/{s['hidden_total']} {'OK' if ok else 'NG'}")
        bad += 0 if ok else 1
    return 1 if bad else 0


def build_parser():
    p = argparse.ArgumentParser(prog="bench.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepare", help="タスク用の新しいリポジトリを作る")
    a.add_argument("--task", required=True)
    a.add_argument("--dest", required=True)
    a.set_defaults(fn=cmd_prepare)
    a = sub.add_parser("score", help="隠しテストを実行して採点する")
    a.add_argument("--task", required=True)
    a.add_argument("--repo", required=True)
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_score)
    a = sub.add_parser("record", help="採点して実行記録を書く")
    a.add_argument("--tool", required=True, choices=TOOLS)
    a.add_argument("--task", required=True)
    a.add_argument("--run", required=True, type=int)
    a.add_argument("--repo", required=True)
    a.add_argument("--interventions", required=True, type=int)
    a.add_argument("--lead-time-min", required=True, type=float)
    a.add_argument("--human-minutes", type=float)
    a.add_argument("--credits", type=float)
    a.add_argument("--model")
    a.add_argument("--tool-version")
    a.add_argument("--completed-without-correction", choices=("yes", "no"))
    a.add_argument("--notes", default="")
    a.set_defaults(fn=cmd_record)
    a = sub.add_parser("aggregate", help="RESULTS.md を作る")
    a.add_argument("--out")
    a.add_argument("--results-dir")
    a.set_defaults(fn=cmd_aggregate)
    a = sub.add_parser("selfcheck", help="reference が隠しテストに通るか確かめる")
    a.set_defaults(fn=cmd_selfcheck)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
