# validate-plan.ps1 — plan.md 分割判定メタデータ検証
#
# Ported from: .github/scripts/bash/validate-plan.sh
#
# Validates:
#   1. Required metadata presence (estimate_total, split_decision, implementation_files)
#   2. estimate_total vs split_decision consistency
#   3. SPLIT_REQUIRED + implementation_files incompatibility
#   4. SPLIT_REQUIRED → subissues.md existence
#   5. subissues_count vs actual <!-- subissue --> block count
#   6. ## 分割判定 section presence
#
# Usage:
#   .\validate-plan.ps1 -Path work/Issue-123/plan.md
#   .\validate-plan.ps1 -Directory work/
#
# Exit codes:
#   0 — All validations passed
#   1 — Validation errors found

[CmdletBinding()]
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
# Internal helpers
# ---------------------------------------------------------------------------

function script:ExtractInt {
    param([string]$Content, [string]$Key)
    $escaped = [regex]::Escape($Key)
    if ($Content -match "<!--\s*$escaped\s*:\s*(\d+)\s*-->") {
        return [int]$Matches[1]
    }
    return 0
}

function script:ExtractStr {
    param([string]$Content, [string]$Key)
    $escaped = [regex]::Escape($Key)
    if ($Content -match "<!--\s*$escaped\s*:\s*(\S+)\s*-->") {
        return $Matches[1]
    }
    return ''
}

function script:CountSubissueBlocks {
    param([string]$FilePath)
    if (-not (Test-Path $FilePath)) { return 0 }
    $content = Get-Content $FilePath -Raw
    $matches2 = [regex]::Matches($content, '<!--\s*subissue\s*-->')
    return $matches2.Count
}

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

    $estimate = ExtractInt -Content $content -Key 'estimate_total'
    $decision = ExtractStr -Content $content -Key 'split_decision'
    $implFiles = ExtractStr -Content $content -Key 'implementation_files'
    $subissuesCount = ExtractInt -Content $content -Key 'subissues_count'

    # Default decision to MISSING if empty
    if (-not $decision) { $decision = 'MISSING' }
    # Default implFiles to MISSING if empty
    if (-not $implFiles) { $implFiles = 'MISSING' }

    Write-Information "Checking: $PlanPath"
    Write-Information "  Estimate: ${estimate}min | Decision: $decision | Impl files: $implFiles | Subissues count: $subissuesCount"

    # Rule 0: required metadata must exist and have valid values
    if ($decision -eq 'MISSING') {
        $errors += "${PlanPath}: missing required metadata <!-- split_decision: ... -->"
    }
    elseif ($decision -ne 'PROCEED' -and $decision -ne 'SPLIT_REQUIRED') {
        $errors += "${PlanPath}: invalid split_decision='$decision'. Must be PROCEED or SPLIT_REQUIRED"
    }

    if ($estimate -eq 0 -and $content -notmatch 'estimate_total') {
        $errors += "${PlanPath}: missing required metadata <!-- estimate_total: ... -->"
    }

    if ($implFiles -eq 'MISSING') {
        $errors += "${PlanPath}: missing required metadata <!-- implementation_files: ... -->"
    }
    elseif ($implFiles -ne 'true' -and $implFiles -ne 'false') {
        $errors += "${PlanPath}: invalid implementation_files='$implFiles'. Must be true or false"
    }

    # Rule 1: estimate > 15 must be SPLIT_REQUIRED
    if ($estimate -gt 15 -and $decision -eq 'PROCEED') {
        $errors += "${PlanPath}: estimate=${estimate}min > 15min but decision=PROCEED. Must be SPLIT_REQUIRED per Skill task-dag-planning §2.2"
    }

    # Rule 2: SPLIT_REQUIRED must not have implementation files
    if ($decision -eq 'SPLIT_REQUIRED' -and $implFiles -eq 'true') {
        $errors += "${PlanPath}: split_decision=SPLIT_REQUIRED but implementation_files=true. Per Skill task-dag-planning §2.3, implementation files are prohibited in split mode."
    }

    # Rule 3: SPLIT_REQUIRED must have subissues.md in same directory
    if ($decision -eq 'SPLIT_REQUIRED') {
        $planDir = Split-Path $PlanPath -Parent
        $subissuesPath = Join-Path $planDir 'subissues.md'
        if (-not (Test-Path $subissuesPath)) {
            $errors += "${PlanPath}: split_decision=SPLIT_REQUIRED but subissues.md not found in $planDir"
        }
        else {
            # Rule 4: subissues_count should match actual block count
            $actualCount = CountSubissueBlocks -FilePath $subissuesPath
            if ($subissuesCount -ne $actualCount) {
                $errors += "${PlanPath}: subissues_count=$subissuesCount but subissues.md has $actualCount <!-- subissue --> blocks"
            }
        }
    }

    # Rule 5: 分割判定 section should exist
    if ($content -notmatch '## 分割判定') {
        $errors += "${PlanPath}: missing required section '## 分割判定'"
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
