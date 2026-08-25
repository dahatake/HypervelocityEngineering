#!/usr/bin/env bash
# workflow-registry.sh — ワークフロー定義レジストリ
#
# Migrated from:
#   - .github/cli/lib/workflow_registry.py
#
# This registry is the single source of truth for workflow DAG definitions used
# by Bash orchestration. Definitions are stored as JSON and queried with jq.
#
# Registered workflow IDs:
#   - aas   (App Architecture Design)       : step execution
#   - asdw-web (Web App Dev & Deploy)           : step execution (container + deploy step を含む)
#   - adfd   (Dataflow Design)                  : step execution
#   - adfdv  (Dataflow Dev)                     : step execution + QA/review feedback
#   - aag   (AI Agent Design)               : step execution
#   - aagd  (AI Agent Dev & Deploy)         : step execution (deploy step を含む)
#   - aar   (Agentic Retrieval Add-on)      : step execution (deploy step を含む)
#   - ada   (Agent Data Architecture)       : step execution
#   - adoc  (Source Codeからのドキュメント作成) : step execution
#
# Registry responsibilities:
#   - Step execution: resolve root steps / next runnable steps from depends_on
#   - PR state transitions: provide workflow-specific state labels
#     (${workflow_id}:{initialized|ready|running|done|blocked})
#   - QA/Review feedback flow: keep workflow-local feedback steps in DAG order
#
# Naming conventions (current registry):
#   - workflow_id: lowercase identifier (e.g. aas, adfdv, aagd)
#   - step.id: "N" or "N.M" (dot-separated numeric segments)
#   - state label prefix: equals workflow_id
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
  "name": "App Architecture Design",
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
    {"id":"1","title":"ソフトウェアアーキテクチャの推薦","custom_agent":"Arch-ArchitectureCandidateAnalyzer","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aas/step-1.md"},
    {"id":"2.1","title":"ドメイン分析","custom_agent":"Arch-Microservice-DomainAnalytics","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aas/step-2.1.md"},
    {"id":"2.2","title":"サービス一覧抽出","custom_agent":"Arch-Microservice-ServiceIdentify","depends_on":["2.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aas/step-2.2.md"},
    {"id":"3.1","title":"データモデル設計","custom_agent":"Arch-DataModeling","depends_on":["2.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aas/step-3.1.md"},
    {"id":"3.2","title":"サンプルデータ生成","custom_agent":"Arch-DataModeling","depends_on":["3.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aas/step-3.2.md"},
    {"id":"4","title":"データカタログ作成","custom_agent":"Arch-DataCatalog","depends_on":["3.1"],"is_container":false,"skip_fallback_deps":["3.1"],"block_unless":[],"body_template_path":"templates/aas/step-4.md"},
    {"id":"5","title":"サービスカタログ","custom_agent":"Arch-Microservice-ServiceCatalog","depends_on":["4"],"is_container":false,"skip_fallback_deps":["4"],"block_unless":[],"body_template_path":"templates/aas/step-5.md"},
    {"id":"6","title":"テスト戦略書","custom_agent":"Arch-TDD-TestStrategy","depends_on":["5"],"is_container":false,"skip_fallback_deps":["5"],"block_unless":[],"body_template_path":"templates/aas/step-6.md"},
    {"id":"7","title":"ペルソナカタログ","custom_agent":"Arch-PersonaCatalog","depends_on":["6"],"is_container":false,"skip_fallback_deps":["6"],"block_unless":[],"body_template_path":"templates/aas/step-7.md"},
    {"id":"8","title":"ペルソナ別共通画面カタログ","custom_agent":"Arch-UI-PersonaScreenList","depends_on":["7"],"is_container":false,"skip_fallback_deps":["7"],"block_unless":[],"body_template_path":"templates/aas/step-8.md"}
  ]
}
JSONEOF
)



_WORKFLOW_REGISTRY[ard]=$(cat <<'JSONEOF'
{
  "id": "ard",
  "name": "Auto Requirement Definition",
  "label_prefix": "ard",
  "state_labels": {
    "initialized": "ard:initialized",
    "ready": "ard:ready",
    "running": "ard:running",
    "done": "ard:done",
    "blocked": "ard:blocked"
  },
  "params": ["company_name", "target_business", "survey_base_date", "survey_period_years", "target_region", "analysis_purpose", "target_recommendation_id", "attached_docs", "include_kpi_okr"],
  "steps": [
    {"id":"1","title":"事業分野候補列挙","custom_agent":"Arch-ARD-BusinessAnalysis-Untargeted","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ard/step-1.md"},
    {"id":"1.1","title":"事業分野別深掘り分析","custom_agent":"Arch-ARD-BusinessAnalysis-Untargeted","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ard/step-1.1.md"},
    {"id":"1.2","title":"事業分析統合","custom_agent":"Arch-ARD-BusinessAnalysis-Untargeted","depends_on":["1.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ard/step-1.2.md"},
    {"id":"2","title":"対象業務深掘り分析","custom_agent":"Arch-ARD-BusinessAnalysis-Targeted","depends_on":[],"is_container":false,"skip_fallback_deps":["1.2"],"block_unless":[],"body_template_path":"templates/ard/step-2.md"},
    {"id":"2.1","title":"KPI/OKR 定義（任意）","custom_agent":"Arch-ARD-KPIOKRDefinition","depends_on":["2"],"is_container":false,"skip_fallback_deps":["1.2"],"block_unless":[],"body_template_path":"templates/ard/step-2.1.md"},
    {"id":"3.1","title":"ユースケース骨格抽出","custom_agent":"Arch-ARD-UseCaseCatalog","depends_on":["2"],"is_container":false,"skip_fallback_deps":["1.2"],"block_unless":[],"body_template_path":"templates/ard/step-3.1.md"},
    {"id":"3.2","title":"ユースケース詳細生成","custom_agent":"Arch-ARD-UseCaseCatalog","depends_on":["3.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ard/step-3.2.md"},
    {"id":"3.3","title":"ユースケースカタログ統合","custom_agent":"Arch-ARD-UseCaseCatalog","depends_on":["3.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ard/step-3.3.md"},
    {"id":"4.1","title":"アプリケーションリスト作成","custom_agent":"Arch-ApplicationAnalytics","depends_on":["3.3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ard/step-4.1.md"},
    {"id":"4.2","title":"APP別要求定義書作成","custom_agent":"Arch-ApplicationRequirementDefinition","depends_on":["4.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ard/step-4.2.md"}
  ]
}
JSONEOF
)



_WORKFLOW_REGISTRY[asdw-web]=$(cat <<'JSONEOF'
{
  "id": "asdw-web",
  "name": "Web App Dev & Deploy",
  "label_prefix": "asdw-web",
  "state_labels": {
    "initialized": "asdw-web:initialized",
    "ready": "asdw-web:ready",
    "running": "asdw-web:running",
    "done": "asdw-web:done",
    "blocked": "asdw-web:blocked"
  },
  "params": ["app_ids", "app_id", "resource_group", "usecase_id", "tdd_max_retries", "create_remote_mcp_server"],
  "steps": [
    {"id":"1","title":"データ（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"2","title":"追加サービス（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"3","title":"Compute（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"4","title":"UI（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"5","title":"レビュー（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"1.1","title":"Azure データストア選定","custom_agent":"Dev-Microservice-Azure-DataDesign","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-1.1.md"},
    {"id":"1.2","title":"データストア検証テスト生成 (TDD RED)","custom_agent":"Dev-Microservice-Azure-DataTestCoding","depends_on":["1.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-1.2.md"},
    {"id":"1.3","title":"Azure データサービス Deploy (TDD GREEN)","custom_agent":"Dev-Microservice-Azure-DataDeploy","depends_on":["1.2","4.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-1.3.md"},
    {"id":"2.1","title":"追加 Azure サービス選定","custom_agent":"Dev-Microservice-Azure-AddServiceDesign","depends_on":["1.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-2.1.md"},
    {"id":"2.2","title":"追加 Azure サービス Deploy","custom_agent":"Dev-Microservice-Azure-AddServiceDeploy","depends_on":["1.3","2.1"],"is_container":false,"skip_fallback_deps":["2.1"],"block_unless":[],"body_template_path":"templates/asdw-web/step-2.2.md"},
    {"id":"2.3","title":"追加サービスのテストコード生成 (TDD RED)","custom_agent":"Dev-Microservice-Azure-AddServiceTestCoding","depends_on":["2.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-2.3.md"},
    {"id":"2.4","title":"追加サービスのテスト実施 (TDD GREEN)","custom_agent":"Dev-Microservice-Azure-AddServiceTesting","depends_on":["2.2","2.3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-2.4.md"},
    {"id":"2.5","title":"Agentic Retrieval Azure 実装設計","custom_agent":"Dev-Microservice-Azure-AgenticRetrievalDesign","depends_on":["2.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-2.5.md"},
    {"id":"2.6","title":"Agentic Retrieval Deploy","custom_agent":"Dev-Microservice-Azure-AgenticRetrievalDeploy","depends_on":["2.2","2.5"],"is_container":false,"skip_fallback_deps":["2.5"],"block_unless":[],"body_template_path":"templates/asdw-web/step-2.6.md"},
    {"id":"3.1","title":"Azure コンピュート選定","custom_agent":"Dev-Microservice-Azure-ComputeDesign","depends_on":["2.3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-3.1.md"},
    {"id":"3.2","title":"サービス テストコード生成 (TDD RED)","custom_agent":"Dev-Microservice-Azure-ServiceTestCoding","depends_on":["3.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-3.2.md"},
    {"id":"3.3","title":"サービスコード実装 (TDD GREEN)","custom_agent":"Dev-Microservice-Azure-ServiceCoding-AzureFunctions","depends_on":["3.2"],"is_container":false,"skip_fallback_deps":["3.2"],"block_unless":[],"body_template_path":"templates/asdw-web/step-3.3.md"},
    {"id":"3.4","title":"Azure Compute Deploy","custom_agent":"Dev-Microservice-Azure-ComputeDeploy-AzureFunctions","depends_on":["2.4","3.3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-3.4.md"},
    {"id":"3.5","title":"Deploy 後 再テスト","custom_agent":"Dev-Microservice-Azure-ComputePostDeployTest","depends_on":["3.4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-3.5.md"},
    {"id":"4.1","title":"UI テストコード生成 (TDD RED)","custom_agent":"Dev-Microservice-Azure-UITestCoding","depends_on":["3.3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-4.1.md"},
    {"id":"4.2","title":"UI 実装 (TDD GREEN)","custom_agent":"Dev-Microservice-Azure-UICoding","depends_on":["1.2","2.5","4.1"],"is_container":false,"skip_fallback_deps":["4.1"],"block_unless":[],"body_template_path":"templates/asdw-web/step-4.2.md"},
    {"id":"4.3","title":"Web アプリ Deploy (Azure SWA)","custom_agent":"Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps","depends_on":["3.5","4.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-4.3.md"},
    {"id":"4.4","title":"UI E2E テスト (Playwright)","custom_agent":"E2ETesting-Playwright","depends_on":["4.3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-4.4.md"},
    {"id":"5.1","title":"WAF アーキテクチャレビュー","custom_agent":"QA-AzureArchitectureReview","depends_on":["4.4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-5.1.md"},
    {"id":"5.2","title":"整合性チェック","custom_agent":"QA-AzureDependencyReview","depends_on":["4.4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-5.2.md"},
    {"id":"5.3","title":"要件適合実測","custom_agent":"QA-RequirementsConformanceEval","depends_on":["5.1","5.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/asdw-web/step-5.3.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[adfd]=$(cat <<'JSONEOF'
{
  "id": "adfd",
  "name": "Dataflow Design",
  "label_prefix": "adfd",
  "state_labels": {
    "initialized": "adfd:initialized",
    "ready": "adfd:ready",
    "running": "adfd:running",
    "done": "adfd:done",
    "blocked": "adfd:blocked"
  },
  "params": ["app_ids", "app_id"],
  "steps": [
    {"id":"0.1","title":"データフローデータモデル定義書","custom_agent":"Arch-Dataflow-DataModel","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfd/step-0.1.md"},
    {"id":"0.2","title":"データフローアプリカタログ","custom_agent":"Arch-Dataflow-AppCatalog","depends_on":["0.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfd/step-0.2.md"},
    {"id":"4","title":"データフローサービスカタログ","custom_agent":"Arch-Dataflow-ServiceCatalog","depends_on":["0.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfd/step-4.md"},
    {"id":"5","title":"データフローテスト戦略書","custom_agent":"Arch-Dataflow-TestStrategy","depends_on":["4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfd/step-5.md"},
    {"id":"1","title":"ジョブ詳細仕様書","custom_agent":"Arch-Dataflow-AppSpec","depends_on":["5"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfd/step-1.md"},
    {"id":"2","title":"監視・運用設計書","custom_agent":"Arch-Dataflow-MonitoringDesign","depends_on":["5"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfd/step-2.md"},
    {"id":"3","title":"TDDテスト仕様書","custom_agent":"Arch-Dataflow-TDD-TestSpec","depends_on":["1","2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfd/step-3.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[adfdv]=$(cat <<'JSONEOF'
{
  "id": "adfdv",
  "name": "Dataflow Dev",
  "label_prefix": "adfdv",
  "state_labels": {
    "initialized": "adfdv:initialized",
    "ready": "adfdv:ready",
    "running": "adfdv:running",
    "done": "adfdv:done",
    "blocked": "adfdv:blocked"
  },
  "params": ["resource_group", "app_id"],
  "steps": [
    {"id":"1.1","title":"データサービス選定","custom_agent":"Dev-Dataflow-DataServiceSelect","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfdv/step-1.1.md"},
    {"id":"1.2","title":"Azure データリソース Deploy","custom_agent":"Dev-Dataflow-DataDeploy","depends_on":["1.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfdv/step-1.2.md"},
    {"id":"2.1","title":"TDD RED — テストコード作成","custom_agent":"Dev-Dataflow-TestCoding","depends_on":["1.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfdv/step-2.1.md"},
    {"id":"2.2","title":"TDD GREEN — データフローアプリ本実装","custom_agent":"Dev-Dataflow-ServiceCoding","depends_on":["2.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfdv/step-2.2.md"},
    {"id":"3","title":"Azure Functions/コンテナ Deploy","custom_agent":"Dev-Dataflow-FunctionsDeploy","depends_on":["2.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfdv/step-3.md"},
    {"id":"4.1","title":"WAF レビュー","custom_agent":"QA-AzureArchitectureReview","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfdv/step-4.1.md"},
    {"id":"4.2","title":"整合性チェック","custom_agent":"QA-AzureDependencyReview","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfdv/step-4.2.md"},
    {"id":"4.3","title":"要件適合実測","custom_agent":"QA-RequirementsConformanceEval","depends_on":["4.1","4.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adfdv/step-4.3.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[aag]=$(cat <<'JSONEOF'
{
  "id": "aag",
  "name": "AI Agent Design",
  "label_prefix": "aag",
  "state_labels": {
    "initialized": "aag:initialized",
    "ready": "aag:ready",
    "running": "aag:running",
    "done": "aag:done",
    "blocked": "aag:blocked"
  },
  "params": ["app_ids", "app_id", "usecase_id"],
  "steps": [
    {"id":"1","title":"AI Agent アプリケーション定義","custom_agent":"Arch-AIAgentDesign-Step1","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aag/step-1.md"},
    {"id":"2","title":"AI Agent 粒度設計","custom_agent":"Arch-AIAgentDesign-Step2","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aag/step-2.md"},
    {"id":"3","title":"AI Agent 詳細設計","custom_agent":"Arch-AIAgentDesign-Step3","depends_on":["2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aag/step-3.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[aagd]=$(cat <<'JSONEOF'
{
  "id": "aagd",
  "name": "AI Agent Dev & Deploy",
  "label_prefix": "aagd",
  "state_labels": {
    "initialized": "aagd:initialized",
    "ready": "aagd:ready",
    "running": "aagd:running",
    "done": "aagd:done",
    "blocked": "aagd:blocked"
  },
  "params": ["app_ids", "app_id", "resource_group", "usecase_id"],
  "steps": [
    {"id":"1","title":"AI Agent 構成設計","custom_agent":"Arch-AIAgentDesign-Step1","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aagd/step-1.md"},
    {"id":"2.1","title":"AI Agent テスト仕様書 (TDD RED)","custom_agent":"Arch-TDD-TestSpec","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aagd/step-2.1.md"},
    {"id":"2.2","title":"AI Agent テストコード生成 (TDD RED)","custom_agent":"Dev-Microservice-Azure-AgentTestCoding","depends_on":["2.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aagd/step-2.2.md"},
    {"id":"2.3","title":"AI Agent 実装 (TDD GREEN)","custom_agent":"Dev-Microservice-Azure-AgentCoding","depends_on":["2.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aagd/step-2.3.md"},
    {"id":"3","title":"AI Agent Deploy","custom_agent":"Dev-Microservice-Azure-AgentDeploy","depends_on":["2.3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aagd/step-3.md"},
    {"id":"4","title":"tool search 実測評価","custom_agent":"QA-ToolSearchEval","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aagd/step-4.md"},
    {"id":"5","title":"要件適合実測","custom_agent":"QA-RequirementsConformanceEval","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aagd/step-5.md"},
    {"id":"6","title":"検索経路の適正化実測","custom_agent":"QA-AgentRouteRightsizingEval","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aagd/step-6.md"},
    {"id":"7","title":"Microsoft 365 / Teams 公開","custom_agent":"Dev-Agent-M365Publish","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aagd/step-7.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[aar]=$(cat <<'JSONEOF'
{
  "id": "aar",
  "name": "Agentic Retrieval Add-on",
  "label_prefix": "aar",
  "state_labels": {
    "initialized": "aar:initialized",
    "ready": "aar:ready",
    "running": "aar:running",
    "done": "aar:done",
    "blocked": "aar:blocked"
  },
  "params": ["app_ids", "app_id", "resource_group", "usecase_id"],
  "steps": [
    {"id":"1","title":"Agentic Retrieval 機能要件詳細","custom_agent":"Arch-AgenticRetrieval-Detail","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aar/step-1.md"},
    {"id":"2","title":"Agentic Retrieval Azure 実装設計","custom_agent":"Dev-Microservice-Azure-AgenticRetrievalDesign","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aar/step-2.md"},
    {"id":"3","title":"Agentic Retrieval テスト仕様","custom_agent":"Arch-TDD-TestSpec","depends_on":["2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aar/step-3.md"},
    {"id":"4","title":"Agentic Retrieval テストコード（TDD RED）","custom_agent":"Dev-Microservice-Azure-AgenticRetrievalTestCoding","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aar/step-4.md"},
    {"id":"5","title":"Agentic Retrieval Deploy","custom_agent":"Dev-Microservice-Azure-AgenticRetrievalDeploy","depends_on":["4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aar/step-5.md"},
    {"id":"6","title":"Retrieval 実測評価（reasoning effort 比較）","custom_agent":"QA-AgenticRetrievalEval","depends_on":["5"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aar/step-6.md"},
    {"id":"7","title":"要件適合実測","custom_agent":"QA-RequirementsConformanceEval","depends_on":["6"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/aar/step-7.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[ada]=$(cat <<'JSONEOF'
{
  "id": "ada",
  "name": "Agent Data Architecture",
  "label_prefix": "ada",
  "state_labels": {
    "initialized": "ada:initialized",
    "ready": "ada:ready",
    "running": "ada:running",
    "done": "ada:done",
    "blocked": "ada:blocked"
  },
  "params": ["app_ids", "app_id"],
  "steps": [
    {"id":"2","title":"ドメイン分析","custom_agent":"Arch-Microservice-DomainAnalytics","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ada/step-2.md"},
    {"id":"3","title":"サービス一覧抽出","custom_agent":"Arch-Microservice-ServiceIdentify","depends_on":["2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ada/step-3.md"},
    {"id":"4.1","title":"データモデル設計","custom_agent":"Arch-DataModeling","depends_on":["3"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ada/step-4.1.md"},
    {"id":"4.2","title":"サンプルデータ生成","custom_agent":"Arch-DataModeling","depends_on":["4.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ada/step-4.2.md"},
    {"id":"5","title":"データカタログ作成","custom_agent":"Arch-DataCatalog","depends_on":["4.1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ada/step-5.md"},
    {"id":"6","title":"ペルソナカタログ","custom_agent":"Arch-PersonaCatalog","depends_on":["5"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ada/step-6.md"},
    {"id":"7","title":"サービス詳細（Tool 定義根拠）","custom_agent":"Arch-Microservice-ServiceDetail","depends_on":["5"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ada/step-7.md"},
    {"id":"8","title":"非構造化データ資産カタログ","custom_agent":"Arch-AgentDataAsset","depends_on":["5"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ada/step-8.md"},
    {"id":"9","title":"テスト戦略書","custom_agent":"Arch-TDD-TestStrategy","depends_on":["6","7","8"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/ada/step-9.md"}
  ]
}
JSONEOF
)

_WORKFLOW_REGISTRY[adoc]=$(cat <<'JSONEOF'
{
  "id": "adoc",
  "name": "Source Codeからのドキュメント作成",
  "label_prefix": "adoc",
  "state_labels": {
    "initialized": "adoc:initialized",
    "ready": "adoc:ready",
    "running": "adoc:running",
    "done": "adoc:done",
    "blocked": "adoc:blocked"
  },
  "params": ["target_dirs", "exclude_patterns", "doc_purpose", "max_file_lines"],
  "steps": [
    {"id":"2","title":"ファイルサマリー（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"3","title":"コンポーネント分析（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"5","title":"アーキテクチャ横断分析（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"6","title":"目的特化ドキュメント（コンテナ）","custom_agent":null,"depends_on":[],"is_container":true,"skip_fallback_deps":[],"block_unless":[],"body_template_path":null},
    {"id":"1","title":"ファイルインベントリ","custom_agent":"Doc-FileInventory","depends_on":[],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-1.md"},
    {"id":"2.1","title":"ファイルサマリー（プロダクションコード）","custom_agent":"Doc-FileSummary","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-2.1.md"},
    {"id":"2.2","title":"ファイルサマリー（テストコード）","custom_agent":"Doc-TestSummary","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-2.2.md"},
    {"id":"2.3","title":"ファイルサマリー（設定・IaC）","custom_agent":"Doc-ConfigSummary","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-2.3.md"},
    {"id":"2.4","title":"ファイルサマリー（CI/CD）","custom_agent":"Doc-CICDSummary","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-2.4.md"},
    {"id":"2.5","title":"ファイルサマリー（大規模ファイル分割）","custom_agent":"Doc-LargeFileSummary","depends_on":["1"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-2.5.md"},
    {"id":"3.1","title":"コンポーネント設計書","custom_agent":"Doc-ComponentDesign","depends_on":["2.1","2.2","2.3","2.4","2.5"],"is_container":false,"skip_fallback_deps":["2.1"],"block_unless":[],"body_template_path":"templates/adoc/step-3.1.md"},
    {"id":"3.2","title":"API 仕様書","custom_agent":"Doc-APISpec","depends_on":["2.1","2.2","2.3","2.4","2.5"],"is_container":false,"skip_fallback_deps":["2.1"],"block_unless":[],"body_template_path":"templates/adoc/step-3.2.md"},
    {"id":"3.3","title":"データモデル定義書","custom_agent":"Doc-DataModel","depends_on":["2.1","2.2","2.3","2.4","2.5"],"is_container":false,"skip_fallback_deps":["2.1"],"block_unless":[],"body_template_path":"templates/adoc/step-3.3.md"},
    {"id":"3.4","title":"テスト仕様サマリー","custom_agent":"Doc-TestSpecSummary","depends_on":["2.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-3.4.md"},
    {"id":"3.5","title":"技術的負債一覧","custom_agent":"Doc-TechDebt","depends_on":["2.1","2.2","2.3","2.4","2.5"],"is_container":false,"skip_fallback_deps":["2.1"],"block_unless":[],"body_template_path":"templates/adoc/step-3.5.md"},
    {"id":"4","title":"コンポーネントインデックス","custom_agent":"Doc-ComponentIndex","depends_on":["3.1","3.2","3.3","3.4","3.5"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-4.md"},
    {"id":"5.1","title":"アーキテクチャ概要","custom_agent":"Doc-ArchOverview","depends_on":["4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-5.1.md"},
    {"id":"5.2","title":"依存関係マップ","custom_agent":"Doc-DependencyMap","depends_on":["4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-5.2.md"},
    {"id":"5.3","title":"インフラ依存分析","custom_agent":"Doc-InfraDeps","depends_on":["4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-5.3.md"},
    {"id":"5.4","title":"非機能要件現状分析","custom_agent":"Doc-NFRAnalysis","depends_on":["4","3.4","3.5"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-5.4.md"},
    {"id":"6.1","title":"オンボーディングガイド","custom_agent":"Doc-Onboarding","depends_on":["5.1","5.2"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-6.1.md"},
    {"id":"6.2","title":"リファクタリングガイド","custom_agent":"Doc-Refactoring","depends_on":["5.2","5.4","3.5"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-6.2.md"},
    {"id":"6.3","title":"移行アセスメント","custom_agent":"Doc-Migration","depends_on":["5.1","5.3","5.4"],"is_container":false,"skip_fallback_deps":[],"block_unless":[],"body_template_path":"templates/adoc/step-6.3.md"}
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
#   WORKFLOW_ID — Workflow identifier (aas, adfd, adfdv, aag, aagd, adoc)
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
