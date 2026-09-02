@echo off
REM clear-python-catch.cmd
REM Wrapper for clear-python-catch.ps1 (Windows cmd.exe).
REM Usage:
REM   tools\hve-app-cash\clear-python-catch.cmd
REM   tools\hve-app-cash\clear-python-catch.cmd -DryRun

setlocal
set "SCRIPT_DIR=%~dp0"
where pwsh >nul 2>&1
if %ERRORLEVEL%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%clear-python-catch.ps1" %*
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%clear-python-catch.ps1" %*
)
endlocal
exit /b %ERRORLEVEL%
