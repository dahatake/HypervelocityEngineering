@echo off
REM ============================================================
REM hve.cmd - HVE CLI launcher (Windows)
REM
REM Purpose:
REM   Run `python -m hve` with the repository-local .venv Python WITHOUT
REM   activating the venv. Prevents ModuleNotFoundError (PySide6, etc.)
REM   caused by forgetting to activate.
REM
REM Usage:
REM   hve.cmd                       (no args -> GUI mode; falls back to CLI when PySide6 missing)
REM   hve.cmd cli
REM   hve.cmd orchestrate --workflow aad
REM   hve.cmd --help
REM
REM Prerequisite:
REM   The .venv must have been created by hve\setup-hve.cmd or hve\setup-hve.ps1.
REM ============================================================

setlocal
set "SCRIPT_DIR=%~dp0"
set "VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [ERROR] .venv Python not found: %VENV_PY%
    echo         Run one of the following first:
    echo           hve\setup-hve.cmd
    echo           pwsh -NoProfile -ExecutionPolicy Bypass -File hve\setup-hve.ps1
    echo         See: users-guide\hve-cli-getting-started.md
    endlocal
    exit /b 1
)

"%VENV_PY%" -m hve %*
endlocal
exit /b %ERRORLEVEL%
