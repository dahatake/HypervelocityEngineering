@echo off
REM ============================================================
REM hve\setup-hve.cmd — HVE complete setup (Windows cmd thin wrapper)
REM
REM This batch file is a thin wrapper that simply re-invokes the
REM PowerShell setup (setup-hve.ps1). All real logic lives in the
REM PowerShell script so behavior stays identical across entry
REM points (.cmd vs powershell).
REM
REM Why a thin wrapper:
REM   - cmd cannot reliably emit non-ASCII / format multi-step output.
REM   - The PowerShell script already supports CheckOnly / NoGui /
REM     Minimal / Force / SkipNltkDownload / WithSkills.
REM
REM REQUIREMENT: PowerShell 7+ (pwsh.exe). Legacy Windows PowerShell 5.x is
REM NOT supported (native command argument quoting differs). If pwsh is not
REM installed, this wrapper auto-installs it via winget.
REM
REM Usage (all PowerShell flags are forwarded as-is):
REM   hve\setup-hve.cmd                       # full install (CLI + GUI)
REM   hve\setup-hve.cmd -CheckOnly
REM   hve\setup-hve.cmd -NoGui
REM   hve\setup-hve.cmd -Minimal
REM   hve\setup-hve.cmd -Force
REM   hve\setup-hve.cmd -SkipNltkDownload
REM   hve\setup-hve.cmd -WithSkills
REM   hve\setup-hve.cmd -Yes               (skip confirmation prompts incl. Python auto-install)
REM   hve\setup-hve.cmd -NoInstallPython   (do not auto-install Python via winget)
REM
REM Prerequisites detected by the PowerShell script (with hints):
REM   - git, GitHub CLI (gh), Python 3.11+ (auto-installs latest 3.14 via winget when missing)
REM ============================================================

setlocal
set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%setup-hve.ps1"

if not exist "%PS1%" (
    echo [ERROR] PowerShell setup script not found: %PS1%
    endlocal
    exit /b 1
)

REM PowerShell 7+ (pwsh.exe) is required. Legacy Windows PowerShell 5.x is not supported.
where pwsh >nul 2>&1
if errorlevel 1 (
    echo [INFO] PowerShell 7+ ^(pwsh^) not found. Attempting to install via winget...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] winget not found. Install PowerShell 7+ manually:
        echo           https://aka.ms/install-powershell
        echo         Or install "App Installer" from Microsoft Store to get winget.
        endlocal
        exit /b 1
    )
    winget install --id Microsoft.PowerShell -e --source winget --scope user --accept-source-agreements --accept-package-agreements --silent
    if errorlevel 1 (
        echo [ERROR] winget install of PowerShell 7 failed.
        echo         Manual install: https://aka.ms/install-powershell
        endlocal
        exit /b 1
    )
    REM Refresh PATH so the freshly installed pwsh is discoverable in this session.
    for /f "usebackq tokens=*" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P"
    where pwsh >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] pwsh still not found on PATH after install. Open a new terminal and re-run.
        endlocal
        exit /b 1
    )
)

REM Forward all arguments verbatim. -ExecutionPolicy Bypass is scoped
REM to this process only and does not change machine policy.
pwsh -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"

REM Pause only when double-clicked (no args) so users see the result.
if "%~1"=="" (
    echo.
    pause
)

endlocal & exit /b %RC%
