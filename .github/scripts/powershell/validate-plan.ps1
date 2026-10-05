# validate-plan.ps1 — plan.md 完了条件検証
#
# Ported from: .github/scripts/bash/validate-plan.sh
#
# Validates:
#   1. ## 完了条件 section presence and non-placeholder content (FR-DOD-02)
#
# Usage:
#   .\validate-plan.ps1 -Path work/Issue-123/plan.md
#   .\validate-plan.ps1 -Directory work/
#
# Exit codes:
#   0 — All validations passed
#   1 — Validation errors found

[CmdletBinding(DefaultParameterSetName = 'Help')]
param(
    [Parameter(ParameterSetName = 'SingleFile')]
    [string]$Path,

    [Parameter(ParameterSetName = 'Directory')]
    [string]$Directory,

    [Parameter()]
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$InformationPreference = 'Continue'

# ---------------------------------------------------------------------------
# validate — validate a single plan.md
# ---------------------------------------------------------------------------

function script:ValidatePlan {
    param([string]$PlanPath)

    $errors = @()

    if (-not (Test-Path $PlanPath)) {
        Write-Error "Error: $PlanPath not found"
        return $false
    }

    $content = Get-Content $PlanPath -Raw

    Write-Information "Checking: $PlanPath"

    # FR-DOD-02: 完了条件 section should exist and have non-placeholder content.
    if ($content -notmatch '## 完了条件') {
        $errors += "${PlanPath}: missing required section '## 完了条件'. See .github/skills/_hve-plan-artifacts/plan-template.md for the required section format"
    }
    else {
        $inDod = $false
        $dodContentFound = $false
        foreach ($line in ($content -split "\r?\n|\r")) {
            if ($line -match '^\s*##\s+完了条件') {
                $inDod = $true
                continue
            }
            if ($inDod -and $line -match '^\s*##\s') {
                $inDod = $false
                continue
            }
            if ($inDod -and $line -notmatch '^\s*(-{3,})?\s*$' -and $line -notmatch '(?i)REPLACE_ME') {
                $dodContentFound = $true
            }
        }
        if (-not $dodContentFound) {
            $errors += "${PlanPath}: section '## 完了条件' has no non-placeholder content. Add at least one verifiable completion condition"
        }
    }

    if ($errors.Count -gt 0) {
        foreach ($err in $errors) {
            Write-Warning "::error::$err"
        }
        return $false
    }

    Write-Information '  ✅ PASS'
    return $true
}

# ---------------------------------------------------------------------------
# validate_directory — find and validate all plan.md files
# ---------------------------------------------------------------------------

function script:ValidateDirectory {
    param([string]$Dir)

    $plans = @(Get-ChildItem -Path $Dir -Filter 'plan.md' -Recurse -File | Sort-Object FullName)

    if ($plans.Count -eq 0) {
        Write-Information "No plan.md files found under $Dir"
        return $true
    }

    $allOk = $true
    foreach ($plan in $plans) {
        if (-not (ValidatePlan -PlanPath $plan.FullName)) {
            $allOk = $false
        }
    }
    return $allOk
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

function script:ShowUsage {
    Write-Information @'
Usage:
  validate-plan.ps1 -Path <plan.md>
  validate-plan.ps1 -Directory <dir>

Options:
  -Path <path>       Validate a single plan.md file
  -Directory <dir>   Recursively find and validate all plan.md files
  -Help              Show this help
'@
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if ($Help) {
    ShowUsage
    exit 0
}

if (-not $Path -and -not $Directory) {
    Write-Warning 'Error: -Path or -Directory is required'
    ShowUsage
    exit 1
}

if ($Path) {
    if (-not (ValidatePlan -PlanPath $Path)) {
        exit 1
    }
}
else {
    if (-not (ValidateDirectory -Dir $Directory)) {
        exit 1
    }
}
