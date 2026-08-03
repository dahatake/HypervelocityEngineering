# cq.ps1 — Run the vendored code-query CLI from any repository (Windows).
#
# Resolves the interpreter, puts vendor/ on the import path, and forwards every
# argument to `python -m cq`.
#
# Usage:
#   .\cq.ps1 index
#   .\cq.ps1 search --q "resolve_run_id"
#   $env:CQ_PROFILE = "main"   # used when --profile is not given explicitly
#
# Environment:
#   CQ_PYTHON   Interpreter to use (default: .venv-cq if present, else python).
#   CQ_PROFILE  Profile injected when the command line has no --profile.

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VendorDir = Join-Path $ScriptDir "vendor"
$VenvPy    = Join-Path $ScriptDir ".venv-cq\Scripts\python.exe"

if (-not (Test-Path (Join-Path $VendorDir "cq\cli.py"))) {
    Write-Error "vendor/cq is missing. Run: pwsh -NoLogo -NoProfile -File sync-vendor.ps1"
    exit 2
}

$Python = if ($env:CQ_PYTHON) { $env:CQ_PYTHON }
          elseif (Test-Path $VenvPy) { $VenvPy }
          else { "python" }

$Arguments = @()
if ($Rest) { $Arguments = @($Rest) }
if ($env:CQ_PROFILE -and ($Arguments -notcontains "--profile")) {
    $Arguments += @("--profile", $env:CQ_PROFILE)
}

$env:PYTHONPATH = if ($env:PYTHONPATH) { "$VendorDir;$env:PYTHONPATH" } else { $VendorDir }
& $Python -m cq @Arguments
exit $LASTEXITCODE
