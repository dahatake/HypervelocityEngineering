"""hve/run_journal.py — Phase 3 (Resume 2-layer txn): Write-Ahead Intent Journal。

`<session-state-dir>/runs/<run_id>/journal.jsonl` に append-only で書き込まれる JSON Lines 形式の
意図ログ。2 段階以上の操作（例: delete --hard、step checkpoint）は
`begin → step* → end` の 3 段階に分解して記録される。

== クラッシュ復旧の原則 ==

- `begin` と `end` で挟まれた seq 区間が未完了の場合、次回起動時に **recovery**
  対象となる（Phase 4 の `cmd_delete` 等で recovery ハンドラを実装）。
- `end` 書き込み完了時点で初めて意図が「正常完了」と認められる。
- recovery 完了後の journal は `<session-state-dir>/journal-archive/<run_id>-<ts>.jsonl` に移動して保持。

== レコードフォーマット ==

各行は 1 JSON オブジェクト:

```json
{"seq": 1, "ts": "2026-05-12T00:00:00+00:00", "kind": "delete-hard.begin",
 "target": "20260507T000000-abc123",
 "payload": {"session_ids": ["hve-sid-1", "hve-sid-2"]}}
```

== ファイルフォーマット ==

- `O_APPEND | O_CREAT` で開く
- 書き込み毎に `os.fsync()` で torn-write を防ぐ
- 10 MB 超過で rotate（`journal.YYYYMMDDTHHMMSS.jsonl.gz` に gzip 圧縮）

== 並行安全性 ==

- 同一 run_id への並行アクセスは Phase 2 の `RunLock` で排他制御される前提。
- 本モジュール自体はインスタンス単位のスレッドロックを持ち、同インスタンス内の
  並行 begin/step/end を直列化する。
"""

from __future__ import annotations

import datetime
import gzip
import json
import os
import shutil
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

JOURNAL_FILENAME: str = "journal.jsonl"
"""`<session-state-dir>/runs/<run_id>/journal.jsonl`"""

DEFAULT_ARCHIVE_DIRNAME: str = "journal-archive"
"""`<session-state-dir>/journal-archive/` — recovery 完了後の journal を保持する。"""

ROTATE_SIZE_BYTES: int = 10 * 1024 * 1024
"""10 MB 超過で rotate。"""

_ROTATE_CHECK_INTERVAL: int = 100
"""rotate サイズチェックの頻度（N レコードごと、Critical #4 修正）。"""

# Kind の標準値（Phase 4 以降で使用）
KIND_DELETE_HARD_BEGIN: str = "delete-hard.begin"
KIND_DELETE_HARD_SDK_DELETED: str = "delete-hard.sdk-deleted"
KIND_DELETE_HARD_SDK_FAILED: str = "delete-hard.sdk-failed"
KIND_DELETE_HARD_DIR_REMOVED: str = "delete-hard.dir-removed"
KIND_DELETE_HARD_END: str = "delete-hard.end"

KIND_STEP_CHECKPOINT: str = "step.checkpoint"


# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------

class JournalError(RuntimeError):
    """journal 書き込み / 読み込み失敗時に投げられる例外。"""


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _ts_for_filename() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")


# ---------------------------------------------------------------------------
# RunJournal 本体
# ---------------------------------------------------------------------------

class RunJournal:
    """append-only な意図ログ。同一 RunJournal インスタンスを介して操作する。

    使用例:
        journal = RunJournal(Path("<session-state-dir>/runs/<run_id>"))
        seq = journal.begin(kind="delete-hard", target="<run_id>", payload={"session_ids": [...]})
        # ... SDK 削除実行 ...
        journal.step(seq, kind="delete-hard.sdk-deleted", target="hve-sid-1")
        # ... ディレクトリ削除実行 ...
        journal.step(seq, kind="delete-hard.dir-removed", target="<run_id>")
        journal.end(seq)
    """

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self._path = self.run_dir / JOURNAL_FILENAME
        self._lock = threading.Lock()
        self._next_seq_cache: Optional[int] = None

    @property
    def path(self) -> Path:
        return self._path

    # ----------------------------------------------------------------- API

    def begin(self, *, kind: str, target: str = "", payload: Optional[Dict[str, Any]] = None) -> int:
        """新規 begin レコードを追記し、seq を返す。

        Args:
            kind: 意図種別。`.begin` サフィックスはここでは付与しない（呼び出し側で
                `delete-hard` 等の base name を渡す。`end` で同じ kind を渡す）。
            target: 対象 ID。
            payload: 任意パラメータ。

        Returns:
            この意図に割り当てられた seq（単調増加）。
        """
        with self._lock:
            seq = self._next_seq()
            rec = {
                "seq": seq,
                "ts": _utc_now_iso(),
                "kind": f"{kind}.begin",
                "target": target,
                "payload": payload or {},
            }
            self._append_record(rec)
            return seq

    def step(self, seq: int, *, kind: str, target: str = "", payload: Optional[Dict[str, Any]] = None) -> None:
        """begin と end の間の進捗レコードを追記する。"""
        if seq <= 0:
            raise ValueError(f"seq は正の整数が必要: {seq}")
        with self._lock:
            rec = {
                "seq": seq,
                "ts": _utc_now_iso(),
                "kind": kind,
                "target": target,
                "payload": payload or {},
            }
            self._append_record(rec)

    def record_event(self, *, kind: str, target: str = "",
                     payload: Optional[Dict[str, Any]] = None) -> int:
        """単発イベントを 1 レコードで記録する（Major #11: checkpoint 用）。

        `begin + end` のペアではなく単一レコードで完結するイベント（例:
        `step.checkpoint`）の記録に使う。記録した seq を返す。

        `pending_intents()` 判定では `.begin` / `.end` 接尾辞のみを見るため、
        本 API で記録された単発イベントは pending 扱いされない。
        """
        with self._lock:
            seq = self._next_seq()
            rec = {
                "seq": seq,
                "ts": _utc_now_iso(),
                "kind": kind,
                "target": target,
                "payload": payload or {},
            }
            self._append_record(rec)
            return seq

    def end(self, seq: int, *, kind: str = "", target: str = "", payload: Optional[Dict[str, Any]] = None) -> None:
        """begin に対応する end レコードを追記して意図を完了させる。

        `kind` が空なら、対応する begin レコードの kind から自動推定する（`.begin` → `.end`）。
        """
        if seq <= 0:
            raise ValueError(f"seq は正の整数が必要: {seq}")
        with self._lock:
            inferred_kind = kind
            if not inferred_kind:
                # begin レコードを探して kind を取得
                for rec in self._read_records():
                    if int(rec.get("seq", -1)) == seq and rec.get("kind", "").endswith(".begin"):
                        inferred_kind = rec["kind"].replace(".begin", ".end")
                        break
                if not inferred_kind:
                    raise JournalError(f"seq={seq} の begin レコードが見つかりません")
            rec = {
                "seq": seq,
                "ts": _utc_now_iso(),
                "kind": inferred_kind,
                "target": target,
                "payload": payload or {},
            }
            self._append_record(rec)

    def pending_intents(self) -> List[Dict[str, Any]]:
        """begin はあるが end がない seq のリストを返す（最新 begin レコード相当）。

        各要素は begin レコード（後続の step レコードは含まない）。
        recovery 用に使う。
        """
        begins: Dict[int, Dict[str, Any]] = {}
        ends: set[int] = set()
        for rec in self._read_records():
            k = rec.get("kind", "")
            seq = int(rec.get("seq", -1))
            if seq < 0:
                continue
            if k.endswith(".begin"):
                begins[seq] = rec
            elif k.endswith(".end"):
                ends.add(seq)
        return [begins[s] for s in sorted(begins) if s not in ends]

    def read_all(self) -> List[Dict[str, Any]]:
        """journal の全レコードを順序通りに返す。"""
        return list(self._read_records())

    def records_for(self, seq: int) -> List[Dict[str, Any]]:
        """特定 seq に紐づく全レコード（begin / step / end）を時系列順に返す。"""
        return [r for r in self._read_records() if int(r.get("seq", -1)) == seq]

    def archive(self, archive_dir: Path) -> Optional[Path]:
        """現在の journal ファイルを archive_dir 配下へ移動する。

        Returns:
            移動先のパス。journal が存在しなければ None。
        """
        if not self._path.exists():
            return None
        archive_dir = Path(archive_dir)
        archive_dir.mkdir(parents=True, exist_ok=True)
        # run_id をディレクトリ名から推定
        run_id = self.run_dir.name
        archive_name = f"{run_id}-{_ts_for_filename()}.jsonl"
        archive_path = archive_dir / archive_name
        with self._lock:
            try:
                shutil.move(str(self._path), str(archive_path))
            except OSError as exc:
                raise JournalError(f"journal archive 失敗: {exc}") from exc
            self._next_seq_cache = None
        return archive_path

    def rotate_if_needed(self) -> Optional[Path]:
        """ファイルサイズが ROTATE_SIZE_BYTES を超えていれば gzip 圧縮して退避する。

        Returns:
            退避先パス。rotate 不要なら None。
        """
        if not self._path.exists():
            return None
        try:
            size = self._path.stat().st_size
        except OSError:
            return None
        if size < ROTATE_SIZE_BYTES:
            return None
        with self._lock:
            rotated_path = self.run_dir / f"journal.{_ts_for_filename()}.jsonl.gz"
            try:
                with self._path.open("rb") as src, gzip.open(rotated_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                self._path.unlink()
            except OSError as exc:
                raise JournalError(f"journal rotate 失敗: {exc}") from exc
            self._next_seq_cache = None
        return rotated_path

    # ----------------------------------------------------------- 内部実装

    def _append_record(self, rec: Dict[str, Any]) -> None:
        """1 レコードを append + fsync で書き込む。

        Critical #4 (v1.0.2): 一定間隔（既定 100 レコードごと）で
        `rotate_if_needed` を呼び、サイズ超過時に gzip rotate する。毎回呼ぶと
        stat の負荷が嵩むためサンプリング。
        """
        self.run_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            fd = os.open(str(self._path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(fd, payload.encode("utf-8"))
                try:
                    os.fsync(fd)
                except OSError:
                    pass
            finally:
                os.close(fd)
        except OSError as exc:
            raise JournalError(f"journal append 失敗: {exc}") from exc

        # rotate 判定（write 後の seq が _ROTATE_CHECK_INTERVAL の倍数のときのみ stat）
        # ロックは握ったまま呼ぶ前提だが、_append_record 自体は _lock 下で呼ばれる
        try:
            current_seq = self._next_seq_cache or 0
            if current_seq and current_seq % _ROTATE_CHECK_INTERVAL == 0:
                # 内部メソッド呼び出し（ロック取得済みなので _rotate_unlocked を使う）
                self._rotate_unlocked()
        except Exception:  # pragma: no cover - rotate 失敗は append を阻害しない
            pass

    def _rotate_unlocked(self) -> Optional[Path]:
        """rotate_if_needed の lock 取得なし版（内部呼び出し用）。"""
        if not self._path.exists():
            return None
        try:
            size = self._path.stat().st_size
        except OSError:
            return None
        if size < ROTATE_SIZE_BYTES:
            return None
        rotated_path = self.run_dir / f"journal.{_ts_for_filename()}.jsonl.gz"
        try:
            with self._path.open("rb") as src, gzip.open(rotated_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            self._path.unlink()
        except OSError as exc:
            raise JournalError(f"journal rotate 失敗: {exc}") from exc
        self._next_seq_cache = None
        return rotated_path

    def _read_records(self) -> Iterator[Dict[str, Any]]:
        """ファイル全体を読み込んで各レコードを yield する。

        破損行（無効 JSON）は警告なしでスキップする。
        """
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return

    def _next_seq(self) -> int:
        """次に使う seq 番号を返す（既存最大 + 1）。"""
        if self._next_seq_cache is not None:
            self._next_seq_cache += 1
            return self._next_seq_cache
        max_seq = 0
        for rec in self._read_records():
            try:
                s = int(rec.get("seq", 0))
                if s > max_seq:
                    max_seq = s
            except (TypeError, ValueError):
                continue
        self._next_seq_cache = max_seq + 1
        return self._next_seq_cache


# ---------------------------------------------------------------------------
# Archive ディレクトリの探索（recovery 用）
# ---------------------------------------------------------------------------

def scan_archive_for_pending(archive_dir: Path) -> List[Path]:
    """`<session-state-dir>/journal-archive/` から、`end` レコードが書かれていない archive を探す。

    通常 `archive()` は end 書き込み後に呼ばれるため、archive 内に pending が
    あることは異常状態（recovery 対象）を示す。

    Returns:
        pending intent を含む archive ファイルパスのリスト。
    """
    archive_dir = Path(archive_dir)
    if not archive_dir.exists():
        return []
    result: List[Path] = []
    for f in sorted(archive_dir.iterdir()):
        if not f.is_file() or not f.name.endswith(".jsonl"):
            continue
        begins: set[int] = set()
        ends: set[int] = set()
        try:
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    k = rec.get("kind", "")
                    seq = rec.get("seq", -1)
                    try:
                        seq = int(seq)
                    except (TypeError, ValueError):
                        continue
                    if k.endswith(".begin"):
                        begins.add(seq)
                    elif k.endswith(".end"):
                        ends.add(seq)
        except OSError:
            continue
        if begins - ends:
            result.append(f)
    return result


__all__ = [
    "JournalError",
    "JOURNAL_FILENAME",
    "DEFAULT_ARCHIVE_DIRNAME",
    "ROTATE_SIZE_BYTES",
    "KIND_DELETE_HARD_BEGIN",
    "KIND_DELETE_HARD_SDK_DELETED",
    "KIND_DELETE_HARD_SDK_FAILED",
    "KIND_DELETE_HARD_DIR_REMOVED",
    "KIND_DELETE_HARD_END",
    "KIND_STEP_CHECKPOINT",
    "RunJournal",
    "scan_archive_for_pending",
]
