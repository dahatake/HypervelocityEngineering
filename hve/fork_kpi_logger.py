"""fork_kpi_logger.py — フォーク KPI ロガー（JSONL 追記）。

Fork-integration (T2.4): `DAGExecutor` がステップ完了時に KPI 3 指標
（トークン量 / 再実行率 / 所要時間）を JSONL で記録するためのロガー。

設計:
    - 1 run = 1 ファイル: `work/run/<run-id>/kpi/fork-kpi.jsonl`
    (dir 名に run-id が入るためファイル名は run_id を含めない)
  - 1 ステップ完了 = 1 行追記
  - `enabled=False` の場合は完全 no-op（フィーチャフラグ off 時の旧挙動互換）
  - I/O 失敗時は warn のみで DAG 実行を止めない
  - 機微情報（プロンプト / トークン / クレデンシャル）は**書き込まない**

スキーマは `work/fork-integration/T1.5-kpi-spec.md` を参照。
"""

from __future__ import annotations

import json
import re as _re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


# KPI ログの既定ディレクトリー名（`work_root` 相対）
KPI_DIRNAME: str = "kpi"
KPI_FILENAME: str = "fork-kpi.jsonl"


def _default_kpi_dir() -> Path:
    """起動時の ``work/run/<run-id>/kpi/`` を返す。遅延解決。"""
    try:
        from hve.split_fork import resolve_work_root
    except ImportError:  # pragma: no cover - script execution path
        from split_fork import resolve_work_root  # type: ignore[no-redef]
    return resolve_work_root() / KPI_DIRNAME


def _sanitize_run_id(run_id: str) -> str:
    """run_id をパス安全な ASCII 文字列に正規化する。

    `hve/run_state.py` の `_safe_run_id_component` と等価規則:
    英数字 / ハイフン / アンダースコアのみを残す。空になった場合は "unknown" を返す。
    """
    rid = _re.sub(r"[^A-Za-z0-9\-_]", "", run_id or "")
    return rid or "unknown"


class ForkKPILogger:
    """フォーク KPI ロガー本体。

    使い方:
        logger = ForkKPILogger(enabled=True, run_id="20260512T031415-abc123")
        logger.log_step(
            step_id="2.3",
            session_id="hve-...-step-2.3",
            forked_session_id=None,
            success=True,
            retry_count=0,
            elapsed_seconds=12.3,
            tokens=0,
            fork_on_retry_enabled=True,
        )

    enabled=False 時は全メソッドが no-op となる。
    """

    def __init__(
        self,
        enabled: bool,
        run_id: str,
        *,
        kpi_dir: Optional[Path] = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._run_id = _sanitize_run_id(run_id)
        self._kpi_dir = Path(kpi_dir) if kpi_dir is not None else _default_kpi_dir()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def log_path(self) -> Path:
        """`work/run/<run-id>/kpi/fork-kpi.jsonl` への Path。"""
        return self._kpi_dir / KPI_FILENAME

    def log_step(
        self,
        *,
        step_id: str,
        session_id: Optional[str],
        forked_session_id: Optional[str],
        success: bool,
        retry_count: int,
        elapsed_seconds: float,
        tokens: int = 0,
        fork_on_retry_enabled: bool = False,
    ) -> None:
        """1 ステップ分の KPI を JSONL に追記する。

        enabled=False の場合は何もしない（no-op）。
        I/O 失敗時は stderr に warn を出すのみで例外を再送出しない。
        """
        if not self._enabled:
            return

        record: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "run_id": self._run_id,
            "step_id": str(step_id),
            "session_id": session_id,
            "forked_session_id": forked_session_id,
            "success": bool(success),
            "retry_count": int(retry_count) if isinstance(retry_count, int) and retry_count >= 0 else 0,
            "elapsed_seconds": float(elapsed_seconds) if isinstance(elapsed_seconds, (int, float)) else 0.0,
            "tokens": int(tokens) if isinstance(tokens, int) and tokens >= 0 else 0,
            "fork_on_retry_enabled": bool(fork_on_retry_enabled),
        }

        try:
            self._kpi_dir.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(
                f"[fork_kpi_logger] WARN: KPI ログ書き込み失敗 (skip): {self.log_path} ({exc})",
                file=sys.stderr,
                flush=True,
            )
