# FR-LOCAL-SURFACE-04: invoked as a file only after the native integrity gate.
[CmdletBinding()]
param(
    [string]$ExpectedVersion,
    [Parameter(Mandatory)][string]$ExpectedExecutable,
    [string]$OwnerPath
)

$ErrorActionPreference = 'Stop'
try {
    $actualExecutable = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { exit 1 }
    if ($ExpectedVersion -and $PSVersionTable.PSVersion.ToString() -cne $ExpectedVersion) { exit 2 }
    if (-not [string]::Equals([IO.Path]::GetFullPath($actualExecutable),
            [IO.Path]::GetFullPath($ExpectedExecutable), [StringComparison]::OrdinalIgnoreCase)) { exit 3 }
    if ($OwnerPath) {
        $env:PSModulePath = Join-Path $PSHOME 'Modules'
        $parentId = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$PID" -Property ParentProcessId).ParentProcessId
        $parent = [Diagnostics.Process]::GetProcessById($parentId)
        if ($parent.ProcessName -ine 'cmd') { exit 4 }
        $started = $parent.StartTime.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss'Z'")
        [IO.File]::WriteAllText($OwnerPath + '.tmp', "PID=$parentId`r`nSTARTED_UTC=$started`r`n", [Text.UTF8Encoding]::new($false))
        [IO.File]::Move($OwnerPath + '.tmp', $OwnerPath, $true)
    }
    Write-Output "edition=Core version=$($PSVersionTable.PSVersion) executable-match=true"
} catch {
    [Console]::Error.WriteLine('BOOTSTRAP_FAIL stage=runtime reason=runtime-check-failed retry=true')
    exit 4
}