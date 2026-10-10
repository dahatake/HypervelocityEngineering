# Usage: .\EABK-Studio\start.ps1 [repo-path] [port] [-Role pm|architect|swe] [-Check] [-NoOpen]
# Other studio.py options can follow, e.g. .\EABK-Studio\start.ps1 . 8765 --no-open
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)][string]$Repo = ".",
    [Parameter(Position = 1)][int]$Port = 8765,
    [ValidateSet("", "pm", "architect", "swe")][string]$Role = "",
    [switch]$Check,
    [switch]$NoOpen,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { Write-Error "Python 3 is required."; exit 1 }
$studioArgs = @("--repo", $Repo, "--port", $Port)
if ($Role) { $studioArgs += @("--role", $Role) }
if ($Check) { $studioArgs += "--check" }
if ($NoOpen) { $studioArgs += "--no-open" }
if ($Rest) { $studioArgs += $Rest }
& $py.Source (Join-Path $PSScriptRoot "studio.py") @studioArgs
exit $LASTEXITCODE
