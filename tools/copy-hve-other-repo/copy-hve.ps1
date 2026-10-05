# Windows launcher for copy_hve.py. All selection and deletion logic is shared.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Destination,
    [switch]$DryRun,
    [switch]$Yes,
    [string]$Python
)

$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    [Console]::Error.WriteLine('PowerShell 7+ (pwsh.exe) is required.')
    exit 2
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir '..\..')
$Entry = Join-Path $ScriptDir 'copy_hve.py'

if (-not (Test-Path -LiteralPath $Entry -PathType Leaf)) {
    [Console]::Error.WriteLine("copy_hve.py not found: $Entry")
    exit 2
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
        $Python = $VenvPython
    } else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $PythonCommand) {
            [Console]::Error.WriteLine('Python 3.11+ was not found. Run hve\setup-hve.ps1 first.')
            exit 2
        }
        $Python = $PythonCommand.Source
    }
}

$Arguments = @($Entry, $Destination)
if ($DryRun) { $Arguments += '--dry-run' }
if ($Yes) { $Arguments += '--yes' }

& $Python @Arguments
exit $LASTEXITCODE