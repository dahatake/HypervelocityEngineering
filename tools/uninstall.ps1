<#
.SYNOPSIS
  Remove the Enterprise App Build Kit (EABK), installed by any version, from the current (or given) git repository.

.DESCRIPTION
  Runs tools/uninstall.py with tools/uninstall-catalog.json (the content of every file every version shipped).
  Only these two files are downloaded, so it works in any repository, also when the manifest is gone or the
  toolkit was installed by an old version (the "hve" names included).
  Without -Purge: the toolkit files (unmodified ones; modified ones are listed as KEEP-LOCAL), the AGENTS.md /
  copilot-instructions blocks and the manifests are removed; docs, the ledger, the config and /work are kept.
  -Purge: those too, and the toolkit's lines in .gitignore / .gitattributes and the backup files.
  -Runs: also the worktrees and merged run/* branches of the old conductor (otherwise only listed).
  Exit code ($LASTEXITCODE): 0 = nothing remains in the chosen scope, 1 = something remains (RESIDUE), 2 = error.

.EXAMPLE
  # in the root of your repository: look first, then remove everything
  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/uninstall.ps1))) -Purge -DryRun
  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/uninstall.ps1))) -Purge

.EXAMPLE
  # from a local clone of the toolkit
  .\tools\uninstall.ps1 -Target C:\src\my-app -Purge
#>
param(
    [string]$Target = (Get-Location).Path,
    [string]$Ref = $(if ($env:EBAK_REF) { $env:EBAK_REF } else { 'main' }),
    [string]$Repo = $(if ($env:EBAK_REPO) { $env:EBAK_REPO } else { 'dahatake/HypervelocityEngineering' }),
    [switch]$DryRun,
    [switch]$Force,
    [switch]$Purge,
    [switch]$Runs,
    [switch]$AllowNonGit
)
$ErrorActionPreference = 'Stop'

$py = $null
foreach ($c in @('python', 'python3', 'py')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch 'WindowsApps\\python') { $py = $c; break }
}
if (-not $py) { throw 'Python 3.9 以上が必要です（https://www.python.org/downloads/ または winget install Python.Python.3.12）' }

$dir = $null
$tmp = $null
try {
    if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'uninstall.py')) -and (Test-Path (Join-Path $PSScriptRoot 'uninstall-catalog.json'))) {
        $dir = $PSScriptRoot
    } else {
        $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("ebak-uninstall-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $tmp | Out-Null
        foreach ($f in @('uninstall.py', 'uninstall-catalog.json')) {
            $url = "https://raw.githubusercontent.com/$Repo/$Ref/tools/$f"
            Write-Host "download: $url"
            Invoke-WebRequest -Uri $url -OutFile (Join-Path $tmp $f) -UseBasicParsing
        }
        $dir = $tmp
    }

    $argsList = @((Join-Path $dir 'uninstall.py'), '--target', $Target)
    if ($DryRun) { $argsList += '--dry-run' }
    if ($Force) { $argsList += '--force' }
    if ($Purge) { $argsList += '--purge' }
    if ($Runs) { $argsList += '--runs' }
    if ($AllowNonGit) { $argsList += '--allow-non-git' }
    $env:PYTHONUTF8 = '1'
    & $py @argsList
    $code = $LASTEXITCODE
} finally {
    if ($tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
}
if ($code -ne 0) { Write-Warning "uninstall.py exit code $code" }
$global:LASTEXITCODE = $code
