@echo off
REM ============================================================
REM HVE setup script for Windows (cmd / batch) - beginner edition
REM
REM This is a SUBSET of hve\setup-hve.ps1 tailored for first-time
REM Windows users who want to install HVE by double-clicking.
REM
REM Default behavior (no args):
REM   - Detect Python 3.11+
REM   - Create .venv if missing
REM   - pip install --upgrade pip
REM   - pip install --upgrade github-copilot-sdk
REM   - pip install -e ".[mdq-watch,mdq-ja]"   (mdq extras)
REM   - pip install -e ".[gui,gui-docconvert]" (GUI extras - ON by default)
REM   - Verify python -m hve --help
REM
REM Supported options:
REM   --check-only   Report state only. Do not modify environment.
REM   --skip-mdq     Skip mdq extras installation.
REM   --no-gui       Skip GUI extras installation (CLI-only setup).
REM   --help / /?    Show this help.
REM
REM For advanced options (-WithWorkIQ / -InstallExternalCopilotCli /
REM -ForceRecreateVenv / -SkipMdqWatch / FTS5 probe / .qm compile),
REM use hve\setup-hve.ps1 instead.
REM ============================================================

setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

REM Capture script directory BEFORE any shift, since default `shift` shifts %%0 too.
set SCRIPT_DIR=%~dp0

set CHECK_ONLY=0
set SKIP_MDQ=0
set WITH_GUI=1
set WITH_SKILLS=0
set INTERACTIVE_PAUSE=1
set WARN=0
set HAD_ARGS=0

:parse
if "%~1"=="" goto :after_parse
set HAD_ARGS=1
if /i "%~1"=="--check-only" ( set CHECK_ONLY=1 & shift /1 & goto :parse )
if /i "%~1"=="--skip-mdq"   ( set SKIP_MDQ=1   & shift /1 & goto :parse )
if /i "%~1"=="--no-gui"     ( set WITH_GUI=0   & shift /1 & goto :parse )
if /i "%~1"=="--with-skills" ( set WITH_SKILLS=1 & shift /1 & goto :parse )
if /i "%~1"=="--help"       goto :help
if /i "%~1"=="-h"           goto :help
if /i "%~1"=="/?"           goto :help
echo [ERROR] Unknown option: %~1
echo Run "hve\setup-hve.cmd --help" to see supported options.
echo For advanced options, use: powershell -ExecutionPolicy Bypass -File hve\setup-hve.ps1
set INTERACTIVE_PAUSE=0
goto :end_error

:after_parse
REM Q9=C: pause only when invoked with no arguments (double-click case)
if "%HAD_ARGS%"=="1" set INTERACTIVE_PAUSE=0

REM Move to repository root (parent of this script's directory).
REM Use SCRIPT_DIR captured before parse-loop shift.
pushd "%SCRIPT_DIR%." >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to change directory to script location.
    goto :end_error
)
cd .. >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to change directory to repository root.
    goto :end_error
)
echo Working directory: %CD%

echo.
echo ==^> HVE Windows setup ^(cmd^)
echo     check-only : %CHECK_ONLY%
echo     skip-mdq   : %SKIP_MDQ%
echo     with-gui   : %WITH_GUI%
echo.

REM ---- Tool detection: git ----
set GIT_PATH=
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GIT_PATH set GIT_PATH=%%G
if defined GIT_PATH (
    echo Git: !GIT_PATH!
) else (
    echo [WARN] git not found. Install from https://git-scm.com/download/win
    set /a WARN+=1
)

REM ---- Tool detection: gh ----
set GH_PATH=
set GH_AVAILABLE=0
for /f "delims=" %%G in ('where gh 2^>nul') do if not defined GH_PATH set GH_PATH=%%G
if defined GH_PATH (
    echo GitHub CLI: !GH_PATH!
    set GH_AVAILABLE=1
) else (
    echo [WARN] GitHub CLI ^(gh^) not found. Install from https://cli.github.com/
    set /a WARN+=1
)

REM ---- Tool detection: Python 3.11+ (Q8=A: ask Python itself) ----
set PYTHON_CMD=
set PYTHON_ARGS=

call :probe_python "py" "-3.11"
if defined PYTHON_CMD goto :python_found

call :probe_python "python" ""
if defined PYTHON_CMD goto :python_found

call :probe_python "python3" ""
if defined PYTHON_CMD goto :python_found

echo [ERROR] Python 3.11 or newer was not found.
echo         Install from https://www.python.org/downloads/
echo         Make sure to check "Add python.exe to PATH" on the installer.
set /a WARN+=1
if "%CHECK_ONLY%"=="0" goto :end_error
goto :skip_python_setup

:python_found
echo Python: %PYTHON_CMD% %PYTHON_ARGS% ^(3.11+ confirmed^)

REM ---- .venv check / create ----
set VENV_PY=.venv\Scripts\python.exe
if exist "%VENV_PY%" (
    echo Existing .venv detected: %VENV_PY%
    "%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Existing .venv is older than Python 3.11.
        echo        Recreate it manually: rmdir /s /q .venv
        echo        Or use: powershell -File hve\setup-hve.ps1 -ForceRecreateVenv
        set /a WARN+=1
        if "%CHECK_ONLY%"=="0" goto :after_python_block
    )
) else (
    if "%CHECK_ONLY%"=="1" (
        echo [WARN] .venv does not exist. Run without --check-only to create it.
        set /a WARN+=1
        goto :after_python_block
    )
    echo ==^> Creating .venv
    %PYTHON_CMD% %PYTHON_ARGS% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        goto :end_error
    )
)

if "%CHECK_ONLY%"=="0" (
    echo ==^> Installing Python dependencies
    "%VENV_PY%" -m pip install --upgrade pip
    if errorlevel 1 ( echo [WARN] pip upgrade failed. & set /a WARN+=1 )

    "%VENV_PY%" -m pip install --upgrade github-copilot-sdk
    if errorlevel 1 ( echo [WARN] github-copilot-sdk install failed. & set /a WARN+=1 )

    if "%SKIP_MDQ%"=="0" (
        echo ==^> Installing mdq extras ^([mdq-watch,mdq-ja]^)
        "%VENV_PY%" -m pip install -e ".[mdq-watch,mdq-ja]"
        if errorlevel 1 (
            echo [WARN] mdq extras install failed. Skill will fall back to MiniBM25.
            set /a WARN+=1
        )
    ) else (
        echo Skipping mdq extras ^(--skip-mdq^).
    )

    if "%WITH_GUI%"=="1" (
        echo ==^> Installing GUI extras ^([gui,gui-docconvert]^)
        "%VENV_PY%" -m pip install -e ".[gui,gui-docconvert]"
        if errorlevel 1 (
            echo [WARN] GUI extras install failed. GUI Orchestrator will not be available.
            set /a WARN+=1
        )
    ) else (
        echo Skipping GUI extras ^(--no-gui^).
    )
)

REM ---- Verify ----
echo ==^> Verifying HVE runtime
"%VENV_PY%" -c "import copilot" >nul 2>&1
if errorlevel 1 (
    echo [WARN] github-copilot-sdk import failed.
    set /a WARN+=1
) else (
    echo github-copilot-sdk import: OK
)

"%VENV_PY%" -m hve --help >nul 2>&1
if errorlevel 1 (
    echo [WARN] "python -m hve --help" failed.
    set /a WARN+=1
) else (
    echo python -m hve --help: OK
)

if "%SKIP_MDQ%"=="0" (
    "%VENV_PY%" -m mdq --help >nul 2>&1
    if errorlevel 1 (
        echo [WARN] "python -m mdq --help" failed.
        set /a WARN+=1
    ) else (
        echo python -m mdq --help: OK
    )
)

:after_python_block
:skip_python_setup

REM ---- gh auth status ----
if "%GH_AVAILABLE%"=="1" (
    echo ==^> Checking GitHub authentication
    gh auth status >nul 2>&1
    if errorlevel 1 (
        echo [WARN] gh auth status failed. Run "gh auth login" before using GitHub features.
        set /a WARN+=1
    ) else (
        echo gh auth status: OK
    )
)

REM ---- Install externally-sourced agent skills via npx ----
if "%WITH_SKILLS%"=="1" if "%CHECK_ONLY%"=="0" (
    echo ==^> Installing externally-sourced agent skills ^(microsoft/skills^)
    where npx >nul 2>&1
    if errorlevel 1 (
        echo [WARN] npx not found. Install Node.js 20+ first, then re-run:
        echo        npx skills add microsoft/skills --skill * --agent copilot --yes --copy
        set /a WARN+=1
    ) else (
        call npx -y skills add microsoft/skills --skill "*" --agent copilot --yes --copy
        if errorlevel 1 (
            echo [WARN] microsoft/skills install failed. Re-run later.
            set /a WARN+=1
        ) else (
            echo microsoft\skills installed under .github\skills\azure-skills\ ^(gitignored^).
        )
    )
)

echo.
echo ==^> Next steps (IMPORTANT)
if exist "%VENV_PY%" (
    echo   このウィンドウで続けて実行する場合は、まず venv を有効化してください:
    echo       .venv\Scripts\activate.bat
    echo       python -m hve --help
    echo.
    echo   activate せずに直接実行する場合 ^(推奨: 同梱ランチャー^):
    echo       hve.cmd --help                      ^(リポジトリ直下のラッパー^)
    echo       .venv\Scripts\python.exe -m hve --help
    echo.
    echo   ※ 素の `python -m hve` ^(activate なし^) はシステム Python を呼び出すため、
    echo      PySide6 等の依存が見つからず失敗します。
    if "%WITH_GUI%"=="1" echo   GUI launch    : hve-gui.bat ^(double-click^)
) else (
    echo   .venv was not created. Re-run without --check-only.
)
echo.
if "%CHECK_ONLY%"=="1" (
    echo Check-only completed with !WARN! warning^(s^).
) else (
    echo HVE setup completed with !WARN! warning^(s^).
)
echo.
echo For advanced options ^(Work IQ / external Copilot CLI / venv recreation^),
echo use: powershell -ExecutionPolicy Bypass -File hve\setup-hve.ps1

popd >nul 2>&1
if "%INTERACTIVE_PAUSE%"=="1" pause
endlocal
exit /b 0

:end_error
popd >nul 2>&1
if "%INTERACTIVE_PAUSE%"=="1" pause
endlocal
exit /b 1

:help
echo.
echo HVE Windows setup script ^(cmd^)
echo.
echo Usage:
echo   hve\setup-hve.cmd                Default: install venv + SDK + mdq + GUI extras
echo   hve\setup-hve.cmd --check-only   Report state only ^(no changes^)
echo   hve\setup-hve.cmd --skip-mdq     Skip mdq extras installation
echo   hve\setup-hve.cmd --no-gui       Skip GUI extras installation
echo   hve\setup-hve.cmd --with-skills  Install externally-sourced agent skills ^(microsoft/skills^) via npx
echo   hve\setup-hve.cmd --help         Show this help
echo.
echo Differences from setup-hve.ps1:
echo   - .cmd installs GUI extras by default ^(setup-hve.ps1 requires -WithGui^).
echo   - .cmd does NOT support: -WithWorkIQ, -InstallExternalCopilotCli,
echo     -ForceRecreateVenv, -SkipMdqWatch, FTS5 trigram probe, .qm compile.
echo     For those, use: powershell -ExecutionPolicy Bypass -File hve\setup-hve.ps1
echo.
set INTERACTIVE_PAUSE=0
popd >nul 2>&1
endlocal
exit /b 0

REM ============================================================
REM Subroutine: probe Python interpreter and verify >= 3.11
REM   %~1 = executable name
REM   %~2 = optional args (e.g. "-3.11" for py launcher)
REM Sets PYTHON_CMD / PYTHON_ARGS on success.
REM ============================================================
:probe_python
where %~1 >nul 2>&1
if errorlevel 1 exit /b 1
%~1 %~2 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
set PYTHON_CMD=%~1
set PYTHON_ARGS=%~2
exit /b 0
