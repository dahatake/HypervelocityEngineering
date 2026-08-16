@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "DESTINATION="
set "MODEL=qwen3:8b"
set "CONTEXT_LENGTH=8192"
set "PWSH="
set "PY_MANAGER="
set "OLLAMA="
set "WAIT_COUNT=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--destination" goto parse_destination
if /I "%~1"=="--model" goto parse_model
if /I "%~1"=="--context-length" goto parse_context
if /I "%~1"=="--help" goto usage
if /I "%~1"=="-h" goto usage
echo ERROR: unknown argument: %~1 1>&2
exit /b 2

:parse_destination
if "%~2"=="" goto missing_destination
set "DESTINATION=%~2"
shift
shift
goto parse_args

:parse_model
if "%~2"=="" goto missing_model
set "MODEL=%~2"
shift
shift
goto parse_args

:parse_context
if "%~2"=="" goto missing_context
set "CONTEXT_LENGTH=%~2"
shift
shift
goto parse_args

:args_done
if not defined DESTINATION goto missing_destination
for /f "delims=0123456789" %%I in ("%CONTEXT_LENGTH%") do goto invalid_context

where winget.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: winget.exe is required. Use Windows 11 with App Installer enabled. 1>&2
  exit /b 1
)

call :find_pwsh
if not defined PWSH (
  echo Installing PowerShell 7 x64 MSI...
  winget install --id Microsoft.PowerShell --exact --source winget --architecture x64 --installer-type wix --accept-package-agreements --accept-source-agreements --disable-interactivity
  if errorlevel 1 exit /b 1
  call :find_pwsh
)
if not defined PWSH (
  echo ERROR: pwsh.exe was not found after installation. 1>&2
  exit /b 1
)

call :find_py_manager
if not defined PY_MANAGER (
  echo Installing Python Install Manager...
  winget install --id 9NQ7512CXL7T --exact --source msstore --architecture x64 --accept-package-agreements --accept-source-agreements --disable-interactivity
  if errorlevel 1 exit /b 1
  call :find_py_manager
)
if not defined PY_MANAGER (
  echo ERROR: pymanager.exe was not found after Python Install Manager installation. 1>&2
  exit /b 1
)

echo Installing the preparation-machine Python 3.14 x64 runtime...
"%PY_MANAGER%" install 3.14-64
if errorlevel 1 exit /b 1

call :find_ollama
if not defined OLLAMA (
  echo Installing Ollama...
  winget install --id Ollama.Ollama --exact --source winget --architecture x64 --accept-package-agreements --accept-source-agreements --disable-interactivity
  if errorlevel 1 exit /b 1
  call :find_ollama
)
if not defined OLLAMA (
  echo ERROR: ollama.exe was not found after installation. 1>&2
  exit /b 1
)

set "OLLAMA_CONTEXT_LENGTH=%CONTEXT_LENGTH%"
curl.exe --fail --silent --max-time 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 start "Ollama preparation server" /b "%OLLAMA%" serve >"%TEMP%\local-llm-dev-ollama-serve.log" 2>&1

:wait_for_ollama
curl.exe --fail --silent --max-time 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if not errorlevel 1 goto ollama_ready
set /a WAIT_COUNT+=1 >nul
if %WAIT_COUNT% GEQ 60 (
  echo ERROR: Ollama loopback did not become ready after 60 retry attempts. 1>&2
  exit /b 1
)
ping.exe -n 2 127.0.0.1 >nul
goto wait_for_ollama

:ollama_ready
echo Pulling required model %MODEL%...
"%OLLAMA%" pull "%MODEL%"
if errorlevel 1 exit /b 1

echo Creating the offline kit...
"%PWSH%" -NoLogo -NoProfile -File "%SCRIPT_DIR%Export-OfflineKit.ps1" -Destination "%DESTINATION%" -Model "%MODEL%" -ContextLength "%CONTEXT_LENGTH%"
exit /b %ERRORLEVEL%

:find_pwsh
for /f "delims=" %%I in ('where pwsh.exe 2^>nul') do if not defined PWSH set "PWSH=%%I"
if not defined PWSH if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "PWSH=%ProgramFiles%\PowerShell\7\pwsh.exe"
exit /b 0

:find_py_manager
for /f "delims=" %%I in ('where pymanager.exe 2^>nul') do if not defined PY_MANAGER set "PY_MANAGER=%%I"
if not defined PY_MANAGER if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\pymanager.exe" set "PY_MANAGER=%LOCALAPPDATA%\Microsoft\WindowsApps\pymanager.exe"
if not defined PY_MANAGER for /d %%D in ("%LOCALAPPDATA%\Microsoft\WindowsApps\PythonSoftwareFoundation.PythonManager_*") do if exist "%%D\pymanager.exe" set "PY_MANAGER=%%D\pymanager.exe"
exit /b 0

:find_ollama
for /f "delims=" %%I in ('where ollama.exe 2^>nul') do if not defined OLLAMA set "OLLAMA=%%I"
if not defined OLLAMA if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
exit /b 0

:missing_destination
echo ERROR: --destination PATH is required. 1>&2
exit /b 2

:missing_model
echo ERROR: --model requires a non-empty value. 1>&2
exit /b 2

:missing_context
echo ERROR: --context-length requires a value. 1>&2
exit /b 2

:invalid_context
echo ERROR: --context-length must contain decimal digits only. 1>&2
exit /b 2

:usage
echo Usage: Prepare-Windows.cmd --destination PATH [--model NAME] [--context-length TOKENS]
echo Default model: qwen3:8b
echo Default context length: 8192
exit /b 0
