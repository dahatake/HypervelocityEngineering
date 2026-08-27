"""FR-CLI-84: Phase 1 リクエストのサイズ計画。

Phase 1 メインタスクを Copilot SDK セッションへ送る前に、送信するプロンプトの
UTF-8 バイト数を計測し、HVE 内部のプロンプト予算と照合して Phase 1 のモデル
呼び出し回数（1 回または 0 回）を確定する。

判定と計画の実装は本モジュールに限定する（FR-MAINT-07）。呼び出し側は
`plan_phase1_request()` の戻り値だけを参照し、同等の判定を再実装しない。

自動切り詰め・自動要約・複数ターン分割・自動再試行は行わない。予算超過時は
Phase 1 のモデル呼び出しを 0 回として Step を失敗させる。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

# Copilot API はリクエスト全体（システムプロンプト・会話履歴・ツール定義を含む）に
# 上限を持つ。具体値は公開仕様として確認できていないため、本定数は HVE 側の安全余白
# であって公開仕様値ではない。実測として、Phase 1 送信が
# "The request is too large to send through CAPI Responses." で失敗した事例がある。
# CLI オプション / GUI 設定項目 / 環境変数として公開しない。
DEFAULT_PHASE1_PROMPT_BUDGET_BYTES = 4_000_000


@dataclass(frozen=True)
class Phase1RequestPlan:
    """Phase 1 送信計画。プロンプト本文は保持しない（FR-RTO-04 / NFR-SEC-01）。"""

    status: str
    prompt_utf8_bytes: int
    budget_bytes: int
    planned_phase1_requests: int
    component_bytes: Tuple[Tuple[str, int], ...] = ()

    @property
    def is_over_budget(self) -> bool:
        return self.status == "blocked"

    def describe(self) -> str:
        """予算照合結果をメタ情報だけで 1 文字列に整形する。

        プロンプト本文・`additional_prompt` 本文・事前 QA 応答本文・認証情報を
        含めてはならない（FR-RTO-04 / NFR-SEC-01）。
        """
        lines = [
            f"Phase 1 リクエストのサイズ計画: status={self.status}",
            f"  プロンプト: {self.prompt_utf8_bytes} bytes",
            f"  予算: {self.budget_bytes} bytes",
            f"  予定 Phase 1 呼び出し回数: {self.planned_phase1_requests}",
        ]
        if self.component_bytes:
            lines.append("  成分別バイト数:")
            lines.extend(f"    {name}: {size} bytes" for name, size in self.component_bytes)
        return "\n".join(lines)


def plan_phase1_request(
    prompt: str,
    *,
    budget_bytes: int = DEFAULT_PHASE1_PROMPT_BUDGET_BYTES,
    components: Optional[Iterable[Tuple[str, str]]] = None,
) -> Phase1RequestPlan:
    """プロンプトの UTF-8 バイト数を予算と照合し、Phase 1 送信計画を返す。

    Args:
        prompt: Phase 1 で送信するプロンプト全文。
        budget_bytes: HVE 内部のプロンプト予算（バイト）。
        components: 内訳表示用の (成分名, 文字列) 列。省略時は内訳を作らない。

    Returns:
        予算内なら status="ready" / planned_phase1_requests=1、
        超過なら status="blocked" / planned_phase1_requests=0。
    """
    prompt_bytes = len(prompt.encode("utf-8"))
    over_budget = prompt_bytes > budget_bytes
    component_bytes = (
        tuple((name, len(text.encode("utf-8"))) for name, text in components)
        if components is not None
        else ()
    )
    return Phase1RequestPlan(
        status="blocked" if over_budget else "ready",
        prompt_utf8_bytes=prompt_bytes,
        budget_bytes=budget_bytes,
        planned_phase1_requests=0 if over_budget else 1,
        component_bytes=component_bytes,
    )
