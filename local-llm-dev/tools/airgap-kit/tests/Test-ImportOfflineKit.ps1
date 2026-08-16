#Requires -Version 7.0
<#
.SYNOPSIS
    WT-02: Windows Import の RED 契約テスト。

.DESCRIPTION
    CONTRACT.md を正本として Import-OfflineKit.ps1 の Windows Import 契約を検査する。
    PowerShell 7 の標準機能だけを使用し、-Apply は決して渡さない。

    動的検査は一時 fixture と隔離したユーザープロファイルだけを使用する。子 PowerShell
    では通信、ファイル変更、インストーラー起動、code/python/ollama 実行を blocker 関数で
    拒否する。実インストール、外部通信、実エンドポイント検証は行わない。
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $IsWindows) {
    [Console]::Error.WriteLine('WT-02 は Windows PowerShell 7 上で実行してください。')
    exit 2
}

$script:KitRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$script:SutPath = Join-Path $script:KitRoot 'Import-OfflineKit.ps1'
$script:Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$script:PwshPath = [Environment]::ProcessPath
if ([string]::IsNullOrWhiteSpace($script:PwshPath)) {
    $script:PwshPath = (Get-Process -Id $PID).Path
}

if (-not [System.IO.File]::Exists($script:SutPath)) {
    [Console]::Error.WriteLine("RED: Windows Import が存在しません: $script:SutPath")
    exit 1
}

$script:SutTokens = $null
$script:SutParseErrors = $null
$script:SutAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $script:SutPath,
    [ref]$script:SutTokens,
    [ref]$script:SutParseErrors
)
if ($script:SutParseErrors.Count -gt 0) {
    [Console]::Error.WriteLine("RED: Import-OfflineKit.ps1 に parser error が $($script:SutParseErrors.Count) 件あります。")
    foreach ($parseError in $script:SutParseErrors) {
        [Console]::Error.WriteLine("  line $($parseError.Extent.StartLineNumber): $($parseError.Message)")
    }
    exit 1
}

function Remove-CommentText {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][System.Management.Automation.Language.Token[]]$Tokens
    )

    $characters = $Source.ToCharArray()
    foreach ($token in $Tokens) {
        if ($token.Kind -ne [System.Management.Automation.Language.TokenKind]::Comment) {
            continue
        }
        for ($offset = $token.Extent.StartOffset; $offset -lt $token.Extent.EndOffset; $offset++) {
            if ($characters[$offset] -notin @("`r", "`n")) {
                $characters[$offset] = ' '
            }
        }
    }
    return -join $characters
}

$script:SutSource = [System.IO.File]::ReadAllText($script:SutPath)
$script:SutCode = Remove-CommentText -Source $script:SutSource -Tokens $script:SutTokens
$script:Failures = [System.Collections.Generic.List[object]]::new()
$script:CheckCount = 0
$script:BaselineDryRunPassed = $false

function Assert-Contract {
    param(
        [Parameter(Mandatory)][bool]$Condition,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Message
    )
    if (-not $Condition) {
        throw [System.InvalidOperationException]::new($Message)
    }
}

function Invoke-ContractCheck {
    param(
        [Parameter(Mandatory)][ValidateRange(1, 8)][int]$Group,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Body
    )

    $script:CheckCount++
    try {
        & $Body
        Write-Host ("ok {0} - ({1}) {2}" -f $script:CheckCount, $Group, $Name)
    }
    catch {
        $failure = [pscustomobject]@{
            Group   = $Group
            Name    = $Name
            Message = $_.Exception.Message
        }
        $script:Failures.Add($failure)
        Write-Host ("not ok {0} - ({1}) {2}: {3}" -f $script:CheckCount, $Group, $Name, $failure.Message) -ForegroundColor Red
    }
}

function Test-CodePattern {
    param([Parameter(Mandatory)][string]$Pattern)
    return [System.Text.RegularExpressions.Regex]::IsMatch(
        $script:SutCode,
        $Pattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase -bor
        [System.Text.RegularExpressions.RegexOptions]::Multiline -bor
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )
}

function Test-IsApplyGuarded {
    param([Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Node)

    $cursor = $Node.Parent
    while ($null -ne $cursor) {
        if ($cursor -is [System.Management.Automation.Language.IfStatementAst]) {
            $conditions = @($cursor.Clauses | ForEach-Object { $_.Item1 })
            $usesApply = @($conditions | ForEach-Object {
                $_.FindAll({
                    param($candidate)
                    $candidate -is [System.Management.Automation.Language.VariableExpressionAst] -and
                    $candidate.VariablePath.UserPath -ieq 'Apply'
                }, $true)
            }).Count -gt 0
            if ($usesApply) {
                return $true
            }
        }
        $cursor = $cursor.Parent
    }
    return $false
}

function Write-FixtureFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Content
    )
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($Path)) | Out-Null
    [System.IO.File]::WriteAllText($Path, $Content, $script:Utf8NoBom)
}

function New-OfflineKitFixture {
    $root = Join-Path ([System.IO.Path]::GetTempPath()) ("wt02-{0}" -f [guid]::NewGuid().ToString('N'))
    $kit = Join-Path $root 'offline-kit'
    $userProfile = Join-Path $root 'state/user-profile'
    $appData = Join-Path $root 'state/appdata'
    $localAppData = Join-Path $root 'state/localappdata'
    $temp = Join-Path $root 'state/temp'

    $pwshStartupCache = Join-Path $userProfile 'AppData/Local/Microsoft/PowerShell'
    foreach ($directory in @($kit, $userProfile, $appData, $localAppData, $temp, $pwshStartupCache)) {
        [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    }

    $payloads = [ordered]@{
        'install-windows.cmd' = "@echo off`r`nexit /b 97`r`n"
        'runtime/powershell/PowerShell-7.5.2-win-x64.msi' = 'WT-02 inert PowerShell installer fixture'
        'runtime/python/python-manager.msixbundle' = 'WT-02 inert Python Install Manager fixture'
        'runtime/python/python-3.13.5-amd64.msix' = 'WT-02 inert Python runtime fixture'
        'runtime/vscode/VSCodeUserSetup-x64.exe' = 'WT-02 inert VS Code installer fixture'
        'runtime/ollama/OllamaSetup.exe' = 'WT-02 inert Ollama installer fixture'
        'models/ollama/blobs/sha256-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' = 'WT-02 inert model blob'
        'models/ollama/manifests/registry.ollama.ai/library/qwen3/8b' = '{"schemaVersion":2,"config":{"digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}'
        'config/chatLanguageModels.json' = '[{"name":"Ollama (local)","vendor":"customendpoint","apiType":"chat-completions","apiKey":"unused","models":[{"id":"qwen3:8b","name":"Qwen3 8B","url":"http://127.0.0.1:11434/v1/chat/completions","toolCalling":true,"maxInputTokens":6144,"maxOutputTokens":2048}]}]'
        'config/settings.offline.json' = '{"extensions.autoUpdate":false,"chat.utilityModel":"qwen3:8b"}'
        'config/ollama-server.json' = '{"disable_ollama_cloud":true}'
        'tools/verify_endpoint.py' = 'raise SystemExit("WT-02 fixture verifier must not run during dry-run")'
        'docs/WINDOWS.md' = '# WT-02 inert Windows guide fixture'
    }

    foreach ($relativePath in $payloads.Keys) {
        Write-FixtureFile -Path (Join-Path $kit $relativePath) -Content $payloads[$relativePath]
    }

    $files = foreach ($relativePath in $payloads.Keys) {
        $fullPath = Join-Path $kit $relativePath
        $item = [System.IO.FileInfo]::new($fullPath)
        [ordered]@{
            path   = $relativePath -replace '\\', '/'
            bytes  = $item.Length
            sha256 = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }

    $manifest = [ordered]@{
        schemaVersion = 1
        createdAt = '2026-08-16T00:00:00Z'
        createdOn = $null
        platform = 'windows'
        architecture = 'x64'
        model = [ordered]@{
            name = 'qwen3:8b'
            digest = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            supportsToolCalling = $true
        }
        contextLength = 8192
        components = @(
            [ordered]@{ name = 'powershell'; required = $true; version = '7.5.2'; path = 'runtime/powershell/PowerShell-7.5.2-win-x64.msi'; sizeMb = 0 }
            [ordered]@{ name = 'python-install-manager'; required = $true; version = '25.0'; path = 'runtime/python/python-manager.msixbundle'; sizeMb = 0 }
            [ordered]@{ name = 'python-runtime'; required = $true; version = '3.13.5'; path = 'runtime/python/python-3.13.5-amd64.msix'; sizeMb = 0 }
            [ordered]@{ name = 'vscode'; required = $true; version = '1.103.0'; path = 'runtime/vscode/VSCodeUserSetup-x64.exe'; sizeMb = 0 }
            [ordered]@{ name = 'ollama'; required = $true; version = '0.11.4'; path = 'runtime/ollama/OllamaSetup.exe'; sizeMb = 0 }
            [ordered]@{ name = 'ollama-model'; required = $true; version = 'qwen3:8b'; path = 'models/ollama'; sizeMb = 0 }
            [ordered]@{ name = 'configuration'; required = $true; version = '1'; path = 'config'; sizeMb = 0 }
            [ordered]@{ name = 'endpoint-verifier'; required = $true; version = '1'; path = 'tools/verify_endpoint.py'; sizeMb = 0 }
            [ordered]@{ name = 'windows-entry'; required = $true; version = '1'; path = 'install-windows.cmd'; sizeMb = 0 }
            [ordered]@{ name = 'windows-guide'; required = $true; version = '1'; path = 'docs/WINDOWS.md'; sizeMb = 0 }
        )
        files = @($files)
    }

    Write-FixtureFile -Path (Join-Path $kit 'manifest.json') -Content ($manifest | ConvertTo-Json -Depth 12)

    return [pscustomobject]@{
        Root = $root
        Kit = $kit
        UserProfile = $userProfile
        AppData = $appData
        LocalAppData = $localAppData
        Temp = $temp
    }
}

function Remove-OfflineKitFixture {
    param([Parameter(Mandatory)]$Fixture)
    if ([System.IO.Directory]::Exists($Fixture.Root)) {
        [System.IO.Directory]::Delete($Fixture.Root, $true)
    }
}

function Get-FixtureManifest {
    param([Parameter(Mandatory)]$Fixture)
    return [System.IO.File]::ReadAllText((Join-Path $Fixture.Kit 'manifest.json')) | ConvertFrom-Json
}

function Set-FixtureManifest {
    param(
        [Parameter(Mandatory)]$Fixture,
        [Parameter(Mandatory)]$Manifest
    )
    Write-FixtureFile -Path (Join-Path $Fixture.Kit 'manifest.json') -Content ($Manifest | ConvertTo-Json -Depth 12)
}

function Get-FixtureSnapshot {
    param([Parameter(Mandatory)]$Fixture)

    $entries = [System.Collections.Generic.List[string]]::new()
    foreach ($base in @($Fixture.Kit, $Fixture.UserProfile, $Fixture.AppData, $Fixture.LocalAppData)) {
        $label = [System.IO.Path]::GetFileName($base)
        foreach ($entry in Get-ChildItem -LiteralPath $base -Force -Recurse | Sort-Object FullName) {
            $relative = [System.IO.Path]::GetRelativePath($base, $entry.FullName) -replace '\\', '/'
            # pwsh 自身が子プロセス起動時に更新するホストキャッシュであり、SUT の導入先ではない。
            if ($label -eq 'user-profile' -and
                $relative -eq 'AppData/Local/Microsoft/PowerShell/StartupProfileData-NonInteractive') {
                continue
            }
            if ($entry.PSIsContainer) {
                $entries.Add("D|$label|$relative")
            }
            else {
                $hash = (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                $entries.Add("F|$label|$relative|$($entry.Length)|$hash")
            }
        }
    }
    return ($entries | Sort-Object) -join "`n"
}

function ConvertTo-PowerShellLiteral {
    param([Parameter(Mandatory)][string]$Value)
    return "'{0}'" -f ($Value -replace "'", "''")
}

function Invoke-ImportDryRun {
    param([Parameter(Mandatory)]$Fixture)

    $harnessRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("wt02-harness-{0}" -f [guid]::NewGuid().ToString('N'))
    [System.IO.Directory]::CreateDirectory($harnessRoot) | Out-Null
    $harnessPath = Join-Path $harnessRoot 'Invoke-BlockedDryRun.ps1'
    $isolatedSutPath = Join-Path $harnessRoot 'Import-OfflineKit.Isolated.ps1'
    $isolatedSutSource = $script:SutSource.Replace(
        '$script:EndpointPort = 11434',
        '$script:EndpointPort = 0')
    if ($isolatedSutSource -ceq $script:SutSource) {
        throw 'fixture isolation could not replace the production endpoint port'
    }
    [System.IO.File]::WriteAllText($isolatedSutPath, $isolatedSutSource, $script:Utf8NoBom)
    $sutLiteral = ConvertTo-PowerShellLiteral -Value $isolatedSutPath
    $kitLiteral = ConvertTo-PowerShellLiteral -Value $Fixture.Kit

    $harnessTemplate = @'
#Requires -Version 7.0
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function global:Invoke-WebRequest { throw 'WT02_BLOCKED_NETWORK: Invoke-WebRequest' }
function global:Invoke-RestMethod { throw 'WT02_BLOCKED_NETWORK: Invoke-RestMethod' }
function global:Start-BitsTransfer { throw 'WT02_BLOCKED_NETWORK: Start-BitsTransfer' }
function global:Get-Process {
    [CmdletBinding()]
    param([string]$Name)
    return @()
}
function global:Start-Process { throw 'WT02_BLOCKED_PROCESS: Start-Process' }
function global:Add-AppxPackage { throw 'WT02_BLOCKED_INSTALL: Add-AppxPackage' }
function global:New-Item { throw 'WT02_BLOCKED_WRITE: New-Item' }
function global:Set-Content { throw 'WT02_BLOCKED_WRITE: Set-Content' }
function global:Add-Content { throw 'WT02_BLOCKED_WRITE: Add-Content' }
function global:Clear-Content { throw 'WT02_BLOCKED_WRITE: Clear-Content' }
function global:Out-File { throw 'WT02_BLOCKED_WRITE: Out-File' }
function global:Copy-Item { throw 'WT02_BLOCKED_WRITE: Copy-Item' }
function global:Move-Item { throw 'WT02_BLOCKED_WRITE: Move-Item' }
function global:Rename-Item { throw 'WT02_BLOCKED_WRITE: Rename-Item' }
function global:Remove-Item { throw 'WT02_BLOCKED_WRITE: Remove-Item' }
function global:code { throw 'WT02_BLOCKED_COMMAND: code' }
function global:code.cmd { throw 'WT02_BLOCKED_COMMAND: code.cmd' }
function global:python { throw 'WT02_BLOCKED_COMMAND: python' }
function global:python.exe { throw 'WT02_BLOCKED_COMMAND: python.exe' }
function global:py { throw 'WT02_BLOCKED_COMMAND: py' }
function global:ollama { throw 'WT02_BLOCKED_COMMAND: ollama' }
function global:ollama.exe { throw 'WT02_BLOCKED_COMMAND: ollama.exe' }
function global:msiexec { throw 'WT02_BLOCKED_INSTALL: msiexec' }
function global:msiexec.exe { throw 'WT02_BLOCKED_INSTALL: msiexec.exe' }
function global:winget { throw 'WT02_BLOCKED_NETWORK: winget' }
function global:winget.exe { throw 'WT02_BLOCKED_NETWORK: winget.exe' }
function global:cmd { throw 'WT02_BLOCKED_PROCESS: cmd' }
function global:cmd.exe { throw 'WT02_BLOCKED_PROCESS: cmd.exe' }

try {
    & __SUT__ -Source __KIT__
    $nativeExitCode = Get-Variable -Name LASTEXITCODE -ValueOnly -ErrorAction SilentlyContinue
    if ($null -ne $nativeExitCode -and $nativeExitCode -ne 0) {
        exit $nativeExitCode
    }
    exit 0
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
'@
    $harness = $harnessTemplate.Replace('__SUT__', $sutLiteral).Replace('__KIT__', $kitLiteral)
    [System.IO.File]::WriteAllText($harnessPath, $harness, $script:Utf8NoBom)

    $environmentNames = @(
        'USERPROFILE', 'HOME', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'PATH',
        'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
        'POWERSHELL_TELEMETRY_OPTOUT', 'DOTNET_CLI_TELEMETRY_OPTOUT'
    )
    $savedEnvironment = @{}
    foreach ($name in $environmentNames) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }

    try {
        $env:USERPROFILE = $Fixture.UserProfile
        $env:HOME = $Fixture.UserProfile
        $env:APPDATA = $Fixture.AppData
        $env:LOCALAPPDATA = $Fixture.LocalAppData
        $env:TEMP = $Fixture.Temp
        $env:TMP = $Fixture.Temp
        $env:PATH = $harnessRoot
        $env:HTTP_PROXY = 'http://127.0.0.1:9'
        $env:HTTPS_PROXY = 'http://127.0.0.1:9'
        $env:ALL_PROXY = 'http://127.0.0.1:9'
        $env:NO_PROXY = 'localhost,127.0.0.1'
        $env:POWERSHELL_TELEMETRY_OPTOUT = '1'
        $env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'

        $outputLines = @(& $script:PwshPath -NoLogo -NoProfile -NonInteractive -File $harnessPath 2>&1)
        $exitCode = $LASTEXITCODE
        return [pscustomobject]@{
            ExitCode = $exitCode
            Output = ($outputLines | ForEach-Object { $_.ToString() }) -join "`n"
        }
    }
    finally {
        foreach ($name in $environmentNames) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
        }
        if ([System.IO.Directory]::Exists($harnessRoot)) {
            [System.IO.Directory]::Delete($harnessRoot, $true)
        }
    }
}

function Get-ExitFailureGuards {
    $guards = [System.Collections.Generic.List[object]]::new()
    $ifStatements = $script:SutAst.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.IfStatementAst]
    }, $true)

    foreach ($ifStatement in $ifStatements) {
        foreach ($clause in $ifStatement.Clauses) {
            $conditionText = $clause.Item1.Extent.Text
            if ($conditionText -notmatch '(?i)(LASTEXITCODE|\.ExitCode)') {
                continue
            }
            if ($conditionText -match '(?i)(LASTEXITCODE|\.ExitCode)\s*-eq\s*0' -and
                $conditionText -notmatch '(?i)-ne|-gt|-not') {
                continue
            }

            $body = $clause.Item2
            $throws = @($body.FindAll({
                param($node)
                $node -is [System.Management.Automation.Language.ThrowStatementAst]
            }, $true))
            $exits = @($body.FindAll({
                param($node)
                $node -is [System.Management.Automation.Language.ExitStatementAst] -and
                $node.Extent.Text -notmatch '(?i)^\s*exit\s+0\s*$'
            }, $true))
            $bodyText = $body.Extent.Text
            $guards.Add([pscustomobject]@{
                Condition = $conditionText
                Body = $bodyText
                Terminates = ($throws.Count -gt 0 -or $exits.Count -gt 0)
                Warns = ($bodyText -match '(?i)\b(?:Write-Warn|Write-Warning)\b')
            })
        }
    }
    return @($guards)
}

Write-Host '# WT-02 Import-OfflineKit.ps1 Windows contract checks'
Write-Host '# Safety: no -Apply, no network, no real installer, temporary fixtures only.'

Invoke-ContractCheck -Group 1 -Name 'verification bypass parameter and variable are absent' -Body {
    $parameterNames = @($script:SutAst.ParamBlock.Parameters | ForEach-Object {
        $_.Name.VariablePath.UserPath
    })
    $bypassParameters = @($parameterNames | Where-Object {
        $_ -match '(?i)^Skip(?:Verify|Hash|Integrity)$'
    })
    $bypassVariables = @($script:SutAst.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.VariableExpressionAst] -and
        $node.VariablePath.UserPath -match '(?i)^Skip(?:Verify|Hash|Integrity)$'
    }, $true))

    Assert-Contract -Condition ($bypassParameters.Count -eq 0) -Message (
        "hash verification bypass parameter is forbidden: {0}" -f ($bypassParameters -join ', ')
    )
    Assert-Contract -Condition ($bypassVariables.Count -eq 0) -Message 'hash verification bypass control flow remains in executable code'
}

Invoke-ContractCheck -Group 2 -Name 'valid default dry-run succeeds without changing kit or isolated destinations' -Body {
    $unguardedDirectExecutions = @($script:SutAst.FindAll({
        param($node)
        if ($node -isnot [System.Management.Automation.Language.CommandAst]) {
            return $false
        }
        $commandName = $node.GetCommandName()
        $isRootedCommand = -not [string]::IsNullOrWhiteSpace($commandName) -and
            [System.IO.Path]::IsPathRooted($commandName)
        $usesCallOperator = $node.InvocationOperator -eq
            [System.Management.Automation.Language.TokenKind]::Ampersand
        return ($isRootedCommand -or $usesCallOperator) -and
            -not (Test-IsApplyGuarded -Node $node)
    }, $true))
    $unsafeLines = @($unguardedDirectExecutions | ForEach-Object {
        $_.Extent.StartLineNumber
    }) -join ', '
    Assert-Contract -Condition ($unguardedDirectExecutions.Count -eq 0) -Message (
        "dry-run safety cannot be isolated: direct process invocation outside an Apply guard at line(s) $unsafeLines"
    )

    $fixture = New-OfflineKitFixture
    try {
        $before = Get-FixtureSnapshot -Fixture $fixture
        $result = Invoke-ImportDryRun -Fixture $fixture
        $after = Get-FixtureSnapshot -Fixture $fixture
        $problems = [System.Collections.Generic.List[string]]::new()
        if ($result.ExitCode -ne 0) {
            $problems.Add("valid dry-run exited $($result.ExitCode): $($result.Output)")
        }
        if ($before -cne $after) {
            $difference = Compare-Object -ReferenceObject ($before -split "`n") -DifferenceObject ($after -split "`n") |
                Select-Object -First 10 | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" }
            $problems.Add(
                "dry-run changed the kit or an isolated installation/configuration destination: $($difference -join '; ')"
            )
        }
        if ($result.Output -match 'WT02_BLOCKED_') {
            $problems.Add('dry-run attempted a blocked network, write, process, installer, or product command')
        }
        Assert-Contract -Condition ($problems.Count -eq 0) -Message ($problems -join '; ')
        $script:BaselineDryRunPassed = $true
    }
    finally {
        Remove-OfflineKitFixture -Fixture $fixture
    }
}

$manifestCases = @(
    [pscustomobject]@{ Name = 'missing schemaVersion'; Mutate = { param($manifest) $manifest.PSObject.Properties.Remove('schemaVersion') } }
    [pscustomobject]@{ Name = 'schemaVersion other than 1'; Mutate = { param($manifest) $manifest.schemaVersion = 2 } }
    [pscustomobject]@{ Name = 'missing platform'; Mutate = { param($manifest) $manifest.PSObject.Properties.Remove('platform') } }
    [pscustomobject]@{ Name = 'platform other than windows'; Mutate = { param($manifest) $manifest.platform = 'macos' } }
    [pscustomobject]@{ Name = 'missing architecture'; Mutate = { param($manifest) $manifest.PSObject.Properties.Remove('architecture') } }
    [pscustomobject]@{ Name = 'Windows architecture other than x64'; Mutate = { param($manifest) $manifest.architecture = 'arm64' } }
)
foreach ($manifestCase in $manifestCases) {
    $caseName = $manifestCase.Name
    $mutator = $manifestCase.Mutate
    Invoke-ContractCheck -Group 3 -Name "manifest rejects $caseName" -Body {
        Assert-Contract -Condition $script:BaselineDryRunPassed -Message 'valid control fixture did not pass; rejection would be ambiguous'
        $fixture = New-OfflineKitFixture
        try {
            $manifest = Get-FixtureManifest -Fixture $fixture
            & $mutator $manifest
            Set-FixtureManifest -Fixture $fixture -Manifest $manifest
            $result = Invoke-ImportDryRun -Fixture $fixture
            Assert-Contract -Condition ($result.ExitCode -ne 0) -Message "invalid manifest was accepted: $caseName"
        }
        finally {
            Remove-OfflineKitFixture -Fixture $fixture
        }
    }
}

$integrityCases = @(
    [pscustomobject]@{
        Name = 'manifest-listed file is missing'
        Mutate = {
            param($fixture)
            [System.IO.File]::Delete((Join-Path $fixture.Kit 'config/settings.offline.json'))
        }
    }
    [pscustomobject]@{
        Name = 'manifest-listed file hash mismatches'
        Mutate = {
            param($fixture)
            [System.IO.File]::AppendAllText((Join-Path $fixture.Kit 'config/settings.offline.json'), "`nchanged", $script:Utf8NoBom)
        }
    }
    [pscustomobject]@{
        Name = 'unlisted extra file exists'
        Mutate = {
            param($fixture)
            Write-FixtureFile -Path (Join-Path $fixture.Kit 'unlisted-extra.txt') -Content 'extra'
        }
    }
    [pscustomobject]@{
        Name = 'manifest path traverses outside the kit'
        Mutate = {
            param($fixture)
            $manifest = Get-FixtureManifest -Fixture $fixture
            $manifest.files = @($manifest.files) + [pscustomobject]@{
                path = '../outside.txt'; bytes = 0; sha256 = ('0' * 64)
            }
            Set-FixtureManifest -Fixture $fixture -Manifest $manifest
        }
    }
    [pscustomobject]@{
        Name = 'manifest contains an absolute path'
        Mutate = {
            param($fixture)
            $manifest = Get-FixtureManifest -Fixture $fixture
            $manifest.files = @($manifest.files) + [pscustomobject]@{
                path = 'C:/outside.txt'; bytes = 0; sha256 = ('0' * 64)
            }
            Set-FixtureManifest -Fixture $fixture -Manifest $manifest
        }
    }
    [pscustomobject]@{
        Name = 'manifest files list is empty'
        Mutate = {
            param($fixture)
            $manifest = Get-FixtureManifest -Fixture $fixture
            $manifest.files = @()
            Set-FixtureManifest -Fixture $fixture -Manifest $manifest
        }
    }
)
foreach ($integrityCase in $integrityCases) {
    $caseName = $integrityCase.Name
    $mutator = $integrityCase.Mutate
    Invoke-ContractCheck -Group 4 -Name "integrity rejects when $caseName" -Body {
        Assert-Contract -Condition $script:BaselineDryRunPassed -Message 'valid control fixture did not pass; rejection would be ambiguous'
        $fixture = New-OfflineKitFixture
        try {
            & $mutator $fixture
            $result = Invoke-ImportDryRun -Fixture $fixture
            Assert-Contract -Condition ($result.ExitCode -ne 0) -Message "integrity violation was accepted: $caseName"
        }
        finally {
            Remove-OfflineKitFixture -Fixture $fixture
        }
    }
}

Invoke-ContractCheck -Group 5 -Name 'PowerShell, Python, VS Code, and Ollama have offline installation paths' -Body {
    $requirements = [ordered]@{
        'PowerShell x64 MSI' = 'runtime[\\/]+powershell.+?\.msi\b'
        'Python Install Manager and runtime' = '(?=.*runtime[\\/]+python)(?=.*python.{0,1000}(?:install.{0,80}manager|manager))(?=.*python.{0,1000}runtime)'
        'VS Code x64 installer' = 'runtime[\\/]+vscode.+?(?:VSCode|Visual\s+Studio\s+Code)'
        'Ollama Windows installer' = 'runtime[\\/]+ollama.+?Ollama'
        'Ollama model cache placement' = 'models[\\/]+ollama'
        'checked process launch' = '(?:Start-Process|Invoke-[A-Za-z0-9_-]*(?:Process|Installer|Command))\b'
    }
    $missing = @($requirements.GetEnumerator() | Where-Object {
        -not (Test-CodePattern -Pattern $_.Value)
    } | ForEach-Object { $_.Key })
    Assert-Contract -Condition ($missing.Count -eq 0) -Message (
        "missing executable offline installation handling: {0}" -f ($missing -join ', ')
    )
}

Invoke-ContractCheck -Group 5 -Name 'Python Install Manager uses unambiguous pymanager command' -Body {
    Assert-Contract -Condition (Test-CodePattern -Pattern 'pymanager(?:\.exe)?') -Message (
        'pymanager.exe is not explicitly resolved'
    )
    Assert-Contract -Condition (-not (Test-CodePattern -Pattern "Get-ApplicationPaths\s+@\('py\.exe'")) -Message (
        'legacy py.exe can be selected as the Python Install Manager'
    )
}

Invoke-ContractCheck -Group 5 -Name 'all fixed configuration artifacts have placement handling' -Body {
    $missing = @(
        'chatLanguageModels\.json',
        'settings\.offline\.json',
        'ollama-server\.json'
    ) | Where-Object { -not (Test-CodePattern -Pattern $_) }
    Assert-Contract -Condition (@($missing).Count -eq 0) -Message (
        "missing configuration handling: {0}" -f ($missing -join ', ')
    )
}

Invoke-ContractCheck -Group 6 -Name 'installer and code failures terminate with a non-zero result' -Body {
    $guards = @(Get-ExitFailureGuards)
    $terminatingGuards = @($guards | Where-Object { $_.Terminates })
    $warningOnlyGuards = @($guards | Where-Object { $_.Warns -and -not $_.Terminates })
    $hasInstallerLaunch = Test-CodePattern -Pattern (
        '(?:Start-Process\b(?=.{0,500}\b-Wait\b)(?=.{0,500}\b-PassThru\b)|' +
        '&\s+[^\r\n]+(?:Setup|Installer|\.msi\b|\.exe\b))'
    )
    $hasCodeInstall = Test-CodePattern -Pattern '(?:\bcode(?:\.cmd)?\b|\$[A-Za-z0-9_]*code[A-Za-z0-9_.]*)[^\r\n]+--install-extension\b'

    $problems = [System.Collections.Generic.List[string]]::new()
    if (-not $hasInstallerLaunch) { $problems.Add('missing waited/direct installer process invocation') }
    if (-not $hasCodeInstall) { $problems.Add('missing code --install-extension invocation') }
    if ($terminatingGuards.Count -eq 0) { $problems.Add('missing throw/non-zero exit for process exit-code failure') }
    if ($warningOnlyGuards.Count -gt 0) {
        $problems.Add("warning-only continuation remains for $($warningOnlyGuards.Count) exit-code failure branch(es)")
    }
    Assert-Contract -Condition ($problems.Count -eq 0) -Message ($problems -join '; ')
}

Invoke-ContractCheck -Group 7 -Name 'different existing settings stop in dry-run without overwrite' -Body {
    Assert-Contract -Condition $script:BaselineDryRunPassed -Message 'valid control fixture did not pass; conflict rejection would be ambiguous'
    $fixture = New-OfflineKitFixture
    try {
        Write-FixtureFile -Path (Join-Path $fixture.AppData 'Code/User/settings.json') -Content '{"extensions.autoUpdate":true}'
        Write-FixtureFile -Path (Join-Path $fixture.AppData 'Code/User/chatLanguageModels.json') -Content '[{"name":"existing-different-model"}]'
        Write-FixtureFile -Path (Join-Path $fixture.UserProfile '.ollama/server.json') -Content '{"disable_ollama_cloud":false}'
        $before = Get-FixtureSnapshot -Fixture $fixture
        $result = Invoke-ImportDryRun -Fixture $fixture
        $after = Get-FixtureSnapshot -Fixture $fixture
        $problems = [System.Collections.Generic.List[string]]::new()
        if ($result.ExitCode -eq 0) { $problems.Add('different existing settings were accepted') }
        if ($before -cne $after) {
            $difference = Compare-Object -ReferenceObject ($before -split "`n") -DifferenceObject ($after -split "`n") |
                Select-Object -First 10 | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" }
            $problems.Add("conflicting existing settings were changed: $($difference -join '; ')")
        }
        Assert-Contract -Condition ($problems.Count -eq 0) -Message ($problems -join '; ')
    }
    finally {
        Remove-OfflineKitFixture -Fixture $fixture
    }
}

Invoke-ContractCheck -Group 7 -Name 'same-content rerun and manual-merge conflict paths are explicit' -Body {
    $hasSameContentSkip = Test-CodePattern -Pattern (
        '(?:Get-FileHash|Compare-Object|SequenceEqual|ReadAllText|-c?eq\b).{0,1600}' +
        '(?:same|identical|unchanged|skip|同一|スキップ)|' +
        '(?:same|identical|unchanged|skip|同一|スキップ).{0,1600}' +
        '(?:Get-FileHash|Compare-Object|SequenceEqual|ReadAllText|-c?eq\b)'
    )
    $hasConflictStop = Test-CodePattern -Pattern (
        '(?:conflict|競合).{0,1200}(?:manual[ -]?merge|手動マージ).{0,1200}(?:\bthrow\b|\bexit\s+(?!0\b))|' +
        '(?:\bthrow\b|\bexit\s+(?!0\b)).{0,1200}(?:conflict|競合).{0,1200}(?:manual[ -]?merge|手動マージ)'
    )
    Assert-Contract -Condition ($hasSameContentSkip -and $hasConflictStop) -Message (
        'missing idempotent same-content skip or fail-closed manual-merge conflict handling'
    )
}

Invoke-ContractCheck -Group 7 -Name 'running Ollama is rejected before Apply' -Body {
    $processCheck = [regex]::Match($script:SutCode, '(?is)' +
        'Get-Process\s+-Name\s+[''\"]ollama\*[''\"].{0,800}' +
        '(?:conflict|競合|実行中).{0,800}' +
        'if\s*\(\s*\$Apply\s*\)\s*\{.{0,800}Get-AppxIdentity')
    Assert-Contract -Condition (
        $processCheck.Success
    ) -Message 'running Ollama is not part of dry-run conflict preflight'
}

Invoke-ContractCheck -Group 7 -Name 'any listener on Ollama endpoint is rejected before Apply' -Body {
    $hasPortProbe = Test-CodePattern -Pattern 'Test-TcpPortInUse\s+-Port\s+\$script:EndpointPort'
    $hasFixedPort = Test-CodePattern -Pattern 'EndpointPort\s*=\s*11434'
    $hasConflict = Test-CodePattern -Pattern 'endpoint port.{0,240}(?:conflict|競合|使用中)'
    Assert-Contract -Condition ($hasPortProbe -and $hasFixedPort -and $hasConflict) -Message (
        'listener on 127.0.0.1:11434 is not part of dry-run conflict preflight')
}

Invoke-ContractCheck -Group 8 -Name 'Agent kit rejects model.supportsToolCalling other than true' -Body {
    Assert-Contract -Condition $script:BaselineDryRunPassed -Message 'valid control fixture did not pass; Agent gate rejection would be ambiguous'
    $fixture = New-OfflineKitFixture
    try {
        $manifest = Get-FixtureManifest -Fixture $fixture
        $manifest.model.supportsToolCalling = $false
        Set-FixtureManifest -Fixture $fixture -Manifest $manifest
        $result = Invoke-ImportDryRun -Fixture $fixture
        Assert-Contract -Condition ($result.ExitCode -ne 0) -Message 'Agent kit accepted model.supportsToolCalling=false'
    }
    finally {
        Remove-OfflineKitFixture -Fixture $fixture
    }
}

Invoke-ContractCheck -Group 8 -Name 'post-install verify_endpoint enforces Agent success and propagates failure' -Body {
    $hasVerifierPath = Test-CodePattern -Pattern 'tools[\\/]+verify_endpoint\.py'
    $hasVerifierArguments = Test-CodePattern -Pattern '(?=.*verify_endpoint\.py)(?=.*--url\b)(?=.*--model\b)'
    $hasExpectedContext = Test-CodePattern -Pattern '(?=.*verify_endpoint\.py)(?=.*--expected-context\b)'
    $hasApplyGate = Test-CodePattern -Pattern '(?:if\s*\([^)]*\$Apply[^)]*\)|if\s+\(.*?\$Apply.*?\)).*?verify_endpoint\.py'
    $hasVerifierFailure = Test-CodePattern -Pattern 'verify_endpoint\.py.{0,3000}(?:LASTEXITCODE|\.ExitCode).{0,800}(?:\bthrow\b|\bexit\s+(?!0\b))'
    $hasFailedVerificationCleanup = Test-CodePattern -Pattern 'verificationSucceeded.{0,5000}finally.{0,1200}Stop-Process.{0,500}ollamaProcess'
    $hasAgentManifestGate = Test-CodePattern -Pattern (
        'supportsToolCalling.{0,500}(?:\$true|true).{0,800}(?:\bthrow\b|\bexit\s+(?!0\b))|' +
        '(?:\bthrow\b|\bexit\s+(?!0\b)).{0,800}supportsToolCalling.{0,500}(?:\$true|true)'
    )
    $hasStrictAgentResult = (Test-CodePattern -Pattern '--require-agent\b') -or (
        (Test-CodePattern -Pattern '結果:\s*すべて\s*OK') -and
        (Test-CodePattern -Pattern '(?:-match|-notmatch|Select-String)') -and
        (Test-CodePattern -Pattern '(?:\bthrow\b|\bexit\s+(?!0\b))')
    )

    $problems = [System.Collections.Generic.List[string]]::new()
    if (-not $hasVerifierPath) { $problems.Add('missing tools/verify_endpoint.py') }
    if (-not $hasVerifierArguments) { $problems.Add('missing verifier invocation with --url and --model') }
    if (-not $hasExpectedContext) { $problems.Add('missing verifier invocation with --expected-context') }
    if (-not $hasApplyGate) { $problems.Add('verifier is not mandatory in the post-install Apply path') }
    if (-not $hasVerifierFailure) { $problems.Add('verifier non-zero status is not propagated') }
    if (-not $hasFailedVerificationCleanup) { $problems.Add('Ollama started by Apply is not stopped after failed verification') }
    if (-not $hasAgentManifestGate) { $problems.Add('supportsToolCalling=true is not fail-closed') }
    if (-not $hasStrictAgentResult) { $problems.Add('Agent warnings can pass without a strict success check') }
    Assert-Contract -Condition ($problems.Count -eq 0) -Message ($problems -join '; ')
}

if ($script:Failures.Count -gt 0) {
    Write-Host ''
    [Console]::Error.WriteLine("RED: $($script:Failures.Count)/$script:CheckCount contract checks failed for $script:SutPath")
    foreach ($group in 1..8) {
        $groupFailures = @($script:Failures | Where-Object { $_.Group -eq $group })
        if ($groupFailures.Count -eq 0) { continue }
        [Console]::Error.WriteLine("  requirement ($group):")
        foreach ($failure in $groupFailures) {
            [Console]::Error.WriteLine("    - $($failure.Name): $($failure.Message)")
        }
    }
    exit 1
}

Write-Host ''
Write-Host "GREEN: all $script:CheckCount Windows Import contract checks passed: $script:SutPath"
exit 0
