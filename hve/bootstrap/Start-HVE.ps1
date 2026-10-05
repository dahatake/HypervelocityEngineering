# FR-LOCAL-SURFACE-04: private Windows distribution launcher (not a setup clone).
[CmdletBinding()]
param(
    [string]$Root = $PSScriptRoot,
    [string]$ExpectedCriticalListHash
)

function Get-HveSetupArgList {
    param([string]$Root)
    @('-NoLogo', '-NoProfile', '-File', (Join-Path $Root 'hve\setup-hve.ps1'),
        '-Yes', '-NoGlobalCleanup')
}

function Get-HveVerifierArgList {
    param([string]$Root)
    @('-I', '-m', 'hve.bootstrap_verify', '--root', $Root, '--json')
}

function Get-HveGuiArgList { @('gui') }

function Sync-HveChildPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @($PSHOME, $machine, $user) | Where-Object { $_ }
    $env:Path = ($parts -join [IO.Path]::PathSeparator)
}

function Resolve-HveBootstrapAction {
    param([string]$State, [int]$VerifierExit)
    $exits = @{ ready = 0; needs_setup = 10; needs_version_decision = 11; blocked = 12 }
    if ($State -cnotin @('ready', 'needs_setup', 'needs_version_decision', 'blocked') -or
        ($exits[$State] -ne $VerifierExit -and -not ($State -ceq 'blocked' -and $VerifierExit -eq 2))) {
        throw 'state-exit-mismatch'
    }
    $actions = @{ ready = 'launch_gui'; needs_setup = 'run_setup'
        needs_version_decision = 'launch_version_entrypoint'; blocked = 'stop' }
    @{ state = $State; verifier_exit = $VerifierExit; action = $actions[$State] }
}

function Resolve-HveChildExit {
    param([string]$Stage, [object]$ChildExit)
    if ($ChildExit -isnot [int]) { throw 'invalid-child-exit' }
    @{ stage = $Stage; exit_code = $ChildExit; launch_gui = ($ChildExit -eq 0) }
}

function New-HveBootstrapProcessInfo {
    param([string]$Root, [string]$Exe, [string[]]$ArgList, [switch]$CaptureOutput,
        [switch]$RedirectInput)
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.UseShellExecute = $false
    $info.WorkingDirectory = $Root
    $info.FileName = $Exe
    foreach ($name in @($info.Environment.Keys)) {
        if ($name -match '^(PYTHON|PIP_)' -or $name -in @('VIRTUAL_ENV', '__PYVENV_LAUNCHER__')) {
            $null = $info.Environment.Remove($name)
        }
    }
    $info.Environment['PYTHONNOUSERSITE'] = '1'
    $info.Environment['PYTHONSAFEPATH'] = '1'
    $info.Environment['PYTHONDONTWRITEBYTECODE'] = '1'
    $info.Environment['PSModulePath'] = Join-Path $PSHOME 'Modules'
    $info.Environment['PATH'] = $PSHOME + [IO.Path]::PathSeparator + $info.Environment['PATH']
    if ([IO.Path]::GetExtension($Exe) -ieq '.cmd') {
        if (@($ArgList).Count -ne 1 -or $ArgList[0] -cne 'gui') { throw 'invalid-entrypoint-arguments' }
        # Expand the path once, in cmd, rather than treating it as shell source.
        $info.FileName = Join-Path ([Environment]::SystemDirectory) 'cmd.exe'
        $info.Environment['HVE_BOOTSTRAP_ENTRY'] = $Exe
        $info.Arguments = '/d /v:off /s /c ""%HVE_BOOTSTRAP_ENTRY%" gui"'
    } else {
        foreach ($argument in $ArgList) { $info.ArgumentList.Add($argument) }
    }
    $info.RedirectStandardOutput = $CaptureOutput
    $info.RedirectStandardError = $CaptureOutput
    $info.RedirectStandardInput = $RedirectInput
    if ($CaptureOutput) {
        $info.StandardOutputEncoding = [Text.UTF8Encoding]::new($false, $true)
        $info.StandardErrorEncoding = [Text.UTF8Encoding]::new($false, $false)
    }
    if ($RedirectInput) { $info.StandardInputEncoding = [Text.UTF8Encoding]::new($false, $true) }
    $info
}

function Invoke-HveBootstrapChild {
    param([string]$Root, [string]$Stage, [string]$Exe, [string[]]$ArgList,
        [switch]$CaptureOutput, [AllowNull()][string]$InputText,
        [int]$TimeoutSeconds = 0)
    $hasInput = $PSBoundParameters.ContainsKey('InputText')
    $info = New-HveBootstrapProcessInfo -Root $Root -Exe $Exe -ArgList $ArgList `
        -CaptureOutput:$CaptureOutput -RedirectInput:$hasInput
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { throw 'child-start-failed' }
        if ($CaptureOutput) {
            $stdout = $process.StandardOutput.ReadToEndAsync()
            $stderr = $process.StandardError.ReadToEndAsync()
        }
        if ($hasInput) {
            $process.StandardInput.Write($InputText)
            $process.StandardInput.Close()
        }
        if ($TimeoutSeconds -gt 0) {
            if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
                $process.Kill($true)
                $process.WaitForExit()
                throw 'child-timeout'
            }
        } else { $process.WaitForExit() }
        $output = if ($CaptureOutput) { $stdout.GetAwaiter().GetResult() } else { '' }
        if ($CaptureOutput) { $null = $stderr.GetAwaiter().GetResult() }
        if (-not $CaptureOutput -and $process.ExitCode -ne 0) {
            [Console]::Error.WriteLine("BOOTSTRAP_FAIL stage=$Stage reason=child-exit retry=true")
        }
        @{ exit_code = $process.ExitCode; stdout = $output }
    } finally { $process.Dispose() }
}

function Validate-BootstrapPayload {
    param([string]$Root, [string]$Json, [int]$VerifierExit)
    # Only the shared T13 validator owns the closed schema and readiness rules.
    # Duplicate JSON members become invalid objects, never last-writer-wins.
    $code = 'import json,sys; from hve.bootstrap_verify import validate_payload; p=json.load(sys.stdin,object_pairs_hook=lambda pairs: dict(pairs) if len(dict(pairs))==len(pairs) else None); e=validate_payload(p,reported_exit=int(sys.argv[1])); sys.exit(2) if e else None; print(p["state"])'
    $child = Invoke-HveBootstrapChild -Root $Root -Stage 'payload' `
        -Exe (Join-Path $Root '.venv\Scripts\python.exe') `
        -ArgList @('-I', '-c', $code, [string]$VerifierExit) -CaptureOutput -InputText $Json -TimeoutSeconds 30
    if ($child.exit_code -ne 0) { throw 'invalid-verifier-payload' }
    Resolve-HveBootstrapAction -State $child.stdout.Trim() -VerifierExit $VerifierExit
}

function Invoke-HveBootstrapSequence {
    param([string]$Root, [string]$InitialState, [int]$InitialExit,
        [scriptblock]$ProcessRunner, [string]$PowerShellExecutable = (Join-Path $PSHOME 'pwsh.exe'))
    if (-not $ProcessRunner) {
        $ProcessRunner = { param($stage, $exe, $argv)
            Invoke-HveBootstrapChild -Root $Root -Stage $stage -Exe $exe -ArgList $argv }
    }
    $plan = Resolve-HveBootstrapAction -State $InitialState -VerifierExit $InitialExit
    if ($plan.action -eq 'stop') { return $InitialExit }
    if ($plan.action -eq 'launch_version_entrypoint') {
        $child = & $ProcessRunner 'version-entrypoint' (Join-Path $Root 'hve.cmd') @(Get-HveGuiArgList)
        return (Resolve-HveChildExit -Stage 'version-entrypoint' -ChildExit $child.exit_code).exit_code
    }
    if ($plan.action -eq 'run_setup') {
        $child = & $ProcessRunner 'setup' $PowerShellExecutable @(Get-HveSetupArgList -Root $Root)
        $result = Resolve-HveChildExit -Stage 'setup' -ChildExit $child.exit_code
        if (-not $result.launch_gui) { return $result.exit_code }
        # setup may install gh/node/copilot and refresh only its child PATH.
        # Rebuild the parent environment before launching the GUI.
        Sync-HveChildPath
        # Design 5.1/5.2: setup owns its final verifier. Never run it a second time.
    }
    $child = & $ProcessRunner 'gui' (Join-Path $Root 'hve.cmd') @(Get-HveGuiArgList)
    (Resolve-HveChildExit -Stage 'gui' -ChildExit $child.exit_code).exit_code
}

function Assert-HvePlainPath {
    param([string]$Root, [string]$Path)
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($base + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'unsafe-path'
    }
    for ($item = $full; $item -and $item.Length -ge $base.Length; $item = [IO.Path]::GetDirectoryName($item)) {
        if ((Test-Path -LiteralPath $item) -and
            ((Get-Item -LiteralPath $item -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'unsafe-path'
        }
    }
}

function Test-HveCriticalPayload {
    param([string]$Root, [string]$ExpectedHash)
    $list = Join-Path $Root 'hve-bootstrap-critical.sha256'
    Assert-HvePlainPath -Root $Root -Path $list
    if ($ExpectedHash -cnotmatch '\A[0-9a-f]{64}\z' -or
        (Get-FileHash -LiteralPath $list -Algorithm SHA256).Hash -ine $ExpectedHash) {
        throw 'critical-list-hash'
    }
    $lines = [IO.File]::ReadAllLines($list)
    if ($lines.Count -eq 0) { throw 'critical-file-hash' }
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($line in $lines) {
        if ($line -cnotmatch '\A([0-9a-f]{64})  ([A-Za-z0-9_./-]+)\z') { throw 'critical-file-hash' }
        $digest = $Matches[1]; $relative = $Matches[2]
        if ($relative.Split('/') -contains '..' -or -not $seen.Add($relative)) { throw 'critical-file-hash' }
        $path = Join-Path $Root $relative
        Assert-HvePlainPath -Root $Root -Path $path
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $digest) {
            throw 'critical-file-hash'
        }
    }
    $required = @('hve-bootstrap-manifest.json', 'pyproject.toml', 'hve/__init__.py',
        'hve/bootstrap_verify.py', 'hve/startup_version.py', 'hve/auth.py',
        'hve/gui/copilot_cli_bridge.py', 'hve/gui/pty_backend.py', 'hve/bootstrap/bootstrap-sources.json',
        'hve/setup-hve.ps1', 'Start-HVE.ps1', 'hve/bootstrap/windows-pwsh-runtime-check.ps1',
        'hve/bootstrap/winget-module-inspect.ps1')
    if ($seen.Count -ne $required.Count) { throw 'critical-file-hash' }
    foreach ($relative in $required) {
        if (-not $seen.Contains($relative)) { throw 'critical-file-hash' }
    }
}

function Get-HveWinGetRepairPlan {
    param([object]$Source)
    if ($Source.repair_live_verified -isnot [bool] -or -not $Source.repair_live_verified) {
        return @{ allowed = $false; reason_code = 'winget-repair-not-live-verified'; argv = @() }
    }
    $expected = @('Repair-WinGetPackageManager', '-Force', '-Latest')
    if (@($Source.repair_argv_candidate).Count -ne 3 -or
        ($Source.repair_argv_candidate -join "`n") -cne ($expected -join "`n") -or
        $Source.candidate_version -cnotmatch '\A[0-9]+\.[0-9]+\.[0-9]+\z' -or
        $Source.package_sha256 -cnotmatch '\A[0-9a-f]{64}\z' -or
        $Source.package_url -cne ('https://www.powershellgallery.com/api/v2/package/Microsoft.WinGet.Client/' + $Source.candidate_version) -or
        (@($Source.redirect_hosts) -join ',') -cne 'www.powershellgallery.com,cdn.powershellgallery.com') {
        throw 'invalid-winget-source'
    }
    @{ allowed = $true; reason_code = 'verified-repair-candidate'; argv = $expected }
}

function Invoke-HvePinnedDownload {
    param([string]$Root, [string]$Url, [string]$Sha256, [string[]]$AllowedHosts,
        [string]$Destination, [scriptblock]$ProcessRunner)
    $uri = [uri]$Url
    if ($uri.Scheme -cne 'https' -or $uri.UserInfo -or -not $uri.IsDefaultPort -or
        $uri.Query -or $uri.Fragment -or $uri.Host -cnotin $AllowedHosts -or
        $Sha256 -cnotmatch '\A[0-9a-f]{64}\z') { throw 'invalid-download-source' }
    Assert-HvePlainPath -Root $Root -Path $Destination
    if (Test-Path -LiteralPath $Destination) { throw 'download-path-exists' }
    if (-not $ProcessRunner) {
        $ProcessRunner = { param($exe, $argv)
            Invoke-HveBootstrapChild -Root $Root -Stage 'download' -Exe $exe -ArgList $argv `
                -CaptureOutput -TimeoutSeconds 330 }
    }
    $argv = @('--disable', '--silent', '--show-error', '--fail', '--location', '--max-redirs', '5',
        '--connect-timeout', '20', '--max-time', '300', '--proto', '=https', '--proto-redir', '=https',
        '--write-out', '%{url_effective}', '--output', $Destination, $Url)
    $result = & $ProcessRunner (Join-Path ([Environment]::SystemDirectory) 'curl.exe') $argv
    if ($result.exit_code -isnot [int] -or $result.exit_code -ne 0) { throw 'download-failed' }
    # The effective URL (possibly signed) stays in memory and is never logged.
    $final = [uri]$result.stdout.Trim()
    if ($final.Scheme -cne 'https' -or $final.UserInfo -or -not $final.IsDefaultPort -or
        $final.Host -cnotin $AllowedHosts) { throw 'redirect-host' }
    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf) -or
        (Get-Item -LiteralPath $Destination).Length -eq 0 -or
        (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ine $Sha256) {
        throw 'download-hash'
    }
}

function Repair-HveWinGet {
    param([string]$Root, [object]$Source)
    $plan = Get-HveWinGetRepairPlan -Source $Source
    if (-not $plan.allowed) { throw $plan.reason_code }
    $directory = Join-Path $Root ('.hve-bootstrap\winget-client-' + [Guid]::NewGuid().ToString('N'))
    Assert-HvePlainPath -Root $Root -Path $directory
    if (Test-Path -LiteralPath $directory) { throw 'repair-path-exists' }
    $null = New-Item -ItemType Directory -Path $directory -ErrorAction Stop
    try {
        $package = Join-Path $directory 'client.zip'
        Invoke-HvePinnedDownload -Root $Root -Url $Source.package_url -Sha256 $Source.package_sha256 `
            -AllowedHosts $Source.redirect_hosts -Destination $package
        $moduleRoot = Join-Path $directory 'module'
        [IO.Compression.ZipFile]::ExtractToDirectory($package, $moduleRoot)
        $child = Invoke-HveBootstrapChild -Root $Root -Stage 'winget-repair' `
            -Exe (Join-Path $PSHOME 'pwsh.exe') -CaptureOutput -TimeoutSeconds 300 `
            -ArgList @('-NoLogo', '-NoProfile', '-File', (Join-Path $Root 'hve\bootstrap\winget-module-inspect.ps1'),
                '-ManifestPath', (Join-Path $moduleRoot 'Microsoft.WinGet.Client.psd1'),
                '-ExpectedVersion', $Source.candidate_version, '-ExpectedModuleBase', $moduleRoot, '-Repair')
        if ($child.exit_code -ne 0) { throw 'winget-repair-failed' }
    } finally {
        Assert-HvePlainPath -Root $Root -Path $directory
        Remove-Item -LiteralPath $directory -Recurse -Force -ErrorAction Stop
        if (Test-Path -LiteralPath $directory) { throw 'cleanup-failed' }
    }
    Write-Host 'BOOTSTRAP_STAGE stage=winget-repair cleanup=true'
}

function Invoke-HveWindowsBootstrap {
    param([string]$Root, [string]$ExpectedCriticalListHash)
    $stage = 'platform'
    try {
        if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7 -or
            -not $IsWindows -or [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
            [Environment]::OSVersion.Version.Build -lt 22000) { throw 'unsupported-platform' }
        $installationType = [Microsoft.Win32.Registry]::GetValue(
            'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'InstallationType', $null)
        if ($installationType -cne 'Client') { throw 'unsupported-platform' }
        $Root = [IO.Path]::GetFullPath($Root)
        $env:PSModulePath = Join-Path $PSHOME 'Modules'
        $stage = 'integrity'
        Test-HveCriticalPayload -Root $Root -ExpectedHash $ExpectedCriticalListHash
        $stage = 'winget-repair'
        $source = Get-Content -LiteralPath (Join-Path $Root 'hve\bootstrap\bootstrap-sources.json') -Raw | ConvertFrom-Json
        $winget = Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        $available = $false
        if ($winget) {
            try {
                $probe = Invoke-HveBootstrapChild -Root $Root -Stage 'winget-probe' -Exe $winget.Source `
                    -ArgList @('--version') -CaptureOutput -TimeoutSeconds 30
                $available = $probe.exit_code -eq 0 -and $probe.stdout.Trim() -match '^v?\d+\.\d+\.\d+'
            } catch { $available = $false }
        }
        if (-not $available) {
            Repair-HveWinGet -Root $Root -Source $source.winget_client
            $env:PATH = $PSHOME + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
            $winget = Get-Command winget.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1
            $probe = Invoke-HveBootstrapChild -Root $Root -Stage 'winget-probe' -Exe $winget.Source `
                -ArgList @('--version') -CaptureOutput -TimeoutSeconds 30
            if ($probe.exit_code -ne 0 -or $probe.stdout.Trim() -notmatch '^v?\d+\.\d+\.\d+') {
                throw 'winget-postcondition-failed'
            }
        }
        $stage = 'setup'
        Invoke-HveBootstrapSequence -Root $Root -InitialState 'needs_setup' -InitialExit 10
    } catch {
        $reason = switch ($_.Exception.Message) {
            'winget-repair-not-live-verified' { 'winget-repair-not-live-verified' }
            'critical-list-hash' { 'critical-list-hash' }
            'critical-file-hash' { 'critical-file-hash' }
            'cleanup-failed' { 'cleanup-failed' }
            default { 'bootstrap-failed' }
        }
        [Console]::Error.WriteLine("BOOTSTRAP_FAIL stage=$stage reason=$reason retry=true")
        if ($stage -in @('platform', 'integrity')) { return 2 }
        return 3
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    $result = Invoke-HveWindowsBootstrap -Root $Root -ExpectedCriticalListHash $ExpectedCriticalListHash
    # Preserve verifier/setup child exits, including their state-specific codes.
    if ($result -eq 10) { exit 10 }
    if ($result -eq 11) { exit 11 }
    if ($result -eq 12) { exit 12 }
    exit $result
}