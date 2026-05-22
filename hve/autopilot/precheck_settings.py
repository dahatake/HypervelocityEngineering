"""hve.autopilot.precheck_settings — 認証・workflow-specific 設定の必須判定。

Qt 非依存。GUI 側で構築済みの providers リスト・settings dict・auth_states を
受け取り、必須プロバイダのうち未認証のものを ``PrecheckItem`` 列として返す。

Workflow-specific 設定（例: ARD の target_business が CLI 引数として必須等）の
拡張点もここに集約する。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from .precheck_model import PrecheckCategory, PrecheckItem


# Workflow ごとに「Autopilot 実行で必須」な workflow-specific 設定キー。
# 現状は空。将来追加時はここに宣言する。
_REQUIRED_SETTING_KEYS: Dict[str, List[str]] = {}


def collect_missing_auth(
    providers: Iterable[Any],
    settings: Mapping[str, Any],
    auth_states: Mapping[str, Any],
    *,
    authenticated_marker: Any,
) -> List[PrecheckItem]:
    """必須認証プロバイダのうち未認証のものを返す。

    Args:
        providers: ``provider.id``/``display_name``/``is_required`` を持つプロバイダ列。
        settings: 現在の設定 dict。``provider.is_required(settings)`` の引数。
        auth_states: ``provider.id`` → ``AuthState`` のマッピング。
        authenticated_marker: ``AuthState.AUTHENTICATED`` と等価な比較値。
            （Qt 非依存にするため呼び出し側から注入）

    Returns:
        未認証 ``PrecheckItem`` リスト。
    """
    from hve.gui.auth_providers import provider_is_required  # local import (Qt なし)

    items: List[PrecheckItem] = []
    for p in providers:
        try:
            if not provider_is_required(p, dict(settings)):
                continue
        except Exception:
            continue
        state = auth_states.get(getattr(p, "id", None))
        if state is authenticated_marker:
            continue
        items.append(
            PrecheckItem(
                category=PrecheckCategory.AUTH,
                workflow_id="",
                step_id=None,
                field_name=getattr(p, "id", "") or "",
                description=(
                    f"必須プロバイダ '{getattr(p, 'display_name', '')}' の認証が完了していません。"
                ),
                remediation_hint=(
                    "メイン画面の [PluginやMCP Serverへの認証] から認証を完了してください。"
                ),
            )
        )
    return items


def collect_missing_workflow_settings(
    workflow_ids: Iterable[str],
    settings_by_workflow: Mapping[str, Mapping[str, Any]],
) -> List[PrecheckItem]:
    """Workflow-specific 必須設定が空のものを返す（現状は空集合を返す拡張点）。"""
    items: List[PrecheckItem] = []
    for wf_id in workflow_ids:
        keys = _REQUIRED_SETTING_KEYS.get(wf_id, [])
        if not keys:
            continue
        values = settings_by_workflow.get(wf_id, {})
        for key in keys:
            value = values.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                items.append(
                    PrecheckItem(
                        category=PrecheckCategory.SETTING,
                        workflow_id=wf_id,
                        step_id=None,
                        field_name=key,
                        description=(
                            f"Workflow '{wf_id}' の必須設定 '{key}' が未設定です。"
                        ),
                        remediation_hint=(
                            f"Step 1 の Autopilot 統合入力パネルで '{key}' を設定してください。"
                        ),
                    )
                )
    return items


__all__ = [
    "collect_missing_auth",
    "collect_missing_workflow_settings",
]
