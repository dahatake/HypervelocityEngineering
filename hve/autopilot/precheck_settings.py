"""hve.autopilot.precheck_settings — workflow-specific 設定の必須判定。

Qt 非依存。

旧版で扱っていた以下は撤去:
  - ``collect_missing_auth``: Plugin/MCP Server 認証は GitHub Copilot CLI 側で
    完結するため HVE 側の AUTH カテゴリ機構ごと削除。

Workflow-specific 設定（例: ARD の target_business が CLI 引数として必須等）の
拡張点はここに集約する。
"""

from __future__ import annotations

from typing import Dict, List


# Workflow ごとに「Autopilot 実行で必須」な workflow-specific 設定キー。
# 現状は空。将来追加時はここに宣言する。
_REQUIRED_SETTING_KEYS: Dict[str, List[str]] = {}


__all__: list = []
