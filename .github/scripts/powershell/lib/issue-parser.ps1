# issue-parser.ps1 — Issue body 解析モジュール
#
# Migrated from:
#   - .github/scripts/bash/lib/issue-parser.sh
#   - .github/cli/lib/issue_parser.py
#
# Prerequisites:
#   - PowerShell 7.0+
#   - gh CLI installed and authenticated
#
# Environment variables:
#   GH_TOKEN / GITHUB_TOKEN — GitHub API token (for Find-ParentIssue)
#   REPO                    — Repository in "owner/repo" format
#   PR_NUMBER               — Current PR number (optional, for Find-ParentIssue)
#   DRY_RUN                 — Set to "1" to enable dry-run mode
#
# Usage:
#   . "$PSScriptRoot/issue-parser.ps1"

# Guard against double-sourcing
if (Test-Path Function:\Get-IssueMetadatum) { return }

# Source gh-api.ps1 for shared functions (Invoke-GhApi, Get-GitHubIssue)
. "$PSScriptRoot/gh-api.ps1"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

function script:TestIssueParserDryRun {
    return ($env:DRY_RUN -eq '1')
}

function script:ResolveIssueParserToken {
    if ($env:GH_TOKEN) { return $env:GH_TOKEN }
    if ($env:GITHUB_TOKEN) { return $env:GITHUB_TOKEN }
    return ''
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

function Get-IssueMetadatum {
    <#
    .SYNOPSIS
        Extract HTML comment metadata from issue body.
        Format: <!-- key: value -->
    .PARAMETER Body
        Issue body text
    .PARAMETER Key
        Metadata key name (e.g. "root-issue", "branch", "auto-review")
    .OUTPUTS
        Value string, or empty string if not found.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyString()][string]$Body,
        [Parameter(Mandatory)][string]$Key
    )

    if (-not $Body) { return '' }

    # Match <!-- key: value -->
    $escapedKey = [regex]::Escape($Key)
    if ($Body -match "<!--\s*$escapedKey\s*:\s*(.+?)\s*-->") {
        return $Matches[1].Trim()
    }
    return ''
}

function Get-CustomAgent {
    <#
    .SYNOPSIS
        Extract Custom Agent name from issue body.
    .PARAMETER Body
        Issue body text
    .OUTPUTS
        Agent name string, or empty string if not found.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyString()][string]$Body
    )

    if (-not $Body) { return '' }

    # Pattern 1: ## Custom Agent\n`AgentName`
    if ($Body -match '(?m)^##\s*Custom Agent\s*\r?\n[^`]*`([^`]+)`') {
        return $Matches[1].Trim()
    }

    # Pattern 2: > **Custom agent used: AgentName**
    if ($Body -match '>\s*\*\*Custom agent used:\s*([^*]+)\*\*') {
        return $Matches[1].Trim()
    }

    return ''
}

function Find-ParentIssue {
    <#
    .SYNOPSIS
        Resolve parent issue number with 4-stage fallback.
    .PARAMETER Repo
        Repository in "owner/repo" format
    .PARAMETER IssueNumber
        Issue number to find parent for
    .OUTPUTS
        Parent issue number string. Returns '' if not found.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$IssueNumber
    )

    if (TestIssueParserDryRun) {
        Write-Information "[DRY_RUN] find_parent_issue $Repo #$IssueNumber"
        return '0'
    }

    $token = ResolveIssueParserToken
    if (-not $token) {
        Write-Warning 'GH_TOKEN / GITHUB_TOKEN が設定されていません。親 Issue を特定できません。'
        return ''
    }

    $currentPr = $env:PR_NUMBER

    # Get issue body (used by Method 1 and 2)
    $issueBody = ''
    try {
        $issueData = Get-GitHubIssue -IssueNum $IssueNumber -Repo $Repo
        if ($issueData) {
            $issueBody = $issueData.body
        }
    }
    catch {
        Write-Debug "Failed to fetch issue body: $_"
    }

    # Method 1: <!-- parent-issue: #NNN -->
    if ($issueBody -match '<!--\s*parent-issue:\s*#(\d+)') {
        $parentNum = $Matches[1]
        Write-Information "  Method 1 (parent-issue comment): #$parentNum"
        return $parentNum
    }

    # Method 2: <!-- pr-number: NNN --> → PR's closingIssuesReferences
    if ($issueBody -match '<!--\s*pr-number:\s*(\d+)') {
        $sourcePr = $Matches[1]
        if ($sourcePr -ne $currentPr) {
            try {
                $prJson = gh api "/repos/$Repo/pulls/$sourcePr" `
                    --header 'Accept: application/vnd.github+json' 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $prData = ($prJson -join "`n") | ConvertFrom-Json
                    $prBody = if ($prData.body) { $prData.body } else { '' }
                    if ($prBody -match '(?i)(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+(?:[\w\-\.]+/[\w\-\.]+)?#(\d+)') {
                        $closingIssue = $Matches[1]
                        Write-Information "  Method 2 (pr-number comment): #$closingIssue via PR #$sourcePr"
                        return $closingIssue
                    }
                }
            }
            catch {
                Write-Debug "Method 2 failed: $_"
            }
        }
    }

    # Method 3a: GraphQL trackedInIssues
    $owner = ($Repo -split '/')[0]
    $repoName = ($Repo -split '/')[1]

    $graphqlQuery = @'
query($owner: String!, $repo: String!, $num: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $num) {
      trackedInIssues(first: 1) {
        nodes { number }
      }
    }
  }
}
'@

    try {
        $graphqlResult = gh api graphql `
            -f "query=$graphqlQuery" `
            -f "owner=$owner" `
            -f "repo=$repoName" `
            -F "num=$IssueNumber" 2>&1

        if ($LASTEXITCODE -eq 0) {
            $grData = ($graphqlResult -join "`n") | ConvertFrom-Json
            $trackedNum = $grData.data.repository.issue.trackedInIssues.nodes[0].number
            if ($trackedNum) {
                Write-Information "  Method 3a (GraphQL trackedInIssues): #$trackedNum"
                return "$trackedNum"
            }
        }
    }
    catch {
        Write-Debug "Method 3a failed: $_"
    }

    # Method 3b: <!-- subissues-created --> PR comment
    try {
        $timelineJson = gh api "/repos/$Repo/issues/$IssueNumber/timeline?per_page=100" `
            --header 'Accept: application/vnd.github+json' 2>&1
        if ($LASTEXITCODE -eq 0) {
            $timeline = ($timelineJson -join "`n") | ConvertFrom-Json

            foreach ($timelineEvent in $timeline) {
                if ($timelineEvent.event -ne 'cross-referenced') { continue }
                if ($null -eq $timelineEvent.source.issue.pull_request) { continue }
                $xrefPr = $timelineEvent.source.issue.number
                if ("$xrefPr" -eq "$currentPr") { continue }

                # Check for <!-- subissues-created --> marker in PR comments
                try {
                    $commentsJson = gh api "/repos/$Repo/issues/$xrefPr/comments?per_page=100" `
                        --header 'Accept: application/vnd.github+json' 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        Start-Sleep -Milliseconds 500
                        continue
                    }

                    $comments = ($commentsJson -join "`n") | ConvertFrom-Json
                    $hasMarker = $false
                    foreach ($commentItem in $comments) {
                        if ($commentItem.body -and $commentItem.body.Contains('<!-- subissues-created -->')) {
                            $hasMarker = $true
                            break
                        }
                    }

                    if (-not $hasMarker) {
                        Start-Sleep -Milliseconds 500
                        continue
                    }

                    # Extract closingIssuesReferences from this PR's body
                    $xrefPrJson = gh api "/repos/$Repo/pulls/$xrefPr" `
                        --header 'Accept: application/vnd.github+json' 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        Start-Sleep -Milliseconds 500
                        continue
                    }

                    $xrefPrData = ($xrefPrJson -join "`n") | ConvertFrom-Json
                    $xrefPrBody = if ($xrefPrData.body) { $xrefPrData.body } else { '' }
                    if ($xrefPrBody -match '(?i)(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+(?:[\w\-\.]+/[\w\-\.]+)?#(\d+)') {
                        $closingRef = $Matches[1]
                        Write-Information "  Method 3b (subissues-created): #$closingRef via PR #$xrefPr"
                        return $closingRef
                    }
                    Start-Sleep -Milliseconds 500
                }
                catch {
                    Write-Debug "Method 3b inner error: $_"
                    Start-Sleep -Milliseconds 500
                    continue
                }
            }
        }
    }
    catch {
        Write-Debug "Method 3b failed: $_"
    }

    Write-Warning '全 Method で親 Issue を特定できませんでした。'
    return ''
}
