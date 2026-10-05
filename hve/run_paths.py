"""hve/run_paths.py — run-id / work root の解決と完了報告の検証マーカー判定。

SDK にも prompt loader にも依存しない純粋関数群。`.github/scripts/check_validation_marker.py`
が本ファイルを単独ファイルとしてロードするため、パッケージ内 import を持たない。

== 公開 API ==

- `resolve_run_id()` — `work/run/<run-id>/` の ``<run-id>`` を解決
- `resolve_work_root()` — `work/run/<run-id>/` の絶対 Path を解決
- `has_validation_marker(text)` — 完了報告の検証マーカー判定（FR-MAINT-06 の単一実装）
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional


WORK_DIRNAME = "work"
WORK_RUN_DIRNAME = "run"

# プロセス内で 1 度だけ採番した run-id をキャッシュする。
# env / Cloud 検出が無いときに `resolve_run_id()` を複数回呼んでも
# 同じ ID を返すことを保証する。
_RESOLVED_RUN_ID: Optional[str] = None


def _detect_cloud_run_id() -> Optional[str]:
    """GitHub Issue 起動時に ``"issue-<N>"`` を返す。それ以外は None。

    検出順:
      1. 環境変数 ``GITHUB_ISSUE_NUMBER``
      2. ``GITHUB_EVENT_PATH`` JSON 内の ``issue.number``
    """
    issue_num = os.environ.get("GITHUB_ISSUE_NUMBER", "").strip()
    if issue_num.isdigit():
        return f"issue-{issue_num}"
    event_path = os.environ.get("GITHUB_EVENT_PATH", "").strip()
    if event_path and os.path.isfile(event_path):
        try:
            import json
            with open(event_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            issue = data.get("issue") or {}
            num = issue.get("number")
            if isinstance(num, int) and num > 0:
                return f"issue-{num}"
        except (OSError, ValueError, TypeError):
            return None
    return None


def resolve_run_id() -> str:
    """`work/run/<run-id>/` の ``<run-id>`` を解決する。

    解決順序（先勝ち）:
      1. 環境変数 ``HVE_RUN_ID``（明示指定）
      2. GitHub Issue 起動検出 → ``"issue-<N>"``
      3. ``generate_run_id()`` で新規採番（プロセス内キャッシュ）

    プロセス内では 1 度だけ採番し、以降は同じ ID を返す。
    """
    global _RESOLVED_RUN_ID
    env_id = os.environ.get("HVE_RUN_ID", "").strip()
    if env_id:
        return env_id
    cloud_id = _detect_cloud_run_id()
    if cloud_id:
        return cloud_id
    if _RESOLVED_RUN_ID is None:
        try:
            from hve.config import generate_run_id
        except ImportError:  # pragma: no cover - script execution path
            from config import generate_run_id  # type: ignore[import-not-found,no-redef]
        _RESOLVED_RUN_ID = generate_run_id()
    return _RESOLVED_RUN_ID


def _reset_run_id_cache() -> None:
    """テスト専用: ``_RESOLVED_RUN_ID`` キャッシュをクリアする。"""
    global _RESOLVED_RUN_ID
    _RESOLVED_RUN_ID = None


def resolve_work_root() -> Path:
    """`work/run/<run-id>/` ディレクトリの絶対 Path を返す。

    解決順序（先勝ち）:
      1. 環境変数 ``HVE_WORK_ROOT`` が設定されていればその値
         （GUI/CLI 起動時に親プロセスが設定した値を子プロセスが継承、
          テストでの override 用途も兼ねる）
      2. ``<repo_root>/work/run/<run-id>/``
         （``<repo_root>`` = ``Path(__file__).resolve().parents[1]``、
          ``<run-id>`` は ``resolve_run_id()`` の結果）

    cwd 依存を排除するための関数。存在しないディレクトリでも Path は返す
    （呼び出し側で `is_dir()` を判定すること）。
    """
    override = os.environ.get("HVE_WORK_ROOT")
    if override:
        return Path(override).resolve()
    return (
        Path(__file__).resolve().parents[1]
        / WORK_DIRNAME
        / WORK_RUN_DIRNAME
        / resolve_run_id()
    ).resolve()


# ---------------------------------------------------------------------------
# 検証マーカー
# ---------------------------------------------------------------------------

_VALIDATION_MARKER_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"<!--\s*validation-confirmed\s*-->", re.IGNORECASE),
    re.compile(r"^#+\s*(検証|検証結果|Validation)\b", re.MULTILINE),
    re.compile(r"^\s*[-*]\s*\*?\*?(検証|Validation)\*?\*?\s*[:：]", re.MULTILINE),
]


def has_validation_marker(text: str, *, html_comment_only: bool = False) -> bool:
    """完了報告の検証マーカー判定の単一実装（FR-MAINT-06）。

    Args:
        text: 検査対象の本文。
        html_comment_only: True のとき HTML コメント形式だけを受理する。
            TDD レポートは template が `<!-- validation-confirmed -->` を出力するため
            厳格化し、PR body / completion-report は 3 形式を許容する。
    """
    patterns = _VALIDATION_MARKER_PATTERNS[:1] if html_comment_only else _VALIDATION_MARKER_PATTERNS
    return any(pattern.search(text) for pattern in patterns)
