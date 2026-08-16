#Requires -Version 7.0
<#
.SYNOPSIS
    Prepare-Windows.cmd の静的契約テスト。
.DESCRIPTION
    対象を実行せず、Windows 11 標準 cmd から必要な準備機ランタイムを導入し、
    指定モデルを取得して Export-OfflineKit.ps1 へ値を渡す契約を確認する。
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$target = Join-Path (Split-Path -Parent $PSScriptRoot) 'Prepare-Windows.cmd'
if (-not [System.IO.File]::Exists($target)) {
    [Console]::Error.WriteLine("RED: Prepare-Windows.cmd が存在しません: $target")
    exit 1
}

$source = [System.IO.File]::ReadAllText($target)
$failures = [System.Collections.Generic.List[string]]::new()

function Assert-Match {
    param([string]$Name, [string]$Pattern)
    if ($source -notmatch $Pattern) { $failures.Add("${Name}: pattern not found: $Pattern") }
}
function Assert-NotMatch {
    param([string]$Name, [string]$Pattern)
    if ($source -match $Pattern) { $failures.Add("${Name}: forbidden pattern found: $Pattern") }
}

Assert-Match 'destination option' '(?i)--destination'
Assert-Match 'model option' '(?i)--model'
Assert-Match 'context option' '(?i)--context-length'
Assert-Match 'default model' '(?i)qwen3:8b'
Assert-Match 'default context' '(?i)8192'
Assert-Match 'script directory captured before shifts' '(?im)^\s*set\s+"SCRIPT_DIR=%~dp0"\s*$'
Assert-Match 'winget guard' '(?i)where\s+winget(?:\.exe)?'
Assert-Match 'PowerShell 7 MSI install' '(?is)winget\s+install.*Microsoft\.PowerShell.*installer-type\s+wix'
Assert-Match 'Python Install Manager install' '(?is)winget\s+install.*9NQ7512CXL7T'
Assert-Match 'Ollama install' '(?is)winget\s+install.*Ollama\.Ollama'
Assert-Match 'PowerShell 7 resolution' '(?i)(ProgramFiles|where\s+pwsh).*pwsh\.exe'
Assert-Match 'Python manager resolution' '(?i)(LOCALAPPDATA|where\s+pymanager).*pymanager\.exe'
Assert-Match 'Python manager packaged resolution' '(?i)PythonSoftwareFoundation\.PythonManager_\*.*pymanager\.exe'
Assert-Match 'Python runtime install uses manager' '(?i)"%PY_MANAGER%"\s+install\s+3\.14-64'
Assert-NotMatch 'legacy py launcher is not selected' '(?i)(where\s+py\.exe|\\py\.exe")'
Assert-Match 'Ollama resolution' '(?i)(LOCALAPPDATA|where\s+ollama).*ollama\.exe'
Assert-Match 'loopback readiness' '(?i)127\.0\.0\.1:11434/(api/tags|v1/models)'
Assert-Match 'finite readiness counter' '(?i)(attempt|count|retry).*(60|30)|(60|30).*(attempt|count|retry)'
Assert-Match 'finite readiness guard' '(?i)if\s+%[A-Z_]*(WAIT|COUNT|RETRY)[A-Z_]*%\s+GEQ\s+(60|30)'
Assert-Match 'model pull' '(?i)ollama(?:\.exe)?.*pull.*MODEL'
Assert-Match 'Export invocation' '(?is)pwsh(?:\.exe)?.*-File\s+"%SCRIPT_DIR%Export-OfflineKit\.ps1"'
Assert-Match 'destination forwarding' '(?is)Export-OfflineKit\.ps1.*-Destination.*DESTINATION'
Assert-Match 'model forwarding' '(?is)Export-OfflineKit\.ps1.*-Model.*MODEL'
Assert-Match 'context forwarding' '(?is)Export-OfflineKit\.ps1.*-ContextLength.*CONTEXT'
Assert-Match 'destination is quoted' '(?i)-Destination\s+"%DESTINATION%"'
Assert-Match 'model is quoted' '(?i)-Model\s+"%MODEL%"'
Assert-Match 'exit propagation' '(?i)exit\s+/b\s+(%ERRORLEVEL%|![A-Za-z_]+!)'
Assert-NotMatch 'Windows PowerShell command prohibited' '(?im)^\s*(?:call\s+)?(?:"[^"]*\\)?powershell(?:\.exe)?"?\s'
Assert-NotMatch 'unbounded network retry prohibited' '(?i)goto\s+:?(wait|retry|poll)\s*$'

if ($failures.Count -gt 0) {
    [Console]::Error.WriteLine("RED: $($failures.Count) Prepare-Windows contract check(s) failed")
    foreach ($failure in $failures) { [Console]::Error.WriteLine("  - $failure") }
    exit 1
}
Write-Host 'GREEN: Prepare-Windows.cmd static contract passed'
exit 0
