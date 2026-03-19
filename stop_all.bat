@echo off
setlocal
chcp 65001 >nul

set "POWERSHELL=D:\Apps\PowerShell\7\pwsh.exe"
set "WORKDIR=D:\20251224\AI_Study\OpenAgents"
set "STOP_SCRIPT=%WORKDIR%\tools\stop_openagents.ps1"

if not exist "%POWERSHELL%" set "POWERSHELL=powershell"

echo ========================================
echo   Stop OpenAgents
echo ========================================
echo.

"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%STOP_SCRIPT%"

echo.
echo ========================================
echo   Stop complete
echo ========================================
echo.
pause
