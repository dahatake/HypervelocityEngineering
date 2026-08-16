#Requires -Version 7.0
<# Windows offline entry static contract test. The target is never executed. #>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$target = Join-Path (Split-Path -Parent $PSScriptRoot) 'install-windows.cmd'
if (-not [System.IO.File]::Exists($target)) {
    [Console]::Error.WriteLine("RED: Install-Windows.cmd が存在しません: $target")
    exit 1
}
$source = [System.IO.File]::ReadAllText($target)
$failures = [System.Collections.Generic.List[string]]::new()

function Assert-Match([string]$Name, [string]$Pattern) {
    if ($source -notmatch $Pattern) { $failures.Add("${Name}: pattern not found: $Pattern") }
}
function Assert-NotMatch([string]$Name, [string]$Pattern) {
    if ($source -match $Pattern) { $failures.Add("${Name}: forbidden pattern found: $Pattern") }
}

Assert-Match 'Apply option' '(?i)-Apply'
Assert-Match 'kit root captured and trailing separator removed before shifts' '(?im)^\s*for\s+%%I\s+in\s+\("%~dp0[.]"\)\s+do\s+set\s+"KIT_ROOT=%%~fI"\s*$'
Assert-Match 'explicit PowerShell bootstrap option' '(?i)-BootstrapPowerShell'
Assert-Match 'PowerShell MSI path' '(?i)runtime\\powershell\\\*\.msi'
Assert-Match 'MSI uniqueness counter initialization' '(?im)^\s*set\s+"?MSI_COUNT=0"?\s*$'
Assert-Match 'MSI uniqueness check' '(?im)^\s*if\s+not\s+"?%MSI_COUNT%"?=="?1"?\s+exit\s+/b\s+[1-9]'
Assert-Match 'MSI interactive checked execution' '(?im)^\s*start\s+""\s+/wait\s+"%POWERSHELL_MSI%"\s*$'
Assert-Match 'MSI failure check' '(?i)if\s+errorlevel\s+1\s+exit\s+/b'
Assert-Match 'PowerShell 7 resolution' '(?i)(where\s+pwsh|ProgramFiles.*PowerShell.*pwsh\.exe)'
Assert-Match 'Import invocation' '(?is)pwsh(?:\.exe)?.*-File.*Import-OfflineKit\.ps1'
Assert-Match 'Source forwarding without a trailing separator' '(?is)Import-OfflineKit\.ps1.*-Source\s+"%KIT_ROOT%"'
Assert-Match 'conditional Apply forwarding' '(?is)if.*APPLY.*Import-OfflineKit\.ps1.*-Apply'
Assert-Match 'exit propagation' '(?i)exit\s+/b\s+(%ERRORLEVEL%|![A-Za-z_]+!)'
Assert-Match 'bootstrap exit captured' '(?im)^\s*set\s+"BOOTSTRAP_EXIT=%ERRORLEVEL%"\s*$'
Assert-Match 'bootstrap exit propagated' '(?im)^\s*if\s+not\s+"%BOOTSTRAP_EXIT%"=="0"\s+exit\s+/b\s+%BOOTSTRAP_EXIT%\s*$'
Assert-Match 'default missing-pwsh stop' '(?im)^\s*if\s+not\s+defined\s+BOOTSTRAP_POWERSHELL\s+if\s+not\s+defined\s+APPLY\s+exit\s+/b\s+[1-9]'
Assert-NotMatch 'Windows PowerShell command prohibited' '(?im)^\s*(?:call\s+)?(?:"[^"]*\\)?powershell(?:\.exe)?"?\s'
Assert-NotMatch 'verification bypass prohibited' '(?i)SkipVerify|SkipHash'

if ($failures.Count -gt 0) {
    [Console]::Error.WriteLine("RED: $($failures.Count) Install-Windows contract check(s) failed")
    foreach ($failure in $failures) { [Console]::Error.WriteLine("  - $failure") }
    exit 1
}
Write-Host 'GREEN: install-windows.cmd static contract passed'
exit 0
