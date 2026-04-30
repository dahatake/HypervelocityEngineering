# workflow-registry.ps1 — ワークフロー定義レジストリ
#
# Migrated from:
#   - .github/scripts/bash/lib/workflow-registry.sh
#   - .github/cli/lib/workflow_registry.py
#
# 5 workflows (AAS/AAD/ASDW/ABD/ABDV) with step DAG definitions stored
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

# AAS — App Architecture Design (2 steps)
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
        (NewWorkflowStep -Id '1.1' -Title 'データサービス選定' -CustomAgent 'Dev-Batch-DataServiceSelect' -BodyTemplatePath 'templates/abdv/step-1.1.md')
        (NewWorkflowStep -Id '1.2' -Title 'Azure データリソース Deploy' -CustomAgent 'Dev-Batch-DataDeploy' -DependsOn @('1.1') -BodyTemplatePath 'templates/abdv/step-1.2.md')
        (NewWorkflowStep -Id '2.1' -Title 'TDD RED — テストコード作成' -CustomAgent 'Dev-Batch-TestCoding' -DependsOn @('1.2') -BodyTemplatePath 'templates/abdv/step-2.1.md')
        (NewWorkflowStep -Id '2.2' -Title 'TDD GREEN — バッチジョブ本実装' -CustomAgent 'Dev-Batch-ServiceCoding' -DependsOn @('2.1') -BodyTemplatePath 'templates/abdv/step-2.2.md')
        (NewWorkflowStep -Id '3' -Title 'Azure Functions/コンテナ Deploy' -CustomAgent 'Dev-Batch-FunctionsDeploy' -DependsOn @('2.2') -BodyTemplatePath 'templates/abdv/step-3.md')
        (NewWorkflowStep -Id '4.1' -Title 'WAF レビュー' -CustomAgent 'QA-AzureArchitectureReview' -DependsOn @('3') -BodyTemplatePath 'templates/abdv/step-4.1.md')
        (NewWorkflowStep -Id '4.2' -Title '整合性チェック' -CustomAgent 'QA-AzureDependencyReview' -DependsOn @('3') -BodyTemplatePath 'templates/abdv/step-4.2.md')
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
        Workflow identifier (aas, aad, asdw, abd, abdv)
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
