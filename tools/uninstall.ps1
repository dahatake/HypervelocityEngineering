<#
.SYNOPSIS
  Uninstall the Enterprise App Build Kit from the current (or given) git repository with one command.

.DESCRIPTION
  Runs tools/install.ps1 with -Uninstall (or -Purge). Without -Purge, unmodified toolkit files, the
  AGENTS.md / copilot-instructions blocks and the manifest are removed; docs, the ledger, the config and
  /work are kept. With -Purge, those are removed too, along with the lines added to .gitignore /
  .gitattributes and the *.ebak-backup-* files.

.EXAMPLE
  # in the root of your repository
  irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/uninstall.ps1 | iex

.EXAMPLE
  # with options (check first, then remove everything including management data)
  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/dahatake/HypervelocityEngineering/main/tools/uninstall.ps1))) -Purge -DryRun

.EXAMPLE
  # from a local clone of the toolkit
  .\tools\uninstall.ps1 -Target C:\src\my-app
#>
param(
    [string]$Target = (Get-Location).Path,
    [string]$Ref = $(if ($env:EBAK_REF) { $env:EBAK_REF } else { 'main' }),
    [string]$Repo = $(if ($env:EBAK_REPO) { $env:EBAK_REPO } else { 'dahatake/HypervelocityEngineering' }),
    [switch]$DryRun,
    [switch]$Force,
    [switch]$Purge
)
$ErrorActionPreference = 'Stop'

$opts = @{ Target = $Target; Ref = $Ref; Repo = $Repo; Uninstall = $true }
if ($DryRun) { $opts.DryRun = $true }
if ($Force) { $opts.Force = $true }
if ($Purge) { $opts.Purge = $true }

$local = if ($PSScriptRoot) { Join-Path $PSScriptRoot 'install.ps1' } else { $null }
if ($local -and (Test-Path $local)) {
    & $local @opts
} else {
    $url = "https://raw.githubusercontent.com/$Repo/$Ref/tools/install.ps1"
    & ([scriptblock]::Create((Invoke-RestMethod -Uri $url -UseBasicParsing))) @opts
}
