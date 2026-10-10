param([string]$Repo = ".", [int]$Port = 8765)
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { Write-Error "Python 3 is required."; exit 1 }
& $py.Source (Join-Path $PSScriptRoot "studio.py") --repo $Repo --port $Port
