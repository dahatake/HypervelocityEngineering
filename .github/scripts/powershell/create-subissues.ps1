# create-subissues.ps1 — subissues.md パース → Sub Issue 一括作成
#
# Ported from: .github/scripts/bash/create-subissues.sh
#
# Parses a subissues.md file on <!-- subissue --> markers, extracts metadata
# (title, labels, custom_agent, depends_on), creates GitHub Issues, links
# them to a parent, and assigns Copilot to root nodes.
#
# Usage:
#   .\create-subissues.ps1 -File work/subissues.md -ParentIssue 100 -DryRun
#
# Environment:
#   REPO        — Repository in "owner/repo" format
#   GH_TOKEN    — GitHub API token
#   COPILOT_PAT — Copilot assignment PAT
#   DRY_RUN     — Set to "1" for dry-run mode

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string]$File,

    [string]$ParentIssue = '',
    [string]$PrNumber = '',
    [string]$BaseBranch = 'main',
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

if ($DryRun) { $env:DRY_RUN = '1' }

# ---------------------------------------------------------------------------
# Metadata extraction from subissue block text
# ---------------------------------------------------------------------------

function script:ExtractComment {
    param([string]$Key, [string]$Text)
    $escaped = [regex]::Escape($Key)
    if ($Text -match "<!--\s*$escaped\s*:\s*(.+?)\s*-->") {
        return $Matches[1].Trim()
    }
    return ''
}

# ---------------------------------------------------------------------------
# Parse subissues.md into block arrays
# ---------------------------------------------------------------------------

function script:ParseSubissues {
    param([string]$FilePath)

    $lines = Get-Content $FilePath
    $knownMetaPattern = '^\s*<!--\s*(title|labels|custom_agent|depends_on)\s*:'

    $blocks = @()
    $inBlock = $false
    $currentLines = @()

    foreach ($line in $lines) {
        if ($line -match '<!--\s*subissue\s*-->') {
            # Process previous block
            if ($inBlock -and $currentLines.Count -gt 0) {
                $blocks += , (ProcessBlock -Lines $currentLines -KnownMetaPattern $knownMetaPattern)
            }
            $inBlock = $true
            $currentLines = @()
            continue
        }
        if ($inBlock) {
            $currentLines += $line
        }
    }

    # Process last block
    if ($inBlock -and $currentLines.Count -gt 0) {
        $blocks += , (ProcessBlock -Lines $currentLines -KnownMetaPattern $knownMetaPattern)
    }

    return $blocks
}

function script:ProcessBlock {
    param([string[]]$Lines, [string]$KnownMetaPattern)

    $rawBlock = $Lines -join "`n"
    $rawBlock = $rawBlock.Trim()

    if (-not $rawBlock) { return $null }

    $title = ExtractComment -Key 'title' -Text $rawBlock
    $labelsRaw = ExtractComment -Key 'labels' -Text $rawBlock
    $customAgent = ExtractComment -Key 'custom_agent' -Text $rawBlock
    $dependsRaw = ExtractComment -Key 'depends_on' -Text $rawBlock

    # Build body: strip known metadata comments
    $bodyLines = @()
    foreach ($line in $Lines) {
        if ($line -match $KnownMetaPattern) { continue }
        $bodyLines += $line
    }
    $body = ($bodyLines -join "`n").Trim()
    # Remove leading/trailing --- separators
    $body = $body -replace '^\s*---\s*', ''
    $body = $body -replace '\s*---\s*$', ''
    $body = $body.Trim()

    return [PSCustomObject]@{
        Title       = $title
        Labels      = $labelsRaw
        CustomAgent = $customAgent
        DependsOn   = $dependsRaw
        Body        = $body
    }
}

# ---------------------------------------------------------------------------
# Dry-run report
# ---------------------------------------------------------------------------

function script:DryRunReport {
    param(
        [object[]]$Blocks,
        [string]$ParentNum
    )

    Write-Information ''
    Write-Information '=== Dry-Run Report ==='
    if ($ParentNum -and $ParentNum -ne '0') {
        Write-Information "Parent issue: #$ParentNum"
    }
    else {
        Write-Information 'No parent issue'
    }
    Write-Information "Total blocks: $($Blocks.Count)"
    Write-Information ''

    $rootNodes = @()
    $depNodes = @()

    for ($i = 0; $i -lt $Blocks.Count; $i++) {
        $block = $Blocks[$i]
        $blockNum = $i + 1
        $title = if ($block.Title) { $block.Title } else { '(no title)' }
        $agent = if ($block.CustomAgent) { $block.CustomAgent } else { [char]0x2014 }
        $labels = if ($block.Labels) { $block.Labels } else { [char]0x2014 }
        $deps = $block.DependsOn

        Write-Information "Block ${blockNum}: $title"
        Write-Information "  Agent: $agent"
        Write-Information "  Labels: $labels"

        if ($deps) {
            $depArr = @($deps -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
            $depDisplay = $depArr -join ', '
            Write-Information "  Depends on: [$depDisplay]"
            $depNodes += $blockNum
        }
        else {
            if ($block.CustomAgent) {
                Write-Information '  Root node — will auto-assign Copilot'
            }
            else {
                Write-Information '  Root node — no custom_agent, Copilot will not be auto-assigned'
            }
            $rootNodes += $blockNum
        }
        Write-Information ''
    }

    $rootDisplay = $rootNodes -join ', '
    $depDisplay = $depNodes -join ', '
    Write-Information "Root nodes (auto-assign): [$rootDisplay]"
    Write-Information "Dependent nodes (wait): [$depDisplay]"
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

function script:ShowUsage {
    Write-Information @'
Usage:
  create-subissues.ps1 -File <path> [-ParentIssue <num>] [-PrNumber <num>]
                       [-BaseBranch <branch>] [-Repo <owner/repo>] [-DryRun]

Options:
  -File <path>          Path to subissues.md file (required)
  -ParentIssue <num>    Explicit parent issue number
  -PrNumber <num>       PR number (for parent detection / summary comment)
  -BaseBranch <branch>  Base branch for Copilot assignment (default: main)
  -Repo <owner/repo>    Repository (env: REPO)
  -DryRun               Preview without creating issues
  -Help                 Show this help
'@
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if ($Help) {
    ShowUsage
    exit 0
}

if (-not $Repo) { $Repo = $env:REPO }

if (-not (Test-Path $File)) {
    Write-Warning "Error: $File not found"
    exit 1
}

# Parse the subissues.md
$blocks = @(ParseSubissues -FilePath $File)
# Filter out null blocks
$blocks = @($blocks | Where-Object { $null -ne $_ })

if ($blocks.Count -eq 0) {
    Write-Information "No <!-- subissue --> blocks found in $File"
    exit 0
}

Write-Information "Found $($blocks.Count) sub-issue block(s) in $File"

# Detect parent issue if not explicitly provided
if (-not $ParentIssue -and $PrNumber -and $Repo) {
    try {
        $ParentIssue = Find-ParentIssue -Repo $Repo -IssueNumber $PrNumber
    }
    catch {
        Write-Debug "Parent issue detection failed: $_"
    }
}

if ($ParentIssue -and $ParentIssue -ne '0') {
    Write-Information "Parent issue: #$ParentIssue"
}
else {
    Write-Information 'No parent issue detected — sub-issue links will not be created.'
}

# Dry-run mode
if ($env:DRY_RUN -eq '1') {
    DryRunReport -Blocks $blocks -ParentNum $ParentIssue
    exit 0
}

# --- Live mode: Create issues ---
if (-not $Repo) {
    Write-Warning 'Error: REPO is required for issue creation'
    exit 1
}

# Check parent labels for propagation
$hasContextReview = $false
$hasQa = $false
if ($ParentIssue -and $ParentIssue -ne '0') {
    try {
        $parentData = Get-GitHubIssue -IssueNum $ParentIssue -Repo $Repo
        if ($parentData) {
            if ($parentData.labels -contains 'auto-context-review') {
                $hasContextReview = $true
                Write-Information '  auto-context-review ラベル伝播: true'
            }
            if ($parentData.labels -contains 'auto-qa') {
                $hasQa = $true
                Write-Information '  auto-qa ラベル伝播: true'
            }
        }
    }
    catch {
        Write-Debug "Parent label check failed: $_"
    }
}

# Pass 1: Create all issues
Write-Information '--- Pass 1: Creating issues ---'
$issueMapNum = @{}    # blockNum -> issue_number
$issueMapId = @{}     # blockNum -> issue_database_id
$issueMapAgent = @{}  # blockNum -> custom_agent

for ($i = 0; $i -lt $blocks.Count; $i++) {
    $block = $blocks[$i]
    $blockNum = $i + 1
    $title = $block.Title
    $agent = $block.CustomAgent
    $body = $block.Body
    $labelsRaw = $block.Labels
    $deps = $block.DependsOn

    if (-not $title) {
        Write-Information "  Block ${blockNum}: missing title — skipped"
        continue
    }

    # Append custom agent line
    if ($agent) {
        $body += "`n`n> **Custom agent used: $agent**"
    }

    # Prepend metadata comments
    $metaLines = ''
    if ($ParentIssue -and $ParentIssue -ne '0') {
        $metaLines += "<!-- parent-issue: #$ParentIssue -->`n"
    }
    if ($PrNumber) {
        $metaLines += "<!-- pr-number: $PrNumber -->`n"
    }
    $metaLines += "<!-- pr-head-branch: $BaseBranch -->`n"
    $body = $metaLines + $body

    # Build label list
    $allLabels = @()
    if ($labelsRaw) {
        $allLabels = @($labelsRaw -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }
    if ($hasContextReview -and $allLabels -notcontains 'auto-context-review') {
        $allLabels += 'auto-context-review'
    }
    if ($hasQa -and $allLabels -notcontains 'auto-qa') {
        $allLabels += 'auto-qa'
    }

    # Build JSON labels array
    $labelsJson = '[]'
    if ($allLabels.Count -gt 0) {
        $labelsJson = ConvertTo-Json @($allLabels) -Compress
    }

    # Create labels
    foreach ($lbl in $allLabels) {
        try { New-GitHubLabel -Name $lbl -Color 'bfd4f2' -Repo $Repo -Confirm:$false } catch { Write-Debug "Suppressed: $_" }
    }

    Write-Information "  Creating: $title"
    try {
        $result = New-GitHubIssue -Title $title -Body $body -LabelsJson $labelsJson -Repo $Repo -Confirm:$false
        $parts = $result -split '\s+'
        $issueNum = $parts[0]
        $issueId = $parts[1]

        Write-Information "  Created #${issueNum}: $title"
        $issueMapNum[$blockNum] = $issueNum
        $issueMapId[$blockNum] = $issueId
        $issueMapAgent[$blockNum] = $agent

        # Link to parent
        if ($ParentIssue -and $ParentIssue -ne '0' -and $issueId) {
            Start-Sleep -Seconds 2
            try {
                Add-SubIssueLink -ParentNum $ParentIssue -ChildId $issueId -Repo $Repo
                Write-Information "  Linked #$issueNum to parent #$ParentIssue"
            }
            catch {
                Write-Information "  Warning: failed to link #$issueNum to parent #$ParentIssue"
            }
        }

        Start-Sleep -Seconds 1
    }
    catch {
        Write-Warning "  Failed to create: $title"
        continue
    }
}

# Pass 2: Copilot assignment and dependency body update
Write-Information '--- Pass 2: Copilot assignment and dependency body update ---'
for ($i = 0; $i -lt $blocks.Count; $i++) {
    $block = $blocks[$i]
    $blockNum = $i + 1
    $deps = $block.DependsOn
    $agent = $block.CustomAgent
    $issueNum = $issueMapNum[$blockNum]

    if (-not $issueNum) { continue }

    if (-not $deps) {
        # Root node: assign Copilot
        if ($agent) {
            try {
                $null = Invoke-CopilotAssign -Repo $Repo -IssueNumber $issueNum -CustomAgent $agent -BaseBranch $BaseBranch
                Write-Information "  #${issueNum}: Copilot assign ✅ 即時"
            }
            catch {
                Write-Information "  #${issueNum}: Copilot assign ⚠️ 失敗"
            }
        }
    }
    else {
        # Dependent node: update body with prerequisite links
        $depArr = @($deps -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        $depRefs = @()
        foreach ($d in $depArr) {
            $depNum = $issueMapNum[[int]$d]
            if ($depNum) { $depRefs += "#$depNum" }
        }

        if ($depRefs.Count -gt 0) {
            try {
                $currentData = Get-GitHubIssue -IssueNum $issueNum -Repo $Repo
                if ($currentData) {
                    $currentBody = $currentData.body
                    $depSection = "`n`n## ⏳ 前提条件（Dependencies）`n`n以下のIssueが完了してから、このIssueにCopilot coding agentをアサインしてください:`n"
                    foreach ($ref in $depRefs) {
                        $depSection += "- $ref`n"
                    }
                    $newBody = $currentBody + $depSection

                    $tmpFile = [System.IO.Path]::GetTempFileName()
                    try {
                        [System.IO.File]::WriteAllText($tmpFile, $newBody)
                        $null = gh issue edit $issueNum --repo $Repo --body-file $tmpFile 2>&1
                    }
                    finally {
                        if (Test-Path $tmpFile) { Remove-Item $tmpFile -Force }
                    }
                }
            }
            catch {
                Write-Debug "Body update failed for #${issueNum}: $_"
            }
        }

        $depRefStr = if ($depRefs.Count -gt 0) { $depRefs -join ' ' } else { '未解決' }
        Write-Information "  #${issueNum}: ⏳ 待ち (依存: $depRefStr)"
    }
}

Write-Information 'Done.'
