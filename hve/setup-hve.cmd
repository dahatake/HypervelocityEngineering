@echo off
REM ============================================================
REM HVE setup script for Windows (cmd / batch) - beginner edition
REM
REM IMPORTANT: All user-visible messages are in ASCII English.
REM Japanese text in `echo` statements breaks the cmd parser on
REM Japanese Windows (default code page 932) even with chcp 65001,
REM because the batch parser reads the script in the ANSI code page
REM BEFORE chcp takes effect for output.
REM
REM Default behavior (no args):
REM   - Detect Python 3.11+ (supports 3.11 / 3.12 / 3.13 / 3.14)
REM   - Create .venv if missing, or recreate if older than 3.11
REM   - pip install --upgrade pip
REM   - pip install --upgrade github-copilot-sdk
REM   - pip install -e ".[mdq-watch,mdq-ja]"
REM   - pip install -e ".[gui,gui-docconvert]"
REM   - Verify python -m hve --help
REM
REM Supported options:
REM   --check-only   Report state only. Do not modify environment.
REM   --skip-mdq     Skip mdq extras installation.
REM   --no-gui       Skip GUI extras installation (CLI-only setup).
REM   --no-recreate  Do not auto-recreate an outdated .venv.
REM   --help / /?    Show this help.
REM ============================================================

setlocal EnableDelayedExpansion

REM Capture script directory BEFORE any shift.
set SCRIPT_DIR=%~dp0

set CHECK_ONLY=0
set SKIP_MDQ=0
set WITH_GUI=1
set WITH_SKILLS=0
set NO_RECREATE=0
set INTERACTIVE_PAUSE=1
set WARN=0
set HAD_ARGS=0

:parse
if "%~1"=="" goto :after_parse
set HAD_ARGS=1
if /i "%~1"=="--check-only"  ( set "CHECK_ONLY=1" & shift /1 & goto :parse )
if /i "%~1"=="--skip-mdq"    ( set "SKIP_MDQ=1" & shift /1 & goto :parse )
if /i "%~1"=="--no-gui"      ( set "WITH_GUI=0" & shift /1 & goto :parse )
if /i "%~1"=="--with-skills" ( set "WITH_SKILLS=1" & shift /1 & goto :parse )
if /i "%~1"=="--no-recreate" ( set "NO_RECREATE=1" & shift /1 & goto :parse )
if /i "%~1"=="--help"        goto :help
if /i "%~1"=="-h"            goto :help
if /i "%~1"=="/?"            goto :help
echo [ERROR] Unknown option: %~1
echo Run "hve\setup-hve.cmd --help" to see supported options.
set INTERACTIVE_PAUSE=0
goto :end_error

:after_parse
REM Pause only when double-clicked (no args).
if "%HAD_ARGS%"=="1" set INTERACTIVE_PAUSE=0

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
echo     check-only  : %CHECK_ONLY%
echo     skip-mdq    : %SKIP_MDQ%
echo     with-gui    : %WITH_GUI%
echo     no-recreate : %NO_RECREATE%
echo.

REM ---- Tool detection: git ----
set GIT_PATH=
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GIT_PATH set GIT_PATH=%%G
if defined GIT_PATH (
    echo Git: !GIT_PATH!
) else (
    echo [WARN] git not found. Install on a clean Windows OS:
    echo        winget install Git.Git    or    https://git-scm.com/download/win
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
    echo [WARN] GitHub CLI ^(gh^) not found. Install on a clean Windows OS:
    echo        winget install GitHub.cli    or    https://cli.github.com/
    set /a WARN+=1
)

REM ---- Tool detection: Python 3.11+ ----
REM Probe order: py -3 (launcher latest), py -3.14, -3.13, -3.12, -3.11,
REM then bare python / python3 from PATH.
REM Each candidate must (a) be on PATH, (b) NOT be the Microsoft Store stub,
REM and (c) report a version >= 3.11 via -c "print(...)" (version string must
REM be non-empty). This avoids false positives from py.exe with no installed
REM runtime, and from python.exe stub that exits 0 silently.
set "PYTHON_CMD="
set "PYTHON_ARGS="
set "PY_VERSION="

call :probe_python "py" "-3"
if defined PYTHON_CMD goto :python_found
call :probe_python "py" "-3.14"
if defined PYTHON_CMD goto :python_found
call :probe_python "py" "-3.13"
if defined PYTHON_CMD goto :python_found
call :probe_python "py" "-3.12"
if defined PYTHON_CMD goto :python_found
call :probe_python "py" "-3.11"
if defined PYTHON_CMD goto :python_found
call :probe_python "python" ""
if defined PYTHON_CMD goto :python_found
call :probe_python "python3" ""
if defined PYTHON_CMD goto :python_found

echo.
echo [ERROR] Python 3.11 or newer was not found on PATH.
echo         Tried: py -3 / py -3.14 / py -3.13 / py -3.12 / py -3.11 / python / python3
echo.
echo         Install one of these on a clean Windows OS:
echo           - winget install Python.Python.3.13         (recommended, Windows 10/11)
echo           - https://www.python.org/downloads/         (official installer)
echo         Make sure to check "Add python.exe to PATH" on the installer.
echo         If you only have py launcher with old Python, install 3.11+.
set /a WARN+=1
if "%CHECK_ONLY%"=="0" goto :end_error
goto :skip_python_setup

:python_found
REM Defensive: probe may set PYTHON_CMD as defined-but-empty in edge cases.
if not defined PYTHON_CMD goto :python_missing
if "%PYTHON_CMD%"=="" goto :python_missing
if "%PY_VERSION%"=="" goto :python_missing
echo Python: %PYTHON_CMD% %PYTHON_ARGS% ^(version %PY_VERSION%^)
goto :after_python_detect

:python_missing
echo [ERROR] Python probe returned empty interpreter. Aborting.
set /a WARN+=1
if "%CHECK_ONLY%"=="0" goto :end_error
goto :skip_python_setup

:after_python_detect

REM ---- .venv check / create / recreate ----
set VENV_PY=.venv\Scripts\python.exe
set NEED_CREATE=0
set NEED_RECREATE=0

if exist "%VENV_PY%" (
    echo Existing .venv detected: %VENV_PY%
    "%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
    if errorlevel 1 (
        if "%NO_RECREATE%"=="1" (
            echo [WARN] Existing .venv is older than Python 3.11. --no-recreate set; skipping.
            set /a WARN+=1
        ) else (
            echo [INFO] Existing .venv is older than Python 3.11. Recreating automatically.
            set NEED_RECREATE=1
        )
    )
) else (
    set NEED_CREATE=1
)

if "%CHECK_ONLY%"=="1" (
    if "%NEED_CREATE%"=="1" (
        echo [WARN] .venv does not exist. Run without --check-only to create it.
        set /a WARN+=1
    )
    if "%NEED_RECREATE%"=="1" (
        echo [WARN] .venv would be recreated. Run without --check-only to apply.
        set /a WARN+=1
    )
    goto :after_python_block
)

if "%NEED_RECREATE%"=="1" (
    echo ==^> Removing outdated .venv
    rmdir /s /q .venv
    if errorlevel 1 (
        echo [ERROR] Failed to remove existing .venv. Close any process using it and retry.
        goto :end_error
    )
    set NEED_CREATE=1
)

if "%NEED_CREATE%"=="1" (
    echo ==^> Creating .venv with %PYTHON_CMD% %PYTHON_ARGS%
    %PYTHON_CMD% %PYTHON_ARGS% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        goto :end_error
    )
)

echo ==^> Upgrading pip / setuptools / wheel
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 ^( echo [WARN] pip/setuptools/wheel upgrade failed. & set /a WARN+=1 ^)

echo ==^> Installing github-copilot-sdk
"%VENV_PY%" -m pip install --upgrade github-copilot-sdk
if errorlevel 1 ^( echo [WARN] github-copilot-sdk install failed. & set /a WARN+=1 ^)

echo ==^> Installing HVE package ^(editable^)
"%VENV_PY%" -m pip install -e .
if errorlevel 1 (
    echo [ERROR] Editable install of HVE package failed.
    set /a WARN+=1
    goto :after_install
)

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
    ) else (
        echo ==^> Downloading Mermaid / KaTeX assets for Markdown preview
        "%VENV_PY%" -m hve.gui.markdown_preview.download_assets
        if errorlevel 1 ^( echo [WARN] Asset download had failures. Markdown body will still render; Mermaid/KaTeX will be disabled. & set /a WARN+=1 ^)
    )
) else (
    echo Skipping GUI extras ^(--no-gui^).
)

:after_install
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

REM ---- Optional: external agent skills via npx ----
if "%WITH_SKILLS%"=="1" if "%CHECK_ONLY%"=="0" (
    echo ==^> Installing externally-sourced agent skills ^(microsoft/skills^)
    where npx >nul 2>&1
    if errorlevel 1 (
        echo [WARN] npx not found. Install Node.js 20+ and re-run:
        echo        npx skills add microsoft/skills --skill * --agent copilot --yes --copy
        set /a WARN+=1
    ) else (
        call npx -y skills add microsoft/skills --skill "*" --agent copilot --yes --copy
        if errorlevel 1 (
            echo [WARN] microsoft/skills install failed. Re-run later.
            set /a WARN+=1
        )
    )
)

echo.
echo ==^> Next steps
if exist "%VENV_PY%" (
    echo   To use this venv in the current shell, activate it first:
    echo       .venv\Scripts\activate.bat
    echo       python -m hve --help
    echo.
    echo   Or use the bundled launcher ^(no activation needed^):
    echo       hve.cmd --help
    echo       .venv\Scripts\python.exe -m hve --help
    echo.
    echo   NOTE: Plain "python -m hve" ^(without activation^) calls the system
    echo         Python and will fail to find PySide6 / other dependencies.
    if "%WITH_GUI%"=="1" echo   GUI launch: hve-gui.bat ^(double-click^)
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
echo For advanced options ^(Work IQ / external Copilot CLI / venv recreation flags^),
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
echo   hve\setup-hve.cmd --no-recreate  Keep existing .venv even if outdated
echo   hve\setup-hve.cmd --with-skills  Install externally-sourced agent skills via npx
echo   hve\setup-hve.cmd --help         Show this help
echo.
echo Supported Python: 3.11 / 3.12 / 3.13 / 3.14
echo.
echo For advanced options ^(-WithWorkIQ, -InstallExternalCopilotCli,
echo -ForceRecreateVenv, FTS5 trigram probe, .qm compile^), use:
echo   powershell -ExecutionPolicy Bypass -File hve\setup-hve.ps1
echo.
set INTERACTIVE_PAUSE=0
popd >nul 2>&1
endlocal
exit /b 0

REM ============================================================
REM Subroutine: probe Python interpreter and verify >= 3.11.
REM   %~1 = executable name (py / python / python3)
REM   %~2 = optional args  (e.g. "-3", "-3.14")
REM On success: sets PYTHON_CMD / PYTHON_ARGS / PY_VERSION (X.Y.Z).
REM Failure modes (silent, exit /b 1):
REM   - command not on PATH
REM   - command runs but returns version < 3.11 or no version string
REM     (this naturally rejects the Microsoft Store stub python.exe,
REM      which exits non-zero with no stdout when invoked with -c)
REM ============================================================
:probe_python
setlocal
set "_CMD=%~1"
set "_ARGS=%~2"
set "_VER="

REM (a) PATH check. NOTE: do NOT reject WindowsApps paths blindly --
REM Store-installed real Python (e.g. 3.14) also lives under WindowsApps.
REM The version-string check in (b) is enough to filter out the stub.
where %_CMD% >nul 2>&1
if errorlevel 1 ( endlocal & exit /b 1 )

REM (b) Run interpreter and capture version string. Empty output = fail.
for /f "delims=" %%V in ('%_CMD% %_ARGS% -c "import sys;v=sys.version_info;print('{}.{}.{}'.format(v[0],v[1],v[2])) if v>=(3,11) else None" 2^>nul') do set "_VER=%%V"
if not defined _VER ( endlocal & exit /b 1 )
if "%_VER%"=="" ( endlocal & exit /b 1 )
if "%_VER%"=="None" ( endlocal & exit /b 1 )

REM (c) Success: propagate to parent scope.
endlocal & set "PYTHON_CMD=%~1" & set "PYTHON_ARGS=%~2" & set "PY_VERSION=%_VER%"
exit /b 0
