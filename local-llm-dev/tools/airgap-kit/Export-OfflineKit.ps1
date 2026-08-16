#Requires -Version 7.0
<#
.SYNOPSIS
    Windows 11 x64 用の完全オフライン導入キットを作成する。

.DESCRIPTION
    オンラインの Windows 11 x64 準備機で、PowerShell 7 x64 MSI、Python
    Install Manager と Python 3.14 x64 オフライン index、VS Code x64 User
    Setup、Ollama Windows installer、指定済み Ollama model cache、設定、導入・
    検証 payload、Windows 手順を収集する。必須処理が一つでも失敗した場合は停止し、
    全 payload の SHA-256 を記録した manifest.json を最後に生成する。

.PARAMETER Destination
    キットの出力先。存在しないか、隠し項目を含めて空でなければならない。

.PARAMETER Model
    準備機の Ollama に存在するモデル名。既定値は qwen3:8b。

.PARAMETER ContextLength
    キットのモデル設定に記録するコンテキスト長。既定値は 8192。

.EXAMPLE
    .\Export-OfflineKit.ps1 -Destination D:\offline-kit

.EXAMPLE
    .\Export-OfflineKit.ps1 -Destination D:\offline-kit -Model qwen3:8b -ContextLength 8192
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Destination,
    [ValidateNotNullOrEmpty()][string]$Model = 'qwen3:8b',
    [ValidateRange(1, [int]::MaxValue)][int]$ContextLength = 8192
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$pythonRuntimeTag = '3.14-64'
$vscodeDownloadUrl = 'https://update.code.visualstudio.com/latest/win32-x64-user/stable'

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-RequiredFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Description
    )

    if (-not [System.IO.File]::Exists($Path)) {
        throw "$Description が欠落しています: $Path"
    }
    if ([System.IO.FileInfo]::new($Path).Length -le 0) {
        throw "$Description が空です: $Path"
    }
}

function Get-KitRelativePath {
    param(
        [Parameter(Mandatory)][string]$KitRoot,
        [Parameter(Mandatory)][string]$Path
    )

    $relativePath = [System.IO.Path]::GetRelativePath($KitRoot, $Path).Replace('\', '/')
    if ([System.IO.Path]::IsPathRooted($relativePath) -or
        $relativePath -eq '..' -or $relativePath.StartsWith('../', [StringComparison]::Ordinal)) {
        throw "キット外のパスは manifest に記録できません: $Path"
    }
    return $relativePath
}

function Get-AppxIdentity {
    param([Parameter(Mandatory)][string]$Path)

    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $manifestEntry = $archive.Entries | Where-Object {
            $_.FullName -ieq 'AppxManifest.xml' -or
            $_.FullName -ieq 'AppxMetadata/AppxBundleManifest.xml'
        } | Select-Object -First 1
        if ($null -eq $manifestEntry) {
            return $null
        }

        $reader = [System.IO.StreamReader]::new($manifestEntry.Open())
        try {
            [xml]$manifestXml = $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
        }
    }
    finally {
        $archive.Dispose()
    }

    $identity = $manifestXml.SelectSingleNode(
        '/*[local-name()="Bundle" or local-name()="Package"]/*[local-name()="Identity"]')
    if ($null -eq $identity) {
        return $null
    }

    return [pscustomobject]@{
        Name = [string]$identity.Name
        Version = [string]$identity.Version
    }
}

function Test-TcpPortInUse {
    param([Parameter(Mandatory)][int]$Port)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        return $task.Wait(500) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Test-OllamaEndpoint {
    param([Parameter(Mandatory)][string]$BaseUrl)

    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseProxy = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(2)
    try {
        $response = $client.GetAsync("$BaseUrl/api/tags").GetAwaiter().GetResult()
        try { return $response.IsSuccessStatusCode } finally { $response.Dispose() }
    }
    catch { return $false }
    finally { $client.Dispose(); $handler.Dispose() }
}

function Write-ValidationLogTail {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$Path
    )

    if (-not [System.IO.File]::Exists($Path)) { return }
    [Console]::Error.WriteLine("--- $Label ($Path): last 30 lines ---")
    foreach ($line in @(Get-Content -LiteralPath $Path -Tail 30 -ErrorAction SilentlyContinue)) {
        [Console]::Error.WriteLine($line)
    }
}

if (-not $IsWindows) {
    throw 'Windows 11 x64 の準備機で実行してください。'
}
if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne
    [System.Runtime.InteropServices.Architecture]::X64) {
    throw 'x64 以外の準備機は保証対象外です。'
}
if ([Environment]::OSVersion.Version.Build -lt 22000) {
    throw 'Windows 11（build 22000 以上）の準備機で実行してください。'
}
if ($ContextLength -lt 2) {
    throw 'ContextLength は入力・出力 token をそれぞれ 1 以上確保できる 2 以上を指定してください。'
}

# 既存の隠し項目も含め、何か一つでもあれば書き込む前に拒否する。
if ((Test-Path -LiteralPath $Destination) -and
    @(Get-ChildItem -LiteralPath $Destination -Force).Count -gt 0) {
    throw "Destination は空でなければなりません: $Destination"
}

$kit = [System.IO.Path]::GetFullPath($Destination)
[System.IO.Directory]::CreateDirectory($kit) | Out-Null

$importSource = Join-Path $PSScriptRoot 'Import-OfflineKit.ps1'
$installWindowsSource = Join-Path $PSScriptRoot 'install-windows.cmd'
$verifierSource = Join-Path (Split-Path -Parent $PSScriptRoot) 'verify_endpoint.py'
Assert-RequiredFile -Path $importSource -Description 'Import-OfflineKit.ps1'
Assert-RequiredFile -Path $installWindowsSource -Description 'install-windows.cmd'
Assert-RequiredFile -Path $verifierSource -Description 'verify_endpoint.py'

$wingetCommand = Get-Command winget.exe -ErrorAction SilentlyContinue
if ($null -eq $wingetCommand) {
    throw 'winget.exe が見つかりません。Windows 11 の App Installer を有効にしてください。'
}
$pythonManagerCommand = Get-Command pymanager.exe -ErrorAction SilentlyContinue
if ($null -eq $pythonManagerCommand) {
    throw 'Python Install Manager の pymanager.exe が見つかりません。準備機へ先に導入してください。'
}
$ollamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue
if ($null -eq $ollamaCommand) {
    throw 'ollama.exe が見つかりません。準備機へ Ollama を導入してください。'
}

$relativeDirectories = @(
    'runtime/powershell',
    'runtime/python/manager',
    'runtime/python/offline-index',
    'runtime/vscode',
    'runtime/ollama',
    'models/ollama',
    'config',
    'tools',
    'docs',
    '.staging/config'
)
foreach ($relativeDirectory in $relativeDirectories) {
    [System.IO.Directory]::CreateDirectory((Join-Path $kit $relativeDirectory)) | Out-Null
}
$stagingRoot = Join-Path $kit '.staging'

$verifierPayload = [System.IO.File]::ReadAllText($verifierSource)
if (-not $verifierPayload.Contains('--require-agent')) {
    throw 'verify_endpoint.py が --require-agent に対応していません。'
}
$stagedVerifier = Join-Path $stagingRoot 'verify_endpoint.py'
[System.IO.File]::WriteAllText($stagedVerifier, $verifierPayload, $utf8NoBom)
Copy-Item -LiteralPath $stagedVerifier -Destination (Join-Path $kit 'tools/verify_endpoint.py')
$kitVerifier = Join-Path $kit 'tools/verify_endpoint.py'
Assert-RequiredFile -Path $kitVerifier -Description 'tools/verify_endpoint.py'

& $pythonManagerCommand.Source exec "-V:$pythonRuntimeTag" `
    -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) {
    throw 'verify_endpoint.py の実行には準備機上の Python 3.10 以上が必要です。'
}

$supportsToolCalling = $false
$validationPort = 11435
$validationEndpoint = "http://127.0.0.1:$validationPort"
if (Test-TcpPortInUse -Port $validationPort) {
    throw "Ollama 検証用 port $validationPort が使用中です。使用中の process を確認してください。"
}
$previousOllamaHost = $env:OLLAMA_HOST
$previousContextLength = $env:OLLAMA_CONTEXT_LENGTH
$validationServer = $null
$validationStdout = Join-Path $env:TEMP ("local-llm-dev-ollama-{0}.out.log" -f [guid]::NewGuid().ToString('N'))
$validationStderr = Join-Path $env:TEMP ("local-llm-dev-ollama-{0}.err.log" -f [guid]::NewGuid().ToString('N'))
try {
    $env:OLLAMA_HOST = "127.0.0.1:$validationPort"
    $env:OLLAMA_CONTEXT_LENGTH = [string]$ContextLength
    $validationServer = Start-Process -FilePath $ollamaCommand.Source -ArgumentList @('serve') `
        -PassThru -RedirectStandardOutput $validationStdout -RedirectStandardError $validationStderr
    $ready = $false
    foreach ($attempt in 1..60) {
        if ($validationServer.HasExited) {
            throw "専用 Ollama server が起動前に終了しました (exit $($validationServer.ExitCode))。"
        }
        if (Test-OllamaEndpoint -BaseUrl $validationEndpoint) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw '専用 Ollama server が 60 秒以内に応答しませんでした。' }

    Write-Step "Ollama で指定モデルを確認します: $Model"
    $modelListOutput = @(& $ollamaCommand.Source list 2>&1 | ForEach-Object { $_.ToString() })
    if ($LASTEXITCODE -ne 0) {
        throw "ollama list が失敗しました (exit $LASTEXITCODE): $($modelListOutput -join ' ')"
    }
    $requestedModelNames = @($Model)
    if ($Model -notmatch ':') { $requestedModelNames += "${Model}:latest" }
    $modelRecord = $null
    foreach ($line in $modelListOutput) {
        $columns = @($line.Trim() -split '\s+')
        if ($columns.Count -lt 2 -or $columns[0] -ieq 'NAME') { continue }
        if ($requestedModelNames -icontains $columns[0]) {
            $modelRecord = [pscustomobject]@{ Name = $columns[0]; Digest = $columns[1] }
            break
        }
    }
    if ($null -eq $modelRecord) { throw "指定モデルが ollama list に存在しません: $Model" }
    if ($modelRecord.Digest -notmatch '^(?:sha256:)?[0-9a-fA-F]{12,64}$') {
        throw "ollama list が返した digest を解釈できません: $($modelRecord.Digest)"
    }

    Write-Step 'models / chat / streaming / tool calling / 実効 context を厳格に検証します'
    & $pythonManagerCommand.Source exec "-V:$pythonRuntimeTag" $kitVerifier `
        --url $validationEndpoint `
        --model $modelRecord.Name `
        --timeout 600 `
        --require-agent `
        --expected-context $ContextLength
    if ($LASTEXITCODE -ne 0) {
        throw "verify_endpoint.py --require-agent が失敗しました (exit $LASTEXITCODE)。"
    }
    $supportsToolCalling = $true
}
catch {
    Write-ValidationLogTail -Label 'Ollama stdout' -Path $validationStdout
    Write-ValidationLogTail -Label 'Ollama stderr' -Path $validationStderr
    throw
}
finally {
    if ($null -ne $validationServer -and -not $validationServer.HasExited) {
        Stop-Process -Id $validationServer.Id -Force -ErrorAction SilentlyContinue
        $validationServer.WaitForExit(5000) | Out-Null
    }
    $env:OLLAMA_HOST = $previousOllamaHost
    $env:OLLAMA_CONTEXT_LENGTH = $previousContextLength
    Remove-Item -LiteralPath $validationStdout, $validationStderr -Force -ErrorAction SilentlyContinue
}

Write-Step 'PowerShell 7 x64 MSI を winget download で取得します'
$powerShellDirectory = Join-Path $kit 'runtime/powershell'
& $wingetCommand.Source download `
    --id Microsoft.PowerShell `
    --exact `
    --source winget `
    --architecture x64 `
    --installer-type wix `
    --download-directory $powerShellDirectory `
    --accept-package-agreements `
    --accept-source-agreements `
    --disable-interactivity
if ($LASTEXITCODE -ne 0) {
    throw "PowerShell 7 x64 MSI の winget download が失敗しました (exit $LASTEXITCODE)。"
}
$powerShellInstallers = @(Get-ChildItem -LiteralPath $powerShellDirectory -Recurse -File -Filter '*.msi')
if ($powerShellInstallers.Count -ne 1) {
    throw "PowerShell 7 x64 MSI を一意に特定できません ($($powerShellInstallers.Count) 件)。"
}
$powerShellInstaller = $powerShellInstallers[0]
Assert-RequiredFile -Path $powerShellInstaller.FullName -Description 'PowerShell 7 x64 MSI'
$powerShellVersion = $null
if ($powerShellInstaller.Name -match '^PowerShell-(?<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)-win-x64\.msi$') {
    $powerShellVersion = $Matches.version
}
elseif ($powerShellInstaller.Name -match '^PowerShell_(?<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)_Machine_X64_wix(?:_[^.]+)?\.msi$') {
    $powerShellVersion = $Matches.version
}
if ([string]::IsNullOrWhiteSpace($powerShellVersion)) {
    throw "PowerShell MSI の版を取得できません: $($powerShellInstaller.Name)"
}

Write-Step 'Python Install Manager を winget download で取得します'
$pythonManagerDirectory = Join-Path $kit 'runtime/python/manager'
& $wingetCommand.Source download `
    --id 9NQ7512CXL7T `
    --exact `
    --source msstore `
    --architecture x64 `
    --skip-license `
    --download-directory $pythonManagerDirectory `
    --accept-package-agreements `
    --accept-source-agreements `
    --disable-interactivity
if ($LASTEXITCODE -ne 0) {
    throw "Python Install Manager の winget download が失敗しました (exit $LASTEXITCODE)。"
}
$pythonManagerMatches = @()
$pythonManagerPackages = @(Get-ChildItem -LiteralPath $pythonManagerDirectory -Recurse -File |
    Where-Object { $_.Name -match '\.(?:msix|msixbundle|appx|appxbundle)$' })
foreach ($candidate in $pythonManagerPackages) {
    $identity = Get-AppxIdentity -Path $candidate.FullName
    if ($null -ne $identity -and $identity.Name -match 'PythonManager') {
        $pythonManagerMatches += [pscustomobject]@{
            File = $candidate
            Identity = $identity
        }
    }
}
if ($pythonManagerMatches.Count -ne 1) {
    throw "Python Install Manager package を一意に特定できません ($($pythonManagerMatches.Count) 件)。"
}
$pythonManagerInstaller = $pythonManagerMatches[0].File
$pythonManagerVersion = $pythonManagerMatches[0].Identity.Version
Assert-RequiredFile -Path $pythonManagerInstaller.FullName -Description 'Python Install Manager package'
if ([string]::IsNullOrWhiteSpace($pythonManagerVersion)) {
    throw 'Python Install Manager package の実際の版を取得できません。'
}

Write-Step "Python $pythonRuntimeTag の offline runtime index を作成します"
$pythonIndexDirectory = Join-Path $kit 'runtime/python/offline-index'
& $pythonManagerCommand.Source install "--download=$pythonIndexDirectory" $pythonRuntimeTag
if ($LASTEXITCODE -ne 0) {
    throw "pymanager install --download が失敗しました (exit $LASTEXITCODE)。"
}
$pythonIndexPath = Join-Path $pythonIndexDirectory 'index.json'
Assert-RequiredFile -Path $pythonIndexPath -Description 'Python offline index.json'
$pythonIndex = [System.IO.File]::ReadAllText($pythonIndexPath) | ConvertFrom-Json
$pythonRuntimeMatches = @()
foreach ($entry in @($pythonIndex.versions | Where-Object {
    $_.company -eq 'PythonCore' -and $_.tag -eq $pythonRuntimeTag
})) {
    $entryUrl = [string]$entry.url
    $entryUri = [System.Uri]::new($entryUrl, [System.UriKind]::RelativeOrAbsolute)
    $archiveName = if ($entryUri.IsAbsoluteUri) {
        [System.IO.Path]::GetFileName($entryUri.AbsolutePath)
    }
    else {
        [System.IO.Path]::GetFileName($entryUrl.Replace('/', '\'))
    }
    $archives = @(Get-ChildItem -LiteralPath $pythonIndexDirectory -Recurse -File |
        Where-Object { $_.Name -ceq $archiveName })
    if ($archives.Count -eq 1) {
        $pythonRuntimeMatches += [pscustomobject]@{
            Entry = $entry
            Archive = $archives[0]
        }
    }
}
if ($pythonRuntimeMatches.Count -ne 1) {
    throw "Python x64 runtime archive を offline index から一意に特定できません ($($pythonRuntimeMatches.Count) 件)。"
}
$pythonRuntimeEntry = $pythonRuntimeMatches[0].Entry
$pythonRuntimeArchive = $pythonRuntimeMatches[0].Archive
Assert-RequiredFile -Path $pythonRuntimeArchive.FullName -Description 'Python x64 runtime archive'
$pythonRuntimeVersion = [string]$pythonRuntimeEntry.'sort-version'
$pythonVersionMatch = [regex]::Match($pythonRuntimeVersion, '^(?<version>[0-9]+\.[0-9]+(?:\.[0-9]+)?)')
if (-not $pythonVersionMatch.Success -or
    [version]$pythonVersionMatch.Groups['version'].Value -lt [version]'3.10') {
    throw "Python runtime は 3.10 以上でなければなりません: $pythonRuntimeVersion"
}
$expectedPythonHash = [string]$pythonRuntimeEntry.hash.sha256
if ($expectedPythonHash -notmatch '^[0-9a-fA-F]{64}$') {
    throw 'Python offline index に有効な SHA-256 がありません。'
}
$actualPythonHash = (Get-FileHash -LiteralPath $pythonRuntimeArchive.FullName -Algorithm SHA256).Hash
if ($actualPythonHash -ine $expectedPythonHash) {
    throw 'Python runtime archive が offline index の SHA-256 と一致しません。'
}

Write-Step 'VS Code x64 User Setup を公式 download server から取得します'
$vscodeInstaller = Join-Path $kit 'runtime/vscode/VSCodeUserSetup-x64.exe'
Invoke-WebRequest `
    -Uri $vscodeDownloadUrl `
    -OutFile $vscodeInstaller `
    -TimeoutSec 600 `
    -ErrorAction Stop
Assert-RequiredFile -Path $vscodeInstaller -Description 'VS Code x64 User Setup'
$vscodeVersionInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($vscodeInstaller)
$vscodeVersion = @($vscodeVersionInfo.ProductVersion, $vscodeVersionInfo.FileVersion) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($vscodeVersion)) {
    throw 'VS Code installer の実際の版を取得できません。'
}
$vscodeVersion = $vscodeVersion.Trim()

Write-Step 'Ollama Windows installer を winget download で取得します'
$ollamaDirectory = Join-Path $kit 'runtime/ollama'
& $wingetCommand.Source download `
    --id Ollama.Ollama `
    --exact `
    --source winget `
    --architecture x64 `
    --download-directory $ollamaDirectory `
    --accept-package-agreements `
    --accept-source-agreements `
    --disable-interactivity
if ($LASTEXITCODE -ne 0) {
    throw "Ollama Windows installer の winget download が失敗しました (exit $LASTEXITCODE)。"
}
$ollamaInstallers = @(Get-ChildItem -LiteralPath $ollamaDirectory -Recurse -File -Filter '*.exe')
if ($ollamaInstallers.Count -ne 1) {
    throw "Ollama Windows installer を一意に特定できません ($($ollamaInstallers.Count) 件)。"
}
$downloadedOllamaInstaller = $ollamaInstallers[0]
if ($downloadedOllamaInstaller.Name -notmatch '^OllamaSetup(?:[-.][0-9][^\/]*)?\.exe$' -and
    $downloadedOllamaInstaller.Name -notmatch '^Ollama_(?<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)_User_X64_inno(?:_[^.]+)?\.exe$') {
    throw "Ollama Windows x64 installer の命名を検証できません: $($downloadedOllamaInstaller.Name)"
}
$canonicalOllamaInstaller = Join-Path $ollamaDirectory 'OllamaSetup.exe'
if ($downloadedOllamaInstaller.FullName -ine $canonicalOllamaInstaller) {
    Move-Item -LiteralPath $downloadedOllamaInstaller.FullName -Destination $canonicalOllamaInstaller
}
Assert-RequiredFile -Path $canonicalOllamaInstaller -Description 'OllamaSetup.exe'
$ollamaVersionInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($canonicalOllamaInstaller)
$ollamaVersion = @($ollamaVersionInfo.ProductVersion, $ollamaVersionInfo.FileVersion) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($ollamaVersion)) {
    throw 'Ollama installer の実際の版を取得できません。'
}
$ollamaVersion = $ollamaVersion.Trim()

Write-Step "Ollama model cache を収集します: $($modelRecord.Name)"
$ollamaModelsRoot = if (-not [string]::IsNullOrWhiteSpace($env:OLLAMA_MODELS)) {
    [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($env:OLLAMA_MODELS))
}
else {
    Join-Path $env:USERPROFILE '.ollama/models'
}
if (-not [System.IO.Directory]::Exists($ollamaModelsRoot)) {
    throw "Ollama model cache が見つかりません: $ollamaModelsRoot"
}
$sourceManifestRoot = Join-Path $ollamaModelsRoot 'manifests'
$sourceBlobRoot = Join-Path $ollamaModelsRoot 'blobs'
if (-not [System.IO.Directory]::Exists($sourceManifestRoot) -or
    -not [System.IO.Directory]::Exists($sourceBlobRoot)) {
    throw 'Ollama model cache に manifests または blobs がありません。'
}

$matchingManifests = @()
foreach ($manifestFile in @(Get-ChildItem -LiteralPath $sourceManifestRoot -Recurse -File)) {
    $relativeManifest = [System.IO.Path]::GetRelativePath($sourceManifestRoot, $manifestFile.FullName)
    $parts = @($relativeManifest -split '[\\/]')
    if ($parts.Count -lt 4) {
        continue
    }
    $registry = $parts[0]
    $tag = $parts[-1]
    $modelSegment = $parts[-2]
    $namespace = ($parts[1..($parts.Count - 3)] -join '/')
    $manifestNames = @(("{0}/{1}/{2}:{3}" -f $registry, $namespace, $modelSegment, $tag))
    if ($registry -ieq 'registry.ollama.ai') {
        $manifestNames += ("{0}/{1}:{2}" -f $namespace, $modelSegment, $tag)
        if ($namespace -ieq 'library') {
            $manifestNames += ("{0}:{1}" -f $modelSegment, $tag)
        }
    }
    if ($manifestNames -icontains $modelRecord.Name) {
        $matchingManifests += $manifestFile
    }
}
$matchingManifests = @($matchingManifests | Sort-Object FullName -Unique)
$modelDestination = Join-Path $kit 'models/ollama'
if ($matchingManifests.Count -eq 1) {
    $selectedManifest = $matchingManifests[0]
    $relativeManifest = [System.IO.Path]::GetRelativePath($sourceManifestRoot, $selectedManifest.FullName)
    $destinationManifest = Join-Path $modelDestination (Join-Path 'manifests' $relativeManifest)
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($destinationManifest)) | Out-Null
    Copy-Item -LiteralPath $selectedManifest.FullName -Destination $destinationManifest

    $ollamaManifest = [System.IO.File]::ReadAllText($selectedManifest.FullName) | ConvertFrom-Json
    $requiredDigests = @([string]$ollamaManifest.config.digest) + @(
        $ollamaManifest.layers | ForEach-Object { [string]$_.digest }
    )
    $requiredDigests = @($requiredDigests | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_)
    } | Sort-Object -Unique)
    if ($requiredDigests.Count -eq 0) {
        throw '指定モデルの Ollama manifest に config/layer digest がありません。'
    }

    $destinationBlobRoot = Join-Path $modelDestination 'blobs'
    [System.IO.Directory]::CreateDirectory($destinationBlobRoot) | Out-Null
    foreach ($digest in $requiredDigests) {
        if ($digest -notmatch '^sha256:[0-9a-fA-F]{64}$') {
            throw "Ollama manifest に不正な digest があります: $digest"
        }
        $blobName = 'sha256-' + $digest.Substring('sha256:'.Length)
        $sourceBlob = Join-Path $sourceBlobRoot $blobName
        Assert-RequiredFile -Path $sourceBlob -Description "Ollama model blob $digest"
        $destinationBlob = Join-Path $destinationBlobRoot $blobName
        Copy-Item -LiteralPath $sourceBlob -Destination $destinationBlob
        $sourceHash = (Get-FileHash -LiteralPath $sourceBlob -Algorithm SHA256).Hash
        $destinationHash = (Get-FileHash -LiteralPath $destinationBlob -Algorithm SHA256).Hash
        if ($sourceHash -ine $destinationHash) {
            throw "Ollama model blob のコピー結果が一致しません: $blobName"
        }
    }
    $modelCacheScope = '指定モデルの manifest と、その config/layer digest が参照する blobs だけをコピーした。'
}
else {
    throw "指定モデルの Ollama manifest を一意に特定できません: $($modelRecord.Name)（候補 $($matchingManifests.Count) 件）"
}
if (@(Get-ChildItem -LiteralPath $modelDestination -Recurse -File -Force).Count -eq 0) {
    throw 'Ollama model cache のコピー結果が空です。'
}

Write-Step '固定設定と Windows 導入 payload を作成します'
$maxOutputTokens = [Math]::Min(2048, [Math]::Max(1, [int][Math]::Floor($ContextLength / 4)))
$maxInputTokens = $ContextLength - $maxOutputTokens
$chatLanguageModels = @(
    [ordered]@{
        name = 'Ollama (local)'
        vendor = 'customendpoint'
        apiType = 'chat-completions'
        apiKey = 'unused-but-required'
        models = @(
            [ordered]@{
                id = $modelRecord.Name
                name = "$($modelRecord.Name) (Ollama)"
                url = 'http://127.0.0.1:11434/v1/chat/completions'
                toolCalling = $supportsToolCalling
                vision = $false
                maxInputTokens = $maxInputTokens
                maxOutputTokens = $maxOutputTokens
            }
        )
    }
)
$offlineSettings = [ordered]@{
    'extensions.autoUpdate' = $false
    'extensions.autoCheckUpdates' = $false
    'extensions.showRecommendationsOnlyOnDemand' = $true
    'extensions.ignoreRecommendations' = $true
    'chat.utilityModel' = $modelRecord.Name
    'chat.utilitySmallModel' = $modelRecord.Name
    'chat.byokUtilityModelDefault' = 'Main Agent Model'
    'inlineChat.defaultModel' = $modelRecord.Name
}
$ollamaServer = [ordered]@{
    disable_ollama_cloud = $true
}

$stagedConfigDirectory = Join-Path $stagingRoot 'config'
[System.IO.File]::WriteAllText(
    (Join-Path $stagedConfigDirectory 'chatLanguageModels.json'),
    ($chatLanguageModels | ConvertTo-Json -Depth 10),
    $utf8NoBom)
[System.IO.File]::WriteAllText(
    (Join-Path $stagedConfigDirectory 'settings.offline.json'),
    ($offlineSettings | ConvertTo-Json -Depth 10),
    $utf8NoBom)
[System.IO.File]::WriteAllText(
    (Join-Path $stagedConfigDirectory 'ollama-server.json'),
    ($ollamaServer | ConvertTo-Json -Depth 10),
    $utf8NoBom)

Copy-Item -LiteralPath (Join-Path $stagedConfigDirectory 'chatLanguageModels.json') `
    -Destination (Join-Path $kit 'config/chatLanguageModels.json')
Copy-Item -LiteralPath (Join-Path $stagedConfigDirectory 'settings.offline.json') `
    -Destination (Join-Path $kit 'config/settings.offline.json')
Copy-Item -LiteralPath (Join-Path $stagedConfigDirectory 'ollama-server.json') `
    -Destination (Join-Path $kit 'config/ollama-server.json')
Copy-Item -LiteralPath $importSource -Destination (Join-Path $kit 'Import-OfflineKit.ps1')
Copy-Item -LiteralPath $installWindowsSource -Destination (Join-Path $kit 'install-windows.cmd')

$windowsGuideTemplate = @'
# Windows 11 x64 オフライン導入

このディレクトリだけで検証と導入を行う。別途リポジトリを取得しない。

- 対象: Windows 11 x64
- モデル: `__MODEL__`
- コンテキスト長: `__CONTEXT__`
- Agent/tool calling/context: 準備機で `verify_endpoint.py --require-agent --expected-context __CONTEXT__` 成功済み

## モデルキャッシュ

__CACHE_SCOPE__

## 導入前確認

1. キット全体を同じディレクトリ構造のまま運用機へコピーする。
2. `manifest.json`、`install-windows.cmd`、`Import-OfflineKit.ps1` がルートにあることを確認する。
3. PowerShell 7 がない場合は `install-windows.cmd -BootstrapPowerShell` で、同梱 x64 MSI を明示的に導入する。

## ドライラン

PowerShell 7 がある場合は `install-windows.cmd` を実行する。無い場合は最初に
`install-windows.cmd -BootstrapPowerShell` を実行する。このオプションだけが PowerShell 7 を導入し、
その後に manifest、OS/CPU、SHA-256、導入予定の dry-run を行う。

## 適用

ドライランに問題がない場合だけ `install-windows.cmd -Apply` を実行する。
各 installer または検証コマンドが非ゼロで終了した場合は、その終了コードで停止する。

## 導入後確認

1. `pwsh --version`、`pymanager exec -V:3.14-64 --version`、`code --version`、`ollama --version` を確認する。
2. `ollama list` に `__MODEL__` が存在することを確認する。
3. Ollama が `127.0.0.1:11434` だけで応答することを確認する。
4. `pymanager exec -V:3.14-64 tools\verify_endpoint.py --url http://127.0.0.1:11434 --model __MODEL__ --require-agent --expected-context __CONTEXT__` を実行する。
5. VS Code のモデルピッカー、Chat、Agent で実往復を確認する。

既存の VS Code/Ollama 設定と内容が異なる場合は上書きせず、停止後に手動マージする。
'@
$windowsGuide = $windowsGuideTemplate.Replace('__MODEL__', $modelRecord.Name).
    Replace('__CONTEXT__', [string]$ContextLength).
    Replace('__CACHE_SCOPE__', $modelCacheScope)
$stagedWindowsGuide = Join-Path $stagingRoot 'WINDOWS.md'
[System.IO.File]::WriteAllText($stagedWindowsGuide, $windowsGuide, $utf8NoBom)
Copy-Item -LiteralPath $stagedWindowsGuide -Destination (Join-Path $kit 'docs/WINDOWS.md')

$requiredKitFiles = @(
    'Import-OfflineKit.ps1',
    'install-windows.cmd',
    'config/chatLanguageModels.json',
    'config/settings.offline.json',
    'config/ollama-server.json',
    'tools/verify_endpoint.py',
    'docs/WINDOWS.md'
)
foreach ($requiredKitFile in $requiredKitFiles) {
    Assert-RequiredFile -Path (Join-Path $kit $requiredKitFile) -Description $requiredKitFile
}

# 一時生成物を manifest の対象から確実に除外する。
Remove-Item -LiteralPath $stagingRoot -Recurse -Force
if (Test-Path -LiteralPath $stagingRoot) {
    throw '.staging を削除できません。manifest の生成を中止します。'
}

$components = @(
    [ordered]@{
        name = 'powershell'
        required = $true
        version = $powerShellVersion
        path = Get-KitRelativePath -KitRoot $kit -Path $powerShellInstaller.FullName
    },
    [ordered]@{
        name = 'python-install-manager'
        required = $true
        version = $pythonManagerVersion
        path = Get-KitRelativePath -KitRoot $kit -Path $pythonManagerInstaller.FullName
    },
    [ordered]@{
        name = 'python-runtime'
        required = $true
        version = $pythonRuntimeVersion
        path = Get-KitRelativePath -KitRoot $kit -Path $pythonIndexPath
    },
    [ordered]@{
        name = 'vscode'
        required = $true
        version = $vscodeVersion
        path = 'runtime/vscode/VSCodeUserSetup-x64.exe'
    },
    [ordered]@{
        name = 'ollama'
        required = $true
        version = $ollamaVersion
        path = 'runtime/ollama/OllamaSetup.exe'
    },
    [ordered]@{
        name = 'ollama-model'
        required = $true
        version = $modelRecord.Name
        path = 'models/ollama'
    },
    [ordered]@{
        name = 'configuration'
        required = $true
        version = '1'
        path = 'config'
    },
    [ordered]@{
        name = 'importer'
        required = $true
        version = '1'
        path = 'Import-OfflineKit.ps1'
    },
    [ordered]@{
        name = 'endpoint-verifier'
        required = $true
        version = '1'
        path = 'tools/verify_endpoint.py'
    },
    [ordered]@{
        name = 'windows-entry'
        required = $true
        version = '1'
        path = 'install-windows.cmd'
    },
    [ordered]@{
        name = 'windows-guide'
        required = $true
        version = '1'
        path = 'docs/WINDOWS.md'
    }
)

Write-Step '全 payload の SHA-256 を計算します'
$files = @(
    Get-ChildItem -LiteralPath $kit -Recurse -File -Force |
        Where-Object { $_.Name -ne 'manifest.json' } |
        ForEach-Object {
            [ordered]@{
                path = Get-KitRelativePath -KitRoot $kit -Path $_.FullName
                bytes = $_.Length
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        } |
        Sort-Object path
)
if ($files.Count -eq 0) {
    throw 'manifest に記録する payload がありません。'
}

$manifest = @{
    schemaVersion = 1
    createdAt = [DateTime]::UtcNow.ToString(
        "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'",
        [Globalization.CultureInfo]::InvariantCulture)
    platform = 'windows'
    architecture = 'x64'
    model = [ordered]@{
        name = $modelRecord.Name
        digest = $modelRecord.Digest
        supportsToolCalling = $supportsToolCalling
    }
    contextLength = $ContextLength
    components = $components
    files = $files
}
$manifestPath = Join-Path $kit 'manifest.json'
[System.IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 12),
    $utf8NoBom)
Assert-RequiredFile -Path $manifestPath -Description 'manifest.json'

Write-Host ''
Write-Step 'Windows 11 x64 オフラインキットを作成しました'
Write-Host "    Destination : $kit"
Write-Host "    Model       : $($modelRecord.Name)"
Write-Host "    Context     : $ContextLength"
Write-Host "    Files       : $($files.Count)"
