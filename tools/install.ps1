<#
.SYNOPSIS
  Install / update the conductor toolkit into the current (or given) git repository with one command.

.EXAMPLE
  # in the root of your repository (downloads the toolkit from GitHub)
  irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.ps1 | iex

.EXAMPLE
  # with options
  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/install.ps1))) -DryRun

.EXAMPLE
  # from a local clone of the toolkit
  .\tools\install.ps1 -Target C:\src\my-app
#>
param(
    [string]$Target = (Get-Location).Path,
    [string]$Ref = $(if ($env:HVE_REF) { $env:HVE_REF } else { 'main' }),
    [string]$Repo = $(if ($env:HVE_REPO) { $env:HVE_REPO } else { 'dahatake/HypervelocityEngineering' }),
    [switch]$DryRun,
    [switch]$Check,
    [switch]$Force,
    [switch]$NoCi,
    [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'

$py = $null
foreach ($c in @('python', 'python3', 'py')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch 'WindowsApps\\python') { $py = $c; break }
}
if (-not $py) { throw 'Python 3.9 以上が必要です（https://www.python.org/downloads/ または winget install Python.Python.3.12）' }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git が必要です' }

$source = $null
$tmp = $null
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'install.py'))) {
    $source = Split-Path $PSScriptRoot -Parent
} else {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("hve-toolkit-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $zip = Join-Path $tmp 'toolkit.zip'
    $url = "https://codeload.github.com/$Repo/zip/$Ref"
    Write-Host "download: $url"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp
    $source = (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName
    $env:HVE_SOURCE_LABEL = "$Repo@$Ref"
}

try {
    $argsList = @((Join-Path $source 'tools/install.py'), '--source', $source, '--target', $Target)
    if ($DryRun) { $argsList += '--dry-run' }
    if ($Check) { $argsList += '--check' }
    if ($Force) { $argsList += '--force' }
    if ($NoCi) { $argsList += '--no-ci' }
    if ($Uninstall) { $argsList += '--uninstall' }
    $env:PYTHONUTF8 = '1'
    & $py @argsList
    $code = $LASTEXITCODE
} finally {
    if ($tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
}
if ($code -ne 0) { Write-Warning "install.py exit code $code" }
