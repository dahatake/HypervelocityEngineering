# validate-subissues.ps1 — subissues.md メタデータ検証
#
# Validates:
#   1. Each <!-- subissue --> block has <!-- title: ... -->
#   2. title value is not empty
#
# Usage:
#   .\validate-subissues.ps1 -Path work/Issue-123/subissues.md
#   .\validate-subissues.ps1 -Directory work/
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

function script:ValidateSubissues {
    param([string]$SubissuesPath)

    $errors = @()

    if (-not (Test-Path $SubissuesPath)) {
        Write-Error "$SubissuesPath not found"
        return $false
    }

    Write-Information "Checking: $SubissuesPath"

    $content = Get-Content $SubissuesPath -Raw
    $blocks = @([regex]::Split($content, '<!--\s*subissue\s*-->') | Select-Object -Skip 1)

    if ($blocks.Count -eq 0) {
        Write-Information '  ⚠️ No <!-- subissue --> blocks found'
        return $true
    }

    $missingBlocks = @()
    $emptyTitleBlocks = @()

    for ($i = 0; $i -lt $blocks.Count; $i++) {
        $block = $blocks[$i]
        $blockIndex = $i + 1

        $titleMatch = [regex]::Match($block, '<!--\s*title:\s*(.*?)\s*-->')
        if (-not $titleMatch.Success) {
            $missingBlocks += $blockIndex
            continue
        }

        $titleValue = $titleMatch.Groups[1].Value.Trim()
        if (-not $titleValue) {
            $emptyTitleBlocks += $blockIndex
        }
    }

    if ($missingBlocks.Count -gt 0) {
        $errors += "${SubissuesPath}: <!-- title: ... --> 欠落ブロック = [$($missingBlocks -join ',')]"
    }
    if ($emptyTitleBlocks.Count -gt 0) {
        $errors += "${SubissuesPath}: <!-- title: ... --> 空値ブロック = [$($emptyTitleBlocks -join ',')]"
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

function script:ValidateDirectory {
    param([string]$Dir)

    $subissuesFiles = @(Get-ChildItem -Path $Dir -Filter 'subissues.md' -Recurse -File | Sort-Object FullName)

    if ($subissuesFiles.Count -eq 0) {
        Write-Information "No subissues.md files found under $Dir"
        return $true
    }

    $allOk = $true
    foreach ($subissues in $subissuesFiles) {
        if (-not (ValidateSubissues -SubissuesPath $subissues.FullName)) {
            $allOk = $false
        }
    }
    return $allOk
}

function script:ShowUsage {
    Write-Information @'
Usage:
  validate-subissues.ps1 -Path <subissues.md>
  validate-subissues.ps1 -Directory <dir>

Options:
  -Path <path>       Validate a single subissues.md file
  -Directory <dir>   Recursively find and validate all subissues.md files
  -Help              Show this help
'@
}

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
    if (-not (ValidateSubissues -SubissuesPath $Path)) {
        exit 1
    }
}
else {
    if (-not (ValidateDirectory -Dir $Directory)) {
        exit 1
    }
}
