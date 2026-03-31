# workflow-registry.ps1 — ワークフロー定義レジストリ
#
# Migrated from:
#   - .github/scripts/bash/lib/workflow-registry.sh
#   - .github/cli/lib/workflow_registry.py
#
# 6 workflows (AAS/AAD/ASDW/ABD/ABDV/AID) with step DAG definitions stored
# as PSCustomObject structures.
#
# Prerequisites:
#   - PowerShell 7.0+
#
# Environment variables:
#   DRY_RUN — Set to "1" to enable dry-run mode
#
# Usage:
#   . "$PSScriptRoot/workflow-registry.ps1"

# Guard against double-sourcing
if (Test-Path Function:\Get-Workflow) { return }

# ---------------------------------------------------------------------------
# Workflow definitions as PSCustomObject
# ---------------------------------------------------------------------------

function script:NewWorkflowStep {
    param(
        [string]$Id,
        [string]$Title,
        $CustomAgent = $null,
        [string[]]$DependsOn = @(),
        [bool]$IsContainer = $false,
        [string[]]$SkipFallbackDeps = @(),
        [string[]]$BlockUnless = @(),
        $BodyTemplatePath = $null
    )
    return [PSCustomObject]@{
        id                 = $Id
        title              = $Title
        custom_agent       = $CustomAgent
        depends_on         = $DependsOn
        is_container       = $IsContainer
        skip_fallback_deps = $SkipFallbackDeps
        block_unless       = $BlockUnless
        body_template_path = $BodyTemplatePath
    }
}

$script:WorkflowRegistryData = @{}

# AAS — App Selection (2 steps)
$script:WorkflowRegistryData['aas'] = [PSCustomObject]@{
    id            = 'aas'
    name          = 'App Selection'
    label_prefix  = 'aas'
    state_labels  = [PSCustomObject]@{
        initialized = 'aas:initialized'
        ready       = 'aas:ready'
        running     = 'aas:running'
        done        = 'aas:done'
        blocked     = 'aas:blocked'
    }
    params        = @()
    steps         = @(
        (NewWorkflowStep -Id '1' -Title 'アプリケーションリストの作成' -CustomAgent 'Arch-ApplicationAnalytics' -BodyTemplatePath 'templates/aas/step-1.md')
        (NewWorkflowStep -Id '2' -Title 'ソフトウェアアーキテクチャの推薦' -CustomAgent 'Arch-ArchitectureCandidateAnalyzer' -DependsOn @('1') -BodyTemplatePath 'templates/aas/step-2.md')
    )
}

# AAD — App Design (16 steps)
$script:WorkflowRegistryData['aad'] = [PSCustomObject]@{
    id            = 'aad'
    name          = 'App Design'
    label_prefix  = 'aad'
    state_labels  = [PSCustomObject]@{
        initialized = 'aad:initialized'
        ready       = 'aad:ready'
        running     = 'aad:running'
        done        = 'aad:done'
        blocked     = 'aad:blocked'
    }
    params        = @()
    steps         = @(
        (NewWorkflowStep -Id '1' -Title 'ドメイン分析 + サービス一覧抽出（コンテナ）' -IsContainer $true)
        (NewWorkflowStep -Id '7' -Title '画面定義書 + マイクロサービス定義書（コンテナ）' -IsContainer $true)
        (NewWorkflowStep -Id '8' -Title 'AI Agent 設計（コンテナ）' -IsContainer $true)
        (NewWorkflowStep -Id '1.1' -Title 'ドメイン分析' -CustomAgent 'Arch-Microservice-DomainAnalytics' -BodyTemplatePath 'templates/aad/step-1.1.md')
        (NewWorkflowStep -Id '1.2' -Title 'サービス一覧抽出' -CustomAgent 'Arch-Microservice-ServiceIdentify' -DependsOn @('1.1') -BodyTemplatePath 'templates/aad/step-1.2.md')
        (NewWorkflowStep -Id '2' -Title 'データモデル' -CustomAgent 'Arch-DataModeling' -DependsOn @('1.2') -BodyTemplatePath 'templates/aad/step-2.md')
        (NewWorkflowStep -Id '3' -Title 'データカタログ作成' -CustomAgent 'Arch-DataCatalog' -DependsOn @('2') -SkipFallbackDeps @('2') -BodyTemplatePath 'templates/aad/step-3.md')
        (NewWorkflowStep -Id '4' -Title '画面一覧と遷移図' -CustomAgent 'Arch-UI-List' -DependsOn @('3') -SkipFallbackDeps @('3') -BodyTemplatePath 'templates/aad/step-4.md')
        (NewWorkflowStep -Id '5' -Title 'サービスカタログ' -CustomAgent 'Arch-Microservice-ServiceCatalog' -DependsOn @('4') -SkipFallbackDeps @('4') -BodyTemplatePath 'templates/aad/step-5.md')
        (NewWorkflowStep -Id '6' -Title 'テスト戦略書' -CustomAgent 'Arch-TDD-TestStrategy' -DependsOn @('5') -SkipFallbackDeps @('5') -BodyTemplatePath 'templates/aad/step-6.md')
        (NewWorkflowStep -Id '7.1' -Title '画面定義書' -CustomAgent 'Arch-UI-Detail' -DependsOn @('6') -SkipFallbackDeps @('5') -BodyTemplatePath 'templates/aad/step-7.1.md')
        (NewWorkflowStep -Id '7.2' -Title 'マイクロサービス定義書' -CustomAgent 'Arch-Microservice-ServiceDetail' -DependsOn @('6') -SkipFallbackDeps @('5') -BodyTemplatePath 'templates/aad/step-7.2.md')
        (NewWorkflowStep -Id '7.3' -Title 'TDDテスト仕様書' -CustomAgent 'Arch-TDD-TestSpec' -DependsOn @('6', '7.1', '7.2') -BodyTemplatePath 'templates/aad/step-7.3.md')
        (NewWorkflowStep -Id '8.1' -Title 'AI Agent アプリケーション定義' -CustomAgent 'Arch-AIAgentDesign' -DependsOn @('7.3') -SkipFallbackDeps @('7.1', '7.2') -BodyTemplatePath 'templates/aad/step-8.1.md')
        (NewWorkflowStep -Id '8.2' -Title 'AI Agent 粒度設計' -CustomAgent 'Arch-AIAgentDesign' -DependsOn @('8.1') -SkipFallbackDeps @('7.3') -BodyTemplatePath 'templates/aad/step-8.2.md')
        (NewWorkflowStep -Id '8.3' -Title 'AI Agent 詳細設計' -CustomAgent 'Arch-AIAgentDesign' -DependsOn @('8.2') -SkipFallbackDeps @('8.1') -BodyTemplatePath 'templates/aad/step-8.3.md')
    )
}

# ASDW — App Dev Microservice Azure (24 steps)
$script:WorkflowRegistryData['asdw'] = [PSCustomObject]@{
    id            = 'asdw'
    name          = 'App Dev Microservice Azure'
    label_prefix  = 'asdw'
    state_labels  = [PSCustomObject]@{
        initialized = 'asdw:initialized'
        ready       = 'asdw:ready'
        running     = 'asdw:running'
        done        = 'asdw:done'
        blocked     = 'asdw:blocked'
    }
    params        = @('app_id', 'resource_group', 'usecase_id')
    steps         = @(
        (NewWorkflowStep -Id '1' -Title 'データ（コンテナ）' -IsContainer $true)
        (NewWorkflowStep -Id '2' -Title 'マイクロサービス作成（コンテナ）' -IsContainer $true)
        (NewWorkflowStep -Id '3' -Title 'UI 作成（コンテナ）' -IsContainer $true)
        (NewWorkflowStep -Id '4' -Title 'アーキテクチャレビュー（コンテナ）' -IsContainer $true)
        (NewWorkflowStep -Id '1.1' -Title 'Azure データストア選定' -CustomAgent 'Dev-Microservice-Azure-DataDesign' -BodyTemplatePath 'templates/asdw/step-1.1.md')
        (NewWorkflowStep -Id '1.2' -Title 'Azure データサービス Deploy' -CustomAgent 'Dev-Microservice-Azure-DataDeploy' -DependsOn @('1.1') -BodyTemplatePath 'templates/asdw/step-1.2.md')
        (NewWorkflowStep -Id '2.1' -Title 'Azure コンピュート選定' -CustomAgent 'Dev-Microservice-Azure-ComputeDesign' -DependsOn @('1.2') -BodyTemplatePath 'templates/asdw/step-2.1.md')
        (NewWorkflowStep -Id '2.2' -Title '追加 Azure サービス選定' -CustomAgent 'Dev-Microservice-Azure-AddServiceDesign' -DependsOn @('2.1') -BodyTemplatePath 'templates/asdw/step-2.2.md')
        (NewWorkflowStep -Id '2.3' -Title '追加 Azure サービス Deploy' -CustomAgent 'Dev-Microservice-Azure-AddServiceDeploy' -DependsOn @('2.2') -SkipFallbackDeps @('2.2') -BodyTemplatePath 'templates/asdw/step-2.3.md')
        (NewWorkflowStep -Id '2.3T' -Title 'サービス テスト仕様書 (TDD RED)' -CustomAgent 'Arch-TDD-TestSpec' -DependsOn @('2.3') -SkipFallbackDeps @('2.3') -BodyTemplatePath 'templates/asdw/step-2.3T.md')
        (NewWorkflowStep -Id '2.3TC' -Title 'サービス テストコード生成 (TDD RED)' -CustomAgent 'Dev-Microservice-Azure-ServiceTestCoding' -DependsOn @('2.3T') -SkipFallbackDeps @('2.3T') -BodyTemplatePath 'templates/asdw/step-2.3TC.md')
        (NewWorkflowStep -Id '2.4' -Title 'サービスコード実装 (Azure Functions)' -CustomAgent 'Dev-Microservice-Azure-ServiceCoding-AzureFunctions' -DependsOn @('2.3TC') -SkipFallbackDeps @('2.3TC') -BodyTemplatePath 'templates/asdw/step-2.4.md')
        (NewWorkflowStep -Id '2.5' -Title 'Azure Compute Deploy' -CustomAgent 'Dev-Microservice-Azure-ComputeDeploy-AzureFunctions' -DependsOn @('2.4') -BodyTemplatePath 'templates/asdw/step-2.5.md')
        (NewWorkflowStep -Id '2.6' -Title 'AI Agent 構成設計' -CustomAgent 'Arch-AIAgentDesign' -DependsOn @('2.5') -SkipFallbackDeps @('2.5') -BodyTemplatePath 'templates/asdw/step-2.6.md')
        (NewWorkflowStep -Id '2.7T' -Title 'AI Agent テスト仕様書 (TDD RED)' -CustomAgent 'Arch-TDD-TestSpec' -DependsOn @('2.6') -SkipFallbackDeps @('2.6') -BodyTemplatePath 'templates/asdw/step-2.7T.md')
        (NewWorkflowStep -Id '2.7TC' -Title 'AI Agent テストコード生成 (TDD RED)' -CustomAgent 'Dev-Microservice-Azure-AgentTestCoding' -DependsOn @('2.7T') -SkipFallbackDeps @('2.7T') -BodyTemplatePath 'templates/asdw/step-2.7TC.md')
        (NewWorkflowStep -Id '2.7' -Title 'AI Agent 実装 (TDD GREEN)' -CustomAgent 'Dev-Microservice-Azure-AgentCoding' -DependsOn @('2.7TC') -SkipFallbackDeps @('2.7TC') -BodyTemplatePath 'templates/asdw/step-2.7.md')
        (NewWorkflowStep -Id '2.8' -Title 'AI Agent Deploy' -CustomAgent 'Dev-Microservice-Azure-AgentDeploy' -DependsOn @('2.7') -SkipFallbackDeps @('2.7') -BodyTemplatePath 'templates/asdw/step-2.8.md')
        (NewWorkflowStep -Id '3.0T' -Title 'UI テスト仕様書 (TDD RED)' -CustomAgent 'Arch-TDD-TestSpec' -DependsOn @('2.8') -SkipFallbackDeps @('2.8') -BodyTemplatePath 'templates/asdw/step-3.0T.md')
        (NewWorkflowStep -Id '3.0TC' -Title 'UI テストコード生成 (TDD RED)' -CustomAgent 'Dev-Microservice-Azure-UITestCoding' -DependsOn @('3.0T') -SkipFallbackDeps @('3.0T') -BodyTemplatePath 'templates/asdw/step-3.0TC.md')
        (NewWorkflowStep -Id '3.1' -Title 'UI 実装' -CustomAgent 'Dev-Microservice-Azure-UICoding' -DependsOn @('3.0TC') -SkipFallbackDeps @('3.0TC') -BodyTemplatePath 'templates/asdw/step-3.1.md')
        (NewWorkflowStep -Id '3.2' -Title 'Web アプリ Deploy (Azure SWA)' -CustomAgent 'Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps' -DependsOn @('3.1') -BodyTemplatePath 'templates/asdw/step-3.2.md')
        (NewWorkflowStep -Id '4.1' -Title 'WAF アーキテクチャレビュー' -CustomAgent 'QA-AzureArchitectureReview' -DependsOn @('3.2') -BodyTemplatePath 'templates/asdw/step-4.1.md')
        (NewWorkflowStep -Id '4.2' -Title '整合性チェック' -CustomAgent 'QA-AzureDependencyReview' -DependsOn @('3.2') -BodyTemplatePath 'templates/asdw/step-4.2.md')
    )
}

# ABD — Batch Design (9 steps)
$script:WorkflowRegistryData['abd'] = [PSCustomObject]@{
    id            = 'abd'
    name          = 'Batch Design'
    label_prefix  = 'abd'
    state_labels  = [PSCustomObject]@{
        initialized = 'abd:initialized'
        ready       = 'abd:ready'
        running     = 'abd:running'
        done        = 'abd:done'
        blocked     = 'abd:blocked'
    }
    params        = @()
    steps         = @(
        (NewWorkflowStep -Id '1.1' -Title 'バッチドメイン分析' -CustomAgent 'Arch-Batch-DomainAnalytics' -BodyTemplatePath 'templates/abd/step-1.1.md')
        (NewWorkflowStep -Id '1.2' -Title 'データソース/デスティネーション分析' -CustomAgent 'Arch-Batch-DataSourceAnalysis' -BodyTemplatePath 'templates/abd/step-1.2.md')
        (NewWorkflowStep -Id '2' -Title 'バッチデータモデル' -CustomAgent 'Arch-Batch-DataModel' -DependsOn @('1.1', '1.2') -BodyTemplatePath 'templates/abd/step-2.md')
        (NewWorkflowStep -Id '3' -Title 'ジョブ設計書' -CustomAgent 'Arch-Batch-JobCatalog' -DependsOn @('2') -SkipFallbackDeps @('2') -BodyTemplatePath 'templates/abd/step-3.md')
        (NewWorkflowStep -Id '4' -Title 'サービスカタログ' -CustomAgent 'Arch-Batch-ServiceCatalog' -DependsOn @('3') -SkipFallbackDeps @('3') -BodyTemplatePath 'templates/abd/step-4.md')
        (NewWorkflowStep -Id '5' -Title 'テスト戦略書' -CustomAgent 'Arch-Batch-TestStrategy' -DependsOn @('4') -SkipFallbackDeps @('4') -BodyTemplatePath 'templates/abd/step-5.md')
        (NewWorkflowStep -Id '6.1' -Title 'ジョブ詳細仕様書' -CustomAgent 'Arch-Batch-JobSpec' -DependsOn @('5') -SkipFallbackDeps @('4') -BodyTemplatePath 'templates/abd/step-6.1.md')
        (NewWorkflowStep -Id '6.2' -Title '監視・運用設計書' -CustomAgent 'Arch-Batch-MonitoringDesign' -DependsOn @('5') -SkipFallbackDeps @('4') -BodyTemplatePath 'templates/abd/step-6.2.md')
        (NewWorkflowStep -Id '6.3' -Title 'TDDテスト仕様書' -CustomAgent 'Arch-Batch-TDD-TestSpec' -DependsOn @('6.1', '6.2') -BodyTemplatePath 'templates/abd/step-6.3.md')
    )
}

# ABDV — Batch Dev (7 steps)
$script:WorkflowRegistryData['abdv'] = [PSCustomObject]@{
    id            = 'abdv'
    name          = 'Batch Dev'
    label_prefix  = 'abdv'
    state_labels  = [PSCustomObject]@{
        initialized = 'abdv:initialized'
        ready       = 'abdv:ready'
        running     = 'abdv:running'
        done        = 'abdv:done'
        blocked     = 'abdv:blocked'
    }
    params        = @('resource_group', 'batch_job_id')
    steps         = @(
        (NewWorkflowStep -Id '1.1' -Title 'データサービス選定' -CustomAgent 'Dev-Batch-Deploy' -BodyTemplatePath 'templates/abdv/step-1.1.md')
        (NewWorkflowStep -Id '1.2' -Title 'Azure データリソース Deploy' -CustomAgent 'Dev-Batch-Deploy' -DependsOn @('1.1') -BodyTemplatePath 'templates/abdv/step-1.2.md')
        (NewWorkflowStep -Id '2.1' -Title 'TDD RED — テストコード作成' -CustomAgent 'Dev-Batch-TestCoding' -DependsOn @('1.2') -BodyTemplatePath 'templates/abdv/step-2.1.md')
        (NewWorkflowStep -Id '2.2' -Title 'TDD GREEN — バッチジョブ本実装' -CustomAgent 'Dev-Batch-ServiceCoding' -DependsOn @('2.1') -BodyTemplatePath 'templates/abdv/step-2.2.md')
        (NewWorkflowStep -Id '3' -Title 'Azure Functions/コンテナ Deploy' -CustomAgent 'Dev-Batch-Deploy' -DependsOn @('2.2') -BodyTemplatePath 'templates/abdv/step-3.md')
        (NewWorkflowStep -Id '4.1' -Title 'WAF レビュー' -CustomAgent 'QA-AzureArchitectureReview' -DependsOn @('3') -BodyTemplatePath 'templates/abdv/step-4.1.md')
        (NewWorkflowStep -Id '4.2' -Title '整合性チェック' -CustomAgent 'QA-AzureDependencyReview' -DependsOn @('3') -BodyTemplatePath 'templates/abdv/step-4.2.md')
    )
}

# AID — IoT Design (10 steps)
$script:WorkflowRegistryData['aid'] = [PSCustomObject]@{
    id            = 'aid'
    name          = 'IoT Design'
    label_prefix  = 'aid'
    state_labels  = [PSCustomObject]@{
        initialized = 'aid:initialized'
        ready       = 'aid:ready'
        running     = 'aid:running'
        done        = 'aid:done'
        blocked     = 'aid:blocked'
    }
    params        = @()
    steps         = @(
        (NewWorkflowStep -Id '5' -Title '画面定義書 + マイクロサービス定義書（コンテナ）' -IsContainer $true)
        (NewWorkflowStep -Id '1.1' -Title 'IoT ドメイン分析' -CustomAgent 'Arch-IoT-DomainAnalytics' -BodyTemplatePath 'templates/aid/step-1.1.md')
        (NewWorkflowStep -Id '1.2' -Title 'デバイスプロファイル＋接続性分析' -CustomAgent 'Arch-IoT-DeviceConnectivity' -BodyTemplatePath 'templates/aid/step-1.2.md')
        (NewWorkflowStep -Id '2' -Title 'データモデル' -CustomAgent 'Arch-DataModeling' -DependsOn @('1.1', '1.2') -BodyTemplatePath 'templates/aid/step-2.md')
        (NewWorkflowStep -Id '3' -Title '画面一覧/構造' -CustomAgent 'Arch-UI-List' -DependsOn @('2') -SkipFallbackDeps @('2') -BodyTemplatePath 'templates/aid/step-3.md')
        (NewWorkflowStep -Id '4' -Title 'サービスカタログ' -CustomAgent 'Arch-Microservice-ServiceCatalog' -DependsOn @('3') -SkipFallbackDeps @('3') -BodyTemplatePath 'templates/aid/step-4.md')
        (NewWorkflowStep -Id '4.5' -Title 'テスト戦略書' -CustomAgent 'Arch-TDD-TestStrategy' -DependsOn @('4') -SkipFallbackDeps @('4') -BodyTemplatePath 'templates/aid/step-4.5.md')
        (NewWorkflowStep -Id '5.1' -Title '画面定義書' -CustomAgent 'Arch-UI-Detail' -DependsOn @('4.5') -SkipFallbackDeps @('4') -BodyTemplatePath 'templates/aid/step-5.1.md')
        (NewWorkflowStep -Id '5.2' -Title 'マイクロサービス定義書' -CustomAgent 'Arch-Microservice-ServiceDetail' -DependsOn @('4.5') -SkipFallbackDeps @('4') -BodyTemplatePath 'templates/aid/step-5.2.md')
        (NewWorkflowStep -Id '5.3' -Title 'TDDテスト仕様書' -CustomAgent 'Arch-TDD-TestSpec' -DependsOn @('4.5', '5.1', '5.2') -BodyTemplatePath 'templates/aid/step-5.3.md')
    )
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

function Get-Workflow {
    <#
    .SYNOPSIS
        Retrieve full workflow definition as PSCustomObject.
    .PARAMETER WorkflowId
        Workflow identifier (aas, aad, asdw, abd, abdv, aid)
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$WorkflowId
    )

    $wfId = $WorkflowId.ToLower()
    if ($script:WorkflowRegistryData.ContainsKey($wfId)) {
        return $script:WorkflowRegistryData[$wfId]
    }

    throw "Unknown workflow: $WorkflowId"
}

function Get-Step {
    <#
    .SYNOPSIS
        Retrieve a single step definition as PSCustomObject.
    .PARAMETER WorkflowId
        Workflow identifier
    .PARAMETER StepId
        Step identifier (e.g. "1.1", "7.3")
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$WorkflowId,
        [Parameter(Mandatory)][string]$StepId
    )

    $wf = Get-Workflow -WorkflowId $WorkflowId
    $step = $wf.steps | Where-Object { $_.id -eq $StepId } | Select-Object -First 1

    if (-not $step) {
        throw "Step '$StepId' not found in workflow '$WorkflowId'"
    }

    return $step
}

function Get-NextStep {
    <#
    .SYNOPSIS
        Given completed and skipped step IDs, compute the next runnable steps.
    .PARAMETER WorkflowId
        Workflow identifier
    .PARAMETER Completed
        Array of completed step IDs
    .PARAMETER Skipped
        Optional array of skipped step IDs
    .OUTPUTS
        Array of PSCustomObject step objects that are next runnable.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$WorkflowId,
        [AllowEmptyCollection()][string[]]$Completed = @(),
        [AllowEmptyCollection()][string[]]$Skipped = @()
    )

    $wf = Get-Workflow -WorkflowId $WorkflowId
    $effectiveDone = @($Completed) + @($Skipped)
    $existingIds = @($wf.steps | ForEach-Object { $_.id })

    return @($wf.steps | Where-Object {
        $step = $_
        # Must not be a container
        if ($step.is_container) { return $false }
        # Must not already be completed
        if ($step.id -in $Completed) { return $false }
        # Must not already be skipped
        if ($step.id -in $Skipped) { return $false }
        # All dependencies must be resolved
        if ($step.depends_on.Count -eq 0) { return $true }
        $allDepsResolved = $true
        foreach ($dep in $step.depends_on) {
            if ($dep -notin $effectiveDone -and $dep -in $existingIds) {
                $allDepsResolved = $false
                break
            }
        }
        return $allDepsResolved
    })
}
