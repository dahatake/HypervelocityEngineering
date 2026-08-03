# mdq.ps1 — Run the vendored markdown-query CLI from any repository (Windows).
#
# Resolves the interpreter, puts vendor/ on the import path, and forwards every
# argument to `python -m mdq`.
#
# Usage:
#   .\mdq.ps1 index
#   .\mdq.ps1 search --q "requirement definition"
#
# Environment:
#   MDQ_PYTHON  Interpreter to use (default: .venv-mdq-gui if present, else python).

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VendorDir = Join-Path $ScriptDir "vendor"
$VenvPy    = Join-Path $ScriptDir ".venv-mdq-gui\Scripts\python.exe"

if (-not (Test-Path (Join-Path $VendorDir "mdq\cli.py"))) {
    Write-Error "vendor/mdq is missing. Run: pwsh -NoLogo -NoProfile -File sync-vendor.ps1"
    exit 2
}

$Python = if ($env:MDQ_PYTHON) { $env:MDQ_PYTHON }
          elseif (Test-Path $VenvPy) { $VenvPy }
          else { "python" }

$Arguments = @()
if ($Rest) { $Arguments = @($Rest) }

$env:PYTHONPATH = if ($env:PYTHONPATH) { "$VendorDir;$env:PYTHONPATH" } else { $VendorDir }
& $Python -m mdq @Arguments
exit $LASTEXITCODE
