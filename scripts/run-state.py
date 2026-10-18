#!/usr/bin/env python3
"""run-state.py - run state under /work/runs/<run-id>/ for the conductor (plan §7.5, §7.6, §8.3).

Usage:
  python scripts/run-state.py start [--options-file F | --options "max_hours: 24\\n..."] [--new]
  python scripts/run-state.py status                       # resume summary (read this first in a new context)
  python scripts/run-state.py stage N [--done]             # 0 init,1 RD,2 audit,3 plan,4 ST design,5 impl,6 final
  python scripts/run-state.py progress "text"              # append one entry (<= 3 lines) to progress.md
  python scripts/run-state.py queue add --id I-01 --req FR-001[,FR-002..] [--ac AC-001] [--boundary B] [--depends I-00] [--shared X] [--summary S]
  python scripts/run-state.py queue set I-01 [--status todo|doing|done|blocked] [--attempts +1] [--branch B] [--worktree P] [--summary S]
  python scripts/run-state.py queue ready [--parallel 5]   # items that can start now (deps done, no shared boundary)
  python scripts/run-state.py queue show
  python scripts/run-state.py time                         # elapsed / max_hours; exit 3 when >= 85 %
  python scripts/run-state.py complete-check               # exit 0 only when the run may end (§8.3)
  python scripts/run-state.py lane decide --changed N [--flags security,conflict,shared,unresolved,goal_unmapped]   # fast|full（工程 1 の後）
  python scripts/run-state.py lane confirm [--flags ...]   # 工程 3 の後に queue の数で再判定。full なら fast に戻さない
  python scripts/run-state.py lane show
  python scripts/run-state.py human answers|resume|instruction [--note "..."]   # count one human prompt (KPI)
  python scripts/run-state.py land [--wait SEC]            # 全件完了の run を、共通ロックの下で main へ 1 本ずつ取り込む（0 取り込み済み・1 失敗・2 競合・3 主が未整備）
  python scripts/run-state.py finish [--result "..."] [--credits "..."]   # append docs/run-history.md, close the run
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ebaklib as h  # noqa: E402

STAGES = {0: "初期化", 1: "要求定義", 2: "独立監査", 3: "計画", 4: "System Test の設計", 5: "実装ループ", 6: "最終"}
DEFAULT_OPTIONS = {
    "max_hours": "24", "approval_policy": "安全範囲は推奨どおり", "parallel_workers": "auto",
    "scope": "承認済みすべて", "git_push": "しない", "deploy": "しない", "external_write": "しない",
    "paid_services": "使わない", "external_exposure": "公開しない",
    "system_test": "必要最小限",
}
HISTORY_HEADER = (
    "# 実行履歴\n\n"
    "conductor の 1 回の実行を 1 行で記録します（工程 6 で `scripts/run-state.py finish` が追記します）。"
    "`/work` の一時ファイルが消えても、実行の結果と KPI をここで追えます。\n\n"
    "| run-id | 開始 | 終了 | HEAD | 結果 | 実装した要求 ID | BLOCKED | AC pass 率 | 経過時間 | 1 回目のゲート通過率 | AI クレジット | 人の介入 | 検証済み要求 |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)
HISTORY_NEW_COLS = ("人の介入", "検証済み要求")
HUMAN_KINDS = ("request", "answers", "resume", "instruction")
MAX_REQS_PER_ITEM = 5
MAX_AC_PER_ITEM = 12


def upgrade_history(text: str) -> str:
    """Add the columns introduced in 1.2.0 to a run-history table written by an older version."""
    lines = text.split("\n")
    in_table = False
    for i, l in enumerate(lines):
        if re.match(r"^\|\s*run-id\s*\|", l):
            if all(c in l for c in HISTORY_NEW_COLS):
                return text
            lines[i] = l.rstrip() + "".join(f" {c} |" for c in HISTORY_NEW_COLS)
            in_table = True
            continue
        if in_table:
            if re.match(r"^\|[\s\-:|]+\|\s*$", l):
                lines[i] = l.rstrip() + "---|" * len(HISTORY_NEW_COLS)
            elif l.startswith("|"):
                lines[i] = l.rstrip() + " - |" * len(HISTORY_NEW_COLS)
            else:
                in_table = False
    return "\n".join(lines)


def ctx(args):
    root = Path(args.root).resolve() if args.root else h.repo_root()
    root = h.conductor_root(root, h.load_config(root))
    cfg = h.load_config(root)
    return root, cfg


def need_run(root, cfg) -> str:
    rid = h.current_run(root, cfg)
    if not rid or not (h.run_dir(root, cfg, rid) / "meta.json").exists():
        raise SystemExit("ERROR run-state: 実行中の run がありません。`run-state.py start` で始めます")
    return rid


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def elapsed_hours(meta: dict) -> float:
    try:
        start = parse_ts(meta["started_at"])
    except Exception:
        return 0.0
    return (dt.datetime.now().astimezone() - start).total_seconds() / 3600


def counts(queue: dict) -> Dict[str, int]:
    c = {"todo": 0, "doing": 0, "done": 0, "blocked": 0}
    for it in queue.get("items", []):
        c[it.get("status", "todo")] = c.get(it.get("status", "todo"), 0) + 1
    return c


def require_own_worktree(root: Path, cfg: dict, args) -> Optional[int]:
    """Each run must live in its own git worktree so that several runs in one VS Code never share a tree.

    A run started in the primary checkout is refused; a dedicated worktree (branch run/<id>) is created and its
    path printed so the job can be started there. Returns an exit code to stop, or None to continue.
    """
    if (cfg.get("run") or {}).get("require_worktree", True) is False or os.environ.get("EABK_ALLOW_PRIMARY") == "1":
        return None
    if getattr(args, "allow_primary", False) or not (root / ".git").is_dir():
        return None
    # The branch ref is created atomically by git, so concurrent starts (several chats in one minute) never share an ID:
    # the loser moves on to the next free minute-stamped ID.
    stamp = dt.datetime.now()
    for _ in range(60):
        rid = stamp.strftime("%Y%m%d%H%M")
        path = root.parent / f"{root.name}-run-{rid}"
        taken = path.exists() or h.ref_exists(root, f"refs/heads/run/{rid}")
        if not taken:
            rc, out = h.git(["worktree", "add", "-b", f"run/{rid}", str(path), "HEAD"], root)
            if rc == 0:
                break
            taken = path.exists() or h.ref_exists(root, f"refs/heads/run/{rid}")
            if not taken:
                print(f"ERROR run-state: 専用 worktree を作れませんでした: {out.strip()[:200]}")
                return 4
        stamp += dt.timedelta(minutes=1)
    else:
        print("ERROR run-state: 空いている run ID が見つかりませんでした")
        return 4
    # start the run inside the new worktree right away: no second VS Code window and no re-sent request
    cmd = [sys.executable, str(path / "scripts" / "run-state.py"), "start", "--run-id", rid]
    if getattr(args, "options_file", None):
        cmd += ["--options-file", str(Path(args.options_file).resolve())]
    elif getattr(args, "options", None):
        cmd += ["--options", args.options]
    proc = subprocess.run(cmd, cwd=str(path), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not (path / "scripts" / "run-state.py").exists():
        print(f"WORKTREE-REQUIRED {path}")
        print((proc.stdout + proc.stderr).strip()[:400])
        print("worktree では run を始められませんでした。その worktree を開き（または cd して）、同じ依頼で `/build` をやり直してください。")
        return 4
    print(f"WORKTREE {path}")
    print("run は専用 worktree で始めました。以後の `python scripts/...`・git・作業役への依頼は、すべてこのパスを cwd にして行います"
          "（VS Code を別に開く必要はありません）。成功すると main へ取り込まれます。")
    print(proc.stdout.strip())
    return 0


def primary_tree(root: Path) -> Path:
    rc, out = h.git(["worktree", "list", "--porcelain"], root)
    for line in out.splitlines():
        if line.startswith("worktree "):
            return Path(line.split(" ", 1)[1].strip())
    return root


def other_active_runs(root: Path) -> int:
    """Active runs in other worktrees of this repository (they share the machine's CPU and memory)."""
    n = 0
    here = os.path.normcase(str(root.resolve()))
    rc, out = h.git(["worktree", "list", "--porcelain"], root)
    for line in out.splitlines():
        if not line.startswith("worktree "):
            continue
        p = Path(line.split(" ", 1)[1].strip())
        if os.path.normcase(str(p.resolve())) == here or not p.exists():
            continue
        try:
            cfg = h.load_config(p)
            rid = h.current_run(p, cfg)
            if rid and h.load_meta(p, cfg, rid).get("status") == "active":
                n += 1
        except Exception:
            continue
    return n


class LandLock:
    """Repository-wide lock (in the git common dir) so that only one run at a time changes the base branch."""

    def __init__(self, root: Path, wait: float, verify_timeout: int = 1800):
        self.stale = max(3600, 2 * (verify_timeout + 120) + 600)
        rc, out = h.git(["rev-parse", "--git-common-dir"], root)
        d = Path(out.strip()) if rc == 0 and out.strip() else root / ".git"
        self.path = (d if d.is_absolute() else root / d) / "ebak-land.lock"
        self.wait = wait

    def __enter__(self):
        deadline = time.time() + self.wait
        while True:
            try:
                if self.path.exists() and (h.lock_orphaned(self.path)
                                           or time.time() - self.path.stat().st_mtime > self.stale):
                    self.path.unlink()
            except OSError:
                pass
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                if time.time() >= deadline:
                    raise SystemExit("LAND-BUSY 別の run が main に取り込み中です（待ち時間切れ。もう一度 land を実行します）")
                time.sleep(2)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


def land_tmp_path(primary: Path) -> Path:
    rc, out = h.git(["rev-parse", "--git-common-dir"], primary)
    d = Path(out.strip()) if rc == 0 and out.strip() else primary / ".git"
    return (d if d.is_absolute() else primary / d) / "ebak-land-wt"


def remove_land_tmp(primary: Path, tmp: Path) -> None:
    if tmp.exists():
        h.git(["worktree", "remove", "--force", str(tmp)], primary)
    if tmp.exists():
        shutil.rmtree(str(tmp), ignore_errors=True)
    h.git(["worktree", "prune"], primary)


def _ts_of(rec) -> str:
    return str((rec or {}).get("last_run_at") or "") if isinstance(rec, dict) else ""


def _merge3(anc, ours, theirs):
    """3-way pick for one value. Returns (value, present)."""
    if ours == theirs:
        return ours, ours is not None
    if anc == ours:
        return theirs, theirs is not None
    if anc == theirs:
        return ours, ours is not None
    if ours is None:
        return theirs, True
    if theirs is None:
        return ours, True
    return (theirs, True) if _ts_of(theirs) > _ts_of(ours) else (ours, True)


def merge_ledgers(anc: dict, ours: dict, theirs: dict) -> dict:
    """Three-way merge of tests/system/ledger.json: cases by id, ac_digests by key (ours = run, theirs = base)."""
    def by_id(d):
        return {c.get("id"): c for c in (d.get("cases") or []) if isinstance(c, dict)}
    a, o, t = by_id(anc), by_id(ours), by_id(theirs)
    order = list(t) + [i for i in o if i not in t]
    cases = []
    for i in order:
        v, ok = _merge3(a.get(i), o.get(i), t.get(i))
        if ok:
            cases.append(v)
    out = dict(theirs)
    for k in set(anc) | set(ours) | set(theirs):
        if k in ("cases", "ac_digests"):
            continue
        v, ok = _merge3(anc.get(k), ours.get(k), theirs.get(k))
        if ok:
            out[k] = v
        else:
            out.pop(k, None)
    ad_a, ad_o, ad_t = (x.get("ac_digests") or {} for x in (anc, ours, theirs))
    digests = {}
    for k in list(ad_t) + [k for k in ad_o if k not in ad_t]:
        v, ok = _merge3(ad_a.get(k), ad_o.get(k), ad_t.get(k))
        if ok:
            digests[k] = v
    out["cases"] = cases
    out["ac_digests"] = digests
    return out


def sync_with_base(root: Path, cfg: dict, branch: str, base: str):
    """Merge the base branch into the run worktree; auto-resolve only tests/system/ledger.json. Returns (ok, conflicts)."""
    import json
    if h.current_branch(root) != branch:
        return False, []
    rc, dirty = h.git(["status", "--porcelain", "--untracked-files=no"], root)
    if rc != 0 or dirty.strip():
        return False, []
    rc, out = h.git(["merge", "--no-ff", "--no-edit", base], root)
    if rc == 0:
        return True, []
    rc, names = h.git(["diff", "--name-only", "--diff-filter=U"], root)
    files = [n.strip() for n in names.splitlines() if n.strip()]
    ledger = h.mf(cfg, "ledger").replace("\\", "/")
    if not files or any(f != ledger for f in files):
        h.git(["merge", "--abort"], root)
        return False, files
    def stage(n):
        rc, txt = h.git(["show", f":{n}:{ledger}"], root)
        return json.loads(txt) if rc == 0 and txt.strip() else None
    try:
        anc, ours, theirs = stage(1) or {}, stage(2), stage(3)
        if ours is None or theirs is None:
            raise ValueError("ledger side missing")
        h.save_ledger(root, cfg, merge_ledgers(anc, ours, theirs))
        h.git(["add", "--", ledger], root)
        rc, out = h.git(["commit", "--no-edit"], root)
        if rc != 0:
            raise ValueError(out)
    except Exception:
        h.git(["merge", "--abort"], root)
        return False, files
    return True, []


def landed(root: Path, branch: str, base: str) -> bool:
    rc, _ = h.git(["merge-base", "--is-ancestor", branch, base], root)
    return rc == 0


def cmd_land(args) -> int:
    """Merge this run's integration branch into the base branch in the primary tree, one run at a time."""
    root, cfg = ctx(args)
    rid = h.current_run(root, cfg)
    if not rid:
        runs = sorted(p.name for p in (h.work_dir(root, cfg) / "runs").glob("*") if (p / "meta.json").exists())
        rid = runs[-1] if runs else None
    if not rid:
        raise SystemExit("ERROR run-state: 取り込む run がありません")
    meta = h.load_meta(root, cfg, rid)
    branch = meta.get("integration_branch") or h.current_branch(root)
    base = cfg.get("base_branch", "main")
    if meta.get("status") != "finished" or meta.get("result") != "全件完了":
        print(f"LAND-SKIP {rid}: 結果が「全件完了」ではない（status={meta.get('status')} result={meta.get('result')}）ので取り込みません")
        return 1
    primary = primary_tree(root)
    if os.path.normcase(str(primary.resolve())) == os.path.normcase(str(root.resolve())):
        print("LAND-SKIP: この作業ツリーが主の作業ツリーです（run は専用 worktree で動かします）")
        return 1
    if landed(primary, branch, base):
        print(f"LANDED {rid}: すでに {base} に取り込み済みです")
        return 0
    deadline = time.time() + args.wait
    vtimeout = int(cfg["verify"].get("timeout_sec", 1800))
    with LandLock(primary, args.wait, vtimeout):
        syncs = 0
        while True:
            rc, old = h.git(["rev-parse", base], primary)
            old = old.strip()
            if rc != 0 or not old:
                print(f"ERROR run-state: {base} を解決できません: {old[:200]}")
                return 1
            tmp = land_tmp_path(primary)
            remove_land_tmp(primary, tmp)
            try:
                rc, out = h.git(["worktree", "add", "--detach", str(tmp), old], primary)
                if rc != 0:
                    print(f"ERROR run-state: 取り込み用の一時 worktree を作れません: {out.strip()[:300]}")
                    return 1
                rc, out = h.git(["merge", "--no-ff", "-m", f"Merge {branch} ({rid})", branch], tmp)
                if rc != 0:
                    h.git(["merge", "--abort"], tmp)
                    remove_land_tmp(primary, tmp)
                    if syncs < 3:
                        syncs += 1
                        ok, files = sync_with_base(root, cfg, branch, base)
                        if ok:
                            continue
                    else:
                        files = []
                    print(f"LAND-CONFLICT {rid}: {out.strip()[:300]}\n"
                          + (f"競合したファイル: {', '.join(files)}\n" if files else "")
                          + f"run の worktree で `git merge {base}` を行って競合を解消し、verify の後にもう一度 land を実行します")
                    return 2
                vrc, vout = h.run([sys.executable, str(tmp / "scripts" / "verify.py"), "--quick"], cwd=tmp,
                                  timeout=vtimeout + 120)
                if vrc != 0:
                    print(f"LAND-VERIFY-FAIL {rid}: 統合後の verify が失敗したので取り込みません\n" + "\n".join(vout.splitlines()[-12:]))
                    return 1
                rc, new = h.git(["rev-parse", "HEAD"], tmp)
                new = new.strip()
                restart = False
                while True:
                    if h.current_branch(primary) == base:
                        rc, out = h.git(["merge", "--ff-only", new], primary)
                    else:
                        rc, out = h.git(["update-ref", f"refs/heads/{base}", new, old], primary)
                        if rc != 0:
                            restart = True  # CAS failed: someone else moved the base branch
                            break
                    if rc == 0:
                        break
                    rc2, now = h.git(["rev-parse", base], primary)
                    if now.strip() != old:
                        restart = True
                        break
                    if time.time() >= deadline:
                        print(f"LAND-WAIT {rid}: 主の作業ツリーの未コミットの変更が重なっていて {base} を進められません"
                              f"（{out.strip()[:200]}）。その変更を commit か退避したあと、もう一度 `run-state.py land` を実行します")
                        return 3
                    time.sleep(5)
                if restart:
                    continue
                rc, sha = h.git(["rev-parse", "--short", new], primary)
                sha = sha.strip()
                break
            finally:
                remove_land_tmp(primary, tmp)
    meta["landed_commit"] = sha
    h.save_meta(root, cfg, rid, meta)
    print(f"LANDED {rid}: {base} @ {sha}")
    return 0


def cmd_start(args) -> int:
    root, cfg = ctx(args)
    rid = h.current_run(root, cfg)
    if rid and not args.new and (h.run_dir(root, cfg, rid) / "meta.json").exists():
        meta = h.load_meta(root, cfg, rid)
        if meta.get("status") == "active":
            print(f"RESUME {rid}")
            return cmd_status(args)
    wt_rc = require_own_worktree(root, cfg, args)
    if wt_rc is not None:
        return wt_rc
    text = ""
    if args.options_file:
        text = h.read_text(Path(args.options_file))
    elif args.options:
        text = args.options.replace("\\n", "\n")
    opts = dict(DEFAULT_OPTIONS)
    opts.update(h.parse_options_text(text))
    pw = str(opts.get("parallel_workers", "auto")).strip()
    auto_note = ""
    if pw.lower() in ("auto", "自動", ""):
        others = other_active_runs(root)
        opts["parallel_workers"] = str(max(1, h.auto_workers() // (others + 1)))
        auto_note = (f"parallel_workers: auto -> {opts['parallel_workers']}（CPU {os.cpu_count()} コア・メモリ {h.total_memory_gb():.0f} GB から算出"
                     f"{f'。同時に動いている別の run {others} 件と分け合う' if others else ''}）")
    rid = args.run_id or h.new_run_id()
    rdir = h.run_dir(root, cfg, rid)
    n = 1
    while rdir.exists():
        rid = f"{args.run_id or h.new_run_id()}-{n}"
        rdir = h.run_dir(root, cfg, rid)
        n += 1
    for sub in ("evidence", "audit", "logs"):
        (rdir / sub).mkdir(parents=True, exist_ok=True)
    branch = start_branch = h.current_branch(root)
    branch_msg = ""
    if branch in (cfg.get("base_branch", "main"), "master") and not args.no_branch:
        rc, out = h.git(["switch", "-c", f"run/{rid}"], root)
        if rc == 0:
            branch_msg = f"integration branch: run/{rid}（{branch} からの作業ブランチ）"
            branch = f"run/{rid}"
        else:
            branch_msg = f"WARN 統合ブランチを作れませんでした: {out.strip()[:200]}"
    meta = {
        "run_id": rid, "status": "active", "started_at": h.now_iso(), "finished_at": None,
        "head_at_start": h.head_commit(root), "branch_at_start": start_branch,
        "integration_branch": branch, "options": opts, "stage": 0,
        "stages_done": [], "ledger_strict": False, "session_id": None, "toolkit": h.TOOLKIT_VERSION,
        "human_interventions": [{"at": h.now_iso(), "kind": "request", "note": ""}],
    }
    h.save_meta(root, cfg, rid, meta)
    h.write_json(rdir / "queue.json", {"run_id": rid, "items": []})
    h.write_text_atomic(rdir / "progress.md", f"# progress {rid}\n\n")
    h.write_text_atomic(h.work_dir(root, cfg) / "current-run.txt", rid + "\n")
    print(f"START {rid}")
    print(f"dir: {rdir.relative_to(root).as_posix()}")
    if branch_msg:
        print(branch_msg)
    print("options: " + ", ".join(f"{k}={v}" for k, v in opts.items()))
    if auto_note:
        print(auto_note)
    models = cfg.get("models") or {}
    if not any(v for k, v in models.items() if not k.startswith("_") and isinstance(v, str)):
        print("HINT models: 全役割が空（既定のモデル）です。実測では conductor・implementer の選択が所要時間と Token を最も左右しました。"
              "較正の手順は EABK-docs/04-customization.md 4.2 を参照してください")
    return 0


def heal_integration_branch(root: Path, cfg: dict, rid: str, meta: dict) -> str:
    """The integration branch was renamed (e.g. from the GitHub Copilot app): follow the current branch."""
    old = meta.get("integration_branch") or ""
    if not old or h.ref_exists(root, f"refs/heads/{old}"):
        return ""
    cur = h.current_branch(root)
    if not cur or cur == "HEAD" or cur in (cfg.get("base_branch", "main"), "master") or cur.startswith("work/"):
        return f"WARN 統合ブランチ {old} が見つかりません。`git branch` で確認し、統合ブランチに切り替えてから続けます"
    meta["integration_branch"] = cur
    meta.setdefault("integration_branch_renamed_from", old)
    h.save_meta(root, cfg, rid, meta)
    return f"WARN 統合ブランチ {old} が見つからないため、現在のブランチ {cur} を統合ブランチとして記録し直しました"


def watch_warning(q: dict) -> str:
    """FR-1065 AC-363: read-only WATCH: line (over-limit doing items, suspicious processes). Never raises."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("watch_mod", Path(__file__).resolve().parent / "watch.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        stuck = mod.stuck_items(q, dt.datetime.now().astimezone())
    except Exception:  # noqa: BLE001
        return ""
    try:
        orphans = sum(1 for r in mod._evaluate(None) if r[1])
    except Exception:  # noqa: BLE001
        orphans = 0
    if not stuck and not orphans:
        return ""
    ids = ",".join(f"{i}({m}分)" for i, m in stuck) or "-"
    return f"WATCH: 時間超過の項目={ids} 疑わしい（孤児）プロセス={orphans}（watch.py stuck / reap）"


def cmd_status(args) -> int:
    root, cfg = ctx(args)
    rid = h.current_run(root, cfg)
    if not rid:
        print("run: なし（新しい実行として始めます: run-state.py start）")
        return 0
    meta = h.load_meta(root, cfg, rid)
    heal = heal_integration_branch(root, cfg, rid, meta) if meta.get("status") == "active" else ""
    q = h.load_queue(root, cfg, rid)
    c = counts(q)
    mh = float(meta.get("options", {}).get("max_hours", 24) or 24)
    el = elapsed_hours(meta)
    print(f"run: {rid} status={meta.get('status')} stage={meta.get('stage')}({STAGES.get(meta.get('stage'), '?')}) done={meta.get('stages_done')}")
    print(f"time: {el:.1f}h / {mh:g}h ({el / mh * 100:.0f}%)  branch={h.current_branch(root)} HEAD={h.head_commit(root)}")
    print(f"integration: {meta.get('integration_branch') or '-'}")
    print(f"lane: {meta.get('lane', '未判定')}")
    if heal:
        print(heal)
    print(f"queue: todo={c['todo']} doing={c['doing']} done={c['done']} blocked={c['blocked']}")
    watch_line = watch_warning(q)
    if watch_line:
        print(watch_line)
    for it in q.get("items", []):
        if it.get("status") in ("doing", "todo"):
            print(f"  {it['id']} {it.get('status')} req={','.join(it.get('requirement_ids', []))} deps={','.join(it.get('depends_on', [])) or '-'} attempts={it.get('attempts', 0)} branch={it.get('branch') or '-'}")
    prog = h.run_dir(root, cfg, rid) / "progress.md"
    if prog.exists():
        lines = [l for l in h.read_text(prog).splitlines() if l.strip()][-args.tail:]
        print("progress (tail):")
        for l in lines:
            print("  " + l)
    return 0


def cmd_stage(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    meta = h.load_meta(root, cfg, rid)
    n = args.n
    if n not in STAGES:
        raise SystemExit("ERROR run-state: stage は 0〜6 です")
    times = meta.setdefault("stage_times", {}).setdefault(str(n), {})
    if args.done:
        times["done"] = h.now_iso()
        if n not in meta["stages_done"]:
            meta["stages_done"].append(n)
        if n == 4:
            meta["ledger_strict"] = True
        msg = f"工程{n} {STAGES[n]} 完了"
    else:
        times.setdefault("start", h.now_iso())
        meta["stage"] = n
        if n == 1:
            meta["ledger_strict"] = False
            meta["stages_done"] = [s for s in meta["stages_done"] if s < 1]
        msg = f"工程{n} {STAGES[n]} 開始"
    h.save_meta(root, cfg, rid, meta)
    append_progress(root, cfg, rid, meta, msg)
    print(msg)
    return 0


def append_progress(root, cfg, rid, meta, text: str) -> None:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()][:3]
    if not lines:
        return
    ts = dt.datetime.now().strftime("%m-%d %H:%M")
    entry = f"- {ts} [工程{meta.get('stage', '?')}] " + lines[0][:300] + "".join("\n  " + l[:300] for l in lines[1:]) + "\n"
    p = h.run_dir(root, cfg, rid) / "progress.md"
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(entry)


def cmd_progress(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    append_progress(root, cfg, rid, h.load_meta(root, cfg, rid), args.text)
    return 0


def ids(v) -> List[str]:
    return [x for x in re.split(r"[,\s]+", v or "") if x]


def mark_status(it: dict, status: str) -> None:
    """Set the status and record the timing used by kpi.py (flow metrics)."""
    now = h.now_iso()
    if status == "doing" and it.get("status") != "doing":
        it.setdefault("first_started_at", now)
        it["started_at"] = now
    if status in ("done", "blocked", "todo") and it.get("status") == "doing" and it.get("started_at"):
        try:
            sec = (parse_ts(now) - parse_ts(it["started_at"])).total_seconds()
            it["work_sec"] = round(it.get("work_sec", 0) + max(sec, 0), 1)
        except ValueError:
            pass
    if status in ("done", "blocked"):
        it["finished_at"] = now
    it["status"] = status


def save_queue(root, cfg, rid, q) -> None:
    h.write_json(h.run_dir(root, cfg, rid) / "queue.json", q)


def cmd_queue(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    q = h.load_queue(root, cfg, rid)
    items = q.setdefault("items", [])
    by_id = {it["id"]: it for it in items}
    if args.qcmd == "add":
        if args.id in by_id:
            raise SystemExit(f"ERROR run-state: {args.id} は既にあります")
        reqs = ids(args.req)
        if not 1 <= len(reqs) <= MAX_REQS_PER_ITEM:
            raise SystemExit(f"ERROR run-state: 1 項目の要求 ID は 1〜{MAX_REQS_PER_ITEM} 個です（縦に切った機能の単位）")
        for d in ids(args.depends):
            if d not in by_id:
                raise SystemExit(f"ERROR run-state: 依存先 {d} がありません")
        n_ac = len(ids(args.ac))
        if n_ac > MAX_AC_PER_ITEM and not args.allow_large:
            raise SystemExit(f"ERROR run-state: 1 項目の AC は {MAX_AC_PER_ITEM} 個までです（{n_ac} 個）。1 項目の作業時間が長いほど 1 回目のゲート通過率が下がるため、分割します（やむを得ない場合は --allow-large）")
        items.append({
            "id": args.id, "requirement_ids": reqs, "ac_ids": ids(args.ac), "boundary": args.boundary or "",
            "shared": ids(args.shared), "depends_on": ids(args.depends), "status": "todo", "attempts": 0,
            "branch": None, "worktree": None, "summary": args.summary or "",
        })
        save_queue(root, cfg, rid, q)
        print(f"added {args.id}")
        return 0
    if args.qcmd == "set":
        it = by_id.get(args.id)
        if not it:
            raise SystemExit(f"ERROR run-state: {args.id} がありません")
        if args.status:
            if args.status not in ("todo", "doing", "done", "blocked"):
                raise SystemExit("ERROR run-state: status は todo/doing/done/blocked です")
            mark_status(it, args.status)
        if args.attempts:
            it["attempts"] = it.get("attempts", 0) + int(args.attempts[1:]) if args.attempts.startswith("+") else int(args.attempts)
        if args.branch is not None:
            it["branch"] = args.branch or None
        if args.worktree is not None:
            it["worktree"] = args.worktree or None
        if args.summary is not None:
            it["summary"] = args.summary
        save_queue(root, cfg, rid, q)
        print(f"{args.id}: status={it['status']} attempts={it.get('attempts', 0)} branch={it.get('branch') or '-'}")
        return 0
    if args.qcmd == "ready":
        doing = [it for it in items if it.get("status") == "doing"]
        busy = set()
        for it in doing:
            busy |= {it.get("boundary")} | set(it.get("shared", []))
        busy.discard("")
        out = []
        slots = max(args.parallel - len(doing), 0)
        for it in items:
            if len(out) >= slots:
                break
            if it.get("status") != "todo":
                continue
            if any(by_id.get(d, {}).get("status") != "done" for d in it.get("depends_on", [])):
                continue
            keys = ({it.get("boundary")} | set(it.get("shared", []))) - {""}
            if keys & busy:
                continue
            busy |= keys
            out.append(it)
        for it in out:
            print(f"{it['id']}\treq={','.join(it['requirement_ids'])}\tac={','.join(it.get('ac_ids', []))}\tboundary={it.get('boundary') or '-'}")
        if not out:
            print("ready: なし")
        return 0
    for it in items:
        print(f"{it['id']}\t{it.get('status')}\treq={','.join(it.get('requirement_ids', []))}\tdeps={','.join(it.get('depends_on', [])) or '-'}\tattempts={it.get('attempts', 0)}\t{it.get('summary', '')}")
    c = counts(q)
    print(f"queue: todo={c['todo']} doing={c['doing']} done={c['done']} blocked={c['blocked']}")
    return 0


def cmd_time(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    meta = h.load_meta(root, cfg, rid)
    mh = float(meta.get("options", {}).get("max_hours", 24) or 24)
    el = elapsed_hours(meta)
    pct = el / mh * 100
    print(f"elapsed={el:.2f}h max_hours={mh:g} used={pct:.0f}%{' -> 新しい項目を始めず工程 6 へ' if pct >= 85 else ''}")
    return 3 if pct >= 85 else 0


def completion(root, cfg, rid) -> List[str]:
    meta = h.load_meta(root, cfg, rid)
    q = h.load_queue(root, cfg, rid)
    c = counts(q)
    reasons = []
    if c["todo"] or c["doing"]:
        reasons.append(f"queue に todo={c['todo']} doing={c['doing']} が残っています")
    if 6 not in meta.get("stages_done", []):
        reasons.append("工程 6（最終）が終わっていません")
    if not (h.run_dir(root, cfg, rid) / "run-report.md").exists():
        reasons.append("run-report.md がありません")
    if not q.get("items") and 3 not in meta.get("stages_done", []):
        reasons.append("工程 3（計画）が終わっていません")
    return reasons


def cmd_complete_check(args) -> int:
    root, cfg = ctx(args)
    rid = h.current_run(root, cfg)
    if not rid:
        print("complete: 実行中の run はありません")
        return 0
    reasons = completion(root, cfg, rid)
    if reasons:
        print("incomplete: " + " / ".join(reasons))
        return 1
    print(f"complete: {rid}")
    return 0


LANE_MAX_CHANGED = 3
LANE_MAX_ITEMS = 2
LANE_FAST_SKIPS = ["工程2 独立監査", "reviewer", "工程6 の全量監査（3 回の多数決）→ 差分 1 回"]
LANE_BLOCKERS = {
    "security": "セキュリティ・個人情報・課金・認証の要求に触れる",
    "conflict": "既存の要求との競合（競合:）が出た",
    "shared": "共通部品・契約（API・スキーマ）・テーブルを変える",
    "unresolved": "未確定の要求・BLOCKED を含む",
    "goal_unmapped": "事業の目的（G）に対応しない、または目的そのものを変える",
}


def decide_lane(changed: int, items, flags) -> tuple:
    """Return (lane, reasons). fast only when every condition holds; any doubt means full."""
    reasons = [LANE_BLOCKERS[f] for f in LANE_BLOCKERS if f in flags]
    if changed > LANE_MAX_CHANGED:
        reasons.append(f"変えた要求が {changed} 件（上限 {LANE_MAX_CHANGED}）")
    if items is not None and items > LANE_MAX_ITEMS:
        reasons.append(f"queue が {items} 項目（上限 {LANE_MAX_ITEMS}）")
    return ("full" if reasons else "fast"), reasons


def cmd_lane(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    meta = h.load_meta(root, cfg, rid)
    if args.lcmd == "show":
        print(f"lane: {meta.get('lane', '未判定')}" + (f" ({meta.get('lane_reason')})" if meta.get("lane_reason") else ""))
        return 0
    flags = [f.strip() for f in (args.flags or "").split(",") if f.strip()]
    bad = [f for f in flags if f not in LANE_BLOCKERS]
    if bad:
        raise SystemExit(f"ERROR run-state: 不明な --flags: {','.join(bad)}（{','.join(LANE_BLOCKERS)}）")
    items = None
    if args.lcmd == "confirm":
        items = len([i for i in h.load_queue(root, cfg, rid).get("items", []) if i.get("status") != "blocked"])
        flags = sorted(set(flags) | set(meta.get("lane_flags", [])))
    lane, reasons = decide_lane(args.changed if args.changed is not None else meta.get("lane_changed", 0), items, flags)
    if args.lcmd == "confirm" and meta.get("lane") == "full":
        lane = "full"
        reasons = reasons or [meta.get("lane_reason", "")]
    if args.lcmd == "decide":
        meta["lane_changed"] = args.changed or 0
    meta["lane"], meta["lane_flags"] = lane, flags
    meta["lane_reason"] = "; ".join(r for r in reasons if r) or "全条件を満たす"
    h.save_meta(root, cfg, rid, meta)
    skipped = ", ".join(LANE_FAST_SKIPS) if lane == "fast" else "なし"
    append_progress(root, cfg, rid, meta, f"レーン: {lane}（{meta['lane_reason']}）省略: {skipped}")
    print(f"LANE: {lane}")
    print(f"reason: {meta['lane_reason']}")
    print(f"skipped: {skipped}")
    return 0


def cmd_human(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    if args.kind not in HUMAN_KINDS:
        raise SystemExit(f"ERROR run-state: human の種類は {'/'.join(HUMAN_KINDS)} です")
    meta = h.load_meta(root, cfg, rid)
    log = meta.setdefault("human_interventions", [])
    log.append({"at": h.now_iso(), "kind": args.kind, "note": (args.note or "")[:200]})
    h.save_meta(root, cfg, rid, meta)
    print(f"human: {args.kind} (計 {len(log)} 回)")
    return 0


def cmd_finish(args) -> int:
    root, cfg = ctx(args)
    rid = need_run(root, cfg)
    reasons = completion(root, cfg, rid)
    if reasons and not args.force:
        raise SystemExit("ERROR run-state: 完了条件を満たしていません: " + " / ".join(reasons))
    meta = h.load_meta(root, cfg, rid)
    q = h.load_queue(root, cfg, rid)
    done = [it for it in q.get("items", []) if it.get("status") == "done"]
    blocked = [it for it in q.get("items", []) if it.get("status") == "blocked"]
    impl = sorted({r for it in done for r in it.get("requirement_ids", [])})
    first_gate = f"{sum(1 for it in done if it.get('attempts', 0) <= 1)}/{len(done)}" if done else "-"
    doc = h.parse_requirements(root, cfg)
    ledger = h.load_ledger(root, cfg)
    sys_acs = [a.id for a in h.system_acs(doc)]
    passed = {a for c in ledger.get("cases", []) if c.get("status") == "pass" for a in c.get("ac_ids", [])}
    ac_rate = f"{sum(1 for a in sys_acs if a in passed)}/{len(sys_acs)}" if sys_acs else "-"
    el = elapsed_hours(meta)
    verified, _ = h.load_script("kpi").verified_requirements(root, cfg, impl)
    human = meta.get("human_interventions")
    human_n = str(len(human)) if isinstance(human, list) else "未記録"
    result = args.result or ("全件完了" if not blocked else "blocked あり")
    meta.update({"status": "finished", "finished_at": h.now_iso(), "result": result})
    h.save_meta(root, cfg, rid, meta)
    hist = root / h.mf(cfg, "run_history")
    text = upgrade_history(h.read_text(hist)) if hist.exists() else HISTORY_HEADER
    if re.search(rf"^\|\s*{re.escape(rid)}\s*\|", text, re.M):
        print(f"run-history: {rid} は既に記録されています")
    else:
        row = (f"| {rid} | {meta['started_at'][:16]} | {meta['finished_at'][:16]} | {h.head_commit(root)} | {result} | "
               f"{', '.join(impl) or '-'} | {len(blocked)} | {ac_rate} | {el:.1f}h | {first_gate} | {args.credits or '未取得'} | "
               f"{human_n} | {len(verified)}/{len(impl)} |")
        if not text.endswith("\n"):
            text += "\n"
        h.write_text_atomic(hist, text + row + "\n")
        print("run-history: " + row)
    cur = h.work_dir(root, cfg) / "current-run.txt"
    if cur.exists() and h.read_text(cur).strip() == rid:
        cur.unlink()
    print(f"finished {rid}: {result}")
    return 0


def main(argv=None) -> int:
    h.setup_io()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--options-file")
    s.add_argument("--options")
    s.add_argument("--new", action="store_true")
    s.add_argument("--run-id", default=None, help="run ID を指定する（専用 worktree の名前と揃える。通常は使わない）")
    s.add_argument("--no-branch", action="store_true", help="main 上でも統合ブランチを作らない")
    s.add_argument("--allow-primary", action="store_true", help="主の作業ツリーでの開始を許す（run ごとの worktree 必須を外す。通常は使わない）")
    s.add_argument("--tail", type=int, default=8)
    st = sub.add_parser("status")
    st.add_argument("--tail", type=int, default=8)
    sg = sub.add_parser("stage")
    sg.add_argument("n", type=int)
    sg.add_argument("--done", action="store_true")
    p = sub.add_parser("progress")
    p.add_argument("text")
    q = sub.add_parser("queue")
    qs = q.add_subparsers(dest="qcmd", required=True)
    qa = qs.add_parser("add")
    qa.add_argument("--id", required=True)
    qa.add_argument("--req", required=True)
    qa.add_argument("--ac", default="")
    qa.add_argument("--boundary", default="")
    qa.add_argument("--shared", default="", help="共通部品・テーブルなど、並行させない対象（カンマ区切り）")
    qa.add_argument("--depends", default="")
    qa.add_argument("--allow-large", action="store_true", help="AC が上限を超える項目を許す")
    qa.add_argument("--summary", default="")
    qset = qs.add_parser("set")
    qset.add_argument("id")
    qset.add_argument("--status")
    qset.add_argument("--attempts")
    qset.add_argument("--branch")
    qset.add_argument("--worktree")
    qset.add_argument("--summary")
    qr = qs.add_parser("ready")
    qr.add_argument("--parallel", type=int, default=5)
    qs.add_parser("show")
    sub.add_parser("time")
    sub.add_parser("complete-check")
    la = sub.add_parser("land", help="全件完了した run を、共通ロックの下で main へ取り込む")
    la.add_argument("--wait", type=float, default=1800, help="ロックと主の作業ツリーを待つ秒数")
    ln = sub.add_parser("lane")
    ls = ln.add_subparsers(dest="lcmd", required=True)
    for name in ("decide", "confirm"):
        lp = ls.add_parser(name)
        lp.add_argument("--changed", type=int, default=None, help="今回変えた要求の件数")
        lp.add_argument("--flags", default="", help="、".join(LANE_BLOCKERS) + "（カンマ区切り）")
    ls.add_parser("show")
    hu = sub.add_parser("human")
    hu.add_argument("kind", choices=HUMAN_KINDS)
    hu.add_argument("--note", default="")
    f = sub.add_parser("finish")
    f.add_argument("--result")
    f.add_argument("--credits")
    f.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    return {"start": cmd_start, "status": cmd_status, "stage": cmd_stage, "progress": cmd_progress,
            "queue": cmd_queue, "time": cmd_time,             "complete-check": cmd_complete_check, "land": cmd_land,
            "lane": cmd_lane, "human": cmd_human, "finish": cmd_finish}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
