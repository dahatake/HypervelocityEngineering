# run-workflow.ps1 — ユーザーエントリポイント
#
# 設計ワークフロー全体実行、ステップ遷移、Copilot CLI 連携など
# すべてのコマンドを1つのスクリプトから実行できるエントリポイント。
#
# Usage:
#   # 設計ワークフロー全体実行
#   $env:REPO = "owner/repo"
#   .\run-workflow.ps1 -Workflow aad -Branch main
#
#   # dry-run + ステップ限定
#   .\run-workflow.ps1 -Workflow aad -Steps "1.1,1.2" -DryRun
#
#   # 完了 → 次ステップ遷移
#   .\run-workflow.ps1 -Action advance -Issue 123 -DryRun
#
#   # Sub-Issue 一括作成
#   .\run-workflow.ps1 -Action create-subissues -File work/subissues.md -ParentIssue 100
#
#   # Plan 検証
#   .\run-workflow.ps1 -Action validate-plan -Path work/Issue-123/plan.md
#
#   # Subissues 検証
#   .\run-workflow.ps1 -Action validate-subissues -Path work/Issue-123/subissues.md
#
#   # Copilot CLI プロンプト駆動
#   .\run-workflow.ps1 -Action copilot -Prompt "仕様を整理して"
#
# Environment:
#   REPO        — Repository in "owner/repo" format
#   GH_TOKEN    — GitHub API token
#   COPILOT_PAT — Copilot assignment PAT
#   DRY_RUN     — Set to "1" for dry-run mode

[CmdletBinding()]
param(
    # Subcommand (default = orchestrate)
    [ValidateSet('', 'advance', 'create-subissues', 'validate-plan', 'validate-subissues', 'copilot', 'help')]
    [string]$Action = '',

    # Orchestrate parameters
    [Alias('w')]
    [string]$Workflow = '',
    [string]$Branch = 'main',
    [string]$Steps = '',

    # Advance parameters
    [string]$Issue = '',

    # Create-subissues parameters
    [string]$File = '',
    [string]$ParentIssue = '',

    # Validate-plan parameters
    [string]$Path = '',
    [string]$Directory = '',

    # Copilot parameters
    [string]$Prompt = '',

    # Common parameters
    [string]$Repo = '',
    [switch]$DryRun,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$InformationPreference = 'Continue'

$ScriptDir = $PSScriptRoot

# ---------------------------------------------------------------------------
# Copilot CLI dispatch
# ---------------------------------------------------------------------------

function script:DispatchCopilot {
    param([string]$PromptText)

    if (-not $PromptText) {
        Write-Warning 'Error: copilot action requires a -Prompt string'
        Write-Information 'Usage: .\run-workflow.ps1 -Action copilot -Prompt "your prompt"'
        return 1
    }

    # Strategy 1: Try standalone copilot CLI
    if (Get-Command 'copilot' -ErrorAction SilentlyContinue) {
        Write-Information 'Using standalone copilot CLI...'
        & copilot $PromptText
        return $LASTEXITCODE
    }

    # Strategy 2: Fallback to gh copilot -p
    if (Get-Command 'gh' -ErrorAction SilentlyContinue) {
        Write-Information 'Falling back to gh copilot...'
        & gh copilot -p $PromptText
        return $LASTEXITCODE
    }

    Write-Warning "Error: Neither 'copilot' nor 'gh' CLI is available."
    Write-Information 'Install GitHub CLI (gh) with Copilot extension:'
    Write-Information '  gh extension install github/gh-copilot'
    return 1
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

function script:ShowUsage {
    Write-Information @'
Usage:
  run-workflow.ps1 [-Action <subcommand>] [options]

Actions:
  (default)         Orchestrate a workflow (create Root + Sub-Issues)
  advance           Mark issue done and activate next steps
  create-subissues  Parse subissues.md and create GitHub Issues
  validate-plan     Validate plan.md metadata consistency
  validate-subissues Validate subissues.md metadata consistency
  copilot           Copilot CLI prompt (standalone → gh copilot fallback)
  help              Show this help

Orchestrate Parameters (default action):
  -Workflow, -w <id>    Workflow ID (aas|aad|asdw|abd|abdv|aid)
  -Branch <name>        Target branch (default: main)
  -Steps <csv>          Comma-separated step IDs

Advance Parameters:
  -Issue <number>       Completed issue number

Create-subissues Parameters:
  -File <path>          Path to subissues.md file
  -ParentIssue <num>    Parent issue number

Validate-plan Parameters:
  -Path <path>          Validate a single plan.md
  -Directory <dir>      Recursively validate all plan.md files

Validate-subissues Parameters:
  -Path <path>          Validate a single subissues.md
  -Directory <dir>      Recursively validate all subissues.md files

Copilot Parameters:
  -Prompt <text>        Copilot prompt string

Common Parameters:
  -Repo <owner/repo>    Repository (env: REPO)
  -DryRun               Dry-run mode
  -Help                 Show this help

Examples:
  # Full workflow execution
  $env:REPO = "owner/repo"
  .\run-workflow.ps1 -Workflow aad -Branch main

  # Dry-run with step filter
  .\run-workflow.ps1 -Workflow aad -Steps "1.1,1.2" -DryRun

  # Advance to next steps
  .\run-workflow.ps1 -Action advance -Issue 123 -DryRun

  # Copilot prompt
  .\run-workflow.ps1 -Action copilot -Prompt "仕様を整理して"
'@
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

if ($Help -or $Action -eq 'help') {
    ShowUsage
    exit 0
}

# Build common args
$commonArgs = @{}
if ($Repo) { $commonArgs['Repo'] = $Repo }
if ($DryRun) { $commonArgs['DryRun'] = $true }

switch ($Action) {
    'advance' {
        if (-not $Issue) {
            # Try env var
            if ($env:ISSUE_NO) { $Issue = $env:ISSUE_NO }
            else {
                Write-Warning 'Error: -Issue is required for advance action'
                ShowUsage
                exit 1
            }
        }
        $advanceArgs = @{ Issue = $Issue }
        $advanceArgs += $commonArgs
        & "$ScriptDir/advance.ps1" @advanceArgs
    }

    'create-subissues' {
        if (-not $File) {
            Write-Warning 'Error: -File is required for create-subissues action'
            ShowUsage
            exit 1
        }
        $csArgs = @{ File = $File }
        if ($ParentIssue) { $csArgs['ParentIssue'] = $ParentIssue }
        $csArgs += $commonArgs
        & "$ScriptDir/create-subissues.ps1" @csArgs
    }

    'validate-plan' {
        if (-not $Path -and -not $Directory) {
            Write-Warning 'Error: -Path or -Directory is required for validate-plan action'
            ShowUsage
            exit 1
        }
        $vpArgs = @{}
        if ($Path) { $vpArgs['Path'] = $Path }
        if ($Directory) { $vpArgs['Directory'] = $Directory }
        & "$ScriptDir/validate-plan.ps1" @vpArgs
    }

    'validate-subissues' {
        if (-not $Path -and -not $Directory) {
            Write-Warning 'Error: -Path or -Directory is required for validate-subissues action'
            ShowUsage
            exit 1
        }
        $vsArgs = @{}
        if ($Path) { $vsArgs['Path'] = $Path }
        if ($Directory) { $vsArgs['Directory'] = $Directory }
        & "$ScriptDir/validate-subissues.ps1" @vsArgs
    }

    'copilot' {
        $exitCode = DispatchCopilot -PromptText $Prompt
        exit $exitCode
    }

    default {
        # Default: orchestrate
        if (-not $Workflow) {
            # Try env var
            if ($env:WORKFLOW) { $Workflow = $env:WORKFLOW }
            else {
                Write-Warning 'Error: -Workflow or $env:WORKFLOW is required'
                Write-Information ''
                ShowUsage
                exit 1
            }
        }

        $orchArgs = @{ Workflow = $Workflow }
        if ($Branch -ne 'main') { $orchArgs['Branch'] = $Branch }
        if ($Steps) { $orchArgs['Steps'] = $Steps }
        $orchArgs += $commonArgs
        & "$ScriptDir/orchestrate.ps1" @orchArgs
    }
}
