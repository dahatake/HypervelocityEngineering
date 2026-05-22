"""hve.gui.workbench_logger — ログ行をパースしてWorkbenchState更新。

CUI版のログ出力形式を解析し、状態変更イベントを抽出する。
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional, Tuple

from .workbench_state import WorkbenchState, StepStatus, ActionLevel


# ログ行の標準形式: [HH:MM:SS] {step_id}: {level}: {message}
_LOG_PATTERN = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2})\]\s+(\S+):\s+(\w+):\s+(.*)$"
)

# Orchestrator が起動直後に stderr へ出力する run_id マーカー。
# 形式: `[hve] run_id=<id>`  (hve/orchestrator.py run_workflow 内で出力)
_RUN_ID_PATTERN = re.compile(r"\[hve\]\s+run_id=(\S+)")

# ステップ状態遷移パターン（メッセージから検出）
_STEP_RUNNING_KEYWORDS = ["開始", "started", "running", "starting", "in progress"]
_STEP_DONE_KEYWORDS = ["完了", "done", "succeeded", "success", "✓"]
_STEP_FAILED_KEYWORDS = ["失敗", "failed", "error", "✗"]
_STEP_SKIPPED_KEYWORDS = ["スキップ", "skipped", "skip"]


# Sub-agent ログ行パターン。
# hve/console.py の subagent_started/_completed/_failed が `_print(f"  {msg}")`
# 経由で出力する確定行を捕捉する。先頭には `_emit` により timestamp prefix
# `[HH:MM:SS] ` が付与され得る点に注意（オプション扱い）。
_SUBAGENT_START_PATTERN = re.compile(
    r"^(?:\[\d{2}:\d{2}:\d{2}\]\s*)?\s*▶\s+(?:\[(?P<step>[^\]]+)\]\s+)?Sub-agent:\s+(?P<name>.+?)\s*$"
)
_SUBAGENT_DONE_PATTERN = re.compile(
    r"^(?:\[\d{2}:\d{2}:\d{2}\]\s*)?\s*✅\s+(?:\[(?P<step>[^\]]+)\]\s+)?Sub-agent\s+完了:\s+(?P<name>.+?)\s*$"
)
_SUBAGENT_FAILED_PATTERN = re.compile(
    r"^(?:\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s*)?\s*❌\s+(?:\[(?P<step>[^\]]+)\]\s+)?Sub-agent\s+失敗:\s+(?P<name>.+?)(?:\s+-\s+(?P<err>.*))?\s*$"
)

# Context 使用量ログ。hve/console.py context_usage() が出力:
#   `📏 [step] Context: <current>/<limit> (<pct>%) msgs=<n>`
# 先頭の `[HH:MM:SS] ` および行頭 2 スペースインデントは任意。
_CONTEXT_USAGE_PATTERN = re.compile(
    r"^(?:\[\d{2}:\d{2}:\d{2}\]\s*)?\s*📏\s+(?:\[(?P<step>[^\]]+)\]\s+)?"
    r"Context:\s+(?P<cur>\d+)\s*/\s*(?P<lim>\d+)\s*\(\d+%?\)\s*msgs=(?P<msgs>\d+)\s*$"
)

# ツール呼び出しログ。hve/console.py tool() が出力:
#   `🔧 [step] <tool_name>(<count>)[ args]`
# tool_name は空白以外の連続文字（括弧含まず）。
_TOOL_INVOKE_PATTERN = re.compile(
    r"^(?:\[\d{2}:\d{2}:\d{2}\]\s*)?\s*🔧\s+(?:\[(?P<step>[^\]]+)\]\s+)?"
    r"(?P<name>[^\s(]+)(?:\(\d+\))?(?:\s+.*)?\s*$"
)

# Skill 読み込みログ。hve/console.py skill_invoked() が出力:
#   `📚 [step] Skill: <name>`
_SKILL_INVOKE_PATTERN = re.compile(
    r"^(?:\[\d{2}:\d{2}:\d{2}\]\s*)?\s*📚\s+(?:\[(?P<step>[^\]]+)\]\s+)?"
    r"Skill:\s+(?P<name>.+?)\s*$"
)

# 絵文字プレフィックス形式の ERROR / WARN ログ行。
# hve/console.py error() が出力: `[HH:MM:SS] ❌ ERROR: <msg>`
# hve/console.py session_error() が出力: `  ⚠️  Session error [<type>]: <msg>`
# _LOG_PATTERN（"<step>: <LEVEL>:" 形式）にマッチしないため別途処理する。
# `⚠️` は U+26A0 + U+FE0F (variation selector) と U+26A0 単独の双方を許容する。
_EMOJI_ERROR_PATTERN = re.compile(
    r"^(?:\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s*)?\s*❌\s+ERROR:\s*(?P<msg>.*?)\s*$"
)
# WARN は誤検出を抑えるため `Session error` で始まる行に限定する。
_EMOJI_SESSION_ERROR_PATTERN = re.compile(
    r"^(?:\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s*)?\s*\u26A0\uFE0F?\s+(?P<msg>Session\s+error\b.*?)\s*$"
)


def parse_subagent_event(
    line: str,
) -> Optional[Tuple[Optional[str], str, str]]:
    """Sub-agent ログ行をパースして (step_id, name, status) を返す。

    status は "running" / "done" / "failed" のいずれか。
    マッチしなければ None。

    step_id は console.subagent_* の引数が空のとき `[step_id] ` プレフィックスが
    付かないため None となり得る。
    """
    m = _SUBAGENT_START_PATTERN.match(line)
    if m:
        return (m.group("step"), m.group("name").strip(), "running")
    m = _SUBAGENT_DONE_PATTERN.match(line)
    if m:
        return (m.group("step"), m.group("name").strip(), "done")
    m = _SUBAGENT_FAILED_PATTERN.match(line)
    if m:
        return (m.group("step"), m.group("name").strip(), "failed")
    return None


def parse_log_line(line: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """ログ行をパースして (timestamp, step_id, level, message) を返す。

    Returns:
        (timestamp, step_id, level, message) のタプル、または (None, None, None, None)
    """
    match = _LOG_PATTERN.match(line)
    if not match:
        return (None, None, None, None)

    timestamp, step_id, level, message = match.groups()
    return (timestamp, step_id, level, message)


def extract_step_status_hint(message: str) -> Optional[StepStatus]:
    """メッセージからステップ状態を推論。"""
    msg_lower = message.lower()

    for keyword in _STEP_FAILED_KEYWORDS:
        if keyword in msg_lower:
            return "failed"

    for keyword in _STEP_SKIPPED_KEYWORDS:
        if keyword in msg_lower:
            return "skipped"

    for keyword in _STEP_DONE_KEYWORDS:
        if keyword in msg_lower:
            return "done"

    for keyword in _STEP_RUNNING_KEYWORDS:
        if keyword in msg_lower:
            return "running"

    return None


def classify_action_level(level_str: str) -> ActionLevel:
    """レベル文字列を ActionLevel に正規化。"""
    level_upper = level_str.upper()
    if level_upper in ("INFO", "WARN", "ERROR"):
        return level_upper  # type: ignore
    if level_upper in ("DEBUG", "TRACE"):
        return "INFO"
    if level_upper in ("WARNING",):
        return "WARN"
    return "INFO"


# 構造化統計ログ行プレフィックス（hve/console.py stats_event() が出力）。
# 形式: `[hve:stats] {"kind":"...","step":"...", ...}`
# 先頭の `[HH:MM:SS] ` および 2 スペース行頭インデントは任意。
_STATS_PREFIX_PATTERN = re.compile(
    r"^(?:\[\d{2}:\d{2}:\d{2}\]\s*)?\s*\[hve:stats\]\s*(?P<json>\{.*\})\s*$"
)


def is_stats_line(line: str) -> bool:
    """`[hve:stats] {...}` 形式の構造化統計ログ行かを判定する。

    判定のみを返し、表示抑止は呼び出し側の責務。GUI ログペインに
    出さないようフィルタする用途で使う。
    """
    return bool(_STATS_PREFIX_PATTERN.match(line))


def parse_stats_event(line: str) -> Optional[dict]:
    """`[hve:stats] {...}` ログ行をパースして payload dict を返す。

    マッチしない / JSON 解析失敗 / dict でない場合は None。副作用なし。
    GUI 側で複数の経路から同じ payload を参照したい場合に使う。
    """
    m = _STATS_PREFIX_PATTERN.match(line)
    if not m:
        return None
    try:
        payload = json.loads(m.group("json"))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _try_consume_stats_event(state: WorkbenchState, line: str) -> bool:
    """`[hve:stats] {...}` ログ行を解析し WorkbenchState に反映する。

    Returns:
        パースに成功し state を更新したら True、それ以外は False。
    """
    payload = parse_stats_event(line)
    if payload is None:
        return False

    kind = payload.get("kind") or ""
    if kind == "session_usage_detail":
        state.apply_session_usage_detail(
            system=payload.get("system"),
            tool_definitions=payload.get("tool_definitions"),
            conversation=payload.get("conversation"),
        )
        return True
    if kind == "assistant_usage":
        state.apply_assistant_usage(
            input_tokens=payload.get("input"),
            output_tokens=payload.get("output"),
            reasoning_tokens=payload.get("reasoning"),
            cache_read=payload.get("cache_read"),
            cache_write=payload.get("cache_write"),
            inter_token_latency_ms=payload.get("inter_token_latency_ms"),
            token_details=payload.get("token_details"),
        )
        if payload.get("model"):
            try:
                state.set_model(str(payload["model"]))
            except Exception:
                pass
        return True
    if kind == "assistant_ttft":
        ttft = payload.get("ttft_ms")
        if ttft is not None:
            state.apply_ttft(ttft)
        return True
    if kind == "compaction_complete":
        removed = payload.get("removed", 0) or 0
        state.apply_compaction(int(removed))
        return True
    if kind == "permission_count":
        cnt = payload.get("count", 0) or 0
        state.apply_permission_count(int(cnt))
        return True
    if kind == "premium_requests":
        cnt = payload.get("count", 0) or 0
        model = payload.get("model") or None
        try:
            state.apply_premium_requests(int(cnt), model=str(model) if model else None)
        except Exception:
            pass
        return True
    if kind == "step_status":
        # console.step_start / step_end から発火される GUI 向けステップ
        # 状態イベント。payload 例: {"step":"2.2","status":"running","title":"..."}
        sid = (payload.get("step") or payload.get("step_id") or "").strip()
        status = (payload.get("status") or "").strip()
        if sid and status in ("pending", "running", "done", "failed", "skipped"):
            try:
                state.set_step_status(sid, status)  # type: ignore[arg-type]
            except Exception:
                pass
        return True
    if kind == "tool_invoked":
        # runner から発火される GUI 用ツール集計イベント。
        # payload 例: {"step":"2.2","tool_name":"view","action_name":"view"}
        sid = (payload.get("step") or payload.get("step_id") or "").strip()
        name = (payload.get("tool_name") or "").strip()
        if name:
            state.record_tool_call(sid or None, name)
        return True
    if kind == "skill_invoked":
        # console.skill_invoked または SKILL.md パス検出フォールバックから。
        # payload 例: {"step":"2.2","name":"task-dag-planning","source":"path_detect"}
        sid = (payload.get("step") or payload.get("step_id") or "").strip()
        name = (payload.get("name") or "").strip()
        if name:
            state.record_skill_invoked(sid or None, name)
        return True
    # 未知 kind は state には反映しないが消費扱い（body には残らない方が望ましい）
    return True


def process_log_line(state: WorkbenchState, line: str) -> None:
    """ログ行を処理して WorkbenchState を更新。"""
    # 構造化統計ログ行 (`[hve:stats] {...}`) は最優先で処理し、本文ログ系の
    # ノイズパース対象から除外する。さらに state.body にも追加しない（人間可読
    # ではない機械可読 JSON 行を body に混ざらないため）。
    if _try_consume_stats_event(state, line):
        return

    state.append_body(line)

    # Context 使用量
    m_ctx = _CONTEXT_USAGE_PATTERN.match(line)
    if m_ctx:
        try:
            state.set_context(
                int(m_ctx.group("cur")),
                int(m_ctx.group("lim")),
                int(m_ctx.group("msgs")),
            )
        except (ValueError, TypeError):
            pass

    # ツール呼び出し / Skill 読み込みは 構造化 stats イベント
    # (kind=tool_invoked / skill_invoked) を唯一の集計経路とする。
    # 旧テキスト正規表現 (`🔧` / `📚`) パースは、`●` への出力変更以降
    # マッチしなくなっており、二重カウント防止のためにも本経路を採用しない。
    # ただし _TOOL_INVOKE_PATTERN / _SKILL_INVOKE_PATTERN 定義自体は他テスト互換性のため
    # 残置している。

    # run_id マーカー検出（orchestrator 起動直後に 1 度だけ出力される）。
    # 既に有効な run_id が設定済みなら上書きしない。
    if state.run_id in ("", "unknown"):
        m = _RUN_ID_PATTERN.search(line)
        if m:
            new_run_id = m.group(1).strip()
            if new_run_id:
                # update_identity 経由で run_id を反映し、Header1 などへ
                # header_updated シグナルを push する。TaskTree root の
                # title 同期も update_identity 側で実施。
                state.update_identity(run_id=new_run_id)

    timestamp, step_id, level_str, message = parse_log_line(line)
    if not (timestamp and step_id and level_str):
        # 標準形式 (`<step>: <LEVEL>:`) に該当しない場合でも、絵文字プレフィックス
        # の ERROR / WARN / Sub-agent 失敗 行は「実行中の課題」へ流したいので
        # 追加パターンで救済する。step_id は console 側で付与されないケースが
        # あり、その場合 None のまま渡す（UI 側で "[main]" に整形される）。
        now_ts = time.strftime("%H:%M:%S")
        m_err = _EMOJI_ERROR_PATTERN.match(line)
        if m_err:
            msg = (m_err.group("msg") or "").strip()
            if msg:
                state.add_user_action(
                    timestamp=m_err.group("ts") or now_ts,
                    level="ERROR",
                    message=msg,
                    step_id=None,
                )
            return
        m_warn = _EMOJI_SESSION_ERROR_PATTERN.match(line)
        if m_warn:
            msg = (m_warn.group("msg") or "").strip()
            if msg:
                state.add_user_action(
                    timestamp=m_warn.group("ts") or now_ts,
                    level="WARN",
                    message=msg,
                    step_id=None,
                )
            return
        m_subfail = _SUBAGENT_FAILED_PATTERN.match(line)
        if m_subfail:
            sub_step = m_subfail.group("step")
            sub_name = (m_subfail.group("name") or "").strip()
            sub_err = (m_subfail.group("err") or "").strip()
            sub_ts = m_subfail.group("ts") or now_ts
            detail = f"Sub-agent 失敗: {sub_name}"
            if sub_err:
                detail = f"{detail} - {sub_err}"
            state.add_user_action(
                timestamp=sub_ts,
                level="ERROR",
                message=detail,
                step_id=sub_step,
            )
        return

    level = classify_action_level(level_str)

    # ユーザーアクションを追加
    state.add_user_action(
        timestamp=timestamp,
        level=level,
        message=message,
        step_id=step_id if step_id != "[main]" else None,
    )

    # ステップ状態の推論と更新
    if step_id not in ("[main]", "main"):
        hint = extract_step_status_hint(message)
        if hint is not None:
            try:
                state.set_step_status(step_id, hint)  # type: ignore
            except Exception:
                pass


def process_subprocess_line(state: WorkbenchState, raw_line: str) -> None:
    """SubprocessReader から受け取った行を処理。

    改行を削除して process_log_line に渡す。
    """
    line = raw_line.rstrip("\r\n")
    process_log_line(state, line)
