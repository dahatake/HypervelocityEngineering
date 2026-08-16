#Requires -Version 7.0
<#
.SYNOPSIS
    Export-OfflineKit.ps1 の Windows Export 契約を静的に検査する。

.DESCRIPTION
    CONTRACT.md を正本として、Export-OfflineKit.ps1 の PowerShell AST とトークンだけを
    読み取る自己完結テストランナー。対象スクリプトは実行せず、外部通信、winget、
    モデル実行も行わない。
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:PassedCount = 0
$script:FailedCount = 0
$script:FailureMessages = [System.Collections.Generic.List[string]]::new()

function Assert-Condition {
    param(
        [Parameter(Mandatory)][bool]$Condition,
        [Parameter(Mandatory)][string]$Message
    )

    if (-not $Condition) {
        throw [System.InvalidOperationException]::new($Message)
    }
}

function Invoke-ContractTest {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Body
    )

    try {
        & $Body
        $script:PassedCount++
        Write-Host "[PASS] $Name" -ForegroundColor Green
    } catch {
        $script:FailedCount++
        $message = "[FAIL] ${Name}: $($_.Exception.Message)"
        $script:FailureMessages.Add($message)
        Write-Host $message -ForegroundColor Red
    }
}

function Test-NodeHasCommand {
    param(
        [Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Node,
        [Parameter(Mandatory)][string[]]$Names
    )

    $commands = @($Node.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.CommandAst]
    }, $true))

    foreach ($command in $commands) {
        $commandName = $command.GetCommandName()
        if ($null -ne $commandName -and $Names -contains $commandName) {
            return $true
        }
    }
    return $false
}

function Test-NodeHasThrow {
    param([Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Node)

    return @($Node.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.ThrowStatementAst]
    }, $true)).Count -gt 0
}

function Test-NodeTerminates {
    param([Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Node)

    if (Test-NodeHasThrow -Node $Node) {
        return $true
    }
    if (@($Node.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.ExitStatementAst] -and
        $candidate.Extent.Text -notmatch '^\s*exit\s+0\s*$'
    }, $true)).Count -gt 0) {
        return $true
    }
    return @($Node.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.ReturnStatementAst] -and
        $candidate.Extent.Text -match '^\s*return\s+\$false\s*$'
    }, $true)).Count -gt 0
}

function Get-StringValue {
    param([Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Node)

    if ($Node -is [System.Management.Automation.Language.StringConstantExpressionAst] -or
        $Node -is [System.Management.Automation.Language.ExpandableStringExpressionAst]) {
        return $Node.Value
    }
    return $null
}

function Test-LiteralHasLeafName {
    param(
        [Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Node,
        [Parameter(Mandatory)][string]$LeafName,
        [string]$ParentDirectory = ''
    )

    $value = Get-StringValue -Node $Node
    if ($null -eq $value) {
        return $false
    }

    $normalized = $value.Replace('\', '/').TrimEnd('/')
    $leaf = ($normalized -split '/')[-1]
    if ($leaf -ine $LeafName) {
        return $false
    }
    if ([string]::IsNullOrWhiteSpace($ParentDirectory)) {
        return $true
    }
    $segments = @($normalized -split '/' | Where-Object { $_ -ne '' })
    return $segments -contains $ParentDirectory
}

function Test-NodeHasCopyCommand {
    param([Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Node)

    $commands = @($Node.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.CommandAst]
    }, $true))

    foreach ($command in $commands) {
        $commandName = $command.GetCommandName()
        if ($commandName -ieq 'Copy-Item') {
            return $true
        }
    }
    return $false
}

function Get-EnclosingAssignmentVariableName {
    param(
        [Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Node,
        [Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Root
    )

    $cursor = $Node.Parent
    while ($null -ne $cursor -and $cursor -ne $Root) {
        if ($cursor -is [System.Management.Automation.Language.AssignmentStatementAst]) {
            if ($cursor.Left -is [System.Management.Automation.Language.VariableExpressionAst]) {
                return $cursor.Left.VariablePath.UserPath
            }
            return $null
        }
        $cursor = $cursor.Parent
    }
    return $null
}

function Test-VariableFeedsCopyLoop {
    param(
        [Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Ast,
        [Parameter(Mandatory)][string]$VariableName
    )

    $loops = @($Ast.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.ForEachStatementAst]
    }, $true))

    foreach ($loop in $loops) {
        $usesVariable = @($loop.Condition.FindAll({
            param($candidate)
            $candidate -is [System.Management.Automation.Language.VariableExpressionAst] -and
            $candidate.VariablePath.UserPath -ieq $VariableName
        }, $true)).Count -gt 0
        if ($usesVariable -and (Test-NodeHasCopyCommand -Node $loop.Body)) {
            return $true
        }
    }
    return $false
}

function Test-VariableFeedsCopyCommand {
    param(
        [Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Ast,
        [Parameter(Mandatory)][string]$VariableName
    )

    $copyCommands = @($Ast.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.CommandAst] -and
        $candidate.GetCommandName() -ieq 'Copy-Item'
    }, $true))
    foreach ($command in $copyCommands) {
        $usesVariable = @($command.FindAll({
            param($candidate)
            $candidate -is [System.Management.Automation.Language.VariableExpressionAst] -and
            $candidate.VariablePath.UserPath -ieq $VariableName
        }, $true)).Count -gt 0
        if ($usesVariable) {
            return $true
        }
    }
    return $false
}

function Test-StaticCopyContract {
    param(
        [Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Ast,
        [Parameter(Mandatory)][string]$LeafName,
        [string]$ParentDirectory = ''
    )

    $literals = @($Ast.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.StringConstantExpressionAst] -or
        $candidate -is [System.Management.Automation.Language.ExpandableStringExpressionAst]
    }, $true) | Where-Object {
        Test-LiteralHasLeafName -Node $_ -LeafName $LeafName -ParentDirectory $ParentDirectory
    })

    foreach ($literal in $literals) {
        $cursor = $literal.Parent
        while ($null -ne $cursor -and $cursor -ne $Ast) {
            if (($cursor -is [System.Management.Automation.Language.PipelineAst] -or
                 $cursor -is [System.Management.Automation.Language.IfStatementAst] -or
                 $cursor -is [System.Management.Automation.Language.ForEachStatementAst] -or
                 $cursor -is [System.Management.Automation.Language.FunctionDefinitionAst]) -and
                (Test-NodeHasCopyCommand -Node $cursor)) {
                return $true
            }
            $cursor = $cursor.Parent
        }

        $assignedVariable = Get-EnclosingAssignmentVariableName -Node $literal -Root $Ast
        if ($null -ne $assignedVariable -and
            ((Test-VariableFeedsCopyLoop -Ast $Ast -VariableName $assignedVariable) -or
             (Test-VariableFeedsCopyCommand -Ast $Ast -VariableName $assignedVariable))) {
            return $true
        }
    }
    return $false
}

function Get-HashtableKeys {
    param([Parameter(Mandatory)][System.Management.Automation.Language.HashtableAst]$Hashtable)

    $keys = @()
    foreach ($pair in $Hashtable.KeyValuePairs) {
        $keyAst = $pair.Item1
        if ($keyAst -is [System.Management.Automation.Language.StringConstantExpressionAst]) {
            $keys += $keyAst.Value
        } else {
            $keys += $keyAst.Extent.Text.Trim("'`"")
        }
    }
    return $keys
}

function Test-HashtableHasKeys {
    param(
        [Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Ast,
        [Parameter(Mandatory)][string[]]$RequiredKeys
    )

    $hashtables = @($Ast.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.HashtableAst]
    }, $true))

    foreach ($hashtable in $hashtables) {
        $keys = @(Get-HashtableKeys -Hashtable $hashtable)
        $missing = @($RequiredKeys | Where-Object { $keys -notcontains $_ })
        if ($missing.Count -eq 0) {
            return $true
        }
    }
    return $false
}

function Test-AssignedHashtableHasKeys {
    param(
        [Parameter(Mandatory)][System.Management.Automation.Language.Ast]$Ast,
        [Parameter(Mandatory)][string[]]$VariableNames,
        [Parameter(Mandatory)][string[]]$RequiredKeys
    )

    $assignments = @($Ast.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $candidate.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
        $VariableNames -contains $candidate.Left.VariablePath.UserPath
    }, $true))
    foreach ($assignment in $assignments) {
        $right = $assignment.Right
        if ($right -is [System.Management.Automation.Language.CommandExpressionAst]) {
            $right = $right.Expression
        }
        if ($right -isnot [System.Management.Automation.Language.HashtableAst]) {
            continue
        }
        $keys = @(Get-HashtableKeys -Hashtable $right)
        if (@($RequiredKeys | Where-Object { $keys -notcontains $_ }).Count -eq 0) {
            return $true
        }
    }
    return $false
}

$kitRoot = Split-Path -Parent $PSScriptRoot
$targetPath = Join-Path $kitRoot 'Export-OfflineKit.ps1'
$contractPath = Join-Path $kitRoot 'CONTRACT.md'

if (-not [System.IO.File]::Exists($targetPath)) {
    throw "テスト対象が見つかりません: $targetPath"
}
if (-not [System.IO.File]::Exists($contractPath)) {
    throw "正本 CONTRACT.md が見つかりません: $contractPath"
}

$targetTokens = $null
$targetParseErrors = $null
$targetAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $targetPath,
    [ref]$targetTokens,
    [ref]$targetParseErrors)
$targetCodeOnly = (($targetTokens | Where-Object {
    $_.Kind -ne [System.Management.Automation.Language.TokenKind]::Comment
} | ForEach-Object { $_.Text }) -join ' ')
Invoke-ContractTest 'ランナー自身が対象実行・外部通信・winget・モデル実行を含まない' {
    $selfTokens = $null
    $selfParseErrors = $null
    $selfAst = [System.Management.Automation.Language.Parser]::ParseFile(
        $PSCommandPath,
        [ref]$selfTokens,
        [ref]$selfParseErrors)
    Assert-Condition ($selfParseErrors.Count -eq 0) 'テストランナー自身に parser error がある。'

    $forbiddenCommands = @(
        'Invoke-WebRequest', 'iwr', 'Invoke-RestMethod', 'irm', 'Start-BitsTransfer',
        'curl', 'curl.exe', 'wget', 'wget.exe', 'bitsadmin', 'bitsadmin.exe',
        'winget', 'winget.exe', 'ollama', 'ollama.exe', 'foundry', 'foundry.exe',
        'python', 'python.exe', 'py', 'py.exe',
        'Start-Process', 'Invoke-Expression', 'pwsh', 'powershell', 'powershell.exe'
    )
    $invokedForbidden = @($selfAst.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.CommandAst]
    }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object {
        $null -ne $_ -and $forbiddenCommands -contains $_
    })
    Assert-Condition ($invokedForbidden.Count -eq 0) (
        '禁止コマンドを実行している: ' + ($invokedForbidden -join ', '))

    $targetInvocations = @($selfAst.FindAll({
        param($candidate)
        if ($candidate -isnot [System.Management.Automation.Language.CommandAst] -or
            $candidate.CommandElements.Count -eq 0) {
            return $false
        }
        $head = $candidate.CommandElements[0]
        return $head -is [System.Management.Automation.Language.VariableExpressionAst] -and
               $head.VariablePath.UserPath -ieq 'targetPath'
    }, $true))
    Assert-Condition ($targetInvocations.Count -eq 0) 'Export-OfflineKit.ps1 を動的実行している。'
}

Invoke-ContractTest 'Export-OfflineKit.ps1 が PowerShell parser error なしで解析できる' {
    $details = @($targetParseErrors | ForEach-Object {
        "line $($_.Extent.StartLineNumber): $($_.Message)"
    }) -join '; '
    Assert-Condition ($targetParseErrors.Count -eq 0) "parser error: $details"
}

Invoke-ContractTest 'Python Install Manager は曖昧でない pymanager.exe を使う' {
    Assert-Condition ($targetCodeOnly -match '(?i)Get-Command\s+pymanager\.exe') (
        'pymanager.exe の明示解決がない。')
    Assert-Condition ($targetCodeOnly -notmatch '(?i)Get-Command\s+py\.exe') (
        'legacy py.exe を Python Install Manager として選択する可能性がある。')
    Assert-Condition ($targetCodeOnly -match '(?i)exec\s+["'']?-V:\$pythonRuntimeTag') (
        'endpoint verifier を同梱Python runtime tagで実行していない。')
    Assert-Condition ($targetCodeOnly -match '(?i)pymanager\s+exec\s+-V:3[.]14-64\s+--version') (
        '生成WindowsガイドがPython確認にpymanagerを使っていない。')
    Assert-Condition ($targetCodeOnly -notmatch '(?i)\bpy\s+--version') (
        '生成Windowsガイドが曖昧なlegacy py launcherを案内している。')
}

Invoke-ContractTest '非空 Destination を拒否する' {
    $validGuard = $false
    $ifStatements = @($targetAst.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.IfStatementAst]
    }, $true))

    foreach ($ifStatement in $ifStatements) {
        $usesDestination = @($ifStatement.FindAll({
            param($candidate)
            $candidate -is [System.Management.Automation.Language.VariableExpressionAst] -and
            $candidate.VariablePath.UserPath -ieq 'Destination'
        }, $true)).Count -gt 0
        $hasTestPath = Test-NodeHasCommand -Node $ifStatement -Names @('Test-Path')
        $childEnumerations = @($ifStatement.FindAll({
            param($candidate)
            $candidate -is [System.Management.Automation.Language.CommandAst] -and
            $candidate.GetCommandName() -ieq 'Get-ChildItem'
        }, $true))
        $includesHiddenItems = $false
        foreach ($enumeration in $childEnumerations) {
            if (@($enumeration.CommandElements | Where-Object {
                $_ -is [System.Management.Automation.Language.CommandParameterAst] -and
                $_.ParameterName -ieq 'Force'
            }).Count -gt 0) {
                $includesHiddenItems = $true
                break
            }
        }

        if ($usesDestination -and $hasTestPath -and $childEnumerations.Count -gt 0 -and
            $includesHiddenItems -and (Test-NodeTerminates -Node $ifStatement)) {
            $validGuard = $true
            break
        }
    }
    Assert-Condition $validGuard (
        'Test-Path と Get-ChildItem -Force を使い、非空 Destination を throw する事前ガードがない。')
}

Invoke-ContractTest 'ルート必須 payload をコピーする' {
    foreach ($leaf in @('Import-OfflineKit.ps1', 'install-windows.cmd')) {
        Assert-Condition (Test-StaticCopyContract -Ast $targetAst -LeafName $leaf) (
            "Copy-Item と静的に結び付いた必須 payload がない: $leaf")
    }
}

Invoke-ContractTest '検証ツールと Windows ガイドを所定ディレクトリへコピーする' {
    Assert-Condition (Test-StaticCopyContract -Ast $targetAst -LeafName 'verify_endpoint.py' -ParentDirectory 'tools') (
        'verify_endpoint.py のコピー契約がない。')
    Assert-Condition (Test-StaticCopyContract -Ast $targetAst -LeafName 'WINDOWS.md' -ParentDirectory 'docs') (
        'WINDOWS.md のコピー契約がない。')
}

Invoke-ContractTest '3 個の必須 config を config ディレクトリへコピーする' {
    foreach ($leaf in @('chatLanguageModels.json', 'settings.offline.json', 'ollama-server.json')) {
        Assert-Condition (Test-StaticCopyContract -Ast $targetAst -LeafName $leaf -ParentDirectory 'config') (
            "Copy-Item と静的に結び付いた必須 config がない: $leaf")
    }
}

Invoke-ContractTest 'offline settings に4つのローカルモデル設定を持つ' {
    foreach ($settingName in @(
        'chat.utilityModel',
        'chat.utilitySmallModel',
        'chat.byokUtilityModelDefault',
        'inlineChat.defaultModel'
    )) {
        Assert-Condition ($targetCodeOnly -match [regex]::Escape($settingName)) (
            "offline settings の必須キーがない: $settingName")
    }
}

Invoke-ContractTest 'manifest に全必須トップレベルフィールドを持つ' {
    $required = @(
        'schemaVersion', 'createdAt', 'platform', 'architecture', 'model',
        'contextLength', 'components', 'files'
    )
    Assert-Condition (Test-AssignedHashtableHasKeys -Ast $targetAst `
        -VariableNames @('manifest', 'report') -RequiredKeys $required) (
        'manifest/report のトップレベル hashtable に必須フィールドが揃っていない。')
}

Invoke-ContractTest 'Windows manifest の固定値と UTC createdAt を生成する' {
    Assert-Condition ($targetCodeOnly -match '(?i)\bschemaVersion\s*=\s*1\b') (
        'schemaVersion = 1 がない。')
    Assert-Condition ($targetCodeOnly -match '(?i)\bplatform\s*=\s*["'']windows["'']') (
        'platform = windows がない。')
    Assert-Condition ($targetCodeOnly -match '(?i)\barchitecture\s*=\s*["'']x64["'']') (
        'architecture = x64 がない。')
    Assert-Condition ($targetCodeOnly -match '(?i)\bUtcNow\b|ToUniversalTime\s*\(') (
        'createdAt を UTC で生成する静的証拠がない。')
    Assert-Condition ($targetCodeOnly -match "(?i)yyyy-MM-dd'T'HH:mm:ss[.]fffffff'Z'") (
        'createdAt を PowerShell JSON round-trip可能な canonical UTC Z 形式で生成していない。')
}

Invoke-ContractTest 'manifest の model と正の contextLength を表現する' {
    Assert-Condition (Test-HashtableHasKeys -Ast $targetAst -RequiredKeys @(
        'name', 'digest', 'supportsToolCalling'
    )) 'model.name / digest / supportsToolCalling を同一オブジェクトで定義していない。'

    $literalContext = [regex]::Match(
        $targetCodeOnly,
        '(?i)\bcontextLength\s*=\s*(?<value>[1-9][0-9]*)\b')
    $hasPositiveLiteral = $literalContext.Success
    $hasValidatedVariable =
        $targetCodeOnly -match '(?i)ValidateRange\s*\(\s*1\s*,' -and
        $targetCodeOnly -match '(?i)\bcontextLength\s*=\s*\$ContextLength\b'
    Assert-Condition ($hasPositiveLiteral -or $hasValidatedVariable) (
        'contextLength の正の値または 1 以上の入力検証がない。')
}

Invoke-ContractTest 'Agent検証へ実効context期待値を渡す' {
    Assert-Condition ($targetCodeOnly -match '(?i)validationPort\s*=\s*11435') (
        '専用Ollama検証portを使用していない。')
    Assert-Condition ($targetCodeOnly -match '(?i)OLLAMA_CONTEXT_LENGTH\s*=\s*\[\s*string\s*\]\s*\$ContextLength') (
        '専用Ollama serverへContextLengthを設定していない。')
    Assert-Condition ($targetCodeOnly -match '(?i)Write-ValidationLogTail') (
        '専用Ollama serverの起動失敗ログを表示していない。')
    $startupLoops = @($targetAst.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.ForEachStatementAst] -and
        $candidate.Extent.Text -match '\$validationServer[.]HasExited' -and
        $candidate.Extent.Text -match 'Test-OllamaEndpoint'
    }, $true))
    $processExitCheckedFirst = $startupLoops.Count -eq 1 -and
        $startupLoops[0].Extent.Text.IndexOf('$validationServer.HasExited', [StringComparison]::Ordinal) -lt
        $startupLoops[0].Extent.Text.IndexOf('Test-OllamaEndpoint', [StringComparison]::Ordinal)
    Assert-Condition $processExitCheckedFirst (
        '専用Ollama process終了より先に別endpoint応答を受理する可能性がある。')
    Assert-Condition ($targetCodeOnly -match '(?i)--expected-context\s+\$ContextLength') (
        'verify_endpoint.py に --expected-context $ContextLength を渡していない。')
}

Invoke-ContractTest 'winget が改名した Ollama x64 installer を正規化する' {
    Assert-Condition ($targetCodeOnly -match '(?i)Ollama_.*_User_X64_inno') (
        'winget の実測 Ollama x64 installer 命名規則に対応していない。')
    Assert-Condition ($targetCodeOnly -match '(?i)canonicalOllamaInstaller.*OllamaSetup[.]exe') (
        'Ollama installer を kit 固定名へ正規化していない。')
}

Invoke-ContractTest 'manifest の components と files に必須メタデータを持つ' {
    $componentShape =
        (Test-HashtableHasKeys -Ast $targetAst -RequiredKeys @('name', 'required', 'version', 'path')) -or
        (Test-HashtableHasKeys -Ast $targetAst -RequiredKeys @('name', 'required', 'actualVersion', 'path'))
    Assert-Condition $componentShape (
        'components 要素に name / required / actual version / path が揃っていない。')
    Assert-Condition (Test-HashtableHasKeys -Ast $targetAst -RequiredKeys @(
        'path', 'bytes', 'sha256'
    )) 'files 要素に path / bytes / sha256 が揃っていない。'
}

Invoke-ContractTest 'SkipHash オプションとハッシュ省略分岐を持たない' {
    $skipHashReferences = @($targetAst.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.VariableExpressionAst] -and
        $candidate.VariablePath.UserPath -ieq 'SkipHash'
    }, $true))
    Assert-Condition ($skipHashReferences.Count -eq 0) (
        'SkipHash パラメーターまたは参照が残っている。')
    Assert-Condition ($targetCodeOnly -notmatch '(?i)\bSkipHash\b') (
        'コードトークンに SkipHash が残っている。')
}

Invoke-ContractTest 'createdOn と COMPUTERNAME を manifest に記録しない' {
    Assert-Condition ($targetCodeOnly -notmatch '(?i)\bcreatedOn\b') (
        'createdOn フィールドが残っている。')
    Assert-Condition ($targetCodeOnly -notmatch '(?i)COMPUTERNAME') (
        '準備機名 COMPUTERNAME を参照している。')
}

Invoke-ContractTest '取得処理の catch はすべて fail-closed で終了する' {
    $openCatches = @($targetAst.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.CatchClauseAst]
    }, $true) | Where-Object { -not (Test-NodeTerminates -Node $_) })
    $lines = @($openCatches | ForEach-Object { $_.Extent.StartLineNumber }) -join ', '
    Assert-Condition ($openCatches.Count -eq 0) (
        "throw せず継続する catch がある (line: $lines)。")
}

Invoke-ContractTest '必須取得失敗を警告だけで継続しない' {
    $failureCue = '(?i)(見つかりません|失敗|欠落|取得でき|スキップ|not found|failed|missing|unable|skip)'
    $warningOnlyFailures = @($targetAst.FindAll({
        param($candidate)
        $candidate -is [System.Management.Automation.Language.IfStatementAst]
    }, $true) | Where-Object {
        $ifAst = $_
        $hasWarning = Test-NodeHasCommand -Node $ifAst -Names @('Write-Warn', 'Write-Warning')
        $hasFailureMessage = @($ifAst.FindAll({
            param($nested)
            ($nested -is [System.Management.Automation.Language.StringConstantExpressionAst] -or
             $nested -is [System.Management.Automation.Language.ExpandableStringExpressionAst]) -and
            $nested.Value -match $failureCue
        }, $true)).Count -gt 0
        return $hasWarning -and $hasFailureMessage -and -not (Test-NodeTerminates -Node $ifAst)
    })
    $lines = @($warningOnlyFailures | ForEach-Object { $_.Extent.StartLineNumber }) -join ', '
    Assert-Condition ($warningOnlyFailures.Count -eq 0) (
        "必須取得失敗を Write-Warn だけで継続する分岐がある (line: $lines)。")
}

Write-Host ''
Write-Host ("Result: {0} passed, {1} failed" -f $script:PassedCount, $script:FailedCount)
if ($script:FailedCount -gt 0) {
    Write-Host 'Failures:' -ForegroundColor Red
    foreach ($failure in $script:FailureMessages) {
        Write-Host "  $failure" -ForegroundColor Red
    }
    exit 1
}
exit 0
