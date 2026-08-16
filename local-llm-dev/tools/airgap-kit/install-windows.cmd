@echo off
setlocal EnableExtensions DisableDelayedExpansion

for %%I in ("%~dp0.") do set "KIT_ROOT=%%~fI"
set "APPLY="
set "BOOTSTRAP_POWERSHELL="
set "PWSH="
set "POWERSHELL_MSI="
set "MSI_COUNT=0"
set "BOOTSTRAP_EXIT=0"

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="-Apply" (
  set "APPLY=1"
  shift
  goto parse_args
)
if /I "%~1"=="-BootstrapPowerShell" (
  set "BOOTSTRAP_POWERSHELL=1"
  shift
  goto parse_args
)
if /I "%~1"=="--help" goto usage
if /I "%~1"=="-h" goto usage
echo ERROR: unknown argument: %~1 1>&2
exit /b 2

:args_done
call :find_pwsh
if defined PWSH goto pwsh_ready
call :bootstrap_pwsh
set "BOOTSTRAP_EXIT=%ERRORLEVEL%"
if not "%BOOTSTRAP_EXIT%"=="0" exit /b %BOOTSTRAP_EXIT%

:pwsh_ready
if defined APPLY goto run_apply
"%PWSH%" -NoLogo -NoProfile -File "%KIT_ROOT%\Import-OfflineKit.ps1" -Source "%KIT_ROOT%"
exit /b %ERRORLEVEL%

:run_apply
"%PWSH%" -NoLogo -NoProfile -File "%KIT_ROOT%\Import-OfflineKit.ps1" -Source "%KIT_ROOT%" -Apply
exit /b %ERRORLEVEL%

:bootstrap_pwsh
if not defined BOOTSTRAP_POWERSHELL if not defined APPLY exit /b 2
set "POWERSHELL_MSI="
set "MSI_COUNT=0"
for /f "delims=" %%F in ('dir /b /s "%KIT_ROOT%runtime\powershell\*.msi" 2^>nul') do call :record_msi "%%F"
if not "%MSI_COUNT%"=="1" exit /b 3
echo Installing the verified PowerShell 7 x64 MSI from the offline kit...
start "" /wait "%POWERSHELL_MSI%"
if errorlevel 1 exit /b %ERRORLEVEL%
call :find_pwsh
if not defined PWSH exit /b 4
exit /b 0

:record_msi
set /a MSI_COUNT+=1 >nul
set "POWERSHELL_MSI=%~1"
exit /b 0

:find_pwsh
set "PWSH="
for /f "delims=" %%I in ('where pwsh.exe 2^>nul') do if not defined PWSH set "PWSH=%%I"
if not defined PWSH if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "PWSH=%ProgramFiles%\PowerShell\7\pwsh.exe"
exit /b 0

:usage
echo Usage: Install-Windows.cmd [-BootstrapPowerShell] [-Apply]
echo.
echo With no option, the command runs the read-only Import dry-run when pwsh.exe exists.
echo If pwsh.exe is missing, -BootstrapPowerShell explicitly installs the one bundled x64 MSI,
echo then runs the dry-run. -Apply permits the same bootstrap and then applies the verified kit.
exit /b 0
