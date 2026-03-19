@echo off
setlocal
chcp 65001 >nul

set "PYTHON=C:\Users\86173\AppData\Local\Programs\Python\Python311\python.exe"
set "WORKDIR=D:\20251224\AI_Study\OpenAgents"
set "HEALTH_CHECK=%WORKDIR%\tools\check_openagents_health.py"
set "STOP_SCRIPT=%WORKDIR%\tools\stop_openagents.ps1"
set "POWERSHELL=D:\Apps\PowerShell\7\pwsh.exe"
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "ALL_PROXY="
set "all_proxy="
set "NO_PROXY=localhost,127.0.0.1"
set "no_proxy=localhost,127.0.0.1"

echo ========================================
echo   OpenAgents startup
echo ========================================
echo.

if not exist "%POWERSHELL%" set "POWERSHELL=powershell"

echo [0/5] Stop stale OpenAgents processes...
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%STOP_SCRIPT%" -Quiet >nul 2>nul
timeout /t 2 /nobreak >nul

echo [1/5] Start fresh Network...
start "OpenAgents-Network" /D "%WORKDIR%" "%PYTHON%" -c "from openagents.cli import app; app(['network', 'start'])"
echo       Waiting for Network health...
for /L %%i in (1,1,25) do (
    timeout /t 1 /nobreak >nul
    "%PYTHON%" "%HEALTH_CHECK%" >nul 2>nul
    if not errorlevel 1 goto network_ready
)
echo [ERROR] Network did not become healthy in time.
pause
exit /b 1

:network_ready
echo [2/5] Start travel_router...
start "Agent-travel_router" /D "%WORKDIR%" "%PYTHON%" -c "from openagents.cli import app; app(['agent', 'start', 'agents/travel_router.yaml', '--network-host', 'localhost', '--network-port', '8700'])"
timeout /t 3 /nobreak >nul

echo [3/5] Start weather_agent...
start "Agent-weather_agent" /D "%WORKDIR%" "%PYTHON%" -c "from openagents.cli import app; app(['agent', 'start', 'agents/weather_agent.yaml', '--network-host', 'localhost', '--network-port', '8700'])"
timeout /t 3 /nobreak >nul

echo [4/5] Start spot_agent...
start "Agent-spot_agent" /D "%WORKDIR%" "%PYTHON%" -c "from openagents.cli import app; app(['agent', 'start', 'agents/spot_agent.yaml', '--network-host', 'localhost', '--network-port', '8700'])"
timeout /t 3 /nobreak >nul

echo [5/5] Start plan_agent...
start "Agent-plan_agent" /D "%WORKDIR%" "%PYTHON%" -c "from openagents.cli import app; app(['agent', 'start', 'agents/plan_agent.yaml', '--network-host', 'localhost', '--network-port', '8700'])"
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   Startup complete
echo   Studio: http://localhost:8700/studio/messaging
echo ========================================
echo.
pause
start http://localhost:8700/studio/messaging
