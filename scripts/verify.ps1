# L1 deterministic verification (plan §10). Exit 0 = pass. Options are passed to verify.py.
$ErrorActionPreference = 'Stop'
$py = $null
foreach ($c in @('python', 'python3', 'py')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch 'WindowsApps\\python') { $py = $c; break }
}
if (-not $py) { Write-Error 'verify: Python 3.9+ が見つかりません'; exit 2 }
$env:PYTHONUTF8 = '1'
& $py (Join-Path $PSScriptRoot 'verify.py') @args
exit $LASTEXITCODE
