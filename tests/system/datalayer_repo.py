"""Disposable target repositories for the data-layer check/repair System Tests
(FR-1045 AC-237/AC-238, FR-1046 AC-240/AC-241).

Test-oracle helper only.  The repositories are built with the toolkit's public commands
(tools/install.py, scripts/next-id.py, scripts/ledger.py) and checked clean with
`python scripts/verify.py --docs-only` before an inconsistency is planted.  Nothing here
reads or imports the repair implementation.

Inconsistencies planted (chosen from AC-237 and from the documented MANUAL kinds):
  automatic  (AC-237 の例): カタログの決定状態のずれ          docs/catalog.md   FR-001 の決定状態
                            ID 台帳の状態のずれ              docs/id-registry.md FR-002 の状態
                            System Test の台帳の欠けた項目    tests/system/ledger.json の case から "evidence" を除く
  manual                  : 実行履歴の同じ run-id の内容の違う 2 行（どちらが正しいかは人が決める）
                            docs/run-history.md

Interface assumed (requirements definition FR-1046 / FR-1045 [ASSUMPTION]):
  check only : python scripts/rdfix.py --full
  apply      : python scripts/rdfix.py --full --apply
  exit codes : 0 = pass / repaired, 1 = manual left / plan exists / not converged, 2 = not run / cancelled
  installer  : tools/install.py [--no-repair] [--skip-verify]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, Tuple

SOURCE = Path(__file__).resolve().parents[2]
SEP = "\u3000"

RD = "docs/requirements-definition.md"
INTEGRATIONS = "docs/integrations.md"
CATALOG = "docs/catalog.md"
REGISTRY = "docs/id-registry.md"
HISTORY = "docs/run-history.md"
LEDGER = "tests/system/ledger.json"
PROTECTED = (RD, INTEGRATIONS)
ROLES = ("rd-author", "test-designer", "implementer", "conductor")
CHECK = ["scripts/rdfix.py", "--full"]
APPLY = ["scripts/rdfix.py", "--full", "--apply"]


def run(args: Iterable, cwd: Path, check: bool = False, env: dict | None = None, timeout: int = 600):
    e = dict(os.environ, PYTHONUTF8="1", EABK_ALLOW_PRIMARY="1")
    e.update(env or {})
    r = subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, timeout=timeout)
    if check and r.returncode:
        raise AssertionError(f"{' '.join(map(str, args))} exited {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}")
    return r


def py(root: Path, *args, **kw):
    return run([sys.executable, *args], root, **kw)


def git_init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q", "-b", "main"], root, check=True)
    run(["git", "config", "user.email", "system-test@example.invalid"], root, check=True)
    run(["git", "config", "user.name", "EABK System Test"], root, check=True)
    run(["git", "config", "commit.gpgsign", "false"], root, check=True)
    (root / "README.md").write_text("disposable repository\n", encoding="utf-8")
    commit(root, "initial")


def commit(root: Path, msg: str) -> None:
    run(["git", "add", "-A"], root, check=True)
    run(["git", "commit", "-q", "--allow-empty", "-m", msg], root, check=True)


def install(root: Path, *extra: str, check: bool = True):
    return run([sys.executable, SOURCE / "tools" / "install.py", "--target", root, *extra], root, check=check)


def _req(rid: str, ac: str, title: str) -> str:
    return "\n".join([
        f"#### {rid} {title}",
        f"- 要求: 利用者は{title}を行える。",
        f"- 決定状態: 承認済み（依頼 2026-10-16）{SEP}出自: 依頼原文{SEP}優先度: MUST（テスト用の合成データ）",
        f"- 上位: G-001{SEP}出典: 依頼原文",
        f"- 対象エンティティ: なし{SEP}関係する状態: なし{SEP}参照パラメータ: なし",
        "- 関連する既存資産: なし",
        f"- 受入基準 {ac}: {title}を行った利用者に、完了したことが表示される。",
        "  - 検証レベル: system",
        "",
    ])


def write_clean_data_layer(root: Path) -> None:
    """In an installed repository: 2 approved requirements, catalog rows, ledger cases, digests."""
    out = py(root, "scripts/next-id.py", "G", check=True).stdout
    assert "G-001" in out, f"next-id の出力から ID を読めない: {out}"
    out = py(root, "scripts/next-id.py", "FR", "--count", "2", check=True).stdout
    frs = re.findall(r"FR-\d+", out)[:2]
    out = py(root, "scripts/next-id.py", "AC", "--count", "2", check=True).stdout
    acs = re.findall(r"AC-\d+", out)[:2]
    assert len(frs) == 2 and len(acs) == 2, f"next-id の出力から ID を読めない: {out}"
    assert frs == ["FR-001", "FR-002"] and acs == ["AC-001", "AC-002"], (frs, acs)
    rd = root / RD
    text = rd.read_text(encoding="utf-8")
    body = _req("FR-001", "AC-001", "注文の登録") + "\n" + _req("FR-002", "AC-002", "注文の照会") + "\n"
    text = text.replace("### 6.1 機能要求\n", "### 6.1 機能要求\n\n" + body, 1)
    goal_hdr = "| ID | 目的 | 成功指標 | 測定方法 |\n|---|---|---|---|\n"
    assert goal_hdr in text
    text = text.replace(goal_hdr, goal_hdr + "| G-001 | 注文の受付を早くする | 受付の所要時間 | 画面の記録 |\n", 1)
    rd.write_text(text, encoding="utf-8", newline="\n")
    cat = root / CATALOG
    ct = cat.read_text(encoding="utf-8")
    hdr = "| 要求 ID | 題名 | 決定状態 | 実装ファイル | テスト | 使っている共通部品 |\n|---|---|---|---|---|---|\n"
    rows = ("| FR-001 | 注文の登録 | 承認済み | 未実装 | 未実装 | なし |\n"
            "| FR-002 | 注文の照会 | 承認済み | 未実装 | 未実装 | なし |\n")
    assert hdr in ct
    cat.write_text(ct.replace(hdr, hdr + rows, 1), encoding="utf-8", newline="\n")
    for rid, ac in (("FR-001", "AC-001"), ("FR-002", "AC-002")):
        py(root, "scripts/ledger.py", "--by", "test-designer", "add", "--req", rid, "--ac", ac,
           "--title", f"{ac} の合成ケース", "--layer", "data", "--command", "python -c pass", check=True)
    py(root, "scripts/ledger.py", "--by", "test-designer", "digests", "--update", check=True)
    py(root, "scripts/next-id.py", "--sync", check=True)  # 採番済み -> 使用中
    hist = root / HISTORY
    hist.write_text(hist.read_text(encoding="utf-8").rstrip("\n") + "\n"
                    "| 202610010000 | 2026-10-01 00:00 | 2026-10-01 01:00 | abc1234 | 完了 | FR-001 | なし | 100% | 60 分 | 100% | 0 | 0 | FR-001 |\n",
                    encoding="utf-8", newline="\n")


def make_clean_installed(root: Path) -> Path:
    """Installed EABK + clean data layer, committed.  Precondition: verify --docs-only passes."""
    git_init(root)
    install(root, "--skip-verify")
    commit(root, "install EABK")
    write_clean_data_layer(root)
    commit(root, "clean data layer")
    v = py(root, "scripts/verify.py", "--docs-only")
    assert v.returncode == 0, f"前提: 合成したデータ層が verify --docs-only に合格しない（テストの誤り）\n{v.stdout}\n{v.stderr}"
    return root


DATA_FILES = (RD, INTEGRATIONS, CATALOG, REGISTRY, HISTORY, LEDGER)


def make_clean_uninstalled(root: Path, scratch: Path) -> Path:
    """A plain git repository that already holds a clean EABK data layer, without the toolkit (new install)."""
    make_clean_installed(scratch)
    git_init(root)
    for rel in DATA_FILES:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(scratch / rel, dst)
    commit(root, "data layer without toolkit")
    return root


# ---------------------------------------------------------------------------------------- planting
def _sub_line(path: Path, pattern: str, repl: str) -> None:
    data = path.read_bytes().decode("utf-8")
    new, n = re.subn(pattern, repl, data, count=1, flags=re.M)
    assert n == 1, f"{path} に {pattern} がない（テストの誤り）"
    path.write_bytes(new.encode("utf-8"))


def plant_automatic(root: Path) -> None:
    # カタログの決定状態のずれ
    _sub_line(root / CATALOG, r"^(\| FR-001 \| 注文の登録 \| )承認済み( \|)", r"\1承認待ち\2")
    # ID 台帳の状態のずれ
    _sub_line(root / REGISTRY, r"^(\| FR-002 \|[^|\n]*\| )使用中( \|)", r"\1採番済み\2")
    # System Test の台帳の欠けた項目
    led = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    assert "evidence" in led["cases"][0]
    del led["cases"][0]["evidence"]
    (root / LEDGER).write_text(json.dumps(led, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def plant_manual(root: Path) -> None:
    hist = root / HISTORY
    hist.write_text(hist.read_text(encoding="utf-8").rstrip("\n") + "\n"
                    "| 202610010000 | 2026-10-01 00:00 | 2026-10-01 02:00 | def5678 | 中断 | FR-002 | なし | 50% | 120 分 | 50% | 0 | 1 | なし |\n",
                    encoding="utf-8", newline="\n")


def automatic_repaired(root: Path) -> Dict[str, bool]:
    led = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    return {
        "catalog": bool(re.search(r"^\| FR-001 \| 注文の登録 \| 承認済み \|", (root / CATALOG).read_text(encoding="utf-8"), re.M)),
        "registry": bool(re.search(r"^\| FR-002 \|[^|\n]*\| 使用中 \|", (root / REGISTRY).read_text(encoding="utf-8"), re.M)),
        "ledger": "evidence" in led["cases"][0],
    }


# ---------------------------------------------------------------------------------------- observation
def data_layer_files(root: Path) -> list[Path]:
    out = [p for p in (root / "docs").rglob("*") if p.is_file()] if (root / "docs").exists() else []
    if (root / LEDGER).exists():
        out.append(root / LEDGER)
    return sorted(out)


def snapshot(root: Path) -> Dict[str, Tuple[bytes, int]]:
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) for p in data_layer_files(root)}


def bytes_of(root: Path, rels: Iterable[str]) -> Dict[str, bytes]:
    return {r: (root / r).read_bytes() for r in rels if (root / r).exists()}


def no_traceback(r) -> bool:
    return "Traceback (most recent call last)" not in (r.stdout + r.stderr)


def fix_lines(text: str) -> list[str]:
    return [l for l in text.splitlines() if re.match(r"^\s*FIX\b", l)]


def manual_lines(text: str) -> list[str]:
    return [l for l in text.splitlines() if re.match(r"^\s*MANUAL\b", l)]


def make_unwritable(path: Path) -> callable:
    """Make writing `path` fail from outside the process; returns the undo function.

    Windows: the read-only attribute makes both in-place writes and os.replace onto it fail.
    POSIX:   a read-only parent directory makes creating temp files and renaming into it fail.
    """
    if os.name == "nt":
        mode = path.stat().st_mode
        os.chmod(path, stat.S_IREAD)
        return lambda: os.chmod(path, mode | stat.S_IWRITE)
    d = path.parent
    mode = d.stat().st_mode
    fmode = path.stat().st_mode
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)

    def undo():
        os.chmod(d, mode)
        os.chmod(path, fmode)
    return undo
