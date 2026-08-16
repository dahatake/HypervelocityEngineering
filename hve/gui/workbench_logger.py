"""hve.gui.workbench_logger — ログ行をパースしてWorkbenchState更新。

CUI版のログ出力形式を解析し、状態変更イベントを抽出する。
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional, Tuple

from .workbench_state import (
    ActionLevel,
    StepStatus,
    WorkbenchState,
    _extract_inline_ctx,
)

try:
    from .. import runtime_observability as _rto
except ImportError:  # pragma: no cover - script 実行経路
    from hve import runtime_observability as _rto  # type: ignore[no-redef]


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
# WARN: `⚠️` で始まる任意の警告行を「実行中の課題」へ流す。
# catalog 見出し WARNING（hve/app_arch_filter.py）/ dry-run 警告 /
# Session error（hve/console.py）等を包含する。
# `⚠️` を含まない通常行は対象外。`⚠️` は U+26A0 + U+FE0F (variation
# selector) と U+26A0 単独の双方を許容する。
_EMOJI_WARN_PATTERN = re.compile(
    r"^(?:\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s*)?\s*\u26A0\uFE0F?\s+(?P<msg>.*?)\s*$"
)

# `✗ [step_id] ツール失敗: <error_msg>` 形式（hve/console.py tool_result が出力）。
# 標準 `_LOG_PATTERN`（`step: LEVEL:` 形式）にはマッチしないため別途処理する。
# step_id 抽出は省略可。
_TOOL_FAILED_PATTERN = re.compile(
    r"^(?:\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s*)?\s*\u2717\s+(?:\[(?P<step>[^\]]+)\]\s+)?\u30c4\u30fc\u30eb\u5931\u6557:\s*(?P<msg>.*?)\s*$"
)

# 敵対的レビューの重大度テーブル行だけを「実行中の課題」へ流す（NFR-OBS-06）。
# 正本の書式は hve/prompts.py の出力フォーマット:
#   `| No. | 軸 | 重大度 | 指摘箇所 | 問題の説明 | 修正案 |`
# 旧実装は自由記述への部分文字列一致（`status` / `FAIL` 等）で判定していたため、
# 標準成果物名 `work-status.md` や標準語彙 `fail-closed` に必ず一致し、
# 2026-07-26 のランでは検知 5 件が全件偽陽性だった。
# テンプレート行（`[Critical/Major/Minor]`）や区切り行は重大度セルが
# 完全一致しないため自動的に除外される。
_FINDING_PATTERN = re.compile(
    r"^(?:\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s*)?"
    r"\|\s*(?P<no>[^|]*?)\s*"
    r"\|\s*(?P<axis>[^|]*?)\s*"
    r"\|\s*(?P<severity>Critical|Major|Minor)\s*"
    r"\|\s*(?P<rest>.*)$",
    re.IGNORECASE,
)

# 重大度 → 課題レベル。Minor は任意修正のため課題ペインへ流さない
# （hve/prompts.py 「Minor は任意」）。
_FINDING_SEVERITY_LEVELS = {"critical": "ERROR", "major": "WARN"}

# 「ツール失敗」課題のメッセージ先頭に付くツール名（hve/runner.py が前置する）。
_TOOL_FAILURE_NAME_PATTERN = re.compile(r"^(?P<tool>[^\s:]+):")

# 降格済み課題に付ける接頭辞（NFR-OBS-07）。
_RECOVERED_PREFIX = "[回復済み] "


def _downgrade_recovered_tool_failures(
    state: WorkbenchState,
    step_id: str,
    tool_name: str,
) -> None:
    """同一 Step・同一ツールの「ツール失敗」課題を解決済みへ降格する。

    失敗レコード自体は削除せず、レベルを INFO に落として接頭辞を付ける。
    後続ターンで Agent が自力回復した一時失敗を、未解決 ERROR として
    残置しないための措置（NFR-OBS-07）。
    """
    for action in state.user_actions:
        if action.category != "ツール失敗" or action.level == "INFO":
            continue
        if (action.step_id or "") != (step_id or ""):
            continue
        m = _TOOL_FAILURE_NAME_PATTERN.match(action.message or "")
        if m is None or m.group("tool") != tool_name:
            continue
        action.level = "INFO"
        if not action.message.startswith(_RECOVERED_PREFIX):
            action.message = _RECOVERED_PREFIX + action.message


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


# FR-MAINT-07: 観測イベントの解析は core 実装を単一の正本とする。
parse_stats_event = _rto.parse_stats_line


def _try_consume_stats_event(state: WorkbenchState, line: str) -> bool:
    """`[hve:stats] {...}` ログ行を解析し WorkbenchState に反映する。

    Returns:
        パースに成功し state を更新したら True、それ以外は False。
    """
    payload = parse_stats_event(line)
    if payload is None:
        return False

    # FR-RTO-05: instance 単位の集計を core reducer で保持する。
    try:
        state.apply_runtime_event(payload)
    except AttributeError:
        pass

    kind = payload.get("kind") or ""
    # FR-RTO-07: Step 別集計の帰属キー。空の場合は実行中 Step へ代替帰属させない。
    step_key = (payload.get("step") or payload.get("step_id") or "").strip()
    if kind == "session_usage_detail":
        state.apply_session_usage_detail(
            system=payload.get("system"),
            tool_definitions=payload.get("tool_definitions"),
            conversation=payload.get("conversation"),
        )
        state.record_step_context(
            step_key or None, payload.get("current"), payload.get("limit")
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
    if kind == "usage_credit":
        # runner.py の assistant.usage ハンドラおよび Fleet 経路から発火される、
        # SDK 直接値の AI Credit (Nano AIU) / Multiplier cost 累積イベント (Phase A)。
        try:
            state.apply_assistant_credit(
                api_call_id=payload.get("api_call_id"),
                model=payload.get("model"),
                multiplier_cost=payload.get("multiplier_cost"),
                nano_aiu=payload.get("nano_aiu"),
                unavailable_reason=payload.get("unavailable_reason"),
                step_id=step_key or None,
            )
        except Exception:
            pass
        # Model 列の源は `usage_credit` とする。`assistant_usage` と 1 API call あたり
        # 1:1 で発火し、かつ Fleet 経路は `usage_credit` のみを発火するため。
        if payload.get("model"):
            state.record_step_model(step_key or None, str(payload["model"]))
        return True
    if kind == "quota_snapshot":
        # runner.py の assistant.usage ハンドラから発火される quota スナップショット。
        # baseline (初回観測) と latest を state 側で管理し、Workflow 実行内の
        # 増分を表示する (used_requests は quota window 全体の累積値のため)。
        qid = payload.get("quota_id")
        if qid:
            snap = {
                "used_requests": payload.get("used_requests", 0),
                "entitlement_requests": payload.get("entitlement_requests", 0),
                "remaining_percentage": payload.get("remaining_percentage", 0),
                "overage": payload.get("overage", 0),
                "is_unlimited_entitlement": payload.get(
                    "is_unlimited_entitlement", False
                ),
                "overage_allowed_with_exhausted_quota": payload.get(
                    "overage_allowed_with_exhausted_quota", False
                ),
                "usage_allowed_with_exhausted_quota": payload.get(
                    "usage_allowed_with_exhausted_quota", False
                ),
                "reset_date_iso": payload.get("reset_date_iso"),
                "model": payload.get("model"),
            }
            try:
                state.apply_quota_snapshot(str(qid), snap)
            except Exception:
                pass
        return True
    if kind == "step_status":
        # console.step_start / step_end から発火される GUI 向けステップ
        # 状態イベント。payload 例: {"step":"2.2","status":"running","title":"..."}
        sid = (payload.get("step") or payload.get("step_id") or "").strip()
        status = (payload.get("status") or "").strip()
        if sid and status in ("pending", "running", "done", "failed", "skipped", "blocked"):
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
    if kind == "tool_result":
        # NFR-OBS-07: 同一 Step・同一ツールの成功で、直前の「ツール失敗」課題を
        # 解決済み（INFO）へ降格する。失敗の事実自体は履歴として残す。
        # payload 例: {"step":"1.1","tool_name":"edit","success":true}
        if not payload.get("success"):
            return True
        sid = (payload.get("step") or payload.get("step_id") or "").strip()
        name = (payload.get("tool_name") or "").strip()
        if name:
            _downgrade_recovered_tool_failures(state, sid, name)
        return True
    if kind == "skill_invoked":        # console.skill_invoked または SKILL.md パス検出フォールバックから。
        # payload 例: {"step":"2.2","name":"task-dag-planning","source":"path_detect"}
        sid = (payload.get("step") or payload.get("step_id") or "").strip()
        name = (payload.get("name") or "").strip()
        if name:
            state.record_skill_invoked(sid or None, name)
        return True
    if kind == "assistant_usage_raw":
        # HVE_DEBUG_ASSISTANT_USAGE=1 でのみ runner.py から発火される
        # 診断専用イベント。state には反映せず、生 SDK ペイロード JSON を
        # body ログに追記して GUI ログタブで目視確認可能にする
        # (`total_nano_aiu` の実値などフィールド単位の真因切り分け用)。
        #
        # SENSITIVE_DEBUG: 生 SDK payload は system prompt / tool 入出力
        # を含む可能性があるため、スクリーンショット共有時はマスキング推奨。
        raw_json = payload.get("payload_json")
        if raw_json is not None:
            if not isinstance(raw_json, str):
                # runner 契約は string だが、将来契約変更時の安全網。
                try:
                    raw_json = json.dumps(raw_json, ensure_ascii=False, default=str)
                except Exception:
                    raw_json = str(raw_json)
            # GUI 応答性とログメモリ保護のための上限。
            _MAX_RAW_USAGE_LEN = 20000
            if len(raw_json) > _MAX_RAW_USAGE_LEN:
                raw_json = raw_json[:_MAX_RAW_USAGE_LEN] + "... [truncated]"
            sid_raw = (payload.get("step") or payload.get("step_id") or "").strip()
            prefix = (
                f"[assistant_usage_raw SENSITIVE_DEBUG step={sid_raw}] "
                if sid_raw
                else "[assistant_usage_raw SENSITIVE_DEBUG] "
            )
            try:
                state.append_body(prefix + raw_json)
            except Exception:
                pass
        return True
    if kind == "debug_env":
        # T1.5: 初回 assistant.usage 到達時に runner から 1 回発火される
        # env dump イベント。state には反映せず、env 値そのものを body に
        # 追記して GUI ログタブで「runner subprocess の中で env が
        # どう見えているか」を目視確認可能にする (P1/P2/P4 切り分け用)。
        sid_env = (payload.get("step") or payload.get("step_id") or "").strip()
        prefix = f"[debug_env step={sid_env}] " if sid_env else "[debug_env] "
        # kind / step 以外のフィールドを並べる (HVE_DEBUG_ASSISTANT_USAGE_raw 等)。
        try:
            shown = {
                k: v
                for k, v in payload.items()
                if k not in ("kind", "step", "step_id")
            }
            state.append_body(
                prefix + json.dumps(shown, ensure_ascii=False, default=str)
            )
        except Exception:
            pass
        return True
    if kind == "assistant_usage_raw_err":
        # T1.5: assistant.usage の raw stats_event 発火が失敗した場合
        # (P3: payload シリアライズエラー等) に runner から発火される。
        # state には反映せず、エラー内容を body に追記。
        sid_err = (payload.get("step") or payload.get("step_id") or "").strip()
        err_type = payload.get("err_type") or "Exception"
        err_msg = payload.get("err") or ""
        prefix = (
            f"[assistant_usage_raw_err step={sid_err}] "
            if sid_err
            else "[assistant_usage_raw_err] "
        )
        try:
            state.append_body(f"{prefix}{err_type}: {err_msg}")
        except Exception:
            pass
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

    # NFR-OBS-05 / NFR-OBS-06: 行頭の `[hve:ctx:<step_id>] ` マーカーを先に分離し、
    # 以降のパターン判定は正規化後の本文に対して行う。
    # これにより ERROR / WARN 行の step_id を復元でき、同時に Agent の地の文が
    # 行頭アンカー付きパターンをすり抜ける経路を閉じる。
    ctx_step_id, line = _extract_inline_ctx(line)

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
                    step_id=ctx_step_id,
                )
            return
        m_warn = _EMOJI_WARN_PATTERN.match(line)
        if m_warn:
            msg = (m_warn.group("msg") or "").strip()
            if msg:
                state.add_user_action(
                    timestamp=m_warn.group("ts") or now_ts,
                    level="WARN",
                    message=msg,
                    step_id=ctx_step_id,
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
                step_id=sub_step or ctx_step_id,
            )
            return
        m_tool_fail = _TOOL_FAILED_PATTERN.match(line)
        if m_tool_fail:
            msg = (m_tool_fail.group("msg") or "").strip()
            if msg:
                state.add_user_action(
                    timestamp=m_tool_fail.group("ts") or now_ts,
                    level="ERROR",
                    category="ツール失敗",
                    message=msg,
                    step_id=m_tool_fail.group("step") or ctx_step_id,
                )
            return
        m_finding = _FINDING_PATTERN.match(line)
        if m_finding:
            severity = (m_finding.group("severity") or "").strip().lower()
            level = _FINDING_SEVERITY_LEVELS.get(severity)
            if level is not None:
                # timestamp は専用フィールドへ入るため、メッセージは表行本体のみとする。
                finding_message = "| {} | {} | {} | {}".format(
                    (m_finding.group("no") or "").strip(),
                    (m_finding.group("axis") or "").strip(),
                    (m_finding.group("severity") or "").strip(),
                    (m_finding.group("rest") or "").strip(),
                )
                state.add_user_action(
                    timestamp=m_finding.group("ts") or now_ts,
                    level=level,
                    category="指摘",
                    message=finding_message,
                    step_id=ctx_step_id,
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
