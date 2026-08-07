# workflow-registry.ps1 — ワークフロー定義レジストリ
#
# Migrated from:
#   - .github/scripts/bash/lib/workflow-registry.sh
#   - .github/cli/lib/workflow_registry.py
#
# 5 workflows (AAS/AAD/ASDW/ADFD/ADFDV) with step DAG definitions stored
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

# AAS — App Architecture Design (11 steps)
$script:WorkflowRegistryData['aas'] = [PSCustomObject]@{
    id            = 'aas'
    name          = 'App Architecture Design'
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
        (NewWorkflowStep -Id '3.1' -Title 'ドメイン分析' -CustomAgent 'Arch-Microservice-DomainAnalytics' -DependsOn @('2') -BodyTemplatePath 'templates/aas/step-3.1.md')
        (NewWorkflowStep -Id '3.2' -Title 'サービス一覧抽出' -CustomAgent 'Arch-Microservice-ServiceIdentify' -DependsOn @('3.1') -BodyTemplatePath 'templates/aas/step-3.2.md')
        (NewWorkflowStep -Id '4.1' -Title 'データモデル設計' -CustomAgent 'Arch-DataModeling' -DependsOn @('3.2') -BodyTemplatePath 'templates/aas/step-4.1.md')
        (NewWorkflowStep -Id '4.2' -Title 'サンプルデータ生成' -CustomAgent 'Arch-DataModeling' -DependsOn @('4.1') -BodyTemplatePath 'templates/aas/step-4.2.md')
        (NewWorkflowStep -Id '5' -Title 'データカタログ作成' -CustomAgent 'Arch-DataCatalog' -DependsOn @('4.1') -SkipFallbackDeps @('4.1') -BodyTemplatePath 'templates/aas/step-5.md')
        (NewWorkflowStep -Id '6' -Title 'サービスカタログ' -CustomAgent 'Arch-Microservice-ServiceCatalog' -DependsOn @('5') -SkipFallbackDeps @('5') -BodyTemplatePath 'templates/aas/step-6.md')
        (NewWorkflowStep -Id '7' -Title 'テスト戦略書' -CustomAgent 'Arch-TDD-TestStrategy' -DependsOn @('6') -SkipFallbackDeps @('6') -BodyTemplatePath 'templates/aas/step-7.md')
        (NewWorkflowStep -Id '8' -Title 'ペルソナカタログ' -CustomAgent 'Arch-PersonaCatalog' -DependsOn @('7') -SkipFallbackDeps @('7') -BodyTemplatePath 'templates/aas/step-8.md')
        (NewWorkflowStep -Id '9' -Title 'ペルソナ別共通画面カタログ' -CustomAgent 'Arch-UI-PersonaScreenList' -DependsOn @('8') -SkipFallbackDeps @('8') -BodyTemplatePath 'templates/aas/step-9.md')
    )
}

# ADFD — Dataflow Design (3 steps)
$script:WorkflowRegistryData['adfd'] = [PSCustomObject]@{
    id            = 'adfd'
    name          = 'Dataflow Design'
    label_prefix  = 'adfd'
    state_labels  = [PSCustomObject]@{
        initialized = 'adfd:initialized'
        ready       = 'adfd:ready'
        running     = 'adfd:running'
        done        = 'adfd:done'
        blocked     = 'adfd:blocked'
    }
    params        = @()
    steps         = @(
        (NewWorkflowStep -Id '1' -Title 'ジョブ詳細仕様書' -CustomAgent 'Arch-Dataflow-AppSpec' -BodyTemplatePath 'templates/adfd/step-1.md')
        (NewWorkflowStep -Id '2' -Title '監視・運用設計書' -CustomAgent 'Arch-Dataflow-MonitoringDesign' -BodyTemplatePath 'templates/adfd/step-2.md')
        (NewWorkflowStep -Id '3' -Title 'TDDテスト仕様書' -CustomAgent 'Arch-Dataflow-TDD-TestSpec' -DependsOn @('1', '2') -BodyTemplatePath 'templates/adfd/step-3.md')
    )
}

# ADFDV — Dataflow Dev (7 steps)
$script:WorkflowRegistryData['adfdv'] = [PSCustomObject]@{
    id            = 'adfdv'
    name          = 'Dataflow Dev'
    label_prefix  = 'adfdv'
    state_labels  = [PSCustomObject]@{
        initialized = 'adfdv:initialized'
        ready       = 'adfdv:ready'
        running     = 'adfdv:running'
        done        = 'adfdv:done'
        blocked     = 'adfdv:blocked'
    }
    params        = @('resource_group', 'app_id')
    steps         = @(
        (NewWorkflowStep -Id '1.1' -Title 'データサービス選定' -CustomAgent 'Dev-Dataflow-DataServiceSelect' -BodyTemplatePath 'templates/adfdv/step-1.1.md')
        (NewWorkflowStep -Id '1.2' -Title 'Azure データリソース Deploy' -CustomAgent 'Dev-Dataflow-DataDeploy' -DependsOn @('1.1') -BodyTemplatePath 'templates/adfdv/step-1.2.md')
        (NewWorkflowStep -Id '2.1' -Title 'TDD RED — テストコード作成' -CustomAgent 'Dev-Dataflow-TestCoding' -DependsOn @('1.2') -BodyTemplatePath 'templates/adfdv/step-2.1.md')
        (NewWorkflowStep -Id '2.2' -Title 'TDD GREEN — データフローアプリ本実装' -CustomAgent 'Dev-Dataflow-ServiceCoding' -DependsOn @('2.1') -BodyTemplatePath 'templates/adfdv/step-2.2.md')
        (NewWorkflowStep -Id '3' -Title 'Azure Functions/コンテナ Deploy' -CustomAgent 'Dev-Dataflow-FunctionsDeploy' -DependsOn @('2.2') -BodyTemplatePath 'templates/adfdv/step-3.md')
        (NewWorkflowStep -Id '4.1' -Title 'WAF レビュー' -CustomAgent 'QA-AzureArchitectureReview' -DependsOn @('3') -BodyTemplatePath 'templates/adfdv/step-4.1.md')
        (NewWorkflowStep -Id '4.2' -Title '整合性チェック' -CustomAgent 'QA-AzureDependencyReview' -DependsOn @('3') -BodyTemplatePath 'templates/adfdv/step-4.2.md')
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
        Workflow identifier (aas, aad, asdw, adfd, adfdv)
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
