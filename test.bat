@echo off
REM Run Phone Locator tests without changing PowerShell execution policy.
REM Usage:
REM   test.bat
REM   test.bat integration
REM   test.bat android

setlocal
set "REPO_ROOT=%~dp0"
set "SCRIPT=%REPO_ROOT%scripts\test.ps1"

if /i "%~1"=="integration" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Integration
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="android" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Android
    exit /b %ERRORLEVEL%
)

if not "%~1"=="" (
    echo Unknown option: %~1
    echo Usage: test.bat [integration^|android]
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
exit /b %ERRORLEVEL%
