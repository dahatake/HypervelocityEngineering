# advance.ps1 — 完了 Issue → 次ステップ起動
#
# Ported from: .github/scripts/bash/advance.sh
#
# Marks a completed issue as done, collects completed/skipped steps,
# determines next steps via workflow DAG, and activates them.
#
# Usage:
#   .\advance.ps1 -Issue 123 -DryRun
#   .\advance.ps1 -Issue 123 -Repo owner/repo
#
# Environment:
#   REPO        — Repository in "owner/repo" format
#   GH_TOKEN    — GitHub API token
#   COPILOT_PAT — Copilot assignment PAT
#   DRY_RUN     — Set to "1" for dry-run mode

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Issue,

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
. "$ScriptDir/lib/issue-parser.ps1"
. "$ScriptDir/lib/workflow-registry.ps1"

if ($DryRun) { $env:DRY_RUN = '1' }
if (-not $Repo) { $Repo = $env:REPO }

# ---------------------------------------------------------------------------
# Title parsing — extract workflow ID and step ID
# ---------------------------------------------------------------------------

function script:ExtractStepIdFromTitle {
    param([string]$Title)
    if ($Title -match '\[[A-Z]+\]\s*Step\.(\d+(?:\.\d+(?:[A-Za-z]*)?))') {
        return $Matches[1]
    }
    return ''
}

function script:DetectWorkflowId {
    param([string]$Title)
    if ($Title -match '\[([A-Z]+)\]\s*Step\.') {
        return $Matches[1].ToLower()
    }
    return ''
}

# ---------------------------------------------------------------------------
# activate_issue — Add labels and assign Copilot
# ---------------------------------------------------------------------------

function script:ActivateIssue {
    param(
        [string]$IssueNum,
        [string]$WorkflowId,
        [string]$Branch = 'main',
        [string]$IssueRepo
    )

    $wf = Get-Workflow -WorkflowId $WorkflowId

    $readyLabel = $wf.state_labels.ready
    $runningLabel = $wf.state_labels.running

    # Add ready label
    if ($readyLabel) {
        try { Add-IssueLabel -IssueNum $IssueNum -Label $readyLabel -Repo $IssueRepo } catch { Write-Debug "Suppressed: $_" }
    }

    # Get issue body and extract custom agent
    $customAgent = ''
    try {
        $issueData = Get-GitHubIssue -IssueNum $IssueNum -Repo $IssueRepo
        if ($issueData) {
            $customAgent = Get-CustomAgent -Body $issueData.body
        }
    }
    catch {
        Write-Debug "Failed to get issue body: $_"
    }

    # Assign Copilot
    try {
        $null = Invoke-CopilotAssign -Repo $IssueRepo -IssueNumber $IssueNum -CustomAgent $customAgent -BaseBranch $Branch
    }
    catch {
        Write-Debug "Copilot assign failed: $_"
    }

    # Add running label
    if ($runningLabel) {
        try { Add-IssueLabel -IssueNum $IssueNum -Label $runningLabel -Repo $IssueRepo } catch { Write-Debug "Suppressed: $_" }
    }
}

# ---------------------------------------------------------------------------
# Fetch all sub-issues (2-level hierarchy)
# ---------------------------------------------------------------------------

function script:FetchAllSubIssues {
    param(
        [string]$RootIssue,
        [string]$Prefix,
        [string]$IssueRepo
    )

    # Get container step IDs
    $wfId = $Prefix.ToLower()
    $containerIds = @()
    try {
        $wf = Get-Workflow -WorkflowId $wfId
        $containerIds = @($wf.steps | Where-Object { $_.is_container } | ForEach-Object { $_.id })
    }
    catch { Write-Debug "Suppressed: $_" }

    $allSubs = @()
    $page = 1
    $perPage = 100

    while ($true) {
        try {
            $pageJson = gh api "/repos/$IssueRepo/issues/$RootIssue/sub_issues?per_page=$perPage&page=$page" `
                --header 'Accept: application/vnd.github+json' 2>&1
            if ($LASTEXITCODE -ne 0) { break }
            $pageData = ($pageJson -join "`n") | ConvertFrom-Json
        }
        catch { break }

        $count = @($pageData).Count
        $allSubs += @($pageData)

        # For each sub-issue, check if it's a container and fetch children
        foreach ($sub in $pageData) {
            $subTitle = if ($sub.title) { $sub.title } else { '' }
            $subNum = $sub.number
            if (-not $subNum) { continue }

            # Extract step ID from title
            $subStepId = ''
            if ($subTitle -match "\[$Prefix\]\s*Step\.(\d+(?:\.\d+(?:[A-Za-z]*)?)?)") {
                $subStepId = $Matches[1]
            }
            if (-not $subStepId) { continue }
            if ($subStepId -notin $containerIds) { continue }

            # Fetch children of container
            $childPage = 1
            while ($true) {
                try {
                    $childJson = gh api "/repos/$IssueRepo/issues/$subNum/sub_issues?per_page=100&page=$childPage" `
                        --header 'Accept: application/vnd.github+json' 2>&1
                    if ($LASTEXITCODE -ne 0) { break }
                    $childData = ($childJson -join "`n") | ConvertFrom-Json
                    $childCount = @($childData).Count
                    if ($childCount -gt 0) { $allSubs += @($childData) }
                    if ($childCount -lt 100) { break }
                    $childPage++
                }
                catch { break }
            }
        }

        if ($count -lt $perPage) { break }
        $page++
    }

    return $allSubs
}

function script:CollectCompletedStepIds {
    param(
        [string]$RootIssue,
        [string]$WorkflowId,
        [string]$IssueRepo,
        [object[]]$CachedSubs = @()
    )

    $prefix = $WorkflowId.ToUpper()
    $subs = if ($CachedSubs.Count -gt 0) { $CachedSubs } else { FetchAllSubIssues -RootIssue $RootIssue -Prefix $prefix -IssueRepo $IssueRepo }

    $completed = @()
    foreach ($sub in $subs) {
        if ($sub.state -ne 'closed') { continue }
        $title = if ($sub.title) { $sub.title } else { '' }
        if ($title -match "\[$prefix\]\s*Step\.(\d+(?:\.\d+(?:[A-Za-z]*)?)?)") {
            $stepId = $Matches[1]
            if ($stepId -notin $completed) { $completed += $stepId }
        }
    }
    return $completed
}

function script:CollectSkippedStepIds {
    param(
        [string]$RootIssue,
        [string]$WorkflowId,
        [string]$IssueRepo,
        [object[]]$CachedSubs = @()
    )

    $prefix = $WorkflowId.ToUpper()
    $subs = if ($CachedSubs.Count -gt 0) { $CachedSubs } else { FetchAllSubIssues -RootIssue $RootIssue -Prefix $prefix -IssueRepo $IssueRepo }

    # Get all step IDs that have Sub-Issues created
    $createdStepIds = @()
    foreach ($sub in $subs) {
        $title = if ($sub.title) { $sub.title } else { '' }
        if ($title -match "\[$prefix\]\s*Step\.(\d+(?:\.\d+(?:[A-Za-z]*)?)?)") {
            $stepId = $Matches[1]
            if ($stepId -notin $createdStepIds) { $createdStepIds += $stepId }
        }
    }

    # Get all non-container step IDs from workflow
    $wf = Get-Workflow -WorkflowId $WorkflowId
    $allStepIds = @($wf.steps | Where-Object { -not $_.is_container } | ForEach-Object { $_.id })

    # Skipped = all steps - created steps
    $skipped = @()
    foreach ($sid in $allStepIds) {
        if ($sid -notin $createdStepIds) { $skipped += $sid }
    }
    return $skipped
}

function script:FindStepIssueNumber {
    param(
        [string]$StepId,
        [string]$WorkflowId,
        [string]$RootIssue,
        [string]$IssueRepo,
        [object[]]$CachedSubs = @()
    )

    $prefix = $WorkflowId.ToUpper()
    $subs = if ($CachedSubs.Count -gt 0) { $CachedSubs } else { FetchAllSubIssues -RootIssue $RootIssue -Prefix $prefix -IssueRepo $IssueRepo }

    $escapedSid = [regex]::Escape($StepId)
    foreach ($sub in $subs) {
        $title = if ($sub.title) { $sub.title } else { '' }
        if ($title -match "\[$prefix\]\s*Step\.$escapedSid([^0-9]|$)") {
            return "$($sub.number)"
        }
    }
    return ''
}

# ---------------------------------------------------------------------------
# Propagate PR labels (auto-context-review / auto-qa)
# ---------------------------------------------------------------------------

function script:PropagatePrLabels {
    param([string]$IssueNum, [string]$Body, [string]$IssueRepo)

    try {
        $timelineJson = gh api "/repos/$IssueRepo/issues/$IssueNum/timeline?per_page=100" `
            --header 'Accept: application/vnd.github+json' 2>&1
        if ($LASTEXITCODE -ne 0) { return }
        $timeline = ($timelineJson -join "`n") | ConvertFrom-Json
    }
    catch { return }

    $prNumbers = @()
    foreach ($ev in $timeline) {
        if ($ev.event -eq 'cross-referenced' -and
            $null -ne $ev.source.issue.pull_request -and
            $ev.source.issue.state -eq 'open') {
            $prNumbers += $ev.source.issue.number
        }
    }
    $prNumbers = $prNumbers | Select-Object -Unique

    $autoReview = Get-IssueMetadatum -Body $Body -Key 'auto-context-review'
    $autoQa = Get-IssueMetadatum -Body $Body -Key 'auto-qa'

    foreach ($prNum in $prNumbers) {
        if ($autoReview -eq 'true') {
            try { Add-IssueLabel -IssueNum "$prNum" -Label 'auto-context-review' -Repo $IssueRepo } catch { Write-Debug "Suppressed: $_" }
        }
        if ($autoQa -eq 'true') {
            try { Add-IssueLabel -IssueNum "$prNum" -Label 'auto-qa' -Repo $IssueRepo } catch { Write-Debug "Suppressed: $_" }
        }
    }
}

# ---------------------------------------------------------------------------
# Mark container done
# ---------------------------------------------------------------------------

function script:MarkContainerDone {
    param(
        [string]$StepId,
        [string]$WorkflowId,
        [string]$RootIssue,
        [string]$IssueRepo,
        [string[]]$CompletedIds,
        [string[]]$SkippedIds
    )

    $wf = Get-Workflow -WorkflowId $WorkflowId
    $doneLabel = $wf.state_labels.done

    # Find parent container for this step
    $parts = $StepId -split '\.'
    if ($parts.Count -eq 0) { return }
    $prefix2 = $parts[0]
    $containerStep = $wf.steps | Where-Object { $_.id -eq $prefix2 -and $_.is_container } | Select-Object -First 1
    if (-not $containerStep) { return }

    $containerId = $containerStep.id

    # Check if all child steps of container are completed or skipped
    $allChildIds = @($wf.steps | Where-Object {
        -not $_.is_container -and $_.id.StartsWith("$containerId.")
    } | ForEach-Object { $_.id })

    $effectiveDone = @($CompletedIds) + @($SkippedIds)
    $allDone = $true
    foreach ($childId in $allChildIds) {
        if ($childId -notin $effectiveDone) {
            $allDone = $false
            break
        }
    }

    if ($allDone -and $doneLabel) {
        $wfPrefix = $WorkflowId.ToUpper()
        $cachedSubs = @(FetchAllSubIssues -RootIssue $RootIssue -Prefix $wfPrefix -IssueRepo $IssueRepo)
        $containerIssueNum = FindStepIssueNumber -StepId $containerId -WorkflowId $WorkflowId -RootIssue $RootIssue -IssueRepo $IssueRepo -CachedSubs $cachedSubs
        if ($containerIssueNum) {
            try { Add-IssueLabel -IssueNum $containerIssueNum -Label $doneLabel -Repo $IssueRepo } catch { Write-Debug "Suppressed: $_" }
            Write-Information "  コンテナ Step.$containerId (#$containerIssueNum) に $doneLabel ラベルを付与しました。"
        }
    }
}

# ---------------------------------------------------------------------------
# Mark workflow done
# ---------------------------------------------------------------------------

function script:MarkWorkflowDone {
    param(
        [string]$WorkflowId,
        [string]$RootIssue,
        [string]$IssueRepo
    )

    $wf = Get-Workflow -WorkflowId $WorkflowId
    $doneLabel = $wf.state_labels.done

    if ($doneLabel) {
        try { Add-IssueLabel -IssueNum $RootIssue -Label $doneLabel -Repo $IssueRepo } catch { Write-Debug "Suppressed: $_" }
        Write-Information "  ワークフロー完了: Root Issue #$RootIssue に $doneLabel ラベルを付与しました。"
    }

    $wfName = $wf.name
    try {
        Add-IssueComment -IssueNum $RootIssue -Body "## ✅ ワークフロー完了`n`n**$wfName** のすべてのステップが完了しました。" -Repo $IssueRepo
    }
    catch { Write-Debug "Suppressed: $_" }
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

function script:ShowUsage {
    Write-Information @'
Usage:
  advance.ps1 -Issue <number> [-Repo <owner/repo>] [-DryRun]

Options:
  -Issue <number>     Completed issue number (required)
  -Repo <owner/repo>  Repository (env: REPO)
  -DryRun             Preview without API calls
  -Help               Show this help
'@
}

# ---------------------------------------------------------------------------
# Main advance function
# ---------------------------------------------------------------------------

if ($Help) {
    ShowUsage
    exit 0
}

$dryRunMode = ($env:DRY_RUN -eq '1')

Write-Information "=== advance: Issue #$Issue ==="
if ($dryRunMode) {
    Write-Information '🔍 ドライラン: 書き込み API 呼び出しなし。次ステップの特定・表示のみ。'
}

# 1. Fetch issue
$issueData = $null
try {
    $issueData = Get-GitHubIssue -IssueNum $Issue -Repo $Repo
}
catch {
    Write-Warning "ERROR: Issue #$Issue の取得に失敗"
    exit 1
}

$title = $issueData.title
$body = $issueData.body
$labels = $issueData.labels

Write-Information "  タイトル: $title"

# 2. Extract step ID and workflow ID
$stepId = ExtractStepIdFromTitle -Title $title
$workflowId = DetectWorkflowId -Title $title

if (-not $stepId) {
    Write-Warning "ERROR: Step 番号が特定できません（title: $title）"
    exit 1
}
if (-not $workflowId) {
    Write-Warning "ERROR: ワークフロー ID が特定できません（title: $title）"
    exit 1
}

$wf = Get-Workflow -WorkflowId $workflowId

Write-Information "  ワークフロー: $($workflowId.ToUpper()), Step: $stepId"

# 3. Extract root issue and branch
$rootIssueRaw = Get-IssueMetadatum -Body $body -Key 'root-issue'
if (-not $rootIssueRaw) {
    Write-Warning 'ERROR: Root Issue 番号が取得できません。スキップ。'
    exit 1
}
$rootIssueNum = $rootIssueRaw -replace '#', '' -replace '\s', ''
$branch = Get-IssueMetadatum -Body $body -Key 'branch'
if (-not $branch) { $branch = 'main' }

Write-Information "  Root Issue: #$rootIssueNum"
Write-Information "  ブランチ: $branch"

# 4. Add done label
$doneLabel = $wf.state_labels.done
if ($doneLabel) {
    $hasLabel = $labels -contains $doneLabel
    if (-not $hasLabel) {
        if ($dryRunMode) {
            Write-Information "  [dry-run] $doneLabel ラベルを付与します（スキップ）。"
        }
        else {
            try { Add-IssueLabel -IssueNum $Issue -Label $doneLabel -Repo $Repo } catch { Write-Debug "Suppressed: $_" }
            Write-Information "  $doneLabel ラベルを付与しました。"
        }
    }
}

# 5. PR label propagation
if (-not $dryRunMode) {
    PropagatePrLabels -IssueNum $Issue -Body $body -IssueRepo $Repo
}

# 6. Collect completed / skipped steps
$completedIds = @()
$skippedIds = @()
$cachedSubs = @()

if ($dryRunMode) {
    $completedIds = @($stepId)
}
else {
    $wfPrefix = $workflowId.ToUpper()
    $cachedSubs = @(FetchAllSubIssues -RootIssue $rootIssueNum -Prefix $wfPrefix -IssueRepo $Repo)

    $completedIds = @(CollectCompletedStepIds -RootIssue $rootIssueNum -WorkflowId $workflowId -IssueRepo $Repo -CachedSubs $cachedSubs)

    # Ensure current step is in completed
    if ($stepId -notin $completedIds) { $completedIds += $stepId }

    $skippedIds = @(CollectSkippedStepIds -RootIssue $rootIssueNum -WorkflowId $workflowId -IssueRepo $Repo -CachedSubs $cachedSubs)

    # Remove completed from skipped
    $skippedIds = @($skippedIds | Where-Object { $_ -notin $completedIds })
}

Write-Information "  完了済みステップ: [$($completedIds -join ', ')]"
Write-Information "  スキップ済みステップ: [$($skippedIds -join ', ')]"

# 7. Mark container done
if (-not $dryRunMode) {
    MarkContainerDone -StepId $stepId -WorkflowId $workflowId -RootIssue $rootIssueNum -IssueRepo $Repo -CompletedIds $completedIds -SkippedIds $skippedIds
}

# 8. Get next steps
$nextSteps = @(Get-NextStep -WorkflowId $workflowId -Completed $completedIds -Skipped $skippedIds)

# Filter blocked steps (block_unless check)
$blockedLabel = $wf.state_labels.blocked

$activatable = @()
foreach ($ns in $nextSteps) {
    $blockUnless = $ns.block_unless
    if ($blockUnless -and $blockUnless.Count -gt 0) {
        $unmet = @($blockUnless | Where-Object { $_ -notin $completedIds })
        if ($unmet.Count -gt 0) {
            Write-Information "  Step.$($ns.id): block_unless 条件未達 (未完了: [$($unmet -join ', ')])。blocked 状態にします。"
            if (-not $dryRunMode -and $blockedLabel) {
                $stepIssue = FindStepIssueNumber -StepId $ns.id -WorkflowId $workflowId -RootIssue $rootIssueNum -IssueRepo $Repo -CachedSubs $cachedSubs
                if ($stepIssue) {
                    try { Add-IssueLabel -IssueNum $stepIssue -Label $blockedLabel -Repo $Repo } catch { Write-Debug "Suppressed: $_" }
                }
            }
            continue
        }
    }
    $activatable += $ns
}

if ($activatable.Count -eq 0) {
    Write-Information '  次のステップはありません。ワークフロー完了を確認します...'

    # Check if all non-container steps done or skipped
    $allNcIds = @($wf.steps | Where-Object { -not $_.is_container } | ForEach-Object { $_.id })
    $effectiveDone = @($completedIds) + @($skippedIds)
    $allDone = $true
    foreach ($ncId in $allNcIds) {
        if ($ncId -notin $effectiveDone) {
            $allDone = $false
            break
        }
    }

    if ($allDone) {
        if ($dryRunMode) {
            Write-Information '  [dry-run] ワークフロー完了ラベルを付与します（スキップ）。'
        }
        else {
            MarkWorkflowDone -WorkflowId $workflowId -RootIssue $rootIssueNum -IssueRepo $Repo
        }
    }
    else {
        Write-Information '  まだ未完了のステップがあります（依存関係未解決）。'
    }
    exit 0
}

# Display next steps
$nextIds = @($activatable | ForEach-Object { $_.id })
Write-Information "  次のステップ: [$($nextIds -join ', ')]"

if ($dryRunMode) {
    foreach ($ns in $activatable) {
        $agentStr = ''
        if ($ns.custom_agent) { $agentStr = " [$($ns.custom_agent)]" }
        Write-Information "  [dry-run] Step.$($ns.id): $($ns.title)$agentStr を起動予定"
    }
    Write-Information ''
    Write-Information "🔍 ドライラン完了: $($activatable.Count) 件のステップを起動予定"
    Write-Information ''
    exit 0
}

# 9. Activate next steps
$activated = 0
foreach ($ns in $activatable) {
    $stepIssueNum = FindStepIssueNumber -StepId $ns.id -WorkflowId $workflowId -RootIssue $rootIssueNum -IssueRepo $Repo -CachedSubs $cachedSubs

    if ($stepIssueNum) {
        Write-Information "  Step.$($ns.id) → Issue #$stepIssueNum を起動..."
        try {
            ActivateIssue -IssueNum $stepIssueNum -WorkflowId $workflowId -Branch $branch -IssueRepo $Repo
            $activated++
        }
        catch {
            Write-Debug "Activation failed for Step.$($ns.id): $_"
        }
    }
    else {
        Write-Information "  Step.$($ns.id) の Issue が見つかりません（スキップ済み？）"
    }
}

Write-Information "=== advance 完了: $activated 件のステップを起動 ==="
