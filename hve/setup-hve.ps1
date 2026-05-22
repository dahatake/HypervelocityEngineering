[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$WithWorkIQ,
    [switch]$WithGui,
    [switch]$NoGui,
    [switch]$WithSkills,
    [switch]$InstallExternalCopilotCli,
    [switch]$Force,
    [switch]$SkipMdq,
    [switch]$SkipMdqWatch
)

# -Force: 冪等な完全再構築モード。.venv を無条件削除して再作成し、
# GUI extras (PySide6 + markitdown) を含むすべての必須/推奨依存を導入する。
# -NoGui を併用した場合のみ GUI extras を除外。extras インストール失敗は
# WARN ではなく ERROR として扱い（exit 1）、追加タスク無しで hve/gui/cli が
# 起動できることを保証する。非対話・確認プロンプト無し（CI 利用可）。
if ($Force -and -not $NoGui) { $WithGui = $true }
$script:ErrorEscalate = [bool]$Force

$ErrorActionPreference = "Stop"
$script:WarningCount = 0
$script:GhAuthOk = $false

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message"
}

function Write-SetupWarning {
    param([string]$Message)
    $script:WarningCount++
    Write-Warning $Message
}

function Invoke-Critical {
    param(
        [string]$Message,
        [scriptblock]$Action
    )
    try {
        & $Action
    } catch {
        if ($script:ErrorEscalate) {
            throw ($Message + ": " + $_.Exception.Message)
        }
        Write-SetupWarning ($Message + ": " + $_.Exception.Message)
    }
}

function Resolve-PreferredCommand {
    param(
        [string]$Name,
        [string[]]$PreferredNames = @()
    )
    foreach ($candidate in $PreferredNames) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    $fallback = Get-Command $Name -ErrorAction SilentlyContinue
    if ($fallback) { return $fallback.Source }
    return $null
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    Write-Host ("> {0} {1}" -f $FilePath, ($Arguments -join " "))
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-Probe {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments *> $null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Get-PythonInfo {
    param(
        [string]$Exe,
        [string[]]$Args = @(),
        [string]$Label = $Exe
    )
    $pythonCode = "import sys; print(sys.executable); print(f'{sys.version_info.major} {sys.version_info.minor} {sys.version_info.micro}')"
    try {
        $output = & $Exe @Args -c $pythonCode 2>$null
        if ($LASTEXITCODE -ne 0 -or $output.Count -lt 2) { return $null }
        $versionParts = ($output[1] -split " ") | ForEach-Object { [int]$_ }
        return [pscustomobject]@{
            Exe = $Exe
            Args = $Args
            Label = $Label
            Executable = $output[0]
            Major = $versionParts[0]
            Minor = $versionParts[1]
            Patch = $versionParts[2]
        }
    } catch {
        return $null
    }
}

function Test-IsPython311OrNewer {
    param($Info)
    return ($Info -and ($Info.Major -gt 3 -or ($Info.Major -eq 3 -and $Info.Minor -ge 11)))
}

function Find-Python311 {
    $candidates = @()
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $candidates += [pscustomobject]@{ Exe = $py.Source; Args = @("-3.11"); Label = "py -3.11" }
    }
    foreach ($name in @("python", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += [pscustomobject]@{ Exe = $command.Source; Args = @(); Label = $name }
        }
    }
    foreach ($candidate in $candidates) {
        $info = Get-PythonInfo -Exe $candidate.Exe -Args $candidate.Args -Label $candidate.Label
        if (Test-IsPython311OrNewer $info) { return $info }
    }
    return $null
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

Set-Location $repoRoot

Write-Step "Checking required tools"
$git = Resolve-PreferredCommand -Name "git"
if ($git) { Write-Host "Git: $git" } else { Write-SetupWarning "Git was not found. Install on a clean Windows OS:`n        winget install Git.Git    or    https://git-scm.com/download/win" }

$gh = Resolve-PreferredCommand -Name "gh"
if ($gh) { Write-Host "GitHub CLI: $gh" } else { Write-SetupWarning "GitHub CLI was not found. Install on a clean Windows OS:`n        winget install GitHub.cli    or    https://cli.github.com/" }

$python = Find-Python311
if ($python) {
    Write-Host ("Python: {0} ({1}.{2}.{3})" -f $python.Executable, $python.Major, $python.Minor, $python.Patch)
} else {
    Write-SetupWarning "Python 3.11+ was not found. Install on a clean Windows OS:`n        winget install Python.Python.3.13`n        or download from https://www.python.org/downloads/`n        Make sure to check 'Add python.exe to PATH'."
    if (-not $CheckOnly) { exit 1 }
}

if ($WithWorkIQ) {
    Write-Step "Checking Work IQ prerequisites"
    foreach ($tool in @("node", "npm")) {
        $resolved = Resolve-PreferredCommand -Name $tool -PreferredNames @("$tool.cmd", "$tool.exe")
        if ($resolved) { Write-Host "${tool}: $resolved" } else { Write-SetupWarning "$tool was not found. Install Node.js before using Work IQ." }
    }
    $npx = Resolve-PreferredCommand -Name "npx" -PreferredNames @("npx.cmd", "npx.exe")
    if ($npx) { Write-Host "npx: $npx" } else { Write-SetupWarning "npx was not found. Work IQ requires npx." }
    Write-Host "Work IQ may require Microsoft 365 sign-in, EULA acceptance, and Entra ID admin consent."
}

if ($InstallExternalCopilotCli) {
    Write-Step "Checking external Copilot CLI"
    $copilot = Resolve-PreferredCommand -Name "copilot" -PreferredNames @("copilot.cmd", "copilot.exe")
    if ($copilot) {
        Write-Host "External Copilot CLI: $copilot"
    } elseif ($CheckOnly) {
        Write-SetupWarning "External Copilot CLI was not found. It is optional unless COPILOT_CLI_PATH or --cli-path is used."
    } else {
        $winget = Resolve-PreferredCommand -Name "winget"
        if (-not $winget) { throw "winget was not found. Install Copilot CLI manually from GitHub Docs." }
        Invoke-Checked -FilePath $winget -Arguments @("install", "--id", "GitHub.Copilot", "-e", "--source", "winget", "--accept-package-agreements", "--accept-source-agreements")
    }
}

Write-Step "Checking Python virtual environment"
if ($Force -and -not $CheckOnly -and (Test-Path $venvDir)) {
    Write-Host "-Force specified: removing existing .venv at $venvDir"
    Remove-Item -Recurse -Force $venvDir
}
if (Test-Path $venvPython) {
    $venvInfo = Get-PythonInfo -Exe $venvPython -Label ".venv"
    if (Test-IsPython311OrNewer $venvInfo) {
        Write-Host ("Existing .venv Python: {0}.{1}.{2}" -f $venvInfo.Major, $venvInfo.Minor, $venvInfo.Patch)
    } else {
        Write-SetupWarning "Existing .venv is older than Python 3.11. Rerun with -Force to recreate it."
        if (-not $CheckOnly) { exit 1 }
    }
} elseif ($CheckOnly) {
    Write-SetupWarning ".venv does not exist. Run without -CheckOnly to create it."
}

if (-not $CheckOnly -and -not (Test-Path $venvPython)) {
    if (-not $python) { throw "Python 3.11+ is required to create .venv." }
    Invoke-Checked -FilePath $python.Exe -Arguments @($python.Args + @("-m", "venv", $venvDir))
}

if (Test-Path $venvPython) {
    if (-not $CheckOnly) {
        Write-Step "Installing Python dependencies"
        Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
        Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "github-copilot-sdk")

        if (-not $SkipMdq) {
            $baseExtras = if ($SkipMdqWatch) { "mdq" } else { "mdq-watch" }
            # mdq-ja は Q5=A 採用上は空 extras（プレースホルダー）だが、今後形態素
            # 解析器を追加する際の拡張点として同梱しておく。
            $extrasTarget = "$baseExtras,mdq-ja"
            Write-Step ("Installing markdown-query optional extras ([{0}])" -f $extrasTarget)
            try {
                Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "-e", ".[$extrasTarget]")
                Write-Host ("[{0}] extras installed." -f $extrasTarget)
            } catch {
                if ($script:ErrorEscalate) { throw ("Failed to install [$extrasTarget] extras: " + $_.Exception.Message) }
                Write-SetupWarning ("Failed to install [$extrasTarget] extras: " + $_.Exception.Message + ". markdown-query Skill will still work with built-in fallback. Re-run later: " + $venvPython + ' -m pip install -e ".[' + $extrasTarget + ']"')
            }
            # FTS5 trigram tokenizer（日本語 ja-jp に使用）のサポートをプローブ。
            $trigramCode = @'
import sqlite3, sys
c = sqlite3.connect(':memory:')
try:
    c.execute("CREATE VIRTUAL TABLE p USING fts5(x, tokenize='trigram')")
    sys.exit(0)
except Exception:
    sys.exit(1)
'@
            $trigramExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-c", $trigramCode)
            if ($trigramExitCode -eq 0) {
                Write-Host "FTS5 trigram tokenizer (ja-jp 用): OK"
            } else {
                Write-SetupWarning "FTS5 trigram tokenizer が未サポートです。SQLite 3.34+ を推奨。フォールバックとして unicode61 が使用されます。"
            }
        }

        if ($WithGui) {
            Write-Step "Installing GUI Orchestrator extras ([gui,gui-docconvert]) including markitdown"
            try {
                Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "-e", ".[gui,gui-docconvert]")
                Write-Host "[gui,gui-docconvert] extras installed (PySide6 + markitdown[all])."
                Write-Step "Downloading Mermaid / KaTeX assets for Markdown preview"
                try {
                    Invoke-Checked -FilePath $venvPython -Arguments @("-m", "hve.gui.markdown_preview.download_assets")
                } catch {
                    Write-SetupWarning ("Asset download had failures: " + $_.Exception.Message + ". Markdown body will still render; Mermaid/KaTeX will be disabled.")
                }
            } catch {
                if ($script:ErrorEscalate) { throw ("Failed to install [gui,gui-docconvert] extras: " + $_.Exception.Message) }
                Write-SetupWarning ("Failed to install [gui,gui-docconvert] extras: " + $_.Exception.Message + ". Re-run later: " + $venvPython + ' -m pip install -e ".[gui,gui-docconvert]"')
            }
        }
    }

    Write-Step "Verifying HVE runtime"
    $importExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-c", "import copilot")
    if ($importExitCode -eq 0) { Write-Host "github-copilot-sdk import: OK" } else { Write-SetupWarning "github-copilot-sdk import failed. Run without -CheckOnly to install dependencies." }

    $hveHelpExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-m", "hve", "--help")
    if ($hveHelpExitCode -eq 0) { Write-Host "python -m hve --help: OK" } else { Write-SetupWarning "python -m hve --help failed." }

    if (-not $SkipMdq) {
        $mdqHelpExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-m", "mdq", "--help")
        if ($mdqHelpExitCode -eq 0) { Write-Host "python -m mdq --help: OK" } else { Write-SetupWarning "python -m mdq --help failed. markdown-query Skill may not be available." }

        if ($CheckOnly) {
            $mdqExtrasExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-c", "import rank_bm25, tiktoken")
            if ($mdqExtrasExitCode -eq 0) { Write-Host "[mdq] extras: OK (rank_bm25, tiktoken)" } else { Write-SetupWarning "[mdq] extras missing. Run without -CheckOnly to install, or pass -SkipMdq to suppress this check." }
            if (-not $SkipMdqWatch) {
                $watchExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-c", "import watchdog")
                if ($watchExitCode -eq 0) { Write-Host "[mdq-watch] extras: OK (watchdog)" } else { Write-SetupWarning "[mdq-watch] extras missing (watchdog). HVE CLI Orchestrator のリアルタイム索引更新は無効になります。Run without -CheckOnly to install, or pass -SkipMdqWatch to suppress this check." }
            }
        }
    }

    if ($WithGui -and $CheckOnly) {
        $guiImportExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-c", "import PySide6")
        if ($guiImportExitCode -eq 0) { Write-Host "[gui] extras: OK (PySide6)" } else { Write-SetupWarning "[gui] extras missing (PySide6). Run without -CheckOnly to install." }
        $mdImportExitCode = Invoke-Probe -FilePath $venvPython -Arguments @("-c", "import markitdown")
        if ($mdImportExitCode -eq 0) { Write-Host "[gui-docconvert] extras: OK (markitdown)" } else { Write-SetupWarning "[gui-docconvert] extras missing (markitdown). Run without -CheckOnly to install." }
        # i18n translation tools (PySide6 同梱)
        $lupdate = Resolve-PreferredCommand -Name "pyside6-lupdate"
        if ($lupdate) { Write-Host "pyside6-lupdate: OK ($lupdate)" } else { Write-SetupWarning "pyside6-lupdate not found on PATH. GUI 多言語化リソース (.ts) の更新には PySide6 同梱の pyside6-lupdate / pyside6-lrelease が必要です。" }
    }

    # GUI 翻訳バイナリ (.qm) の自動生成: WithGui かつ .ts が存在し .qm が古い/欠落の場合
    if ($WithGui -and -not $CheckOnly) {
        $tsPath = Join-Path $repoRoot "hve\gui\i18n\hve_gui_en_US.ts"
        $qmPath = Join-Path $repoRoot "hve\gui\i18n\hve_gui_en_US.qm"
        if (Test-Path $tsPath) {
            $needBuild = $true
            if (Test-Path $qmPath) {
                $tsTime = (Get-Item $tsPath).LastWriteTime
                $qmTime = (Get-Item $qmPath).LastWriteTime
                if ($qmTime -ge $tsTime) { $needBuild = $false }
            }
            if ($needBuild) {
                $lrelease = Resolve-PreferredCommand -Name "pyside6-lrelease"
                if ($lrelease) {
                    Write-Step "Compiling GUI translations (hve_gui_en_US.ts -> .qm)"
                    try {
                        Invoke-Checked -FilePath $lrelease -Arguments @($tsPath, "-qm", $qmPath)
                        Write-Host "GUI translations compiled: $qmPath"
                    } catch {
                        Write-SetupWarning ("Failed to compile GUI translations: " + $_.Exception.Message + ". 英語表示にフォールバックする際は日本語のままになります。")
                    }
                } else {
                    Write-SetupWarning "pyside6-lrelease not found; skipping GUI translation compile. Run manually: pyside6-lrelease hve/gui/i18n/translations.pro"
                }
            }
        }
    }
}

if ($WithSkills -and -not $CheckOnly) {
    Write-Step "Installing externally-sourced agent skills (microsoft/skills)"
    $npx = Resolve-PreferredCommand -Name "npx"
    if (-not $npx) {
        Write-SetupWarning "npx not found on PATH. Skipping skills install. Install Node.js 20+ first, then re-run: npx skills add microsoft/skills --skill '*' --agent copilot --yes --copy"
    } else {
        try {
            Invoke-Checked -FilePath $npx -Arguments @("-y", "skills", "add", "microsoft/skills", "--skill", "*", "--agent", "copilot", "--yes", "--copy")
            Write-Host "microsoft/skills installed under .github/skills/azure-skills/ (gitignored)."
        } catch {
            Write-SetupWarning ("Failed to install microsoft/skills: " + $_.Exception.Message + ". Re-run later: npx skills add microsoft/skills --skill '*' --agent copilot --yes --copy")
        }
    }
}

if ($gh) {
    Write-Step "Checking GitHub authentication"
    $ghAuthExitCode = Invoke-Probe -FilePath $gh -Arguments @("auth", "status")
    if ($ghAuthExitCode -eq 0) {
        $script:GhAuthOk = $true
        Write-Host "gh auth status: OK"
    } else {
        Write-SetupWarning "gh auth status failed. Run 'gh auth login' before using GitHub operations."
    }
}

Write-Step "Next steps"
if ($gh) {
    if ($script:GhAuthOk) {
        Write-Host "GitHub auth: OK (gh auth status)"
    } else {
        Write-Host "Authenticate GitHub CLI if needed: gh auth login"
        Write-Host "Then verify: gh auth status"
    }
}
if (Test-Path $venvPython) {
    Write-Host "Basic runtime check: $venvPython -m hve --help"
    if (-not $SkipMdq) {
        Write-Host "Markdown query (local): $venvPython -m mdq index ; $venvPython -m mdq stats"
        if (-not $SkipMdqWatch) {
            Write-Host "Markdown query (realtime, CLI Orchestrator only): watchdog installed. Disable with --no-mdq-watch or HVE_MDQ_WATCH=0."
        }
    }

    # `python -m hve` を直接叩けるよう venv アクティベート手順を案内し、
    # 現在 PATH 上の `python` が venv を指していない場合は警告する。
    $activateScript = Join-Path $venvDir "Scripts\Activate.ps1"
    Write-Host ""
    Write-Host "To use 'python -m hve' directly in this shell, activate the venv:"
    Write-Host "  . $activateScript"
    Write-Host "Or always use the full venv path shown above."

    $pythonOnPath = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonOnPath) {
        try {
            $resolved = (Resolve-Path $pythonOnPath.Source -ErrorAction Stop).Path
            $venvResolved = (Resolve-Path $venvPython -ErrorAction Stop).Path
            if ($resolved -ne $venvResolved) {
                Write-SetupWarning ("'python' on PATH ($resolved) is NOT the venv Python ($venvResolved). Running 'python -m hve' will fail with ModuleNotFoundError. Activate the venv first: . $activateScript")
            }
        } catch { }
    }
} else {
    Write-Host "Create .venv first (run setup without -CheckOnly), then run: .venv\\Scripts\\python.exe -m hve --help"
}
Write-Host "Optional: Node.js / npm / npx are only required when using Work IQ or Node-based MCP tools."
if ($SkipMdq) {
    Write-Host "markdown-query [mdq] extras skipped (-SkipMdq). Built-in fallback (MiniBM25) will be used."
} elseif ($SkipMdqWatch) {
    Write-Host "markdown-query watcher extras skipped (-SkipMdqWatch). [mdq] installed but watchdog is not; HVE CLI Orchestrator realtime index update will be disabled."
}
if ($WithGui) {
    Write-Host "GUI Orchestrator: PySide6 + markitdown installed. Launch with: $venvPython -m hve gui"
} else {
    Write-Host "GUI Orchestrator: skipped. To enable, re-run with -WithGui (installs PySide6 and markitdown for attachment Markdown conversion)."
}
if ($WithSkills) {
    Write-Host "Azure agent skills: installed via npx skills add microsoft/skills."
} else {
    Write-Host "Azure agent skills: skipped. To install externally-sourced skills under .github/skills/azure-skills/, re-run with -WithSkills (requires Node.js / npx)."
}

if ($CheckOnly) {
    Write-Host "`nCheck-only completed with $script:WarningCount warning(s)."
} else {
    Write-Host "`nHVE setup completed with $script:WarningCount warning(s)."
}
