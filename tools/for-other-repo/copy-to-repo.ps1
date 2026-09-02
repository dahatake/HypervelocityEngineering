# copy-to-repo.ps1 - Windows launcher. copy_to_repo.py owns every decision.
#
# Kept ASCII-only so Windows PowerShell 5.1 (which reads .ps1 as ANSI) can parse it.
#
# Usage:
#   pwsh -NoLogo -NoProfile -File copy-to-repo.ps1 D:\other-repo\tools\hve-kits
#   pwsh -NoLogo -NoProfile -File copy-to-repo.ps1 D:\other-repo\tools -p tool-search
#   pwsh -NoLogo -NoProfile -File copy-to-repo.ps1 --list

[CmdletBinding()]
param(
    [string]$Python = "python",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Entry = Join-Path $ScriptDir "copy_to_repo.py"

if (-not (Test-Path -LiteralPath $Entry)) {
    [Console]::Error.WriteLine("copy_to_repo.py not found: $Entry")
    exit 2
}

& $Python $Entry @Rest
exit $LASTEXITCODE
