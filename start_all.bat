@echo off
chcp 65001 >nul
title OpenAgents - 一键启动
echo ========================================
echo   OpenAgents 一键部署脚本
echo ========================================
echo.

set PYTHON=C:\Users\86173\AppData\Local\Programs\Python\Python311\python.exe
set WORKDIR=d:\20251224\AI_Study\OpenAgents


echo [1/5] 启动 Network 服务器...
start "OpenAgents-Network" /D "%WORKDIR%" %PYTHON% -c "from openagents.cli import app; app(['network', 'start'])"
echo       等待 Network 就绪...
timeout /t 6 /nobreak >nul

echo [2/5] 启动 travel_router Agent...
start "Agent-travel_router" /D "%WORKDIR%" %PYTHON% -c "from openagents.cli import app; app(['agent', 'start', 'agents/travel_router.yaml'])"
timeout /t 3 /nobreak >nul

echo [3/5] 启动 weather_agent Agent...
start "Agent-weather_agent" /D "%WORKDIR%" %PYTHON% -c "from openagents.cli import app; app(['agent', 'start', 'agents/weather_agent.yaml'])"
timeout /t 3 /nobreak >nul

echo [4/5] 启动 spot_agent Agent...
start "Agent-spot_agent" /D "%WORKDIR%" %PYTHON% -c "from openagents.cli import app; app(['agent', 'start', 'agents/spot_agent.yaml'])"
timeout /t 3 /nobreak >nul

echo [5/5] 启动 plan_agent Agent...
start "Agent-plan_agent" /D "%WORKDIR%" %PYTHON% -c "from openagents.cli import app; app(['agent', 'start', 'agents/plan_agent.yaml'])"
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   全部启动完毕！
echo   Studio: http://localhost:8700/studio/
echo   MCP Server: stdio 模式运行中
echo ========================================
echo.
echo 按任意键打开浏览器...
pause >nul
start http://localhost:8700/studio/messaging
