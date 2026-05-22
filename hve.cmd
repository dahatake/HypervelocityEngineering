@echo off
REM ============================================================
REM hve.cmd ? HVE CLI �����`���[ (Windows)
REM
REM �ړI:
REM   .venv �� activate �����ɁA���|�W�g�������� .venv �� Python ��
REM   `python -m hve` �����s���锖�����b�p�[�B
REM   activate �Y��ɂ�� ModuleNotFoundError (PySide6 ��) ��h���B
REM
REM �g����:
REM   hve.cmd                       (�����Ȃ� �� GUI ���� / PySide6 ���������� CLI �t�H�[���o�b�N)
REM   hve.cmd cli
REM   hve.cmd orchestrate --workflow aad
REM   hve.cmd --help
REM
REM �O��:
REM   hve\setup-hve.cmd �܂��� hve\setup-hve.ps1 �� .venv ���쐬�ς݂ł��邱�ƁB
REM ============================================================

setlocal
set SCRIPT_DIR=%~dp0
set VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe

if not exist "%VENV_PY%" (
    echo [ERROR] .venv ��������܂���: %VENV_PY%
    echo         ��Ɏ��̂����ꂩ�����s���Ă�������:
    echo           hve\setup-hve.cmd
    echo           powershell -ExecutionPolicy Bypass -File hve\setup-hve.ps1
    endlocal
    exit /b 1
)

"%VENV_PY%" -m hve %*
endlocal
exit /b %ERRORLEVEL%
