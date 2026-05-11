@echo off
chcp 65001 >nul
REM =============================================================================
REM AI Agent 服务停止脚本 (Windows)
REM =============================================================================

setlocal enabledelayedexpansion

echo [INFO] 停止 AI Agent 服务...

REM 停止 gunicorn 进程
taskkill /F /IM "gunicorn.exe" >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Gunicorn 已停止
)

REM 停止可能的 uvicorn 进程
taskkill /F /FI "WINDOWTITLE eq AI-Agent*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq AI-Agent-Dev*" >nul 2>&1

REM 停止 Python 进程（如果是启动脚本直接启动的）
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq AI-Agent*" /FO LIST ^| findstr "PID:"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [INFO] 服务已停止
pause
