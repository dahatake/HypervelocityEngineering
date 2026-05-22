"""hve.gui.workflow_display — ワークフロー表示書式の共通ヘルパー（GUI 専用）。

全 GUI 画面で統一書式 ``{ワークフロー名} ({ワークフローID:全て大文字})`` を提供する。
例: ``Auto Requirement Definition (ARD)``

データソース優先順位:
  1. 呼び出し側が ``workflow_name`` を明示指定した場合はそれを使用
     （ただし空文字 / ``workflow_id`` と同値の場合は無視して下記へフォールバック）。
  2. :mod:`hve.template_engine` の ``_WORKFLOW_DISPLAY_NAMES``
     （CLI / Issue タイトル側と同一表示を保証するためここを最優先解決源とする）。
  3. :mod:`hve.workflow_registry` の ``WorkflowDef.name``。

CLI / Issue タイトル側で表示名を変更した場合、本ヘルパー経由の GUI 表示も
同時に追従する。GUI 専用ヘルパーであり、CLI 側からは直接利用しない。
"""

from __future__ import annotations

import html
import logging
from typing import Optional

_logger = logging.getLogger(__name__)


def _lookup_display_name(workflow_id: str) -> str:
    """登録済みソースから workflow_id に対応する表示名を解決する。

    1. ``template_engine._WORKFLOW_DISPLAY_NAMES`` を優先
    2. 上記が空 / 未登録なら ``workflow_registry.WorkflowDef.name``
    解決できなければ空文字を返す。
    """
    if not workflow_id:
        return ""
    # 1) template_engine（CLI/Issue タイトル側と統一）
    try:
        from hve.template_engine import _WORKFLOW_DISPLAY_NAMES

        name = _WORKFLOW_DISPLAY_NAMES.get(workflow_id)
        if name:
            return name
    except (ImportError, AttributeError) as exc:
        _logger.debug("template_engine display name lookup failed: %s", exc)
    # 2) workflow_registry
    try:
        from hve.workflow_registry import get_workflow

        wf = get_workflow(workflow_id)
        if wf is not None and wf.name:
            return wf.name
    except (ImportError, AttributeError) as exc:
        _logger.debug("workflow_registry display name lookup failed: %s", exc)
    return ""


def _resolve_name(workflow_id: str, workflow_name: Optional[str]) -> str:
    """workflow_name が空 / ID と同一の場合は登録済みソースから解決する。"""
    name = (workflow_name or "").strip()
    wf_id = (workflow_id or "").strip()
    if name and name.lower() != wf_id.lower():
        return name
    return _lookup_display_name(wf_id) or name


def format_workflow_label(
    workflow_id: str,
    workflow_name: Optional[str] = None,
) -> str:
    """プレーンテキスト用の統一書式を返す。

    Returns:
        ``"{name} ({ID-UPPER})"``。
        - name が解決できないとき: ``"({ID-UPPER})"``
        - workflow_id が空のとき: ``name``（空なら空文字）
    """
    wf_id = (workflow_id or "").strip()
    name = _resolve_name(wf_id, workflow_name)
    wf_upper = wf_id.upper()
    if name and wf_id:
        return f"{name} ({wf_upper})"
    if wf_id:
        return f"({wf_upper})"
    return name


def format_workflow_label_activity(
    workflow_id: str,
    workflow_name: Optional[str] = None,
) -> str:
    """Step 2 「作業状況」表示専用の書式を返す。

    書式: ``{ID-UPPER}-{Name}``（例: ``ARD-Auto Requirement Definition``）

    エッジケース:
        - name 解決不可: ``{ID-UPPER}``
        - workflow_id 空: ``name``（空なら空文字）
        - 両方空: ``""``
    """
    wf_id = (workflow_id or "").strip()
    name = _resolve_name(wf_id, workflow_name)
    wf_upper = wf_id.upper()
    if name and wf_id:
        return f"{wf_upper}-{name}"
    if wf_id:
        return wf_upper
    return name


def format_workflow_label_html(
    workflow_id: str,
    workflow_name: Optional[str] = None,
) -> str:
    """HTML エスケープ済の統一書式を返す。"""
    wf_id = (workflow_id or "").strip()
    name = _resolve_name(wf_id, workflow_name)
    wf_upper = wf_id.upper()
    name_esc = html.escape(name)
    wf_esc = html.escape(wf_upper)
    if name and wf_id:
        return f"{name_esc} ({wf_esc})"
    if wf_id:
        return f"({wf_esc})"
    return name_esc
