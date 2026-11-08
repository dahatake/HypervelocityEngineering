@echo off
rem Double-click to start EABK Studio (Windows). Repo = the folder containing this file.
setlocal
set "HERE=%~dp0"
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (where py >nul 2>nul && set "PY=py")
if not defined PY (
  echo Python 3 is required. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)
"%PY%" "%HERE%EABK-Studio\studio.py" --repo "%HERE%." --port 8765 %*
if errorlevel 1 pause
endlocal
