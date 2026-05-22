# gh-api.ps1 — GitHub REST API utilities (gh CLI wrapper)
#
# Migrated from:
#   - .github/scripts/bash/lib/gh-api.sh
#   - .github/cli/lib/github_api.py
#
# Prerequisites:
#   - PowerShell 7.0+
#   - gh CLI installed and authenticated (gh auth status)
#
# Environment variables:
#   REPO      — Repository in "owner/repo" format (required unless passed as argument)
#   DRY_RUN   — Set to "1" to enable dry-run mode (prints commands instead of executing)
#
# Usage:
#   . "$PSScriptRoot/gh-api.ps1"

# Guard against double-sourcing
if (Test-Path Function:\Invoke-GhApi) { return }

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

function script:ResolveGhApiRepo {
    param([string]$Repo)
    if ($Repo) { return $Repo }
    if ($env:REPO) { return $env:REPO }
    throw 'Repository not specified. Set REPO environment variable (owner/repo).'
}

function script:TestGhApiDryRun {
    return ($env:DRY_RUN -eq '1')
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

function Invoke-GhApi {
    <#
    .SYNOPSIS
        Lightweight wrapper around gh api.
    .PARAMETER Method
        HTTP method (GET, POST, PATCH, DELETE)
    .PARAMETER Endpoint
        API endpoint path
    .PARAMETER Data
        Optional JSON request body (string)
    .PARAMETER Repo
        Optional repository override (owner/repo)
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Endpoint,
        [string]$Data,
        [string]$Repo
    )

    $Repo = ResolveGhApiRepo -Repo $Repo

    if (TestGhApiDryRun) {
        Write-Information "[DRY_RUN] gh api -X $Method $Endpoint"
        if ($Data) {
            Write-Information '[DRY_RUN]   --input (json data)'
        }
        return '{}'
    }

    $cmd = @('api', '-X', $Method, '--header', 'Accept: application/vnd.github+json', '--retry', '3')

    if ($Data) {
        $cmd += @('--input', '-')
        $result = $Data | gh @cmd $Endpoint 2>&1
    }
    else {
        $result = gh @cmd $Endpoint 2>&1
    }

    if ($LASTEXITCODE -ne 0) {
        throw "gh api failed: $result"
    }
    return ($result -join "`n")
}

function New-GitHubIssue {
    <#
    .SYNOPSIS
        Create a GitHub Issue and return "number id" (space-separated).
    .PARAMETER Title
        Issue title
    .PARAMETER Body
        Issue body in Markdown
    .PARAMETER LabelsJson
        JSON array string of label names
    .PARAMETER Repo
        Optional repository override
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$Body,
        [Parameter(Mandatory)][string]$LabelsJson,
        [string]$Repo
    )

    $Repo = ResolveGhApiRepo -Repo $Repo

    if (TestGhApiDryRun) {
        Write-Information "[DRY_RUN] gh issue create -R $Repo --title '$Title' --body-file ... --label ..."
        return '0 0'
    }

    if (-not $PSCmdlet.ShouldProcess("Issue '$Title' in $Repo", 'Create')) {
        return '0 0'
    }

    # Build label args from JSON array
    $labelArgs = @()
    try {
        $labels = $LabelsJson | ConvertFrom-Json
        foreach ($lbl in $labels) {
            if ($lbl) {
                $labelArgs += @('--label', "$lbl")
            }
        }
    }
    catch {
        Write-Debug "Label JSON parse failed: $_"
    }

    # Use --body-file to avoid command-line length limits
    $tmpFile = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($tmpFile, $Body)

        $ghArgs = @('issue', 'create', '-R', $Repo, '--title', $Title, '--body-file', $tmpFile) + $labelArgs
        $result = gh @ghArgs 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "create_issue failed: $result"
        }

        # gh issue create prints the URL; extract the issue number from it
        $issueUrl = "$result"
        if ($issueUrl -match '(\d+)$') {
            $issueNumber = $Matches[1]
        }
        else {
            throw "Could not extract issue number from: $issueUrl"
        }

        # Fetch the numeric database ID (required by Add-SubIssueLink)
        $issueJson = gh api "/repos/$Repo/issues/$issueNumber" --header 'Accept: application/vnd.github+json' 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Could not fetch issue details for #$issueNumber"
        }

        $issueData = ($issueJson -join "`n") | ConvertFrom-Json
        $issueId = $issueData.id

        return "$issueNumber $issueId"
    }
    finally {
        if (Test-Path $tmpFile) { Remove-Item $tmpFile -Force }
    }
}

function Add-SubIssueLink {
    <#
    .SYNOPSIS
        Link an issue as a sub-issue of a parent issue (idempotent).
    .PARAMETER ParentNum
        Parent issue number
    .PARAMETER ChildId
        Sub-issue numeric database ID
    .PARAMETER Repo
        Optional repository override
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ParentNum,
        [Parameter(Mandatory)][string]$ChildId,
        [string]$Repo
    )

    $Repo = ResolveGhApiRepo -Repo $Repo

    if (TestGhApiDryRun) {
        Write-Information "[DRY_RUN] gh api POST /repos/$Repo/issues/$ParentNum/sub_issues --field sub_issue_id=$ChildId"
        Start-Sleep -Seconds 1
        return
    }

    $payload = "{`"sub_issue_id`":$ChildId}"
    $null = $payload | gh api -X POST "/repos/$Repo/issues/$ParentNum/sub_issues" `
        --header 'Accept: application/vnd.github+json' `
        --input - 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "link_sub_issue 失敗: parent=#$ParentNum child_id=$ChildId"
    }
    Start-Sleep -Seconds 1
}

function Add-IssueLabel {
    <#
    .SYNOPSIS
        Add a label to an issue or pull request.
    .PARAMETER IssueNum
        Issue or PR number
    .PARAMETER Label
        Label name
    .PARAMETER Repo
        Optional repository override
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$IssueNum,
        [Parameter(Mandatory)][string]$Label,
        [string]$Repo
    )

    $Repo = ResolveGhApiRepo -Repo $Repo

    if (TestGhApiDryRun) {
        Write-Information "[DRY_RUN] gh issue edit $IssueNum -R $Repo --add-label '$Label'"
        Start-Sleep -Seconds 1
        return
    }

    $null = gh issue edit $IssueNum -R $Repo --add-label $Label 2>&1
    Start-Sleep -Seconds 1
}

function New-GitHubLabel {
    <#
    .SYNOPSIS
        Create a repository label. 422 (already exists) is silently ignored.
    .PARAMETER Name
        Label name
    .PARAMETER Color
        Hex color without leading '#'
    .PARAMETER Description
        Optional label description
    .PARAMETER Repo
        Optional repository override
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Color,
        [string]$Description = '',
        [string]$Repo
    )

    $Repo = ResolveGhApiRepo -Repo $Repo

    if (TestGhApiDryRun) {
        Write-Information "[DRY_RUN] gh api POST /repos/$Repo/labels --field name='$Name' --field color='$Color'"
        Start-Sleep -Seconds 1
        return
    }

    if (-not $PSCmdlet.ShouldProcess("Label '$Name' in $Repo", 'Create')) {
        return
    }

    $payload = @{
        name        = $Name
        color       = $Color
        description = $Description
    } | ConvertTo-Json -Compress

    $result = $payload | gh api -X POST "/repos/$Repo/labels" `
        --header 'Accept: application/vnd.github+json' `
        --input - 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Information "ラベル作成: $Name"
    }
    else {
        $resultStr = "$result"
        if ($resultStr -match 'already_exists|already exists|422') {
            Write-Information "ラベル既存（スキップ）: $Name"
        }
        else {
            Write-Warning "ラベル作成エラー: $Name — $resultStr"
            Start-Sleep -Seconds 1
            throw "Label creation failed: $resultStr"
        }
    }
    Start-Sleep -Seconds 1
}

function Add-IssueComment {
    <#
    .SYNOPSIS
        Post a comment on an issue or pull request.
    .PARAMETER IssueNum
        Issue or PR number
    .PARAMETER Body
        Comment body in Markdown
    .PARAMETER Repo
        Optional repository override
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$IssueNum,
        [Parameter(Mandatory)][string]$Body,
        [string]$Repo
    )

    $Repo = ResolveGhApiRepo -Repo $Repo

    if (TestGhApiDryRun) {
        Write-Information "[DRY_RUN] gh issue comment $IssueNum -R $Repo --body-file ..."
        Start-Sleep -Seconds 1
        return
    }

    # Use --body-file to avoid command-line length limits
    $tmpFile = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($tmpFile, $Body)
        $null = gh issue comment $IssueNum -R $Repo --body-file $tmpFile 2>&1
        Start-Sleep -Seconds 1
    }
    finally {
        if (Test-Path $tmpFile) { Remove-Item $tmpFile -Force }
    }
}

function Get-GitHubIssue {
    <#
    .SYNOPSIS
        Fetch issue details and return a PSCustomObject with normalised fields.
    .PARAMETER IssueNum
        Issue number
    .PARAMETER Repo
        Optional repository override
    .OUTPUTS
        PSCustomObject with keys: number, title, body, state, labels, assignees, id, node_id
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$IssueNum,
        [string]$Repo
    )

    $Repo = ResolveGhApiRepo -Repo $Repo

    if (TestGhApiDryRun) {
        Write-Information "[DRY_RUN] gh issue view $IssueNum -R $Repo --json ..."
        return [PSCustomObject]@{
            number    = 0
            title     = ''
            body      = ''
            state     = ''
            labels    = @()
            assignees = @()
            id        = 0
            node_id   = ''
        }
    }

    $raw = gh api "/repos/$Repo/issues/$IssueNum" `
        --header 'Accept: application/vnd.github+json' 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "get_issue failed for #${IssueNum}: $raw"
    }

    $data = ($raw -join "`n") | ConvertFrom-Json

    # Normalise: extract label names and assignee logins into flat arrays
    $labelNames = @()
    if ($data.labels) {
        $labelNames = @($data.labels | ForEach-Object { $_.name })
    }

    $assigneeLogins = @()
    if ($data.assignees) {
        $assigneeLogins = @($data.assignees | ForEach-Object { $_.login })
    }

    return [PSCustomObject]@{
        number    = if ($null -ne $data.number) { $data.number } else { 0 }
        title     = if ($data.title) { $data.title } else { '' }
        body      = if ($data.body) { $data.body } else { '' }
        state     = if ($data.state) { $data.state } else { '' }
        labels    = $labelNames
        assignees = $assigneeLogins
        id        = if ($null -ne $data.id) { $data.id } else { 0 }
        node_id   = if ($data.node_id) { $data.node_id } else { '' }
    }
}
