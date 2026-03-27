#!/usr/bin/env bash
# workflow-registry.sh — ワークフロー定義レジストリ
#
# Migrated from:
#   - .github/cli/lib/workflow_registry.py
#
# 6 workflows (AAS/AAD/ASDW/ABD/ABDV/AID) with step DAG definitions stored
# as JSON and queried with jq.
#
# Prerequisites:
#   - bash 4.0+ (associative arrays)
#   - jq installed (JSON parsing)
#
# Environment variables:
#   DRY_RUN — Set to "1" to enable dry-run mode
#
# Usage:
#   source ".github/scripts/bash/lib/workflow-registry.sh"

# NOTE: No `set -euo pipefail` — this file is sourced as a library and must
# not alter the caller's shell options.

# Guard against double-sourcing
if [[ -n "${_WORKFLOW_REGISTRY_SH_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
readonly _WORKFLOW_REGISTRY_SH_LOADED=1

# ---------------------------------------------------------------------------
# Workflow definitions as JSON
# ---------------------------------------------------------------------------
# Each workflow is stored as a JSON string in an associative array, keyed by
# the workflow ID (lowercase). Steps include:
#   id, title, custom_agent, depends_on[], is_container, skip_fallback_deps[], block_unless[]

declare -A _WORKFLOW_REGISTRY

_WORKFLOW_REGISTRY[aas]=$(cat <<'JSONEOF'
{
  "id": "aas",
  "name": "Auto App Selection",
  "label_prefix": "aas",
  "state_labels": {
    "initialized": "aas:initialized",
    "ready": "aas:ready",
    "running": "aas:running",
    "done": "aas:done",
    "blocked": "aas:blocked"
  },
  "params": [],
  "steps": [
    {"id":"1","title":"アプリケーションリストの作成","custom_agent":"Arch-ApplicationAnalytics","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aas/step-1.md"},
    {"id":"2","title":"ソフトウェアアーキテクチャの推薦","custom_agent":"Arch-ArchitectureCandidateAnalyzer","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aas/step-2.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[aad]=$(cat <<'JSONEOF'
{
  "id": "aad",
  "name": "Auto App Design",
  "label_prefix": "aad",
  "state_labels": {
    "initialized": "aad:initialized",
    "ready": "aad:ready",
    "running": "aad:running",
    "done": "aad:done",
    "blocked": "aad:blocked"
  },
  "params": [],
  "steps": [
    {"id":"1","title":"ドメイン分析 + サービス一覧抽出（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"7","title":"画面定義書 + マイクロサービス定義書（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"8","title":"AI Agent 設計（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"1.1","title":"ドメイン分析","custom_agent":"Arch-Microservice-DomainAnalytics","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aad/step-1.1.md"},
    {"id":"1.2","title":"サービス一覧抽出","custom_agent":"Arch-Microservice-ServiceIdentify","depends_on":["1.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aad/step-1.2.md"},
    {"id":"2","title":"データモデル","custom_agent":"Arch-DataModeling","depends_on":["1.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aad/step-2.md"},
    {"id":"3","title":"データカタログ作成","custom_agent":"Arch-DataCatalog","depends_on":["2"],"is_container":false,"skip_fallback_deps":["2"],"block_unless":[],"body_template_path":"templates/aad/step-3.md"},
    {"id":"4","title":"画面一覧と遷移図","custom_agent":"Arch-UI-List","depends_on":["3"],"is_container":false,"skip_fallback_deps":["3"],"block_unless":[],"body_template_path":"templates/aad/step-4.md"},
    {"id":"5","title":"サービスカタログ","custom_agent":"Arch-Microservice-ServiceCatalog","depends_on":["4"],"is_container":false,"skip_fallback_deps":["4"],"block_unless":[],"body_template_path":"templates/aad/step-5.md"},
    {"id":"6","title":"テスト戦略書","custom_agent":"Arch-TDD-TestStrategy","depends_on":["5"],"is_container":false,"skip_fallback_deps":["5"],"block_unless":[],"body_template_path":"templates/aad/step-6.md"},
    {"id":"7.1","title":"画面定義書","custom_agent":"Arch-UI-Detail","depends_on":["6"],"is_container":false,"skip_fallback_deps":["5"],"block_unless":[],"body_template_path":"templates/aad/step-7.1.md"},
    {"id":"7.2","title":"マイクロサービス定義書","custom_agent":"Arch-Microservice-ServiceDetail","depends_on":["6"],"is_container":false,"skip_fallback_deps":["5"],"block_unless":[],"body_template_path":"templates/aad/step-7.2.md"},
    {"id":"7.3","title":"TDDテスト仕様書","custom_agent":"Arch-TDD-TestSpec","depends_on":["6","7.1","7.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aad/step-7.3.md"},
    {"id":"8.1","title":"AI Agent アプリケーション定義","custom_agent":"Arch-AIAgentDesign","depends_on":["7.3"],"is_container":false,"skip_fallback_deps":["7.1","7.2"],"block_unless":[],"body_template_path":"templates/aad/step-8.1.md"},
    {"id":"8.2","title":"AI Agent 粒度設計","custom_agent":"Arch-AIAgentDesign","depends_on":["8.1"],"is_container":false,"skip_fallback_deps":["7.3"],"block_unless":[],"body_template_path":"templates/aad/step-8.2.md"},
    {"id":"8.3","title":"AI Agent 詳細設計","custom_agent":"Arch-AIAgentDesign","depends_on":["8.2"],"is_container":false,"skip_fallback_deps":["8.1"],"block_unless":[],"body_template_path":"templates/aad/step-8.3.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[asdw]=$(cat <<'JSONEOF'
{
  "id": "asdw",
  "name": "Auto App Dev Microservice Azure",
  "label_prefix": "asdw",
  "state_labels": {
    "initialized": "asdw:initialized",
    "ready": "asdw:ready",
    "running": "asdw:running",
    "done": "asdw:done",
    "blocked": "asdw:blocked"
  },
  "params": ["app_id", "resource_group", "usecase_id"],
  "steps": [
    {"id":"1","title":"データ（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"2","title":"マイクロサービス作成（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"3","title":"UI 作成（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"4","title":"アーキテクチャレビュー（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"1.1","title":"Azure データストア選定","custom_agent":"Dev-Microservice-Azure-DataDesign","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw/step-1.1.md"},
    {"id":"1.2","title":"Azure データサービス Deploy","custom_agent":"Dev-Microservice-Azure-DataDeploy","depends_on":["1.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw/step-1.2.md"},
    {"id":"2.1","title":"Azure コンピュート選定","custom_agent":"Dev-Microservice-Azure-ComputeDesign","depends_on":["1.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw/step-2.1.md"},
    {"id":"2.2","title":"追加 Azure サービス選定","custom_agent":"Dev-Microservice-Azure-AddServiceDesign","depends_on":["2.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw/step-2.2.md"},
    {"id":"2.3","title":"追加 Azure サービス Deploy","custom_agent":"Dev-Microservice-Azure-AddServiceDeploy","depends_on":["2.2"],"is_container":false,"skip_fallback_deps":["2.2"],"block_unless":[],"body_template_path":"templates/asdw/step-2.3.md"},
    {"id":"2.3T","title":"サービス テスト仕様書 (TDD RED)","custom_agent":"Arch-TDD-TestSpec","depends_on":["2.3"],"is_container":false,"skip_fallback_deps":["2.3"],"block_unless":[],"body_template_path":"templates/asdw/step-2.3T.md"},
    {"id":"2.3TC","title":"サービス テストコード生成 (TDD RED)","custom_agent":"Dev-Microservice-Azure-ServiceTestCoding","depends_on":["2.3T"],"is_container":false,"skip_fallback_deps":["2.3T"],"block_unless":[],"body_template_path":"templates/asdw/step-2.3TC.md"},
    {"id":"2.4","title":"サービスコード実装 (Azure Functions)","custom_agent":"Dev-Microservice-Azure-ServiceCoding-AzureFunctions","depends_on":["2.3TC"],"is_container":false,"skip_fallback_deps":["2.3TC"],"block_unless":[],"body_template_path":"templates/asdw/step-2.4.md"},
    {"id":"2.5","title":"Azure Compute Deploy","custom_agent":"Dev-Microservice-Azure-ComputeDeploy-AzureFunctions","depends_on":["2.4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw/step-2.5.md"},
    {"id":"2.6","title":"AI Agent 構成設計","custom_agent":"Arch-AIAgentDesign","depends_on":["2.5"],"is_container":false,"skip_fallback_deps":["2.5"],"block_unless":[],"body_template_path":"templates/asdw/step-2.6.md"},
    {"id":"2.7T","title":"AI Agent テスト仕様書 (TDD RED)","custom_agent":"Arch-TDD-TestSpec","depends_on":["2.6"],"is_container":false,"skip_fallback_deps":["2.6"],"block_unless":[],"body_template_path":"templates/asdw/step-2.7T.md"},
    {"id":"2.7TC","title":"AI Agent テストコード生成 (TDD RED)","custom_agent":"Dev-Microservice-Azure-AgentTestCoding","depends_on":["2.7T"],"is_container":false,"skip_fallback_deps":["2.7T"],"block_unless":[],"body_template_path":"templates/asdw/step-2.7TC.md"},
    {"id":"2.7","title":"AI Agent 実装 (TDD GREEN)","custom_agent":"Dev-Microservice-Azure-AgentCoding","depends_on":["2.7TC"],"is_container":false,"skip_fallback_deps":["2.7TC"],"block_unless":[],"body_template_path":"templates/asdw/step-2.7.md"},
    {"id":"2.8","title":"AI Agent Deploy","custom_agent":"Dev-Microservice-Azure-AgentDeploy","depends_on":["2.7"],"is_container":false,"skip_fallback_deps":["2.7"],"block_unless":[],"body_template_path":"templates/asdw/step-2.8.md"},
    {"id":"3.0T","title":"UI テスト仕様書 (TDD RED)","custom_agent":"Arch-TDD-TestSpec","depends_on":["2.8"],"is_container":false,"skip_fallback_deps":["2.8"],"block_unless":[],"body_template_path":"templates/asdw/step-3.0T.md"},
    {"id":"3.0TC","title":"UI テストコード生成 (TDD RED)","custom_agent":"Dev-Microservice-Azure-UITestCoding","depends_on":["3.0T"],"is_container":false,"skip_fallback_deps":["3.0T"],"block_unless":[],"body_template_path":"templates/asdw/step-3.0TC.md"},
    {"id":"3.1","title":"UI 実装","custom_agent":"Dev-Microservice-Azure-UICoding","depends_on":["3.0TC"],"is_container":false,"skip_fallback_deps":["3.0TC"],"block_unless":[],"body_template_path":"templates/asdw/step-3.1.md"},
    {"id":"3.2","title":"Web アプリ Deploy (Azure SWA)","custom_agent":"Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps","depends_on":["3.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw/step-3.2.md"},
    {"id":"4.1","title":"WAF アーキテクチャレビュー","custom_agent":"QA-AzureArchitectureReview","depends_on":["3.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw/step-4.1.md"},
    {"id":"4.2","title":"整合性チェック","custom_agent":"QA-AzureDependencyReview","depends_on":["3.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw/step-4.2.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[abd]=$(cat <<'JSONEOF'
{
  "id": "abd",
  "name": "Auto Batch Design",
  "label_prefix": "abd",
  "state_labels": {
    "initialized": "abd:initialized",
    "ready": "abd:ready",
    "running": "abd:running",
    "done": "abd:done",
    "blocked": "abd:blocked"
  },
  "params": [],
  "steps": [
    {"id":"1.1","title":"バッチドメイン分析","custom_agent":"Arch-Batch-DomainAnalytics","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abd/step-1.1.md"},
    {"id":"1.2","title":"データソース/デスティネーション分析","custom_agent":"Arch-Batch-DataSourceAnalysis","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abd/step-1.2.md"},
    {"id":"2","title":"バッチデータモデル","custom_agent":"Arch-Batch-DataModel","depends_on":["1.1","1.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abd/step-2.md"},
    {"id":"3","title":"ジョブ設計書","custom_agent":"Arch-Batch-JobCatalog","depends_on":["2"],"is_container":false,"skip_fallback_deps":["2"],"block_unless":[],"body_template_path":"templates/abd/step-3.md"},
    {"id":"4","title":"サービスカタログ","custom_agent":"Arch-Batch-ServiceCatalog","depends_on":["3"],"is_container":false,"skip_fallback_deps":["3"],"block_unless":[],"body_template_path":"templates/abd/step-4.md"},
    {"id":"5","title":"テスト戦略書","custom_agent":"Arch-Batch-TestStrategy","depends_on":["4"],"is_container":false,"skip_fallback_deps":["4"],"block_unless":[],"body_template_path":"templates/abd/step-5.md"},
    {"id":"6.1","title":"ジョブ詳細仕様書","custom_agent":"Arch-Batch-JobSpec","depends_on":["5"],"is_container":false,"skip_fallback_deps":["4"],"block_unless":[],"body_template_path":"templates/abd/step-6.1.md"},
    {"id":"6.2","title":"監視・運用設計書","custom_agent":"Arch-Batch-MonitoringDesign","depends_on":["5"],"is_container":false,"skip_fallback_deps":["4"],"block_unless":[],"body_template_path":"templates/abd/step-6.2.md"},
    {"id":"6.3","title":"TDDテスト仕様書","custom_agent":"Arch-Batch-TDD-TestSpec","depends_on":["6.1","6.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abd/step-6.3.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[abdv]=$(cat <<'JSONEOF'
{
  "id": "abdv",
  "name": "Auto Batch Dev",
  "label_prefix": "abdv",
  "state_labels": {
    "initialized": "abdv:initialized",
    "ready": "abdv:ready",
    "running": "abdv:running",
    "done": "abdv:done",
    "blocked": "abdv:blocked"
  },
  "params": ["resource_group", "batch_job_id"],
  "steps": [
    {"id":"1.1","title":"データサービス選定","custom_agent":"Dev-Batch-Deploy","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abdv/step-1.1.md"},
    {"id":"1.2","title":"Azure データリソース Deploy","custom_agent":"Dev-Batch-Deploy","depends_on":["1.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abdv/step-1.2.md"},
    {"id":"2.1","title":"TDD RED — テストコード作成","custom_agent":"Dev-Batch-TestCoding","depends_on":["1.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abdv/step-2.1.md"},
    {"id":"2.2","title":"TDD GREEN — バッチジョブ本実装","custom_agent":"Dev-Batch-ServiceCoding","depends_on":["2.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abdv/step-2.2.md"},
    {"id":"3","title":"Azure Functions/コンテナ Deploy","custom_agent":"Dev-Batch-Deploy","depends_on":["2.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abdv/step-3.md"},
    {"id":"4.1","title":"WAF レビュー","custom_agent":"QA-AzureArchitectureReview","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abdv/step-4.1.md"},
    {"id":"4.2","title":"整合性チェック","custom_agent":"QA-AzureDependencyReview","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/abdv/step-4.2.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[aid]=$(cat <<'JSONEOF'
{
  "id": "aid",
  "name": "Auto IoT Design",
  "label_prefix": "aid",
  "state_labels": {
    "initialized": "aid:initialized",
    "ready": "aid:ready",
    "running": "aid:running",
    "done": "aid:done",
    "blocked": "aid:blocked"
  },
  "params": [],
  "steps": [
    {"id":"5","title":"画面定義書 + マイクロサービス定義書（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"1.1","title":"IoT ドメイン分析","custom_agent":"Arch-IoT-DomainAnalytics","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aid/step-1.1.md"},
    {"id":"1.2","title":"デバイスプロファイル＋接続性分析","custom_agent":"Arch-IoT-DeviceConnectivity","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aid/step-1.2.md"},
    {"id":"2","title":"データモデル","custom_agent":"Arch-DataModeling","depends_on":["1.1","1.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aid/step-2.md"},
    {"id":"3","title":"画面一覧/構造","custom_agent":"Arch-UI-List","depends_on":["2"],"is_container":false,"skip_fallback_deps":["2"],"block_unless":[],"body_template_path":"templates/aid/step-3.md"},
    {"id":"4","title":"サービスカタログ","custom_agent":"Arch-Microservice-ServiceCatalog","depends_on":["3"],"is_container":false,"skip_fallback_deps":["3"],"block_unless":[],"body_template_path":"templates/aid/step-4.md"},
    {"id":"4.5","title":"テスト戦略書","custom_agent":"Arch-TDD-TestStrategy","depends_on":["4"],"is_container":false,"skip_fallback_deps":["4"],"block_unless":[],"body_template_path":"templates/aid/step-4.5.md"},
    {"id":"5.1","title":"画面定義書","custom_agent":"Arch-UI-Detail","depends_on":["4.5"],"is_container":false,"skip_fallback_deps":["4"],"block_unless":[],"body_template_path":"templates/aid/step-5.1.md"},
    {"id":"5.2","title":"マイクロサービス定義書","custom_agent":"Arch-Microservice-ServiceDetail","depends_on":["4.5"],"is_container":false,"skip_fallback_deps":["4"],"block_unless":[],"body_template_path":"templates/aid/step-5.2.md"},
    {"id":"5.3","title":"TDDテスト仕様書","custom_agent":"Arch-TDD-TestSpec","depends_on":["4.5","5.1","5.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aid/step-5.3.md"}
  ]
}
JSONEOF
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# get_workflow WORKFLOW_ID
#
# Retrieve full workflow definition as JSON.
#
# Args:
#   WORKFLOW_ID — Workflow identifier (aas, aad, asdw, abd, abdv, aid)
#
# Output:
#   Workflow JSON on stdout.
#   Returns 0 if found, 1 if not found.
get_workflow() {
  local workflow_id="${1:?get_workflow: WORKFLOW_ID required}"
  workflow_id=$(echo "${workflow_id}" | tr '[:upper:]' '[:lower:]')

  if [[ -n "${_WORKFLOW_REGISTRY[${workflow_id}]+x}" ]]; then
    echo "${_WORKFLOW_REGISTRY[${workflow_id}]}"
    return 0
  fi

  echo "ERROR: Unknown workflow: ${workflow_id}" >&2
  return 1
}

# get_step WORKFLOW_ID STEP_ID
#
# Retrieve a single step definition as JSON.
#
# Args:
#   WORKFLOW_ID — Workflow identifier
#   STEP_ID    — Step identifier (e.g. "1.1", "7.3")
#
# Output:
#   Step JSON on stdout.
#   Returns 0 if found, 1 if not found.
get_step() {
  local workflow_id="${1:?get_step: WORKFLOW_ID required}"
  local step_id="${2:?get_step: STEP_ID required}"

  local wf_json
  wf_json=$(get_workflow "${workflow_id}") || return 1

  local step_json
  step_json=$(echo "${wf_json}" | jq --arg sid "${step_id}" '.steps[] | select(.id == $sid)' 2>/dev/null)

  if [[ -z "${step_json}" || "${step_json}" == "null" ]]; then
    echo "ERROR: Step '${step_id}' not found in workflow '${workflow_id}'" >&2
    return 1
  fi

  echo "${step_json}"
}

# get_root_steps WORKFLOW_ID
#
# Retrieve root nodes (no dependencies, non-container) as JSON array.
#
# Args:
#   WORKFLOW_ID — Workflow identifier
#
# Output:
#   JSON array of root step objects on stdout.
get_root_steps() {
  local workflow_id="${1:?get_root_steps: WORKFLOW_ID required}"

  local wf_json
  wf_json=$(get_workflow "${workflow_id}") || return 1

  echo "${wf_json}" | jq '[.steps[] | select(.is_container == false) | select((.depends_on | length) == 0)]'
}

# get_next_steps WORKFLOW_ID COMPLETED_JSON [SKIPPED_JSON]
#
# Given completed and skipped step IDs, compute the next runnable steps.
#
# "Runnable" means:
#   1. Not completed, not skipped, not a container
#   2. All dependencies are resolved (completed, skipped, or not in registry)
#
# Args:
#   WORKFLOW_ID    — Workflow identifier
#   COMPLETED_JSON — JSON array of completed step IDs, e.g. '["1","1.1"]'
#   SKIPPED_JSON   — Optional JSON array of skipped step IDs, e.g. '["3"]'
#
# Output:
#   JSON array of runnable step objects on stdout.
get_next_steps() {
  local workflow_id="${1:?get_next_steps: WORKFLOW_ID required}"
  local completed_json="${2:?get_next_steps: COMPLETED_JSON required}"
  local skipped_json="${3:-[]}"

  local wf_json
  wf_json=$(get_workflow "${workflow_id}") || return 1

  echo "${wf_json}" | jq --argjson completed "${completed_json}" --argjson skipped "${skipped_json}" '
    # Build sets for fast lookup
    ($completed + $skipped) as $effective_done |
    [.steps[].id] as $existing_ids |
    [
      .steps[]
      | select(.is_container == false)
      | select(.id as $id | ($completed | index($id)) | not)
      | select(.id as $id | ($skipped | index($id)) | not)
      | select(
          if (.depends_on | length) == 0 then
            true
          else
            .depends_on | all(
              . as $dep |
              ($effective_done | index($dep) != null) or ($existing_ids | index($dep) == null)
            )
          end
        )
    ]
  '
}
