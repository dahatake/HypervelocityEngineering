# orchestrate.ps1 — ワークフロー起動（Issue 一括作成 + Copilot アサイン）
#
# Ported from: .github/scripts/bash/orchestrate.sh
#
# Creates Root Issue, Sub-Issues from templates, establishes parent-child
# links, and assigns Copilot to the first executable step.
#
# Usage:
#   .\orchestrate.ps1 -Workflow aad -Branch main -Steps "1.1,1.2" -DryRun
#
# Environment:
#   REPO        — Repository in "owner/repo" format
#   GH_TOKEN    — GitHub API token
#   COPILOT_PAT — Copilot assignment PAT
#   DRY_RUN     — Set to "1" for dry-run mode

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [Alias('w')]
    [string]$Workflow,

    [string]$Branch = 'main',
    [string]$Steps = '',
    [string]$AppId = '',
    [string]$ResourceGroup = '',
    [string]$UsecaseId = '',
    [string]$BatchJobId = '',
    [string]$Comment = '',
    [switch]$SkipReview,
    [switch]$SkipQa,
    [string]$Repo = '',
    [switch]$DryRun,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$InformationPreference = 'Continue'

# Resolve script directory and source shared libraries
$ScriptDir = $PSScriptRoot
. "$ScriptDir/lib/gh-api.ps1"
. "$ScriptDir/lib/copilot-assign.ps1"
. "$ScriptDir/lib/workflow-registry.ps1"

if ($DryRun) { $env:DRY_RUN = '1' }
if (-not $Repo) { $Repo = $env:REPO }

# Templates base path: .github/scripts/templates/
$TemplatesBase = (Resolve-Path (Join-Path $ScriptDir '../templates')).Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

$script:WorkflowDisplayNames = @{
    aas  = 'App Selection'
    aad  = 'App Design'
    asdw = 'App Dev Microservice Azure'
    abd  = 'Batch Design'
    abdv = 'Batch Dev'
    aid  = 'IoT Design'
}

$script:TriggerLabels = @{
    aas  = 'auto-app-selection'
    aad  = 'auto-app-design'
    asdw = 'auto-app-dev-microservice'
    abd  = 'auto-batch-design'
    abdv = 'auto-batch-dev'
    aid  = 'auto-iot-design'
}

$script:WorkflowPrefixMap = @{
    aas  = 'AAS'
    aad  = 'AAD'
    asdw = 'ASDW'
    abd  = 'ABD'
    abdv = 'ABDV'
    aid  = 'AID'
}

# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

function script:LoadTemplate {
    param([string]$TemplatePath)
    $fullPath = Join-Path $TemplatesBase $TemplatePath
    if (-not (Test-Path $fullPath)) {
        Write-Warning "  ⚠️ テンプレートが見つかりません: $TemplatePath"
        return ''
    }
    return Get-Content $fullPath -Raw
}

function script:BuildRootRef {
    param(
        [string]$RootIssueNum,
        [string]$RefBranch = 'main',
        [string]$RefResourceGroup = '',
        [string]$RefAppId = '',
        [string]$RefBatchJobId = '',
        [string]$AutoReview = 'true',
        [string]$AutoQa = 'true'
    )

    $parts = @()
    $parts += "<!-- root-issue: #$RootIssueNum -->"
    $parts += "<!-- branch: $RefBranch -->"
    if ($RefResourceGroup) { $parts += "<!-- resource-group: $RefResourceGroup -->" }
    if ($RefAppId) { $parts += "<!-- app-id: $RefAppId -->" }
    if ($RefBatchJobId) { $parts += "<!-- batch-job-ids: $RefBatchJobId -->" }
    $parts += "<!-- auto-review: $AutoReview -->"
    $parts += "<!-- auto-context-review: true -->"
    $parts += "<!-- auto-qa: $AutoQa -->"
    return $parts -join "`n"
}

function script:BuildAdditionalSection {
    param([string]$AdditionalComment)
    if ($AdditionalComment) {
        return "`n`n## 追加コメント`n$AdditionalComment"
    }
    return ''
}

function script:BuildAppIdSection {
    param([string]$RefAppId)
    if (-not $RefAppId) { return '' }
    return "`n`n## 対象アプリケーション`n- APP-ID: ``$RefAppId```n- この Step では APP-ID ``$RefAppId`` に関連するサービス/エンティティ/画面のみを対象とする`n- ``docs/app-list.md`` を参照し、対象 APP-ID に紐づく項目を特定する`n- 共有サービス/エンティティ（複数 APP で利用されるもの）も対象に含む"
}

function script:BuildRgSection {
    param([string]$RefResourceGroup)
    if (-not $RefResourceGroup) { return '' }
    return "`n`n## リソースグループ`n``$RefResourceGroup``"
}

function script:BuildJobSection {
    param([string]$RefBatchJobId)
    if (-not $RefBatchJobId) { return '' }
    return "`n`n## 対象バッチジョブ ID`n``$RefBatchJobId``"
}

function script:RenderTemplate {
    param(
        [string]$TemplatePath,
        [string]$RootIssueNum,
        [string]$RefBranch = 'main',
        [string]$RefResourceGroup = '',
        [string]$RefAppId = '',
        [string]$RefBatchJobId = '',
        [string]$RefUsecaseId = '',
        [string]$AdditionalComment = '',
        [string]$AutoReview = 'true',
        [string]$AutoQa = 'true'
    )

    $bodyContent = LoadTemplate -TemplatePath $TemplatePath
    if (-not $bodyContent) { return '' }

    $rootRef = BuildRootRef -RootIssueNum $RootIssueNum -RefBranch $RefBranch -RefResourceGroup $RefResourceGroup -RefAppId $RefAppId -RefBatchJobId $RefBatchJobId -AutoReview $AutoReview -AutoQa $AutoQa
    $additionalSection = BuildAdditionalSection -AdditionalComment $AdditionalComment
    $appIdSection = BuildAppIdSection -RefAppId $RefAppId
    $rgSection = BuildRgSection -RefResourceGroup $RefResourceGroup
    $jobSection = BuildJobSection -RefBatchJobId $RefBatchJobId

    $bodyContent = $bodyContent -replace '\{root_ref\}', $rootRef
    $bodyContent = $bodyContent -replace '\{additional_section\}', $additionalSection
    $bodyContent = $bodyContent -replace '\{app_id_section\}', $appIdSection
    $bodyContent = $bodyContent -replace '\{resource_group\}', $RefResourceGroup
    $bodyContent = $bodyContent -replace '\{usecase_id\}', $RefUsecaseId
    $bodyContent = $bodyContent -replace '\{rg_section\}', $rgSection
    $bodyContent = $bodyContent -replace '\{job_section\}', $jobSection
    $bodyContent = $bodyContent -replace '\{s7_subtasks\}', 'Step.7.1, Step.7.2, Step.7.3'
    $bodyContent = $bodyContent -replace '\{s5_subtasks\}', 'Step.5.1, Step.5.2, Step.5.3'

    return $bodyContent
}

# ---------------------------------------------------------------------------
# Root Issue body
# ---------------------------------------------------------------------------

function script:BuildRootIssueBody {
    param(
        [string]$WorkflowId,
        [string]$RefBranch = 'main',
        [string]$RefResourceGroup = '',
        [string]$RefAppId = '',
        [string]$RefBatchJobId = '',
        [string]$RefUsecaseId = '',
        [string]$AdditionalComment = '',
        [string]$SkipReviewStr = 'false',
        [string]$SkipQaStr = 'false'
    )

    $prefix = $script:WorkflowPrefixMap[$WorkflowId]
    $displayName = $script:WorkflowDisplayNames[$WorkflowId]

    $autoReview = if ($SkipReviewStr -eq 'true') { 'false' } else { 'true' }
    $autoQa = if ($SkipQaStr -eq 'true') { 'false' } else { 'true' }

    $lines = @()
    $lines += "# [$prefix] $displayName"
    $lines += ''
    $lines += "<!-- branch: $RefBranch -->"
    if ($RefResourceGroup) { $lines += "<!-- resource-group: $RefResourceGroup -->" }
    if ($RefAppId) { $lines += "<!-- app-id: $RefAppId -->" }
    if ($RefBatchJobId) { $lines += "<!-- batch-job-ids: $RefBatchJobId -->" }
    $lines += "<!-- auto-review: $autoReview -->"
    $lines += "<!-- auto-context-review: true -->"
    $lines += "<!-- auto-qa: $autoQa -->"
    $lines += ''
    $lines += "ワークフロー: **$displayName**"
    $lines += "ブランチ: ``$RefBranch``"

    if ($RefAppId) { $lines += "APP-ID: ``$RefAppId``" }
    if ($RefResourceGroup) { $lines += "リソースグループ: ``$RefResourceGroup``" }
    if ($RefUsecaseId) { $lines += "ユースケースID: ``$RefUsecaseId``" }
    if ($RefBatchJobId) { $lines += "バッチジョブ ID: ``$RefBatchJobId``" }

    if ($AdditionalComment) {
        $lines += ''
        $lines += '## 追加コメント'
        $lines += $AdditionalComment
    }

    return $lines -join "`n"
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

function script:ShowUsage {
    Write-Information @'
Usage:
  orchestrate.ps1 -Workflow <id> [options]

Options:
  -Workflow, -w <id>     Workflow ID: aas|aad|asdw|abd|abdv|aid (required)
  -Branch <name>         Target branch (default: main)
  -Steps <csv>           Comma-separated step IDs (default: all)
  -AppId <id>            ASDW: Application ID
  -ResourceGroup <name>  ASDW/ABDV: Resource group name
  -UsecaseId <id>        ASDW: Usecase ID
  -BatchJobId <ids>      ABDV: Batch job IDs (comma-separated)
  -Comment <text>        Additional comment
  -SkipReview            Skip self-review
  -SkipQa                Skip QA questionnaire
  -Repo <owner/repo>     Repository (env: REPO)
  -DryRun                Preview without API calls
  -Help                  Show this help
'@
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if ($Help) {
    ShowUsage
    exit 0
}

$workflowId = $Workflow.ToLower()
$prefix = $script:WorkflowPrefixMap[$workflowId]
$displayName = $script:WorkflowDisplayNames[$workflowId]
$dryRunMode = ($env:DRY_RUN -eq '1')

if (-not $prefix) {
    Write-Warning "ERROR: 不明なワークフロー: $workflowId"
    exit 1
}

$wf = Get-Workflow -WorkflowId $workflowId

if (-not $Repo -and -not $dryRunMode) {
    Write-Warning 'ERROR: REPO 環境変数またはリポジトリの指定が必要です。'
    exit 1
}

$autoReview = if ($SkipReview) { 'false' } else { 'true' }
$autoQa = if ($SkipQa) { 'false' } else { 'true' }

# Parse selected steps
$selectedSteps = @()
if ($Steps) {
    $selectedSteps = @($Steps -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

# Get all step IDs from workflow
$allStepIds = @($wf.steps | ForEach-Object { $_.id })

# Determine active step IDs
$activeStepIds = @()
if ($selectedSteps.Count -eq 0) {
    $activeStepIds = $allStepIds
}
else {
    foreach ($sid in $selectedSteps) {
        if ($sid -in $allStepIds) {
            $activeStepIds += $sid
        }
        else {
            Write-Information "  ⚠️ 未知の Step ID: $sid（除外します）"
        }
    }

    if ($activeStepIds.Count -eq 0) {
        Write-Information '  ⚠️ 有効な Step ID がないため、全ステップを実行します。'
        $activeStepIds = $allStepIds
    }

    # Add parent containers for selected steps
    $containerIds = @($wf.steps | Where-Object { $_.is_container } | ForEach-Object { $_.id })
    foreach ($cid in $containerIds) {
        foreach ($sid in @($activeStepIds)) {
            $parts = $sid -split '\.'
            if ($parts.Count -gt 0 -and $parts[0] -eq $cid) {
                if ($cid -notin $activeStepIds) {
                    $activeStepIds += $cid
                }
                break
            }
        }
    }
}

# Compute skipped steps (non-container steps not in active set)
$skippedStepIds = @()
foreach ($sid in $allStepIds) {
    $step = $wf.steps | Where-Object { $_.id -eq $sid -and $_.is_container } | Select-Object -First 1
    if ($step) { continue }
    if ($sid -notin $activeStepIds) { $skippedStepIds += $sid }
}

# Display execution plan
Write-Information ''
Write-Information '============================================================'
Write-Information " 実行計画: [$prefix] $displayName"
Write-Information '============================================================'

# Count non-container and container active steps
$activeNonContainer = 0
$activeContainers = 0
foreach ($sid in $activeStepIds) {
    $step = $wf.steps | Where-Object { $_.id -eq $sid -and $_.is_container } | Select-Object -First 1
    if ($step) { $activeContainers++ } else { $activeNonContainer++ }
}

Write-Information ''
Write-Information " 作成するステップ ($activeNonContainer 個):"
foreach ($sid in $activeStepIds) {
    $step = $wf.steps | Where-Object { $_.id -eq $sid } | Select-Object -First 1
    if (-not $step -or $step.is_container) { continue }
    $agentStr = ''
    if ($step.custom_agent) { $agentStr = " [$($step.custom_agent)]" }
    Write-Information "   ✅ Step.${sid}: $($step.title)$agentStr"
}

if ($activeContainers -gt 0) {
    Write-Information ''
    Write-Information " コンテナ Issue ($activeContainers 個):"
    foreach ($sid in $activeStepIds) {
        $step = $wf.steps | Where-Object { $_.id -eq $sid -and $_.is_container } | Select-Object -First 1
        if (-not $step) { continue }
        Write-Information "   📦 Step.${sid}: $($step.title)"
    }
}

if ($skippedStepIds.Count -gt 0) {
    Write-Information ''
    Write-Information " スキップされるステップ ($($skippedStepIds.Count) 個):"
    foreach ($sid in $skippedStepIds) {
        $step = $wf.steps | Where-Object { $_.id -eq $sid } | Select-Object -First 1
        if (-not $step) { continue }
        Write-Information "   ⏭️  Step.${sid}: $($step.title)"
    }
}

if ($dryRunMode) {
    Write-Information ''
    Write-Information '🔍 ドライラン: GitHub API 呼び出しなし。計画の表示のみ。'
    Write-Information ''
    exit 0
}

# --- Live mode: Create Issues ---
Write-Information ''
Write-Information '============================================================'
Write-Information ' 実行開始'
Write-Information '============================================================'
Write-Information ''

# 1. Create labels
Write-Information '📋 ラベル作成...'
$triggerLabel = $script:TriggerLabels[$workflowId]
foreach ($lbl in @($wf.state_labels.initialized, $wf.state_labels.ready, $wf.state_labels.running, $wf.state_labels.done, $wf.state_labels.blocked)) {
    if ($lbl) { try { New-GitHubLabel -Name $lbl -Color 'ededed' -Repo $Repo -Confirm:$false } catch { Write-Debug "Suppressed: $_" } }
}
try { New-GitHubLabel -Name $triggerLabel -Color 'ededed' -Repo $Repo -Confirm:$false } catch { Write-Debug "Suppressed: $_" }
try { New-GitHubLabel -Name 'auto-context-review' -Color '1D76DB' -Repo $Repo -Confirm:$false } catch { Write-Debug "Suppressed: $_" }
try { New-GitHubLabel -Name 'auto-qa' -Color 'BFD4F2' -Repo $Repo -Confirm:$false } catch { Write-Debug "Suppressed: $_" }

# 2. Create Root Issue
Write-Information ''
Write-Information '📝 Root Issue 作成...'
$rootBody = BuildRootIssueBody -WorkflowId $workflowId -RefBranch $Branch -RefResourceGroup $ResourceGroup -RefAppId $AppId -RefBatchJobId $BatchJobId -RefUsecaseId $UsecaseId -AdditionalComment $Comment -SkipReviewStr $(if ($SkipReview) { 'true' } else { 'false' }) -SkipQaStr $(if ($SkipQa) { 'true' } else { 'false' })
$rootTitle = "[$prefix] $displayName"
$initializedLabel = $wf.state_labels.initialized
$rootLabelsJson = ConvertTo-Json @($triggerLabel, $initializedLabel) -Compress

$rootResult = New-GitHubIssue -Title $rootTitle -Body $rootBody -LabelsJson $rootLabelsJson -Repo $Repo -Confirm:$false
$rootParts = $rootResult -split '\s+'
$rootNum = $rootParts[0]
Write-Information "  ✅ Root Issue 作成: #$rootNum"

# Add auto-context-review / auto-qa labels to Root
try { Add-IssueLabel -IssueNum $rootNum -Label 'auto-context-review' -Repo $Repo } catch { Write-Debug "Suppressed: $_" }
if ($autoQa -eq 'true') {
    try { Add-IssueLabel -IssueNum $rootNum -Label 'auto-qa' -Repo $Repo } catch { Write-Debug "Suppressed: $_" }
}

# 3. Create Sub-Issues
Write-Information ''
Write-Information '📦 Sub-Issue 一括生成...'

$stepLabels = @($triggerLabel, 'auto-context-review')
if ($autoQa -eq 'true') { $stepLabels += 'auto-qa' }

$appIdSuffix = ''
if ($AppId) { $appIdSuffix = " ($AppId)" }

$createdNums = @{}   # step_id -> issue number
$createdIds = @{}    # step_id -> issue database id

foreach ($step in $wf.steps) {
    $sid = $step.id
    if ($sid -notin $activeStepIds) { continue }

    $issueTitle = "[$prefix] Step.${sid}: $($step.title)$appIdSuffix"
    $issueBody = ''

    if ($step.body_template_path) {
        $issueBody = RenderTemplate -TemplatePath $step.body_template_path -RootIssueNum $rootNum -RefBranch $Branch -RefResourceGroup $ResourceGroup -RefAppId $AppId -RefBatchJobId $BatchJobId -RefUsecaseId $UsecaseId -AdditionalComment $Comment -AutoReview $autoReview -AutoQa $autoQa
    }
    if (-not $issueBody) {
        $rootRef = BuildRootRef -RootIssueNum $rootNum -RefBranch $Branch -RefResourceGroup $ResourceGroup -RefAppId $AppId -RefBatchJobId $BatchJobId -AutoReview $autoReview -AutoQa $autoQa
        $additionalSection = BuildAdditionalSection -AdditionalComment $Comment
        $issueBody = "$rootRef`n`nStep.${sid}: $($step.title)$additionalSection"
    }

    $issueLabelsJson = ConvertTo-Json @($stepLabels) -Compress

    try {
        $result = New-GitHubIssue -Title $issueTitle -Body $issueBody -LabelsJson $issueLabelsJson -Repo $Repo -Confirm:$false
        $resultParts = $result -split '\s+'
        $num = $resultParts[0]
        $dbId = $resultParts[1]
        $createdNums[$sid] = $num
        $createdIds[$sid] = $dbId

        $marker = if ($step.is_container) { '📦' } else { '✅' }
        Write-Information "  $marker Step.${sid}: #$num ($($step.title))"

        Start-Sleep -Seconds 1
    }
    catch {
        Write-Warning "  ❌ Step.${sid}: 作成失敗"
        continue
    }
}

# 4. Link parent-child
Write-Information ''
Write-Information '🔗 親子紐付け...'

$containerIdsArr = @($wf.steps | Where-Object { $_.is_container -and $_.id -in $activeStepIds } | ForEach-Object { $_.id })

foreach ($sid in $createdIds.Keys) {
    $num = $createdNums[$sid]
    $dbId = $createdIds[$sid]
    $isContainer = $null -ne ($wf.steps | Where-Object { $_.id -eq $sid -and $_.is_container } | Select-Object -First 1)

    if ($isContainer) {
        # Container → Root child
        try {
            Add-SubIssueLink -ParentNum $rootNum -ChildId $dbId -Repo $Repo
            Write-Information "  🔗 Root #$rootNum → Step.$sid #$num"
        }
        catch {
            Write-Information "  ⚠️ 紐付け失敗: Root #$rootNum → Step.$sid #$num"
        }
    }
    else {
        # Non-container: find parent container or link to root
        $parentCid = ''
        $parts = $sid -split '\.'
        if ($parts.Count -gt 0) {
            $candidateCid = $parts[0]
            if ($candidateCid -in $containerIdsArr) {
                $parentCid = $candidateCid
            }
        }

        if ($parentCid -and $createdNums.ContainsKey($parentCid)) {
            $parentNum = $createdNums[$parentCid]
            try {
                Add-SubIssueLink -ParentNum $parentNum -ChildId $dbId -Repo $Repo
                Write-Information "  🔗 Step.$parentCid #$parentNum → Step.$sid #$num"
            }
            catch {
                Write-Information "  ⚠️ 紐付け失敗: Step.$parentCid #$parentNum → Step.$sid #$num"
            }
        }
        else {
            try {
                Add-SubIssueLink -ParentNum $rootNum -ChildId $dbId -Repo $Repo
                Write-Information "  🔗 Root #$rootNum → Step.$sid #$num"
            }
            catch {
                Write-Information "  ⚠️ 紐付け失敗: Root #$rootNum → Step.$sid #$num"
            }
        }
    }
}

# 5. Assign Copilot to first executable step
Write-Information ''
Write-Information '🤖 Copilot アサイン...'


$candidates = @(Get-NextStep -WorkflowId $workflowId -Completed @() -Skipped $skippedStepIds)

$assignedStepId = ''
foreach ($cand in $candidates) {
    $candId = $cand.id
    $candAgent = $cand.custom_agent

    if (-not $createdNums.ContainsKey($candId)) { continue }
    if (-not $candAgent) { continue }

    $candNum = $createdNums[$candId]
    Write-Information "  → Step.$candId (#$candNum, agent: $candAgent) にアサイン試行..."

    # Add ready label
    $readyLabel = $wf.state_labels.ready
    if ($readyLabel) {
        try { Add-IssueLabel -IssueNum $candNum -Label $readyLabel -Repo $Repo } catch { Write-Debug "Suppressed: $_" }
    }

    try {
        $null = Invoke-CopilotAssign -Repo $Repo -IssueNumber $candNum -CustomAgent $candAgent -BaseBranch $Branch
        Write-Information "  ✅ Step.$candId にアサイン成功"
        $runningLabel = $wf.state_labels.running
        if ($runningLabel) {
            try { Add-IssueLabel -IssueNum $candNum -Label $runningLabel -Repo $Repo } catch { Write-Debug "Suppressed: $_" }
        }
        $assignedStepId = $candId
        break
    }
    catch {
        Write-Information "  ⚠️ Step.$candId アサイン失敗。次のステップを試行..."
    }
}

if (-not $assignedStepId) {
    Write-Information '  ⚠️ アサイン可能なステップがありません。手動アサインが必要です。'
}

# 6. Post summary comment
$stepListMd = ''
foreach ($sid in $createdNums.Keys) {
    $stepListMd += "- Step.${sid}: #$($createdNums[$sid])`n"
}

$summary = @"
## ✅ ワークフロー初期化完了

**ワークフロー**: $displayName
**作成した Sub-Issue**: $($createdNums.Count) 件

$stepListMd
"@

if ($assignedStepId -and $createdNums.ContainsKey($assignedStepId)) {
    $summary += "`n**Copilot アサイン先**: Step.$assignedStepId (#$($createdNums[$assignedStepId]))"
}

try {
    Add-IssueComment -IssueNum $rootNum -Body $summary -Repo $Repo
}
catch { Write-Debug "Suppressed: $_" }

Write-Information ''
Write-Information '============================================================'
Write-Information ' ✅ 完了'
Write-Information "   Root Issue: #$rootNum"
Write-Information "   Sub-Issue: $($createdNums.Count) 件作成"
if ($assignedStepId) { Write-Information "   Copilot アサイン: Step.$assignedStepId" }
Write-Information '============================================================'
Write-Information ''
