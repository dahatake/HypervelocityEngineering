# sync-vendor.ps1 - Windows launcher for the shared kit sync (FR-KIT-03).
#
# The rules for what ships and what is excluded live in
# tools/skills/_kit/kit_sync.py. Run this inside the upstream repository only;
# downstream copies ship the generated directories as-is.
#
# Usage:
#   pwsh -NoLogo -NoProfile -File sync-vendor.ps1
#   pwsh -NoLogo -NoProfile -File sync-vendor.ps1 -Source C:\path\to\cq

[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$Source = $null,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Entry = Join-Path (Split-Path -Parent $ScriptDir) "_kit\kit_sync.py"

if (-not (Test-Path -LiteralPath $Entry)) {
    [Console]::Error.WriteLine("shared sync implementation not found: $Entry (run this inside the upstream repository)")
    exit 2
}

$Arguments = @("--kit-dir", $ScriptDir)
if ($Source) { $Arguments += @("--source", $Source) }
if ($Rest) { $Arguments += $Rest }

& $Python $Entry @Arguments
exit $LASTEXITCODE
