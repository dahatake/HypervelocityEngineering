# toolsearch.ps1 - Run the vendored Tool Search CLI from any repository (Windows).
#
# Kept ASCII-only so Windows PowerShell 5.1 (which reads .ps1 as ANSI) can parse it.
#
# Resolves the interpreter, puts vendor/ on the import path, and forwards every
# argument to `python -m toolsearch`.
#
# Usage:
#   .\toolsearch.ps1 dashboard
#   .\toolsearch.ps1 dashboard --html tool-search.html
#   .\toolsearch.ps1 skills --repo-root .
#
# Environment:
#   TOOLSEARCH_PYTHON  Interpreter to use (default: .venv-toolsearch if present, else python).

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VendorDir = Join-Path $ScriptDir "vendor"
$VenvPy    = Join-Path $ScriptDir ".venv-toolsearch\Scripts\python.exe"

if (-not (Test-Path (Join-Path $VendorDir "toolsearch\cli.py"))) {
    Write-Error "vendor/toolsearch is missing. Re-copy the kit with copy_to_repo.py."
    exit 2
}

$Python = if ($env:TOOLSEARCH_PYTHON) { $env:TOOLSEARCH_PYTHON }
          elseif (Test-Path $VenvPy) { $VenvPy }
          else { "python" }

$Arguments = @()
if ($Rest) { $Arguments = @($Rest) }

$env:PYTHONPATH = if ($env:PYTHONPATH) { "$VendorDir;$env:PYTHONPATH" } else { $VendorDir }
& $Python -m toolsearch @Arguments
exit $LASTEXITCODE
