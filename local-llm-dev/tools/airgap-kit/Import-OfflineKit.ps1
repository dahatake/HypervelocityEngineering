#Requires -Version 7.0
<#
.SYNOPSIS
    Windows 11 x64 の運用機へ Offline Kit を導入する。

.DESCRIPTION
    manifest と全 payload を fail-closed で検証し、導入先を全件 preflight する。
    既定は書込みも外部プロセス実行もしない dry-run。-Apply 指定時だけ、検証済み
    payload の対話導入、固定設定・モデル配置、Ollama loopback 検証を行う。

.PARAMETER Source
    Export-OfflineKit.ps1 が生成した Offline Kit のディレクトリ。

.PARAMETER Apply
    検証済みの導入予定を実際に適用する。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Source,
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:PathComparison = [StringComparison]::OrdinalIgnoreCase
$script:EndpointUrl = 'http://127.0.0.1:11434'
$script:EndpointPort = 11434

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Note {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "    $Message"
}

function Write-Plan {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "    [予定] $Message" -ForegroundColor DarkGray
}

function Get-RequiredProperty {
    param(
        [Parameter(Mandatory)][object]$Object,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Context
    )

    $property = @($Object.PSObject.Properties | Where-Object { $_.Name -ceq $Name })
    if ($property.Count -ne 1) {
        throw "$Context に必須フィールド '$Name' がありません。"
    }
    return $property[0].Value
}

function Test-JsonInteger {
    param([AllowNull()][object]$Value)
    return $Value -is [byte] -or $Value -is [sbyte] -or
        $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64]
}

function Resolve-KitPath {
    param([Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$RelativePath)

    if ([System.IO.Path]::IsPathRooted($RelativePath) -or
        $RelativePath -match '^[A-Za-z]:' -or
        $RelativePath.StartsWith('\\', [StringComparison]::Ordinal)) {
        throw "manifest に絶対パスが含まれています: $RelativePath"
    }
    $segments = @($RelativePath -split '[\\/]')
    if ($segments.Count -eq 0 -or @($segments | Where-Object {
        [string]::IsNullOrWhiteSpace($_) -or $_ -eq '.' -or $_ -eq '..'
    }).Count -gt 0) {
        throw "manifest にパストラバーサルまたは曖昧な path が含まれています: $RelativePath"
    }
    if (@($segments | Where-Object {
        $_ -match '[\x00-\x1f:*?"<>|]' -or $_.EndsWith(' ') -or $_.EndsWith('.')
    }).Count -gt 0) {
        throw "manifest に Windows で安全に扱えない path が含まれています: $RelativePath"
    }

    $resolved = [System.IO.Path]::GetFullPath(
        [System.IO.Path]::Combine($script:SourceRoot, ($RelativePath -replace '/', '\')))
    $prefix = $script:SourceRoot.TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($prefix, $script:PathComparison)) {
        throw "manifest が Offline Kit 外を参照しています: $RelativePath"
    }
    return $resolved
}

function ConvertTo-NormalizedVersion {
    param([AllowNull()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    $match = [regex]::Match($Value, '(?<!\d)(\d+(?:\.\d+){1,3})(?!\d)')
    if (-not $match.Success) { return $null }
    $parts = [System.Collections.Generic.List[int]]::new()
    foreach ($part in $match.Groups[1].Value.Split('.')) { $parts.Add([int]$part) }
    while ($parts.Count -gt 2 -and $parts[$parts.Count - 1] -eq 0) {
        $parts.RemoveAt($parts.Count - 1)
    }
    return $parts -join '.'
}

function Test-SameVersion {
    param([AllowNull()][string]$Expected, [AllowNull()][string]$Actual)
    $expectedVersion = ConvertTo-NormalizedVersion $Expected
    $actualVersion = ConvertTo-NormalizedVersion $Actual
    return $null -ne $expectedVersion -and $null -ne $actualVersion -and
        $expectedVersion -ceq $actualVersion
}

function Get-FileVersion {
    param([Parameter(Mandatory)][string]$Path)
    try {
        $info = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($Path)
        return @($info.ProductVersion, $info.FileVersion) |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Select-Object -First 1
    }
    catch { return $null }
}

function Get-ApplicationPaths {
    param([Parameter(Mandatory)][string[]]$Names)
    $result = [System.Collections.Generic.List[string]]::new()
    foreach ($name in $Names) {
        foreach ($command in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            if ([System.IO.File]::Exists($command.Source) -and -not $result.Contains($command.Source)) {
                $result.Add($command.Source)
            }
        }
    }
    return @($result)
}

function Find-VSCode {
    $root = Join-Path $env:LOCALAPPDATA 'Programs/Microsoft VS Code'
    $officialExe = Join-Path $root 'Code.exe'
    $officialCli = Join-Path $root 'bin/code.cmd'
    if ([System.IO.File]::Exists($officialExe)) {
        return [pscustomobject]@{
            Exe = $officialExe
            Cli = if ([System.IO.File]::Exists($officialCli)) { $officialCli } else { $officialExe }
        }
    }
    foreach ($path in @(Get-ApplicationPaths @('code.cmd', 'code.exe', 'code'))) {
        if ([System.IO.Path]::GetFileName($path) -ieq 'code.cmd') {
            $exe = Join-Path (Split-Path -Parent (Split-Path -Parent $path)) 'Code.exe'
            if ([System.IO.File]::Exists($exe)) { return [pscustomobject]@{ Exe = $exe; Cli = $path } }
        }
        elseif ([System.IO.Path]::GetFileName($path) -ieq 'code.exe') {
            return [pscustomobject]@{ Exe = $path; Cli = $path }
        }
    }
    return $null
}

function Find-Ollama {
    $official = Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe'
    if ([System.IO.File]::Exists($official)) { return $official }
    return @(Get-ApplicationPaths @('ollama.exe', 'ollama')) | Select-Object -First 1
}

function Find-PyManager {
    $windowsApps = Join-Path $env:LOCALAPPDATA 'Microsoft/WindowsApps'
    $official = Join-Path $windowsApps 'pymanager.exe'
    if ([System.IO.File]::Exists($official)) { return $official }
    foreach ($packageDirectory in @(Get-ChildItem -LiteralPath $windowsApps -Directory `
        -Filter 'PythonSoftwareFoundation.PythonManager_*' -ErrorAction SilentlyContinue)) {
        $packagedCommand = Join-Path $packageDirectory.FullName 'pymanager.exe'
        if ([System.IO.File]::Exists($packagedCommand)) { return $packagedCommand }
    }
    return @(Get-ApplicationPaths @('pymanager.exe', 'pymanager')) | Select-Object -First 1
}

function Update-ProcessPath {
    $parts = [System.Collections.Generic.List[string]]::new()
    foreach ($scope in @('Machine', 'User')) {
        foreach ($part in @([Environment]::GetEnvironmentVariable('Path', $scope) -split ';')) {
            if (-not [string]::IsNullOrWhiteSpace($part) -and -not $parts.Contains($part)) {
                $parts.Add($part)
            }
        }
    }
    foreach ($candidate in @(
        (Join-Path $env:LOCALAPPDATA 'Microsoft/WindowsApps'),
        (Join-Path $env:LOCALAPPDATA 'Programs/Microsoft VS Code/bin'),
        (Join-Path $env:LOCALAPPDATA 'Programs/Ollama')
    )) {
        if ([System.IO.Directory]::Exists($candidate) -and -not $parts.Contains($candidate)) {
            $parts.Add($candidate)
        }
    }
    $env:PATH = $parts -join ';'
}

function Get-DestinationProblem {
    param([Parameter(Mandatory)][string]$Path)
    $cursor = [System.IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        if ([System.IO.File]::Exists($cursor) -or [System.IO.Directory]::Exists($cursor)) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                return "reparse point があります: $cursor"
            }
        }
        $parent = [System.IO.Path]::GetDirectoryName($cursor)
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -ceq $cursor) { break }
        if ([System.IO.File]::Exists($parent)) { return "親 path が file です: $parent" }
        $cursor = $parent
    }
    return $null
}

function Get-AppxIdentity {
    param([Parameter(Mandatory)][string]$Path)
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entry = $archive.Entries | Where-Object {
            $_.FullName -ieq 'AppxManifest.xml' -or
            $_.FullName -ieq 'AppxMetadata/AppxBundleManifest.xml'
        } | Select-Object -First 1
        if ($null -eq $entry) { throw "Appx manifest がありません: $Path" }
        $reader = [System.IO.StreamReader]::new($entry.Open())
        try { [xml]$xml = $reader.ReadToEnd() } finally { $reader.Dispose() }
    }
    finally { $archive.Dispose() }
    $identity = $xml.SelectSingleNode(
        '/*[local-name()="Bundle" or local-name()="Package"]/*[local-name()="Identity"]')
    if ($null -eq $identity -or [string]::IsNullOrWhiteSpace([string]$identity.Name) -or
        [string]::IsNullOrWhiteSpace([string]$identity.Version)) {
        throw "Appx identity を取得できません: $Path"
    }
    return [pscustomobject]@{ Name = [string]$identity.Name; Version = [string]$identity.Version }
}

function Test-OllamaLoopback {
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(2)
    try {
        $response = $client.GetAsync("$script:EndpointUrl/api/tags").GetAwaiter().GetResult()
        try { return $response.IsSuccessStatusCode } finally { $response.Dispose() }
    }
    catch { return $false }
    finally { $client.Dispose(); $handler.Dispose() }
}

function Test-TcpPortInUse {
    param([Parameter(Mandatory)][int]$Port)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        return $task.Wait(500) -and $client.Connected
    }
    catch { return $false }
    finally { $client.Dispose() }
}

if (-not $IsWindows) { throw 'Windows 11 x64 で実行してください。' }
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 以上で実行してください。'
}
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne
    [System.Runtime.InteropServices.Architecture]::X64) {
    throw 'x64 以外の Windows は保証対象外です。'
}
if ([Environment]::OSVersion.Version.Build -lt 22000) {
    throw 'Windows 11（build 22000 以上）で実行してください。'
}
if (-not [System.IO.Directory]::Exists($Source)) { throw "Source がありません: $Source" }

$script:SourceRoot = [System.IO.Path]::TrimEndingDirectorySeparator(
    [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Source).ProviderPath))
$manifestPath = Join-Path $script:SourceRoot 'manifest.json'
if (-not [System.IO.File]::Exists($manifestPath)) { throw "manifest.json がありません: $manifestPath" }
try {
    $manifest = [System.IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
}
catch { throw "manifest.json を読み取れません: $($_.Exception.Message)" }
if ($manifest -isnot [pscustomobject]) { throw 'manifest root は JSON object でなければなりません。' }

Write-Step 'manifest schema を fail-closed で検証します'
$schemaVersion = Get-RequiredProperty $manifest 'schemaVersion' 'manifest'
if (-not (Test-JsonInteger $schemaVersion) -or [int64]$schemaVersion -ne 1) {
    throw 'manifest.schemaVersion は整数 1 でなければなりません。'
}
$createdAt = Get-RequiredProperty $manifest 'createdAt' 'manifest'
$createdAtIsUtc = $false
if ($createdAt -is [string] -and $createdAt.EndsWith('Z', [StringComparison]::Ordinal)) {
    try {
        $createdAtValue = [DateTimeOffset]::Parse(
            $createdAt,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::RoundtripKind)
        $createdAtIsUtc = $createdAtValue.Offset -eq [TimeSpan]::Zero
    }
    catch {
        $createdAtIsUtc = $false
    }
}
elseif ($createdAt -is [DateTime]) {
    $createdAtIsUtc = $createdAt.Kind -eq [DateTimeKind]::Utc
}
elseif ($createdAt -is [DateTimeOffset]) {
    $createdAtIsUtc = $createdAt.Offset -eq [TimeSpan]::Zero
}
if (-not $createdAtIsUtc) {
    throw 'manifest.createdAt は UTC の ISO 8601 文字列でなければなりません。'
}
$platform = Get-RequiredProperty $manifest 'platform' 'manifest'
if ($platform -isnot [string] -or $platform -cne 'windows') {
    throw 'manifest.platform は windows でなければなりません。'
}
$architecture = Get-RequiredProperty $manifest 'architecture' 'manifest'
if ($architecture -isnot [string] -or $architecture -cne 'x64') {
    throw 'manifest.architecture は x64 でなければなりません。'
}
$model = Get-RequiredProperty $manifest 'model' 'manifest'
if ($model -isnot [pscustomobject]) { throw 'manifest.model は JSON object でなければなりません。' }
$modelName = Get-RequiredProperty $model 'name' 'manifest.model'
$modelDigest = Get-RequiredProperty $model 'digest' 'manifest.model'
$supportsToolCalling = Get-RequiredProperty $model 'supportsToolCalling' 'manifest.model'
if ($modelName -isnot [string] -or [string]::IsNullOrWhiteSpace($modelName) -or
    $modelName -match '[\x00-\x1f]') { throw 'manifest.model.name が不正です。' }
if ($modelDigest -isnot [string] -or $modelDigest -notmatch '^(?:sha256:)?[0-9a-fA-F]{12,64}$') {
    throw 'manifest.model.digest が不正です。'
}
if ($supportsToolCalling -isnot [bool] -or -not $supportsToolCalling) {
    throw 'Agent 用 kit は manifest.model.supportsToolCalling=true が必須です。'
}
$contextLength = Get-RequiredProperty $manifest 'contextLength' 'manifest'
if (-not (Test-JsonInteger $contextLength) -or [int64]$contextLength -le 0 -or
    [int64]$contextLength -gt [int32]::MaxValue) {
    throw 'manifest.contextLength は正の 32-bit 整数でなければなりません。'
}
$contextLength = [int]$contextLength

$components = @(Get-RequiredProperty $manifest 'components' 'manifest')
if ($components.Count -eq 0) { throw 'manifest.components は空にできません。' }
$componentPathRules = [ordered]@{
    'powershell' = '^runtime/powershell/.+\.msi$'
    'python-install-manager' = '^runtime/python/.+\.(?:msix|msixbundle|appx|appxbundle)$'
    'python-runtime' = '^runtime/python/'
    'vscode' = '^runtime/vscode/VSCodeUserSetup-x64\.exe$'
    'ollama' = '^runtime/ollama/OllamaSetup\.exe$'
    'ollama-model' = '^models/ollama$'
    'configuration' = '^config$'
    'importer' = '^Import-OfflineKit\.ps1$'
    'endpoint-verifier' = '^tools/verify_endpoint\.py$'
    'windows-entry' = '^install-windows\.cmd$'
    'windows-guide' = '^docs/WINDOWS\.md$'
}
$requiredComponents = @(
    'powershell', 'python-install-manager', 'python-runtime', 'vscode', 'ollama',
    'ollama-model', 'configuration', 'endpoint-verifier', 'windows-entry', 'windows-guide'
)
$componentMap = @{}
foreach ($component in $components) {
    if ($component -isnot [pscustomobject]) { throw 'component は JSON object でなければなりません。' }
    $name = Get-RequiredProperty $component 'name' 'component'
    $required = Get-RequiredProperty $component 'required' "component '$name'"
    $version = Get-RequiredProperty $component 'version' "component '$name'"
    $path = Get-RequiredProperty $component 'path' "component '$name'"
    if ($name -isnot [string] -or -not $componentPathRules.Contains($name)) {
        throw "未対応 component です: $name"
    }
    if ($componentMap.ContainsKey($name)) { throw "component が重複しています: $name" }
    if ($required -isnot [bool] -or -not $required) { throw "component '$name' は required=true が必須です。" }
    if ($version -isnot [string] -or [string]::IsNullOrWhiteSpace($version)) {
        throw "component '$name' の version が不正です。"
    }
    if ($path -isnot [string] -or [string]::IsNullOrWhiteSpace($path)) {
        throw "component '$name' の path が不正です。"
    }
    $relativePath = $path.Replace('\', '/')
    if ($relativePath -notmatch $componentPathRules[$name]) {
        throw "component '$name' の path が固定構造と一致しません: $path"
    }
    $fullPath = Resolve-KitPath $path
    if (-not [System.IO.File]::Exists($fullPath) -and -not [System.IO.Directory]::Exists($fullPath)) {
        throw "component '$name' が欠落しています: $path"
    }
    $componentMap[$name] = [pscustomobject]@{
        Version = $version; RelativePath = $relativePath; FullPath = $fullPath
    }
}
foreach ($name in $requiredComponents) {
    if (-not $componentMap.ContainsKey($name)) { throw "必須 component がありません: $name" }
}

Write-Step '全 listed file の bytes と SHA-256 を検証します'
$files = @(Get-RequiredProperty $manifest 'files' 'manifest')
if ($files.Count -eq 0) { throw 'manifest.files は空にできません。' }
$listed = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$verifiedFiles = [System.Collections.Generic.List[object]]::new()
foreach ($entry in $files) {
    if ($entry -isnot [pscustomobject]) { throw 'file entry は JSON object でなければなりません。' }
    $path = Get-RequiredProperty $entry 'path' 'file entry'
    $bytes = Get-RequiredProperty $entry 'bytes' "file '$path'"
    $sha256 = Get-RequiredProperty $entry 'sha256' "file '$path'"
    if ($path -isnot [string] -or [string]::IsNullOrWhiteSpace($path)) { throw 'file.path が不正です。' }
    $fullPath = Resolve-KitPath $path
    if ($fullPath.Equals($manifestPath, $script:PathComparison)) {
        throw 'manifest.json 自身を files に含めることはできません。'
    }
    if (-not $listed.Add($fullPath)) { throw "file.path が重複しています: $path" }
    if (-not (Test-JsonInteger $bytes) -or [int64]$bytes -lt 0) { throw "file.bytes が不正です: $path" }
    if ($sha256 -isnot [string] -or $sha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "file.sha256 が不正です: $path"
    }
    if (-not [System.IO.File]::Exists($fullPath)) { throw "manifest-listed file が欠落しています: $path" }
    $info = [System.IO.FileInfo]::new($fullPath)
    if ($info.Length -ne [int64]$bytes) {
        throw "bytes が一致しません: $path (expected $bytes, actual $($info.Length))"
    }
    if ((Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash -ine $sha256) {
        throw "SHA-256 が一致しません: $path"
    }
    $verifiedFiles.Add([pscustomobject]@{ RelativePath = $path.Replace('\', '/'); FullPath = $fullPath })
}
$kitEntries = @(Get-ChildItem -LiteralPath $script:SourceRoot -Force -Recurse -ErrorAction Stop)
$reparse = @($kitEntries | Where-Object {
    ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
})
if ($reparse.Count -gt 0) { throw "kit 内の reparse point は禁止です: $($reparse[0].FullName)" }
$extra = @($kitEntries | Where-Object {
    -not $_.PSIsContainer -and -not $_.FullName.Equals($manifestPath, $script:PathComparison) -and
    -not $listed.Contains([System.IO.Path]::GetFullPath($_.FullName))
})
if ($extra.Count -gt 0) {
    $firstExtra = [System.IO.Path]::GetRelativePath($script:SourceRoot, $extra[0].FullName)
    throw "manifest 未記載 file が $($extra.Count) 件あります: $firstExtra"
}
Write-Note "$($verifiedFiles.Count) files の missing / extra / bytes / SHA-256 を検証済み"

$powerShellMsi = $componentMap['powershell'].FullPath
$pythonManagerPackage = $componentMap['python-install-manager'].FullPath
$vscodeInstaller = $componentMap['vscode'].FullPath
$ollamaInstaller = $componentMap['ollama'].FullPath
$modelSource = Resolve-KitPath 'models/ollama'
$chatModelsSource = Resolve-KitPath 'config/chatLanguageModels.json'
$settingsSource = Resolve-KitPath 'config/settings.offline.json'
$ollamaSettingsSource = Resolve-KitPath 'config/ollama-server.json'
$verifierPath = Resolve-KitPath 'tools/verify_endpoint.py'
foreach ($path in @(
    $powerShellMsi, $pythonManagerPackage, $vscodeInstaller, $ollamaInstaller,
    $chatModelsSource, $settingsSource, $ollamaSettingsSource, $verifierPath
)) {
    if (-not [System.IO.File]::Exists($path)) { throw "必須 payload が欠落しています: $path" }
}
if (-not [System.IO.Directory]::Exists($modelSource)) { throw 'models/ollama が欠落しています。' }

try {
    $chatModelsConfig = [System.IO.File]::ReadAllText($chatModelsSource) | ConvertFrom-Json
    $offlineSettingsConfig = [System.IO.File]::ReadAllText($settingsSource) | ConvertFrom-Json
    $ollamaSettingsConfig = [System.IO.File]::ReadAllText($ollamaSettingsSource) | ConvertFrom-Json
}
catch { throw "config JSON を読み取れません: $($_.Exception.Message)" }
$configuredModels = @($chatModelsConfig | ForEach-Object { @($_.models) } | ForEach-Object { $_ })
$matchingModels = @($configuredModels | Where-Object {
    $_.id -ceq $modelName -and
    $_.url -ceq 'http://127.0.0.1:11434/v1/chat/completions' -and
    $_.toolCalling -is [bool] -and $_.toolCalling
})
if ($matchingModels.Count -ne 1) {
    throw 'config/chatLanguageModels.json が manifest model の loopback Agent 設定と一致しません。'
}
$maxInputTokens = Get-RequiredProperty $matchingModels[0] 'maxInputTokens' 'configured model'
$maxOutputTokens = Get-RequiredProperty $matchingModels[0] 'maxOutputTokens' 'configured model'
if (-not (Test-JsonInteger $maxInputTokens) -or -not (Test-JsonInteger $maxOutputTokens) -or
    [int64]$maxInputTokens -le 0 -or [int64]$maxOutputTokens -le 0 -or
    [int64]$maxInputTokens + [int64]$maxOutputTokens -ne $contextLength) {
    throw 'config/chatLanguageModels.json の token 合計が manifest.contextLength と一致しません。'
}
if ((Get-RequiredProperty $offlineSettingsConfig 'chat.utilityModel' 'config/settings.offline.json') -cne $modelName) {
    throw 'config/settings.offline.json の utility model が manifest.model.name と一致しません。'
}
$disableOllamaCloud = Get-RequiredProperty $ollamaSettingsConfig 'disable_ollama_cloud' 'config/ollama-server.json'
if ($disableOllamaCloud -isnot [bool] -or -not $disableOllamaCloud) {
    throw 'config/ollama-server.json は disable_ollama_cloud=true が必須です。'
}

$pythonIndexCandidates = @($verifiedFiles | Where-Object {
    $_.RelativePath -match '^runtime/python/(?:.+/)?index\.json$'
})
if ($componentMap['python-runtime'].RelativePath.EndsWith('/index.json', [StringComparison]::OrdinalIgnoreCase)) {
    $pythonIndexCandidates = @($verifiedFiles | Where-Object {
        $_.RelativePath -ieq $componentMap['python-runtime'].RelativePath
    })
}
if ($pythonIndexCandidates.Count -gt 1) { throw 'Python offline index.json を一意に特定できません。' }
$pythonIndexPath = if ($pythonIndexCandidates.Count -eq 1) { $pythonIndexCandidates[0].FullPath } else { $null }
$runtimeVersionMatch = [regex]::Match($componentMap['python-runtime'].Version, '^(3\.[0-9]+)')
$pythonRuntimeTag = if ($runtimeVersionMatch.Success) { "$($runtimeVersionMatch.Groups[1].Value)-64" } else { $null }
if ($null -ne $pythonIndexPath) {
    try { $pythonIndex = [System.IO.File]::ReadAllText($pythonIndexPath) | ConvertFrom-Json }
    catch { throw "Python offline index.json を読み取れません: $($_.Exception.Message)" }
    $runtimeEntries = @($pythonIndex.versions | Where-Object {
        $_.company -eq 'PythonCore' -and $_.tag -is [string] -and $_.tag -match '^3\.[0-9]+(?:\.[0-9]+)?-64$'
    })
    $exactRuntime = @($runtimeEntries | Where-Object {
        [string]$_.'sort-version' -eq $componentMap['python-runtime'].Version
    })
    $selectedRuntime = $null
    if ($exactRuntime.Count -eq 1) { $selectedRuntime = $exactRuntime[0] }
    elseif ($runtimeEntries.Count -eq 1) { $selectedRuntime = $runtimeEntries[0] }
    else { throw 'Python x64 runtime tag を offline index から一意に特定できません。' }
    $pythonRuntimeTag = [string]$selectedRuntime.tag
    $runtimeUrl = Get-RequiredProperty $selectedRuntime 'url' 'Python runtime index entry'
    if ($runtimeUrl -isnot [string] -or [string]::IsNullOrWhiteSpace($runtimeUrl) -or
        [Uri]::IsWellFormedUriString($runtimeUrl, [UriKind]::Absolute) -or
        $runtimeUrl.Contains('?') -or $runtimeUrl.Contains('#')) {
        throw 'Python offline index の runtime URL は kit 内の相対 path でなければなりません。'
    }
    $runtimeArchivePath = [System.IO.Path]::GetFullPath(
        [System.IO.Path]::Combine(
            [System.IO.Path]::GetDirectoryName($pythonIndexPath),
            ([Uri]::UnescapeDataString($runtimeUrl) -replace '/', '\')))
    $sourcePrefix = $script:SourceRoot.TrimEnd('\') + '\'
    if (-not $runtimeArchivePath.StartsWith($sourcePrefix, $script:PathComparison) -or
        -not [System.IO.File]::Exists($runtimeArchivePath) -or
        -not $listed.Contains($runtimeArchivePath)) {
        throw 'Python offline index の runtime archive は kit 内の manifest-listed file でなければなりません。'
    }
    $runtimeHash = Get-RequiredProperty (Get-RequiredProperty $selectedRuntime 'hash' 'Python runtime index entry') `
        'sha256' 'Python runtime index entry hash'
    if ($runtimeHash -isnot [string] -or $runtimeHash -notmatch '^[0-9a-fA-F]{64}$' -or
        (Get-FileHash -LiteralPath $runtimeArchivePath -Algorithm SHA256).Hash -ine $runtimeHash) {
        throw 'Python offline index の runtime archive SHA-256 が一致しません。'
    }
}
elseif ($Apply) {
    throw 'runtime/python 配下に検証済み offline index.json がありません。Apply を中止します。'
}
if ([string]::IsNullOrWhiteSpace($pythonRuntimeTag)) { throw 'Python runtime tag を決定できません。' }

Write-Step 'VS Code / Ollama / settings / model destination を全件 preflight します'
$conflicts = [System.Collections.Generic.List[string]]::new()
$plans = [System.Collections.Generic.List[string]]::new()

$vscodeRoot = Join-Path $env:LOCALAPPDATA 'Programs/Microsoft VS Code'
$existingVsCode = Find-VSCode
$installVsCode = $null -eq $existingVsCode
if ($null -ne $existingVsCode) {
    $actual = Get-FileVersion $existingVsCode.Exe
    if (Test-SameVersion $componentMap['vscode'].Version $actual) {
        $installVsCode = $false; $plans.Add("VS Code $actual は同一版のためスキップ")
    }
    else { $conflicts.Add("VS Code destination に異なる版があります: $($existingVsCode.Exe)") }
}
elseif ([System.IO.Directory]::Exists($vscodeRoot) -and @(Get-ChildItem $vscodeRoot -Force).Count -gt 0) {
    $conflicts.Add("VS Code destination が空ではありません: $vscodeRoot")
}
else { $plans.Add('VS Code User Setup を対話導入: runtime/vscode/VSCodeUserSetup-x64.exe') }

$ollamaRoot = Join-Path $env:LOCALAPPDATA 'Programs/Ollama'
$existingOllama = Find-Ollama
$installOllama = [string]::IsNullOrWhiteSpace($existingOllama)
if (-not $installOllama) {
    $actual = Get-FileVersion $existingOllama
    if (Test-SameVersion $componentMap['ollama'].Version $actual) {
        $installOllama = $false; $plans.Add("Ollama $actual は同一版のためスキップ")
    }
    else { $conflicts.Add("Ollama destination に異なる版があります: $existingOllama") }
}
elseif ([System.IO.Directory]::Exists($ollamaRoot) -and @(Get-ChildItem $ollamaRoot -Force).Count -gt 0) {
    $conflicts.Add("Ollama destination が空ではありません: $ollamaRoot")
}
else { $plans.Add('OllamaSetup.exe を対話導入: runtime/ollama/OllamaSetup.exe') }

$configPlacements = @(
    [pscustomobject]@{ Label = 'VS Code BYOK'; Source = $chatModelsSource; Destination = Join-Path $env:APPDATA 'Code/User/chatLanguageModels.json' },
    [pscustomobject]@{ Label = 'VS Code settings'; Source = $settingsSource; Destination = Join-Path $env:APPDATA 'Code/User/settings.json' },
    [pscustomobject]@{ Label = 'Ollama settings'; Source = $ollamaSettingsSource; Destination = Join-Path $env:USERPROFILE '.ollama/server.json' }
)
$configActions = [System.Collections.Generic.List[object]]::new()
foreach ($placement in $configPlacements) {
    $problem = Get-DestinationProblem $placement.Destination
    if ($null -ne $problem) { $conflicts.Add("$($placement.Label): $problem"); continue }
    if ([System.IO.Directory]::Exists($placement.Destination)) {
        $conflicts.Add("$($placement.Label) destination が directory です: $($placement.Destination)"); continue
    }
    if ([System.IO.File]::Exists($placement.Destination)) {
        $sourceInfo = [System.IO.FileInfo]::new($placement.Source)
        $destinationInfo = [System.IO.FileInfo]::new($placement.Destination)
        $sameContent = $sourceInfo.Length -eq $destinationInfo.Length -and
            (Get-FileHash $placement.Source -Algorithm SHA256).Hash -ieq
            (Get-FileHash $placement.Destination -Algorithm SHA256).Hash
        if ($sameContent) {
            $configActions.Add([pscustomobject]@{ Action = 'Skip'; Value = $placement })
            $plans.Add("$($placement.Label) は同一内容のためスキップ")
        }
        else { $conflicts.Add("$($placement.Label) に異なる既存内容があります: $($placement.Destination)") }
    }
    else {
        $configActions.Add([pscustomobject]@{ Action = 'Copy'; Value = $placement })
        $plans.Add("$($placement.Label) を新規配置: $($placement.Destination)")
    }
}

$modelDestination = Join-Path $env:USERPROFILE '.ollama/models'
$modelProblem = Get-DestinationProblem $modelDestination
if ($null -ne $modelProblem) { $conflicts.Add("Ollama model destination: $modelProblem") }
$configuredModelDestination = @(
    [Environment]::GetEnvironmentVariable('OLLAMA_MODELS', 'Process'),
    [Environment]::GetEnvironmentVariable('OLLAMA_MODELS', 'User'),
    [Environment]::GetEnvironmentVariable('OLLAMA_MODELS', 'Machine')
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1
if (-not [string]::IsNullOrWhiteSpace($configuredModelDestination)) {
    try {
        $configuredModelDestination = [System.IO.Path]::GetFullPath(
            [Environment]::ExpandEnvironmentVariables($configuredModelDestination))
        if (-not $configuredModelDestination.Equals(
            [System.IO.Path]::GetFullPath($modelDestination), $script:PathComparison)) {
            $conflicts.Add("OLLAMA_MODELS が固定 model destination と異なります: $configuredModelDestination")
        }
    }
    catch { $conflicts.Add("OLLAMA_MODELS を安全な path として解決できません: $configuredModelDestination") }
}
$modelFiles = @(Get-ChildItem $modelSource -Force -Recurse -File)
if ($modelFiles.Count -eq 0) { throw 'models/ollama に file がありません。' }
$modelActions = [System.Collections.Generic.List[object]]::new()
foreach ($sourceFile in $modelFiles) {
    $destination = Join-Path $modelDestination ([System.IO.Path]::GetRelativePath($modelSource, $sourceFile.FullName))
    $problem = Get-DestinationProblem $destination
    if ($null -ne $problem) { $conflicts.Add("Ollama model: $problem"); continue }
    if ([System.IO.Directory]::Exists($destination)) {
        $conflicts.Add("Ollama model destination が directory です: $destination"); continue
    }
    if ([System.IO.File]::Exists($destination)) {
        $destinationInfo = [System.IO.FileInfo]::new($destination)
        $sameContent = $sourceFile.Length -eq $destinationInfo.Length -and
            (Get-FileHash $sourceFile.FullName -Algorithm SHA256).Hash -ieq
            (Get-FileHash $destination -Algorithm SHA256).Hash
        if ($sameContent) { $modelActions.Add([pscustomobject]@{ Action = 'Skip'; Source = $sourceFile.FullName; Destination = $destination }) }
        else { $conflicts.Add("Ollama model cache に異なる既存内容があります: $destination") }
    }
    else { $modelActions.Add([pscustomobject]@{ Action = 'Copy'; Source = $sourceFile.FullName; Destination = $destination }) }
}
$modelCopyCount = @($modelActions | Where-Object Action -eq 'Copy').Count
$modelSkipCount = @($modelActions | Where-Object Action -eq 'Skip').Count
$plans.Add("Ollama model cache: copy $modelCopyCount / same-content skip $modelSkipCount")

$existingContext = [Environment]::GetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', 'User')
$setContext = [string]::IsNullOrWhiteSpace($existingContext)
if ($setContext) { $plans.Add("User 環境変数 OLLAMA_CONTEXT_LENGTH=$contextLength を設定") }
elseif ($existingContext -ceq [string]$contextLength) {
    $setContext = $false; $plans.Add('OLLAMA_CONTEXT_LENGTH は同一値のためスキップ')
}
else { $conflicts.Add("OLLAMA_CONTEXT_LENGTH に異なる既存値があります: $existingContext") }

$vsixFiles = @(Get-ChildItem (Join-Path $script:SourceRoot 'runtime/vscode') -Recurse -File -Filter '*.vsix')
if ($vsixFiles.Count -gt 0) { $plans.Add("$($vsixFiles.Count) VSIX を code --install-extension で導入") }

$installPythonManager = $true
if (@(Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue).Count -gt 0) {
    $conflicts.Add('Ollama が実行中です。環境変数と local-only 設定を確実に反映するため終了してから再実行してください。')
}
if (Test-TcpPortInUse -Port $script:EndpointPort) {
    $conflicts.Add("Ollama endpoint port $($script:EndpointPort) が使用中です。使用中のprocessを終了してから再実行してください。")
}
if ($Apply) {
    $identity = Get-AppxIdentity $pythonManagerPackage
    $installedManagers = @(Get-AppxPackage -Name $identity.Name -ErrorAction SilentlyContinue)
    if ($installedManagers.Count -gt 1) { $conflicts.Add('Python Install Manager package が複数あります。') }
    elseif ($installedManagers.Count -eq 1) {
        if (Test-SameVersion $identity.Version ([string]$installedManagers[0].Version)) {
            $installPythonManager = $false; $plans.Add('Python Install Manager は同一版のためスキップ')
        }
        else { $conflicts.Add("Python Install Manager に異なる既存版があります: $($installedManagers[0].Version)") }
    }
}
else { $plans.Add('Python Install Manager package を Add-AppxPackage で導入') }
$plans.Add('対話 installer は Start-Process checked-Wait checked-PassThru で終了確認')
$plans.Add("Python runtime: pymanager install --source=<index.json> $pythonRuntimeTag")
$plans.Add('Ollama loopback 待機後、tools/verify_endpoint.py --url/--model/--require-agent/--expected-context を実行')

if ($conflicts.Count -gt 0) {
    $details = $conflicts | ForEach-Object { "  - $_" }
    throw "競合を検出しました。既存内容は上書きしません。手動マージまたは手動整理してから再実行してください。`n$($details -join "`n")"
}

Write-Host ''
if (-not $Apply) {
    Write-Step 'dry-run: 導入予定を表示します'
    Write-Plan '現在の PowerShell 7+ を使用（runtime/powershell x64 MSI はスキップ）'
    foreach ($plan in $plans) { Write-Plan $plan }
    Write-Plan 'Apply 後に PATH を更新し、LOCALAPPDATA の公式既定候補と Get-Command から実体を特定'
    Write-Host ''
    Write-Step 'dry-run 完了（書込み・外部プロセス実行なし）'
    return
}

if ($Apply) {
    Write-Step '検証済み Offline Kit を適用します'

    if ($PSVersionTable.PSVersion.Major -ge 7) {
        Write-Note "PowerShell $($PSVersionTable.PSVersion) を使用中のため MSI はスキップします。"
    }
    else {
        $msiexec = Join-Path $env:SystemRoot 'System32/msiexec.exe'
        $process = Start-Process -FilePath $msiexec -ArgumentList @('/i', ('"{0}"' -f $powerShellMsi)) -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "PowerShell MSI が失敗しました (exit $($process.ExitCode))。" }
    }

    if ($installPythonManager) {
        Write-Step 'Python Install Manager package を導入します'
        Add-AppxPackage -Path $pythonManagerPackage
    }
    else { Write-Note 'Python Install Manager は同一版のためスキップします。' }

    Update-ProcessPath
    $pythonManagerCommand = Find-PyManager
    if ([string]::IsNullOrWhiteSpace($pythonManagerCommand) -or
        -not [System.IO.File]::Exists($pythonManagerCommand)) {
        throw 'PATH 更新後も pymanager.exe を LOCALAPPDATA または Get-Command から特定できません。'
    }
    Write-Step "Python $pythonRuntimeTag を offline index から導入します"
    & $pythonManagerCommand install "--source=$pythonIndexPath" $pythonRuntimeTag
    if ($LASTEXITCODE -ne 0) {
        throw "pymanager install --source=<index.json> が失敗しました (exit $LASTEXITCODE)。"
    }

    Write-Step '固定設定を配置します（JSON merge は行いません）'
    foreach ($action in $configActions) {
        if ($action.Action -eq 'Skip') { Write-Note "$($action.Value.Label) は同一内容のためスキップします。"; continue }
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($action.Value.Destination)) | Out-Null
        Copy-Item -LiteralPath $action.Value.Source -Destination $action.Value.Destination
    }

    Write-Step 'Ollama model cache を配置します'
    foreach ($action in $modelActions) {
        if ($action.Action -eq 'Skip') { continue }
        $destinationDirectory = [System.IO.Path]::GetDirectoryName($action.Destination)
        [System.IO.Directory]::CreateDirectory($destinationDirectory) | Out-Null
        $temporaryDestination = Join-Path $destinationDirectory (
            '.offline-kit-' + [guid]::NewGuid().ToString('N') + '.partial')
        try {
            Copy-Item -LiteralPath $action.Source -Destination $temporaryDestination
            $sourceHash = (Get-FileHash -LiteralPath $action.Source -Algorithm SHA256).Hash
            $temporaryHash = (Get-FileHash -LiteralPath $temporaryDestination -Algorithm SHA256).Hash
            if ($sourceHash -ine $temporaryHash) {
                throw "Ollama model file のコピー結果が一致しません: $($action.Destination)"
            }
            Move-Item -LiteralPath $temporaryDestination -Destination $action.Destination
        }
        finally {
            if ([System.IO.File]::Exists($temporaryDestination)) {
                Remove-Item -LiteralPath $temporaryDestination -Force
            }
        }
    }
    Write-Note "copy $modelCopyCount / same-content skip $modelSkipCount"

    if ($setContext) {
        [Environment]::SetEnvironmentVariable('OLLAMA_CONTEXT_LENGTH', [string]$contextLength, 'User')
    }
    $env:OLLAMA_CONTEXT_LENGTH = [string]$contextLength
    $env:OLLAMA_HOST = '127.0.0.1:11434'

    if ($installVsCode) {
        Write-Step 'VS Code User Setup を対話実行します'
        $process = Start-Process -FilePath $vscodeInstaller -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "VS Code User Setup が失敗しました (exit $($process.ExitCode))。" }
    }
    else { Write-Note 'VS Code installer は同一版のためスキップします。' }

    if ($installOllama) {
        Write-Step 'OllamaSetup.exe を対話実行します'
        $process = Start-Process -FilePath $ollamaInstaller -Wait -PassThru
        if ($process.ExitCode -ne 0) { throw "OllamaSetup.exe が失敗しました (exit $($process.ExitCode))。" }
    }
    else { Write-Note 'Ollama installer は同一版のためスキップします。' }

    Update-ProcessPath
    $installedVsCode = Find-VSCode
    $ollamaCommand = Find-Ollama
    if ($null -eq $installedVsCode -or -not [System.IO.File]::Exists($installedVsCode.Cli)) {
        throw 'PATH 更新後も VS Code を LOCALAPPDATA または Get-Command から特定できません。'
    }
    if ([string]::IsNullOrWhiteSpace($ollamaCommand) -or -not [System.IO.File]::Exists($ollamaCommand)) {
        throw 'PATH 更新後も Ollama を LOCALAPPDATA または Get-Command から特定できません。'
    }
    $installedVsCodeVersion = Get-FileVersion $installedVsCode.Exe
    if (-not (Test-SameVersion $componentMap['vscode'].Version $installedVsCodeVersion)) {
        throw "導入後の VS Code version が manifest と一致しません: $installedVsCodeVersion"
    }
    $installedOllamaVersion = Get-FileVersion $ollamaCommand
    if (-not (Test-SameVersion $componentMap['ollama'].Version $installedOllamaVersion)) {
        throw "導入後の Ollama version が manifest と一致しません: $installedOllamaVersion"
    }

    foreach ($vsix in $vsixFiles) {
        & $installedVsCode.Cli --install-extension $vsix.FullName
        if ($LASTEXITCODE -ne 0) { throw "code --install-extension が失敗しました (exit $LASTEXITCODE)。" }
    }

    $ollamaProcess = $null
    $verificationSucceeded = $false
    try {
        Write-Step 'Ollama を loopback で起動して待機します'
        if (-not (Test-OllamaLoopback)) {
            $ollamaProcess = Start-Process -FilePath $ollamaCommand -ArgumentList @('serve') -PassThru
            $ready = $false
            foreach ($attempt in 1..60) {
                if ($ollamaProcess.HasExited) {
                    throw "ollama serve が起動前に終了しました (exit $($ollamaProcess.ExitCode))。"
                }
                if (Test-OllamaLoopback) { $ready = $true; break }
                Start-Sleep -Seconds 1
            }
            if (-not $ready) { throw 'Ollama loopback が 60 秒以内に応答しませんでした。' }
        }

        $pythonOutput = @(& $pythonManagerCommand exec "-V:$pythonRuntimeTag" `
            -c 'import sys; print(sys.executable)' 2>&1)
        if ($LASTEXITCODE -ne 0) { throw "導入 Python の特定に失敗しました (exit $LASTEXITCODE)。" }
        $pythonExecutable = @($pythonOutput | ForEach-Object { $_.ToString().Trim().Trim('"') } |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and [System.IO.File]::Exists($_) }) |
            Select-Object -Last 1
        if ([string]::IsNullOrWhiteSpace($pythonExecutable) -or -not [System.IO.File]::Exists($pythonExecutable)) {
            throw "導入 Python executable がありません: $pythonExecutable"
        }

        Write-Step 'tools/verify_endpoint.py で Agent endpoint を必須検証します'
        & $pythonExecutable $verifierPath --url $script:EndpointUrl --model $modelName `
            --require-agent --expected-context $contextLength
        $verifierExitCode = $LASTEXITCODE
        if ($verifierExitCode -ne 0) {
            throw "tools/verify_endpoint.py が失敗しました (exit $verifierExitCode)。"
        }
        $verificationSucceeded = $true

        Write-Host ''
        Write-Step 'Offline Kit の導入と Agent endpoint 検証が完了しました'
    }
    finally {
        if (-not $verificationSucceeded -and $null -ne $ollamaProcess -and
            -not $ollamaProcess.HasExited) {
            Stop-Process -Id $ollamaProcess.Id -Force -ErrorAction SilentlyContinue
            $ollamaProcess.WaitForExit(5000) | Out-Null
        }
    }
}
