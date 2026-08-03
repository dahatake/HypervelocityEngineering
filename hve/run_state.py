"""run_state.py — SDK セッション ID 生成ヘルパー。

ワークフロー実行の各 Step に対して決定論的な session_id を割り当てる。
Copilot SDK の `client.create_session(session_id=...)` に渡す ID と、
fork-on-retry のフォーク用 ID 再構成に使用する。

== 公開 API ==

- make_session_id(run_id, step_id, suffix="", prefix=...) -> str
- DEFAULT_SESSION_ID_PREFIX : セッション ID の既定 prefix（"hve"）
- _safe_run_id_component(run_id) -> str : run_id のパス安全正規化
"""

from __future__ import annotations

import re


def _safe_run_id_component(run_id: str) -> str:
    """run_id をパス安全な文字列に正規化する（hve/runner.py の _safe_run_id と同等規則）。

    - 許可文字: 英数字 / ハイフン / アンダースコア
    - 空文字や全削除になった場合は ValueError（呼び出し側で fallback 生成すべき）
    """
    rid = re.sub(r"[^A-Za-z0-9\-_]", "", run_id or "")
    if not rid:
        raise ValueError(f"run_id='{run_id}' はパス安全に正規化できません（空または不正文字のみ）")
    return rid


# ---------------------------------------------------------------------------
# SDK セッション ID 安定化
# ---------------------------------------------------------------------------

# session_id のデフォルト prefix。SDKConfig.session_id_prefix が空の場合に使用する。
DEFAULT_SESSION_ID_PREFIX: str = "hve"

# session_id 構成要素の最大長（SDK 側の長さ制限を想定した安全マージン）。
# Copilot SDK の session_id は OS のファイル名長制限（通常 255 byte）に
# 依存するため、prefix + run_id + step_id + suffix 合計で 200 文字以内に収める。
_SESSION_ID_MAX_RUN_ID: int = 64
_SESSION_ID_MAX_STEP_ID: int = 48
_SESSION_ID_MAX_SUFFIX: int = 32


def _safe_session_id_token(value: str, *, allow_underscore_dot: bool = True) -> str:
    """session_id の構成要素をパストラバーサル安全に正規化する。

    - 許可文字: 英数字・ハイフン
    - allow_underscore_dot=True の場合はアンダースコア・ドットも許可する
      （step_id の "1.1" のような表記を保持するため）。
    - 不正文字は "-" に置換し、連続する "-" は 1 個に圧縮する。
    """
    if not value:
        return ""
    if allow_underscore_dot:
        cleaned = re.sub(r"[^A-Za-z0-9\-_.]", "-", value)
    else:
        cleaned = re.sub(r"[^A-Za-z0-9\-]", "-", value)
    # 連続するハイフンを 1 個に圧縮し、両端のハイフン/ドットを除去
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-.")
    return cleaned


def make_session_id(
    run_id: str,
    step_id: str,
    suffix: str = "",
    *,
    prefix: str = DEFAULT_SESSION_ID_PREFIX,
) -> str:
    """SDK `client.create_session(session_id=...)` 用の決定論的 ID を生成する。

    Run 内の各 Step に対して安定した session_id を割り当てる。fork-on-retry が
    リトライ時に同一規則でフォーク用 session_id を再構成するためにも使用する。

    形式:
      `{prefix}-{run_id}-step-{step_id}[-{suffix}]`

    注意:
      Copilot SDK の sessionId バリデーションは `^[A-Za-z0-9_-]+$` のみ許可する
      （ドット `.` 不許可）。そのため step_id 中の `.` は `-` に正規化する。

    例:
      make_session_id("20260507T153012-abc123", "1.1")
        -> "hve-20260507T153012-abc123-step-1-1"
      make_session_id("20260507T153012-abc123", "1.1", suffix="qa")
        -> "hve-20260507T153012-abc123-step-1-1-qa"

    Args:
        run_id: Run 識別子（_safe_session_id_token で正規化される）。空の場合は
            "unknown" にフォールバックする（呼び出し側のクラッシュを防ぐ）。
        step_id: Step 識別子（"1.1" 等のドット表記を保持）。
        suffix: サブセッション種別（"qa" / "review" / "workiq-prefetch" 等）。
        prefix: 先頭固定文字列。デフォルト "hve"。SDKConfig.session_id_prefix が
            非空の場合は呼び出し側で上書きする。

    Returns:
        パストラバーサル安全な ASCII 文字列。長さは prefix によるが
        通常 60〜120 文字程度。
    """
    safe_prefix = _safe_session_id_token(prefix or DEFAULT_SESSION_ID_PREFIX, allow_underscore_dot=False) or DEFAULT_SESSION_ID_PREFIX
    # SDK の sessionId バリデーション `^[A-Za-z0-9_-]+$` はドット不許可のため、
    # run_id / step_id / suffix 内のドットを `-` に置換する（アンダースコアは許可）。
    safe_run = _safe_session_id_token(run_id or "").replace(".", "-")[:_SESSION_ID_MAX_RUN_ID] or "unknown"
    safe_step = _safe_session_id_token(step_id or "").replace(".", "-")[:_SESSION_ID_MAX_STEP_ID] or "unknown"
    base = f"{safe_prefix}-{safe_run}-step-{safe_step}"
    if suffix:
        safe_suffix = _safe_session_id_token(suffix, allow_underscore_dot=False)[:_SESSION_ID_MAX_SUFFIX]
        if safe_suffix:
            base = f"{base}-{safe_suffix}"
    return base
