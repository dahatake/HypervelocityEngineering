# ============================================================
# hve/setup-hve.ps1  EHVE 完�EセチE�E��E�アチE�E�E (Windows / PowerShell)
#
# 目皁E
#   OS しか入ってぁE�E��E�ぁE�E��E�リーンな Windows 環墁E�E��E�ら、HVE の CLI と GUI の
#   全機�Eを実行できる .venv をゼロから構築する、E
#
# 既定で導�Eする extras (pyproject.toml [project.optional-dependencies] と一致):
#   - mdq-watch    : rank_bm25, tiktoken, watchdog
#   - mdq-ja       : (現状空。封E�E��E�の形態素解析器拡張用)
#   - semantic     : fastembed, nltk, numpy   (semantic_paragraph 戦略)
#   - gui          : PySide6, markdown-it-py, mdit-py-plugins, Pygments
#   - gui-pty      : pywinpty  (GUI 冁EPTY で copilot/az/gh の対話認証)
#   - gui-docconvert: markitdown[pdf,docx,pptx,xlsx,xls,outlook]
#
# 追加で行うこと:
#   - .venv 作�E / 検証 (Python 3.11+ 忁E�E��E�E
#   - pip / setuptools / wheel をアチE�E�EグレーチE
#   - editable install: pip install -e .
#   - nltk punkt_tab を事前ダウンローチE(semantic 初回ビルド�Eオフライン安定化)
#   - Mermaid / KaTeX アセチE�E��E� DL (Markdown プレビュー)
#   - GUI 翻訳 .ts ↁE.qm コンパイル (pyside6-lrelease)
#   - git / gh / Python の存在確認と winget での導�E手頁E�E��E��E�E
#
# 使ぁE�E��E�:
#   powershell -ExecutionPolicy Bypass -File hve\setup-hve.ps1
#       既宁E 全 extras を導�E (CLI + GUI 完�E構�E)
#   ... -CheckOnly       状態確認�Eみ。変更なぁE
#   ... -NoGui           GUI 系 extras をスキチE�E�E (CLI 専用)
#   ... -Minimal         base のみ (extras なぁE。検証/開発の最小構�E
#   ... -Force           .venv を無条件削除し�E構篁E
#   ... -SkipNltkDownload  nltk punkt_tab の事前 DL をスキチE�E�E
#   ... -WithSkills      microsoft/skills めEnpx で .github/skills/azure-skills/ に導�E
# ============================================================

[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$NoGui,
    [switch]$Minimal,
    [switch]$Force,
    [switch]$SkipNltkDownload,
    [switch]$WithSkills,
    [switch]$Yes,
    [switch]$NoInstallPython
)

$ErrorActionPreference = 'Stop'
$script:WarningCount = 0

# PowerShell 7+ 必須（Windows PowerShell 5.x は非対応）
if ($PSVersionTable.PSVersion.Major -lt 7) {
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
    # ネイチE��ブコマンド�E stderr めEStop ポリシー下でも例外化しなぁE��ぁE��時的に Continue、E
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # 出力�E捨て、終亁E��ード�Eみ取得、E
        $null = & $Exe @ArgList 2>&1
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Find-Python311 {
    # 候補生戁E py launcher (バ�Eジョン別) + python / python3
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
            # `--version` は "Python X.Y.Z" を返す。f-string めE�E��E�用符を避けて堁E�E��E�化、E
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

# ---------- パス解決 ----------
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Resolve-Path (Join-Path $scriptDir '..')
$venvDir   = Join-Path $repoRoot '.venv'
$venvPy    = Join-Path $venvDir 'Scripts\python.exe'
Set-Location $repoRoot

# ---------- フラグ整吁E----------
if ($Minimal -and ($Force -or $WithSkills)) {
    # Minimal でめEForce/Skills は許容するぁEGUI extras は強制 OFF
}
$installGui = -not $NoGui -and -not $Minimal

Write-Host "HVE setup (Windows / PowerShell)"
Write-Host "  CheckOnly=$CheckOnly  NoGui=$NoGui  Minimal=$Minimal  Force=$Force  SkipNltkDownload=$SkipNltkDownload  WithSkills=$WithSkills"
Write-Host "  repoRoot=$repoRoot"

# ---------- 忁E�E��E�チE�Eル ----------
Write-Step 'Checking required OS tools'

$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) { Write-Ok "git: $($git.Source)" }
else {
    Write-Warn2 "git not found. Install: winget install --id Git.Git -e --source winget"
}

$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) { Write-Ok "gh : $($gh.Source)" }
else {
    Write-Warn2 "GitHub CLI (gh) not found. Install: winget install --id GitHub.cli -e --source winget"
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
if (-not (Test-Path $venvPy) -and -not $CheckOnly) {
    if (-not $python) { throw 'Python 3.11+ is required to create .venv.' }
    Invoke-Checked -Exe $python.Exe -ArgList ($python.ExtraArgs + @('-m','venv',$venvDir))
    Write-Ok ".venv created"
}

if ($CheckOnly) {
    if (-not (Test-Path $venvPy)) { Write-Warn2 ".venv does not exist. Run without -CheckOnly." }
    Write-Host "`nCheck-only completed with $script:WarningCount warning(s)."
    exit 0
}

# ---------- pip / wheel ----------
Write-Step 'Upgrading pip / setuptools / wheel'
Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','--upgrade','pip','setuptools','wheel')

# ---------- editable install + extras ----------
if ($Minimal) {
    Write-Step 'Installing HVE (base only, no extras)'
    Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','-e','.')
} else {
    $extras = @('mdq-watch','mdq-ja','semantic')
    if ($installGui) { $extras += @('gui','gui-pty','gui-docconvert') }
    $target = "-e .[" + ($extras -join ',') + "]"
    Write-Step "Installing HVE with extras: [$($extras -join ',')]"
    Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install',$target)
}

# ---------- github-copilot-sdk: 最新へ ----------
# NOTE: --no-deps を付与し SDK 本体のみ更新する。これを付けないと pip resolver が
#   pydantic-core を最新版 (例: 2.47.0) へ引き上げ、pydantic 2.13.4 が要求する
#   pin (pydantic-core==2.46.4) と不整合になり GUI 起動時に例外となる。
#   SDK の依存 (pydantic>=2.0 等) は editable install 時点で既に充足済み。
Write-Step 'Upgrading github-copilot-sdk to latest (no-deps)'
Invoke-Checked -Exe $venvPy -ArgList @('-m','pip','install','--upgrade','--no-deps','github-copilot-sdk')

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

# ---------- Mermaid / KaTeX アセチE�E��E� ----------
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

# ---------- microsoft/skills (任愁E ----------
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
$ok = $true

$checks = @(
    @{ Name='hve --help';     Args=@('-m','hve','--help') },
    @{ Name='copilot import'; Args=@('-c','import copilot') }
)
if (-not $Minimal) {
    $checks += @{ Name='mdq --help';      Args=@('-m','mdq','--help') }
    $checks += @{ Name='rank_bm25';       Args=@('-c','import rank_bm25') }
    $checks += @{ Name='tiktoken';        Args=@('-c','import tiktoken') }
    $checks += @{ Name='watchdog';        Args=@('-c','import watchdog') }
    $checks += @{ Name='fastembed';       Args=@('-c','import fastembed') }
    $checks += @{ Name='nltk';            Args=@('-c','import nltk') }
    $checks += @{ Name='numpy';           Args=@('-c','import numpy') }
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
    else { Write-Warn2 "$($c.Name) verification failed"; $ok = $false }
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

# gh auth (惁E�E��E�のみ)
if ($gh) {
    if ((Invoke-Probe -Exe $gh.Source -ArgList @('auth','status')) -eq 0) { Write-Ok 'gh auth status' }
    else { Write-Warn2 "gh not authenticated. Run: gh auth login" }
}

# ---------- まとめE----------
Write-Step 'Next steps'
Write-Host "  CLI : $venvPy -m hve --help     (or .\hve.cmd --help)"
if ($installGui) {
    Write-Host "  GUI : $venvPy -m hve gui        (or .\hve.cmd gui)"
}
Write-Host "  Activate venv: . $venvDir\Scripts\Activate.ps1"

Write-Host "`nHVE setup completed with $script:WarningCount warning(s)."
exit 0
