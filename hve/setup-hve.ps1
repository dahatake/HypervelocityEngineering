# ============================================================
# hve/setup-hve.ps1 — HVE 完全セットアップ (Windows / PowerShell)
#
# 目的:
#   OS しか入っていないクリーンな Windows 環境から、HVE の CLI と GUI の
#   全機能を実行できる .venv をゼロから構築する。
#
# 既定で導入する extras (pyproject.toml [project.optional-dependencies] と一致):
#   - test         : pytest (repository / VS Code task verification)
#   - mdq-watch    : rank_bm25, tiktoken, watchdog
#   - mdq-ja       : (現状空。将来の形態素解析器拡張用)
#   - semantic     : fastembed, nltk, numpy   (semantic_paragraph 戦略)
#   - gui          : PySide6, markdown-it-py, mdit-py-plugins, Pygments
#   - gui-pty      : pywinpty  (GUI 内 PTY で copilot/az/gh の対話認証)
#   - gui-docconvert: markitdown[pdf,docx,pptx,xlsx,xls,outlook]
#   - code         : tree-sitter 文法 + sqlglot (code-query Skill の高フィデリティ解析)
#
# opt-in の extras (既定では導入しない):
#   - graphrag     : lightrag-hku  (graphrag 戦略)。-Graphrag 指定時のみ。
#                    pandas を 2.4 未満へダウングレードし、別途 Ollama の
#                    導入と起動、モデル取得が必要なため既定では入れない。
#
# winget で導入する OS ツール (未導入時のみ。-NoInstallTools で抑止):
#   - Git.Git             : リポジトリ操作 / git diff
#   - GitHub.cli          : gh auth login / Issue / PR
#   - OpenJS.NodeJS.LTS   : MCP Server / Work IQ / npx skills
#   - Microsoft.AzureCLI  : Azure 系ワークフロー (asdw-* / ADFD)
#   - koalaman.shellcheck : ASDW Step 1.2 の静的検証
#   - @github/copilot     : GUI の Copilot チャットパネル (npm -g、Node.js 導入後)
#
# 追加で行うこと:
#   - グローバル Python 環境からの遮断 (PYTHONPATH/PYTHONHOME/PIP_* の無効化、
#     グローバルへ誤導入された hve の除去、隔離性の検証)
#   - venv (stdlib モジュール) の利用可否確認と不足時の修復案内
#   - .venv 作成 / 検証 (Python 3.11+ 必須)
#   - pip / setuptools / wheel をアップグレード
#   - editable install: pip install -e .
#   - github-copilot-sdk を hve\copilot-sdk.lock 固定版で導入 (--no-deps で
#     pydantic-core 不整合を回避) し、pin された Copilot ランタイムを
#     先読みして版の整合を検証 (-UpgradeSdk で最新化 + lock 更新)
#   - nltk punkt_tab を事前ダウンロード (semantic 初回ビルドのオフライン安定化)
#   - Mermaid / KaTeX アセット DL (Markdown プレビュー)
#   - GUI 翻訳 .ts → .qm コンパイル (pyside6-lrelease)
#   - git / gh / Python の存在確認と winget での導入手順案内
#
# 使い方:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File hve\setup-hve.ps1
#       既定: 全 extras を導入 (CLI + GUI 完全構成)
#   ... -CheckOnly         状態確認のみ。変更なし (通常 GUI 構成では gh / PTY backend
#                          の不足を警告として報告するが、非ゼロ終了はしない)
#   ... -NoGui             GUI 系 extras をスキップ (CLI 専用)
#   ... -Graphrag          graphrag extras を追加で導入 (別途 Ollama が必要)
#   ... -CodeLanguages python,csharp
#                          code-query の tree-sitter 文法を指定言語だけに絞る
#                          (未指定なら全言語。受理する名前は $CodeLanguageExtras を参照)
#   ... -Minimal           runtime base のみ (extras / pytest なし)
#   ... -Force             .venv を無条件削除し再構築
#   ... -SkipNltkDownload  nltk punkt_tab の事前 DL をスキップ
#   ... -WithSkills        microsoft/skills を npx で .github/skills/azure-skills/ に導入
#   ... -UpgradeSdk        github-copilot-sdk を最新化し hve\copilot-sdk.lock を更新
#   ... -Yes               確認プロンプトをスキップ (Python の winget 自動導入を含む)
#   ... -NoInstallPython   Python の winget 自動導入を行わない
#   ... -NoInstallTools    git / gh / Node.js / Azure CLI / ShellCheck / Copilot CLI の
#                          自動導入を行わない (検出と手動導入手順の案内のみ)
#   ... -NoGlobalCleanup   グローバル Python に導入された hve を除去しない (検出と警告のみ)
# ============================================================
[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$NoGui,
    [switch]$Graphrag,
    [string]$CodeLanguages = '',
    [switch]$Minimal,
    [switch]$Force,
    [switch]$SkipNltkDownload,
    [switch]$WithSkills,
    [switch]$UpgradeSdk,
    [switch]$Yes,
    [switch]$NoInstallPython,
    [switch]$NoInstallTools,
    [switch]$NoGlobalCleanup
)

$ErrorActionPreference = 'Stop'
$script:WarningCount = 0

# PowerShell 7+ (PSEdition Core) 必須。Windows PowerShell 5.x へはフォールバックしない。
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    Write-Host "[ERROR] PowerShell 7+ is required. Current: $($PSVersionTable.PSVersion)" -ForegroundColor Red
    Write-Host "        Install via: winget install --id Microsoft.PowerShell -e --source winget" -ForegroundColor Yellow
    Write-Host "        Or: https://aka.ms/install-powershell" -ForegroundColor Yellow
    Write-Host "        Then re-run this script with 'pwsh' instead of 'powershell'." -ForegroundColor Yellow
    exit 1
}

function Write-Step([string]$Msg) { Write-Host "`n==> $Msg" -ForegroundColor Cyan }
function Write-Ok([string]$Msg)   { Write-Host "  [OK] $Msg" -ForegroundColor Green }
function Write-Warn2([string]$Msg) { $script:WarningCount++; Write-Host "  [WARN] $Msg" -ForegroundColor Yellow }
function Write-ErrLine([string]$Msg) { Write-Host "  [ERROR] $Msg" -ForegroundColor Red }

function Invoke-Checked {
    param([string]$Exe, [string[]]$ArgList)
    Write-Host "  > $Exe $($ArgList -join ' ')" -ForegroundColor DarkGray
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit=$LASTEXITCODE): $Exe $($ArgList -join ' ')"
    }
}

function Invoke-Probe {
    param([string]$Exe, [string[]]$ArgList)
    # ネイティブコマンドの stderr が Stop ポリシー下でも例外化しないよう、一時的に Continue。
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # 出力は捨て、終了コードのみ取得。
        $null = & $Exe @ArgList 2>&1
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Find-Python311 {
    # 候補生成: py launcher (バージョン別) + python / python3
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($ver in '-3.14','-3.13','-3.12','-3.11','-3') {
            $candidates += [pscustomobject]@{ Exe='py'; ExtraArgs=@($ver) }
        }
    }
    foreach ($n in 'python','python3') {
        if (Get-Command $n -ErrorAction SilentlyContinue) {
            $candidates += [pscustomobject]@{ Exe=$n; ExtraArgs=@() }
        }
    }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        foreach ($c in $candidates) {
            # `--version` は "Python X.Y.Z" を返す。f-string の二重引用符を避けて堅牢化。
            $verArgs = $c.ExtraArgs + @('--version')
            $raw = & $c.Exe @verArgs 2>&1
            if ($LASTEXITCODE -ne 0 -or -not $raw) { continue }
            $line = ($raw | Out-String).Trim()
            if ($line -match 'Python\s+(\d+)\.(\d+)\.(\d+)') {
                $maj = [int]$Matches[1]; $min = [int]$Matches[2]
                if ($maj -gt 3 -or ($maj -eq 3 -and $min -ge 11)) {
                    return [pscustomobject]@{
                        Exe       = $c.Exe
                        ExtraArgs = $c.ExtraArgs
                        Version   = "$maj.$min.$($Matches[3])"
                    }
                }
            }
        }
    } finally {
        $ErrorActionPreference = $prev
    }
    return $null
}

function Update-PathFromRegistry {
    # winget 導入直後の実行ファイルを同一セッションで解決できるようにする。
    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path','User')
}

function Install-OsTool {
    # 未導入なら winget で導入する。値は返さず、状態はメッセージで報告する。
    param(
        [Parameter(Mandatory)][string]$Command,
        [Parameter(Mandatory)][string]$WingetId,
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][string]$Purpose
    )
    $found = Get-Command $Command -ErrorAction SilentlyContinue
    if ($found) { Write-Ok "$Label : $($found.Source)"; return }

    $hint = "winget install --id $WingetId -e --source winget"
    if ($CheckOnly -or $NoInstallTools) {
        Write-Warn2 "$Label not found ($Purpose). Install: $hint"
        return
    }
    $proceed = $Yes
    if (-not $proceed) {
        $resp = Read-Host "Install $Label via winget? ($Purpose) [y/N]"
        $proceed = ($resp -match '^[Yy]$')
    }
    if (-not $proceed) { Write-Warn2 "$Label skipped. Install later: $hint"; return }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Warn2 "winget not found. Install 'App Installer' from the Microsoft Store, then: $hint"
        return
    }

    # user scope を優先し、user scope 非対応パッケージ (MSI 等) は既定 scope で再試行。
    $installed = $false
    foreach ($scopeArgs in @(@('--scope','user'), @())) {
        $wingetArgs = @('install','--id',$WingetId,'-e','--source','winget') + $scopeArgs +
                      @('--accept-source-agreements','--accept-package-agreements','--silent')
        Write-Host "  > winget $($wingetArgs -join ' ')" -ForegroundColor DarkGray
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { & winget @wingetArgs 2>&1 | Out-Host } finally { $ErrorActionPreference = $prev }
        if ($LASTEXITCODE -eq 0) { $installed = $true; break }
    }
    if (-not $installed) {
        Write-Warn2 "$Label install failed. Install manually: $hint"
        return
    }

    Update-PathFromRegistry
    $found = Get-Command $Command -ErrorAction SilentlyContinue
    if ($found) { Write-Ok "$Label installed: $($found.Source)" }
    else { Write-Warn2 "$Label installed but '$Command' is not on PATH yet. Open a new terminal and re-run." }
}

# ---------- グローバル Python 環境からの遮断 ----------
function Clear-InheritedPythonEnv {
    # PYTHONPATH / PYTHONHOME / PIP_* が継承されていると .venv の python でも
    # グローバル環境の import 解決が混入し、.venv を作る意味が失われる。
    # 本プロセス内だけを無効化する（ユーザーの永続環境変数は変更しない）。
    $vars = @(
        'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONUSERBASE',
        'PIP_TARGET', 'PIP_PREFIX', 'PIP_USER', 'PIP_PYTHON', 'PIP_REQUIRE_VIRTUALENV'
    )
    $cleared = @()
    foreach ($v in $vars) {
        $cur = [Environment]::GetEnvironmentVariable($v, 'Process')
        if (-not [string]::IsNullOrEmpty($cur)) {
            $cleared += "$v=$cur"
            Remove-Item -LiteralPath "Env:$v" -ErrorAction SilentlyContinue
        }
    }
    $env:PYTHONNOUSERSITE = '1'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    return $cleared
}

function Get-PythonEnvPaths {
    # 指定 Python の site-packages / Scripts ディレクトリを JSON で取得する。
    param([Parameter(Mandatory)][pscustomobject]$Python)
    $code = @'
import json, site, sys, sysconfig
sites = []
try:
    sites.extend(site.getsitepackages())
except Exception:
    pass
purelib = sysconfig.get_paths().get('purelib')
if purelib:
    sites.append(purelib)
try:
    sites.append(site.getusersitepackages())
except Exception:
    pass
scripts = []
s = sysconfig.get_paths().get('scripts')
if s:
    scripts.append(s)
try:
    scripts.append(sysconfig.get_path('scripts', 'nt_user' if sys.platform == 'win32' else 'posix_user'))
except Exception:
    pass
print(json.dumps({
    'site': [p for p in dict.fromkeys(sites) if p],
    'scripts': [p for p in dict.fromkeys(scripts) if p],
}))
'@
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $Python.Exe @($Python.ExtraArgs + @('-c', $code)) 2>$null
    } finally { $ErrorActionPreference = $prev }
    if ($LASTEXITCODE -ne 0 -or -not $out) {
        return [pscustomobject]@{ site = @(); scripts = @() }
    }
    try { return (($out | Out-String).Trim() | ConvertFrom-Json) }
    catch { return [pscustomobject]@{ site = @(); scripts = @() } }
}

function Remove-GlobalHveInstall {
    # グローバル Python に導入された hve を検出して除去する。
    # 古い editable install は MAPPING を導入時点で凍結するため、後から
    # pyproject に追加されたトップレベルパッケージ (cq 等) を解決できず、
    # PATH 上で .venv を shadow して ModuleNotFoundError の原因になる。
    param([Parameter(Mandatory)][pscustomobject]$Python)

    $hasHve = (Invoke-Probe -Exe $Python.Exe -ArgList ($Python.ExtraArgs + @('-m','pip','show','hve'))) -eq 0

    $paths = Get-PythonEnvPaths -Python $Python
    $residue = @()
    foreach ($sp in @($paths.site)) {
        if (-not (Test-Path -LiteralPath $sp)) { continue }
        $residue += @(Get-ChildItem -LiteralPath $sp -Force -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -like '__editable__*hve*' -or $_.Name -like 'hve-*.dist-info' -or $_.Name -eq 'hve.egg-link'
        })
    }
    foreach ($sd in @($paths.scripts)) {
        if (-not (Test-Path -LiteralPath $sd)) { continue }
        $residue += @(Get-ChildItem -LiteralPath $sd -Force -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -in @('hve.exe','hve-script.py','hve-mdq.exe','mdq.exe')
        })
    }

    if (-not $hasHve -and $residue.Count -eq 0) {
        Write-Ok 'No hve installation in the global Python environment'
        return
    }

    Write-Warn2 'hve is installed in the GLOBAL Python environment. It shadows .venv on PATH and a stale editable install cannot resolve packages added later (e.g. cq) -> ModuleNotFoundError.'
    foreach ($r in $residue) { Write-Host "    residue: $($r.FullName)" -ForegroundColor DarkGray }

    if ($CheckOnly) { Write-Host '    Re-run without -CheckOnly to remove it.'; return }
    if ($NoGlobalCleanup) { Write-Host '    -NoGlobalCleanup specified: leaving the global install in place.'; return }

    $proceed = $Yes
    if (-not $proceed) {
        $resp = Read-Host 'Uninstall hve from the GLOBAL Python environment? (.venv keeps its own isolated copy) [Y/n]'
        $proceed = ($resp -notmatch '^[Nn]')
    }
    if (-not $proceed) {
        Write-Warn2 "Global hve left in place. The 'hve' command on PATH may keep resolving to it."
        return
    }

    if ($hasHve) {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { & $Python.Exe @($Python.ExtraArgs + @('-m','pip','uninstall','-y','hve')) | Out-Host }
        finally { $ErrorActionPreference = $prev }
    }
    foreach ($r in $residue) {
        if (-not (Test-Path -LiteralPath $r.FullName)) { continue }
        try {
            Remove-Item -LiteralPath $r.FullName -Recurse -Force -ErrorAction Stop
            Write-Host "    removed: $($r.FullName)" -ForegroundColor DarkGray
        } catch {
            Write-Warn2 "Could not remove $($r.FullName): $($_.Exception.Message)"
        }
    }
    Update-PathFromRegistry
    Write-Ok 'Global hve installation removed'
}

# ---------- パス解決 ----------
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Resolve-Path (Join-Path $scriptDir '..')
$venvDir   = Join-Path $repoRoot '.venv'
$venvPy    = Join-Path $venvDir 'Scripts\python.exe'
Set-Location $repoRoot

# ---------- フラグ整理 ----------
if ($Minimal -and ($Force -or $WithSkills)) {
    # Minimal でも Force/Skills は許容するが、GUI extras は強制 OFF
}
$installGui = -not $NoGui -and -not $Minimal

Write-Host "HVE setup (Windows / PowerShell)"
Write-Host "  CheckOnly=$CheckOnly  NoGui=$NoGui  Graphrag=$Graphrag  Minimal=$Minimal  Force=$Force  SkipNltkDownload=$SkipNltkDownload  WithSkills=$WithSkills  NoInstallTools=$NoInstallTools  NoGlobalCleanup=$NoGlobalCleanup  UpgradeSdk=$UpgradeSdk"
Write-Host "  repoRoot=$repoRoot"

# ---------- グローバル Python 環境の遮断 ----------
Write-Step 'Isolating from the global Python environment'
$clearedEnv = Clear-InheritedPythonEnv
if ($clearedEnv.Count -gt 0) {
    Write-Warn2 "Inherited Python/pip environment variables were disabled for this setup process:"
    foreach ($e in $clearedEnv) { Write-Host "    $e" -ForegroundColor DarkGray }
    Write-Host '    Remove them from your user environment as well, otherwise .venv stays contaminated at runtime.'
} else {
    Write-Ok 'No PYTHONPATH / PYTHONHOME / PIP_* leakage from the shell'
}
Write-Ok 'PYTHONNOUSERSITE=1 (user site-packages disabled for every python invocation below)'

# ---------- 必須ツール ----------
Write-Step 'Checking OS tools'

# git / gh は HVE の必須ツール。Node.js / Azure CLI / ShellCheck は
# MCP Server・Azure ワークフロー・ASDW Step 1.2 静的検証で必要になる。
Install-OsTool -Command 'git'        -WingetId 'Git.Git'             -Label 'Git'         -Purpose 'repository operations / git diff'
Install-OsTool -Command 'gh'         -WingetId 'GitHub.cli'          -Label 'GitHub CLI'  -Purpose 'gh auth login / Issue / PR'
Install-OsTool -Command 'node'       -WingetId 'OpenJS.NodeJS.LTS'   -Label 'Node.js LTS' -Purpose 'MCP Server / Work IQ / npx skills'
Install-OsTool -Command 'az'         -WingetId 'Microsoft.AzureCLI'  -Label 'Azure CLI'   -Purpose 'Azure workflows (asdw-* / ADFD)'
Install-OsTool -Command 'shellcheck' -WingetId 'koalaman.shellcheck' -Label 'ShellCheck'  -Purpose 'ASDW Step 1.2 static verification'

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) { Write-Warn2 'git is unavailable. Repository operations and git diff will fail.' }
$gh  = Get-Command gh  -ErrorAction SilentlyContinue
if ($installGui -and -not $gh) {
    if ($CheckOnly) {
        # -CheckOnly は変更を行わない診断モード。通常実行の fail-closed 契約とは分離し、警告のみで続行する。
        Write-Warn2 'GitHub CLI (gh) is unavailable. The GUI "GitHub CLI でログイン" feature will not work. Re-run this setup without -CheckOnly to install it.'
    } else {
        Write-ErrLine 'GitHub CLI (gh) is required for the GUI "GitHub CLI でログイン" feature.'
        Write-Host '    Re-run this setup without -NoInstallTools, or install GitHub CLI and re-run this setup.'
        exit 1
    }
}

$python = Find-Python311
if (-not $python -and -not $NoInstallPython -and -not $CheckOnly) {
    Write-Warn2 "Python 3.11+ not found. Attempting auto-install (Python 3.14)."
    $proceed = $Yes
    if (-not $proceed) {
        $resp = Read-Host "Install Python 3.14 via winget now? UAC elevation may be requested. [y/N]"
        $proceed = ($resp -match '^[Yy]$')
    }
    if ($proceed) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) {
            Write-ErrLine 'winget not found. Install "App Installer" from the Microsoft Store, or install Python manually: https://www.python.org/downloads/'
        } else {
            try {
                # --scope user keeps install user-local and avoids UAC when possible.
                Invoke-Checked -Exe 'winget' -ArgList @('install','--id','Python.Python.3.14','-e','--source','winget','--scope','user','--accept-source-agreements','--accept-package-agreements','--silent')
                # Refresh PATH so newly installed py launcher / python is discoverable in this session.
                $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
                $python = Find-Python311
            } catch {
                Write-Warn2 "winget install failed: $($_.Exception.Message)"
            }
        }
    }
}
if ($python) {
    Write-Ok "Python 3.11+: $($python.Exe) $($python.ExtraArgs -join ' ') ($($python.Version))"
} else {
    Write-ErrLine "Python 3.11+ not found."
    Write-Host "    Install one of:"
    Write-Host "      winget install --id Python.Python.3.14 -e --source winget"
    Write-Host "      https://www.python.org/downloads/  (check 'Add python.exe to PATH')"
    if (-not $CheckOnly) { exit 1 }
}

# ---------- グローバル hve の除去 ----------
Write-Step 'Checking global Python for a stray hve installation'
if ($python) { Remove-GlobalHveInstall -Python $python }

# ---------- venv モジュール ----------
# Windows の CPython は venv/ensurepip を同梱するが、embeddable 版 / Microsoft Store の
# stub / インストーラで pip 機能を外した構成では欠落する。.venv 作成前に検出する。
Write-Step 'Checking Python venv module'
if ($python) {
    $venvProbe = Invoke-Probe -Exe $python.Exe -ArgList ($python.ExtraArgs + @('-c','import venv, ensurepip'))
    if ($venvProbe -eq 0) {
        Write-Ok "venv module available ($($python.Exe) -m venv)"
    } elseif ($CheckOnly) {
        Write-Warn2 'venv module (or ensurepip) is missing. Repair Python: winget install --id Python.Python.3.14 -e --source winget --force'
    } else {
        Write-Warn2 'venv module (or ensurepip) is missing. Attempting repair via winget.'
        $repaired = $false
        if (-not $NoInstallPython) {
            $proceed = $Yes
            if (-not $proceed) {
                $resp = Read-Host 'Reinstall Python 3.14 via winget to restore the venv module? [y/N]'
                $proceed = ($resp -match '^[Yy]$')
            }
            if ($proceed) {
                $winget = Get-Command winget -ErrorAction SilentlyContinue
                if (-not $winget) {
                    Write-ErrLine 'winget not found. Install "App Installer" from the Microsoft Store, or reinstall Python manually: https://www.python.org/downloads/'
                } else {
                    try {
                        Invoke-Checked -Exe 'winget' -ArgList @('install','--id','Python.Python.3.14','-e','--source','winget','--scope','user','--force','--accept-source-agreements','--accept-package-agreements','--silent')
                        $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
                        $python = Find-Python311
                        if ($python) {
                            $repaired = (Invoke-Probe -Exe $python.Exe -ArgList ($python.ExtraArgs + @('-c','import venv, ensurepip'))) -eq 0
                        }
                    } catch {
                        Write-Warn2 "winget repair failed: $($_.Exception.Message)"
                    }
                }
            }
        }
        if ($repaired) {
            Write-Ok 'venv module installed'
        } else {
            Write-ErrLine 'venv module unavailable. Reinstall Python with the "pip" optional feature enabled:'
            Write-Host '      winget install --id Python.Python.3.14 -e --source winget --force'
            Write-Host '      https://www.python.org/downloads/  (do not use the embeddable package)'
            exit 1
        }
    }
}

# ---------- .venv ----------
Write-Step 'Preparing .venv'
if ($Force -and -not $CheckOnly -and (Test-Path $venvDir)) {
    Write-Host "  -Force: removing existing .venv"
    Remove-Item -Recurse -Force $venvDir
}
if (Test-Path $venvPy) {
    $code = Invoke-Probe -Exe $venvPy -ArgList @('-c','import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)')
    if ($code -ne 0) {
        if ($CheckOnly) { Write-Warn2 "Existing .venv is older than Python 3.11. Re-run with -Force to rebuild." }
        else {
            Write-Host "  Existing .venv is older than Python 3.11. Recreating."
            Remove-Item -Recurse -Force $venvDir
        }
    } else {
        Write-Ok ".venv exists and is Python 3.11+"
    }
}
# `python -m venv --system-site-packages` で作られた .venv はグローバルの
# site-packages を継承する。隔離を保証するため作り直す。
$venvCfg = Join-Path $venvDir 'pyvenv.cfg'
if ((Test-Path $venvPy) -and (Test-Path -LiteralPath $venvCfg)) {
    if ((Get-Content -LiteralPath $venvCfg -Raw) -match '(?im)^\s*include-system-site-packages\s*=\s*true\s*$') {
        if ($CheckOnly) {
            Write-Warn2 '.venv inherits global site-packages (include-system-site-packages = true). Re-run with -Force to rebuild it isolated.'
        } else {
            Write-Warn2 '.venv inherits global site-packages (include-system-site-packages = true). Rebuilding it isolated.'
            Remove-Item -Recurse -Force $venvDir
        }
    }
}
if (-not (Test-Path $venvPy) -and -not $CheckOnly) {
    if (-not $python) { throw 'Python 3.11+ is required to create .venv.' }
    Invoke-Checked -Exe $python.Exe -ArgList ($python.ExtraArgs + @('-m','venv',$venvDir))
    Write-Ok ".venv created (isolated: system site-packages excluded)"
}

if ($CheckOnly) {
    if (-not (Test-Path $venvPy)) {
        Write-Warn2 ".venv does not exist. Run without -CheckOnly."
    } elseif ($installGui) {
        Write-Step 'Auditing embedded GitHub CLI terminal prerequisites'
        $ptyProbe = Invoke-Probe -Exe $venvPy -ArgList @(
            '-c',
            'from hve.gui.pty_backend import is_pty_available; raise SystemExit(0 if is_pty_available() else 1)'
        )
        if ($ptyProbe -eq 0) {
            Write-Ok 'PTY backend for the embedded GitHub CLI terminal'
        } else {
            Write-Warn2 'The PTY backend required by the GUI "GitHub CLI でログイン" feature is unavailable. Re-run this setup without -CheckOnly to install it.'
        }
    }
    Write-Host "`nCheck-only completed with $script:WarningCount warning(s)."
    exit 0
}

# ---------- pip / wheel ----------
Write-Step 'Upgrading pip / setuptools / wheel'
Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','--upgrade','pip','setuptools','wheel')

# ---------- editable install + extras ----------
if ($Minimal) {
    Write-Step 'Installing HVE (base only, no extras)'
    if ($Graphrag) { Write-Warn2 '-Graphrag is ignored because -Minimal installs no extras.' }
    if ($CodeLanguages.Trim()) { Write-Warn2 '-CodeLanguages is ignored because -Minimal installs no code-query grammars.' }
    Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','-e','.')
} else {
    $extras = @('test','mdq-watch','mdq-ja','semantic','code-watch','code-tokenizer','code-semantic')
    if ($installGui) { $extras += @('gui','gui-pty','gui-docconvert') }
    if ($Graphrag) { $extras += 'graphrag' }
    $target = ".[" + ($extras -join ',') + "]"
    Write-Step "Installing HVE with extras: [$($extras -join ',')]"
    Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','-e',$target)
    if ($Graphrag) {
        Write-Warn2 'graphrag extras installed. It also needs Ollama running on http://127.0.0.1:11434 with the qwen2.5:7b and nomic-embed-text models: winget install --id Ollama.Ollama --exact, then ollama pull qwen2.5:7b; ollama pull nomic-embed-text'
    }
}

if ($installGui) {
    Write-Step 'Verifying embedded GitHub CLI terminal prerequisites'
    $ptyProbe = Invoke-Probe -Exe $venvPy -ArgList @(
        '-c',
        'from hve.gui.pty_backend import is_pty_available; raise SystemExit(0 if is_pty_available() else 1)'
    )
    if ($ptyProbe -ne 0) {
        Write-ErrLine 'The PTY backend required by the GUI "GitHub CLI でログイン" feature is unavailable.'
        Write-Host '    Re-run this setup after resolving the GUI dependency installation failure.'
        exit 1
    }
    Write-Ok 'PTY backend for the embedded GitHub CLI terminal'
}

# ---------- code-query 用文法 (extras: code / code-<言語>) ----------
# tree-sitter 文法は platform ごとに wheel 有無が異なるため、本体インストールとは
# 分離して警告止まりにする。未導入時は code-query が regex (lite) へ降格するだけ。
# NOTE: code-sql (sqlfluff) は click pin が semantic extras と衝突するため導入しない。
# 利用者が打つ言語名 → pyproject.toml の extras 名。`sql` だけは sqlfluff 用の
# 既存 `code-sql` と衝突するため `code-sqlglot` へ写す。
$CodeLanguageExtras = [ordered]@{
    python     = 'code-python';     csharp     = 'code-csharp'
    javascript = 'code-javascript'; typescript = 'code-typescript'
    java       = 'code-java';       go         = 'code-go'
    rust       = 'code-rust';       c          = 'code-c'
    cpp        = 'code-cpp';        scala      = 'code-scala'
    shell      = 'code-shell';      powershell = 'code-powershell'
    batch      = 'code-batch';      sql        = 'code-sqlglot'
}
if (-not $Minimal) {
    if ($CodeLanguages.Trim()) {
        $requested = @(
            $CodeLanguages.Split(',') |
                ForEach-Object { $_.Trim().ToLowerInvariant() } |
                Where-Object { $_ }
        )
        $unknown = @($requested | Where-Object { -not $CodeLanguageExtras.Contains($_) })
        if ($unknown.Count -gt 0) {
            Write-ErrLine "-CodeLanguages contains unknown languages: $($unknown -join ', ')"
            Write-Host "    Available: $($CodeLanguageExtras.Keys -join ', ')"
            exit 1
        }
        $codeExtras = @($requested | ForEach-Object { $CodeLanguageExtras[$_] } | Select-Object -Unique)
    } else {
        $codeExtras = @('code')
    }
    Write-Step "Installing code-query grammars (extras: $($codeExtras -join ','))"
    try {
        Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','-e',(".[" + ($codeExtras -join ',') + "]"))
        Write-Ok "code-query grammars installed: $($codeExtras -join ',')"
    } catch {
        Write-Warn2 "code extras install failed: $($_.Exception.Message). code-query falls back to regex (lite) parsing."
    }
}

# ---------- github-copilot-sdk ----------
# NOTE: --no-deps を付与し SDK 本体のみ更新する。これを付けないと pip resolver が
#   pydantic-core を最新版 (例: 2.47.0) へ引き上げ、pydantic 2.13.4 が要求する
#   pin (pydantic-core==2.46.4) と不整合になり GUI 起動時に例外となる。
#   SDK の依存 (pydantic>=2.0 等) は editable install 時点で既に充足済み。
# 版は hve\copilot-sdk.lock で固定する。無条件に最新へ追従すると「セットアップ
#   した日」でマシンごとに版が変わり、公開直後のリリースにパーサ不整合があった
#   場合に特定の人だけ壊れて再現・切り分けが不能になるため。
$lockFile = Join-Path $repoRoot 'hve\copilot-sdk.lock'
# NOTE: Python ソース内は単一引用符のみ使用（PowerShell のネイティブコマンド
#       引数渡しで二重引用符が剥がれる問題を回避するため）。
$lockUpdatePy = @'
import re, sys, pathlib
import importlib.metadata as m
import copilot._cli_version as v
p = pathlib.Path(sys.argv[1])
sdk = m.version('github-copilot-sdk')
cli = v.CLI_VERSION or 'unknown'
t = p.read_text(encoding='utf-8')
t = re.sub(r'(?m)^# pinned Copilot CLI runtime:.*$', '# pinned Copilot CLI runtime: ' + cli, t)
t = re.sub(r'(?m)^github-copilot-sdk==.*$', 'github-copilot-sdk==' + sdk, t)
p.write_text(t, encoding='utf-8', newline='\n')
print(sdk)
'@

if ($UpgradeSdk) {
    Write-Step 'Upgrading github-copilot-sdk to latest (no-deps) and refreshing the lock'
    Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','--upgrade','--no-deps','github-copilot-sdk')
    if (-not (Test-Path -LiteralPath $lockFile)) {
        Write-Warn2 "Lock file not found: $lockFile"
    } else {
        $prev = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { $newSdk = (& $venvPy -c $lockUpdatePy $lockFile 2>$null | Select-Object -First 1 | Out-String).Trim() }
        finally { $ErrorActionPreference = $prev }
        if ($newSdk) {
            Write-Ok "hve\copilot-sdk.lock now pins $newSdk. Review the diff and commit it so the whole team moves together."
        } else {
            Write-Warn2 'Could not refresh hve\copilot-sdk.lock. Update it by hand.'
        }
    }
} elseif (Test-Path -LiteralPath $lockFile) {
    Write-Step 'Installing github-copilot-sdk from hve\copilot-sdk.lock (no-deps)'
    Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','--no-deps','-r',$lockFile)
} else {
    Write-Warn2 'hve\copilot-sdk.lock not found. Falling back to the latest release; re-run with -UpgradeSdk to regenerate the lock.'
    Write-Step 'Upgrading github-copilot-sdk to latest (no-deps)'
    Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','--upgrade','--no-deps','github-copilot-sdk')
}

# ---------- 依存整合性チェック（pydantic / pydantic-core 等） ----------
# github-copilot-sdk の --upgrade 時に pip resolver が pydantic-core を
# 最新版 (例: 2.47.0) へ引き上げ、pydantic 本体が要求する pin
# (例: pydantic 2.13.4 → pydantic-core==2.46.4) と不整合になるケースを
# 自動修復する。`pip check` が NG なら pydantic を force-reinstall。
Write-Step 'Verifying dependency consistency (pip check)'
& $venvPy -m pip check *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 'pip check detected inconsistencies. Reinstalling pydantic to re-pin pydantic-core.'
    Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','--upgrade','--force-reinstall','pydantic')
}

# ---------- Copilot ランタイム整合性 ----------
# github-copilot-sdk は wheel ごとに Copilot CLI ランタイム版を pin し
# (copilot/_cli_version.py の CLI_VERSION)、生成イベントパーサ
# (copilot/generated/session_events.py) はその版のスキーマ専用に生成される。
# パーサはイベント "種別" にしか前方互換が無く、エンベロープ (id/timestamp/type) は
# assert で固めてあるため、pin と異なるランタイムを掴むと session.event の解析が
# AssertionError となり当該イベントが黙って捨てられる。終端イベントを取り逃すと
# send_and_wait がタイムアウトまで返らない。
# 「最新化」では防げない (むしろ公開直後の版を掴むリスクを増やす) ため、
# pin 版の先読みと、pin を無効化する環境変数・版不一致の検出をここで行う。
Write-Step 'Verifying Copilot runtime consistency'

foreach ($bypassVar in 'COPILOT_CLI_PATH','COPILOT_CLI_EXTRACT_DIR','COPILOT_SKIP_CLI_DOWNLOAD') {
    $bypassValue = [Environment]::GetEnvironmentVariable($bypassVar)
    if ($bypassValue) {
        Write-Warn2 "$bypassVar is set ($bypassValue). It bypasses the runtime version pinned by github-copilot-sdk and leads to session.event parse failures (AssertionError). Unset it unless you know why."
    }
}

function Get-CopilotCliVersion {
    # `--version` 単体はオンライン更新チェックを走らせ "最新利用可能版" を表示するため
    # pin との突合に使えない。実際に動く埋め込み版を得るには --no-auto-update が必須。
    param([Parameter(Mandatory)][string]$Exe)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $raw = (& $Exe '--no-auto-update' '--version' 2>$null | Select-Object -First 1 | Out-String) }
    catch { return '' }
    finally { $ErrorActionPreference = $prev }
    if ($raw -match '(\d+\.\d+\.\d+(?:-\d+)?)') { return $Matches[1] }
    return ''
}

# NOTE: Python ソース内は単一引用符のみ使用（PowerShell のネイティブコマンド
#       引数渡しで二重引用符が剥がれる問題を回避するため）。
$sdkProbe = @'
import importlib.metadata as m
try:
    print(m.version('github-copilot-sdk'))
except Exception:
    print('')
try:
    import copilot._cli_version as v
    print(v.CLI_VERSION or '')
except Exception:
    print('')
'@
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try { $probeOut = @(& $venvPy -c $sdkProbe 2>$null) } finally { $ErrorActionPreference = $prev }
$sdkVer    = if ($probeOut.Count -ge 1) { "$($probeOut[0])".Trim() } else { '' }
$pinnedCli = if ($probeOut.Count -ge 2) { "$($probeOut[1])".Trim() } else { '' }
$sdkLabel  = if ($sdkVer) { $sdkVer } else { 'unknown' }
$pinLabel  = if ($pinnedCli) { $pinnedCli } else { 'unknown' }
Write-Host "    github-copilot-sdk=$sdkLabel  pinned Copilot CLI=$pinLabel" -ForegroundColor DarkGray

if (-not $pinnedCli) {
    Write-Warn2 'github-copilot-sdk pins no runtime version (development install). Skipping the runtime check.'
} else {
    try {
        Invoke-Checked -Exe $venvPy -ArgList @('-m','copilot','download-runtime')
        Write-Ok "Copilot runtime v$pinnedCli is cached"
    } catch {
        Write-Warn2 "Copilot runtime prefetch failed: $($_.Exception.Message). hve downloads it lazily on first run; re-run this setup once the network is available."
    }
    $cacheProbe = @'
try:
    import copilot._cli_download as d
    print(d.get_cached_cli_path() or '')
except Exception:
    print('')
'@
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $runtimePath = (& $venvPy -c $cacheProbe 2>$null | Select-Object -First 1 | Out-String).Trim() }
    finally { $ErrorActionPreference = $prev }
    if (-not $runtimePath -or -not (Test-Path -LiteralPath $runtimePath)) {
        Write-Warn2 'Copilot runtime binary was not found in the SDK cache.'
    } else {
        $actualCli = Get-CopilotCliVersion -Exe $runtimePath
        if (-not $actualCli) {
            Write-Warn2 "Could not read the runtime version from $runtimePath"
        } elseif ($actualCli -ne $pinnedCli) {
            Write-Warn2 "Copilot runtime mismatch: pinned=$pinnedCli actual=$actualCli ($runtimePath). session.event parse failures are likely."
        } else {
            Write-Ok "Copilot runtime matches the SDK pin (v$pinnedCli)"
        }
    }
}

# ---------- NLTK punkt_tab 事前 DL ----------
if (-not $Minimal -and -not $SkipNltkDownload) {
    Write-Step 'Pre-downloading nltk punkt_tab (semantic_paragraph)'
    # 失敗時の原因を可視化するため quiet=False + 1回リトライ。stderr は表示。
    # NOTE: Python ソース内は単一引用符のみ使用（PowerShell のネイティブコマンド
    #       引数渡しで二重引用符が剥がれる問題を回避するため）。
    $dlScript = @'
import nltk, sys, time
last = None
for i in range(2):
    try:
        if nltk.download('punkt_tab', quiet=False, raise_on_error=True):
            sys.exit(0)
        last = 'nltk.download returned False'
    except Exception as e:
        last = f'{type(e).__name__}: {e}'
        sys.stderr.write(f'[retry {i+1}/2] {last}\n')
        time.sleep(2)
sys.stderr.write(f'[final] {last}\n')
sys.exit(1)
'@
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $venvPy -c $dlScript } finally { $ErrorActionPreference = $prev }
    if ($LASTEXITCODE -eq 0) { Write-Ok 'nltk punkt_tab downloaded' }
    else { Write-Warn2 'nltk punkt_tab download failed (see error above). semantic_paragraph will fallback to regex split until network is available.' }
}

# ---------- Mermaid / KaTeX アセット ----------
if ($installGui) {
    Write-Step 'Downloading Mermaid / KaTeX assets for Markdown preview'
    try {
        Invoke-Checked -Exe $venvPy -ArgList @('-m','hve.gui.markdown_preview.download_assets')
        Write-Ok 'Mermaid / KaTeX assets ready'
    } catch {
        Write-Warn2 "Asset download failed: $($_.Exception.Message). Markdown body will still render; Mermaid/KaTeX disabled."
    }
}

# ---------- GUI 翻訳 .ts -> .qm ----------
if ($installGui) {
    $tsPath = Join-Path $repoRoot 'hve\gui\i18n\hve_gui_en_US.ts'
    $qmPath = Join-Path $repoRoot 'hve\gui\i18n\hve_gui_en_US.qm'
    if (Test-Path $tsPath) {
        $needBuild = -not (Test-Path $qmPath) -or ((Get-Item $tsPath).LastWriteTime -gt (Get-Item $qmPath).LastWriteTime)
        if ($needBuild) {
            Write-Step 'Compiling GUI translations (.ts -> .qm)'
            $lrelease = Join-Path $venvDir 'Scripts\pyside6-lrelease.exe'
            if (-not (Test-Path $lrelease)) {
                $cmd = Get-Command pyside6-lrelease -ErrorAction SilentlyContinue
                if ($cmd) { $lrelease = $cmd.Source }
            }
            if (Test-Path $lrelease) {
                try {
                    Invoke-Checked -Exe $lrelease -ArgList @($tsPath,'-qm',$qmPath)
                    Write-Ok ".qm compiled: $qmPath"
                } catch { Write-Warn2 "pyside6-lrelease failed: $($_.Exception.Message)" }
            } else {
                Write-Warn2 'pyside6-lrelease not found in .venv. GUI will show Japanese fallback even when English is selected.'
            }
        } else { Write-Ok '.qm is up-to-date' }
    }
}

# ---------- GitHub Copilot CLI (外部 copilot コマンド) ----------
# GUI の Copilot チャットパネルは外部 `copilot` コマンドが無いと無効化される
# (hve/gui/copilot_chat_panel.py)。Step 実行自体は SDK 同梱のため本 CLI 不要。
# WARNING: この CLI は SDK の pin とは独立に自己更新する。COPILOT_CLI_PATH /
#   --cli-path でこの CLI を Step 実行に流用すると、上の整合検証で固定した
#   ランタイム版から必ず乖離し session.event 解析エラーの原因になる。
Write-Step 'Checking GitHub Copilot CLI (copilot)'
$copilotHint = 'npm install -g @github/copilot'
$copilot = Get-Command copilot -ErrorAction SilentlyContinue
if ($copilot) {
    Write-Ok "copilot: $($copilot.Source)"
    $copilotVer = Get-CopilotCliVersion -Exe $copilot.Source
    if ($copilotVer) {
        Write-Host "    version: $copilotVer (independent of the SDK pin; do not point COPILOT_CLI_PATH here)" -ForegroundColor DarkGray
    }
    $npmForUpdate = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $NoInstallTools -and $npmForUpdate -and
        (Invoke-Probe -Exe $npmForUpdate.Source -ArgList @('ls','-g','--depth=0','@github/copilot')) -eq 0) {
        try {
            Invoke-Checked -Exe $npmForUpdate.Source -ArgList @('install','-g','@github/copilot@latest')
            Write-Ok "copilot CLI updated to $(Get-CopilotCliVersion -Exe $copilot.Source)"
        } catch {
            Write-Warn2 "copilot CLI update failed: $($_.Exception.Message). Update manually: $copilotHint@latest"
        }
    }
} elseif ($NoInstallTools) {
    Write-Warn2 "copilot not found (GUI Copilot chat panel). Install: $copilotHint"
} else {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        Write-Warn2 "npm not found. Install Node.js, then: $copilotHint"
    } else {
        $proceed = $Yes
        if (-not $proceed) {
            $resp = Read-Host 'Install GitHub Copilot CLI via npm? (enables the GUI Copilot chat panel) [y/N]'
            $proceed = ($resp -match '^[Yy]$')
        }
        if (-not $proceed) {
            Write-Warn2 "copilot skipped. Install later: $copilotHint"
        } else {
            try {
                Invoke-Checked -Exe $npm.Source -ArgList @('install','-g','@github/copilot')
                Update-PathFromRegistry
                $copilot = Get-Command copilot -ErrorAction SilentlyContinue
                if ($copilot) { Write-Ok "copilot installed: $($copilot.Source)" }
                else { Write-Warn2 "copilot installed but not on PATH yet. Open a new terminal and re-run." }
            } catch {
                Write-Warn2 "Copilot CLI install failed: $($_.Exception.Message). Install manually: $copilotHint"
            }
        }
    }
}

# ---------- microsoft/skills (任意) ----------
if ($WithSkills) {
    Write-Step 'Installing microsoft/skills via npx'
    $npx = Get-Command npx -ErrorAction SilentlyContinue
    if (-not $npx) {
        Write-Warn2 'npx not found. Install Node.js 20+ and re-run with -WithSkills.'
    } else {
        try {
            Invoke-Checked -Exe $npx.Source -ArgList @('-y','skills','add','microsoft/skills','--skill','*','--agent','copilot','--yes','--copy')
            Write-Ok 'microsoft/skills installed under .github/skills/azure-skills/'
        } catch { Write-Warn2 "microsoft/skills install failed: $($_.Exception.Message)" }
    }
}

# ---------- 検証 ----------
Write-Step 'Verifying installation'

$checks = @(
    @{ Name='hve --help';     Args=@('-m','hve','--help') },
    @{ Name='cq.watcher import'; Args=@('-c','import cq.watcher') },
    @{ Name='copilot import'; Args=@('-c','import copilot') }
)
if (-not $Minimal) {
    $checks += @{ Name='mdq --help';      Args=@('-m','mdq','--help') }
    $checks += @{ Name='cq --help';       Args=@('-m','cq','--help') }
    $checks += @{ Name='rank_bm25';       Args=@('-c','import rank_bm25') }
    $checks += @{ Name='tiktoken';        Args=@('-c','import tiktoken') }
    $checks += @{ Name='watchdog';        Args=@('-c','import watchdog') }
    $checks += @{ Name='fastembed';       Args=@('-c','import fastembed') }
    $checks += @{ Name='nltk';            Args=@('-c','import nltk') }
    $checks += @{ Name='numpy';           Args=@('-c','import numpy') }
    $checks += @{ Name='tree_sitter';     Args=@('-c','import tree_sitter') }
    $checks += @{ Name='sqlglot';         Args=@('-c','import sqlglot') }
}
if ($installGui) {
    $checks += @{ Name='PySide6';         Args=@('-c','import PySide6') }
    $checks += @{ Name='PySide6.QtWebEngineWidgets'; Args=@('-c','import PySide6.QtWebEngineWidgets') }
    $checks += @{ Name='markdown_it';     Args=@('-c','import markdown_it') }
    $checks += @{ Name='mdit_py_plugins'; Args=@('-c','import mdit_py_plugins') }
    $checks += @{ Name='pygments';        Args=@('-c','import pygments') }
    $checks += @{ Name='markitdown';      Args=@('-c','import markitdown') }
    $checks += @{ Name='pywinpty';        Args=@('-c','import winpty') }
}

foreach ($c in $checks) {
    $code = Invoke-Probe -Exe $venvPy -ArgList $c.Args
    if ($code -eq 0) { Write-Ok $c.Name }
    else { Write-Warn2 "$($c.Name) verification failed" }
}

# ---------- 隔離性の検証 ----------
# .venv がグローバル環境から完全に独立していることを実行時に確認する。
$isolationCode = @'
import importlib, os, site, sys

repo = os.environ.get('HVE_SETUP_REPO_ROOT', '')


def under(path, root):
    if not path or not root:
        return False
    try:
        p = os.path.normcase(os.path.realpath(path))
        r = os.path.normcase(os.path.realpath(root))
    except OSError:
        return False
    return p == r or p.startswith(r + os.sep)


problems = []

if sys.prefix == sys.base_prefix:
    problems.append('not running inside a virtualenv (sys.prefix == sys.base_prefix)')

if site.ENABLE_USER_SITE:
    problems.append('user site-packages is enabled')

leak_roots = [
    os.path.join(sys.base_prefix, 'Lib', 'site-packages'),
    os.path.join(sys.base_prefix, 'lib', 'site-packages'),
    os.path.join(sys.base_prefix, 'lib', 'python%d.%d' % sys.version_info[:2], 'site-packages'),
]
try:
    leak_roots.append(site.getusersitepackages())
except Exception:
    pass

for entry in sys.path:
    for root in leak_roots:
        if under(entry, root):
            problems.append('global site-packages on sys.path: ' + entry)

for var in ('PYTHONPATH', 'PYTHONHOME'):
    if os.environ.get(var):
        problems.append(var + ' is set: ' + os.environ[var])

for name in ('hve', 'cq', 'mdq'):
    try:
        mod = importlib.import_module(name)
    except Exception as exc:
        problems.append('import ' + name + ' failed: ' + type(exc).__name__ + ': ' + str(exc))
        continue
    origin = getattr(mod, '__file__', None) or ''
    if repo and not under(origin, repo):
        problems.append(name + ' resolves outside the repository: ' + origin)

for p in problems:
    sys.stderr.write('    - ' + p + '\n')
sys.exit(1 if problems else 0)
'@
$env:HVE_SETUP_REPO_ROOT = "$repoRoot"
$prev = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try { & $venvPy -c $isolationCode } finally { $ErrorActionPreference = $prev }
if ($LASTEXITCODE -eq 0) {
    Write-Ok 'venv isolation (no global site-packages; hve/cq/mdq resolve inside the repository)'
} else {
    Write-Warn2 'venv isolation check failed (details above).'
}

# PATH 上の `hve` が .venv 以外を指していると、ユーザーが `hve` と打った時に
# グローバル環境の古い実装が起動してしまう。
$venvScripts = Join-Path $venvDir 'Scripts'
$hveOnPath = Get-Command hve -ErrorAction SilentlyContinue
if (-not $hveOnPath) {
    Write-Ok "No 'hve' shim on PATH (use .\hve.cmd from the repository root)"
} elseif ($hveOnPath.Source -and $hveOnPath.Source.StartsWith($venvScripts, [StringComparison]::OrdinalIgnoreCase)) {
    Write-Ok "'hve' on PATH resolves to .venv: $($hveOnPath.Source)"
} else {
    Write-Warn2 "'hve' on PATH resolves OUTSIDE .venv: $($hveOnPath.Source)"
    Write-Host "    Use .\hve.cmd from the repository root, or remove that installation."
}

# FTS5 trigram (ja-jp)
$trigramCode = @'
import sqlite3, sys
c = sqlite3.connect(":memory:")
try:
    c.execute("CREATE VIRTUAL TABLE p USING fts5(x, tokenize='trigram')")
    sys.exit(0)
except Exception:
    sys.exit(1)
'@
if ((Invoke-Probe -Exe $venvPy -ArgList @('-c',$trigramCode)) -eq 0) {
    Write-Ok 'SQLite FTS5 trigram tokenizer (ja-jp)'
} else {
    Write-Warn2 'SQLite < 3.34: FTS5 trigram unavailable. Falls back to unicode61.'
}

# gh auth (情報のみ)
if ($gh) {
    if ((Invoke-Probe -Exe $gh.Source -ArgList @('auth','status')) -eq 0) { Write-Ok 'gh auth status' }
    else { Write-Warn2 "gh not authenticated. Run: gh auth login" }
}

# ---------- まとめ ----------
Write-Step 'Next steps'
Write-Host "  CLI : .\hve.cmd --help          (recommended; always uses .venv)"
if ($installGui) {
    Write-Host "  GUI : .\hve.cmd gui             (recommended; always uses .venv)"
}
Write-Host "  Direct: $venvPy -m hve --help"
Write-Host "  Activate venv: . $venvDir\Scripts\Activate.ps1"
Write-Host "  Do NOT run 'pip install -e .' against the global Python; it shadows .venv on PATH."

Write-Host "`nHVE setup completed with $script:WarningCount warning(s)."
exit 0
