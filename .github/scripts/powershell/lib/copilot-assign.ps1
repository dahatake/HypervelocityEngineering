# copilot-assign.ps1 — Copilot cloud agent アサインモジュール
#
# Migrated from:
#   - .github/scripts/bash/lib/copilot-assign.sh
#   - .github/cli/lib/copilot_assign.py
#
# Prerequisites:
#   - PowerShell 7.0+
#   - gh CLI installed and authenticated
#
# Environment variables:
#   GH_TOKEN / GITHUB_TOKEN — GitHub REST API token (idempotency checks / comments)
#   COPILOT_PAT             — Copilot assignment PAT (GraphQL mutation)
#   REPO                    — Repository in "owner/repo" format
#   DRY_RUN                 — Set to "1" to enable dry-run mode
#
# Usage:
#   . "$PSScriptRoot/copilot-assign.ps1"

# Guard against double-sourcing
if (Test-Path Function:\Invoke-CopilotAssign) { return }

# Source gh-api.ps1 for shared functions (Add-IssueComment, Get-GitHubIssue)
. "$PSScriptRoot/gh-api.ps1"

# GraphQL Features header (enables Copilot assignment API)
$script:GraphQLFeatures = 'issues_copilot_assignment_api_support,coding_agent_model_selection'

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

function script:TestCopilotAssignDryRun {
    return ($env:DRY_RUN -eq '1')
}

function script:ResolveGhToken {
    if ($env:GH_TOKEN) { return $env:GH_TOKEN }
    if ($env:GITHUB_TOKEN) { return $env:GITHUB_TOKEN }
    return ''
}

function script:TestCopilotAssigned {
    <#
    .SYNOPSIS
        Check whether copilot-swe-agent is already assigned (idempotency guard).
    #>
    param(
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$IssueNumber
    )

    try {
        $issueData = Get-GitHubIssue -IssueNum $IssueNumber -Repo $Repo
        if (-not $issueData) { return $false }

        foreach ($assignee in $issueData.assignees) {
            if ($assignee -match '^(copilot-swe-agent|Copilot)$') {
                return $true
            }
        }
        return $false
    }
    catch {
        Write-Debug "TestCopilotAssigned error: $_"
        return $false
    }
}

function script:TestHasOpenPr {
    <#
    .SYNOPSIS
        Check whether an open PR already exists for the issue (idempotency guard).
    #>
    param(
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$IssueNumber
    )

    $ghToken = ResolveGhToken
    if (-not $ghToken) { return $false }

    try {
        $timelineJson = gh api "/repos/$Repo/issues/$IssueNumber/timeline?per_page=100" `
            --header 'Accept: application/vnd.github+json' 2>&1
        if ($LASTEXITCODE -ne 0) { return $false }

        $timeline = ($timelineJson -join "`n") | ConvertFrom-Json

        foreach ($timelineEvent in $timeline) {
            if ($timelineEvent.event -eq 'cross-referenced' -and
                $null -ne $timelineEvent.source.issue.pull_request -and
                $timelineEvent.source.issue.state -eq 'open') {
                return $true
            }
        }
        return $false
    }
    catch {
        Write-Debug "TestHasOpenPr error: $_"
        return $false
    }
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

function Invoke-CopilotAssign {
    <#
    .SYNOPSIS
        3-stage dispatch for Copilot assignment.
    .PARAMETER Repo
        Repository in "owner/repo" format
    .PARAMETER IssueNumber
        Issue number to assign
    .PARAMETER CustomAgent
        Custom Agent name (optional)
    .PARAMETER BaseBranch
        Base branch for Copilot (default: "main")
    .PARAMETER CustomInstructions
        Custom instructions text (optional)
    .PARAMETER MaxRetries
        Maximum retry count (default: 3)
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$IssueNumber,
        [string]$CustomAgent = '',
        [string]$BaseBranch = 'main',
        [string]$CustomInstructions = '',
        [int]$MaxRetries = 3
    )

    Write-Information "=== Copilot アサイン開始: Issue #$IssueNumber ==="
    Write-Information "  custom_agent: $CustomAgent"
    Write-Information "  base_branch: $BaseBranch"

    if (TestCopilotAssignDryRun) {
        Write-Information "[DRY_RUN] assign_copilot $Repo #$IssueNumber agent=$CustomAgent"
        return $true
    }

    $ghToken = ResolveGhToken

    # Idempotency guard: already assigned check
    if ($ghToken -and (TestCopilotAssigned -Repo $Repo -IssueNumber $IssueNumber)) {
        Write-Information '  copilot-swe-agent は既にアサイン済みです。スキップします。'
        return $true
    }

    # Idempotency guard: open PR check
    if ($ghToken -and (TestHasOpenPr -Repo $Repo -IssueNumber $IssueNumber)) {
        Write-Information "  Issue #$IssueNumber に紐づく Open な PR が既に存在します。スキップします。"
        return $true
    }

    # Stage 1: Try standalone copilot assign (future support)
    if (Get-Command 'copilot' -ErrorAction SilentlyContinue) {
        try {
            $null = copilot assign --issue $IssueNumber --repo $Repo 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Information '  Stage 1: copilot assign 成功'
                Write-Information "=== Copilot アサイン完了: Issue #$IssueNumber ==="
                return $true
            }
        }
        catch {
            Write-Debug "Stage 1 failed: $_"
        }
    }

    # Stage 2: Simple assignee (no Custom Agent)
    if (-not $CustomAgent) {
        try {
            $null = gh issue edit $IssueNumber -R $Repo --add-assignee '@copilot' 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Information '  Stage 2: gh issue edit --add-assignee 成功'
                Write-Information "=== Copilot アサイン完了: Issue #$IssueNumber ==="
                Start-Sleep -Seconds 2
                return $true
            }
        }
        catch {
            Write-Debug "Stage 2 failed: $_"
        }
        Write-Information '  Stage 2 failed, falling through to Stage 3 (GraphQL)'
    }

    # Stage 3: GraphQL mutation (Custom Agent support — current primary path)
    $copilotPat = $env:COPILOT_PAT
    if (-not $copilotPat) {
        Write-Warning 'COPILOT_PAT が設定されていません。Copilot アサインをスキップします。'
        Write-Warning '  → Copilot アサイン権限を持つ PAT を作成し、COPILOT_PAT 環境変数に設定してください。'
        throw 'COPILOT_PAT not set'
    }

    $owner = ($Repo -split '/')[0]
    $repoName = ($Repo -split '/')[1]
    $waitSec = 5

    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        Write-Information "  アサイン試行 $attempt/$MaxRetries..."

        # Fetch bot_id, issue_node_id, repo_node_id in one query
        $graphqlQuery = @'
query($owner: String!, $repoName: String!, $issueNumber: Int!) {
  repository(owner: $owner, name: $repoName) {
    id
    issue(number: $issueNumber) { id }
    suggestedActors(capabilities: [CAN_BE_ASSIGNED], first: 100) {
      nodes {
        login
        ... on Bot { id databaseId }
      }
    }
  }
}
'@

        $envBackup = $env:GH_TOKEN
        try {
            $env:GH_TOKEN = $copilotPat
            $queryResult = gh api graphql `
                -f "query=$graphqlQuery" `
                -f "owner=$owner" `
                -f "repoName=$repoName" `
                -F "issueNumber=$IssueNumber" 2>&1

            if ($LASTEXITCODE -ne 0) {
                Write-Warning "GraphQL クエリ失敗 (試行 $attempt/$MaxRetries)"
                if ($attempt -lt $MaxRetries) { Start-Sleep -Seconds $waitSec; $waitSec *= 2 }
                continue
            }

            $qrData = ($queryResult -join "`n") | ConvertFrom-Json

            $botId = ''
            foreach ($node in $qrData.data.repository.suggestedActors.nodes) {
                if ($node.login -eq 'copilot-swe-agent') {
                    $botId = $node.id
                    break
                }
            }
            $issueNodeId = $qrData.data.repository.issue.id
            $repoNodeId = $qrData.data.repository.id

            if (-not $botId) {
                Write-Warning "copilot-swe-agent の Bot ID を取得できませんでした。試行 $attempt/$MaxRetries"
                if ($attempt -lt $MaxRetries) { Start-Sleep -Seconds $waitSec; $waitSec *= 2 }
                continue
            }
            if (-not $issueNodeId) {
                Write-Warning "Issue #$IssueNumber の Node ID を取得できませんでした。試行 $attempt/$MaxRetries"
                if ($attempt -lt $MaxRetries) { Start-Sleep -Seconds $waitSec; $waitSec *= 2 }
                continue
            }
            if (-not $repoNodeId) {
                Write-Warning "Repository の Node ID を取得できませんでした。試行 $attempt/$MaxRetries"
                if ($attempt -lt $MaxRetries) { Start-Sleep -Seconds $waitSec; $waitSec *= 2 }
                continue
            }

            Write-Information "  Bot ID: $botId, Issue Node ID: $issueNodeId, Repo Node ID: $repoNodeId"

            # Run the assignment mutation
            $mutationQuery = @'
mutation(
  $assignableId: ID!,
  $botId: ID!,
  $targetRepositoryId: ID!,
  $baseRef: String!,
  $customInstructions: String!,
  $customAgent: String!
) {
  addAssigneesToAssignable(input: {
    assignableId: $assignableId,
    assigneeIds: [$botId],
    agentAssignment: {
      targetRepositoryId: $targetRepositoryId,
      baseRef: $baseRef,
      customInstructions: $customInstructions,
      customAgent: $customAgent,
      model: ""
    }
  }) {
    assignable {
      ... on Issue {
        id
        title
        assignees(first: 10) {
          nodes { login }
        }
      }
    }
  }
}
'@

            $mutationResult = gh api graphql `
                --header "GraphQL-Features: $($script:GraphQLFeatures)" `
                -f "query=$mutationQuery" `
                -f "assignableId=$issueNodeId" `
                -f "botId=$botId" `
                -f "targetRepositoryId=$repoNodeId" `
                -f "baseRef=$BaseBranch" `
                -f "customInstructions=$CustomInstructions" `
                -f "customAgent=$CustomAgent" 2>&1

            if ($LASTEXITCODE -ne 0) {
                Write-Warning "GraphQL mutation 失敗 (試行 $attempt/$MaxRetries)"
                if ($attempt -lt $MaxRetries) { Start-Sleep -Seconds $waitSec; $waitSec *= 2 }
                continue
            }

            $mrData = ($mutationResult -join "`n") | ConvertFrom-Json

            # Check if copilot-swe-agent is in the assignees
            $isAssigned = $false
            foreach ($node in $mrData.data.addAssigneesToAssignable.assignable.assignees.nodes) {
                if ($node.login -match '^(copilot-swe-agent|Copilot)$') {
                    $isAssigned = $true
                    break
                }
            }

            if ($isAssigned) {
                Write-Information '  copilot-swe-agent のアサインを確認しました。'
                Write-Information "=== Copilot アサイン完了: Issue #$IssueNumber ==="
                Start-Sleep -Seconds 2
                return $true
            }

            Write-Warning "copilot-swe-agent が assignees に含まれていません。試行 $attempt/$MaxRetries"
            if ($attempt -lt $MaxRetries) { Start-Sleep -Seconds $waitSec; $waitSec *= 2 }
        }
        finally {
            $env:GH_TOKEN = $envBackup
        }
    }

    # All retries exhausted — post failure comment
    $failMsg = @"
⚠️ Copilot cloud agent (copilot-swe-agent) を Issue #$IssueNumber にアサインできませんでした。

手動でアサインする手順:
1. Issue #$IssueNumber を開く
2. 右サイドバーの「Assignees」から ``copilot-swe-agent`` を選択する

失敗原因として考えられるもの:
- ``COPILOT_PAT`` の権限不足または失効
- Copilot cloud agent が有効化されていない
- GraphQL API の一時的な障害
"@

    $commentToken = if ($ghToken) { $ghToken } else { $copilotPat }
    if ($commentToken) {
        $envBackupComment = $env:GH_TOKEN
        try {
            $env:GH_TOKEN = $commentToken
            Add-IssueComment -IssueNum $IssueNumber -Body $failMsg -Repo $Repo
            Write-Warning "Issue #$IssueNumber へのアサイン失敗通知を投稿しました。"
        }
        catch {
            Write-Warning "アサイン失敗通知の投稿にも失敗しました: $_"
        }
        finally {
            $env:GH_TOKEN = $envBackupComment
        }
    }
    throw "Copilot assignment failed for Issue #$IssueNumber after $MaxRetries retries"
}
