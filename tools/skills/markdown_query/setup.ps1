# setup.ps1 — Windows setup for the standalone markdown-query GUI.
#
# This script creates a local virtual environment at .venv-mdq-gui, installs
# the dependencies, and (optionally) builds the initial Markdown index.
#
# Usage:
#   pwsh -ExecutionPolicy Bypass -File setup.ps1            # install only
#   pwsh -ExecutionPolicy Bypass -File setup.ps1 -BuildIndex  # also run `mdq index`
#   pwsh -ExecutionPolicy Bypass -File setup.ps1 -Python C:\Python313\python.exe
#
# Requirements: Python 3.11 or newer on PATH (or supplied via -Python).

[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$BuildIndex,
    [switch]$WithWatch,
    # Repository root to operate on when -BuildIndex is set.
    # Default: current working directory at invocation time.
    [string]$RepoRoot = (Get-Location).Path
)

$ErrorActionPreference = "Stop"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir    = Join-Path $ScriptDir ".venv-mdq-gui"
$VendorDir  = Join-Path $ScriptDir "vendor"

Write-Host "[markdown-query gui setup] Python:" $Python
& $Python --version
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python が見つかりません。--Python <path> で指定するか、PATH を確認してください。"
    exit 1
}

if (-not (Test-Path $VenvDir)) {
    Write-Host "[markdown-query gui setup] Creating venv at $VenvDir ..."
    & $Python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[markdown-query gui setup] Installing dependencies (rank_bm25, tiktoken, PySide6)..."
& $VenvPy -m pip install "rank_bm25>=0.2.2" "tiktoken>=0.7.0" "PySide6>=6.6"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($WithWatch) {
    Write-Host "[markdown-query gui setup] Installing watchdog (realtime index update)..."
    & $VenvPy -m pip install "watchdog>=4.0"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not (Test-Path (Join-Path $VendorDir "mdq\__init__.py"))) {
    Write-Error "vendor/mdq/ が見つかりません。リポジトリのコピーが不完全です。"
    exit 2
}

if ($BuildIndex) {
    Write-Host "[markdown-query gui setup] Building initial index at $RepoRoot ..."
    if (-not (Test-Path $RepoRoot)) {
        Write-Error "RepoRoot does not exist: $RepoRoot"
        exit 2
    }
    $env:PYTHONPATH = "$VendorDir;$env:PYTHONPATH"
    Push-Location $RepoRoot
    try {
        & $VenvPy -m mdq index
        if ($LASTEXITCODE -ne 0) { Write-Warning "Initial index build failed (LASTEXITCODE=$LASTEXITCODE)." }
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "[markdown-query gui setup] Done."
Write-Host "Launch the GUI with:  .\launch-gui.cmd"
